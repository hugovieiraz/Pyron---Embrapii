"""Detecção de retas, pontos de fuga (vx, vy, vz) e linha do horizonte em imagens monoculares.

Implementa a classe VanishingGeometryEstimator conforme a especificação técnica do Pyron.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np

EPS = 1e-9


@dataclass(frozen=True)
class LineSegment:
    """Segmento de reta 2D com coordenadas (x1, y1) -> (x2, y2)."""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def angle_rad(self) -> float:
        """Ângulo da reta em radianos no intervalo [-pi/2, pi/2)."""
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        angulo = math.atan2(dy, dx)
        if angulo < -math.pi / 2:
            angulo += math.pi
        elif angulo >= math.pi / 2:
            angulo -= math.pi
        return angulo

    @property
    def midpoint(self) -> tuple[float, float]:
        return (self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0

    def as_homogeneous_line(self) -> np.ndarray:
        """Calcula a representação homogênea l = p1 x p2 com a^2 + b^2 = 1."""
        p1 = np.array([self.x1, self.y1, 1.0], dtype=np.float64)
        p2 = np.array([self.x2, self.y2, 1.0], dtype=np.float64)
        linha = np.cross(p1, p2)
        norma = math.hypot(linha[0], linha[1])
        if norma > EPS:
            return linha / norma
        return np.array([0.0, 0.0, 1.0], dtype=np.float64)


@dataclass(frozen=True)
class VanishingPoint:
    """Ponto de fuga em coordenadas homogêneas [x, y, w]^T e euclidianas."""

    point_homog: np.ndarray
    point_euclidean: tuple[float, float] | None
    is_at_infinity: bool
    inliers_count: int = 0


@dataclass(frozen=True)
class VanishingGeometry:
    """Geometria projetiva canônica de fuga da cena."""

    v_x: VanishingPoint
    v_y: VanishingPoint
    v_z: VanishingPoint
    horizon_line: np.ndarray  # [a, b, c] normalizado onde ax + by + c = 0

    def distance_to_horizon(self, point: Sequence[float] | np.ndarray) -> float:
        """Distância algébrica e orientada de um ponto (x, y) à linha do horizonte."""
        pt = np.asarray(point, dtype=np.float64).reshape(-1)
        x, y = pt[0], pt[1]
        a, b, c = self.horizon_line
        return float(a * x + b * y + c)


def intersect_lines(l1: np.ndarray, l2: np.ndarray) -> np.ndarray:
    """Interseção de duas retas homogêneas p = l1 x l2."""
    pt = np.cross(l1, l2)
    norma = np.linalg.norm(pt)
    return pt / norma if norma > EPS else np.array([0.0, 0.0, 1.0], dtype=np.float64)


def line_from_points(p1: Sequence[float] | np.ndarray, p2: Sequence[float] | np.ndarray) -> np.ndarray:
    """Reta homogênea passando por p1 e p2 com a^2 + b^2 = 1."""
    pt1 = np.array([p1[0], p1[1], 1.0 if len(p1) == 2 else p1[2]], dtype=np.float64)
    pt2 = np.array([p2[0], p2[1], 1.0 if len(p2) == 2 else p2[2]], dtype=np.float64)
    linha = np.cross(pt1, pt2)
    norma = math.hypot(linha[0], linha[1])
    return linha / norma if norma > EPS else np.array([0.0, 0.0, 1.0], dtype=np.float64)


class VanishingGeometryEstimator:
    """Deteção de Pontos de Fuga e Linha do Horizonte conforme especificação detalhada do Pyron.

    Entrada: Imagem em escala de cinzas ou RGB.
    Detetor de Linhas: cv2.createLineSegmentDetector() (LSD) ou cv2.HoughLinesP().
    Agrupamento e Interseção (RANSAC):
      - Separação de retas com dominância vertical daquelas com dominância horizontal.
      - Ponto de fuga vertical (vz) via interseção projetiva.
      - Pontos de fuga horizontais (vx, vy) a partir de vigas e treliças.
      - Equação da linha do horizonte (l_horiz = vx x vy), ou normal ao eixo vertical se um ponto for estável.
    Saída: Dicionário com {"vanishing_point_z": (vx, vy), "horizon_line": (a, b, c), "horizon_y_center": y_val}.
    """

    def __init__(self, min_line_length: float = 25.0, ransac_threshold_rad: float = 0.04):
        self.min_line_length = min_line_length
        self.ransac_threshold_rad = ransac_threshold_rad

    def detect_lines(self, image: np.ndarray) -> list[LineSegment]:
        """Extrai segmentos de reta usando cv2.createLineSegmentDetector() (LSD) ou cv2.HoughLinesP()."""
        if image.ndim == 3:
            cinza = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY if image.shape[2] == 3 else cv2.COLOR_RGB2GRAY)
        else:
            cinza = image

        segmentos: list[LineSegment] = []
        try:
            lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
            lines, _, _, _ = lsd.detect(cinza)
            if lines is not None:
                for line in np.asarray(lines).reshape(-1, 4):
                    x1, y1, x2, y2 = line
                    seg = LineSegment(float(x1), float(y1), float(x2), float(y2))
                    if seg.length >= self.min_line_length:
                        segmentos.append(seg)
        except Exception:
            segmentos = []

        if not segmentos:
            arestas = cv2.Canny(cinza, 50, 150, apertureSize=3)
            lines = cv2.HoughLinesP(
                arestas,
                rho=1,
                theta=np.pi / 180,
                threshold=40,
                minLineLength=int(self.min_line_length),
                maxLineGap=5,
            )
            if lines is not None:
                for line in np.asarray(lines).reshape(-1, 4):
                    x1, y1, x2, y2 = line
                    seg = LineSegment(float(x1), float(y1), float(x2), float(y2))
                    if seg.length >= self.min_line_length:
                        segmentos.append(seg)

        return segmentos

    def filter_segments_by_orientation(
        self,
        lines: Sequence[LineSegment],
    ) -> tuple[list[LineSegment], list[LineSegment], list[LineSegment]]:
        """Separa linhas com dominância vertical daquelas com dominância horizontal (2 grupos de vigas/treliças)."""
        verticais: list[LineSegment] = []
        horiz_x: list[LineSegment] = []
        horiz_y: list[LineSegment] = []

        for line in lines:
            ang_deg = math.degrees(line.angle_rad)
            # Dominância vertical: inclinação próxima de 90° (|ang| >= 55°)
            if abs(ang_deg) >= 55.0:
                verticais.append(line)
            elif ang_deg >= 0.0:
                horiz_x.append(line)
            else:
                horiz_y.append(line)

        return verticais, horiz_x, horiz_y

    def estimate_vp_ransac(
        self,
        lines: Sequence[LineSegment],
        max_iters: int = 300,
        random_seed: int = 42,
    ) -> VanishingPoint:
        """Determina ponto de fuga ótimo via interseção projetiva RANSAC."""
        if len(lines) < 2:
            return VanishingPoint(
                point_homog=np.array([0.0, 1.0, 0.0], dtype=np.float64),
                point_euclidean=None,
                is_at_infinity=True,
                inliers_count=len(lines),
            )

        rng = np.random.default_rng(random_seed)
        linhas_homog = [line.as_homogeneous_line() for line in lines]
        n_lines = len(lines)
        melhor_vp: np.ndarray = np.array([0.0, 1.0, 0.0], dtype=np.float64)
        max_inliers = -1

        for _ in range(min(max_iters, n_lines * (n_lines - 1) // 2 + 1)):
            idx1, idx2 = rng.choice(n_lines, size=2, replace=False)
            l1, l2 = linhas_homog[idx1], linhas_homog[idx2]

            vp_cand = np.cross(l1, l2)
            norma = np.linalg.norm(vp_cand)
            if norma < EPS:
                continue
            vp_cand = vp_cand / norma

            inliers = 0
            for l in linhas_homog:
                dist_proj = abs(float(np.dot(l, vp_cand)))
                if dist_proj < math.sin(self.ransac_threshold_rad):
                    inliers += 1

            if inliers > max_inliers:
                max_inliers = inliers
                melhor_vp = vp_cand

        w = float(melhor_vp[2])
        is_inf = abs(w) < 1e-6
        eucl = (float(melhor_vp[0] / w), float(melhor_vp[1] / w)) if not is_inf else None

        return VanishingPoint(
            point_homog=melhor_vp,
            point_euclidean=eucl,
            is_at_infinity=is_inf,
            inliers_count=max_inliers,
        )

    def estimate(
        self,
        image_or_shape: np.ndarray | tuple[int, int],
        lines: Sequence[LineSegment] | None = None,
    ) -> dict:
        """Executa a estimativa completa de pontos de fuga e horizonte.

        Retorna dicionário no formato exigido pela especificação:
            {
                "vanishing_point_z": (vx, vy),
                "horizon_line": (a, b, c),
                "horizon_y_center": y_val
            }
        """
        geom = self.estimate_geometry(image_or_shape, lines=lines)
        a, b, c = [float(v) for v in geom.horizon_line]

        # Centro horizontal (x = w/2)
        if isinstance(image_or_shape, tuple):
            h, w = image_or_shape
        else:
            h, w = image_or_shape.shape[:2]

        x_center = w / 2.0
        # ax + by + c = 0 -> y = -(ax + c) / b
        if abs(b) > EPS:
            horizon_y = float(-(a * x_center + c) / b)
        else:
            horizon_y = float(h / 2.0)

        vz_eucl = geom.v_z.point_euclidean
        if vz_eucl is None:
            # Ponto de fuga vertical no infinito: direção (x_center, -1e6)
            vz_tuple = (float(x_center), -1e6)
        else:
            vz_tuple = (float(vz_eucl[0]), float(vz_eucl[1]))

        return {
            "vanishing_point_z": vz_tuple,
            "horizon_line": (a, b, c),
            "horizon_y_center": round(horizon_y, 2),
            "geometry_object": geom,
        }

    def estimate_geometry(
        self,
        image_or_shape: np.ndarray | tuple[int, int],
        lines: Sequence[LineSegment] | None = None,
    ) -> VanishingGeometry:
        """Estima e retorna o objeto VanishingGeometry canônico."""
        if isinstance(image_or_shape, tuple):
            h, w = image_or_shape
            img = None
        else:
            h, w = image_or_shape.shape[:2]
            img = image_or_shape

        if lines is None:
            if img is None:
                raise ValueError("Para detectar retas automaticamente, forneça a imagem.")
            lines = self.detect_lines(img)

        verticais, horiz_x, horiz_y = self.filter_segments_by_orientation(lines)

        # 1. Ponto de fuga vertical (vz)
        if verticais:
            v_z = self.estimate_vp_ransac(verticais)
        else:
            v_z = VanishingPoint(np.array([0.0, 1.0, 0.0]), None, True, 0)

        # 2. Pontos de fuga horizontais (vx, vy)
        v_x = self.estimate_vp_ransac(horiz_x) if horiz_x else VanishingPoint(np.array([1.0, 0.0, 0.0]), None, True, 0)
        v_y = self.estimate_vp_ransac(horiz_y) if horiz_y else VanishingPoint(np.array([-1.0, 0.0, 0.0]), None, True, 0)

        # 3. Equação da linha do horizonte l_horiz = vx x vy
        if v_x.point_euclidean is not None and v_y.point_euclidean is not None:
            p1 = np.array([v_x.point_euclidean[0], v_x.point_euclidean[1], 1.0])
            p2 = np.array([v_y.point_euclidean[0], v_y.point_euclidean[1], 1.0])
            horizonte = np.cross(p1, p2)
            norma = math.hypot(horizonte[0], horizonte[1])
            horizonte = horizonte / norma if norma > EPS else np.array([0.0, 1.0, -h / 2.0])
        elif v_x.point_euclidean is not None:
            y_h = v_x.point_euclidean[1]
            horizonte = np.array([0.0, 1.0, -y_h], dtype=np.float64)
        elif v_y.point_euclidean is not None:
            y_h = v_y.point_euclidean[1]
            horizonte = np.array([0.0, 1.0, -y_h], dtype=np.float64)
        else:
            horizonte = np.array([0.0, 1.0, -h / 2.0], dtype=np.float64)

        norma = math.hypot(horizonte[0], horizonte[1])
        if norma > EPS:
            horizonte = horizonte / norma
        if horizonte[1] < 0:
            horizonte = -horizonte

        return VanishingGeometry(v_x=v_x, v_y=v_y, v_z=v_z, horizon_line=horizonte)


# Alias para retrocompatibilidade
VanishingPointEstimator = VanishingGeometryEstimator
