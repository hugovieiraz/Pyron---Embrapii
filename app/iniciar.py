"""Abre o Pyron: sobe o servidor local e mostra a interface.

Uso (na pasta do projeto):

    python -m app.iniciar                 # abre no navegador padrão; encerre fechando o console
    python -m app.iniciar --janela        # janela própria (Edge em modo aplicativo)
    python -m app.iniciar --porta 8765 --sem-navegador --auto-encerrar   # usado pelo Pyron.exe

Com ``--auto-encerrar``, o servidor se desliga sozinho quando a interface é fechada: a página
manda um sinal a cada 20 s e avisa ao sair (``/api/sinal``).

Modo servidor (vários engenheiros pela rede, com login; ver ``docs/servidor/implantacao.md``)::

    python -m app.iniciar --modo servidor --porta 8765 --proxy 127.0.0.1

No modo servidor não há janela nem auto-encerrar, e ele só sobe com um administrador com senha
(``python -m app.acesso usuario ...``). O padrão continua sendo ouvir só o próprio computador
(127.0.0.1), com o Caddy na frente fazendo o HTTPS; ``--host 0.0.0.0`` só é aceito no modo servidor.
"""

from __future__ import annotations

import argparse
import json
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
                    "--start-maximized",  # tamanho fixo maior que a tela deixava o pé da página fora dela
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-features=Translate",
                ]
            )
            return
    webbrowser.open(url)


TEMA_EDGE = {"claro": 1, "escuro": 2, "sistema": 0}  # browser.theme.color_scheme2 do Chromium


def preparar_perfil_janela(pasta_perfil: Path, tema: str = "claro") -> None:
    """Acerta o perfil próprio da janela do aplicativo (dados_app/janela) antes de abri-la.

    O Edge em modo aplicativo desenha a barra de título na cor do tema dele, que segue o Windows (escuro
    neste computador) e ignora o theme-color da página: o tema vai gravado aqui, igual ao de Configurações ›
    Aparência (claro por padrão). Também apaga o tamanho e a posição que o Edge guardou da última janela,
    para ela abrir sempre maximizada. Só este perfil muda; o Edge do usuário fica como está. O Edge regrava
    o arquivo ao fechar, por isso isto roda com a janela fechada (o servidor só sobe sem janela aberta).
    """
    arquivo = pasta_perfil / "Default" / "Preferences"
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}
    except (OSError, ValueError):
        return
    navegador = dados.setdefault("browser", {})
    valor = TEMA_EDGE.get(tema, 1)
    navegador.setdefault("theme", {}).update({"color_scheme2": valor, "color_scheme": valor})
    navegador.pop("app_window_placement", None)
    try:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps(dados), encoding="utf-8")
    except OSError:
        pass


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


LOOPBACK = ("127.0.0.1", "localhost", "::1")


