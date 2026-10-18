"""Servidor do aplicativo de apresentação: só a análise, o modelo e a avaliação.

Roda só neste computador (127.0.0.1). Rotas:

- ``/``: a interface (``estatico/``);
- ``/api/estado``: o modelo, onde ele roda (placa de vídeo ou processador) e se já está pronto;
- ``/api/exemplos``: as 27 fotos de teste (nunca vistas no treino), lidas do acervo deste computador;
- ``/api/exemplos/{nome}/analisar`` e ``/api/analisar``: a análise de uma foto do acervo ou enviada;
- ``/api/avaliacao`` e ``/api/figuras/...``: as métricas e as figuras da avaliação dos modelos;
- ``/api/celular/...``: a câmera do celular (o modo celular do Pyron, ``app/celular.py``: um servidor
  HTTPS à parte na rede local, com código no link, só enquanto ligado) e ``/api/celular/ws``, o vídeo
  do celular no computador.
"""

from __future__ import annotations

import io
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

from apresentacao import analise
from apresentacao.detector import Detector

# O modo celular é o mesmo do Pyron completo: a página do celular, a transmissão por WebSocket, o rastro
# da câmera e a leitura da barra de cores (app/celular.py, nucleo/enquadrar.py, nucleo/barra.py).
from app import celular  # noqa: E402
from nucleo import barra, enquadrar  # noqa: E402

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
ESTATICO = AQUI / "estatico"
AVALIACAO = AQUI / "dados" / "avaliacao"
MODELO = Path(os.environ.get("PYRON_APRESENTACAO_MODELO", RAIZ / "modelos" / "para-raios-rfdetr-local-20260930-1627"))
ACERVO = Path(os.environ.get("PYRON_ACERVO", RAIZ / "dados" / "sciencedb_10185" / "Infrared Power Equipment Dataset" / "Surge Arresters"))
LIMITE_ARQUIVO = 20 * 1024 * 1024
NOME_FOTO = re.compile(r"^[A-Za-z0-9_.-]{1,80}\.jpe?g$", re.IGNORECASE)

