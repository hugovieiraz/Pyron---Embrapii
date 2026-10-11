"""O mesmo modelo rodando na placa de vídeo, para o ao vivo (celular e vídeo).

Na CPU, o RF-DETR em ONNX leva ~270 ms por quadro mesmo na versão INT8: o celular fica em 2 a 3
análises por segundo, e dividir o processador entre duas análises não rende mais (ele já está cheio:
~4 análises/s no máximo, com qualquer divisão de núcleos). Dois motores para a placa, nesta ordem:

1. **DirectML** (pacote ``onnxruntime-directml``, da Microsoft): o mesmo arquivo ``modelo.onnx``, na
   placa de alto desempenho (a RTX 3050 deste notebook, não a Intel integrada). ~54 ms por quadro,
   com as mesmas notas da CPU (diferença de 0,0002). Vale para qualquer modelo ONNX instalado. As
   DLLs são assinadas pela Microsoft: o Controle Inteligente de Aplicativos do Windows deixa rodar.
2. **PyTorch com CUDA**, quando o modelo traz os pesos do PyTorch (``cartao.pytorch``). ~38 ms, mas
   as DLLs do PyTorch não têm assinatura e o Windows às vezes as barra (WinError 4551; aconteceu em
   11/10/2026 à noite, depois de passar de manhã). Fica de reserva para quando não há DirectML.

O motor leva alguns segundos para carregar: carrega num fio à parte e, até ficar pronto (ou se
falhar), o ao vivo segue na CPU. A captura que vira inspeção continua no ONNX da CPU.
"""

from __future__ import annotations

import threading

import numpy as np

from nucleo.detectores.onnx_modelo import DetectorONNX

_trava = threading.Lock()
_prontos: dict[str, DetectorONNX] = {}
_carregando: set[str] = set()
_falhas: dict[str, str] = {}

# Placa de alto desempenho, não a integrada: pela ordem dos adaptadores, a Intel vem antes e leva
# ~440 ms por quadro (pior que a CPU).
OPCOES_DIRECTML = {"performance_preference": "high_performance", "device_filter": "gpu"}


def tem_directml() -> bool:
    try:
        import onnxruntime as ort
    except (ImportError, OSError):
        return False
    return "DmlExecutionProvider" in ort.get_available_providers()


def tem_pesos(det) -> bool:
    """O modelo traz os pesos do PyTorch junto do ONNX."""
    especificacao = getattr(det, "cartao", {}).get("pytorch")
    return isinstance(det, DetectorONNX) and bool(especificacao) and (det.pasta / especificacao["pesos"]).exists()


def _motor(base) -> type | None:
    if not isinstance(base, DetectorONNX):
        return None
    if tem_directml():
        return DetectorDirectML
    if tem_pesos(base):
        return DetectorPlaca
    return None


def variante(base) -> DetectorONNX | None:
    """O modelo na placa, se já carregado. Senão começa a carregar (em outro fio) e devolve None."""
    motor = _motor(base)
    if motor is None:
        return None
    with _trava:
        pronto = _prontos.get(base.id)
        if pronto is not None or base.id in _falhas or base.id in _carregando:
            return pronto
        _carregando.add(base.id)
    threading.Thread(target=_carregar, args=(base, motor), name="pyron-placa", daemon=True).start()
    return None


def situacao(base) -> dict:
    """Onde o ao vivo roda este modelo: ``placa`` (com o motor), ``carregando``, ``cpu`` e o motivo."""
    if _motor(base) is None:
        return {"onde": "cpu", "motivo": "sem motor para a placa de vídeo (nem DirectML nem pesos do PyTorch)"}
    with _trava:
        if base.id in _prontos:
            return {"onde": "placa", "placa": _prontos[base.id].nome_placa}
        if base.id in _carregando:
            return {"onde": "carregando"}
        return {"onde": "cpu", "motivo": _falhas.get(base.id, "")}


def _carregar(base, motor) -> None:
    try:
        det = motor(base)
        det.carregar()
        with _trava:
            _prontos[base.id] = det
    except Exception as erro:  # noqa: BLE001 — DLL barrada, sem placa, pesos de outra versão
        with _trava:
            _falhas[base.id] = f"{type(erro).__name__}: {erro}"[:300]
    finally:
        with _trava:
            _carregando.discard(base.id)


