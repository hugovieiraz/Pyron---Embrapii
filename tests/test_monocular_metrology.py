"""Testes unitários sintéticos e validação numérica de metrologia monocular projetiva (Criminisi et al. + SAM 2)."""

from __future__ import annotations

import math
import numpy as np
import pytest

from src.geometry.vanishing_points import (
    LineSegment,
    VanishingGeometry,
    VanishingGeometryEstimator,
    VanishingPoint,
    intersect_lines,
)
from src.geometry.criminisi_metrology import (
    CriminisiMetrology,
    ProjectiveMetrologyEngine,
    ReferenceObject,
)
from src.segmentation.sam2_segmentor import (
    SAM2Segmentor,
    SegmentationResult,
)
from src.pipeline.metrology_pipeline import (
    MonocularMetrologyPipeline,
    MonocularMetrologyResult,
)


class MockPredictor:
    """Simula as respostas do SAM2ImagePredictor com máscara cilíndrica de isolador."""

    def __init__(self):
        self.image = None

    def set_image(self, image: np.ndarray) -> None:
        self.image = image

    def predict(self, *, box: np.ndarray, multimask_output: bool):
        x1, y1, x2, y2 = [int(round(v)) for v in box]
        h, w = self.image.shape[:2]
        mascara = np.zeros((h, w), dtype=np.float32)

        w_box = x2 - x1
        x_start = x1 + int(w_box * 0.15)
        x_end = x2 - int(w_box * 0.15)
        mascara[y1:y2, x_start:x_end] = 1.0

        scores = np.array([0.965], dtype=np.float32)
        return np.expand_dims(mascara, axis=0), scores, None


# ==============================================================================
# 1. VanishingGeometryEstimator: Retas, RANSAC e Dicionário de Saída
# ==============================================================================


def test_vanishing_geometry_estimator_output_format():
    """Valida o formato de saída exigido: {"vanishing_point_z": (vx, vy), "horizon_line": (a, b, c), "horizon_y_center": y_val}."""
    estimator = VanishingGeometryEstimator()

    # Imagem sintética 600x800 com linhas verticais e horizontais
    img = np.zeros((600, 800, 3), dtype=np.uint8)
    linhas = [
        LineSegment(400.0, 100.0, 400.0, 500.0),
        LineSegment(300.0, 120.0, 300.0, 480.0),
        LineSegment(100.0, 300.0, 700.0, 300.0),  # linha horizontal em y=300
        LineSegment(150.0, 350.0, 650.0, 350.0),
    ]

    res = estimator.estimate(img, lines=linhas)
    assert isinstance(res, dict)
    assert "vanishing_point_z" in res
    assert "horizon_line" in res
    assert "horizon_y_center" in res

    assert len(res["vanishing_point_z"]) == 2
    assert len(res["horizon_line"]) == 3
    assert isinstance(res["horizon_y_center"], float)


def test_line_segment_and_intersections():
    seg = LineSegment(0.0, 0.0, 10.0, 0.0)
    assert seg.length == pytest.approx(10.0)
    assert seg.angle_rad == pytest.approx(0.0)

    l1 = np.array([1.0, 0.0, -10.0])
    l2 = np.array([0.0, 1.0, -20.0])
    pt = intersect_lines(l1, l2)
    assert (pt[0] / pt[2]) == pytest.approx(10.0)
    assert (pt[1] / pt[2]) == pytest.approx(20.0)


# ==============================================================================
# 2. SAM2Segmentor com segment_object
# ==============================================================================


def test_sam2_segmentor_segment_object():
    """Valida a classe SAM2Segmentor e o método segment_object(image_rgb, bbox_xyxy) -> np.ndarray."""
    mock = MockPredictor()
    segmentor = SAM2Segmentor(predictor=mock)

    img = np.zeros((400, 400, 3), dtype=np.uint8)
    bbox = [100.0, 50.0, 200.0, 300.0]

    mask = segmentor.segment_object(img, bbox)
    assert isinstance(mask, np.ndarray)
    assert mask.shape == (400, 400)
    assert mask.dtype == np.uint8
    assert mask.sum() > 0
    # Verifica que a máscara está contida na caixa delimitadora
    assert mask[0:50, :].sum() == 0
    assert mask[301:, :].sum() == 0


# ==============================================================================
# 3. ProjectiveMetrologyEngine: Lógica Matemática Exata de Criminisi
# ==============================================================================


