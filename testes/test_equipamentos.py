"""Equipamentos: agrupamento das inspeções, tendência, projeção até a MTA e próxima inspeção."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app import equipamentos as eq
from testes.test_servidor import _termograma_flir


def _item(id_, data, t_max, severidade="normal", pct=None, inst="SE Teste", equip="TR-01"):
    return {
        "id": id_, "data_captura": data, "criado_em": "2026-10-01T10:00:00",
        "identificacao": {"instalacao": inst, "equipamento": equip},
        "resumo": {"severidade": severidade, "t_max_cena": t_max + 5, "maior_pct_mta": pct},
        "destaque": {"nome": "Bucha 1", "t_max": t_max, "dt": None},
    }


def test_chave_estavel_e_legivel() -> None:
    assert eq.chave("SE Campina Grande II", "TR-01 69/13,8 kV") == "se-campina-grande-ii--tr-01-69-13-8-kv"
    assert eq.chave("Subestação Ação", "Disjuntor 52") == eq.chave("subestacao acao", "DISJUNTOR  52")
    assert eq.chave("SE", "") == eq.SEM_EQUIPAMENTO


def test_tendencia_por_mes_e_minimos() -> None:
    base = datetime(2026, 1, 1)
    pontos = [eq.ponto(_item(f"a{i}", (base + timedelta(days=30 * i)).isoformat(), 40 + i)) for i in range(4)]
    t = eq.tendencia(pontos)
    assert t["por_mes"] == pytest.approx(1.0, abs=0.01) and t["r2"] == pytest.approx(1.0) and t["n"] == 4
    assert eq.tendencia(pontos[:2]) is None  # poucos pontos
    curtos = [eq.ponto(_item(f"b{i}", (base + timedelta(days=3 * i)).isoformat(), 40 + 10 * i)) for i in range(4)]
    assert eq.tendencia(curtos) is None  # em dias, a diferença é de carga e horário, não de desgaste


def test_projecao_ate_a_mta() -> None:
    base = datetime(2026, 1, 1)
    pontos = [eq.ponto(_item(f"a{i}", (base + timedelta(days=30 * i)).isoformat(), 50 + i, pct=60 + 5 * i)) for i in range(5)]
    p = eq.projecao_mta(pontos)
    # 80% na última (dia 120), +5 pontos a cada 30 dias: chega a 100% em 120 dias
    assert p["dias"] == pytest.approx(120, abs=1) and p["confiavel"]
    caindo = [eq.ponto(_item(f"c{i}", (base + timedelta(days=30 * i)).isoformat(), 50, pct=80 - 5 * i)) for i in range(4)]
    assert eq.projecao_mta(caindo) is None


def test_proxima_inspecao_pela_severidade() -> None:
    hoje = datetime(2026, 10, 7)
    normal = eq.proxima_inspecao({"data": "2026-10-01T10:00:00", "severidade": "normal"}, hoje)
    assert normal["data"] == "2027-10-01" and not normal["vencida"] and normal["prazo_dias"] == 365
    urgente = eq.proxima_inspecao({"data": "2026-09-01T10:00:00", "severidade": "urgente"}, hoje)
    assert urgente["vencida"] and urgente["dias"] < 0


def test_lista_do_pior_para_o_melhor_e_sem_equipamento_no_fim() -> None:
    itens = [
        _item("a", "2026-01-01T10:00:00", 40, equip="TR-01"),
        _item("b", "2026-03-01T10:00:00", 70, "urgente", equip="TR-02"),
        _item("c", "2026-02-01T10:00:00", 30, equip=""),
        _item("d", "2026-05-01T10:00:00", 45, "atencao", equip="TR-01"),
    ]
    lista = eq.listar(itens, hoje=datetime(2026, 6, 1))
    assert [e["equipamento"] or e["chave"] for e in lista] == ["TR-02", "TR-01", eq.SEM_EQUIPAMENTO]
    tr01 = lista[1]
    assert tr01["inspecoes"] == 2 and tr01["severidade"] == "atencao" and tr01["ultima_id"] == "d"
    assert [p["id"] for p in tr01["serie"]] == ["a", "d"]  # ordem da captura
    assert "proxima_inspecao" not in lista[2]


def test_componentes_por_classe() -> None:
    analises = [
        {"id": "a", "data_captura": "2026-01-01T10:00:00", "metadados": {}, "regioes": [
            {"classe": "bucha", "nome": "Bucha 1", "medida": {"t_max": 40.0}, "severidade": "normal"},
            {"classe": "bucha", "nome": "Bucha 2", "medida": {"t_max": 44.0}, "severidade": "atencao", "dt_corrigido": 4.0}]},
        {"id": "b", "data_captura": "2026-02-01T10:00:00", "metadados": {}, "regioes": [
            {"classe": "bucha", "nome": "Bucha 2", "medida": {"t_max": 48.0}, "severidade": "programar"}]},
    ]
    [bucha] = eq.componentes(analises)
    assert [p["t_max"] for p in bucha["pontos"]] == [44.0, 48.0] and bucha["severidade"] == "programar"


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    return TestClient(servidor.app)


def test_rotas_de_equipamento(cliente) -> None:
    enviar = lambda **campos: cliente.post("/api/analises", files={"arquivo": ("t.jpg", _termograma_flir(), "image/jpeg")}, data=campos).json()
    a = enviar(instalacao="SE Teste", equipamento="TR-01")
    assert a["identificacao"]["equipamento"] == "TR-01" and a["equipamento_chave"] == "se-teste--tr-01"
    b, c = enviar(), enviar()
    assert {it["equipamento_chave"] for it in cliente.get("/api/analises").json()} == {"se-teste--tr-01", eq.SEM_EQUIPAMENTO}

    r = cliente.post("/api/analises/identificacao", json={"ids": [b["id"], c["id"]], "instalacao": "SE Teste", "equipamento": "TR-01"})
    assert r.status_code == 200 and r.json() == {"atualizadas": 2, "chave": "se-teste--tr-01"}
    assert cliente.post("/api/analises/identificacao", json={"ids": [b["id"]], "equipamento": ""}).status_code == 422
    assert cliente.post("/api/analises/identificacao", json={"ids": ["naoexiste"], "equipamento": "X"}).status_code == 404

    [e] = cliente.get("/api/equipamentos").json()
    assert e["chave"] == "se-teste--tr-01" and e["inspecoes"] == 3 and "proxima_inspecao" in e
    d = cliente.get("/api/equipamentos/se-teste--tr-01").json()
    assert len(d["lista"]) == 3 and d["componentes"] and d["prazos_dias"]["normal"] == 365
    assert cliente.get("/api/equipamentos/outro--x").status_code == 404
    # a identificação antiga (responsável, ART) não se perde ao trocar o equipamento
    cliente.put(f"/api/analises/{b['id']}", json={"identificacao": {"equipamento": "TR-01", "instalacao": "SE Teste", "art": "PB1"}})
    cliente.post("/api/analises/identificacao", json={"ids": [b["id"]], "instalacao": "SE Teste", "equipamento": "TR-02"})
    assert cliente.get(f"/api/analises/{b['id']}").json()["identificacao"]["art"] == "PB1"


def test_tendencia_a_plena_carga_com_ambiente_e_carga() -> None:
    base = datetime(2026, 1, 1)
    itens = []
    # Mesma elevação real a plena carga (40 °C) medida com cargas diferentes: a medida oscila, a normalizada não.
    for i, (carga, amb) in enumerate([(50, 25.0), (100, 30.0), (70, 20.0), (90, 28.0)]):
        it = _item(f"a{i}", (base + timedelta(days=30 * i)).isoformat(), amb + 40 * (carga / 100) ** 2)
        it["condicoes"] = {"ambiente_c": amb, "carga_pct": carga}
        itens.append(it)
    [e] = eq.listar(itens)
    assert [p["elevacao_plena"] for p in e["serie"]] == pytest.approx([40.0] * 4, abs=0.2)
    assert abs(e["tendencia_plena"]["por_mes"]) < 0.1 and e["tendencia"]["r2"] < 0.9
    it = _item("b", "2026-06-01T10:00:00", 50)
    it["condicoes"] = {"ambiente_c": 25.0, "carga_pct": 30}  # carga baixa demais: não projeta
    assert eq.ponto(it)["elevacao_plena"] is None
