// Pyron desktop (0.9, F5): janela Tauri v2 sem barra do Windows, cliente fino do servidor do Pyron.
//
// Modo local (padrão): sobe o Python do .venv (servidor.rs), mostra a abertura (desktop/abertura) até /api/saude
// responder e então carrega http://127.0.0.1:<porta>. Modo remoto: "servidor" em %APPDATA%\Pyron\desktop.json (ou
// --servidor <url>) e a janela carrega https://<servidor> direto.
//
// Segurança: a página do servidor só ganha o que está em PERMISSOES_DO_SERVIDOR, e só para a origem configurada
// (capability criada aqui, em tempo de execução). Nada de shell nem de arquivos para conteúdo remoto. Endereço de fora
// abre no navegador do usuário; a janela nunca navega para outra origem.
//
// O lancador/ em C# (Pyron.exe) continua sendo o padrão até este executável, assinado, passar no Controle Inteligente
// de Aplicativos das máquinas de destino (docs/v09/5-tauri.md).

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod servidor;
mod textos;

use std::collections::HashSet;
use std::path::PathBuf;
use std::process::Child;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::Deserialize;
use tauri::ipc::CapabilityBuilder;
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::webview::NewWindowResponse;
use tauri::{AppHandle, Emitter, Listener, Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder};

const JANELA: &str = "principal";

/// O que a página do servidor pode pedir ao Tauri: os botões da janela (casca.js), o arraste do topo, eventos da
/// bandeja e o aviso do Windows para alerta novo. testes/test_janela.py confere que nada mais entra aqui.
const PERMISSOES_DO_SERVIDOR: &[&str] = &[
    "core:window:allow-minimize",
    "core:window:allow-toggle-maximize",
    "core:window:allow-close",
    "core:window:allow-is-maximized",
    "core:window:allow-start-dragging",
    "core:event:allow-listen",
    "core:event:allow-unlisten",
    "core:event:allow-emit",
    "notification:allow-notify",
];

#[derive(Deserialize, Default)]
struct Configuracao {
    /// https://<servidor da equipe>; vazio: modo local
    servidor: Option<String>,
    /// pasta do Pyron no modo local, se não estiver acima do executável
    projeto: Option<String>,
}

/// %APPDATA%\Pyron\desktop.json; `--servidor <url>` na linha de comando vale mais.
fn ler_configuracao() -> Configuracao {
    let mut cfg: Configuracao = std::env::var("APPDATA")
        .ok()
        .and_then(|p| std::fs::read_to_string(PathBuf::from(p).join("Pyron").join("desktop.json")).ok())
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_default();
    let argumentos: Vec<String> = std::env::args().collect();
    if let Some(i) = argumentos.iter().position(|a| a == "--servidor") {
        cfg.servidor = argumentos.get(i + 1).cloned();
    }
    cfg.servidor = cfg.servidor.filter(|s| !s.trim().is_empty());
    cfg
}

/// Endereço remoto aceito: https, ou http só para este computador.
fn endereco_valido(texto: &str) -> Option<Url> {
    let url = Url::parse(texto.trim()).ok()?;
    let local = matches!(url.host_str(), Some("127.0.0.1") | Some("localhost"));
    (url.scheme() == "https" || (url.scheme() == "http" && local)).then_some(url)
}

struct Local {
    porta: u16,
    geracao: u64,
    filho: Child,
    _job: servidor::Job,
}

struct Estado {
    cfg: Configuracao,
    /// origem do servidor que a janela pode mostrar (e a única com permissões)
    origem: Arc<Mutex<Option<String>>>,
    liberadas: Mutex<HashSet<String>>,
    local: Mutex<Option<Local>>,
    projeto: Mutex<Option<PathBuf>>,
    geracao: AtomicU64,
    saindo: AtomicBool,
}

fn estado(app: &AppHandle) -> tauri::State<'_, Estado> {
    app.state::<Estado>()
}

// ---------------------------------------------------------------- janela

fn mostrar(app: &AppHandle) {
    if let Some(j) = app.get_webview_window(JANELA) {
        let _ = j.unminimize();
        let _ = j.show();
        let _ = j.set_focus();
    }
}

/// A abertura (conteúdo do próprio executável), com o erro e o detalhe na URL.
fn abertura(app: &AppHandle, erro: Option<(&str, &str)>) {
    let Some(j) = app.get_webview_window(JANELA) else { return };
    let mut url = Url::parse("http://tauri.localhost/index.html").expect("url fixa");
    if let Some((codigo, detalhe)) = erro {
        url.query_pairs_mut().append_pair("erro", codigo).append_pair("detalhe", detalhe);
        if let Some(p) = estado(app).projeto.lock().unwrap().as_ref() {
            let registro = servidor::pasta_dados(p).join("servidor.log");
            url.query_pairs_mut().append_pair("registro", &registro.to_string_lossy());
        }
    }
    let _ = j.navigate(url);
}

