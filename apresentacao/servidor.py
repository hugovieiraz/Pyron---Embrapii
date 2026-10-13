"""Servidor do aplicativo de apresentação: só a análise, o modelo e a avaliação.

Roda só neste computador (127.0.0.1). Rotas:

- ``/``: a interface (``estatico/``);
- ``/api/estado``: o modelo, onde ele roda (placa de vídeo ou processador) e se já está pronto;
- ``/api/exemplos``: as 27 fotos de teste (nunca vistas no treino), lidas do acervo deste computador;
- ``/api/exemplos/{nome}/analisar`` e ``/api/analisar``: a análise de uma foto do acervo ou enviada;
- ``/api/avaliacao`` e ``/api/figuras/...``: as métricas e as figuras da avaliação dos modelos.
"""

from __future__ import annotations

import io
import json
import os
import re
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

from apresentacao import analise
from apresentacao.detector import Detector

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

detector = Detector(MODELO)
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
