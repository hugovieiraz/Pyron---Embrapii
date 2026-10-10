"""Câmera do celular: o celular aponta para uma imagem térmica e o Pyron identifica os componentes ao vivo.

O celular abre uma página do Pyron no navegador, no mesmo Wi-Fi, manda os quadros da câmera e recebe
as caixas de volta. Só identificação: uma foto tirada pelo celular (da tela do computador, por exemplo)
não traz os números do sensor nem a escala, então não há temperatura.

Três cuidados:

- **Servidor à parte.** O Pyron normal só atende o próprio computador (127.0.0.1). O modo celular sobe
  um segundo servidor, ouvindo a rede local, com SÓ as rotas do celular: ninguém na rede alcança as
  inspeções, os backups ou as configurações.
- **Código no link.** Cada vez que o modo liga, sai um código novo; sem ele, nada responde.
- **HTTPS.** O navegador do celular só libera a câmera em conexão segura. O certificado é gerado aqui
  (OpenSSL); por não ser de uma autoridade, o celular avisa uma vez e a pessoa confirma.
"""

from __future__ import annotations

import io
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

ESTATICO = Path(__file__).resolve().parent / "estatico"
PORTA_INICIAL = 8791
LIMITE_QUADRO = 4 * 1024 * 1024  # bytes de um quadro ou captura (o celular manda ~60 KB)
LADO_MAXIMO = 1280  # o quadro é reduzido a isso antes do detector
CONECTADO_S = 4.0  # sem quadro há mais que isso: o celular saiu da página ou perdeu a rede
DIAS_CERTIFICADO = 825


# ---------------------------------------------------------------- rede e certificado