/// Libera as permissões para a origem do servidor e carrega a página.
fn abrir_servidor(app: &AppHandle, url: Url) {
    let origem = url.origin().ascii_serialization();
    *estado(app).origem.lock().unwrap() = Some(origem.clone());
    let nova = estado(app).liberadas.lock().unwrap().insert(origem.clone());
    if nova {
        let mut cap = CapabilityBuilder::new(format!("servidor-{}", estado(app).liberadas.lock().unwrap().len()))
            .remote(format!("{origem}/*"))
            .local(false)
            .window(JANELA);
        for p in PERMISSOES_DO_SERVIDOR {
            cap = cap.permission(*p);
        }
        if let Err(e) = app.add_capability(cap) {
            abertura(app, Some(("iniciar", &e.to_string())));
            return;
        }
    }
    if let Some(j) = app.get_webview_window(JANELA) {
        let _ = j.navigate(url);
    }
}

/// A janela só mostra a abertura e o servidor configurado; o resto vai para o navegador do usuário.
fn permitido(origem: &Arc<Mutex<Option<String>>>, url: &Url) -> bool {
    if url.host_str() == Some("tauri.localhost") || url.scheme() == "tauri" || url.scheme() == "about" {
        return true;
    }
    let destino = url.origin().ascii_serialization();
    origem.lock().unwrap().as_deref() == Some(destino.as_str())
}

fn abrir_fora(url: &Url) {
    if !matches!(url.scheme(), "http" | "https" | "mailto") {
        return;
    }
    use windows_sys::Win32::UI::Shell::ShellExecuteW;
    use windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;
    let largo = |s: &str| s.encode_utf16().chain(Some(0)).collect::<Vec<u16>>();
    let (verbo, alvo) = (largo("open"), largo(url.as_str()));
    unsafe {
        ShellExecuteW(std::ptr::null_mut(), verbo.as_ptr(), alvo.as_ptr(), std::ptr::null(), std::ptr::null(), SW_SHOWNORMAL);
    }
}

// ---------------------------------------------------------------- servidor local

fn abrir(app: AppHandle) {
    let Some(texto) = estado(&app).cfg.servidor.clone() else {
        abrir_local(&app);
        return;
    };
    match endereco_valido(&texto) {
        Some(url) => abrir_servidor(&app, url),
        None => abertura(&app, Some(("endereco", &texto))),
    }
}

fn abrir_local(app: &AppHandle) {
    let Some(projeto) = servidor::localizar_projeto(estado(app).cfg.projeto.as_deref()) else {
        abertura(app, Some(("projeto", "")));
        return;
    };
    *estado(app).projeto.lock().unwrap() = Some(projeto.clone());

    // Um servidor do Pyron já no ar, na versão desta pasta (aberto pelo Pyron.exe, por exemplo): só conecta.
    let salva = servidor::porta_salva(&projeto);
    if let Some(no_ar) = servidor::versao_no_ar(salva) {
        let do_projeto = servidor::versao_do_projeto(&projeto);
        if do_projeto.is_none() || do_projeto.as_deref() == Some(no_ar.as_str()) {
            abrir_servidor(app, url_local(salva));
            return;
        }
        // versão antiga na memória: ela sai e a nova sobe
        servidor::pedir_encerramento(salva);
        let limite = Instant::now() + Duration::from_secs(15);
        while Instant::now() < limite && servidor::versao_no_ar(salva).is_some() {
            std::thread::sleep(Duration::from_millis(250));
        }
    }

    let python = servidor::python(&projeto);
    if !python.is_file() {
        abertura(app, Some(("python", &python.to_string_lossy())));
        return;
    }
    let porta = servidor::porta_livre();
    let (filho, job) = match servidor::subir(&projeto, porta) {
        Ok(par) => par,
        Err(e) => {
            abertura(app, Some(("iniciar", &e.to_string())));
            return;
        }
    };
    servidor::salvar_porta(&projeto, porta);
    let geracao = estado(app).geracao.fetch_add(1, Ordering::SeqCst) + 1;
    // trocar o anterior fecha o Job dele, e o Windows encerra aquele Python
    *estado(app).local.lock().unwrap() = Some(Local { porta, geracao, filho, _job: job });

    let inicio = Instant::now();
    loop {
        if servidor::versao_no_ar(porta).is_some() {
            break;
        }
        if terminou(app, geracao) {
            abertura(app, Some(("parou", "")));
            return;
        }
        if inicio.elapsed() > servidor::ESPERA_MAXIMA {
            abertura(app, Some(("demorou", "")));
            return;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    abrir_servidor(app, url_local(porta));
    vigiar(app.clone(), geracao);
}

fn url_local(porta: u16) -> Url {
    Url::parse(&format!("http://127.0.0.1:{porta}/")).expect("url local")
}

/// O Python desta geração já saiu?
fn terminou(app: &AppHandle, geracao: u64) -> bool {
    let estado = estado(app);
    let mut local = estado.local.lock().unwrap();
    match local.as_mut() {
        Some(l) if l.geracao == geracao => !matches!(l.filho.try_wait(), Ok(None)),
        _ => true,
    }
}

/// Se o Python cair com a janela aberta, a janela mostra o erro e oferece "Reiniciar".
fn vigiar(app: AppHandle, geracao: u64) {
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_millis(500));
        if estado(&app).geracao.load(Ordering::SeqCst) != geracao || estado(&app).saindo.load(Ordering::SeqCst) {
            return;
        }
        if terminou(&app, geracao) {
            abertura(&app, Some(("parou", "")));
            return;
        }
    });
}

