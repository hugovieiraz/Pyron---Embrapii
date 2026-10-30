"""Onde o modelo ONNX roda: a escolha do provedor do ONNX Runtime num lugar só (0.9, F4).

Usado por ``onnx_modelo.py`` (a sessão de referência, na CPU) e por ``placa.py`` (a mesma rede na placa de vídeo).

``PYRON_ACELERADOR`` = ``auto`` (padrão) | ``tensorrt`` | ``cuda`` | ``directml`` | ``cpu``

- ``auto``: TensorRT > CUDA > DirectML > CPU, só entre os que este ONNX Runtime oferece
  (``get_available_providers``). No computador de desenvolvimento (``onnxruntime-directml``) isso dá DirectML,
  como antes da 0.9; no servidor NVIDIA (``onnxruntime-gpu``, ambiente ``.venv-gpu``), TensorRT.
- Pedido explícito que não existe neste ONNX Runtime: desce para o próximo da ordem e a situação diz o motivo.
- ``cpu``: nada vai para a placa.

Por que a sessão de referência fica na CPU (diagnóstico da F0, ``docs/v09/0-diagnostico.md`` §6): ela é o padrão
de comparação (paridade) e roda sem exigências; cada provedor de placa tem as suas (DirectML sem padrão de memória
e em sequência; TensorRT com cache de motor e perfil de formas) e entra só pela ``placa.py``, que espera ficar
pronto em outro fio. Com a lista explícita, o ONNX Runtime também nunca escolhe sozinho a placa integrada.

TensorRT: FP16 por padrão (``PYRON_TRT_FP16=0`` desliga), cache do motor em ``<dados>/cache_trt`` (o primeiro motor
leva minutos para montar; os seguintes, segundos) e perfil de formas (min/opt/max) a partir do ``cartao.json``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ORDEM = ("tensorrt", "cuda", "directml", "cpu")
PROVEDOR = {"tensorrt": "TensorrtExecutionProvider", "cuda": "CUDAExecutionProvider",
            "directml": "DmlExecutionProvider", "cpu": "CPUExecutionProvider"}
NOMES = {"tensorrt": "TensorRT", "cuda": "CUDA", "directml": "DirectML", "cpu": "processador"}
# Placa de alto desempenho, não a integrada: pela ordem dos adaptadores, a Intel vem antes e leva
# ~440 ms por quadro (pior que a CPU).
OPCOES_DIRECTML = {"performance_preference": "high_performance", "device_filter": "gpu"}


def pedido() -> str:
    """O que ``PYRON_ACELERADOR`` pede (valor desconhecido vale ``auto``)."""
    valor = (os.environ.get("PYRON_ACELERADOR") or "auto").strip().lower()
    return valor if valor in ("auto", *ORDEM) else "auto"


def fp16() -> bool:
    return (os.environ.get("PYRON_TRT_FP16") or "1").strip() not in ("0", "false", "nao", "não")


def disponiveis(ort=None) -> list[str]:
    """Os aceleradores que este ONNX Runtime oferece, na ordem de preferência (a CPU sempre)."""
    try:
        if ort is None:
            import onnxruntime as ort
        oferecidos = set(ort.get_available_providers())
    except (ImportError, OSError):
        oferecidos = set()
    return [a for a in ORDEM if PROVEDOR[a] in oferecidos or a == "cpu"]


def escolher(pedido_: str | None = None, oferecidos: list[str] | None = None) -> tuple[str, str]:
    """(acelerador, motivo). O motivo explica quando o pedido não pôde ser atendido."""
    pedido_ = pedido_ or pedido()
    oferecidos = disponiveis() if oferecidos is None else oferecidos
    if pedido_ == "auto":
        return next(a for a in ORDEM if a in oferecidos), ""
    if pedido_ in oferecidos:
        return pedido_, ""
    resto = ORDEM[ORDEM.index(pedido_) + 1:]
    escolhido = next(a for a in resto if a in oferecidos)
    return escolhido, f"{NOMES[pedido_]} pedido em PYRON_ACELERADOR, mas este ONNX Runtime não o oferece; usando {NOMES[escolhido]}."


def pasta_dados() -> Path:
    return Path(os.environ.get("PYRON_DADOS") or Path(__file__).resolve().parents[2] / "app" / "dados_app")


def pasta_cache_trt() -> Path:
    pasta = pasta_dados() / "cache_trt"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def perfil_formas(cartao: dict, nome_entrada: str, forma: list) -> dict:
    """min/opt/max do TensorRT para entradas com dimensão variável; o tamanho vem do cartão do modelo.

    ``entrada.lote_max`` (padrão 1) limita o lote. Entrada toda fixa: sem perfil (o TensorRT não precisa).
    """
    if all(isinstance(d, int) and d > 0 for d in forma):
        return {}
    e = cartao.get("entrada") or {}
    altura, largura = int(e.get("altura") or 384), int(e.get("largura") or 384)
    lote_max = max(1, int(e.get("lote_max") or 1))
    canais = forma[1] if len(forma) > 1 and isinstance(forma[1], int) and forma[1] > 0 else 3
    fmt = lambda lote: f"{nome_entrada}:{lote}x{canais}x{altura}x{largura}"  # noqa: E731
    return {"trt_profile_min_shapes": fmt(1), "trt_profile_opt_shapes": fmt(1), "trt_profile_max_shapes": fmt(lote_max)}


def opcoes_tensorrt(cartao: dict | None = None, nome_entrada: str | None = None, forma: list | None = None,
                    meia_precisao: bool | None = None, cache: Path | None = None) -> dict:
    cache = cache or pasta_cache_trt()
    opcoes = {
        "trt_fp16_enable": fp16() if meia_precisao is None else meia_precisao,
        "trt_engine_cache_enable": True,
        "trt_engine_cache_path": str(cache),
        "trt_timing_cache_enable": True,
        "trt_timing_cache_path": str(cache),
    }
    if cartao and nome_entrada and forma:
        opcoes.update(perfil_formas(cartao, nome_entrada, forma))
    return opcoes


def preparar_bibliotecas() -> None:
    """Windows com as bibliotecas da NVIDIA instaladas pelo pip (ambiente .venv-gpu): CUDA, cuDNN e TensorRT
    entram no caminho de DLLs deste processo. Sem elas, não faz nada."""
    global _bibliotecas_prontas
    if sys.platform != "win32" or _bibliotecas_prontas:
        return
    _bibliotecas_prontas = True
    # As DLLs principais e as auxiliares que elas carregam depois (o cuDNN 9 carrega as "engines" sob demanda):
    # a pasta de cada pacote nvidia-*/bin e tensorrt_libs entra no caminho de DLLs e no PATH deste processo.
    pastas = []
    for raiz in map(Path, sys.path):
        pastas += sorted((raiz / "nvidia").glob("*/bin")) if (raiz / "nvidia").is_dir() else []
        if (raiz / "tensorrt_libs").is_dir():
            pastas.append(raiz / "tensorrt_libs")
    for pasta in pastas:
        os.add_dll_directory(str(pasta))
    if pastas:
        os.environ["PATH"] = os.pathsep.join([*map(str, pastas), os.environ.get("PATH", "")])
    try:
        import onnxruntime as ort

        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()  # CUDA e cuDNN dos pacotes nvidia-* (onnxruntime-gpu[cuda,cudnn])
    except Exception:  # noqa: BLE001 — sem as bibliotecas, o provedor só não fica disponível
        pass


_bibliotecas_prontas = False


def conferir(sessao, acelerador: str) -> None:
    """Depois de uma conta: o acelerador continua com o modelo (se a placa falhar, o ONNX Runtime pode passar
    para a CPU por conta própria; aqui isso vira erro, não um resultado da CPU com o nome da placa)."""
    if sessao.get_providers()[0] != PROVEDOR[acelerador]:
        raise RuntimeError(f"o {NOMES[acelerador]} largou o modelo na primeira conta (ficou com {sessao.get_providers()[0]})")


def lista_provedores(acelerador: str, cartao: dict | None = None, nome_entrada: str | None = None,
                     forma: list | None = None, meia_precisao: bool | None = None) -> list:
    """Provedores para a sessão, com as opções de cada um; a CPU sempre por último (o que a placa não fizer)."""
    if acelerador == "tensorrt":
        return [(PROVEDOR["tensorrt"], opcoes_tensorrt(cartao, nome_entrada, forma, meia_precisao)), PROVEDOR["cuda"], PROVEDOR["cpu"]]
    if acelerador == "cuda":
        return [(PROVEDOR["cuda"], {"cudnn_conv_algo_search": "HEURISTIC"}), PROVEDOR["cpu"]]
    if acelerador == "directml":
        return [(PROVEDOR["directml"], OPCOES_DIRECTML), PROVEDOR["cpu"]]
    return [PROVEDOR["cpu"]]


def opcoes_sessao(acelerador: str):
    import onnxruntime as ort

    opcoes = ort.SessionOptions()
    if acelerador == "cpu":
        # Metade dos núcleos e sem espera ativa: com o processador livre fica igual ou mais rápido e, dividindo
        # o processador com o navegador ou o vídeo, não desaba (commit ff48843, medido no notebook do Hugo).
        opcoes.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
        opcoes.add_session_config_entry("session.intra_op.allow_spinning", "0")
    elif acelerador == "directml":
        opcoes.enable_mem_pattern = False  # exigências do DirectML
        opcoes.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    return opcoes


def criar_sessao(arquivo: Path, acelerador: str = "cpu", cartao: dict | None = None, meia_precisao: bool | None = None):
    """Sessão do ONNX Runtime no acelerador pedido. Falha se ele não assumir o modelo (a CPU não substitui
    a placa em silêncio: quem chama decide o que fazer)."""
    import onnxruntime as ort

    if acelerador in ("tensorrt", "cuda"):
        preparar_bibliotecas()
    nome_entrada = forma = None
    if acelerador == "tensorrt":
        leitura = ort.InferenceSession(str(arquivo), providers=[PROVEDOR["cpu"]])  # só para o nome e a forma da entrada
        entrada = leitura.get_inputs()[0]
        nome_entrada, forma = entrada.name, list(entrada.shape)
        del leitura
    sessao = ort.InferenceSession(str(arquivo), opcoes_sessao(acelerador),
                                  providers=lista_provedores(acelerador, cartao, nome_entrada, forma, meia_precisao))
    if sessao.get_providers()[0] != PROVEDOR[acelerador]:
        raise RuntimeError(f"o {NOMES[acelerador]} não assumiu o modelo (ficou com {sessao.get_providers()[0]})")
    if acelerador != "cpu" and hasattr(sessao, "disable_fallback"):
        sessao.disable_fallback()  # erro na placa é erro, não uma volta silenciosa para a CPU
    return sessao


def situacao() -> dict:
    """Para /api/sistema: o que foi pedido, o que este ONNX Runtime oferece e o que vale."""
    escolhido, motivo = escolher()
    try:
        import onnxruntime as ort

        versao = ort.__version__
    except (ImportError, OSError):
        versao = None
    return {"pedido": pedido(), "disponiveis": disponiveis(), "escolhido": escolhido, "nome": NOMES[escolhido],
            "motivo": motivo, "fp16": fp16() if escolhido == "tensorrt" else None, "onnxruntime": versao}
