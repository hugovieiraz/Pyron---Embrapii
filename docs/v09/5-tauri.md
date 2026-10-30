# Pyron 0.9 · F5 · Pyron desktop (Tauri v2)

Data: 30/10/2026. Sem commit (pedido do usuário); mesmo branch `v09-f1-servidor`.
Máquina: Acer Nitro AN515-55, Windows 11 10.0.26200, **Controle Inteligente de Aplicativos desligado** (registro
`VerifiedAndReputablePolicyState = 0`, só lido). Rust 1.99.1 (instalado pelo usuário), Visual Studio Build Tools 2022
17.14 com o compilador C++ x64 e o SDK do Windows 11 (instalados nesta fase, com aprovação, pelo winget). Tauri 2.12.5.

## Resumo em 3 linhas

1. Feito: `desktop/` com o Pyron desktop (Tauri v2), cliente fino do servidor local (sobe o Python do `.venv` num Job
   Object) ou remoto (`https://`); adaptador `js/janela.js` para os três hospedeiros; bandeja; aviso do Windows para alerta novo.
2. Conferido neste computador: modo local e remoto abrem; o Python não sobra depois de fechar nem com fim de tarefa; queda
   do Python mostra o erro e "Reiniciar" volta; segunda abertura só traz a janela para a frente.
3. Pendente: **assinatura** e o teste numa máquina com o Controle Inteligente ligado (aceite do plano); licenças indiretas
   do Tauri fora de MIT/Apache para aprovar; bandeja e aviso do Windows sem conferência automatizada.
   O `Pyron.exe` em C# continua o padrão; nada foi apagado.

## Como fica

```
desktop/
  abertura/            tela de abertura (conteúdo do próprio executável): index.html, abertura.css, abertura.js
    gerado/            cópias feitas pelo build.rs: tokens.css, base.css, componentes.css, textos.js, icones.js, logo (fora do git)
  src-tauri/
    Cargo.toml         tauri 2 (tray-icon), tauri-plugin-single-instance, tauri-plugin-notification, serde, windows-sys
    build.rs           copia o que a abertura usa de app/ e o ícone de marca/pyron.ico; declara o comando "reiniciar"
    tauri.conf.json    sem janelas declaradas (a janela nasce no main.rs com os filtros de navegação), CSP da abertura
    capabilities/abertura.json   arrastar, minimizar, fechar e reiniciar, só para a abertura
    src/main.rs        configuração, janela, permissões da página do servidor, bandeja, ciclo de vida
    src/servidor.rs    pasta do projeto, porta, /api/saude, Job Object, subida do Python
    src/textos.rs      textos da bandeja (os da página ficam em app/interface/textos.js)
```

Compilar: `cd desktop\src-tauri` e `cargo build --release` (sem a CLI do Tauri nem Node). Primeira compilação ~3 min,
depois ~2 min com LTO. Sai `target\release\pyron-desktop.exe`, **4,8 MB** (contra ~100 KB do `Pyron.exe`).

## Comportamento

| Situação | O que acontece |
|---|---|
| Modo local (padrão) | acha a pasta (PYRON_PASTA, `projeto` em `desktop.json` ou acima do executável); se um Pyron na mesma versão já responde na porta de `dados_app/porta.txt`, só conecta; senão sobe `pythonw -m app.iniciar --porta N --sem-navegador --auto-encerrar` (argumentos fixos) dentro de um Job Object com "matar ao fechar" |
| Modo remoto | `"servidor": "https://…"` em `%APPDATA%\Pyron\desktop.json` ou `--servidor <url>`; aceita `https` ou `http` só para 127.0.0.1/localhost; a janela vai direto ao servidor |
| Permissões da página do servidor | criadas em tempo de execução só para a origem configurada: minimizar, maximizar, fechar, estado, arrastar, eventos e aviso (`PERMISSOES_DO_SERVIDOR`). Sem shell, sem arquivos, sem o comando do aplicativo |
| Navegação | a janela só mostra a abertura e a origem do servidor; outro endereço abre no navegador do usuário. Janela nova da mesma origem (PDF do laudo, `blob:`) abre à parte |
| Queda do Python | a janela volta à abertura com "O servidor do Pyron parou.", o caminho do `servidor.log` e "Reiniciar" |
| Fechar | pede `/api/encerrar`, espera até 5 s e o Job encerra o que sobrar |
| Fim de tarefa | o Windows fecha o Job e encerra o Python (o lançador do `.venv` e o Python de verdade) |
| Segunda abertura | `tauri-plugin-single-instance`: traz a janela existente para a frente |
| Bandeja | Abrir o Pyron, Monitoramento (marcado conforme `/api/status`; a página liga ou desliga pela API, com a sessão e a permissão de quem está nela) e Sair |
| Alerta novo | a casca compara `alertas_pendentes` a cada 30 s e, no Pyron desktop, pede o aviso do Windows (a primeira contagem não avisa) |

