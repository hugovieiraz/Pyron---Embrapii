"""Câmera do celular: o celular aponta para uma imagem térmica e o Pyron identifica os componentes ao vivo.

O celular abre uma página do Pyron no navegador, no mesmo Wi-Fi, transmite a câmera e recebe as caixas
de volta. Uma foto tirada pelo celular não traz os números do sensor; a temperatura só sai quando a
barra de cores aparece no quadro (estimada pelas cores dela).

Transmissão: um WebSocket por celular. O celular manda quadros JPEG sem parar (uns 12 por segundo,
sem acumular fila); o servidor guarda sempre o mais novo e analisa um por vez, descartando os que
chegaram enquanto o detector trabalhava. É o arranjo usual para visão em rede local: sem o custo de
um pedido HTTP por quadro e sem o atraso de uma fila crescendo. O computador recebe os quadros por
outro WebSocket e mostra o vídeo ao vivo.

Cada quadro leva na frente o número dele e a posição da câmera que o celular estimou (quanto a cena
andou no quadro desde o início, comparando miniaturas). A resposta da análise volta com o número do
quadro analisado: com as duas posições, o celular e o computador levam as caixas junto com a câmera
enquanto a próxima análise não chega.

Três cuidados:

- **Servidor à parte.** O Pyron normal só atende o próprio computador (127.0.0.1). O modo celular sobe
  um segundo servidor, ouvindo a rede local, com SÓ as rotas do celular: ninguém na rede alcança as
  inspeções, os backups ou as configurações.
- **Código no link.** Cada vez que o modo liga, sai um código novo; sem ele, nada responde.
- **HTTPS.** O navegador do celular só libera a câmera em conexão segura. O certificado é gerado aqui
  (OpenSSL); por não ser de uma autoridade, o celular avisa uma vez e a pessoa confirma.
"""

from __future__ import annotations

import asyncio
import io
import json
import math
import os
import secrets
import shutil
import socket
import struct
import subprocess
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

LIMITE_FOTO_MEDICAO = 40 * 1024 * 1024  # foto original do celular (12 a 50 MP)
LIMITE_VIDEO_MEDICAO = 100 * 1024 * 1024  # vídeo curto para medir (alguns segundos)
FOTOS_MEDICAO = 20  # fotos de medição que o celular pode citar (as mais novas)
ESTATICO = Path(__file__).resolve().parent / "estatico"
PORTA_INICIAL = 8791
LIMITE_QUADRO = 4 * 1024 * 1024  # bytes de um quadro ou captura (o celular manda ~60 KB)
LADO_MAXIMO = 1280  # o quadro é reduzido a isso antes do detector
CONECTADO_S = 4.0  # sem quadro há mais que isso: o celular saiu da página ou perdeu a rede
IOU_MESMA_PECA = 0.3  # caixas de quadros seguidos com essa sobreposição são a mesma peça
QUADROS_TEMPERATURA = 5  # a máxima mostrada de cada peça é a mediana dela nos últimos quadros
DIAS_CERTIFICADO = 825
# Antes do JPEG de cada quadro transmitido: número do quadro, trecho do rastro e posição da câmera em x
# e y (fração da largura e da altura do quadro), little-endian. O trecho muda quando o celular perde o
# rastro da câmera (sacudiu, trocou o zoom): posições de trechos diferentes não se comparam.
CABECALHO = struct.Struct("<IIff")


def cabecalho(quadro: int, posicao: dict | None) -> bytes:
    if not posicao:
        return CABECALHO.pack(quadro & 0xFFFFFFFF, 0, math.nan, math.nan)
    return CABECALHO.pack(quadro & 0xFFFFFFFF, posicao["trecho"] & 0xFFFFFFFF, posicao["x"], posicao["y"])


def ler_cabecalho(dados: bytes) -> tuple[int, dict | None]:
    quadro, trecho, x, y = CABECALHO.unpack_from(dados)
    if not (math.isfinite(x) and math.isfinite(y)):
        return quadro, None
    return quadro, {"x": round(x, 5), "y": round(y, 5), "trecho": trecho}


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
    if not openssl and cert.exists() and chave.exists():
        # sem OpenSSL (outro computador, com o pacote portátil): o certificado que veio junto serve. Ele não é do
        # endereço desta rede, mas o celular já avisa de qualquer jeito (certificado próprio) e segue igual.
        return cert, chave
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


