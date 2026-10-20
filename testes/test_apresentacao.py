"""Aplicativo de apresentação: ponto mais quente dentro do para-raio, a peça onde ele cai e as rotas."""

from __future__ import annotations

import io
import re
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
    galeria = [e["nome"] for e in c.get("/api/exemplos").json()]
    assert len(galeria) == 27 and len(set(galeria)) == 27
    assert galeria[:5] == ["FLIR2620.jpg", "FLIR2618.jpg", "FLIR2614.jpg", "FLIR2812.jpg", "FLIR2612.jpg"]
    assert c.post("/api/exemplos/nao_existe.jpg/analisar").status_code == 404
    assert c.post("/api/analisar", files={"arquivo": ("vazio.jpg", b"", "image/jpeg")}).status_code == 422
    pagina = c.get("/").text
    assert "Pyron" in pagina
    # os arquivos da tela vão com a versão no endereço: mudou o arquivo, muda o endereço (a janela não usa o antigo)
    assert re.search(r'src="/e/app\.js\?v=\d+"', pagina) and re.search(r'href="/e/estilo\.css\?v=\d+"', pagina)
    for arquivo in ("app.js", "estilo.css", "tokens.css", "rotulos.js"):  # a página não funciona sem eles
        r = c.get(f"/e/{arquivo}")
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"  # a janela confere a versão depois de atualizar


def test_nome_exibido_das_saias(tmp_path) -> None:
    import json

    from apresentacao.detector import Detector

    (tmp_path / "cartao.json").write_text(json.dumps({
        "id": "x", "nome": "X", "classes": ["para_raio", "aletas_isoladoras"], "entrada": {"largura": 640, "altura": 640},
        "nomes": {"para_raio": "Para-raio", "aletas_isoladoras": "Aletas Isoladoras"}}), encoding="utf-8")
    det = Detector(tmp_path)
    assert det.nomes["aletas_isoladoras"] == "Saias" and det.nomes["para_raio"] == "Para-raio"
    assert det.classes == ["para_raio", "aletas_isoladoras"]  # a classe do modelo não muda


def test_sem_a_pasta_do_modelo_o_aplicativo_abre_e_avisa(tmp_path) -> None:
    from apresentacao.detector import Detector

    det = Detector(tmp_path / "nao_existe")
    assert det.classes == [] and not det.pronto
    with pytest.raises(FileNotFoundError, match="Modelo não encontrado"):
        det.carregar()


def test_camera_do_celular_identifica_e_estima_a_temperatura(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from apresentacao import servidor
    from nucleo import barra
    from testes.test_barra import _OCRFalso, _caixa
    from testes.test_celular import _termograma_na_sala

    class _Detector(_DetectorFalso):
        classes = ["para_raio", "aletas_isoladoras"]
        cartao = {"id": "teste", "nome": "Modelo de teste"}

    monkeypatch.setattr(servidor, "detector", _Detector([
        {"classe": "aletas_isoladoras", "nome": "Saias", "confianca": 0.9, "caixa": [0.4, 0.4, 0.6, 0.6]}]))
    monkeypatch.setattr(servidor, "iniciar_carga", lambda: None)
    ocr = _OCRFalso([(_caixa(0, 0, 30, 15), "50.0", 0.9)], [(_caixa(0, 0, 30, 15), "10.0", 0.9)])
    monkeypatch.setattr(servidor, "leitor_escala", barra.LeitorAoVivo(lambda: ocr))
    from app import celular

    quadro = celular.ler_imagem(_termograma_na_sala())
    servidor._celular_detectar(quadro)  # a primeira leitura dos números ainda não vale
    pecas, info = servidor._celular_detectar(quadro)
    assert info["escala"]["estado"] == "lida" and (info["escala"]["min"], info["escala"]["max"]) == (10.0, 50.0)
    assert pecas[0]["nome"] == "Saias" and 10.0 <= pecas[0]["tmax"] <= 50.0
    assert pecas[0]["caixa"][1] > 400  # em pixels do quadro, não do recorte do termograma (que começa em y = 400)

    c = TestClient(servidor.app)
    estado = c.get("/api/celular").json()
    assert estado["ligado"] is False and estado["modelo"]["captura"] is False
    assert c.get("/api/celular/qr.png").status_code == 404  # desligado: sem link


def test_servidor_so_desliga_quando_a_janela_fecha() -> None:
    from apresentacao.iniciar import deve_desligar

    class _Edge:
        def __init__(self, vivo):
            self.vivo = vivo

        def poll(self):
            return None if self.vivo else 0

    # janela escondida (PowerPoint na frente): o sinal atrasa 10 min, mas o Edge está vivo → fica
    assert not deve_desligar(1000.0 + 600, 1000.0, 1000.0, {"proc": _Edge(True), "aberta_em": 1000.0})
    # o Edge da janela rodou e terminou → a janela fechou
    assert deve_desligar(1100.0, 1000.0, 1090.0, {"proc": _Edge(False), "aberta_em": 1000.0})
    # o Edge terminou logo depois de abrir: entregou a janela a outro Edge; vale o sinal (5 min)
    entregou = {"proc": _Edge(False), "aberta_em": 1000.0, "terminou_em": 1002.0}
    assert not deve_desligar(1200.0, 1000.0, 1150.0, entregou)
    assert deve_desligar(1500.0, 1000.0, 1150.0, entregou)
