"""Escolha do provedor do ONNX Runtime (0.9, F4), com o ONNX Runtime simulado: roda em qualquer computador."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo.detectores import provedores

TODOS = ["TensorrtExecutionProvider", "CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"]


def _ort(*nomes):
    return SimpleNamespace(get_available_providers=lambda: list(nomes))


def test_disponiveis_na_ordem_e_cpu_sempre() -> None:
    assert provedores.disponiveis(_ort(*TODOS)) == ["tensorrt", "cuda", "directml", "cpu"]
    assert provedores.disponiveis(_ort("CPUExecutionProvider", "DmlExecutionProvider")) == ["directml", "cpu"]
    assert provedores.disponiveis(_ort()) == ["cpu"]


@pytest.mark.parametrize("oferecidos, esperado", [
    (["tensorrt", "cuda", "directml", "cpu"], "tensorrt"),
    (["cuda", "cpu"], "cuda"),
    (["directml", "cpu"], "directml"),  # o computador de desenvolvimento: igual a antes da 0.9
    (["cpu"], "cpu"),
])
def test_automatico_tensorrt_cuda_directml_cpu(oferecidos, esperado) -> None:
    assert provedores.escolher("auto", oferecidos) == (esperado, "")


def test_pedido_que_nao_existe_desce_e_explica() -> None:
    escolhido, motivo = provedores.escolher("tensorrt", ["directml", "cpu"])
    assert escolhido == "directml" and "TensorRT" in motivo
    assert provedores.escolher("cuda", ["tensorrt", "cuda", "cpu"]) == ("cuda", "")
    assert provedores.escolher("cpu", ["tensorrt", "cpu"]) == ("cpu", "")


def test_variavel_de_ambiente(monkeypatch) -> None:
    monkeypatch.setenv("PYRON_ACELERADOR", "TensorRT")
    assert provedores.pedido() == "tensorrt"
    monkeypatch.setenv("PYRON_ACELERADOR", "placa-magica")
    assert provedores.pedido() == "auto"
    monkeypatch.delenv("PYRON_TRT_FP16", raising=False)
    assert provedores.fp16() is False  # padrão FP32 até o usuário aprovar o FP16 (paridade)
    monkeypatch.setenv("PYRON_TRT_FP16", "1")
    assert provedores.fp16() is True


def test_opcoes_do_tensorrt_com_cache_e_perfil(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PYRON_DADOS", str(tmp_path))
    cartao = {"entrada": {"largura": 384, "altura": 320, "lote_max": 4}}
    lista = provedores.lista_provedores("tensorrt", cartao, "input", ["lote", 3, 320, 384], meia_precisao=True)
    nome, opcoes = lista[0]
    assert nome == "TensorrtExecutionProvider" and lista[1:] == ["CUDAExecutionProvider", "CPUExecutionProvider"]
    assert opcoes["trt_fp16_enable"] is True and opcoes["trt_engine_cache_enable"] is True
    assert opcoes["trt_engine_cache_path"] == str(tmp_path / "cache_trt") and (tmp_path / "cache_trt").is_dir()
    assert opcoes["trt_profile_min_shapes"] == "input:1x3x320x384"
    assert opcoes["trt_profile_opt_shapes"] == "input:1x3x320x384"
    assert opcoes["trt_profile_max_shapes"] == "input:4x3x320x384"
    fixa = provedores.lista_provedores("tensorrt", cartao, "input", [1, 3, 320, 384], meia_precisao=False)[0][1]
    assert "trt_profile_min_shapes" not in fixa and fixa["trt_fp16_enable"] is False  # entrada fixa: sem perfil


def test_listas_dos_outros_aceleradores() -> None:
    assert provedores.lista_provedores("cuda")[0][0] == "CUDAExecutionProvider"
    assert provedores.lista_provedores("directml") == [("DmlExecutionProvider", provedores.OPCOES_DIRECTML), "CPUExecutionProvider"]
    assert provedores.lista_provedores("cpu") == ["CPUExecutionProvider"]


def test_sessao_que_nao_assume_a_placa_falha(monkeypatch, tmp_path) -> None:
    import onnxruntime as ort

    class Falsa:
        def __init__(self, *_a, providers=None, **_k):
            self.pedidos = providers

        def get_providers(self):
            return ["CPUExecutionProvider"]

    monkeypatch.setattr(ort, "InferenceSession", Falsa)
    with pytest.raises(RuntimeError, match="DirectML não assumiu"):
        provedores.criar_sessao(tmp_path / "x.onnx", "directml")
    assert provedores.criar_sessao(tmp_path / "x.onnx", "cpu").pedidos == ["CPUExecutionProvider"]


def test_placa_segue_a_escolha(monkeypatch) -> None:
    from nucleo.detectores import placa
    from nucleo.detectores.onnx_modelo import DetectorONNX

    base = DetectorONNX.__new__(DetectorONNX)  # só o tipo importa para a escolha do carregador
    base.id, base.cartao, base.pasta = "pr", {}, None
    monkeypatch.setattr(provedores, "disponiveis", lambda ort=None: ["tensorrt", "cuda", "cpu"])
    assert placa._motor(base) is not None
    monkeypatch.setenv("PYRON_ACELERADOR", "cpu")
    assert placa._motor(base) is None
    assert placa.situacao(base) == {"onde": "cpu", "motivo": "PYRON_ACELERADOR=cpu"}
    monkeypatch.setenv("PYRON_ACELERADOR", "auto")
    monkeypatch.setattr(placa, "_carregando", {"pr"})
    assert placa.situacao(base) == {"onde": "carregando", "acelerador": "TensorRT"}


def test_detector_acelerado_diz_o_acelerador(monkeypatch) -> None:
    from nucleo.detectores import placa

    det = placa.DetectorAcelerado.__new__(placa.DetectorAcelerado)
    monkeypatch.setattr(placa.DetectorONNX, "__init__", lambda self, pasta: setattr(self, "pasta", pasta))
    base = SimpleNamespace(pasta=None, nome="Para-raios")
    placa.DetectorAcelerado.__init__(det, base, "tensorrt", meia_precisao=True)
    assert det.nome_placa == "TensorRT FP16"
    placa.DetectorAcelerado.__init__(det, base, "cuda")
    assert det.nome_placa == "CUDA"
    assert issubclass(placa.DetectorDirectML, placa.DetectorAcelerado)  # o nome de antes continua valendo


def test_sistema_mostra_o_acelerador(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "d"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "d")
    c = TestClient(servidor.app)
    s = c.get("/api/sistema").json()
    assert s["acelerador"]["escolhido"] in provedores.ORDEM and "disponiveis" in s["acelerador"]
    assert "acelerador" in c.get("/api/modelos").json()


def test_placa_nao_volta_para_a_cpu_em_silencio(monkeypatch, tmp_path) -> None:
    """Erro na placa durante a conta: o ONNX Runtime voltaria sozinho para a CPU; aqui isso é proibido e conferido."""
    import onnxruntime as ort

    class Placa:
        def __init__(self, *_a, providers=None, **_k):
            self.provedores = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            self.sem_volta = False

        def get_providers(self):
            return self.provedores

        def disable_fallback(self):
            self.sem_volta = True

    monkeypatch.setattr(ort, "InferenceSession", Placa)
    monkeypatch.setattr(provedores, "preparar_bibliotecas", lambda: None)
    s = provedores.criar_sessao(tmp_path / "x.onnx", "cuda")
    assert s.sem_volta is True
    provedores.conferir(s, "cuda")
    s.provedores = ["CPUExecutionProvider"]  # a placa largou o modelo na primeira conta
    with pytest.raises(RuntimeError, match="largou o modelo"):
        provedores.conferir(s, "cuda")


def test_cache_do_tensorrt_nunca_em_caminho_longo_demais(tmp_path, monkeypatch) -> None:
    """No Windows, o motor não é gravado (sem erro) se o caminho passar de 260 caracteres."""
    import sys

    longa = tmp_path / ("p" * 120) / ("q" * 60)
    monkeypatch.setenv("PYRON_DADOS", str(longa))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.delenv("PYRON_CACHE_TRT", raising=False)
    pasta = provedores.pasta_cache_trt()
    if sys.platform == "win32":
        assert pasta == tmp_path / "local" / "Pyron" / "cache_trt"
    assert len(str(pasta)) + provedores.FOLGA_NOME_MOTOR <= provedores.LIMITE_CAMINHO_WINDOWS or sys.platform != "win32"
    monkeypatch.setenv("PYRON_CACHE_TRT", str(tmp_path / "meu_cache"))
    assert provedores.pasta_cache_trt() == tmp_path / "meu_cache"


def test_tensorrt_monta_o_motor_em_outro_processo(monkeypatch, tmp_path) -> None:
    """A montagem (minutos) não pode segurar o interpretador do servidor: vai para outro processo."""
    import subprocess

    from nucleo.detectores import placa

    chamadas = []

    def falso_run(cmd, **kw):
        chamadas.append(cmd)
        return SimpleNamespace(returncode=1, stderr="sem placa", stdout="")

    monkeypatch.setattr(subprocess, "run", falso_run)
    monkeypatch.setenv("PYRON_CACHE_TRT", str(tmp_path / "cache"))
    with pytest.raises(RuntimeError, match="não montou o motor: sem placa"):
        provedores.montar_em_outro_processo(tmp_path / "m.onnx", {"entrada": {}}, True)
    assert chamadas[0][1:4] == ["-m", "nucleo.detectores.provedores", "montar"] and chamadas[0][-1] == "1"

    det = placa.DetectorAcelerado.__new__(placa.DetectorAcelerado)
    det.acelerador, det.arquivo, det.cartao, det.meia_precisao = "tensorrt", tmp_path / "m.onnx", {}, False
    with pytest.raises(RuntimeError, match="não montou"):
        det.carregar()  # falhou no outro processo: nem tenta montar aqui
