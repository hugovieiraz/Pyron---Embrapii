"""O servidor só se desliga quando a última janela do aplicativo fecha."""

from __future__ import annotations

from app.iniciar import deve_encerrar


def _sinais(**clientes: float) -> dict:
    return {"clientes": dict(clientes), "algum": bool(clientes), "encerrar": False}


def test_fechar_uma_de_duas_janelas_nao_desliga() -> None:
    s = _sinais(a=100.0, b=100.0)
    s["clientes"].pop("a")  # a janela "a" avisou que saiu
    sair, vazio = deve_encerrar(s, agora=130.0, inicio=0.0, vazio_desde=None)
    assert not sair and vazio is None


def test_ultima_janela_fechada_desliga_depois_da_tolerancia() -> None:
    s = _sinais()
    s["algum"] = True
    sair, vazio = deve_encerrar(s, agora=200.0, inicio=0.0, vazio_desde=None)
    assert not sair and vazio == 200.0  # começa a contar
    sair, _ = deve_encerrar(s, agora=205.0, inicio=0.0, vazio_desde=vazio)
    assert not sair  # uma recarga de página cabe aqui
    sair, _ = deve_encerrar(s, agora=209.0, inicio=0.0, vazio_desde=vazio)
    assert sair


def test_recarga_volta_a_contar_do_zero() -> None:
    s = _sinais()
    s["algum"] = True
    _, vazio = deve_encerrar(s, agora=200.0, inicio=0.0, vazio_desde=None)
    s["clientes"]["nova"] = 203.0  # a página recarregada mandou sinal
    sair, vazio = deve_encerrar(s, agora=204.0, inicio=0.0, vazio_desde=vazio)
    assert not sair and vazio is None


def test_janela_muda_expira() -> None:
    s = _sinais(a=0.0)
    sair, vazio = deve_encerrar(s, agora=181.0, inicio=0.0, vazio_desde=None)
    assert "a" not in s["clientes"] and not sair and vazio == 181.0


def test_ninguem_abriu() -> None:
    s = _sinais()
    assert not deve_encerrar(s, agora=500.0, inicio=0.0, vazio_desde=None)[0]
    assert deve_encerrar(s, agora=601.0, inicio=0.0, vazio_desde=None)[0]


def test_rota_de_sinal_conta_janelas(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app import servidor

    monkeypatch.setattr(servidor, "sinais", {"clientes": {}, "algum": False, "encerrar": False})
    c = TestClient(servidor.app)
    assert c.get("/api/saude").json()["app"] == "Pyron"
    assert c.post("/api/sinal?cliente=a").json()["janelas"] == 1
    assert c.post("/api/sinal?cliente=b").json()["janelas"] == 2
    assert c.post("/api/sinal?cliente=a&saindo=true").json()["janelas"] == 1
    assert servidor.sinais["algum"]
