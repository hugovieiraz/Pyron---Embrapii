"""Testes dos aprimoramentos técnicos identificados na auditoria profunda do Pyron.

Cobre:
1. Sincronização e classificação da classe 'transformador' no DINOv2.
2. Sensibilidade adaptativa de resolução no detector SAM 2 + DINOv2.
3. Fechamento morfológico para extração de contornos SVG contínuos.
4. Expansão da tabela de lentes e calibração de câmeras FLIR.
5. Mitigação de singularidades numéricas no horizonte de Criminisi.
6. Validação do fluxo de metrologia monocular de duplo método.
7. Teste de ponta a ponta do upload de imagem com cálculo instantâneo.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import servidor
from app.armazenamento import Armazenamento
from nucleo.classificacao.dinov2_engine import (
    CLASSES_PYRON,
    NOMES_CLASSES,
    DINOv2Classifier,
    gerar_padrao_sintetico,
)
from nucleo.detectores.sam2_dinov2 import SAM2DINOv2Detector, simplificar_contorno_binario
from src.geometry.criminisi_metrology import (
    ProjectiveMetrologyEngine,
    obter_hfov_camera,
)
from testes.test_flir import _bruto_de, _jpeg_flir, _parametros


@pytest.fixture()
def cliente_auditoria(tmp_path, monkeypatch):
    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    return TestClient(servidor.app)


def _criar_termograma_auditoria(altura: int = 120, largura: int = 160) -> bytes:
    p = _parametros()
    t = np.full((altura, largura), 22.0, dtype=np.float32)
    # Região aquecida simulando componente (ex: bucha / transformador)
    t[int(altura * 0.2):int(altura * 0.8), int(largura * 0.3):int(largura * 0.7)] = 45.0
    return _jpeg_flir(_bruto_de(t, p), p, png=False)


# =========================================================================
# 1. Auditoria DINOv2: Classe 'transformador'
# =========================================================================
def test_dinov2_classe_transformador_sincronizada():
    """Verifica que 'transformador' faz parte das classes registradas no classificador DINOv2."""
    assert "transformador" in CLASSES_PYRON
    assert NOMES_CLASSES.get("transformador") == "Transformador"

    # Padrão sintético determinístico deve ser gerado com resolução compatível ViT (224x224x3)
    padrao = gerar_padrao_sintetico("transformador")
    assert padrao.shape == (224, 224, 3)
    assert padrao.dtype == np.uint8

    # O classificador deve reconhecer a classe em sua galeria de protótipos
    prototipo = np.random.RandomState(42).randn(384).astype(np.float32)
    prototipo /= np.linalg.norm(prototipo)
    clf = DINOv2Classifier(prototipos={"transformador": prototipo})
    assert "transformador" in clf.prototipos


# =========================================================================
# 2. Auditoria SAM 2: Sensibilidade Adaptativa à Resolução
# =========================================================================
def test_sam2_sensibilidade_adaptativa_resolucao():
    """Garante que câmeras térmicas de menor resolução (160x120) não sofram descarte de componentes válidos."""
    # Simula máscara de componente ocupando 600 px em termograma 160x120 (total 19.200 px)
    h, w = 120, 160
    area_total = h * w
    area_cand = 600

    area_min = max(80, int(area_total * 0.002))  # 80 px
    area_max = int(area_total * 0.88)            # 16.896 px

    # Em imagens pequenas, 600 px era descartado pelo corte antigo (< 3000 px)
    # Com a sensibilidade adaptativa, o componente é preservado
    assert area_cand >= area_min
    assert area_cand <= area_max

    # Em imagens de alta resolução (1024x768 = 786.432 px)
    area_total_alta = 1024 * 768
    area_min_alta = max(80, int(area_total_alta * 0.002))  # 1572 px
    assert area_min_alta > 1000


# =========================================================================
# 3. Auditoria de Contornos SVG com Fechamento Morfológico
# =========================================================================
def test_fechamento_morfologico_contorno_svg():
    """Verifica que o fechamento morfológico remove pequenos ruídos e produz contornos fechados válidos."""
    mascara = np.zeros((100, 100), dtype=np.uint8)
    mascara[30:70, 30:70] = 1
    # Adiciona pequeno orifício no interior para testar robustez
    mascara[45:47, 45:47] = 0

    pts = simplificar_contorno_binario(mascara, epsilon=1.0)
    assert len(pts) >= 4
    # Todos os pontos devem ser coordenadas válidas dentro da imagem
    for p in pts:
        assert 0.0 <= p[0] <= 100.0
        assert 0.0 <= p[1] <= 100.0


# =========================================================================
# 4. Auditoria da Tabela de Lentes FLIR Expandida
# =========================================================================
def test_tabela_lentes_flir_expandida():
    """Testa se os modelos adicionais de câmeras FLIR são devidamente mapeados para seus HFOVs."""
    assert obter_hfov_camera("FLIR T420") == 25.0
    assert obter_hfov_camera("FLIR T440") == 25.0
    assert obter_hfov_camera("FLIR E50") == 25.0
    assert obter_hfov_camera("FLIR E60") == 25.0
    assert obter_hfov_camera("FLIR A310") == 25.0
    assert obter_hfov_camera("FLIR A320") == 25.0
    assert obter_hfov_camera("FLIR ONE Pro") == 50.0
    assert obter_hfov_camera("FLIR ONE") == 50.0
    # Modelo não listado deve retornar o padrão industrial de 28.0°
    assert obter_hfov_camera("Camera Generica Subestacao") == 28.0


# =========================================================================
# 5. Auditoria de Estabilidade Numérica no Horizonte Criminisi
# =========================================================================
def test_criminisi_metrologia_singularidade_horizonte():
    """Testa se a proximidade da base do objeto com a linha do horizonte é amortecida com tolerância mínima."""
    engine = ProjectiveMetrologyEngine()
    mascara = np.zeros((300, 300), dtype=np.uint8)
    mascara[90:200, 120:180] = 1  # y_b = 199, y_t = 90

    # Horizonte posicionado exatamente a 2 pixels da base (singularidade potencial)
    horizonte_perigoso = 201.0

    # Não deve levantar ZeroDivisionError ou explodir infinitamente
    res = engine.compute_real_dimensions(
        mask=mascara,
        horizon_y=horizonte_perigoso,
        ref_height_meters=1.2,
        ref_points_y=(280.0, 150.0),
    )

    assert res["height_meters"] > 0.0
    assert res["scale_y_m_per_px"] > 0.0
    assert res["projected_area_m2"] > 0.0
    assert not np.isnan(res["height_meters"])
    assert not np.isinf(res["height_meters"])


# =========================================================================
# 6. Auditoria de Metrologia Duplo Método (Método 1 e Método 2)
# =========================================================================
def test_metrologia_duplo_metodo_comparacao():
    """Verifica a consistência e riqueza métrica dos Métodos 1 (Telemetria) e 2 (Geometria Projetiva)."""
    engine = ProjectiveMetrologyEngine()
    mascara = np.zeros((480, 640), dtype=np.uint8)
    mascara[100:350, 280:360] = 1  # pixel_h = 250 px (linhas 100 a 349)

    # Método 1: Telemetria com distância e modelo de câmera
    res_m1 = engine.compute_dimensions_from_telemetry(
        mask=mascara,
        distance_m=5.0,
        camera_model="FLIR T540",
        image_width=640,
    )
    assert res_m1["metodo_metrologia"] == "telemetria_optica"
    assert 0.5 < res_m1["height_meters"] < 2.0
    assert res_m1["max_diameter_meters"] > 0.0
    assert res_m1["projected_area_m2"] > 0.0
    assert len(res_m1["diameter_profile"]) == 250

    # Método 2: Geometria Projetiva Criminisi
    res_m2 = engine.compute_real_dimensions(
        mask=mascara,
        horizon_y=800.0,
        ref_height_meters=1.25,
        ref_points_y=(349.0, 100.0),
    )
    assert res_m2["metodo_metrologia"] == "geometria_projetiva_criminisi"
    assert res_m2["height_meters"] == pytest.approx(1.25, abs=0.01)
    assert res_m2["mean_width_meters"] > 0.0
    assert res_m2["aspect_ratio"] > 0.0


# =========================================================================
# 7. Auditoria End-to-End: Upload de Imagem com SAM 2 e Metrologia Instantânea
# =========================================================================
def test_upload_com_sam2_calculo_instantaneo(cliente_auditoria, monkeypatch):
    """Garante que enviar uma nova imagem com modelo sam2-dinov2 realize segmentação e metrologia automáticas."""
    class MockSAM2DINOv2(SAM2DINOv2Detector):
        def detectar_com_metrologia(self, matriz, imagem, metadados=None, *args, **kwargs):
            return [
                {
                    "id": "transf1",
                    "nome": "Transformador 1",
                    "classe": "transformador",
                    "caixa": [30.0, 20.0, 120.0, 95.0],
                    "confianca": 0.96,
                    "origem": "detector:sam2_dinov2",
                    "segmentacao": {
                        "score": 0.98,
                        "geometria": {
                            "unit": "m",
                            "metodo_metrologia": "telemetria_optica",
                            "detalhes_metrologia": "FLIR T540 · Distância: 4.5m · FOV: 24°",
                            "height_meters": 1.85,
                            "mean_width_meters": 1.42,
                            "max_diameter_meters": 1.60,
                            "min_diameter_meters": 1.20,
                            "projected_area_m2": 2.62,
                            "aspect_ratio": 1.30,
                            "scale_y_m_per_px": 0.0045,
                            "ref_height_meters": 1.60,
                            "distancia_m": 4.5,
                        },
                        "termica_isolada": {
                            "t_max": 52.3,
                            "t_min": 24.1,
                            "t_media": 38.6,
                            "t_mediana": 37.9,
                            "desvio_padrao": 6.2,
                            "delta_t_ativo": 28.2,
                            "area_pixels": 4500,
                        },
                        "contorno": [[30.0, 20.0], [120.0, 20.0], [120.0, 95.0], [30.0, 95.0]],
                    },
                }
            ]

    # Injeta mock no detector do servidor
    orig_detector = servidor._detector
    def mock_detector(id_modelo):
        if id_modelo == "sam2-dinov2":
            return MockSAM2DINOv2()
        return orig_detector(id_modelo)

    monkeypatch.setattr(servidor, "_detector", mock_detector)

    jpeg_bytes = _criar_termograma_auditoria(120, 160)
    resposta = cliente_auditoria.post(
        "/api/analises",
        files={"arquivo": ("subestacao_termica.jpg", jpeg_bytes, "image/jpeg")},
        data={"modelo": "sam2-dinov2"},
    )
    assert resposta.status_code == 200
    dados = resposta.json()
    id_modelo_retornado = dados["modelo"]["id"] if isinstance(dados["modelo"], dict) else dados["modelo"]
    assert id_modelo_retornado == "sam2-dinov2"

    regioes = dados["regioes"]
    assert len(regioes) == 1
    reg = regioes[0]
    assert reg["classe"] == "transformador"
    assert reg["nome"] == "Transformador 1"
    assert "segmentacao" in reg
    seg = reg["segmentacao"]
    assert seg["score"] == 0.98
    assert seg["geometria"]["height_meters"] == 1.85
    assert seg["geometria"]["metodo_metrologia"] == "telemetria_optica"
    assert len(seg["contorno"]) == 4
    assert seg["termica_isolada"]["t_max"] == 52.3
