"""Monitoramento: pasta vigiada, alerta pela severidade mínima e mensagem para o WhatsApp."""

from __future__ import annotations

import os
import time
from urllib.parse import unquote

import numpy as np
import pytest

from app import monitoramento
from testes.test_flir import _bruto_de, _jpeg_flir, _parametros


def _termograma(t_quente: float) -> bytes:
    """Equipamento a 30 °C com uma conexão mais quente no meio (detectada pela regra de pontos quentes)."""
    p = _parametros()
    t = np.full((120, 160), -15.0)
    t[40:110, 30:130] = 30.0
    t[60:64, 78:82] = t_quente
    return _jpeg_flir(_bruto_de(t, p), p, png=False)


def _gravar_antigo(caminho, dados: bytes) -> None:
    """Grava e envelhece o arquivo: o monitor só pega arquivos que já pararam de ser gravados."""
    caminho.write_bytes(dados)
    antes = time.time() - 30
    os.utime(caminho, (antes, antes))


def test_validar_configuracao(tmp_path) -> None:
    ok = monitoramento.validar({"ativo": True, "pasta": str(tmp_path), "destinatarios": [{"nome": "Ana", "telefone": "+55 83 99999-0000"}]})
    assert ok["ativo"] and ok["destinatarios"][0]["telefone"] == "+55 83 99999-0000"
    with pytest.raises(monitoramento.ConfiguracaoInvalida, match="pasta"):
        monitoramento.validar({"ativo": True, "pasta": ""})
    with pytest.raises(monitoramento.ConfiguracaoInvalida, match="DDI"):
        monitoramento.validar({"destinatarios": [{"nome": "Ana", "telefone": "9999"}]})
    with pytest.raises(monitoramento.ConfiguracaoInvalida, match="desenvolvimento"):
        monitoramento.validar({"fonte": "rtsp"})
    with pytest.raises(monitoramento.ConfiguracaoInvalida, match="desenvolvimento"):
        monitoramento.validar({"envio": "automatico"})


def test_link_do_whatsapp_leva_so_digitos_e_texto_codificado() -> None:
    links = monitoramento.links_whatsapp("[Pyron] URGENTE\nLinha 2", [{"nome": "Ana", "telefone": "+55 (83) 99999-0000"}])
    assert links[0]["url"].startswith("https://wa.me/5583999990000?text=")
    assert unquote(links[0]["url"].split("text=")[1]) == "[Pyron] URGENTE\nLinha 2"


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    yield TestClient(servidor.app)
    servidor.monitor.parar()


def test_pasta_vigiada_analisa_o_novo_e_alerta_uma_vez(cliente, tmp_path) -> None:
    pasta = tmp_path / "camera"
    pasta.mkdir()
    _gravar_antigo(pasta / "ja_estava.jpg", _termograma(80.0))  # anterior ao monitoramento: ignorada

    r = cliente.put("/api/monitoramento", json={
        "ativo": True, "pasta": str(pasta), "intervalo_s": 3600, "severidade_minima": "urgente",
        "instalacao": "SE Teste", "equipamento": "TR-01",
        "destinatarios": [{"nome": "Ana", "telefone": "+55 83 99999-0000"}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["config"]["ativo"] is True

    _gravar_antigo(pasta / "nova_quente.jpg", _termograma(80.0))  # 80 °C numa conexão: 89% da MTA de 90 °C
    assert cliente.post("/api/monitoramento/verificar").status_code == 200

    analises = cliente.get("/api/analises").json()
    assert [a["arquivo"] for a in analises] == ["nova_quente.jpg"]
    assert analises[0]["fonte"] == "monitoramento"
    assert analises[0]["identificacao"]["equipamento"] == "TR-01"
    assert analises[0]["resumo"]["severidade"] == "urgente"

    alertas = cliente.get("/api/alertas").json()
    assert alertas["pendentes"] == 1
    alerta = alertas["alertas"][0]
    assert alerta["mensagem"].startswith("[Pyron] URGENTE: SE Teste · TR-01")
    assert "89% da MTA" in alerta["mensagem"]

    # Outra imagem no mesmo nível logo em seguida: analisa, mas não repete o alerta.
    _gravar_antigo(pasta / "outra_quente.jpg", _termograma(80.0))
    cliente.post("/api/monitoramento/verificar")
    assert len(cliente.get("/api/analises").json()) == 2
    assert cliente.get("/api/alertas").json()["pendentes"] == 1

    wa = cliente.get(f"/api/alertas/{alerta['id']}/whatsapp").json()
    assert wa["links"][0]["url"].startswith("https://wa.me/5583999990000?text=")

    assert cliente.put(f"/api/alertas/{alerta['id']}", json={"status": "resolvido"}).json()["status"] == "resolvido"
    status = cliente.get("/api/status").json()
    assert status["alertas_pendentes"] == 0 and status["monitoramento"]["ativo"] is True

    assert cliente.put("/api/monitoramento", json={"ativo": False}).json()["estado"]["vigiando"] is False


def test_imagem_abaixo_do_minimo_nao_alerta(cliente, tmp_path) -> None:
    pasta = tmp_path / "camera"
    pasta.mkdir()
    cliente.put("/api/monitoramento", json={"ativo": True, "pasta": str(pasta), "intervalo_s": 3600, "severidade_minima": "urgente"})
    _gravar_antigo(pasta / "morna.jpg", _termograma(45.0))  # 50% da MTA: normal
    cliente.post("/api/monitoramento/verificar")
    assert len(cliente.get("/api/analises").json()) == 1
    assert cliente.get("/api/alertas").json()["alertas"] == []


def test_configuracao_invalida_da_mensagem_clara(cliente, tmp_path) -> None:
    r = cliente.put("/api/monitoramento", json={"ativo": True, "pasta": str(tmp_path / "nao_existe")})
    assert r.status_code == 422
    assert "não existe" in r.json()["erro"]


def test_cada_subpasta_e_um_equipamento(cliente, tmp_path) -> None:
    pasta = tmp_path / "cameras"
    (pasta / "TR-01").mkdir(parents=True)
    (pasta / "TR-02").mkdir()
    _gravar_antigo(pasta / "TR-01" / "antiga.jpg", _termograma(45.0))  # já estava: fica de fora
    r = cliente.put("/api/monitoramento", json={"ativo": True, "pasta": str(pasta), "intervalo_s": 3600, "subpastas": True,
                                                "instalacao": "SE Teste", "equipamento": "Geral"})
    assert r.status_code == 200 and r.json()["config"]["subpastas"] is True
    _gravar_antigo(pasta / "TR-01" / "a.jpg", _termograma(45.0))
    _gravar_antigo(pasta / "TR-02" / "b.jpg", _termograma(45.0))
    _gravar_antigo(pasta / "solta.jpg", _termograma(45.0))
    cliente.post("/api/monitoramento/verificar")
    equips = {a["arquivo"]: a["identificacao"].get("equipamento") for a in cliente.get("/api/analises").json()}
    assert equips == {"a.jpg": "TR-01", "b.jpg": "TR-02", "solta.jpg": "Geral"}
    assert {e["equipamento"] for e in cliente.get("/api/equipamentos").json()} == {"TR-01", "TR-02", "Geral"}
