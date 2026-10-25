"""Pipeline unificado de metrologia monocular para subestações elétricas no Pyron.

Combina segmentação SAM 2 com Single View Metrology de Criminisi et al.
para extrair altura, largura média, perfil de diâmetros e área projetada reais.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np

from src.geometry.criminisi_metrology import (
    CriminisiMetrology,
    ProjectiveMetrologyEngine,
    ReferenceObject,
    VerticalMeasurement,
)
from src.geometry.vanishing_points import (
    LineSegment,
    VanishingGeometry,
    VanishingGeometryEstimator,
)
from src.segmentation.sam2_segmentor import SAM2Segmentor, SegmentationResult

EPS = 1e-9


@dataclass(frozen=True)
class MonocularMetrologyResult:
    """Resultado completo da inspeção metrológica monocular de um ativo."""

    height: float  # Altura métrica real em metros
    mean_width: float  # Largura média métrica real em metros
    projected_area: float  # Área projetada métrica real em m²
    aspect_ratio: float  # Razão altura / largura
    unit: str  # Unidade física (padrão: 'm')
    sam2_iou: float  # Confiança do modelo SAM 2
    pixel_height: float
    pixel_width: float
    pixel_area: int
    metric_scale: float  # Fator de escala axial (metros/pixel)
    base_point: tuple[float, float]
    top_point: tuple[float, float]
    horizon_line: list[float]  # Coeficientes [a, b, c]
    horizon_y_center: float
    cross_ratio: float
    contour_points: list[list[float]]
    diameter_profile: dict[int, float]
    elapsed_ms: dict[str, float]
    thermal_stats: dict | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["height_formatted"] = f"{self.height:.2f} {self.unit}"
        d["mean_width_formatted"] = f"{self.mean_width:.2f} {self.unit}"
        d["projected_area_formatted"] = f"{self.projected_area:.2f} {self.unit}²"
        return d


class MonocularMetrologyPipeline:
    """Orquestrador do pipeline de metrologia monocular (Entrada -> SAM 2 -> Geometria -> Métricas)."""

    def __init__(
        self,
        segmentor: SAM2Segmentor | None = None,
        vp_estimator: VanishingGeometryEstimator | None = None,
        metrology_engine: ProjectiveMetrologyEngine | None = None,
        default_unit: str = "m",
    ):
        self.segmentor = segmentor or SAM2Segmentor()
        self.vp_estimator = vp_estimator or VanishingGeometryEstimator()
        self.metrology_engine = metrology_engine or ProjectiveMetrologyEngine(default_unit=default_unit)
        self.unit = default_unit

    def process(
        self,
        image_rgb: np.ndarray,
        bbox_xyxy: Sequence[float],
        camera_height: float | None = None,
        reference: ReferenceObject | None = None,
        ref_height_meters: float | None = None,
        ref_points_y: tuple[float, float] | None = None,
        custom_geometry: VanishingGeometry | None = None,
        detected_lines: Sequence[LineSegment] | None = None,
        thermal_matrix: np.ndarray | None = None,
    ) -> MonocularMetrologyResult:
        """Executa a medição monocular ponta a ponta do ativo dentro da caixa informada."""
        tempos: dict[str, float] = {}

        # 1. Geometria de Fuga e Linha do Horizonte
        t0 = time.perf_counter()
        if custom_geometry is not None:
            geom_dict = {
                "geometry_object": custom_geometry,
                "horizon_line": tuple(float(v) for v in custom_geometry.horizon_line),
                "horizon_y_center": float(-custom_geometry.horizon_line[2] / max(EPS, abs(custom_geometry.horizon_line[1]))),
                "vanishing_point_z": custom_geometry.v_z.point_euclidean or (image_rgb.shape[1] / 2.0, -1e6),
            }
        else:
            geom_dict = self.vp_estimator.estimate(image_rgb, lines=detected_lines)
        tempos["geometria_fuga"] = round((time.perf_counter() - t0) * 1000, 2)

        horizon_y = geom_dict["horizon_y_center"]
        horizon_line = geom_dict["horizon_line"]
        vz = geom_dict["vanishing_point_z"]
        geometria: VanishingGeometry = geom_dict["geometry_object"]

        # 2. Segmentação SAM 2
        t0 = time.perf_counter()
        self.segmentor.set_image(image_rgb)
        seg_res: SegmentationResult = self.segmentor.segment_bbox(bbox_xyxy)
        tempos["sam2_segmentacao"] = round((time.perf_counter() - t0) * 1000, 2)

        # 3. Metrologia Projetiva
        t0 = time.perf_counter()
        if ref_height_meters is not None:
            pts_y = ref_points_y or (float(seg_res.base_point[1]), float(seg_res.top_point[1]))
            dim_res = self.metrology_engine.compute_real_dimensions(
                mask=seg_res.mask,
                horizon_y=horizon_y,
                vz=vz,
                ref_height_meters=ref_height_meters,
                ref_points_y=pts_y,
            )
            height_m = dim_res["height_meters"]
            mean_width_m = dim_res["mean_width_meters"]
            area_m2 = dim_res["projected_area_m2"]
            scale_y = dim_res["scale_y_m_per_px"]
            aspect_ratio = dim_res["aspect_ratio"]
            cross_ratio = dim_res["delta_proj"] / max(EPS, dim_res["delta_ref"])
            diameter_profile = dim_res["diameter_profile"]
            pixel_h = float(abs(dim_res["y_base"] - dim_res["y_top"]))
            pixel_w = mean_width_m / max(EPS, scale_y)
        else:
            calculador = CriminisiMetrology(geometry=geometria, default_unit=self.unit)
            medicao: VerticalMeasurement = calculador.measure_segmented_object(
                mask=seg_res.mask,
                camera_height=camera_height,
                reference=reference,
                base_override=seg_res.base_point,
                top_override=seg_res.top_point,
            )
            height_m = medicao.height_metric
            mean_width_m = medicao.mean_width_metric
            area_m2 = medicao.projected_area_metric
            scale_y = medicao.metric_scale
            aspect_ratio = round(height_m / mean_width_m, 2) if mean_width_m > 0 else 0.0
            cross_ratio = medicao.cross_ratio
            diameter_profile = {}
            pixel_h = medicao.pixel_height
            pixel_w = medicao.mean_pixel_width

        tempos["metrologia_projetiva"] = round((time.perf_counter() - t0) * 1000, 2)

        # 4. Pureza Térmica (Opcional)
        thermal_stats: dict | None = None
        if thermal_matrix is not None:
            t0 = time.perf_counter()
            import cv2

            t_mat = np.asarray(thermal_matrix, dtype=np.float32)
            if t_mat.shape != seg_res.mask.shape:
                masc_term = cv2.resize(seg_res.mask, (t_mat.shape[1], t_mat.shape[0]), interpolation=cv2.INTER_NEAREST)
            else:
                masc_term = seg_res.mask

            dentro = (masc_term > 0) & np.isfinite(t_mat)
            if dentro.any():
                valores = t_mat[dentro]
                thermal_stats = {
                    "t_max": float(valores.max()),
                    "t_med": float(valores.mean()),
                    "t_min": float(valores.min()),
                    "t_desvio": float(valores.std()),
                    "pixels_validos": int(valores.size),
                }
            tempos["analise_termica"] = round((time.perf_counter() - t0) * 1000, 2)

        return MonocularMetrologyResult(
            height=height_m,
            mean_width=mean_width_m,
            projected_area=area_m2,
            aspect_ratio=aspect_ratio,
            unit=self.unit,
            sam2_iou=seg_res.iou_score,
            pixel_height=pixel_h,
            pixel_width=pixel_w,
            pixel_area=int(seg_res.mask.sum()),
            metric_scale=scale_y,
            base_point=seg_res.base_point,
            top_point=seg_res.top_point,
            horizon_line=list(horizon_line),
            horizon_y_center=round(horizon_y, 2),
            cross_ratio=round(cross_ratio, 6),
            contour_points=seg_res.contour,
            diameter_profile=diameter_profile,
            elapsed_ms=tempos,
            thermal_stats=thermal_stats,
        )
