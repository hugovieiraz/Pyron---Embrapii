"""Medidas geométricas de um ativo a partir da máscara binária (metrologia por imagem).

Do maior contorno fechado da máscara saem:

- **área** (``cv2.contourArea``) e a contagem de pixels da peça;
- **comprimento** (eixo maior) e **largura** (eixo menor) do retângulo de área mínima
  (``cv2.minAreaRect``), que acompanha a peça inclinada, e a **largura média** (área / comprimento),
  mais fiel em peças afuniladas como isoladores;
- **orientação** do eixo maior, em graus, de 0 a 180 a partir do eixo x da imagem. Como o y da
  imagem cresce para baixo, ângulo positivo é sentido horário na tela.

Com ``metric_ratio`` (unidade real por pixel, ex.: mm/px vindo de uma referência de tamanho
conhecido na cena), as medidas saem também na unidade real. A escala só vale para o plano do
objeto: peça inclinada em profundidade aparece encurtada (perspectiva), e isso não é corrigido aqui.

Nota sobre ``area_px``: o contorno passa pelos centros dos pixels da borda, então a área do contorno
fica abaixo da contagem de pixels em cerca de meio perímetro (um retângulo cheio de w x h pixels dá
(w-1)·(h-1)). ``pixel_count`` traz a contagem direta para quem precisar dela.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np

GRAUS_MEIA_VOLTA = 180.0


class MascaraVaziaError(ValueError):
    """A máscara não tem nenhum contorno (nenhum pixel do ativo)."""


@dataclass(frozen=True)
class MedidasGeometricas:
    area_px: float
    pixel_count: int
    length_px: float
    width_px: float
    mean_width_px: float
    rotation_deg: float
    centroid_px: tuple[float, float]
    bbox_corners: list[list[float]]  # 4 cantos (x, y) do retângulo de área mínima
    unit: str | None = None
    metric_ratio: float | None = None
    area_metric: float | None = None  # unidade²
    length_metric: float | None = None
    width_metric: float | None = None
    mean_width_metric: float | None = None


class DimensionEstimator:
    """Extrai área, comprimento, largura e orientação de uma máscara binária."""

    def __init__(self, unit: str = "mm"):
        self.unit = unit

    @staticmethod
    def maior_contorno(mask: np.ndarray) -> np.ndarray:
        import cv2

        mascara = np.asarray(mask)
        if mascara.ndim != 2:
            raise ValueError(f"máscara deve ser H x W; veio {mascara.shape}")
        binaria = (mascara > 0).astype(np.uint8)
        contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contornos:
            raise MascaraVaziaError("máscara vazia: nenhum contorno para medir")
        return max(contornos, key=cv2.contourArea)

    @staticmethod
    def _eixos(retangulo) -> tuple[float, float, float]:
        """Comprimento, largura e ângulo do eixo maior em [0, 180) a partir do minAreaRect."""
        (_, _), (lado_a, lado_b), angulo = retangulo
        # O OpenCV dá o ângulo do lado "a"; se o lado maior é o "b", ele está 90° adiante.
        if lado_a >= lado_b:
            return float(lado_a), float(lado_b), float(angulo) % GRAUS_MEIA_VOLTA
        return float(lado_b), float(lado_a), (float(angulo) + 90.0) % GRAUS_MEIA_VOLTA

    def analyze_contour(self, mask: np.ndarray, metric_ratio: float | None = None) -> dict:
        """Medidas do maior contorno da máscara; com ``metric_ratio`` (unidade/px), também na unidade real."""
        import cv2

        if metric_ratio is not None and not (np.isfinite(metric_ratio) and metric_ratio > 0):
            raise ValueError(f"metric_ratio deve ser positivo; veio {metric_ratio!r}")
        contorno = self.maior_contorno(mask)
        area_px = float(cv2.contourArea(contorno))
        # Pixels da própria peça (o contorno preenchido), sem contar outras ilhas da máscara.
        so_peca = np.zeros(np.asarray(mask).shape, dtype=np.uint8)
        cv2.drawContours(so_peca, [contorno], -1, 1, thickness=cv2.FILLED)
        pixel_count = int(np.count_nonzero(so_peca & (np.asarray(mask) > 0)))

        retangulo = cv2.minAreaRect(contorno)
        comprimento, largura, rotacao = self._eixos(retangulo)
        largura_media = area_px / comprimento if comprimento > 0 else 0.0
        momentos = cv2.moments(contorno)
        if momentos["m00"] > 0:
            centroide = (momentos["m10"] / momentos["m00"], momentos["m01"] / momentos["m00"])
        else:  # contorno degenerado (linha ou ponto): usa o centro do retângulo
            centroide = tuple(float(v) for v in retangulo[0])

        medidas = MedidasGeometricas(
            area_px=area_px,
            pixel_count=pixel_count,
            length_px=comprimento,
            width_px=largura,
            mean_width_px=largura_media,
            rotation_deg=rotacao,
            centroid_px=(float(centroide[0]), float(centroide[1])),
            bbox_corners=cv2.boxPoints(retangulo).astype(float).tolist(),
        )
        if metric_ratio is not None:
            medidas = replace(
                medidas,
                unit=self.unit,
                metric_ratio=float(metric_ratio),
                area_metric=area_px * metric_ratio**2,
                length_metric=comprimento * metric_ratio,
                width_metric=largura * metric_ratio,
                mean_width_metric=largura_media * metric_ratio,
            )
        return asdict(medidas)
