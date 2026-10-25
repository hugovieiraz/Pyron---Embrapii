"""Wrapper do SAM 2 (Segment Anything 2) com prompt de Bounding Box.

Implementa a classe SAM2Segmentor conforme especificação técnica do Pyron.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

import cv2
import numpy as np

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parents[2]
PASTA_PESOS = RAIZ / "modelos" / "sam2"
CHECKPOINT_PADRAO = PASTA_PESOS / "sam2.1_hiera_small.pt"
CONFIG_PADRAO = "configs/sam2.1/sam2.1_hiera_s.yaml"


class PredictorProtocol(Protocol):
    """Protocolo de interface compatível com SAM2ImagePredictor."""

    def set_image(self, image: np.ndarray) -> None: ...

    def predict(
        self,
        *,
        box: np.ndarray,
        multimask_output: bool,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...


@dataclass(frozen=True)
class SegmentationResult:
    """Resultado da segmentação de um ativo."""

    mask: np.ndarray  # uint8 (H x W) binário (0 ou 1)
    iou_score: float
    bbox: tuple[float, float, float, float]
    base_point: tuple[float, float]
    top_point: tuple[float, float]
    contour: list[list[float]]


class SAM2Segmentor:
    """Segmentador SAM 2 com Prompt BBox conforme especificação do Pyron.

    - Carrega o modelo Hiera do SAM 2 (build_sam2) com checkpoint especificado em modo eval / torch.no_grad().
    - Instancia o SAM2ImagePredictor.
    - Método segment_object(image_rgb: np.ndarray, bbox_xyxy: list | np.ndarray) -> np.ndarray.
    """

    def __init__(
        self,
        checkpoint: str | Path | None = None,
        config: str = CONFIG_PADRAO,
        device: str | None = None,
        predictor: PredictorProtocol | None = None,
    ):
        self._predictor = predictor
        self._checkpoint = Path(checkpoint) if checkpoint else CHECKPOINT_PADRAO
        self._config = config
        self._device_str = device
        self._frame_shape: tuple[int, int] | None = None

        if self._predictor is None:
            self._init_predictor()

    def _init_predictor(self) -> None:
        """Carrega o modelo Hiera do SAM 2 em modo de avaliação com torch.no_grad()."""
        if not self._checkpoint.is_file():
            return

        try:
            import torch
            from sam2.build_sam import build_sam2
            from sam2.sam2_image_predictor import SAM2ImagePredictor

            dev = self._device_str or ("cuda" if torch.cuda.is_available() else "cpu")
            with torch.no_grad():
                modelo = build_sam2(self._config, str(self._checkpoint), device=dev, mode="eval")
            self._predictor = SAM2ImagePredictor(modelo)
        except Exception as e:
            log.warning(f"Não foi possível inicializar SAM2ImagePredictor de {self._checkpoint}: {e}")
            self._predictor = None

    @staticmethod
    def _to_rgb_uint8(image: np.ndarray) -> np.ndarray:
        arr = np.asarray(image)
        if arr.ndim == 2:
            arr = np.repeat(arr[..., None], 3, axis=2)
        elif arr.ndim == 3 and arr.shape[2] == 1:
            arr = np.repeat(arr, 3, axis=2)
        elif arr.ndim == 3 and arr.shape[2] == 4:
            arr = arr[..., :3]

        if arr.dtype != np.uint8:
            validos = np.isfinite(arr)
            if validos.any():
                v_min, v_max = float(arr[validos].min()), float(arr[validos].max())
                escala = (arr - v_min) / max(1e-6, v_max - v_min)
                arr = np.clip(escala * 255.0, 0, 255).astype(np.uint8)
            else:
                arr = np.zeros(arr.shape, dtype=np.uint8)

        return np.ascontiguousarray(arr)

    def set_image(self, image_rgb: np.ndarray) -> None:
        """Define a imagem no preditor (predictor.set_image)."""
        rgb = self._to_rgb_uint8(image_rgb)
        if self._predictor is None:
            raise RuntimeError("Preditor SAM 2 não disponível. Verifique o checkpoint ou injete um preditor mock.")
        self._predictor.set_image(rgb)
        self._frame_shape = rgb.shape[:2]

    def segment_object(
        self,
        image_rgb: np.ndarray,
        bbox_xyxy: list | np.ndarray,
    ) -> np.ndarray:
        """Executa inferência usando BBox fornecida e retorna a máscara binária booleana/uint8 (H x W) com maior score."""
        self.set_image(image_rgb)

        caixa = [float(v) for v in bbox_xyxy]
        if len(caixa) != 4 or caixa[2] <= caixa[0] or caixa[3] <= caixa[1]:
            raise ValueError(f"Caixa inválida: {bbox_xyxy}")

        box_arr = np.array(caixa, dtype=np.float32)
        mascaras, scores, _ = self._predictor.predict(box=box_arr, multimask_output=False)

        mascaras = np.asarray(mascaras)
        scores = np.asarray(scores).reshape(-1)
        melhor_idx = int(np.argmax(scores))

        mascara_bin = (mascaras[melhor_idx] > 0).astype(np.uint8)
        return mascara_bin

    def segment_bbox(
        self,
        bbox_xyxy: Sequence[float],
        multimask: bool = False,
    ) -> SegmentationResult:
        """Versão estruturada com metadados detalhados de keypoints e contorno."""
        if self._predictor is None:
            raise RuntimeError("Preditor SAM 2 não inicializado.")

        caixa = [float(v) for v in bbox_xyxy]
        box_arr = np.array(caixa, dtype=np.float32)
        mascaras, scores, _ = self._predictor.predict(box=box_arr, multimask_output=multimask)

        mascaras = np.asarray(mascaras)
        scores = np.asarray(scores).reshape(-1)
        melhor_idx = int(np.argmax(scores))

        mascara_bin = (mascaras[melhor_idx] > 0).astype(np.uint8)
        score_val = float(scores[melhor_idx])

        # Extrai pontos-chave (base e topo)
        linhas, colunas = np.nonzero(mascara_bin)
        if len(linhas):
            y_b = int(linhas.max())
            x_b = float(colunas[linhas == y_b].mean())
            base_pt = (x_b, float(y_b))

            y_t = int(linhas.min())
            x_t = float(colunas[linhas == y_t].mean())
            top_pt = (x_t, float(y_t))
        else:
            base_pt = (float((caixa[0] + caixa[2]) / 2), float(caixa[3]))
            top_pt = (float((caixa[0] + caixa[2]) / 2), float(caixa[1]))

        # Contorno externo simplificado
        contornos, _ = cv2.findContours(mascara_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contornos:
            maior = max(contornos, key=cv2.contourArea)
            aprox = cv2.approxPolyDP(maior, epsilon=1.5, closed=True)
            contorno = [[float(pt[0][0]), float(pt[0][1])] for pt in aprox]
        else:
            contorno = []

        return SegmentationResult(
            mask=mascara_bin,
            iou_score=round(score_val, 4),
            bbox=(caixa[0], caixa[1], caixa[2], caixa[3]),
            base_point=base_pt,
            top_point=top_pt,
            contour=contorno,
        )


# Alias
SAM2MonocularSegmentor = SAM2Segmentor