class DetectorDirectML(DetectorONNX):
    """O mesmo detector e o mesmo arquivo ONNX; a sessão roda na placa pelo DirectML."""

    def __init__(self, base: DetectorONNX):
        super().__init__(base.pasta)
        self.nome = f"{base.nome} · placa de vídeo"
        self.nome_placa = "DirectML"
        self._trava_placa = threading.Lock()  # uma conta por vez na placa

    def carregar(self) -> None:
        import onnxruntime as ort

        opcoes = ort.SessionOptions()
        opcoes.enable_mem_pattern = False  # exigências do DirectML
        opcoes.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        sessao = ort.InferenceSession(str(self.arquivo), opcoes,
                                      providers=[("DmlExecutionProvider", OPCOES_DIRECTML), "CPUExecutionProvider"])
        if sessao.get_providers()[0] != "DmlExecutionProvider":
            raise RuntimeError("o DirectML não assumiu o modelo")
        self._sessao = sessao
        e = self.entrada
        self._rodar(np.zeros((1, 3, int(e["altura"]), int(e["largura"])), np.float32))  # primeira conta é lenta

    def _rodar(self, x: np.ndarray) -> dict:
        with self._trava_placa:
            return super()._rodar(x)


class DetectorPlaca(DetectorONNX):
    """O mesmo detector (cartão, entrada, leitura da saída); só a conta roda no PyTorch, na placa."""

    def __init__(self, base: DetectorONNX):
        super().__init__(base.pasta)
        self.nome = f"{base.nome} · placa de vídeo"
        self.nome_placa = ""
        self._modulo = None
        self._trava_placa = threading.Lock()  # uma conta por vez na placa

    def carregar(self) -> None:
        import rfdetr
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("o PyTorch não achou placa de vídeo com CUDA")
        especificacao = self.cartao["pytorch"]
        classe = getattr(rfdetr, especificacao["arquitetura"])
        modelo = classe(resolution=int(especificacao["resolucao"]), pretrain_weights=str(self.pasta / especificacao["pesos"]),
                        trust_checkpoint=True)
        modulo = modelo.model.model
        modulo.eval()
        modulo.export()  # mesma saída do ONNX: caixas e notas
        self._modulo = modulo.to("cuda")
        self.nome_placa = torch.cuda.get_device_name(0)
        e = self.entrada
        self._rodar(np.zeros((1, 3, int(e["altura"]), int(e["largura"])), np.float32))  # primeira conta é lenta

    def preparar_imagem(self, imagem: np.ndarray):
        """Como a do ONNX (redimensiona bilinear com antisserrilhado, de 0 a 1, padroniza), mas na placa.

        Com o PyTorch, as peças ficam as mesmas do ONNX em 223 de 225 (31 fotos do acervo); as outras
        duas no limite da confiança.
        """
        import torch

        e = self.entrada
        with torch.inference_mode():
            t = torch.from_numpy(np.ascontiguousarray(imagem[..., :3], dtype=np.uint8)).to("cuda")
            t = t.permute(2, 0, 1)[None].float() / 255
            t = torch.nn.functional.interpolate(t, size=(int(e["altura"]), int(e["largura"])), mode="bilinear",
                                                antialias=True, align_corners=False)
            media = torch.tensor(e.get("media", (0.485, 0.456, 0.406)), device="cuda").view(1, 3, 1, 1)
            desvio = torch.tensor(e.get("desvio", (0.229, 0.224, 0.225)), device="cuda").view(1, 3, 1, 1)
            return (t - media) / desvio

    def _rodar(self, x) -> dict:
        import torch

        with self._trava_placa, torch.inference_mode():
            entrada = torch.from_numpy(x).to("cuda") if isinstance(x, np.ndarray) else x
            caixas, notas = (s.float().cpu().numpy() for s in self._modulo(entrada)[:2])
        nomes = self.saida.get("nomes", {})
        return {nomes.get("caixas", "dets"): caixas, nomes.get("notas", "labels"): notas}
