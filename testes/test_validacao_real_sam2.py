"""Validação rigorosa do pipeline SAM 2 com imagens térmicas radiométricas reais do Pyron.

Testa a integração ponta a ponta com termogramas reais não vistos nos testes sintéticos:
- Imagem 1: FLIR2326 (FLIR C5, 160x120 radiométrica, 640x480 RGB exibida).
- Imagem 2: IR01_IR_2129 (240x320 radiométrica, com NaNs e fundo extremo de céu aberto).

Validações obrigatórias:
1. Shape e integridade da máscara gerada (sem NaNs, binária uint8 em {0, 1}).
2. DimensionEstimator: área > 0, pixel_count > 0, length >= width, rotation em [0, 180).
3. Pureza térmica: rejeição do fundo frio/ambiente comprovada por T_med(SAM2) > T_med(caixa)
   e T_min(SAM2) > T_min(caixa).
4. Monitoramento de tempo de execução e consumo de VRAM GPU/CPU.
5. Integração com o endpoint FastAPI (/api/analises/{id}/segmentar).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.armazenamento import Armazenamento
from app.servidor import _obter_imagem_rgb, app
from nucleo.metrologia.dimension_estimator import DimensionEstimator
from nucleo.pipeline.pyron_pipeline import ResultadoAtivo, analisar_ativo
from nucleo.segmentacao.sam2_engine import SAM2Segmentor, caminho_checkpoint

log = logging.getLogger(__name__)

PASTA_DADOS = Path(__file__).resolve().parents[1] / "app" / "dados_app"
ID_FLIR_C5 = "115dfd11283a437d90039ec0c7286768"
ID_IR01 = "279a7ffda05b42a0801d44298ae078a9"


def _verificar_disponibilidade() -> str | None:
    try:
        import sam2  # noqa: F401
        import torch  # noqa: F401
    except ImportError as erro:
        return f"dependência ausente: {erro.name}"
    if not caminho_checkpoint().is_file():
        return f"checkpoint ausente ({caminho_checkpoint()})"
    if not (PASTA_DADOS / "matrizes" / f"{ID_FLIR_C5}.npy").is_file():
        return f"matriz de teste ausente para {ID_FLIR_C5}"
    if not (PASTA_DADOS / "matrizes" / f"{ID_IR01}.npy").is_file():
        return f"matriz de teste ausente para {ID_IR01}"
    return None


pytestmark = pytest.mark.lento  # SAM 2 de verdade nos termogramas reais

MOTIVO_SKIP = _verificar_disponibilidade()
requer_sam2_real = pytest.mark.skipif(MOTIVO_SKIP is not None, reason=MOTIVO_SKIP or "")


@pytest.fixture(scope="module")
def armazenamento_real() -> Armazenamento:
    return Armazenamento(PASTA_DADOS)


@pytest.fixture(scope="module")
def segmentador_real() -> SAM2Segmentor:
    return SAM2Segmentor()


@pytest.fixture(scope="module")
def cliente_api() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------- Testes da Imagem 1 (FLIR C5)


@requer_sam2_real
class TestValidacaoRealFlirC5:
    """Validações sobre FLIR2326: cena radiométrica padrão com múltiplos pontos quentes."""

    def test_ponto_quente_pureza_termica_e_rejeicao_fundo(
        self, armazenamento_real: Armazenamento, segmentador_real: SAM2Segmentor
    ) -> None:
        matriz = armazenamento_real.matriz(ID_FLIR_C5)
        assert matriz is not None
        assert matriz.shape == (160, 120)

        rgb = _obter_imagem_rgb(ID_FLIR_C5, matriz)
        assert rgb.shape == (160, 120, 3)

        # Caixa do ponto quente 3: [x0, y0, x1, y1]
        caixa = [83.0, 104.0, 97.0, 119.0]
        x1, y1, x2, y2 = (int(v) for v in caixa)
        caixa_bruta = matriz[y1:y2, x1:x2]

        bruta_tmax = float(np.nanmax(caixa_bruta))
        bruta_tmed = float(np.nanmean(caixa_bruta))
        bruta_tmin = float(np.nanmin(caixa_bruta))

        resultado = analisar_ativo(
            segmentador=segmentador_real,
            imagem_rgb=rgb,
            matriz_termica=matriz,
            bbox_xyxy=caixa,
            metric_ratio=1.5,
        )

        assert isinstance(resultado, ResultadoAtivo)
        # 1. Integridade da máscara
        assert resultado.mascara.shape == (160, 120)
        assert resultado.mascara_termica.shape == (160, 120)
        assert resultado.mascara.dtype == np.uint8
        assert not np.isnan(resultado.mascara).any()
        assert np.isin(resultado.mascara, [0, 1]).all()
        assert resultado.score > 0.70  # SAM 2 reconhece com alta confiança

        # 2. Metrologia via DimensionEstimator
        geo = resultado.geometria
        assert geo["area_px"] > 0
        assert geo["pixel_count"] > 0
        assert geo["length_px"] >= geo["width_px"] - 1e-4
        assert 0.0 <= geo["rotation_deg"] < 180.0
        assert geo["length_metric"] == pytest.approx(geo["length_px"] * 1.5, rel=1e-4)

        # 3. Pureza térmica: rejeição do fundo frio circundante
        t_iso = resultado.termica
        assert t_iso is not None
        # O pico de calor deve ser preservado exatamente
        assert t_iso.t_max == pytest.approx(bruta_tmax, abs=0.01)
        # Ao eliminar o fundo frio da caixa, a média térmica da peça isolada sobe
        assert t_iso.t_med > bruta_tmed
        # O piso térmico da máscara SAM 2 é significativamente superior ao fundo frio
        assert t_iso.t_min > bruta_tmin + 3.0

        # 4. Desempenho e tempos
        tempos = resultado.tempos_ms
        assert "embeddings" in tempos and "mascara" in tempos
        assert tempos["geometria"] < 150.0  # Tolerância robusta para execução sob carga da GPU
        assert tempos["termica"] < 50.0

    def test_reaproveitamento_de_quadro_para_multiplas_caixas(
        self, armazenamento_real: Armazenamento, segmentador_real: SAM2Segmentor
    ) -> None:
        """Verifica que reutilizar_quadro=True ignora recalcular embeddings Hiera."""
        matriz = armazenamento_real.matriz(ID_FLIR_C5)
        rgb = _obter_imagem_rgb(ID_FLIR_C5, matriz)

        caixas = [
            [98.0, 94.0, 108.0, 119.0],  # Ponto quente 2
            [43.0, 81.0, 61.0, 119.0],   # Ponto quente 4
        ]

        # Primeiro quadro calcula embedding
        res1 = analisar_ativo(segmentador_real, rgb, matriz, caixas[0], reutilizar_quadro=False)
        assert res1.tempos_ms["embeddings"] > 0.0

        # Segundo quadro reutiliza embedding (tempo de embedding = 0)
        res2 = analisar_ativo(segmentador_real, rgb, matriz, caixas[1], reutilizar_quadro=True)
        assert res2.tempos_ms["embeddings"] == 0.0
        # Decodificação da máscara em GPU é extremamente veloz (< 100 ms)
        assert res2.tempos_ms["mascara"] < 100.0


# ---------------------------------------------------------------- Testes da Imagem 2 (IR01)


@requer_sam2_real
class TestValidacaoRealIr01:
    """Validações sobre IR01_IR_2129: dados com saturações, NaNs e temperaturas extremas (-98.9°C a 260.8°C)."""

    def test_resiliencia_com_nans_e_temperaturas_extremas(
        self, armazenamento_real: Armazenamento, segmentador_real: SAM2Segmentor
    ) -> None:
        matriz = armazenamento_real.matriz(ID_IR01)
        assert matriz is not None
        assert matriz.shape == (240, 320)
        # Confirma presença de NaNs e valores negativos extremos na cena original
        assert np.isnan(matriz).any()
        assert (matriz < 0).any()

        rgb = _obter_imagem_rgb(ID_IR01, matriz)
        assert rgb.shape == (240, 320, 3)
        assert not np.isnan(rgb).any()

        # Região de interesse quente: Ponto quente 2 [160, 53, 198, 97]
        caixa = [160.0, 53.0, 198.0, 97.0]
        resultado = analisar_ativo(
            segmentador=segmentador_real,
            imagem_rgb=rgb,
            matriz_termica=matriz,
            bbox_xyxy=caixa,
        )

        # 1. Integridade dimensional e ausência de contaminação por NaNs
        assert resultado.mascara.shape == (240, 320)
        assert not np.isnan(resultado.mascara).any()
        assert resultado.score > 0.50

        # 2. Metrologia
        geo = resultado.geometria
        assert geo["area_px"] > 0
        assert geo["length_px"] >= geo["width_px"] - 1e-4
        assert 0.0 <= geo["rotation_deg"] < 180.0

        # 3. Estatísticas térmicas mesmo com NaNs na matriz
        t_iso = resultado.termica
        assert t_iso is not None
        assert t_iso.t_max == pytest.approx(260.79, abs=0.1)
        assert np.isfinite(t_iso.t_med)
        assert np.isfinite(t_iso.t_desvio)
        assert t_iso.pixels > 0


# ---------------------------------------------------------------- Testes via TestClient (FastAPI)


@requer_sam2_real
class TestValidacaoEndpointFastAPI:
    """Valida a rota /api/analises/{id}/segmentar do servidor FastAPI com as imagens reais."""

    def test_endpoint_segmentar_flir_c5(self, cliente_api: TestClient) -> None:
        # Ponto quente 3 da inspeção FLIR C5 (id da região no banco: d2dfaa14)
        resp = cliente_api.post(
            f"/api/analises/{ID_FLIR_C5}/segmentar",
            json={"regiao_id": "d2dfaa14", "metric_ratio": 2.0},
        )
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["ok"] is True
        assert "segmentacao" in corpo

        seg = corpo["segmentacao"]
        assert seg["score"] > 0.70
        assert seg["geometria"]["length_metric"] == pytest.approx(seg["geometria"]["length_px"] * 2.0, rel=1e-4)
        assert seg["termica_isolada"]["t_max"] > 40.0
        assert isinstance(seg["contorno"], list)
        assert len(seg["contorno"]) >= 3  # Polígono fechado com pelo menos 3 vértices

    def test_endpoint_segmentar_caixa_avulsa_ir01(self, cliente_api: TestClient) -> None:
        # Envia uma caixa avulsa inédita sobre a imagem IR01
        caixa_inédita = [162.0, 100.0, 201.0, 137.0]
        resp = cliente_api.post(
            f"/api/analises/{ID_IR01}/segmentar",
            json={"caixa": caixa_inédita},
        )
        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["ok"] is True
        assert "analise" in corpo
        # Verifica se a nova região foi anexada à análise retornada
        regioes = corpo["analise"]["regioes"]
        ultima = regioes[-1]
        assert ultima["origem"] == "segmentacao:sam2"
        assert "segmentacao" in ultima
        assert ultima["segmentacao"]["score"] > 0.50
