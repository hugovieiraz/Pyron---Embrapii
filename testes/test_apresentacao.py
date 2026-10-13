"""Aplicativo de apresentação: ponto mais quente dentro do para-raio, a peça onde ele cai e as rotas."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from apresentacao import analise

ACERVO = Path(__file__).resolve().parents[1] / "dados" / "sciencedb_10185" / "Infrared Power Equipment Dataset" / "Surge Arresters"


class _DetectorFalso:
    """Um para-raio no meio da foto, com o terminal superior em cima e as aletas embaixo."""

    motor = "teste"
    pronto = True

    def __init__(self, pecas=None):
        self.pecas = pecas or [
            {"classe": "para_raio", "nome": "Para-raio", "confianca": 0.95, "caixa": [0.40, 0.10, 0.60, 0.90]},
            {"classe": "terminal_superior", "nome": "Terminal Superior", "confianca": 0.8, "caixa": [0.42, 0.10, 0.58, 0.30]},
            {"classe": "aletas_isoladoras", "nome": "Aletas Isoladoras", "confianca": 0.9, "caixa": [0.41, 0.28, 0.59, 0.88]},
        ]

    def detectar(self, _rgb):
        return [dict(p) for p in self.pecas]


def test_ponto_mais_quente_dentro_da_caixa() -> None:
    temp = np.full((120, 160), 20.0, np.float32)
    temp[30, 80] = 35.0  # dentro da caixa
    temp[5, 5] = 90.0  # fora da caixa: não conta
    tmax, ponto = analise.ponto_mais_quente(temp, [0.4, 0.1, 0.6, 0.9])
    assert tmax == 35.0
    assert ponto == [round(80.5 / 160, 4), round(30.5 / 120, 4)]


def test_foto_sem_dados_radiometricos_so_identifica() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (20, 30, 120)).save(buf, format="JPEG")
    r = analise.analisar(buf.getvalue(), "print.jpg", _DetectorFalso())
    assert r["radiometrica"] is False and "matriz" not in r
    assert [p["numero"] for p in r["para_raios"]] == [1] and "tmax" not in r["para_raios"][0]
    with pytest.raises(ValueError):
        analise.analisar(b"isto nao e imagem", "x.jpg", _DetectorFalso())


@pytest.mark.skipif(not (ACERVO / "FLIR2618.jpg").exists(), reason="acervo do ScienceDB não está neste computador")
def test_foto_da_flir_da_o_ponto_mais_quente_e_a_peca_onde_ele_cai(monkeypatch) -> None:
    dados = (ACERVO / "FLIR2618.jpg").read_bytes()
    _, temp, info = analise.abrir(dados)
    assert temp is not None and info["camera"] == "FLIR C5"
    # coloca o ponto mais quente no terminal superior e confere que a análise diz isso
    temp[int(0.15 * temp.shape[0]), int(0.5 * temp.shape[1])] = 99.0
    monkeypatch.setattr(analise, "abrir", lambda _dados: (np.zeros((640, 480, 3), np.uint8), temp, info))
    r = analise.analisar(dados, "FLIR2618.jpg", _DetectorFalso())
    pr = r["para_raios"][0]
    assert pr["tmax"] == 99.0 and pr["onde"] == "Terminal Superior"
    assert {p["nome"] for p in pr["partes"]} == {"Terminal Superior", "Aletas Isoladoras"}
    m = r["matriz"]
    assert len(m["valores"]) == m["largura"] * m["altura"] and m["max"] == 99.0


def test_rotas_da_avaliacao_e_das_figuras(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from apresentacao import servidor

    monkeypatch.setattr(servidor, "detector", _DetectorFalso())
    monkeypatch.setattr(servidor, "iniciar_carga", lambda: None)
    c = TestClient(servidor.app)
    av = c.get("/api/avaliacao").json()
    assert [m["nome"] for m in av["comparacao"]["modelos"]] == ["Faster R-CNN", "YOLO26S", "RF-DETR Medium"]
    assert av["treino_local"]["teste"]["acertos"] == 159 and av["figuras"]["comparacao"]
    assert c.get(f"/api/figuras/comparacao/{av['figuras']['comparacao'][0]}").status_code == 200
    assert c.get("/api/figuras/comparacao/..%2F..%2Favaliacao.json").status_code == 404
    assert c.get("/api/figuras/outro/metricas.png").status_code == 404
    assert len(c.get("/api/exemplos").json()) == 27
    assert c.post("/api/exemplos/nao_existe.jpg/analisar").status_code == 404
    assert c.post("/api/analisar", files={"arquivo": ("vazio.jpg", b"", "image/jpeg")}).status_code == 422
    assert "Pyron" in c.get("/").text