app = FastAPI(title="Pyron · Apresentação", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/e", StaticFiles(directory=ESTATICO), name="estatico")

detector = Detector(MODELO)  # sem a pasta do modelo, abre do mesmo jeito e a tela mostra o que falta
_carga = {"erro": None, "iniciada": False}
_trava_carga = threading.Lock()
sinais = {"ultimo": 0.0}  # último sinal da janela (o lançador desliga o servidor quando ela fecha)
_miniaturas: dict[str, bytes] = {}


def iniciar_carga() -> None:
    """Abre o modelo num fio à parte (uma vez só): a janela aparece enquanto ele carrega (~2 s)."""
    with _trava_carga:
        if _carga["iniciada"]:
            return
        _carga["iniciada"] = True

    def carregar() -> None:
        try:
            detector.carregar()
        except Exception as erro:  # noqa: BLE001 — mostrado na tela
            _carga["erro"] = f"{type(erro).__name__}: {erro}"

    threading.Thread(target=carregar, name="modelo", daemon=True).start()


def _avaliacao() -> dict:
    return json.loads((AVALIACAO / "avaliacao.json").read_text(encoding="utf-8"))


def _esperar_modelo() -> None:
    iniciar_carga()
    for _ in range(300):
        if detector.pronto or _carga["erro"]:
            break
        time.sleep(0.1)
    if not detector.pronto:
        raise HTTPException(503, _carga["erro"] or "O modelo ainda está carregando.")


@app.get("/")
def pagina() -> FileResponse:
    return FileResponse(ESTATICO / "index.html", headers={"Cache-Control": "no-store"})


@app.post("/api/sinal")
def sinal() -> dict:
    sinais["ultimo"] = time.time()
    return {"ok": True}


@app.get("/api/estado")
def estado() -> dict:
    iniciar_carga()
    c, r = detector.cartao, detector.relatorio
    return {
        "pronto": detector.pronto,
        "erro": _carga["erro"],
        "motor": detector.motor,
        "modelo": {
            "nome": c.get("nome"), "arquitetura": c.get("arquitetura"), "classes": [detector.nomes.get(k, k) for k in detector.classes],
            "entrada": [c["entrada"]["largura"], c["entrada"]["altura"]], "limiar": detector.limiar,
            "treino": c.get("treino", {}), "limitacoes": c.get("limitacoes", []), "ms_por_foto_cpu": r.get("ms_por_foto_cpu"),
        },
    }


@app.get("/api/exemplos")
def exemplos() -> list[dict]:
    return [{"nome": n, "disponivel": (ACERVO / n).exists()} for n in _avaliacao()["fotos_teste"]]


def _foto_do_acervo(nome: str) -> Path:
    if not NOME_FOTO.match(nome) or nome not in _avaliacao()["fotos_teste"]:
        raise HTTPException(404, "Foto de teste desconhecida.")
    caminho = ACERVO / nome
    if not caminho.exists():
        raise HTTPException(404, f"A foto {nome} não está no acervo deste computador.")
    return caminho


@app.get("/api/exemplos/{nome}/miniatura.jpg")
def miniatura(nome: str) -> Response:
    if nome not in _miniaturas:
        img = ImageOps.exif_transpose(Image.open(_foto_do_acervo(nome))).convert("RGB")
        img.thumbnail((240, 240))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        _miniaturas[nome] = buf.getvalue()
    return Response(_miniaturas[nome], media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@app.post("/api/exemplos/{nome}/analisar")
def analisar_exemplo(nome: str) -> dict:
    caminho = _foto_do_acervo(nome)
    _esperar_modelo()
    return {**analise.analisar(caminho.read_bytes(), nome, detector), "exemplo": True}


@app.post("/api/analisar")
async def analisar_enviada(arquivo: UploadFile = File(...)) -> dict:
    dados = await arquivo.read()
    if not dados:
        raise HTTPException(422, "O arquivo está vazio.")
    if len(dados) > LIMITE_ARQUIVO:
        raise HTTPException(413, "Arquivo grande demais (até 20 MB).")
    _esperar_modelo()
    try:
        return {**analise.analisar(dados, arquivo.filename or "foto.jpg", detector), "exemplo": False}
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro


@app.get("/api/avaliacao")
def avaliacao() -> dict:
    a = _avaliacao()
    a["figuras"] = {g: sorted(p.name for p in (AVALIACAO / g).glob("*.png")) for g in ("comparacao", "treino_local")}
    return a


@app.get("/api/figuras/{grupo}/{arquivo}")
def figura(grupo: str, arquivo: str) -> FileResponse:
    if grupo not in ("comparacao", "treino_local") or not re.match(r"^[a-z0-9_]+\.png$", arquivo):
        raise HTTPException(404, "Figura desconhecida.")
    caminho = AVALIACAO / grupo / arquivo
    if not caminho.exists():
        raise HTTPException(404, "Figura não encontrada.")
    return FileResponse(caminho, headers={"Cache-Control": "max-age=3600"})


# ---------------------------------------------------------------- câmera do celular

leitor_escala = barra.LeitorAoVivo()
_fio_escala = ThreadPoolExecutor(max_workers=1, thread_name_prefix="escala")


def _celular_detectar(rgb: np.ndarray) -> tuple[list[dict], dict]:
    """Peças no quadro do celular: só dentro da área do termograma, com a máxima pela barra de cores.

    O modelo foi treinado só com termogramas: no quadro inteiro (a sala, a mesa) ele vê para-raios em
    qualquer coisa. A barra é lida em paralelo com o detector, noutro fio.
    """
    area = enquadrar.achar_termograma(rgb)
    if area is None:
        return [], {"area": None}
    recorte = np.ascontiguousarray(rgb[area.y0:area.y1, area.x0:area.x1])
    h, w = recorte.shape[:2]
    img_lab = barra.lab(recorte)
    leitura = _fio_escala.submit(leitor_escala.ler, recorte, img_lab)
    pecas = []
    for d in detector.detectar(recorte):
        x0, y0, x1, y1 = d["caixa"]
        pecas.append({**d, "caixa": [x0 * w, y0 * h, x1 * w, y1 * h]})
    escala, achada, estado_escala = leitura.result()
    for p in pecas:
        if escala is not None:
            t, acima = barra.maxima(img_lab, escala, p["caixa"])
            if t is not None:
                p["tmax"], p["tmax_acima"] = round(t, 1), acima
        x0, y0, x1, y1 = p["caixa"]
        p["caixa"] = [x0 + area.x0, y0 + area.y0, x1 + area.x0, y1 + area.y0]
    info_escala = None
    if achada is not None:
        bx0, by0, bx1, by1 = achada.caixa()
        info_escala = {"estado": estado_escala, "barra": [bx0 + area.x0, by0 + area.y0, bx1 + area.x0, by1 + area.y0]}
        if escala is not None:
            info_escala.update(min=round(escala.t_min, 1), max=round(escala.t_max, 1))
    return pecas, {"area": area.caixa(), "escala": info_escala}


def _celular_capturar(_dados: bytes, _nome: str) -> dict:
    raise ValueError("A versão de apresentação não salva capturas.")


def _celular_modelo() -> dict:
    iniciar_carga()
    if _carga["erro"]:
        raise ValueError(_carga["erro"])
    return {"id": detector.cartao.get("id"), "nome": detector.cartao.get("nome"), "classes": detector.classes,
            "captura": False, "motor": detector.motor}


celular_modo = celular.ModoCelular(AQUI / ".celular", _celular_detectar, _celular_capturar, _celular_modelo)
INTERVALO_ESPELHO_S = 1 / 30


@app.get("/api/celular")
def celular_estado() -> dict:
    return celular_modo.estado()


@app.post("/api/celular/ligar")
def celular_ligar() -> dict:
    """Abre o servidor do celular na rede local (HTTPS, só as rotas do celular, com código no link)."""
    try:
        _celular_modelo()
        leitor_escala.reiniciar()
        celular_modo.ligar()
    except ValueError as erro:
        raise HTTPException(409, str(erro)) from erro
    except (RuntimeError, OSError) as erro:
        raise HTTPException(503, str(erro)) from erro
    return celular_modo.estado()


@app.post("/api/celular/desligar")
def celular_desligar() -> dict:
    celular_modo.desligar()
    return celular_modo.estado()


@app.get("/api/celular/qr.png")
def celular_qr() -> Response:
    if not celular_modo.url:
        raise HTTPException(404, "A câmera do celular está desligada.")
    return Response(celular.qr_png(celular_modo.url), media_type="image/png", headers={"Cache-Control": "no-store"})


@app.websocket("/api/celular/ws")
async def celular_ao_vivo(ws: WebSocket) -> None:
    """Vídeo do celular no computador: cada quadro novo (cabeçalho + JPEG) e cada resultado novo (JSON)."""
    import anyio

    await ws.accept()
    async with anyio.create_task_group() as grupo:

        async def mandar() -> None:
            visto_quadro = visto_resultado = -1
            try:
                while True:
                    vivo, ultimo = celular_modo.vivo, celular_modo.ultimo
                    if vivo.seq != visto_quadro and vivo.jpeg:
                        visto_quadro = vivo.seq
                        await ws.send_bytes(celular.cabecalho(vivo.quadro, vivo.posicao) + vivo.jpeg)
                    if ultimo.seq != visto_resultado and ultimo.quando:
                        visto_resultado = ultimo.seq
                        await ws.send_json({"deteccoes": ultimo.deteccoes, "area": ultimo.area, "escala": ultimo.escala,
                                            "seq": ultimo.seq, "ms": ultimo.ms, "quadro": ultimo.quadro, "posicao": ultimo.posicao})
                    await anyio.sleep(INTERVALO_ESPELHO_S)
            except (WebSocketDisconnect, RuntimeError):
                pass
            finally:
                grupo.cancel_scope.cancel()

        async def ouvir() -> None:  # só para saber quando a tela fecha
            try:
                while (await ws.receive())["type"] != "websocket.disconnect":
                    pass
            finally:
                grupo.cancel_scope.cancel()

        grupo.start_soon(mandar)
        grupo.start_soon(ouvir)
