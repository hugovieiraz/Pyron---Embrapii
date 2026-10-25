"""Testes do detector automático SAM 2 + DINOv2 e da rota /auto_identificar."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import servidor
from app.armazenamento import Armazenamento
from nucleo.detectores.sam2_dinov2 import SAM2DINOv2Detector
from testes.test_flir import _bruto_de, _jpeg_flir, _parametros


@pytest.fixture()
def cliente_teste(tmp_path, monkeypatch):
    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    return TestClient(servidor.app)


def _termograma_sintetico() -> bytes:
    p = _parametros()
    t = np.full((120, 160), 20.0)
    t[20:100, 50:110] = 38.0
    return _jpeg_flir(_bruto_de(t, p), p, png=False)


def test_sam2_dinov2_detector_propriedades():
    det = SAM2DINOv2Detector()
    assert det.id == "sam2-dinov2"
    assert "SAM 2 + DINOv2" in det.nome
    assert det.precisa_imagem is True
    assert "bucha" in det.classes
    assert "isolador" in det.classes
    assert "ponto_quente" not in det.classes[:5]

    desc = det.descrever()
    assert desc["id"] == "sam2-dinov2"
    assert isinstance(desc["cartao"], dict)
    assert "treino" in desc["cartao"]
    assert "vantagens" in desc["cartao"]


def test_endpoint_auto_identificar_analise(cliente_teste, monkeypatch):
    # Mock do detector para teste unitário ágil sem inferência neural pesada
    class MockDetector(SAM2DINOv2Detector):
        def detectar_com_metrologia(self, matriz, imagem, metadados=None, *args, **kwargs):
            return [
                {
                    "id": "bucha1",
                    "nome": "Bucha 1",
                    "classe": "bucha",
                    "caixa": [50.0, 20.0, 110.0, 100.0],
                    "confianca": 0.94,
                    "origem": "detector:sam2_dinov2",
                    "segmentacao": {
                        "score": 0.95,
                        "geometria": {
                            "unit": "m",
                            "height_meters": 1.25,
                            "mean_width_meters": 0.35,
                            "max_diameter_meters": 0.42,
                            "projected_area_m2": 0.43,
                            "aspect_ratio": 3.57,
                            "scale_y_m_per_px": 0.0035,
                        },
                        "termica_isolada": {"t_max": 38.0, "t_med": 36.5},
                        "contorno": [[50.0, 20.0], [110.0, 20.0], [110.0, 100.0], [50.0, 100.0]],
                    },
                    "classificacao_dinov2": {
                        "classe": "bucha",
                        "confianca": 0.94,
                        "nome": "Bucha",
                        "scores": {"bucha": 0.94, "isolador": 0.04},
                    },
                }
            ]

    import nucleo.detectores.sam2_dinov2 as s2d
    monkeypatch.setattr(s2d, "SAM2DINOv2Detector", MockDetector)

    resp_criacao = cliente_teste.post(
        "/api/analises",
        files={"arquivo": ("subestacao.jpg", _termograma_sintetico(), "image/jpeg")},
    )
    assert resp_criacao.status_code == 200
    id_analise = resp_criacao.json()["id"]

    resp_auto = cliente_teste.post(f"/api/analises/{id_analise}/auto_identificar")
    assert resp_auto.status_code == 200
    dados = resp_auto.json()

    assert len(dados["regioes"]) == 1
    reg = dados["regioes"][0]
    assert reg["classe"] == "bucha"
    assert reg["nome"] == "Bucha 1"
    assert reg["confianca"] == 0.94
    assert reg["segmentacao"]["score"] == 0.95
    assert reg["segmentacao"]["geometria"]["height_meters"] == 1.25
    assert reg["classificacao_dinov2"]["classe"] == "bucha"
    assert len(reg["segmentacao"]["contorno"]) == 4


def test_selecao_metrologia_telemetria_vs_criminisi():
    """Valida a prioridade do Método 1 (Telemetria Óptica) sobre o Método 2 (Criminisi)."""
    from nucleo.pipeline.pyron_pipeline import analisar_ativo
    from nucleo.segmentacao.sam2_engine import SAM2Segmentor, Segmentacao

    class MockSegmentor(SAM2Segmentor):
        def __init__(self):
            pass

        def set_frame(self, frame):
            pass

        def segmentar(self, bbox_xyxy):
            mask = np.zeros((200, 200), dtype=np.uint8)
            mask[40:160, 80:120] = 1  # 120 px de altura
            return Segmentacao(mascara=mask, score=0.98, caixa=(80.0, 40.0, 120.0, 160.0), tempo_ms=10.0)

    seg = MockSegmentor()
    rgb = np.full((200, 200, 3), 128, dtype=np.uint8)
    mat = np.full((200, 200), 25.0, dtype=np.float32)

    # Caso 1: Câmera com metadados e distância (Método 1 - Telemetria Óptica)
    meta_flir = {"camera": "FLIR T1020", "distancia_m": 5.0}
    res_telemetria = analisar_ativo(
        segmentador=seg,
        imagem_rgb=rgb,
        matriz_termica=mat,
        bbox_xyxy=[80, 40, 120, 160],
        metadados_camera=meta_flir,
    )
    geom_tel = res_telemetria.geometria
    assert geom_tel["metodo_metrologia"] == "telemetria_optica"
    assert "Distância: 5.0m" in geom_tel["detalhes_metrologia"]
    assert geom_tel["distancia_m"] == 5.0
    assert geom_tel["height_meters"] > 0

    # Caso 2: Câmera sem distância / sem metadados (Método 2 - Criminisi Single View Metrology)
    res_criminisi = analisar_ativo(
        segmentador=seg,
        imagem_rgb=rgb,
        matriz_termica=mat,
        bbox_xyxy=[80, 40, 120, 160],
        metadados_camera=None,
    )
    geom_crim = res_criminisi.geometria
    assert geom_crim["metodo_metrologia"] == "geometria_projetiva_criminisi"
    assert geom_crim["height_meters"] > 0
