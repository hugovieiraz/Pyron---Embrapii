"""Modelo de componentes + detector de pontos quentes: em qual peça está o calor e como as peças se comparam."""

from __future__ import annotations

import json

import numpy as np
import pytest

from nucleo import analise, detectores
from testes.test_avaliacoes import _cartao, _zip, sessao_falsa  # noqa: F401  (fixture da sessão ONNX falsa)
from testes.test_servidor import _termograma_flir


def _cena() -> tuple[np.ndarray, list[dict]]:
    """Três para-raios lado a lado; o terminal superior do primeiro tem um ponto a 45 °C."""
    t = np.full((120, 160), -10.0)  # céu
    regioes = []
    for fase, x0 in enumerate((20, 70, 120), start=1):
        t[15:105, x0:x0 + 20] = 25.0 + fase * 0.3  # corpo do para-raio
        regioes.append({"id": f"pr{fase}", "nome": f"Para-raio {fase}", "classe": "para_raio", "caixa": [x0, 15, x0 + 20, 105]})
        regioes.append({"id": f"ts{fase}", "nome": f"Terminal superior {fase}", "classe": "terminal_superior", "caixa": [x0, 15, x0 + 20, 30]})
    t[20:23, 28:31] = 45.0  # defeito no terminal superior da fase 1
    regioes.append({"id": "pq1", "nome": "Ponto quente 1", "classe": "ponto_quente", "caixa": [26, 18, 33, 25]})
    return t, regioes


def test_ponto_quente_fica_na_peca_mais_especifica() -> None:
    t, regioes = _cena()
    itens, resumo = analise.analisar_regioes(t, regioes)
    pq = next(i for i in itens if i["id"] == "pq1")
    assert pq["componente"]["id"] == "ts1"  # o terminal, não o para-raio inteiro que também contém o ponto

    ponto = resumo["ponto_mais_quente"]
    assert ponto["t_max"] == pytest.approx(45.0)
    assert ponto["componente"]["nome"] == "Terminal superior 1"
    assert [c["id"] for c in ponto["dentro_de"]] == ["pr1"]
    assert ponto["regiao"]["id"] == "pq1"


def test_comparacao_entre_pecas_iguais() -> None:
    t, regioes = _cena()
    _, resumo = analise.analisar_regioes(t, regioes)
    grupos = {g["classe"]: g for g in resumo["comparacao_componentes"]}
    assert set(grupos) == {"para_raio", "terminal_superior"}  # o ponto quente não entra na comparação
    ts = grupos["terminal_superior"]
    assert [i["id"] for i in ts["itens"]] == ["ts1", "ts3", "ts2"]  # do mais quente para o mais frio
    assert ts["amplitude_c"] == pytest.approx(45.0 - 25.6, abs=0.01)
    assert ts["itens"][0]["dt"] == pytest.approx(45.0 - 25.9, abs=0.01)  # contra a mediana dos três
    amplitudes = [g["amplitude_c"] for g in resumo["comparacao_componentes"]]
    assert amplitudes == sorted(amplitudes, reverse=True)  # maior diferença primeiro
    # a caixa do para-raio contém o terminal: o calor do terminal também aparece no para-raio 1
    assert grupos["para_raio"]["itens"][0]["id"] == "pr1"


def test_so_pontos_quentes_nao_inventa_peca() -> None:
    t, regioes = _cena()
    itens, resumo = analise.analisar_regioes(t, [r for r in regioes if r["classe"] == "ponto_quente"])
    assert "componente" not in itens[0]
    assert resumo["ponto_mais_quente"]["componente"] is None
    assert resumo["comparacao_componentes"] == []


def test_lista_oferece_um_outro_ou_os_dois(tmp_path) -> None:
    pasta = tmp_path / "modelos" / "para-raios-rfdetr-teste"
    pasta.mkdir(parents=True)
    (pasta / "cartao.json").write_text(json.dumps(_cartao()), encoding="utf-8")
    (pasta / "modelo.onnx").write_bytes(b"onnx falso")
    lista = detectores.listar(tmp_path / "modelos")
    assert [d.id for d in lista] == ["pontos-quentes", "pontos-quentes-sam2", "para-raios-rfdetr-teste", "para-raios-rfdetr-teste+pontos-quentes"]
    combinado = lista[-1]
    assert combinado.tipo == "combinado" and combinado.precisa_imagem
    assert "ponto_quente" in combinado.classes and "aletas_isoladoras" in combinado.classes