def test_projective_metrology_engine_mathematical_formulation():
    """Valida a formulação matemática exata especificada:

    Delta_proj = |yb - yt| / |yb - horizon_y|
    Delta_ref = |y_ref_base - y_ref_top| / |y_ref_base - horizon_y|
    H_objeto = H_ref * (Delta_proj / Delta_ref)
    """
    engine = ProjectiveMetrologyEngine(default_unit="m")

    # Criar uma máscara sintética de isolador:
    # y_b = 500, y_t = 300 -> |yb - yt| = 200 px
    # horizon_y = 200
    # |yb - horizon_y| = |500 - 200| = 300 px
    # Delta_proj = 200 / 300 = 0.666667
    mask = np.zeros((600, 800), dtype=np.uint8)
    mask[300:501, 380:420] = 1  # 40 px de largura

    horizon_y = 200.0
    vz = (400.0, -1e6)

    # Elemento de referência:
    # y_ref_base = 550, y_ref_top = 400 -> |y_ref_b - y_ref_t| = 150 px
    # |y_ref_base - horizon_y| = |550 - 200| = 350 px
    # Delta_ref = 150 / 350 = 0.428571
    # H_ref = 1.80 metros
    ref_h_m = 1.80
    ref_points_y = (550.0, 400.0)

    # Cálculo analítico esperado:
    delta_proj_esperado = (500.0 - 300.0) / (500.0 - 200.0)  # 200 / 300
    delta_ref_esperado = (550.0 - 400.0) / (550.0 - 200.0)   # 150 / 350
    h_objeto_esperado = ref_h_m * (delta_proj_esperado / delta_ref_esperado)  # 1.80 * (2/3) / (3/7) = 1.80 * 14 / 9 = 2.80 m!

    res = engine.compute_real_dimensions(
        mask=mask,
        horizon_y=horizon_y,
        vz=vz,
        ref_height_meters=ref_h_m,
        ref_points_y=ref_points_y,
    )

    assert isinstance(res, dict)
    assert res["height_meters"] == pytest.approx(h_objeto_esperado, abs=1e-3)
    assert res["height_meters"] == pytest.approx(2.80, abs=1e-3)
    assert res["delta_proj"] == pytest.approx(delta_proj_esperado, abs=1e-5)
    assert res["delta_ref"] == pytest.approx(delta_ref_esperado, abs=1e-5)
    assert res["y_base"] == 500
    assert res["y_top"] == 300
    assert res["scale_y_m_per_px"] == pytest.approx(2.80 / 200.0, abs=1e-5)

    # Perfil de diâmetros
    assert len(res["diameter_profile"]) == 201
    assert res["mean_width_meters"] > 0.0
    assert res["projected_area_m2"] > 0.0


# ==============================================================================
# 4. Pipeline Unificado de Metrologia Monocular
# ==============================================================================


def test_monocular_pipeline_with_reference():
    mock = MockPredictor()
    segmentor = SAM2Segmentor(predictor=mock)
    pipeline = MonocularMetrologyPipeline(segmentor=segmentor, default_unit="m")

    img = np.full((600, 800, 3), 30, dtype=np.uint8)
    bbox = [300.0, 300.0, 450.0, 500.0]

    # Geometria pré-definida
    l_horiz = np.array([0.0, 1.0, -200.0])
    vz = VanishingPoint(np.array([0.0, 1.0, 0.0]), None, True, 10)
    vx = VanishingPoint(np.array([1.0, 0.0, 0.0]), None, True, 10)
    vy = VanishingPoint(np.array([0.0, 0.0, 1.0]), (400.0, 200.0), False, 10)
    geom = VanishingGeometry(v_x=vx, v_y=vy, v_z=vz, horizon_line=l_horiz)

    resultado = pipeline.process(
        image_rgb=img,
        bbox_xyxy=bbox,
        ref_height_meters=1.50,
        ref_points_y=(500.0, 350.0),
        custom_geometry=geom,
    )

    assert isinstance(resultado, MonocularMetrologyResult)
    assert resultado.height > 0.0
    assert resultado.mean_width > 0.0
    assert resultado.projected_area > 0.0
    assert resultado.aspect_ratio > 0.0
    assert resultado.sam2_iou == pytest.approx(0.965)
    assert "height_formatted" in resultado.to_dict()
