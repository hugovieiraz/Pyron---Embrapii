"""Testes do registro de detectores, da regra de pontos quentes e da análise por região."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from nucleo import analise, detectores
from nucleo.detectores.pontos_quentes import PontosQuentes


def _cena_com_ponto_quente() -> np.ndarray:
    """Céu frio, um equipamento morno e uma conexão bem mais quente no meio dele."""
    t = np.full((120, 160), -15.0)
    t[40:110, 30:130] = 30.0  # equipamento
    t[60:64, 78:82] = 45.0  # conexão quente (4×4 pixels)
    return t


def test_regra_acha_o_ponto_quente_e_ignora_o_equipamento_uniforme() -> None:
    dets = PontosQuentes().detectar(_cena_com_ponto_quente())
    assert len(dets) == 1
    x0, y0, x1, y1 = dets[0].caixa
    assert x0 <= 78 and x1 >= 82 and y0 <= 60 and y1 >= 64


def test_regra_nao_acusa_cena_uniforme() -> None:
    t = np.full((120, 160), -15.0)
    t[40:110, 30:130] = 30.0
    assert PontosQuentes().detectar(t) == []


def test_severidade_entre_fases_semelhantes() -> None:
    t = np.full((120, 160), 25.0)
    t[20:30, 20:30] = 30.0  # fase A
    t[20:30, 70:80] = 30.5  # fase B
    t[20:30, 120:130] = 38.0  # fase C: 7,5 °C acima da mediana
    regioes = [
        {"id": f, "nome": f, "classe": "terminal_superior", "caixa": [x - 1, 19, x + 11, 31]}
        for f, x in (("A", 20), ("B", 70), ("C", 120))
    ]
    saida, resumo = analise.analisar_regioes(t, regioes)
    por_nome = {r["nome"]: r for r in saida}
    assert por_nome["C"]["ref_tipo"] == "semelhantes"
    assert por_nome["C"]["dt_ref"] == pytest.approx(7.5, abs=0.01)
    assert por_nome["C"]["severidade"] == "atencao"  # modelo brasileiro: 5 a 10 °C
    assert por_nome["C"]["criterio_disparo"] == ["ΔT entre semelhantes"]
    assert por_nome["A"]["severidade"] == "normal"
    assert resumo["severidade"] == "atencao"
    assert not por_nome["C"]["indicativa"]
    neta, _ = analise.analisar_regioes(t, regioes, criterios=analise.CRITERIOS_NETA)
    assert {r["nome"]: r for r in neta}["C"]["severidade"] == "programar"  # NETA: 4 a 15 °C


def test_projecao_para_plena_carga_contra_a_mta() -> None:
    t = np.full((60, 60), 30.0)
    t[20:30, 20:30] = 50.0  # conexão a 50 °C com ambiente de 30 °C e 50% de carga
    regioes = [{"id": "1", "nome": "Conexão", "classe": "conexao", "caixa": [19, 19, 31, 31]}]
    saida, resumo = analise.analisar_regioes(t, regioes, ambiente_c=30.0, carga_pct=50.0)
    r = saida[0]
    assert r["referencia"]["mta_c"] == 90.0
    assert r["t_projetada"] == pytest.approx(110.0)  # 30 + 20 × (100/50)²
    assert r["pct_mta"] == pytest.approx(122.2, abs=0.1)
    assert r["severidade"] == "imediato"
    assert r["criterio_disparo"] == ["% da MTA"]
    assert r["carga_limite"]["vezes_corrente_atual"] == pytest.approx(1.73, abs=0.01)  # sqrt(60/20)
    assert r["carga_limite"]["pct_nominal"] == pytest.approx(87, abs=1)
    assert r["avaliacao_absoluta"] == "completa" and not r["indicativa"]
    assert resumo["maior_pct_mta"] == pytest.approx(122.2, abs=0.1)


def test_para_raio_usa_faixa_propria_sem_correcao_de_carga() -> None:
    t = np.full((40, 90), 20.0)
    t[10:30, 10:15] = 30.0
    t[10:30, 40:45] = 30.2
    t[10:30, 70:75] = 33.5  # 3,3 °C acima da mediana das fases
    regioes = [{"id": f, "nome": f, "classe": "para_raio", "caixa": [x - 1, 9, x + 6, 31]} for f, x in (("A", 10), ("B", 40), ("C", 70))]
    saida, _ = analise.analisar_regioes(t, regioes, ambiente_c=25.0, carga_pct=50.0)
    c = {r["nome"]: r for r in saida}["C"]
    assert c["dt_corrigido"] == pytest.approx(3.3, abs=0.01)  # sem o fator (100/50)²
    assert c["severidade"] == "atencao"
    assert c["pct_mta"] is None  # para-raio não tem MTA útil


def test_entorno_informa_mas_nao_classifica() -> None:
    t = np.full((60, 60), -10.0)  # céu
    t[10:50, 10:50] = 30.0  # equipamento
    t[20:24, 20:24] = 45.0  # ponto quente
    saida, _ = analise.analisar_regioes(t, [{"id": "1", "nome": "P", "classe": "ponto_quente", "caixa": [18, 18, 26, 26]}])
    r = saida[0]
    assert r["dt_entorno"] == pytest.approx(15.0)
    assert "semelhantes" not in r["niveis"]
    assert r["pct_mta"] == pytest.approx(50.0)  # sem ambiente: medida contra a MTA de 90 °C
    assert r["severidade"] == "normal" and r["indicativa"]


def test_correcao_de_carga_projeta_para_plena_carga() -> None:
    t = np.full((60, 60), 25.0)
    t[10:20, 5:15] = 30.0
    t[10:20, 25:35] = 30.0
    t[10:20, 45:55] = 33.0  # 3 °C a 50% de carga -> 12 °C a plena carga
    regioes = [{"id": str(i), "nome": str(i), "classe": "bucha", "caixa": [x - 1, 9, x + 11, 21]} for i, x in enumerate((5, 25, 45))]
    saida, resumo = analise.analisar_regioes(t, regioes, carga_pct=50)
    quente = max(saida, key=lambda r: r["medida"]["t_max"])
    assert quente["dt_corrigido"] == pytest.approx(12.0, abs=0.05)
    assert quente["severidade"] == "programar"
    assert resumo["fator_carga"] == pytest.approx(4.0)


def test_limites_do_criterio() -> None:
    lim = analise.CRITERIOS_PADRAO["similares"]  # 5–10 atenção, >10–20 programar, >20–40 urgente, >40 imediato
    assert analise.nivel_por_limites(3.0, lim) == "normal"
    assert analise.nivel_por_limites(5.0, lim) == "atencao"
    assert analise.nivel_por_limites(10.0, lim) == "atencao"
    assert analise.nivel_por_limites(10.5, lim) == "programar"
    assert analise.nivel_por_limites(25.0, lim) == "urgente"
    assert analise.nivel_por_limites(41.0, lim) == "imediato"
    mta = analise.CRITERIOS_PADRAO["mta_faixas"]  # % da MTA: >60 atenção, >70 programar, >80 urgente, >100 imediato
    assert analise.nivel_por_limites(60.0, mta) == "normal"
    assert analise.nivel_por_limites(75.0, mta) == "programar"
    assert analise.nivel_por_limites(101.0, mta) == "imediato"


def _modelo_onnx_minimo(pasta: Path) -> None:
    """Rede que ignora a imagem e sempre devolve duas caixas: segue o contrato do LEIA-ME."""
    import onnx
    from onnx import TensorProto, helper

    caixas = np.array([[[0.25, 0.25, 0.5, 0.5], [0.6, 0.6, 0.7, 0.7]]], dtype=np.float32)
    pontuacoes = np.array([[0.9, 0.2]], dtype=np.float32)
    classes = np.array([[1, 0]], dtype=np.int64)
    nos = [
        helper.make_node("Shape", ["imagem"], ["forma"]),
        helper.make_node("Constant", [], ["caixas"], value=helper.make_tensor("c", TensorProto.FLOAT, caixas.shape, caixas.ravel())),
        helper.make_node("Constant", [], ["pontuacoes"], value=helper.make_tensor("p", TensorProto.FLOAT, pontuacoes.shape, pontuacoes.ravel())),
        helper.make_node("Constant", [], ["classes"], value=helper.make_tensor("k", TensorProto.INT64, classes.shape, classes.ravel())),
    ]
    grafo = helper.make_graph(
        nos,
        "minimo",
        [helper.make_tensor_value_info("imagem", TensorProto.FLOAT, [1, 3, 64, 64])],
        [
            helper.make_tensor_value_info("caixas", TensorProto.FLOAT, [1, 2, 4]),
            helper.make_tensor_value_info("pontuacoes", TensorProto.FLOAT, [1, 2]),
            helper.make_tensor_value_info("classes", TensorProto.INT64, [1, 2]),
            helper.make_tensor_value_info("forma", TensorProto.INT64, [4]),
        ],
    )
    modelo = helper.make_model(grafo, opset_imports=[helper.make_opsetid("", 17)])
    modelo.ir_version = 8
    onnx.save(modelo, pasta / "modelo.onnx")
    cartao = {
        "id": "teste-minimo",
        "nome": "Modelo mínimo de teste",
        "arquitetura": "constante",
        "classes": ["para_raio", "terminal_superior"],
        "entrada": {"largura": 64, "altura": 64, "t_min": -20, "t_max": 80},
        "limiar_confianca": 0.5,
    }
    (pasta / "cartao.json").write_text(json.dumps(cartao), encoding="utf-8")


def test_modelo_instalado_e_reconhecido_e_usado(tmp_path: Path) -> None:
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    pasta = tmp_path / "teste-minimo"
    pasta.mkdir()
    _modelo_onnx_minimo(pasta)

    ids = [d.id for d in detectores.listar(tmp_path)]
    assert ids == ["pontos-quentes", "teste-minimo"]
    det = detectores.obter("teste-minimo", tmp_path)
    assert det.tipo == "aprendizado"
    dets = det.detectar(np.full((120, 160), 20.0))
    assert len(dets) == 1  # a segunda caixa fica abaixo do limiar de confiança
    assert dets[0].classe == "terminal_superior"
    assert dets[0].caixa == pytest.approx([40.0, 30.0, 80.0, 60.0])


def test_modelo_com_arquivo_faltando_aparece_com_erro(tmp_path: Path) -> None:
    pasta = tmp_path / "quebrado"
    pasta.mkdir()
    (pasta / "cartao.json").write_text(json.dumps({"id": "quebrado", "nome": "x", "arquitetura": "x", "classes": [], "entrada": {}}), encoding="utf-8")
    lista = detectores.listar(tmp_path)
    assert lista[-1].nome.endswith("(com erro)")
    with pytest.raises(ValueError):
        lista[-1].detectar(np.zeros((4, 4)))
