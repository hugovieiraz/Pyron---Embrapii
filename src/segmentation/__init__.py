"""Módulo de segmentação de alta precisão com SAM 2."""

from src.segmentation.sam2_segmentor import (
    SAM2Segmentor,
    SAM2MonocularSegmentor,
    SegmentationResult,
    PredictorProtocol,
)

__all__ = [
    "SAM2Segmentor",
    "SAM2MonocularSegmentor",
    "SegmentationResult",
    "PredictorProtocol",
]