def iou(a: list[float], b: list[float]) -> float:
    """Sobreposição de duas caixas (x0, y0, x1, y1): interseção sobre união."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    uniao = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / uniao if uniao > 0 else 0.0


# ---------------------------------------------------------------- estado do modo celular


@dataclass
class Ultimo:
    """A última análise de um quadro do celular."""

    deteccoes: list = field(default_factory=list)
    largura: int = 0
    altura: int = 0
    quando: float = 0.0
    ms: int = 0
    seq: int = 0  # número da análise: o espelho no computador só redesenha as caixas quando ele muda
    area: list | None = None  # onde está o termograma no quadro (0 a 1), ou None se não há
    escala: dict | None = None  # barra de cores achada e lida no quadro (temperatura estimada)
    quadro: int = 0  # número do quadro analisado, como o celular mandou
    posicao: dict | None = None  # posição da câmera nesse quadro, como o celular estimou


@dataclass
class Vivo:
    """O quadro mais novo que chegou do celular (para o vídeo ao vivo no computador)."""

    jpeg: bytes = b""
    seq: int = 0
    quando: float = 0.0
    quadro: int = 0
    posicao: dict | None = None


class ModoCelular:
    """Liga e desliga o servidor do celular e guarda o último quadro para o espelho no computador.

    ``detectar(rgb)`` devolve ``(deteccoes, info_modelo)``; ``capturar(jpeg, nome)`` salva uma inspeção.
    Os dois vêm do servidor principal, que sabe qual modelo usar e onde guardar.
    """

    def __init__(self, pasta: Path, detectar: Callable, capturar: Callable, modelo: Callable,
                 guardar_foto: Callable | None = None, previa: Callable | None = None, guardar_video: Callable | None = None):
        self.pasta = pasta
        self._detectar, self._capturar, self._modelo = detectar, capturar, modelo
        # fotos para medir no computador (nucleo/medicao): o celular só tira e envia. guardar_foto(bytes) -> código;
        # previa(código) -> JPEG para mostrar a foto que o navegador do celular não abre (HEIC)
        self._guardar_foto, self._previa = guardar_foto, previa
        self._guardar_video = guardar_video  # guardar_video(bytes, extensão) -> código; o computador mede o vídeo
        self.videos_medicao: OrderedDict[str, float] = OrderedDict()
        self.fotos_medicao: OrderedDict[str, float] = OrderedDict()  # código -> quando chegou (as últimas)
        self.versao_medicao = 0
        self.host = "0.0.0.0"  # toda a rede local; os testes usam 127.0.0.1
        self.token: str | None = None
        self.porta: int | None = None
        self.ip: str | None = None
        self.erro: str | None = None
        self.ultimo = Ultimo()
        self.vivo = Vivo()
        self.medidas: dict = {}  # o que o celular conta que está gastando (câmera, envio, rastro, JPEG)
        self.capturas = 0
        self._tempos: deque[float] = deque(maxlen=20)  # instantes dos últimos quadros (análises por segundo)
        self._recebidos: deque[float] = deque(maxlen=40)  # instantes dos quadros que chegaram (transmissão)
        # peças dos quadros anteriores, com a posição da câmera em cada um, para confirmar
        self._anteriores: deque[tuple[list, dict | None]] = deque(maxlen=2)
        # máximas de cada peça nos últimos quadros (com a posição da câmera e a escala), para suavizar
        self._temperaturas: deque[tuple[list, dict | None, tuple | None]] = deque(maxlen=QUADROS_TEMPERATURA - 1)
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

    @property
    def url_medir(self) -> str | None:
        return f"{self.url}/medir" if self.ligado else None

    # ------------------------------------------------------------ medir objetos em foto

    def receber_foto_medicao(self, dados: bytes) -> str:
        """A foto que o celular tirou para medir, guardada como chegou (sem recomprimir: qualidade e metadados)."""
        if self._guardar_foto is None:
            raise RuntimeError("A medição não está disponível neste Pyron.")
        if not dados or len(dados) > LIMITE_FOTO_MEDICAO:
            raise ValueError("Foto vazia ou maior que 40 MB.")
        codigo = self._guardar_foto(dados)
        self.fotos_medicao[codigo] = time.time()
        self.fotos_medicao.move_to_end(codigo)
        while len(self.fotos_medicao) > FOTOS_MEDICAO:
            self.fotos_medicao.popitem(last=False)
        self.versao_medicao += 1
        return codigo

    def receber_video_medicao(self, dados: bytes, extensao: str = ".mp4") -> str:
        """Vídeo curto gravado no celular para medir no computador, guardado como chegou."""
        if self._guardar_video is None:
            raise RuntimeError("A medição em vídeo não está disponível neste Pyron.")
        if not dados or len(dados) > LIMITE_VIDEO_MEDICAO:
            raise ValueError("Vídeo vazio ou maior que 100 MB.")
        codigo = self._guardar_video(dados, extensao)
        self.videos_medicao[codigo] = time.time()
        self.videos_medicao.move_to_end(codigo)
        while len(self.videos_medicao) > FOTOS_MEDICAO:
            self.videos_medicao.popitem(last=False)
        self.versao_medicao += 1
        return codigo

    def estado_medicao(self) -> dict:
        return {"ligado": self.ligado, "url": self.url_medir, "versao": self.versao_medicao,
                "fotos": [{"id": k, "quando": v} for k, v in reversed(self.fotos_medicao.items())],
                "videos": [{"id": k, "quando": v} for k, v in reversed(self.videos_medicao.items())]}

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
            self.vivo = Vivo()
            self.medidas = {}
            self._tempos.clear()
            self._recebidos.clear()
            self._anteriores.clear()
            self._temperaturas.clear()
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

    def registrar_medidas(self, texto: str) -> None:
        """Medidas que o celular manda a cada 2 s (texto JSON); campos conhecidos, só números ou sim/não."""
        try:
            m = json.loads(texto[:2000])
        except ValueError:
            return
        if not isinstance(m, dict) or m.get("tipo") != "medidas":
            return
        campos = ("camera_por_s", "enviados_por_s", "alvo_por_s", "rastro_ms", "rastro_metade", "jpeg_ms", "lado")
        self.medidas = {k: m[k] for k in campos if isinstance(m.get(k), (int, float, bool, list))}
        self.medidas["quando"] = time.time()

    def receber_quadro(self, jpeg: bytes, quadro: int = 0, posicao: dict | None = None) -> None:
        """Quadro que acabou de chegar: vira o quadro ao vivo do computador, analisado ou não."""
        agora = time.time()
        self._recebidos.append(time.perf_counter())
        self.vivo = Vivo(jpeg, self.vivo.seq + 1, agora, quadro, posicao)

    def processar(self, dados: bytes, quadro: int = 0, posicao: dict | None = None) -> dict:
        rgb = ler_imagem(dados)
        h, w = rgb.shape[:2]
        if not self._trava.acquire(timeout=10):
            raise RuntimeError("O detector está ocupado.")
        try:
            t0 = time.perf_counter()
            caixas, info = self._detectar(rgb)
            ms = round((time.perf_counter() - t0) * 1000)
        finally:
            self._trava.release()
        normalizar = lambda c: [round(c[0] / w, 4), round(c[1] / h, 4), round(c[2] / w, 4), round(c[3] / h, 4)]  # noqa: E731
        area = normalizar(info["area"]) if info.get("area") else None
        atuais = [{**d, "caixa": normalizar(d["caixa"])} for d in caixas]
        deteccoes = self._suavizar(self._confirmar(atuais, area is not None, posicao), atuais, posicao, info.get("escala"))
        agora = time.time()
        self._tempos.append(time.perf_counter())
        escala = info.get("escala")
        if escala and escala.get("barra"):
            escala = {**escala, "barra": normalizar(escala["barra"])}
        self.ultimo = Ultimo(deteccoes, w, h, agora, ms, self.ultimo.seq + 1, area, escala, quadro, posicao)
        return {"deteccoes": deteccoes, "area": area, "escala": escala, "ms": ms, "largura": w, "altura": h,
                "quadro": quadro, "posicao": posicao}

    def _confirmar(self, atuais: list[dict], com_termograma: bool, posicao: dict | None = None) -> list[dict]:
        """Só mostra a peça que aparece em dois quadros seguidos: engano costuma surgir num quadro e sumir.

        Com a câmera andando, a mesma peça muda de lugar entre um quadro analisado e o seguinte: a caixa
        antiga é levada pelo tanto que a câmera andou (posição que o celular mandou) antes de comparar.
        """
        if not com_termograma:
            self._anteriores.clear()
            self._temperaturas.clear()
            return []
        confirmadas = [d for d in atuais
                       if any(a["classe"] == d["classe"] and iou(_levar(a["caixa"], antes, posicao), d["caixa"]) >= IOU_MESMA_PECA
                              for quadro, antes in self._anteriores for a in quadro)]
        self._anteriores.append((atuais, posicao))
        return confirmadas

    def _suavizar(self, confirmadas: list[dict], atuais: list[dict], posicao: dict | None, escala: dict | None) -> list[dict]:
        """Máxima de cada peça pela mediana dos últimos quadros em que ela apareceu (com a mesma escala).

        A 10 análises por segundo, a máxima de um quadro para o outro pula: ruído da foto da tela e, às
        vezes, a mira da câmera passando por cima da peça. A mediana segura os picos isolados. A peça é a
        mesma de um quadro para o outro como na confirmação: mesma classe e caixa sobreposta, descontado
        o quanto a câmera andou.
        """
        limites = (escala.get("min"), escala.get("max")) if escala and escala.get("estado") == "lida" else None
        saida = []
        for d in confirmadas:
            if d.get("tmax") is None:
                saida.append(d)
                continue
            valores, acima = [d["tmax"]], [bool(d.get("tmax_acima"))]
            for quadro, antes, lim in self._temperaturas:
                if lim != limites:
                    continue
                pares = [(iou(_levar(a["caixa"], antes, posicao), d["caixa"]), a) for a in quadro
                         if a["classe"] == d["classe"] and a.get("tmax") is not None]
                melhor = max(pares, default=(0.0, None), key=lambda p: p[0])
                if melhor[0] >= IOU_MESMA_PECA:
                    valores.append(melhor[1]["tmax"])
                    acima.append(bool(melhor[1].get("tmax_acima")))
            saida.append({**d, "tmax": round(float(np.median(valores)), 1), "tmax_acima": sum(acima) * 2 > len(acima)})
        self._temperaturas.append((atuais, posicao, limites))
        return saida

    def capturar(self, dados: bytes) -> dict:
        ler_imagem(dados)  # confere antes de gravar
        nome = f"celular_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
        resumo = self._capturar(dados, nome)
        self.capturas += 1
        return resumo

    def analises_por_s(self) -> float | None:
        return _ritmo(self._tempos)

    def quadros_por_s(self) -> float | None:
        return _ritmo(self._recebidos)

    def estado(self) -> dict:
        ligado = self.ligado
        u = self.ultimo
        visto = max(u.quando, self.vivo.quando)
        conectado = ligado and visto > 0 and time.time() - visto < CONECTADO_S
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
            "medidas_celular": self.medidas if self.medidas and time.time() - self.medidas.get("quando", 0) < CONECTADO_S else None,
            "ultimo": None if not u.quando else {
                "deteccoes": u.deteccoes, "area": u.area, "escala": u.escala, "largura": u.largura, "altura": u.altura,
                "ms": u.ms, "seq": u.seq, "ha_s": round(time.time() - u.quando, 1), "analises_por_s": self.analises_por_s(),
                "quadros_por_s": self.quadros_por_s(),
            },
        }


def _levar(caixa: list[float], de: dict | None, para: dict | None) -> list[float]:
    """Caixa (fração do quadro) levada pelo tanto que a cena andou entre duas posições da câmera."""
    if not de or not para or de["trecho"] != para["trecho"]:
        return caixa
    dx, dy = para["x"] - de["x"], para["y"] - de["y"]
    return [caixa[0] + dx, caixa[1] + dy, caixa[2] + dx, caixa[3] + dy]


def _ritmo(instantes: deque) -> float | None:
    """Eventos por segundo nos últimos 10 s (relógio de alta resolução: no Windows, ``time.time`` anda de
    15 em 15 ms e quadros que chegam juntos pareciam simultâneos)."""
    recentes = [t for t in instantes if time.perf_counter() - t < 10]
    if len(recentes) < 2 or recentes[-1] <= recentes[0]:
        return None
    return round((len(recentes) - 1) / (recentes[-1] - recentes[0]), 2)


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

    @app.middleware("http")
    async def _sempre_a_versao_nova(request: Request, seguir):
        """Os scripts da página sempre conferem a versão: o navegador do celular guardava o antigo."""
        resposta = await seguir(request)
        if request.url.path.startswith("/e/"):
            resposta.headers["Cache-Control"] = "no-cache"
        return resposta

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
        modo.receber_quadro(dados)  # sem WebSocket (rede que bloqueia): o computador também vê o quadro
        try:
            return await _em_fio(modo.processar, dados)
        except ValueError as erro:
            raise HTTPException(422, str(erro)) from erro
        except RuntimeError as erro:
            raise HTTPException(503, str(erro)) from erro

    @app.websocket("/c/{token}/ws")
    async def ao_vivo(ws: WebSocket, token: str):
        """Transmissão do celular: quadros chegam sem parar; analisa sempre o mais novo, um por vez.

        Cada mensagem do celular: o cabeçalho (número do quadro e posição da câmera) e o JPEG. A
        resposta vai em JSON com o número do quadro analisado.
        """
        if not modo.token or not secrets.compare_digest(token, modo.token):
            await ws.close(code=4404)
            return
        await ws.accept()
        novo = asyncio.Event()
        pendente: dict = {"jpeg": None, "quadro": 0, "posicao": None, "fim": False}

        async def receber():
            try:
                while True:
                    mensagem = await ws.receive()
                    if mensagem["type"] == "websocket.disconnect":
                        break
                    if mensagem.get("text"):
                        modo.registrar_medidas(mensagem["text"])
                        continue
                    dados = mensagem.get("bytes") or b""
                    if len(dados) <= CABECALHO.size or len(dados) > LIMITE_QUADRO:
                        continue
                    quadro, posicao = ler_cabecalho(dados)
                    jpeg = dados[CABECALHO.size:]
                    modo.receber_quadro(jpeg, quadro, posicao)
                    pendente.update(jpeg=jpeg, quadro=quadro, posicao=posicao)
                    novo.set()
            except (WebSocketDisconnect, RuntimeError):
                pass
            finally:
                pendente["fim"] = True
                novo.set()

        async def analisar():
            while True:
                await novo.wait()
                novo.clear()
                if pendente["fim"]:
                    return
                jpeg, quadro, posicao = pendente["jpeg"], pendente["quadro"], pendente["posicao"]
                try:
                    r = await _em_fio(modo.processar, jpeg, quadro, posicao)
                    resposta = {"tipo": "resultado", **r}
                except (ValueError, RuntimeError) as erro:
                    resposta = {"tipo": "erro", "quadro": quadro, "mensagem": str(erro)}
                try:
                    await ws.send_json(resposta)
                except (WebSocketDisconnect, RuntimeError):
                    return

        await asyncio.gather(receber(), analisar())

    @app.get("/c/{token}/medir")
    def pagina_medir(token: str):
        """Fotos para medir: o celular tira (ou escolhe da galeria) e envia o original; a medida é no computador."""
        if not modo.token or not secrets.compare_digest(token, modo.token):
            return pagina(token)
        return FileResponse(ESTATICO / "medir_celular.html", headers={"Cache-Control": "no-store"})

    @app.post("/c/{token}/medir/foto")
    async def medir_foto(token: str, request: Request) -> dict:
        conferir(token)
        try:
            return {"id": await _em_fio(modo.receber_foto_medicao, await request.body())}
        except ValueError as erro:
            raise HTTPException(422, str(erro)) from erro
        except RuntimeError as erro:
            raise HTTPException(503, str(erro)) from erro

    @app.post("/c/{token}/medir/video")
    async def medir_video(token: str, request: Request) -> dict:
        conferir(token)
        tipo = request.headers.get("content-type", "")
        extensao = {"video/quicktime": ".mov", "video/webm": ".webm", "video/3gpp": ".3gp"}.get(tipo.split(";")[0], ".mp4")
        try:
            return {"id": await _em_fio(modo.receber_video_medicao, await request.body(), extensao)}
        except ValueError as erro:
            raise HTTPException(422, str(erro)) from erro
        except RuntimeError as erro:
            raise HTTPException(503, str(erro)) from erro

    @app.get("/c/{token}/medir/{codigo}/previa")
    async def medir_previa(token: str, codigo: str):
        conferir(token)
        if modo._previa is None or codigo not in modo.fotos_medicao:
            raise HTTPException(404, "Foto não encontrada. Tire de novo.")
        from fastapi.responses import Response

        return Response(await _em_fio(modo._previa, codigo), media_type="image/jpeg")

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