def test_resolve_modelo_termico_e_marca_principais(monkeypatch) -> None:
    from app import servidor

    def treinado(id_: str, otimizacao: dict | None = None) -> detectores.Detector:
        cartao = {"id": id_, "classes": ["para_raio"]}
        if otimizacao:
            cartao["otimizacao"] = otimizacao
        return detectores.Detector(id_, id_, "aprendizado", "teste", "", ["para_raio"], cartao=cartao)

    pontos = detectores.obter("pontos-quentes")
    sam2 = detectores.Detector("sam2-dinov2", "SAM 2", "aprendizado", "teste", "", [], cartao={})
    modelo = treinado("para-raios")
    rapido = treinado("para-raios-int8", {"origem": "para-raios"})
    combinados = [detectores.Combinado(d, pontos) for d in (modelo, rapido)]
    instalados = [pontos, detectores.obter("pontos-quentes-sam2"), sam2, modelo, rapido, *combinados]
    config = {"modelo_ativo": "pontos-quentes"}
    monkeypatch.setattr(servidor, "_config", lambda: config)
    monkeypatch.setattr(servidor.detectores, "listar", lambda _: instalados)
    monkeypatch.setattr(servidor, "_onde_modelo_ativo", lambda: None)
    monkeypatch.setattr(servidor.provedores, "situacao", lambda: {})

    assert servidor._modelo_termico() == "para-raios+pontos-quentes"
    resposta = servidor.modelos()
    assert resposta["ativo"] == "para-raios+pontos-quentes"
    principais = {m["id"] for m in resposta["modelos"] if m.get("principal")}
    assert principais == {"para-raios+pontos-quentes"}

    config["modelo_ativo"] = "para-raios-int8+pontos-quentes"
    assert servidor._modelo_termico() == "para-raios-int8+pontos-quentes"
    instalados = [pontos, detectores.obter("pontos-quentes-sam2"), sam2, rapido, combinados[1]]
    resposta = servidor.modelos()
    assert {m["id"] for m in resposta["modelos"] if m.get("principal")} == {"pontos-quentes"}
    instalados = [pontos, detectores.obter("pontos-quentes-sam2"), sam2, modelo, rapido, *combinados]
    config["modelo_ativo"] = "para-raios"
    monkeypatch.setattr(servidor, "_salvar_config", lambda _: None)
    servidor.definir_ativo({"id": "para-raios"})
    assert config["modelo_ativo"] == "para-raios+pontos-quentes"

    instalados = [pontos, detectores.obter("pontos-quentes-sam2"), sam2]
    config["modelo_ativo"] = "pontos-quentes"
    resposta = servidor.modelos()
    assert servidor._modelo_termico() == "pontos-quentes"
    assert {m["id"] for m in resposta["modelos"] if m.get("principal")} == {"pontos-quentes"}


def test_ponto_quente_normal_some_e_anormal_permanece(monkeypatch) -> None:
    from app import servidor

    for temperatura, esperado in ((25.0, False), (100.0, True)):
        matriz = np.full((20, 20), 25.0)
        matriz[8:12, 8:12] = temperatura
        analise_regiao = {
            "id": "pq", "nome": "Ponto quente 1", "classe": "ponto_quente",
            "caixa": [8, 8, 12, 12], "origem": "modelo:pontos-quentes",
        }
        a = {"condicoes": {}, "regioes": [analise_regiao]}
        servidor._calcular(a, matriz)
        if esperado:
            assert a["regioes"][0]["severidade"] not in ("normal", "sem_medida")
        servidor._remover_pontos_quentes_sem_anomalia(a, matriz)
        assert bool(a["regioes"]) is esperado
        # O marcador e a temperatura máxima continuam vindo da matriz toda.
        assert a["resumo"]["t_max_cena"] == pytest.approx(temperatura)
        assert a["resumo"]["ponto_mais_quente"]["t_max"] == pytest.approx(temperatura)


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    return TestClient(servidor.app)


def test_analise_com_os_dois_juntos(cliente, sessao_falsa) -> None:  # noqa: F811
    cartao = _cartao()
    pacote = {f"{cartao['id']}/cartao.json": json.dumps(cartao).encode(), f"{cartao['id']}/modelo.onnx": b"onnx falso"}
    assert cliente.post("/api/modelos/instalar", files={"arquivo": ("m.zip", _zip(pacote), "application/zip")}).status_code == 200
    combinado = f"{cartao['id']}+pontos-quentes"
    assert cliente.put("/api/modelos/ativo", json={"id": combinado}).status_code == 200

    a = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _termograma_flir(), "image/jpeg")}).json()
    assert a["modelo"]["tipo"] == "combinado"
    classes = sorted(r["classe"] for r in a["regioes"])
    assert classes == ["aletas_isoladoras", "ponto_quente"]  # a peça (modelo) e o calor (regra)
    pq = next(r for r in a["regioes"] if r["classe"] == "ponto_quente")
    assert pq["componente"]["classe"] == "aletas_isoladoras"
    assert a["resumo"]["ponto_mais_quente"]["t_max"] == pytest.approx(45.0, abs=0.1)
    assert a["resumo"]["ponto_mais_quente"]["componente"]["classe"] == "aletas_isoladoras"

    cliente.put("/api/configuracoes", json={"responsaveis": [{"nome": "Maria Souza", "registro": "CREA-PB 123456"}]})
    pdf = cliente.get(f"/api/analises/{a['id']}/laudo.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    # só o modelo de peças: sem ponto quente
    r = cliente.post(f"/api/analises/{a['id']}/detectar", json={"modelo": cartao["id"]}).json()
    assert [x["classe"] for x in r["regioes"]] == ["aletas_isoladoras"]
