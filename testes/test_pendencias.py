"""Pendências: prazo pela severidade, fluxo da anomalia até a verificação e sugestão de reinspeção."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app import pendencias as pd


def _item(id_, data, severidade, equip="TR-01", acomp=None):
    return {
        "id": id_, "arquivo": f"{id_}.jpg", "data_captura": data, "criado_em": data,
        "identificacao": {"instalacao": "SE Teste", "equipamento": equip},
        "resumo": {"severidade": severidade}, "destaque": {"nome": "Bucha 1", "t_max": 80.0},
        "acompanhamento": acomp,
    }


def test_prazo_pela_severidade_e_vencimento() -> None:
    hoje = date(2026, 10, 7)
    itens = [_item("a", "2026-10-01T10:00:00", "urgente"), _item("b", "2026-09-01T10:00:00", "atencao"),
             _item("c", "2026-10-01T10:00:00", "normal")]
    lista = pd.listar(itens, hoje)
    assert [p["id"] for p in lista] == ["a", "b"]  # a normal não vira pendência
    a, b = lista
    assert a["prazo"] == "2026-10-08" and not a["vencida"] and a["dias"] == 1 and a["prazo_padrao"]
    assert b["prazo"] == "2026-11-30" and b["status"] == "aberta"


def test_vencidas_primeiro_e_corrigida_nao_vence() -> None:
    hoje = date(2026, 10, 7)
    itens = [_item("a", "2026-10-06T10:00:00", "imediato"), _item("b", "2026-01-01T10:00:00", "atencao"),
             _item("c", "2026-01-01T10:00:00", "programar", acomp={"status": "corrigida"})]
    lista = pd.listar(itens, hoje)
    assert [p["id"] for p in lista] == ["b", "a", "c"]
    assert lista[0]["vencida"] and not lista[2]["vencida"]  # corrigida aguarda reinspeção, não está atrasada


def test_reinspecao_normal_do_mesmo_equipamento_e_sugerida() -> None:
    itens = [_item("a", "2026-03-01T10:00:00", "programar"), _item("b", "2026-04-01T10:00:00", "normal"),
             _item("c", "2026-02-01T10:00:00", "normal"), _item("d", "2026-05-01T10:00:00", "normal", equip="TR-02")]
    [p] = pd.listar(itens, date(2026, 10, 7))
    assert p["reinspecao"]["id"] == "b"  # a primeira normal depois, do mesmo equipamento


def test_atualizar_registra_historico_e_valida() -> None:
    a = {"id": "x", "resumo": {"severidade": "urgente"}}
    agora = datetime(2026, 10, 7, 9, 30)
    pd.atualizar(a, {"status": "programada", "ordem_servico": "OS 142", "prazo": "2026-10-20", "nota": "Parada no sábado"}, agora)
    ac = a["acompanhamento"]
    assert ac["status"] == "programada" and ac["ordem_servico"] == "OS 142" and ac["prazo"] == "2026-10-20"
    assert ac["historico"] == [{"quando": "2026-10-07T09:30:00", "status": "programada", "nota": "Parada no sábado"}]
    pd.atualizar(a, {"responsavel": "Equipe B"}, agora)  # sem mudar a situação nem anotar: não polui o histórico
    assert len(a["acompanhamento"]["historico"]) == 1 and a["acompanhamento"]["responsavel"] == "Equipe B"
    pd.atualizar(a, {"prazo": ""}, agora)
    assert "prazo" not in a["acompanhamento"]  # volta ao prazo padrão
    with pytest.raises(ValueError):
        pd.atualizar(a, {"status": "resolvida"})
    with pytest.raises(ValueError):
        pd.atualizar(a, {"prazo": "amanhã"})


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    return TestClient(servidor.app)


def _termograma_quente() -> bytes:
    """Ponto a 80 °C num equipamento a 30 °C: passa de 70% da MTA (90 °C) e vira anomalia."""
    import numpy as np

    from testes.test_flir import _bruto_de, _jpeg_flir, _parametros

    p = _parametros()
    t = np.full((120, 160), -15.0)
    t[40:110, 30:130] = 30.0
    t[60:64, 78:82] = 80.0
    return _jpeg_flir(_bruto_de(t, p), p, png=False)


def test_rotas_de_pendencia(cliente) -> None:
    a = cliente.post("/api/analises", files={"arquivo": ("t.jpg", _termograma_quente(), "image/jpeg")}).json()
    assert a["resumo"]["severidade"] != "normal"
    assert a["pendencia"]["status"] == "aberta"
    [p] = cliente.get("/api/pendencias").json()
    assert p["id"] == a["id"]
    r = cliente.put(f"/api/analises/{a['id']}/acompanhamento", json={"status": "corrigida", "nota": "Reaperto"})
    assert r.status_code == 200 and r.json()["status"] == "corrigida"
    assert cliente.get(f"/api/analises/{a['id']}").json()["pendencia"]["historico"][-1]["nota"] == "Reaperto"
    assert cliente.put(f"/api/analises/{a['id']}/acompanhamento", json={"status": "x"}).status_code == 422
    assert cliente.put("/api/analises/naoexiste/acompanhamento", json={"status": "aberta"}).status_code == 404
