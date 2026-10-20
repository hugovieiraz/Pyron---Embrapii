"""Abre o aplicativo de apresentação: sobe o servidor local e mostra a janela (Edge em modo aplicativo).

Uso, na pasta do projeto: ``.venv\\Scripts\\pythonw.exe -m apresentacao`` (o atalho "Pyron
Apresentação" da área de trabalho faz isso). O servidor desliga sozinho quando a janela fecha.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

EDGE = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
]
# A janela manda um sinal a cada 10 s. Escondida (minimizada, coberta pelo PowerPoint em tela cheia, tela
# bloqueada), o Edge segura os relógios da página e o sinal chega no máximo uma vez por minuto: por isso o
# servidor vigia o processo da janela e só usa o sinal quando não tem esse processo para olhar.
SEM_SINAL_S = 300
SEM_SINAL_PRESO_S = 3 * 3600  # com o processo da janela vivo: 3 h sem sinal nenhum
ENTREGOU_S = 10  # o Edge que termina antes disso só entregou a janela a outro Edge aberto
SEM_JANELA_S = 600  # ninguém abriu a janela


def porta_livre(inicio: int = 8770) -> int:
    for porta in range(inicio, inicio + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", porta)) != 0:
                return porta
    raise RuntimeError("Nenhuma porta livre entre 8770 e 8789.")


def abrir_janela(url: str) -> subprocess.Popen | None:
    """Abre a janela; devolve o processo do Edge (None se abriu no navegador padrão)."""
    for edge in EDGE:
        if edge.exists():
            return subprocess.Popen(
                # maximizada: ocupa a área útil da tela que estiver em uso. Um tamanho fixo maior que a tela (1480 × 920
                # numa tela de 1536 × 816) deixa o pé da página fora da tela, sem barra para rolar até lá.
                [str(edge), f"--app={url}", f"--user-data-dir={AQUI / '.janela'}", "--start-maximized",
                 "--no-first-run", "--no-default-browser-check", "--disable-features=Translate",
                 "--disable-component-update"],  # sem os ~500 MB de componentes que o Edge baixa sozinho
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    webbrowser.open(url)
    return None


def deve_desligar(agora: float, inicio: float, ultimo_sinal: float, janela: dict) -> bool:
    """A janela fechou? Sem confundir janela escondida (sinal lento) com janela fechada."""
    sem_sinal = agora - (ultimo_sinal or inicio)
    proc = janela.get("proc")
    if proc is not None and proc.poll() is None:
        # a janela está aberta, mesmo escondida; só um Edge preso em segundo plano passa tanto tempo calado
        return sem_sinal > SEM_SINAL_PRESO_S
    if proc is not None and janela.setdefault("terminou_em", agora) - janela["aberta_em"] > ENTREGOU_S:
        return True  # o Edge desta janela rodou e terminou: a janela foi fechada
    # sem processo para olhar (navegador padrão, ou o Edge entregou a janela a outro já aberto): fica o sinal
    if ultimo_sinal == 0.0:
        return agora - inicio > SEM_JANELA_S
    return sem_sinal > SEM_SINAL_S


def vigiar(servidor, sinais: dict, inicio: float, janela: dict) -> None:
    while not servidor.should_exit:
        time.sleep(2)
        servidor.should_exit = deve_desligar(time.time(), inicio, sinais["ultimo"], janela)


def main() -> None:
    sem_janela = "--sem-janela" in sys.argv  # diagnóstico: só o servidor, o endereço vai para o registro
    sem_console = sys.stdout is None or "pythonw" in Path(sys.executable).name.lower()
    if sem_console:
        registro = open(AQUI / "registro.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = registro
    print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} início")

    import uvicorn

    from apresentacao import servidor as srv

    srv.iniciar_carga()
    porta = porta_livre()
    url = f"http://127.0.0.1:{porta}"
    print("Pyron · Apresentação em", url)
    config = uvicorn.Config(srv.app, host="127.0.0.1", port=porta, log_level="warning", log_config=None)
    servidor = uvicorn.Server(config)
    janela: dict = {"proc": None, "fechou_em": 0.0}
    threading.Thread(target=vigiar, args=(servidor, srv.sinais, time.time(), janela), daemon=True).start()

    def abrir_quando_pronto() -> None:
        for _ in range(150):
            if servidor.started:
                if not sem_janela:
                    janela["aberta_em"] = time.time()
                    janela["proc"] = abrir_janela(url)
                return
            time.sleep(0.1)

    threading.Thread(target=abrir_quando_pronto, daemon=True).start()
    servidor.run()
    print(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} fim")


if __name__ == "__main__":
    main()