`casca.js` não fala mais direto com `chrome.webview`: `js/janela.js` devolve o hospedeiro (Tauri, WebView2 do Pyron.exe ou
nenhum) com os mesmos `pedir`, `aoMudar`, e, no Tauri, `arrastar`, `notificar`, `ouvir` e `contar`. O Pyron.exe recebe
exatamente as mesmas mensagens `janela:*` de antes.

### Desvio do plano, de propósito

O plano pedia o Python "por comando com escopo no plugin shell". O Python sobe pelo próprio Rust (`std::process`), com
argumentos fixos, e o plugin shell não entra: assim nem a abertura nem a página têm qualquer permissão de shell, e há uma
dependência a menos.

## Conferido

| Bateria | Resultado |
|---|---|
| `node --test testes/js/janela.test.mjs` (8, rodado pelo `testes/test_janela.py`) | navegador sem hospedeiro; Tauri: botões, estado, arraste, aviso, eventos; Pyron.exe: mensagens de antes; Tauri tem prioridade; arraste fora dos controles; alertas novos |
| `testes/test_janela.py` (5) | capability da abertura mínima; página do servidor só com janela, eventos e aviso; sem plugins shell/fs/opener/process; argumentos fixos; versão igual no Cargo e no Tauri |
| Modo local, cache frio | servidor responde em 13 s; janela maximizada com o Painel e os botões do Pyron (`capturas/f5/local-painel.jpg`) |
| Fim de tarefa no `pyron-desktop.exe` | os dois processos do Python (lançador do `.venv` e Python 3.12) somem em menos de 2 s |
| Queda do Python com a janela aberta | abertura com o erro e "Reiniciar" (`capturas/f5/servidor-parou.jpg`); "Reiniciar" sobe de novo |
| Fechar pela janela | aplicativo e Python saem |
| Segunda abertura | continua um processo só |
| Endereço inválido (`http://exemplo.com`) | erro com o endereço e "Tentar de novo" (`capturas/f5/endereco-invalido.jpg`) |
| Remoto (`--servidor http://127.0.0.1:8790/#pendencias`, servidor subido à parte) | abre na tela pedida, com os botões da janela (`capturas/f5/remoto-pendencias.jpg`); ao fechar, o servidor de fora continua no ar |
| Não conferido por automação | menu da bandeja, aviso do Windows, arraste pelo topo e abertura do PDF do laudo em janela à parte: conferir à mão |

## Licenças

Diretas: Tauri, plugins, serde, windows-sys (MIT/Apache 2.0). Build Tools: licença Microsoft (aprovada em 30/10/2026).
`cargo metadata` resolve 262 crates; 28 têm licenças fora de MIT/Apache, todas permissivas e presentes em qualquer
aplicativo Tauri: **MPL-2.0** (cssparser, cssparser-macros, selectors, dtoa-short, option-ext; uso sem modificação),
**Unicode-3.0** (icu_*, zerovec, yoke, tinystr…, via `url`), **BSD-3-Clause** (alloc-stdlib, alloc-no-stdlib, via brotli)
e **Zlib** (foldhash, zlib-rs). **Esperando aprovação** antes de distribuir o executável.

## Pendências e decisões suas

- **Assinatura e Controle Inteligente:** o aceite do plano ("binário assinado abre sem bloqueio numa máquina com o
  Controle Inteligente ligado") não dá para conferir aqui: ele está desligado neste computador e não há certificado. O
  executável de 4,8 MB sem assinatura tende a ser barrado como foi o `Pyron.exe` de 390 KB. Caminhos: GitHub Actions +
  Azure Trusted Signing ou certificado OV/EV. Até lá, o `Pyron.exe` em C# continua o padrão.
- **Licenças indiretas** acima.
- **Conferência à mão** da bandeja, do aviso do Windows, do arraste e do PDF.
- **Espaço:** `desktop\src-tauri\target` ocupa 1,3 GB (compilação); pode ser apagado e refeito com `cargo build --release`.
