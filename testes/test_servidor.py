"""Teste de ponta a ponta do servidor: analisar, editar regiões, recalcular e gerar o laudo."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from testes.test_flir import _bruto_de, _jpeg_flir, _parametros


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    return TestClient(servidor.app)


def _termograma_flir() -> bytes:
    p = _parametros()
    t = np.full((120, 160), -15.0)
    t[40:110, 30:130] = 30.0
    t[60:64, 78:82] = 45.0
    return _jpeg_flir(_bruto_de(t, p), p, png=False)


def test_fluxo_completo(cliente) -> None:
    r = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _termograma_flir(), "image/jpeg")})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["radiometrica"] is True
    assert a["matriz"]["largura"] == 160
    assert len(a["regioes"]) == 1
    assert a["regioes"][0]["medida"]["t_max"] == pytest.approx(45.0, abs=0.1)

    regioes = [{k: v for k, v in x.items() if k in ("id", "nome", "classe", "caixa", "origem")} for x in a["regioes"]]
    regioes.append({"nome": "Manual", "classe": "componente", "caixa": [35, 45, 60, 70], "origem": "manual"})
    r = cliente.put(f"/api/analises/{a['id']}", json={"regioes": regioes, "condicoes": {"ambiente_c": "28", "carga_pct": ""}})
    assert r.status_code == 200, r.text
    b = r.json()
    assert len(b["regioes"]) == 2
    assert b["condicoes"] == {"ambiente_c": 28.0, "carga_pct": None}

    assert len(cliente.get("/api/analises").json()) == 1
    cliente.put("/api/configuracoes", json={"responsaveis": [{"nome": "Maria Souza", "registro": "CREA-PB 123456"}]})
    pdf = cliente.get(f"/api/analises/{a['id']}/laudo.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert cliente.delete(f"/api/analises/{a['id']}").status_code == 200
    assert cliente.get(f"/api/analises/{a['id']}").status_code == 404


def test_arquivo_invalido_da_mensagem_clara(cliente) -> None:
    r = cliente.post("/api/analises", files={"arquivo": ("x.jpg", b"isto nao e imagem", "image/jpeg")})
    assert r.status_code == 422
    assert "Não consegui abrir" in r.json()["erro"]


def test_imagem_sem_escala_e_sem_dados_da_mensagem_clara(cliente) -> None:
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (20, 40, 90)).save(buf, format="JPEG")
    r = cliente.post("/api/analises", files={"arquivo": ("comum.jpg", buf.getvalue(), "image/jpeg")})
    assert r.status_code == 422
    assert "barra de cores" in r.json()["erro"]


def test_modelos_e_interface(cliente) -> None:
    m = cliente.get("/api/modelos").json()
    assert m["ativo"] == "pontos-quentes"
    assert cliente.get("/").status_code == 200
    assert "Pyron" in cliente.get("/").text
