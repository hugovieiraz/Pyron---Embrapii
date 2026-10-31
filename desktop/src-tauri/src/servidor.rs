// Servidor local do modo local: acha a pasta do Pyron, sobe o pythonw do .venv com argumentos fixos e o amarra a um
// Job Object do Windows. O Job fecha junto com este processo (inclusive no "Finalizar tarefa"), e o Windows encerra
// o Python e tudo o que ele abriu. Mesma regra do lancador/Pyron.cs: porta salva em dados_app/porta.txt, servidor já
// no ar na mesma versão é reaproveitado (sem Job: não foi este processo que o subiu).

use std::fs;
use std::io::{Read, Write};
use std::net::{Ipv4Addr, SocketAddrV4, TcpListener, TcpStream};
use std::os::windows::io::AsRawHandle;
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::time::Duration;

use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
use windows_sys::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation, SetInformationJobObject,
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};
use windows_sys::Win32::System::Threading::CREATE_NO_WINDOW;

pub const PORTA_INICIAL: u16 = 8765;
pub const ESPERA_MAXIMA: Duration = Duration::from_secs(120);

/// A pasta do Pyron: PYRON_PASTA, o campo "projeto" de desktop.json ou uma pasta acima do executável
/// (desktop/src-tauri/target/release fica quatro níveis abaixo da raiz).
pub fn localizar_projeto(configurado: Option<&str>) -> Option<PathBuf> {
    let mut candidatos: Vec<PathBuf> = Vec::new();
    if let Ok(p) = std::env::var("PYRON_PASTA") {
        candidatos.push(p.into());
    }
    if let Some(p) = configurado {
        candidatos.push(p.into());
    }
    if let Ok(exe) = std::env::current_exe() {
        candidatos.extend(exe.ancestors().skip(1).take(6).map(Path::to_path_buf));
    }
    candidatos.into_iter().find(|c| c.join("app").join("iniciar.py").is_file())
}

pub fn python(projeto: &Path) -> PathBuf {
    projeto.join(".venv").join("Scripts").join("pythonw.exe")
}

pub fn pasta_dados(projeto: &Path) -> PathBuf {
    projeto.join("app").join("dados_app")
}

pub fn porta_salva(projeto: &Path) -> u16 {
    fs::read_to_string(pasta_dados(projeto).join("porta.txt"))
        .ok()
        .and_then(|t| t.trim().parse().ok())
        .unwrap_or(PORTA_INICIAL)
}

pub fn salvar_porta(projeto: &Path, porta: u16) {
    let pasta = pasta_dados(projeto);
    let _ = fs::create_dir_all(&pasta);
    let _ = fs::write(pasta.join("porta.txt"), porta.to_string());
}

pub fn porta_livre() -> u16 {
    (PORTA_INICIAL..PORTA_INICIAL + 30)
        .find(|p| TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, *p)).is_ok())
        .unwrap_or(PORTA_INICIAL)
}

/// Pedido HTTP mínimo ao 127.0.0.1 (sem biblioteca de HTTP: só o servidor do próprio computador).
fn pedir(porta: u16, metodo: &str, caminho: &str) -> Option<String> {
    let endereco = SocketAddrV4::new(Ipv4Addr::LOCALHOST, porta).into();
    let mut conexao = TcpStream::connect_timeout(&endereco, Duration::from_millis(800)).ok()?;
    conexao.set_read_timeout(Some(Duration::from_millis(1500))).ok()?;
    let pedido = format!("{metodo} {caminho} HTTP/1.1\r\nHost: 127.0.0.1:{porta}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
    conexao.write_all(pedido.as_bytes()).ok()?;
    let mut resposta = String::new();
    conexao.read_to_string(&mut resposta).ok()?;
    resposta.starts_with("HTTP/1.1 200").then_some(resposta)
}

/// Versão do Pyron que responde nesta porta (None se não for o Pyron).
pub fn versao_no_ar(porta: u16) -> Option<String> {
    let resposta = pedir(porta, "GET", "/api/saude")?;
    if !resposta.contains("\"Pyron\"") {
        return None;
    }
    let depois = resposta.split("\"versao\"").nth(1)?;
    Some(depois.split('"').nth(1)?.to_string())
}

/// A constante VERSAO de app/servidor.py.
pub fn versao_do_projeto(projeto: &Path) -> Option<String> {
    let codigo = fs::read_to_string(projeto.join("app").join("servidor.py")).ok()?;
    let linha = codigo.lines().find(|l| l.starts_with("VERSAO = \""))?;
    Some(linha.split('"').nth(1)?.to_string())
}

pub fn pedir_encerramento(porta: u16) {
    let _ = pedir(porta, "POST", "/api/encerrar");
}

/// Job Object com "matar ao fechar": o último handle fecha quando este processo sai, de qualquer jeito.
pub struct Job(HANDLE);

// O handle só é usado para fechar; o Windows aceita isso de qualquer thread.
unsafe impl Send for Job {}

impl Job {
    fn novo() -> std::io::Result<Job> {
        unsafe {
            let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if job.is_null() {
                return Err(std::io::Error::last_os_error());
            }
            let mut limites: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            limites.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let ok = SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &limites as *const _ as *const _,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );
            if ok == 0 {
                let erro = std::io::Error::last_os_error();
                CloseHandle(job);
                return Err(erro);
            }
            Ok(Job(job))
        }
    }

    fn amarrar(&self, filho: &Child) -> std::io::Result<()> {
        let ok = unsafe { AssignProcessToJobObject(self.0, filho.as_raw_handle() as HANDLE) };
        if ok == 0 {
            return Err(std::io::Error::last_os_error());
        }
        Ok(())
    }
}

impl Drop for Job {
    fn drop(&mut self) {
        unsafe { CloseHandle(self.0) };
    }
}

/// Sobe `pythonw -m app.iniciar --porta N --sem-navegador --auto-encerrar` sem console, já dentro do Job.
pub fn subir(projeto: &Path, porta: u16) -> std::io::Result<(Child, Job)> {
    let job = Job::novo()?;
    let porta = porta.to_string();
    let mut filho = Command::new(python(projeto))
        .args(["-m", "app.iniciar", "--porta", &porta, "--sem-navegador", "--auto-encerrar"])
        .current_dir(projeto)
        .creation_flags(CREATE_NO_WINDOW)
        .spawn()?;
    // O Python leva centenas de milissegundos para abrir qualquer outro processo; os que ele abrir depois já
    // nascem dentro do Job.
    if let Err(erro) = job.amarrar(&filho) {
        let _ = filho.kill();
        return Err(erro);
    }
    Ok((filho, job))
}
