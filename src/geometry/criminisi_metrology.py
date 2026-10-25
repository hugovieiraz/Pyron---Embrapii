"""Motor de Metrologia Projetiva (Single View Metrology de Criminisi et al.).

Implementa a classe ProjectiveMetrologyEngine conforme as especificações detalhadas do Pyron:
- Resolução da razão cruzada (cross-ratio) entre objeto e referência estrutural.
- Escala axial local s_y (metros/pixel).
- Perfil de diâmetros ao longo de cada fatia de altura y.
- Integração da área projetada real em metros quadrados (m²).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np

from src.geometry.vanishing_points import VanishingGeometry, line_from_points

EPS = 1e-9

TABELA_LENTES_FLIR = {
    "t1020": 28.0,
    "t1010": 28.0,
    "t1030": 28.0,
    "t1040": 28.0,
    "t530": 24.0,
    "t540": 24.0,
    "t600": 25.0,
    "t620": 25.0,
    "t640": 25.0,
    "t660": 25.0,
    "t840": 24.0,
    "t860": 24.0,
    "e75": 24.0,
    "e85": 24.0,
    "e95": 24.0,
    "e54": 24.0,
    "e76": 24.0,
    "e86": 24.0,
    "e96": 24.0,
    "e4": 45.0,
    "e5": 45.0,
    "e6": 45.0,
    "e8": 45.0,
    "c2": 41.0,
    "c3": 41.0,
    "c5": 54.0,
    "t420": 25.0,
    "t440": 25.0,
    "e50": 25.0,
    "e60": 25.0,
    "a310": 25.0,
    "a320": 25.0,
    "flir one pro": 50.0,
    "flir one": 50.0,
}


def obter_hfov_camera(modelo: str | None) -> float:
    """Retorna o HFOV horizontal em graus para o modelo da câmera (ordenado pelo prefixo mais específico)."""
    if not modelo:
        return 28.0
    mod_lower = modelo.lower()
    for chave in sorted(TABELA_LENTES_FLIR.keys(), key=len, reverse=True):
        if chave in mod_lower:
            return TABELA_LENTES_FLIR[chave]
    return 28.0  # padrão industrial FLIR (lente 28°)



@dataclass(frozen=True)
class ReferenceObject:
    """Objeto vertical de referência com altura física conhecida."""

    base_pt: tuple[float, float]
    top_pt: tuple[float, float]
    height_metric: float  # Altura real conhecida em metros
    name: str = "Referência"


@dataclass(frozen=True)
class VerticalMeasurement:
    """Resultado da medição métrica monocular projetiva de um objeto vertical."""

    height_metric: float
    mean_width_metric: float
    projected_area_metric: float
    pixel_height: float
    mean_pixel_width: float
    pixel_area: float
    metric_scale: float
    base_point: tuple[float, float]
    top_point: tuple[float, float]
    cross_ratio: float
    unit: str = "m"


@dataclass(frozen=True)
class ProjectiveDimensionsResult:
    """Resultado completo retornado por ProjectiveMetrologyEngine.compute_real_dimensions."""

    height_meters: float
    mean_width_meters: float
    projected_area_m2: float
    scale_y_m_per_px: float
    y_base: int
    y_top: int
    delta_proj: float
    delta_ref: float
    diameter_profile: dict[int, float]  # y_px -> diametro_em_metros
    max_diameter_meters: float
    min_diameter_meters: float
    aspect_ratio: float

    def to_dict(self) -> dict:
        return asdict(self)


class ProjectiveMetrologyEngine:
    """Motor de Metrologia Projetiva conforme especificação detalhada do Pyron."""

    def __init__(self, default_unit: str = "m"):
        self.default_unit = default_unit

    def compute_dimensions_from_telemetry(
        self,
        mask: np.ndarray,
        distance_m: float,
        camera_model: str | None = None,
        image_width: int = 1024,
        hfov_deg: float | None = None,
    ) -> dict:
        """MÉTODO 1 (Telemetria Óptica): Calcula dimensões reais diretamente da distância e lente da câmera."""
        binaria = (np.asarray(mask) > 0).astype(np.uint8)
        if not binaria.any():
            raise ValueError("A máscara fornecida está vazia.")

        linhas, colunas = np.nonzero(binaria)
        y_b = int(linhas.max())
        y_t = int(linhas.min())
        pixel_height = float(abs(y_b - y_t) + 1)

        hfov = float(hfov_deg) if hfov_deg is not None else obter_hfov_camera(camera_model)
        dist = float(distance_m)
        if dist <= 0:
            raise ValueError(f"Distância inválida para telemetria ({dist} m).")

        largura_cena_m = 2.0 * dist * math.tan(math.radians(hfov / 2.0))
        scale_m_per_px = largura_cena_m / float(max(image_width, 1))

        # Altura física real calculada diretamente dos pixels e da lente
        h_calculada = pixel_height * scale_m_per_px

        diameter_profile: dict[int, float] = {}
        larguras_metricas: list[float] = []

        for y_coord in range(y_t, y_b + 1):
            xs_na_linha = colunas[linhas == y_coord]
            if len(xs_na_linha) > 0:
                largura_px = float(xs_na_linha.max() - xs_na_linha.min() + 1)
            else:
                largura_px = 0.0
            diam_m = largura_px * scale_m_per_px
            diameter_profile[y_coord] = round(diam_m, 4)
            if largura_px > 0:
                larguras_metricas.append(diam_m)

        max_diam = max(larguras_metricas) if larguras_metricas else 0.0
        min_diam = min(larguras_metricas) if larguras_metricas else 0.0
        area_projetada_m2 = float(binaria.sum()) * (scale_m_per_px ** 2)
        mean_width_m = area_projetada_m2 / max(h_calculada, 1e-6)
        aspect_ratio = h_calculada / max(mean_width_m, 1e-6)

        return {
            "metodo_metrologia": "telemetria_optica",
            "detalhes_metrologia": f"{camera_model or 'Câmera'} · Distância: {dist:.1f}m · FOV: {hfov:.0f}° · Escala: {scale_m_per_px*1000:.2f} mm/px",
            "height_meters": round(h_calculada, 4),
            "mean_width_meters": round(mean_width_m, 4),
            "max_diameter_meters": round(max_diam, 4),
            "min_diameter_meters": round(min_diam, 4),
            "projected_area_m2": round(area_projetada_m2, 4),
            "scale_y_m_per_px": scale_m_per_px,
            "aspect_ratio": round(aspect_ratio, 2),
            "diameter_profile": diameter_profile,
            "distancia_m": dist,
            "hfov_deg": hfov,
        }

    def compute_real_dimensions(
        self,
        mask: np.ndarray,
        horizon_y: float,
        vz: tuple[float, float] | Sequence[float] | None = None,
        ref_height_meters: float = 1.0,
        ref_points_y: tuple[float, float] = (400.0, 200.0),
    ) -> dict:
        """Calcula altura, largura média, perfil de diâmetros e área projetada reais a partir da máscara e referência.

        Parâmetros:
          - mask: Máscara binária do objeto obtida pelo SAM 2 (uint8 ou booleana).
          - horizon_y: Coordenada vertical da linha do horizonte no plano da imagem.
          - vz: Ponto de fuga vertical (vzx, vzy).
          - ref_height_meters: Altura conhecida do elemento estrutural de referência (metros).
          - ref_points_y: Tupla com a base e o topo em pixels do elemento de referência (y_ref_base, y_ref_top).

        Fórmulas matemáticas especificadas:
          Delta_proj = |y_b - y_t| / |y_b - horizon_y|
          Delta_ref  = |y_ref_base - y_ref_top| / |y_ref_base - horizon_y|
          H_objeto   = H_ref * (Delta_proj / Delta_ref)
          s_y        = H_objeto / |y_b - y_t|  (metros/pixel)
        """
        binaria = (np.asarray(mask) > 0).astype(np.uint8)
        if not binaria.any():
            raise ValueError("A máscara fornecida está vazia.")

        linhas, colunas = np.nonzero(binaria)
        y_b = int(linhas.max())  # base: maior coordenada vertical
        y_t = int(linhas.min())  # topo: menor coordenada vertical

        pixel_height = float(abs(y_b - y_t))
        if pixel_height < 1.0:
            raise ValueError(f"Altura em pixels da máscara é insuficiente ({pixel_height:.1f} px).")

        y_ref_base, y_ref_top = float(ref_points_y[0]), float(ref_points_y[1])
        ref_pixel_h = abs(y_ref_base - y_ref_top)
        if ref_pixel_h < 1.0:
            raise ValueError(f"Altura em pixels da referência é insuficiente ({ref_pixel_h:.1f} px).")

        # Proteção contra singularidade numérica e estabilização de horizonte l_inf
        dist_base_horizon = max(abs(y_b - horizon_y), 5.0)
        dist_ref_base_horizon = max(abs(y_ref_base - horizon_y), 5.0)

        # 1. Razões projetivas (Cross-ratio simplificado de Criminisi)
        delta_proj = pixel_height / dist_base_horizon
        delta_ref = ref_pixel_h / dist_ref_base_horizon

        # 2. Altura real do objeto em metros
        h_objeto = float(ref_height_meters * (delta_proj / delta_ref))

        # 3. Escala métrica axial local s_y (metros por pixel)
        s_y = h_objeto / pixel_height

        # 4. Perfil de diâmetros ao longo da altura
        # Para cada y ativo, mede a extensão horizontal de pixels da seção transversal
        diameter_profile: dict[int, float] = {}
        larguras_metricas: list[float] = []
        area_projetada_m2 = 0.0

        for y in range(y_t, y_b + 1):
            xs = colunas[linhas == y]
            if not len(xs):
                continue
            largura_px = float(xs.max() - xs.min() + 1)

            # A escala transversal s(y) ao longo do objeto vertical:
            # Em objetos esbeltos de subestação, a escala métrica é calibrada pelo eixo vertical s_y
            diametro_m = largura_px * s_y
            diameter_profile[int(y)] = round(diametro_m, 4)
            larguras_metricas.append(diametro_m)

            # Área do elemento de altura 1 px: largura_m * dy_m = largura_px * (s_y ** 2)
            area_projetada_m2 += largura_px * (s_y ** 2)

        mean_width_meters = float(np.mean(larguras_metricas)) if larguras_metricas else 0.0
        max_diam = float(max(larguras_metricas)) if larguras_metricas else 0.0
        min_diam = float(min(larguras_metricas)) if larguras_metricas else 0.0
        aspect_ratio = round(h_objeto / mean_width_meters, 2) if mean_width_meters > 0 else 0.0

        return {
            "metodo_metrologia": "geometria_projetiva_criminisi",
            "detalhes_metrologia": f"Referência projetiva: {ref_height_meters:.2f}m · Linha do horizonte l∞",
            "height_meters": round(h_objeto, 4),
            "mean_width_meters": round(mean_width_meters, 4),
            "projected_area_m2": round(area_projetada_m2, 4),
            "scale_y_m_per_px": s_y,
            "y_base": y_b,
            "y_top": y_t,
            "delta_proj": round(delta_proj, 6),
            "delta_ref": round(delta_ref, 6),
            "diameter_profile": diameter_profile,
            "max_diameter_meters": round(max_diam, 4),
            "min_diameter_meters": round(min_diam, 4),
            "aspect_ratio": aspect_ratio,
        }


class CriminisiMetrology:
    """Implementa medições projetivas com objetos de referência e altura de câmera."""

    def __init__(self, geometry: VanishingGeometry, default_unit: str = "m"):
        self.geometry = geometry
        self.unit = default_unit
        self.engine = ProjectiveMetrologyEngine(default_unit=default_unit)

    @staticmethod
    def _to_homog(pt: Sequence[float] | np.ndarray) -> np.ndarray:
        arr = np.asarray(pt, dtype=np.float64).reshape(-1)
        if len(arr) == 2:
            return np.array([arr[0], arr[1], 1.0], dtype=np.float64)
        return arr / (arr[2] if abs(arr[2]) > EPS else 1.0)

    def compute_height_from_camera_height(
        self,
        base_pt: Sequence[float],
        top_pt: Sequence[float],
        camera_height: float,
    ) -> tuple[float, float]:
        """Calcula altura a partir da altura da câmera Zc."""
        if camera_height <= 0:
            raise ValueError(f"camera_height deve ser positivo; veio {camera_height}")

        b_h = self._to_homog(base_pt)
        t_h = self._to_homog(top_pt)
        l_horiz = self.geometry.horizon_line

        dist_b = float(np.dot(l_horiz, b_h))
        dist_t = float(np.dot(l_horiz, t_h))

        if abs(dist_b) < EPS:
            raise ValueError("Base coincide com horizonte.")

        vz = self.geometry.v_z
        if vz.is_at_infinity:
            ratio_vz = 1.0
        else:
            vz_h = vz.point_homog
            denom_vz = float(np.dot(vz_h, t_h))
            ratio_vz = float(np.dot(vz_h, b_h)) / denom_vz if abs(denom_vz) > EPS else 1.0

        termo = (dist_t / dist_b) * ratio_vz
        height = camera_height * (1.0 - termo)
        return float(abs(height)), float(termo)

    def compute_height_from_reference(
        self,
        base_target: Sequence[float],
        top_target: Sequence[float],
        reference: ReferenceObject,
    ) -> tuple[float, float]:
        """Calcula altura a partir de objeto de referência vertical com Zref conhecido."""
        b = np.asarray(base_target, dtype=np.float64)[:2]
        t = np.asarray(top_target, dtype=np.float64)[:2]
        b_ref = np.asarray(reference.base_pt, dtype=np.float64)[:2]
        t_ref = np.asarray(reference.top_pt, dtype=np.float64)[:2]

        l_horiz = self.geometry.horizon_line
        b_h = self._to_homog(b)
        t_h = self._to_homog(t)
        b_ref_h = self._to_homog(b_ref)
        t_ref_h = self._to_homog(t_ref)

        l_base = np.cross(b_ref_h, b_h)
        v_base_h = np.cross(l_base, l_horiz)
        l_top_ref = np.cross(v_base_h, t_ref_h)
        l_vert = np.cross(b_h, t_h)

        t_prime_h = np.cross(l_top_ref, l_vert)
        if abs(t_prime_h[2]) > EPS:
            t_prime_h = t_prime_h / t_prime_h[2]

        dist_b = float(np.dot(l_horiz, b_h))
        dist_t = float(np.dot(l_horiz, t_h))
        dist_t_prime = float(np.dot(l_horiz, t_prime_h))

        vz = self.geometry.v_z
        if vz.is_at_infinity:
            ratio_vz_t = 1.0
            ratio_vz_prime = 1.0
        else:
            vz_h = vz.point_homog
            denom_t = float(np.dot(vz_h, t_h))
            denom_prime = float(np.dot(vz_h, t_prime_h))
            num_b = float(np.dot(vz_h, b_h))
            ratio_vz_t = num_b / denom_t if abs(denom_t) > EPS else 1.0
            ratio_vz_prime = num_b / denom_prime if abs(denom_prime) > EPS else 1.0

        termo_t = 1.0 - (dist_t / dist_b) * ratio_vz_t
        termo_prime = 1.0 - (dist_t_prime / dist_b) * ratio_vz_prime

        cross_ratio = termo_t / termo_prime if abs(termo_prime) > EPS else 1.0
        height = reference.height_metric * cross_ratio
        return float(abs(height)), float(cross_ratio)

    def measure_segmented_object(
        self,
        mask: np.ndarray,
        camera_height: float | None = None,
        reference: ReferenceObject | None = None,
        base_override: Sequence[float] | None = None,
        top_override: Sequence[float] | None = None,
    ) -> VerticalMeasurement:
        """Medição de altura, largura média e área projetada da máscara."""
        binaria = (np.asarray(mask) > 0).astype(np.uint8)
        if not binaria.any():
            raise ValueError("Máscara vazia.")

        linhas, colunas = np.nonzero(binaria)
        y_base = int(linhas.max()) if base_override is None else int(base_override[1])
        x_base = float(colunas[linhas == y_base].mean()) if base_override is None else float(base_override[0])
        base_pt = (x_base, float(y_base))

        y_top = int(linhas.min()) if top_override is None else int(top_override[1])
        x_top = float(colunas[linhas == y_top].mean()) if top_override is None else float(top_override[0])
        top_pt = (x_top, float(y_top))

        pixel_height = float(abs(y_base - y_top))
        if pixel_height < 1.0:
            raise ValueError("Altura em pixels da máscara insuficiente.")

        if camera_height is not None:
            height_metric, cr = self.compute_height_from_camera_height(base_pt, top_pt, camera_height)
        elif reference is not None:
            height_metric, cr = self.compute_height_from_reference(base_pt, top_pt, reference)
        else:
            raise ValueError("Forneça camera_height ou reference.")

        metric_scale = height_metric / pixel_height
        alturas_fatia = linhas.max() - linhas.min() + 1
        mean_pixel_width = float(binaria.sum()) / float(alturas_fatia) if alturas_fatia > 0 else 0.0

        mean_width_metric = mean_pixel_width * metric_scale
        projected_area_metric = float(binaria.sum()) * (metric_scale**2)

        return VerticalMeasurement(
            height_metric=round(height_metric, 3),
            mean_width_metric=round(mean_width_metric, 3),
            projected_area_metric=round(projected_area_metric, 3),
            pixel_height=round(pixel_height, 2),
            mean_pixel_width=round(mean_pixel_width, 2),
            pixel_area=int(binaria.sum()),
            metric_scale=metric_scale,
            base_point=base_pt,
            top_point=top_pt,
            cross_ratio=round(cr, 6),
            unit=self.unit,
        )
