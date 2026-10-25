"""Segmentação de ativos elétricos com o SAM 2 a partir de uma caixa (bounding box).

O SAM 2 (Segment Anything 2, Meta) é um modelo fundacional: não precisa de treino para as peças
do Pyron. Recebe a imagem e uma caixa ``[x1, y1, x2, y2]`` em pixels e devolve a máscara do objeto
dentro dela (corpo do isolador, bucha, ferragem). A caixa vem de fora: de um detector do
``nucleo/detectores`` ou desenhada pelo usuário.

Uso em duas etapas, para reaproveitar o trabalho pesado:

1. ``set_frame(imagem)`` roda o codificador Hiera uma vez por imagem (a parte cara);
2. ``predict_mask_from_bbox(caixa)`` roda só o decodificador, barato: várias caixas por imagem.

Os pesos ficam em ``modelos/sam2/`` (fora do git); ``ferramentas/baixar_sam2.py`` baixa e confere.
Dependências opcionais: ``pip install -e .[segmentacao]`` (ver ``pyproject.toml``).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

import numpy as np

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parents[2]
PASTA_PESOS = RAIZ / "modelos" / "sam2"

MB = 2**20
CANAIS_RGB = 3
VALORES_CAIXA = 4
BYTE_MAX = 255


@dataclass(frozen=True)
class VarianteSAM2:
    """Um checkpoint publicado pela Meta e o arquivo de configuração (Hydra) que o descreve."""

    nome: str
    arquivo: str
    config: str  # caminho dentro do pacote ``sam2`` (ex.: configs/sam2.1/sam2.1_hiera_s.yaml)
    url: str
    tamanho_min_mb: float  # piso de sanidade: arquivo menor que isso veio truncado


_URL_21 = "https://dl.fbaipublicfiles.com/segment_anything_2/092824/"
_URL_20 = "https://dl.fbaipublicfiles.com/segment_anything_2/072824/"

VARIANTES: dict[str, VarianteSAM2] = {
    v.nome: v
    for v in (
        VarianteSAM2("sam2.1_hiera_tiny", "sam2.1_hiera_tiny.pt", "configs/sam2.1/sam2.1_hiera_t.yaml",
                     _URL_21 + "sam2.1_hiera_tiny.pt", 140),
        VarianteSAM2("sam2.1_hiera_small", "sam2.1_hiera_small.pt", "configs/sam2.1/sam2.1_hiera_s.yaml",
                     _URL_21 + "sam2.1_hiera_small.pt", 160),
        VarianteSAM2("sam2.1_hiera_base_plus", "sam2.1_hiera_base_plus.pt", "configs/sam2.1/sam2.1_hiera_b+.yaml",
                     _URL_21 + "sam2.1_hiera_base_plus.pt", 300),
        VarianteSAM2("sam2_hiera_small", "sam2_hiera_small.pt", "configs/sam2/sam2_hiera_s.yaml",
                     _URL_20 + "sam2_hiera_small.pt", 160),
        VarianteSAM2("sam2_hiera_base_plus", "sam2_hiera_base_plus.pt", "configs/sam2/sam2_hiera_b+.yaml",
                     _URL_20 + "sam2_hiera_base_plus.pt", 300),
    )
}
# Small: bom equilíbrio para GPUs de 4 GB (ex.: GTX 1650) e ainda roda em CPU.
VARIANTE_PADRAO = "sam2.1_hiera_small"


class Preditor(Protocol):
    """O que o segmentador usa do ``SAM2ImagePredictor`` (permite trocar por um falso nos testes)."""

    def set_image(self, image: np.ndarray) -> None: ...

    def predict(self, *, box: np.ndarray, multimask_output: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...


@dataclass(frozen=True)
class Segmentacao:
    mascara: np.ndarray  # uint8 (H x W), 1 no ativo e 0 fora
    score: float  # IoU previsto pelo próprio SAM 2 para a máscara escolhida (0 a 1)
    caixa: tuple[float, float, float, float]  # caixa efetivamente usada, já recortada à imagem
    tempo_ms: float


def registrar(evento: str, **campos) -> None:
    """Log estruturado (uma linha JSON por evento), fácil de filtrar e de levar para o Grafana."""
    log.info(json.dumps({"evento": evento, **campos}, ensure_ascii=False, default=str))


def memoria_gpu(dispositivo) -> dict:
    """Memória da GPU em uso pelo PyTorch, em MB; vazio quando roda em CPU."""
    import torch

    if getattr(dispositivo, "type", str(dispositivo)) != "cuda" or not torch.cuda.is_available():
        return {}
    return {
        "gpu": torch.cuda.get_device_name(dispositivo),
        "gpu_alocada_mb": round(torch.cuda.memory_allocated(dispositivo) / MB, 1),
        "gpu_reservada_mb": round(torch.cuda.memory_reserved(dispositivo) / MB, 1),
        "gpu_pico_mb": round(torch.cuda.max_memory_allocated(dispositivo) / MB, 1),
    }


def escolher_dispositivo(preferido: str | None = None):
    import torch

    if preferido:
        return torch.device(preferido)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def para_rgb_uint8(imagem: np.ndarray) -> np.ndarray:
    """Deixa a imagem no formato que o SAM 2 espera: H x W x 3, uint8, RGB.

    Aceita a imagem óptica (RGB uint8), a térmica colorida ou a matriz térmica crua
    (H x W, float em °C): esta é normalizada pelo mínimo e máximo, ignorando NaN.
    """
    if imagem.ndim == 3 and imagem.shape[2] == 1:
        imagem = imagem[..., 0]
    if imagem.ndim == 2:
        imagem = np.repeat(imagem[..., None], CANAIS_RGB, axis=2)
    if imagem.ndim != 3 or imagem.shape[2] != CANAIS_RGB:
        raise ValueError(f"imagem deve ser H x W ou H x W x 3; veio {imagem.shape}")
    if imagem.dtype == np.uint8:
        return np.ascontiguousarray(imagem)
    valores = imagem.astype(np.float32)
    validos = np.isfinite(valores)
    if not validos.any():
        raise ValueError("imagem sem nenhum valor finito")
    menor, maior = float(valores[validos].min()), float(valores[validos].max())
    escala = (valores - menor) / (maior - menor) if maior > menor else np.zeros_like(valores)
    return np.nan_to_num(escala * BYTE_MAX, nan=0.0).round().astype(np.uint8)


def validar_caixa(bbox_xyxy: Sequence[float] | np.ndarray, largura: int, altura: int) -> tuple[float, ...]:
    """Confere ``[x1, y1, x2, y2]`` e recorta à imagem; erro se sobrar caixa vazia."""
    caixa = np.asarray(bbox_xyxy, dtype=np.float64).reshape(-1)
    if caixa.size != VALORES_CAIXA or not np.isfinite(caixa).all():
        raise ValueError(f"caixa deve ter 4 números finitos [x1, y1, x2, y2]; veio {bbox_xyxy!r}")
    x1, y1, x2, y2 = caixa
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"caixa invertida ou vazia (x2 <= x1 ou y2 <= y1): {caixa.tolist()}")
    x1, x2 = np.clip([x1, x2], 0, largura)
    y1, y2 = np.clip([y1, y2], 0, altura)
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"caixa fora da imagem {largura}x{altura}: {caixa.tolist()}")
    return float(x1), float(y1), float(x2), float(y2)


def caminho_checkpoint(variante: str = VARIANTE_PADRAO, pasta: Path = PASTA_PESOS) -> Path:
    return pasta / VARIANTES[variante].arquivo


class SAM2Segmentor:
    """Segmenta o ativo dentro de uma caixa com o ``SAM2ImagePredictor``.

    ``preditor`` permite injetar outro objeto com ``set_image``/``predict`` (testes, versões
    exportadas); sem ele, o modelo Hiera é montado com ``build_sam2`` a partir do checkpoint.
    """

    def __init__(
        self,
        checkpoint: str | Path | None = None,
        variante: str = VARIANTE_PADRAO,
        device: str | None = None,
        multimask: bool = False,
        preditor: Preditor | None = None,
    ):
        if variante not in VARIANTES:
            raise ValueError(f"variante desconhecida '{variante}'; opções: {sorted(VARIANTES)}")
        self.variante = VARIANTES[variante]
        # Com caixa, o pedido não é ambíguo: a Meta recomenda uma máscara só (multimask=False).
        self.multimask = multimask
        self._forma_quadro: tuple[int, int] | None = None
        if preditor is not None:
            self.dispositivo = None
            self.preditor = preditor
            return
        self.dispositivo = escolher_dispositivo(device)
        self.preditor = self._construir(Path(checkpoint) if checkpoint else caminho_checkpoint(variante))

    def _construir(self, checkpoint: Path) -> Preditor:
        if not checkpoint.is_file():
            raise FileNotFoundError(
                f"checkpoint do SAM 2 não encontrado em {checkpoint}. "
                f"Baixe com: python ferramentas/baixar_sam2.py --variante {self.variante.nome}"
            )
        try:
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor
        except ImportError as erro:
            raise ImportError("pacote 'sam2' ausente; instale com: pip install -e .[segmentacao]") from erro

        inicio = time.perf_counter()
        # build_sam2 carrega o state_dict de forma estrita: chave faltando ou sobrando vira erro.
        modelo = build_sam2(self.variante.config, str(checkpoint), device=str(self.dispositivo), mode="eval")
        registrar(
            "sam2.modelo_carregado",
            variante=self.variante.nome,
            checkpoint=str(checkpoint),
            dispositivo=str(self.dispositivo),
            tempo_ms=round((time.perf_counter() - inicio) * 1000, 1),
            **memoria_gpu(self.dispositivo),
        )
        return SAM2ImagePredictor(modelo)

    def _contexto(self):
        """Sem gradiente e, nas GPUs com bfloat16 (Ampere+), precisão mista como no exemplo oficial."""
        import contextlib

        import torch

        pilha = contextlib.ExitStack()
        pilha.enter_context(torch.no_grad())
        dispositivo = self.dispositivo
        if dispositivo is not None and dispositivo.type == "cuda" and torch.cuda.is_bf16_supported(including_emulation=False):
            pilha.enter_context(torch.autocast("cuda", dtype=torch.bfloat16))
        return pilha

    def _sincronizar(self) -> None:
        if self.dispositivo is not None and self.dispositivo.type == "cuda":
            import torch

            torch.cuda.synchronize(self.dispositivo)

    def set_frame(self, image_rgb: np.ndarray) -> None:
        """Calcula os embeddings da imagem (uma vez por quadro)."""
        imagem = para_rgb_uint8(np.asarray(image_rgb))
        inicio = time.perf_counter()
        with self._contexto():
            self.preditor.set_image(imagem)
        self._sincronizar()
        self._forma_quadro = imagem.shape[:2]
        registrar(
            "sam2.set_frame",
            altura=imagem.shape[0],
            largura=imagem.shape[1],
            tempo_ms=round((time.perf_counter() - inicio) * 1000, 1),
            **memoria_gpu(self.dispositivo),
        )

    def segmentar(self, bbox_xyxy: Sequence[float] | np.ndarray) -> Segmentacao:
        """Máscara, confiança e tempo para uma caixa ``[x1, y1, x2, y2]`` no quadro atual."""
        if self._forma_quadro is None:
            raise RuntimeError("chame set_frame(imagem) antes de pedir uma máscara")
        altura, largura = self._forma_quadro
        caixa = validar_caixa(bbox_xyxy, largura, altura)
        inicio = time.perf_counter()
        with self._contexto():
            mascaras, scores, _ = self.preditor.predict(box=np.asarray(caixa, dtype=np.float32), multimask_output=self.multimask)
        self._sincronizar()
        tempo_ms = (time.perf_counter() - inicio) * 1000
        mascaras = np.asarray(mascaras).reshape(-1, altura, largura)
        scores = np.asarray(scores, dtype=np.float32).reshape(-1)
        melhor = int(np.argmax(scores))
        mascara = (mascaras[melhor] > 0).astype(np.uint8)
        registrar(
            "sam2.predict",
            caixa=[round(v, 1) for v in caixa],
            score=round(float(scores[melhor]), 4),
            pixels_mascara=int(mascara.sum()),
            tempo_ms=round(tempo_ms, 1),
            **memoria_gpu(self.dispositivo),
        )
        return Segmentacao(mascara=mascara, score=float(scores[melhor]), caixa=caixa, tempo_ms=tempo_ms)

    def predict_mask_from_bbox(self, bbox_xyxy: list | tuple | np.ndarray) -> np.ndarray:
        """Máscara binária uint8 (H x W) do ativo dentro da caixa ``[x1, y1, x2, y2]``."""
        return self.segmentar(bbox_xyxy).mascara
