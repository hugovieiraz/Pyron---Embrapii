"""Versão rápida (INT8) de um modelo: gerada ao lado do original e preferida pela câmera do celular."""

from __future__ import annotations

import json

import numpy as np
import pytest

from nucleo.detectores import Detector


def _importar_ou_pular(nome: str):
    """Importa o pacote ou pula o teste: o Controle Inteligente de Aplicativos do Windows às vezes barra
    DLL sem assinatura (onnx, torch) com OSError ou ImportError, conforme o dia."""
    import importlib

    try:
        return importlib.import_module(nome)
    except (ImportError, OSError) as erro:
        pytest.skip(f"{nome} não carrega neste computador: {erro}")


def _modelo_minusculo(pasta) -> None:
    """ONNX de uma camada (imagem 8×8 → 4 números por um MatMul) com um cartão válido do Pyron."""
    onnx = _importar_ou_pular("onnx")
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


def test_video_usa_a_versao_rapida_tambem_do_modelo_combinado(monkeypatch) -> None:
    from app import servidor
    from nucleo import detectores
    from nucleo.detectores.pontos_quentes import PontosQuentes

    pontos = PontosQuentes()
    original, rapido = _Imagem("pr"), _Imagem("pr-int8", {"origem": "pr"})
    comb, comb_rapido = detectores.Combinado(original, pontos), detectores.Combinado(rapido, pontos)
    monkeypatch.setattr(detectores, "listar", lambda _pasta=None: [pontos, original, rapido, comb, comb_rapido])
    assert servidor._versao_rapida(comb) is comb_rapido
    assert servidor._versao_rapida(original) is rapido
    assert servidor._versao_rapida(pontos) is pontos  # regra não tem versão rápida
    assert servidor._versao_rapida(comb_rapido) is comb_rapido


def test_ao_vivo_vai_para_a_placa_de_video_quando_ela_fica_pronta(monkeypatch) -> None:
    from app import servidor
    from nucleo import detectores
    from nucleo.detectores import placa
    from nucleo.detectores.pontos_quentes import PontosQuentes

    pontos = PontosQuentes()
    original, rapido = _Imagem("pr"), _Imagem("pr-int8", {"origem": "pr"})
    na_placa = _Imagem("pr")
    monkeypatch.setattr(detectores, "listar", lambda _pasta=None: [pontos, original, rapido, detectores.Combinado(rapido, pontos)])
    pedidos = []
    monkeypatch.setattr(placa, "variante", lambda det: pedidos.append(det.id) or None)
    assert servidor._ao_vivo(original) is rapido  # placa ainda carregando: a versão rápida na CPU
    assert servidor._ao_vivo(rapido) is rapido and pedidos == ["pr", "pr"]  # a placa roda o original, não o INT8
    monkeypatch.setattr(placa, "variante", lambda det: na_placa if det.id == "pr" else None)
    assert servidor._ao_vivo(original) is na_placa
    combinado = servidor._ao_vivo(detectores.Combinado(original, pontos))
    assert combinado.partes[0] is na_placa and combinado.partes[1] is pontos


def test_sem_pesos_do_pytorch_o_modelo_fica_na_cpu() -> None:
    from nucleo.detectores import placa

    assert placa.variante(_Imagem("sem-pesos")) is None
    assert placa.situacao(_Imagem("sem-pesos"))["onde"] == "cpu"


def test_na_placa_de_video_as_pecas_sao_as_mesmas_do_onnx() -> None:
    """Só roda neste notebook: modelo instalado com os pesos do PyTorch e placa com CUDA."""
    from pathlib import Path

    from nucleo.detectores import placa
    from nucleo.detectores.onnx_modelo import DetectorONNX

    pasta = Path(__file__).resolve().parents[1] / "modelos" / "para-raios-rfdetr-local-20260930-1627"
    if not (pasta / "pesos.pth").exists():
        pytest.skip("modelo com pesos do PyTorch não instalado")
    torch = _importar_ou_pular("torch")
    if not torch.cuda.is_available():
        pytest.skip("sem placa de vídeo com CUDA")
    from testes.test_paleta import _cena, _imagem_sintetica

    cpu = DetectorONNX(pasta)
    gpu = placa.DetectorPlaca(cpu)
    gpu.carregar()
    img = _imagem_sintetica(50.0, 10.0, _cena())
    t = np.zeros(img.shape[:2], np.float32)
    a, b = cpu.detectar(t, img), gpu.detectar(t, img)
    assert [d.classe for d in a] == [d.classe for d in b]
    for x, y in zip(a, b):
        assert np.allclose(x.caixa, y.caixa, atol=2.0) and abs(x.confianca - y.confianca) < 0.02
