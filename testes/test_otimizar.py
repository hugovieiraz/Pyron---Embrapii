"""Versão rápida (INT8) de um modelo: gerada ao lado do original e preferida pela câmera do celular."""

from __future__ import annotations

import json

import numpy as np
import pytest

from nucleo.detectores import Detector


def _modelo_minusculo(pasta) -> None:
    """ONNX de uma camada (imagem 8×8 → 4 números por um MatMul) com um cartão válido do Pyron."""
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper, numpy_helper

    pasta.mkdir(parents=True)
    peso = numpy_helper.from_array(np.random.default_rng(0).standard_normal((192, 4)).astype(np.float32), "peso")
    forma = numpy_helper.from_array(np.array([1, 192], dtype=np.int64), "forma")
    grafo = helper.make_graph(
        [helper.make_node("Reshape", ["input", "forma"], ["plano"]), helper.make_node("MatMul", ["plano", "peso"], ["saida"])],
        "minusculo",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 8, 8])],
        [helper.make_tensor_value_info("saida", TensorProto.FLOAT, [1, 4])],
        initializer=[peso, forma],
    )
    modelo = helper.make_model(grafo, opset_imports=[helper.make_opsetid("", 17)])
    modelo.ir_version = 8
    onnx.save(modelo, str(pasta / "modelo.onnx"))
    (pasta / "cartao.json").write_text(json.dumps({
        "id": "minusculo", "nome": "Minúsculo", "arquitetura": "MatMul", "classes": ["para_raio"],
        "entrada": {"fonte": "imagem_exibida", "largura": 8, "altura": 8}, "saida": {"formato": "contrato"},
    }), encoding="utf-8")


def test_gera_a_versao_int8_ao_lado_do_original(tmp_path) -> None:
    from ml import otimizar

    original = tmp_path / "modelos" / "minusculo"
    _modelo_minusculo(original)
    destino = otimizar.otimizar(original)
    assert destino.name == "minusculo-int8"
    cartao = json.loads((destino / "cartao.json").read_text(encoding="utf-8"))
    assert cartao["id"] == "minusculo-int8" and "INT8" in cartao["nome"]
    assert cartao["otimizacao"]["origem"] == "minusculo" and cartao["otimizacao"]["tempo_ms"] >= 0
    with pytest.raises(SystemExit):  # não otimiza o que já foi otimizado
        otimizar.otimizar(destino)


class _Imagem(Detector):
    def __init__(self, id_, otimizacao=None):
        super().__init__(id_, id_, "aprendizado", "-", "", ["para_raio"], cartao={"otimizacao": otimizacao} if otimizacao else {},
                         precisa_imagem=True)


def test_celular_prefere_a_versao_rapida_do_modelo_escolhido(monkeypatch) -> None:
    from app import servidor
    from nucleo import detectores

    original, rapido, outro = _Imagem("pr"), _Imagem("pr-int8", {"origem": "pr"}), _Imagem("outro")
    monkeypatch.setattr(detectores, "listar", lambda _pasta=None: [original, rapido, outro])
    monkeypatch.setattr(servidor, "_detector", lambda _id: original)
    assert servidor._detector_imagem() is rapido
    monkeypatch.setattr(servidor, "_detector", lambda _id: outro)
    assert servidor._detector_imagem() is outro  # sem versão rápida, fica o escolhido
    monkeypatch.setattr(servidor, "_detector", lambda _id: rapido)
    assert servidor._detector_imagem() is rapido
