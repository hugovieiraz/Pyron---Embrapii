"""Abre o Pyron: sobe o servidor local e mostra a interface.

Uso (na pasta do projeto):

    python -m app.iniciar                 # abre no navegador padrão; encerre fechando o console
    python -m app.iniciar --janela        # janela própria (Edge em modo aplicativo)
    python -m app.iniciar --porta 8765 --sem-navegador --auto-encerrar   # usado pelo Pyron.exe

Com ``--auto-encerrar``, o servidor se desliga sozinho quando a interface é fechada: a página
manda um sinal a cada 20 s e avisa ao sair (``/api/sinal``).
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

EDGE = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
]


def porta_livre(inicio: int = 8765) -> int:
    for porta in range(inicio, inicio + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", porta)) != 0:
                return porta
    raise RuntimeError("Nenhuma porta livre entre 8765 e 8784.")


def abrir_janela(url: str, pasta_perfil: Path) -> None:
    """Janela sem barra de endereço (Edge --app); sem Edge, o navegador padrão."""
    for edge in EDGE:
        if edge.exists():
            subprocess.Popen(
                [
                    str(edge),
                    f"--app={url}",
                    f"--user-data-dir={pasta_perfil}",
                    "--window-size=1480,920",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-features=Translate",
                ],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return
    webbrowser.open(url)


def deve_encerrar(sinais: dict, agora: float, inicio: float, vazio_desde: float | None) -> tuple[bool, float | None]:
    """Decide se o servidor pode sair. Devolve (sair, desde quando não há janela aberta).

    Janelas que somem sem avisar (queda, suspensão) expiram após 180 s sem sinal: janela
    minimizada pode ter os temporizadores limitados a um disparo por minuto pelo navegador.
    Uma recarga de página (aviso de saída seguido de novo sinal) cabe na tolerância de 8 s.
    """
    if sinais.get("encerrar"):
        return True, vazio_desde
    clientes = sinais["clientes"]
    for cliente, visto in list(clientes.items()):
        if agora - visto > 180:
            clientes.pop(cliente, None)
    if not sinais.get("algum"):
        return agora - inicio > 600, vazio_desde  # ninguém abriu a interface
    if clientes:
        return False, None
    vazio_desde = vazio_desde or agora
    return agora - vazio_desde > 8, vazio_desde


def vigiar(servidor, sinais: dict, inicio: float) -> None:
    """Desliga o servidor quando a última janela do aplicativo é fechada."""
    vazio_desde = None
    while not servidor.should_exit:
        time.sleep(2)
        sair, vazio_desde = deve_encerrar(sinais, time.time(), inicio, vazio_desde)
        if sair:
            servidor.should_exit = True


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Abre o Pyron.")
    ap.add_argument("--porta", type=int, default=0)
    ap.add_argument("--janela", action="store_true", help="abrir em janela própria (Edge em modo aplicativo)")
    ap.add_argument("--sem-navegador", action="store_true", help="só o servidor (o Pyron.exe abre a janela)")
    ap.add_argument("--auto-encerrar", action="store_true", help="desligar quando a interface for fechada")
    args = ap.parse_args(argv)

    from app import servidor as srv

    if args.auto_encerrar:
        # Sem console (pythonw): mensagens e erros vão para um arquivo de registro.
        srv.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        registro = open(srv.PASTA_DADOS / "servidor.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = registro
        print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} início")

    import uvicorn

    porta = args.porta or porta_livre()
    url = f"http://127.0.0.1:{porta}"
    print("Pyron", srv.VERSAO)
    print(f"Endereço: {url}. Para encerrar, feche a janela do aplicativo{'' if args.auto_encerrar else ' e este console'}.")

    config = uvicorn.Config(srv.app, host="127.0.0.1", port=porta, log_level="warning", log_config=None if args.auto_encerrar else uvicorn.config.LOGGING_CONFIG)
    servidor = uvicorn.Server(config)
    if args.auto_encerrar:
        threading.Thread(target=vigiar, args=(servidor, srv.sinais, time.time()), daemon=True).start()

    if not args.sem_navegador:

        def abrir_quando_pronto() -> None:
            for _ in range(150):
                if servidor.started:
                    if args.janela:
                        abrir_janela(url, srv.PASTA_DADOS / "janela")
                    else:
                        webbrowser.open(url)
                    return
                time.sleep(0.1)

        threading.Thread(target=abrir_quando_pronto, daemon=True).start()

    servidor.run()
    print(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} fim")


if __name__ == "__main__":
    main()
