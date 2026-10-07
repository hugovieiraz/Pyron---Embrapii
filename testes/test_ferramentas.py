"""Ferramentas de análise: ponto, linha (perfil), escala e paleta guardadas, parâmetros de medição
e exportação (PNG, CSV da matriz e planilha das inspeções)."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from nucleo import analise
from testes.test_servidor import _termograma_flir


def test_ponto_e_perfil_na_matriz() -> None:
    t = np.zeros((10, 20), dtype=np.float32)
    t[5, :] = np.arange(20)
    t[5, 7] = np.nan
    assert analise.medir_ponto(t, 12.7, 5.2) == {"t": 12.0, "x": 12, "y": 5}
    assert analise.medir_ponto(t, 7, 5) is None  # sem medida naquele pixel
    p = analise.perfil_linha(t, 0, 5, 19, 5)
    assert len(p["valores"]) == 20 and p["valores"][7] is None
    assert p["t_max"] == 19 and p["x_max"] == 19 and p["t_min"] == 0
    nomes = [m["nome"] for m in analise.medir_medicoes(t, [{"tipo": "ponto", "x": 1, "y": 1}, {"tipo": "linha", "x0": 0, "y0": 0, "x1": 3, "y1": 3},
                                                          {"tipo": "ponto", "x": 2, "y": 2}, {"tipo": "outro"}])]
    assert nomes == ["P1", "L1", "P2"]


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    return TestClient(servidor.app)


def _analisar(cliente) -> dict:
    r = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _termograma_flir(), "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()


def test_pontos_linhas_e_exibicao_ficam_na_inspecao(cliente) -> None:
    a = _analisar(cliente)
    med = [{"tipo": "ponto", "x": 80, "y": 62}, {"tipo": "linha", "x0": 40, "y0": 62, "x1": 120, "y1": 62}]
    b = cliente.put(f"/api/analises/{a['id']}", json={"medicoes": med, "exibicao": {"paleta": "cinza", "faixa": [50, 20]}}).json()
    p1, l1 = b["medicoes"]
    assert p1["nome"] == "P1" and p1["valor"]["t"] == pytest.approx(45.0, abs=0.1)
    assert l1["nome"] == "L1" and l1["valor"]["t_max"] == pytest.approx(45.0, abs=0.1) and l1["valor"]["t_min"] == pytest.approx(30.0, abs=0.1)
    assert b["exibicao"] == {"paleta": "cinza", "faixa": [20.0, 50.0]}  # em ordem
    # continuam lá ao reabrir, e um PUT sem medições não as apaga
    c = cliente.put(f"/api/analises/{a['id']}", json={"condicoes": {"ambiente_c": "25"}}).json()
    assert [m["nome"] for m in c["medicoes"]] == ["P1", "L1"]
    assert cliente.put(f"/api/analises/{a['id']}", json={"medicoes": [{"tipo": "ponto", "x": "a"}]}).status_code == 422
    assert cliente.put(f"/api/analises/{a['id']}", json={"exibicao": {"faixa": [30, 30]}}).status_code == 422


def test_exportacoes(cliente) -> None:
    a = _analisar(cliente)
    cliente.put(f"/api/analises/{a['id']}", json={"medicoes": [{"tipo": "ponto", "x": 80, "y": 62}]})
    png = cliente.get(f"/api/analises/{a['id']}/imagem.png", params={"largura": 640})
    assert png.status_code == 200 and "teste_termograma.png" in png.headers["content-disposition"]
    assert Image.open(io.BytesIO(png.content)).size == (640, 480)

    csv = cliente.get(f"/api/analises/{a['id']}/temperaturas.csv")
    texto = csv.content.decode("utf-8")
    assert texto.startswith("﻿") and "teste_temperaturas.csv" in csv.headers["content-disposition"]
    linhas = texto.lstrip("﻿").splitlines()
    assert len(linhas) == 121 and linhas[0].startswith("y / x;0;1;2") and len(linhas[1].split(";")) == 161
    assert "45,00" in linhas[61]  # vírgula decimal, como o Excel em português espera

    planilha = cliente.get("/api/inspecoes.csv").content.decode("utf-8").lstrip("﻿").splitlines()
    assert planilha[0].startswith("Data da captura;Arquivo;Instalação") and "teste.jpg" in planilha[1]


def test_parametros_de_medicao(cliente) -> None:
    a = _analisar(cliente)
    t0 = a["regioes"][0]["medida"]["t_max"]
    b = cliente.post(f"/api/analises/{a['id']}/parametros", json={"emissividade": 0.7, "umidade_relativa": 60})
    assert b.status_code == 200, b.text
    b = b.json()
    assert b["parametros_ajustados"] == ["emissividade", "umidade_relativa"]
    assert b["metadados"]["emissividade"] == pytest.approx(0.7) and b["metadados"]["umidade_relativa"] == pytest.approx(0.6)
    assert b["regioes"][0]["medida"]["t_max"] > t0 + 2  # emissividade menor: o objeto está mais quente do que parecia
    c = cliente.post(f"/api/analises/{a['id']}/parametros", json={"restaurar": True}).json()
    assert "parametros_ajustados" not in c and c["regioes"][0]["medida"]["t_max"] == pytest.approx(t0, abs=0.01)
    assert cliente.post(f"/api/analises/{a['id']}/parametros", json={"emissividade": 1.5}).status_code == 422
    assert cliente.post(f"/api/analises/{a['id']}/parametros", json={"distancia_m": "longe"}).status_code == 422