def ip_local() -> str:
    """Endereço do computador na rede local (o do adaptador que sai para a rede; nada é enviado)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def porta_livre(inicio: int = PORTA_INICIAL, host: str = "0.0.0.0") -> int:
    for porta in range(inicio, inicio + 20):
        with socket.socket() as s:
            try:
                s.bind((host, porta))
                return porta
            except OSError:
                continue
    raise RuntimeError(f"Nenhuma porta livre entre {inicio} e {inicio + 19} para o celular.")


def _openssl() -> str | None:
    """O OpenSSL do sistema ou o que vem com o Git para Windows."""
    achado = shutil.which("openssl")
    if achado:
        return achado
    bases = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", r"C:\Program Files"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")]
    for base in bases:
        for sub in (r"Git\mingw64\bin\openssl.exe", r"Git\usr\bin\openssl.exe"):
            caminho = Path(base) / sub
            if caminho.exists():
                return str(caminho)
    return None


def certificado(pasta: Path, ip: str) -> tuple[Path, Path]:
    """Certificado próprio para o endereço da rede; refeito quando o endereço muda."""
    pasta.mkdir(parents=True, exist_ok=True)
    cert, chave, marca = pasta / "certificado.pem", pasta / "chave.pem", pasta / "endereco.txt"
    if cert.exists() and chave.exists() and marca.exists() and marca.read_text(encoding="utf-8").strip() == ip:
        return cert, chave
    openssl = _openssl()
    if not openssl:
        raise RuntimeError("Para ligar o celular falta o OpenSSL, que gera o certificado da conexão segura. "
                           "Instale o Git para Windows (ele traz o OpenSSL) e tente de novo.")
    # MSYS2_ARG_CONV_EXCL: o OpenSSL do Git (MSYS) não troca "/CN=..." por um caminho do Windows.
    ambiente = {**os.environ, "MSYS2_ARG_CONV_EXCL": "*"}
    r = subprocess.run(
        [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(chave), "-out", str(cert),
         "-days", str(DIAS_CERTIFICADO), "-subj", "/CN=Pyron (rede local)",
         "-addext", f"subjectAltName=IP:{ip},DNS:localhost"],
        capture_output=True, text=True, timeout=60, env=ambiente,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if r.returncode != 0 or not cert.exists():
        raise RuntimeError(f"O OpenSSL não conseguiu gerar o certificado: {(r.stderr or '').strip()[-200:]}")
    marca.write_text(ip, encoding="utf-8")
    return cert, chave


def qr_png(texto: str, escala: int = 8) -> bytes:
    """QR code do link, em PNG (OpenCV, que o Pyron já usa no vídeo)."""
    import cv2

    qr = cv2.QRCodeEncoder.create().encode(texto)
    grande = cv2.resize(qr, (qr.shape[1] * escala, qr.shape[0] * escala), interpolation=cv2.INTER_NEAREST)
    grande = cv2.copyMakeBorder(grande, 4 * escala, 4 * escala, 4 * escala, 4 * escala, cv2.BORDER_CONSTANT, value=255)
    ok, png = cv2.imencode(".png", grande)
    if not ok:
        raise RuntimeError("não consegui gerar o QR code")
    return png.tobytes()


def ler_imagem(dados: bytes) -> np.ndarray:
    """JPEG do celular → RGB, reduzido a LADO_MAXIMO no lado maior."""
    if not dados:
        raise ValueError("Quadro vazio.")
    if len(dados) > LIMITE_QUADRO:
        raise ValueError("Quadro grande demais.")
    try:
        img = Image.open(io.BytesIO(dados))
        img.load()
    except OSError as erro:
        raise ValueError("O quadro não é uma imagem.") from erro
    img = img.convert("RGB")
    if max(img.size) > LADO_MAXIMO:
        img.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    return np.asarray(img)


# ---------------------------------------------------------------- estado do modo celular


@dataclass
class Ultimo:
    jpeg: bytes = b""
    deteccoes: list = field(default_factory=list)
    largura: int = 0
    altura: int = 0
    quando: float = 0.0
    ms: int = 0
    seq: int = 0  # número do quadro: o espelho no computador só baixa a imagem quando ele muda


class ModoCelular:
    """Liga e desliga o servidor do celular e guarda o último quadro para o espelho no computador.

    ``detectar(rgb)`` devolve ``(deteccoes, info_modelo)``; ``capturar(jpeg, nome)`` salva uma inspeção.
    Os dois vêm do servidor principal, que sabe qual modelo usar e onde guardar.
    """

    def __init__(self, pasta: Path, detectar: Callable, capturar: Callable, modelo: Callable):
        self.pasta = pasta
        self._detectar, self._capturar, self._modelo = detectar, capturar, modelo
        self.host = "0.0.0.0"  # toda a rede local; os testes usam 127.0.0.1
        self.token: str | None = None
        self.porta: int | None = None
        self.ip: str | None = None
        self.erro: str | None = None
        self.ultimo = Ultimo()
        self.capturas = 0
        self._tempos: deque[float] = deque(maxlen=20)  # instantes dos últimos quadros (análises por segundo)
        self._servidor = None
        self._fio: threading.Thread | None = None
        self._trava = threading.Lock()  # um quadro por vez no detector
        self._liga = threading.Lock()

    # ------------------------------------------------------------ ligar e desligar

    @property
    def ligado(self) -> bool:
        return bool(self._servidor and self._fio and self._fio.is_alive() and not self._servidor.should_exit)

    @property
    def url(self) -> str | None:
        return f"https://{self.ip}:{self.porta}/c/{self.token}" if self.ligado else None

    def ligar(self) -> None:
        import uvicorn

        with self._liga:
            if self.ligado:
                return
            self.erro = None
            self.ip = ip_local()
            cert, chave = certificado(self.pasta, self.ip)
            self.porta = porta_livre(host=self.host)
            self.token = secrets.token_urlsafe(6)
            self.ultimo = Ultimo()
            self._tempos.clear()
            config = uvicorn.Config(criar_app(self), host=self.host, port=self.porta, ssl_certfile=str(cert),
                                    ssl_keyfile=str(chave), log_level="warning", log_config=None)
            self._servidor = uvicorn.Server(config)
            self._fio = threading.Thread(target=self._servidor.run, name="pyron-celular", daemon=True)
            self._fio.start()
            for _ in range(100):  # até 10 s para subir
                if self._servidor.started:
                    return
                if not self._fio.is_alive():
                    break
                time.sleep(0.1)
            self._servidor.should_exit = True
            raise RuntimeError(f"O servidor do celular não subiu na porta {self.porta}.")

    def desligar(self) -> None:
        with self._liga:
            if self._servidor:
                self._servidor.should_exit = True
            if self._fio:
                self._fio.join(timeout=5)
            self._servidor = self._fio = None
            self.token = None

    # ------------------------------------------------------------ quadros

    def processar(self, dados: bytes) -> dict:
        rgb = ler_imagem(dados)
        h, w = rgb.shape[:2]
        if not self._trava.acquire(timeout=10):
            raise RuntimeError("O detector está ocupado.")
        try:
            t0 = time.perf_counter()
            caixas, _ = self._detectar(rgb)
            ms = round((time.perf_counter() - t0) * 1000)
        finally:
            self._trava.release()
        deteccoes = [{**d, "caixa": [round(d["caixa"][0] / w, 4), round(d["caixa"][1] / h, 4),
                                      round(d["caixa"][2] / w, 4), round(d["caixa"][3] / h, 4)]} for d in caixas]
        agora = time.time()
        self._tempos.append(agora)
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format="JPEG", quality=80)
        self.ultimo = Ultimo(buf.getvalue(), deteccoes, w, h, agora, ms, self.ultimo.seq + 1)
        return {"deteccoes": deteccoes, "ms": ms, "largura": w, "altura": h}

    def capturar(self, dados: bytes) -> dict:
        ler_imagem(dados)  # confere antes de gravar
        nome = f"celular_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
        resumo = self._capturar(dados, nome)
        self.capturas += 1
        return resumo

    def analises_por_s(self) -> float | None:
        recentes = [t for t in self._tempos if time.time() - t < 10]
        if len(recentes) < 2:
            return None
        return round((len(recentes) - 1) / (recentes[-1] - recentes[0]), 2) if recentes[-1] > recentes[0] else None

    def estado(self) -> dict:
        ligado = self.ligado
        u = self.ultimo
        conectado = ligado and u.quando > 0 and time.time() - u.quando < CONECTADO_S
        try:
            modelo = self._modelo()
        except ValueError as erro:
            modelo = {"erro": str(erro)}
        return {
            "ligado": ligado,
            "url": self.url,
            "ip": self.ip,
            "porta": self.porta if ligado else None,
            "erro": self.erro,
            "modelo": modelo,
            "conectado": conectado,
            "capturas": self.capturas,
            "ultimo": None if not u.quando else {
                "deteccoes": u.deteccoes, "largura": u.largura, "altura": u.altura, "ms": u.ms, "seq": u.seq,
                "ha_s": round(time.time() - u.quando, 1), "analises_por_s": self.analises_por_s(),
            },
        }


# ---------------------------------------------------------------- servidor do celular (só estas rotas)


def criar_app(modo: ModoCelular) -> FastAPI:
    app = FastAPI(title="Pyron · celular", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/e", StaticFiles(directory=ESTATICO), name="estatico")

    def conferir(token: str) -> None:
        if not modo.token or not secrets.compare_digest(token, modo.token):
            raise HTTPException(404, "Link vencido. Gere um novo em Câmera do celular, no Pyron do computador.")

    @app.exception_handler(HTTPException)
    async def _erro(_request: Request, exc: HTTPException):
        return JSONResponse({"erro": exc.detail}, status_code=exc.status_code)

    @app.get("/c/{token}")
    def pagina(token: str):
        if not modo.token or not secrets.compare_digest(token, modo.token):
            return HTMLResponse("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                                "<body style='font-family:sans-serif;padding:24px'><h1>Link vencido</h1>"
                                "<p>Gere um novo em <b>Câmera do celular</b>, no Pyron do computador.</p>", status_code=404)
        return FileResponse(ESTATICO / "celular.html", headers={"Cache-Control": "no-store"})

    @app.get("/c/{token}/modelo")
    def modelo(token: str) -> dict:
        conferir(token)
        try:
            return modo._modelo()
        except ValueError as erro:
            raise HTTPException(409, str(erro)) from erro

    @app.post("/c/{token}/quadro")
    async def quadro(token: str, request: Request) -> dict:
        conferir(token)
        dados = await request.body()
        try:
            return await _em_fio(modo.processar, dados)
        except ValueError as erro:
            raise HTTPException(422, str(erro)) from erro
        except RuntimeError as erro:
            raise HTTPException(503, str(erro)) from erro

    @app.post("/c/{token}/capturar")
    async def capturar(token: str, request: Request) -> dict:
        conferir(token)
        dados = await request.body()
        try:
            return await _em_fio(modo.capturar, dados)
        except ValueError as erro:
            raise HTTPException(422, str(erro)) from erro

    return app


async def _em_fio(funcao, *args):
    """O detector leva centenas de milissegundos: roda fora do laço de eventos."""
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(funcao, *args)