def conferir_argumentos(args) -> list[str]:
    """Combinações que o Pyron recusa ou ajusta. Devolve avisos; erro vira SystemExit (pelo argparse)."""
    avisos = []
    if args.modo == "local" and args.host not in LOOPBACK:
        raise ValueError("No modo local o Pyron só ouve o próprio computador. Para a rede, use --modo servidor (com login).")
    if args.modo == "local" and (args.proxy or getattr(args, "porta_proxy", 0) or getattr(args, "origem", [])):
        raise ValueError("--proxy, --porta-proxy e --origem só valem no modo servidor.")
    if args.modo == "servidor":
        if args.auto_encerrar:
            avisos.append("Modo servidor: --auto-encerrar ignorado (o servidor fica no ar até ser parado).")
            args.auto_encerrar = False
        if args.janela or not args.sem_navegador:
            args.janela, args.sem_navegador = False, True  # quem usa abre pelo navegador ou pelo tablet
    return avisos


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Abre o Pyron.")
    ap.add_argument("--porta", type=int, default=0)
    ap.add_argument("--janela", action="store_true", help="abrir em janela própria (Edge em modo aplicativo)")
    ap.add_argument("--sem-navegador", action="store_true", help="só o servidor (o Pyron.exe abre a janela)")
    ap.add_argument("--auto-encerrar", action="store_true", help="desligar quando a interface for fechada")
    ap.add_argument("--dados", help="outra pasta de dados (demonstração), no lugar de app/dados_app")
    ap.add_argument("--modo", choices=("local", "servidor"), default=os.environ.get("PYRON_MODO") or "local",
                    help="local (padrão: só este computador, sem login) ou servidor (vários usuários, com login)")
    ap.add_argument("--host", default="127.0.0.1", help="onde ouvir (padrão 127.0.0.1; 0.0.0.0 só no modo servidor)")
    ap.add_argument("--proxy", action="append", default=[],
                    help="endereço do proxy HTTPS (Caddy) cujos cabeçalhos X-Forwarded-* valem; pode repetir")
    ap.add_argument("--porta-proxy", type=int, default=int(os.environ.get("PYRON_PORTA_PROXY") or 0),
                    help="segunda porta, só em 127.0.0.1, para o proxy HTTPS (tailscale serve): tudo que chega por ela é de fora")
    ap.add_argument("--origem", action="append", default=[],
                    help="endereço público aceito no cabeçalho Origin (ex.: https://pyron.tail1234.ts.net); pode repetir")
    args = ap.parse_args(argv)
    try:
        avisos = conferir_argumentos(args)
    except ValueError as erro:
        ap.error(str(erro))
    if args.dados:
        os.environ["PYRON_DADOS"] = str(Path(args.dados).resolve())
    os.environ["PYRON_MODO"] = args.modo

    from app import acesso
    from app import servidor as srv

    acesso.configurar(args.modo, args.proxy or [p for p in os.environ.get("PYRON_PROXY", "").split(",") if p.strip()],
                      porta_proxy=args.porta_proxy or None,
                      origens=args.origem or [o for o in os.environ.get("PYRON_ORIGEM", "").split(",") if o.strip()])
    if args.modo == "servidor" and (falta := acesso.falta_para_servidor(srv._config()["responsaveis"])):
        ap.exit(2, falta + "\n")

    if args.auto_encerrar:
        # Sem console (pythonw): mensagens e erros vão para um arquivo de registro.
        srv.PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        registro = open(srv.PASTA_DADOS / "servidor.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = registro
        print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} início")

    import uvicorn

    if args.modo == "local":
        preparar_perfil_janela(srv.PASTA_DADOS / "janela", srv._config().get("tema", "claro"))
    porta = args.porta or porta_livre()
    url = f"http://127.0.0.1:{porta}"
    print("Pyron", srv.VERSAO, "· modo servidor" if args.modo == "servidor" else "")
    for aviso in avisos:
        print(aviso)
    if args.modo == "servidor":
        print(f"Ouvindo em {args.host}:{porta}. Proxy confiável: {', '.join(sorted(acesso._estado['proxies'])) or 'nenhum'}."
              + (f" Porta do proxy: 127.0.0.1:{args.porta_proxy}." if args.porta_proxy else "")
              + " Para encerrar, Ctrl+C ou pare o serviço.")
    else:
        print(f"Endereço: {url}. Para encerrar, feche a janela do aplicativo{'' if args.auto_encerrar else ' e este console'}.")

    # No modo servidor, os cabeçalhos do proxy são lidos por app.acesso (só do --proxy): o uvicorn não os aplica.
    config = uvicorn.Config(srv.app, host=args.host, port=porta, log_level="warning",
                            log_config=None if args.auto_encerrar else uvicorn.config.LOGGING_CONFIG,
                            proxy_headers=args.modo == "local")
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

    if args.porta_proxy:
        # duas portas no mesmo processo: a principal e a do proxy (só no próprio computador)
        soquetes = []
        for endereco in ((args.host, porta), ("127.0.0.1", args.porta_proxy)):
            s = socket.socket(socket.AF_INET6 if ":" in endereco[0] else socket.AF_INET, socket.SOCK_STREAM)
            s.bind(endereco)
            soquetes.append(s)
        servidor.run(sockets=soquetes)
    else:
        servidor.run()
    print(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} fim")


if __name__ == "__main__":
    main()
