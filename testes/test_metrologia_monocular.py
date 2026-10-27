"""Testes unitários de metrologia monocular projetiva (Criminisi et al. e pontos de fuga).

Migrado e consolidado na arquitetura Pyron em nucleo.metrologia.
"""

from __future__ import annotations

import numpy as np
import pytest

from nucleo.metrologia.criminisi_metrology import (
    ProjectiveMetrologyEngine,
)
from nucleo.metrologia.vanishing_points import (
    LineSegment,
    VanishingGeometryEstimator,
    intersect_lines,
)


def test_vanishing_geometry_estimator_output_format():
    """Valida o formato de saída exigido:

    {"vanishing_point_z": (vx, vy), "horizon_line": (a, b, c), "horizon_y_center": y_val}.
    """
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
    """Valida propriedades de segmentos de reta e interseção projetiva homogênea."""
    seg = LineSegment(0.0, 0.0, 10.0, 0.0)
    assert seg.length == pytest.approx(10.0)
    assert seg.angle_rad == pytest.approx(0.0)

    l1 = np.array([1.0, 0.0, -10.0])
    l2 = np.array([0.0, 1.0, -20.0])
    pt = intersect_lines(l1, l2)
    assert (pt[0] / pt[2]) == pytest.approx(10.0)
    assert (pt[1] / pt[2]) == pytest.approx(20.0)


def test_projective_metrology_engine_mathematical_formulation():
    """Valida a formulação matemática exata de Criminisi et al.:

    Delta_proj = |yb - yt| / |yb - horizon_y|
    Delta_ref = |y_ref_base - y_ref_top| / |y_ref_base - horizon_y|
    H_objeto = H_ref * (Delta_proj / Delta_ref)
    """
    engine = ProjectiveMetrologyEngine(default_unit="m")

    # Máscara sintética de ativo:
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
    h_objeto_esperado = ref_h_m * (delta_proj_esperado / delta_ref_esperado)  # 2.80 m

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