/// Fim do aplicativo: pede ao Python para sair (fecha o banco com calma) e, depois de 5 s, o Job encerra o que sobrar.
fn encerrar_local(app: &AppHandle) {
    estado(app).saindo.store(true, Ordering::SeqCst);
    let Some(mut local) = estado(app).local.lock().unwrap().take() else { return };
    servidor::pedir_encerramento(local.porta);
    let limite = Instant::now() + Duration::from_secs(5);
    while Instant::now() < limite && matches!(local.filho.try_wait(), Ok(None)) {
        std::thread::sleep(Duration::from_millis(100));
    }
}

/// "Reiniciar" da abertura: derruba o Python desta janela (se ainda houver) e começa de novo.
#[tauri::command]
fn reiniciar(app: AppHandle) {
    estado(&app).geracao.fetch_add(1, Ordering::SeqCst);
    *estado(&app).local.lock().unwrap() = None;
    abertura(&app, None);
    std::thread::spawn(move || abrir(app));
}

// ---------------------------------------------------------------- bandeja

fn montar_bandeja(app: &AppHandle) -> tauri::Result<()> {
    let abrir_item = MenuItem::with_id(app, "abrir", textos::ABRIR, true, None::<&str>)?;
    let monitor = CheckMenuItem::with_id(app, "monitoramento", textos::MONITORAMENTO, true, false, None::<&str>)?;
    let sair = MenuItem::with_id(app, "sair", textos::SAIR, true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&abrir_item, &monitor, &PredefinedMenuItem::separator(app)?, &sair])?;
    let mut bandeja = TrayIconBuilder::with_id("bandeja")
        .tooltip(textos::TITULO)
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, ev| match ev.id().as_ref() {
            "abrir" => mostrar(app),
            // quem liga ou desliga é a página (casca.js), com a sessão e as permissões de quem está nela
            "monitoramento" => {
                let _ = app.emit_to(JANELA, "bandeja:monitoramento", ());
            }
            "sair" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|bandeja, ev| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = ev {
                mostrar(bandeja.app_handle());
            }
        });
    if let Some(icone) = app.default_window_icon() {
        bandeja = bandeja.icon(icone.clone());
    }
    bandeja.build(app)?;
    // a página conta o estado do monitoramento a cada atualização da barra e depois de cada troca
    let marcado = monitor.clone();
    app.listen("pyron:monitoramento", move |ev| {
        let _ = marcado.set_checked(ev.payload() == "true");
    });
    Ok(())
}

// ---------------------------------------------------------------- início

fn main() {
    let estado_inicial = Estado {
        cfg: ler_configuracao(),
        origem: Arc::new(Mutex::new(None)),
        liberadas: Mutex::new(HashSet::new()),
        local: Mutex::new(None),
        projeto: Mutex::new(None),
        geracao: AtomicU64::new(0),
        saindo: AtomicBool::new(false),
    };
    let origem = estado_inicial.origem.clone();

    let app = tauri::Builder::default()
        // a segunda abertura só traz a janela da primeira para a frente
        .plugin(tauri_plugin_single_instance::init(|app, _argumentos, _pasta| mostrar(app)))
        .plugin(tauri_plugin_notification::init())
        .manage(estado_inicial)
        .invoke_handler(tauri::generate_handler![reiniciar])
        .setup(move |app| {
            let navegacao = origem.clone();
            let janela_nova = origem.clone();
            WebviewWindowBuilder::new(app, JANELA, WebviewUrl::App("index.html".into()))
                .title(textos::TITULO)
                .inner_size(1280.0, 800.0)
                .min_inner_size(800.0, 560.0)
                .decorations(false)
                .maximized(true)
                .on_navigation(move |url| {
                    let ok = permitido(&navegacao, url);
                    if !ok {
                        abrir_fora(url);
                    }
                    ok
                })
                // PDF do laudo (blob: do próprio servidor) abre numa janela à parte; endereço de fora, no navegador
                .on_new_window(move |url, _recursos| {
                    if permitido(&janela_nova, &url) {
                        NewWindowResponse::Allow
                    } else {
                        abrir_fora(&url);
                        NewWindowResponse::Deny
                    }
                })
                .build()?;
            montar_bandeja(app.handle())?;
            let handle = app.handle().clone();
            std::thread::spawn(move || abrir(handle));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Pyron desktop");

    app.run(|app, ev| {
        if let RunEvent::Exit = ev {
            encerrar_local(app);
        }
    });
}
