"""O mesmo modelo rodando na placa de vídeo (PyTorch com CUDA), para o ao vivo (celular e vídeo).

Na CPU, o RF-DETR em ONNX leva ~270 ms por quadro mesmo na versão INT8: o celular fica em 2 a 3
análises por segundo, e dividir o processador entre duas análises não rende mais (ele já está cheio:
~4 análises/s no máximo, com qualquer divisão de núcleos). O mesmo modelo na RTX 3050 deste notebook
leva ~38 ms e o quadro inteiro do celular ~60 ms (~16 por segundo). Com a entrada preparada como a do
ONNX, as peças são as mesmas (225 de 225 em 31 fotos do acervo, confiança a menos de 0,01); com o
redimensionamento também na placa (20 ms a menos por quadro), 223 de 225, as outras duas no limite
da confiança (diferença de até 0,04). Em meia precisão seriam 10 ms a menos, mas some peça no
limite; fica a precisão normal. A captura que vira inspeção continua no ONNX.

Entra só quando o modelo traz os pesos do PyTorch (``cartao.pytorch``: arquitetura do RF-DETR,
resolução e o arquivo de pesos na pasta do modelo) e a placa responde. O PyTorch leva alguns segundos
para carregar e pode ser barrado pelo Controle Inteligente de Aplicativos do Windows: carrega num fio
à parte e, até ficar pronto (ou se falhar), o ao vivo segue na CPU.
"""

from __future__ import annotations

import threading

import numpy as np

from nucleo.detectores.onnx_modelo import DetectorONNX

_trava = threading.Lock()
_prontos: dict[str, "DetectorPlaca"] = {}
_carregando: set[str] = set()
_falhas: dict[str, str] = {}


def tem_pesos(det) -> bool:
    """O modelo traz os pesos do PyTorch junto do ONNX."""
    especificacao = getattr(det, "cartao", {}).get("pytorch")
    return isinstance(det, DetectorONNX) and bool(especificacao) and (det.pasta / especificacao["pesos"]).exists()


def variante(base) -> "DetectorPlaca | None":
    """O modelo na placa, se já carregado. Senão começa a carregar (em outro fio) e devolve None."""
    if not tem_pesos(base):
        return None
    with _trava:
        pronto = _prontos.get(base.id)
        if pronto is not None or base.id in _falhas or base.id in _carregando:
            return pronto
        _carregando.add(base.id)
    threading.Thread(target=_carregar, args=(base,), name="pyron-placa", daemon=True).start()
    return None


def situacao(base) -> dict:
    """Onde o ao vivo roda este modelo: ``placa`` (com o nome dela), ``carregando``, ``cpu`` e o motivo."""
    if not tem_pesos(base):
        return {"onde": "cpu", "motivo": "o modelo não traz os pesos para a placa de vídeo"}
    with _trava:
        if base.id in _prontos:
            return {"onde": "placa", "placa": _prontos[base.id].nome_placa}
        if base.id in _carregando:
            return {"onde": "carregando"}
        return {"onde": "cpu", "motivo": _falhas.get(base.id, "")}


def _carregar(base) -> None:
    try:
        det = DetectorPlaca(base)
        det.carregar()
        with _trava:
            _prontos[base.id] = det
    except Exception as erro:  # noqa: BLE001 — DLL barrada, PyTorch sem CUDA, sem placa, pesos de outra versão
        with _trava:
            _falhas[base.id] = f"{type(erro).__name__}: {erro}"[:300]
    finally:
        with _trava:
            _carregando.discard(base.id)


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

        No processador, o redimensionamento do PIL levava 20 ms dos ~80 de um quadro do celular.
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
