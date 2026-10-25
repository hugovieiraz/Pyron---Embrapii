"""Segmentação SAM 2, metrologia e leitura térmica pela máscara.

Duas camadas:

- testes sempre executados, com um preditor falso que imita o ``SAM2ImagePredictor`` (contrato de
  entrada/saída, caixas, escolha da máscara) e com máscaras sintéticas de geometria conhecida;
- testes de integração com o SAM 2 de verdade, pulados quando o pacote ``sam2``, o ``torch`` ou o
  checkpoint (``python ferramentas/baixar_sam2.py``) não estão disponíveis.
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from nucleo.metrologia.dimension_estimator import DimensionEstimator, MascaraVaziaError  # noqa: E402
from nucleo.pipeline.pyron_pipeline import (  # noqa: E402
    ajustar_mascara,
    analisar_ativo,
    estatisticas_termicas,
    exportar_mascara,
)
from nucleo.segmentacao.sam2_engine import (  # noqa: E402
    SAM2Segmentor,
    caminho_checkpoint,
    para_rgb_uint8,
    validar_caixa,
)

ALTURA, LARGURA = 240, 320
# Retângulo cheio de 120 x 60 pixels (colunas 100..219, linhas 90..149)
X0, Y0, W, H = 100, 90, 120, 60
FUNDO_C, PECA_C, QUENTE_C = 20.0, 45.0, 80.0


def imagem_sintetica() -> np.ndarray:
    imagem = np.full((ALTURA, LARGURA, 3), 30, dtype=np.uint8)
    imagem[Y0:Y0 + H, X0:X0 + W] = (200, 210, 220)
    return imagem


def mascara_verdade() -> np.ndarray:
    mascara = np.zeros((ALTURA, LARGURA), dtype=np.uint8)
    mascara[Y0:Y0 + H, X0:X0 + W] = 1
    return mascara


def iou(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.astype(bool), b.astype(bool)
    return float((a & b).sum() / max(1, (a | b).sum()))


class PreditorFalso:
    """Imita o SAM2ImagePredictor: devolve (máscaras C x H x W float, scores C, low_res)."""

    def __init__(self):
        self.imagem = None
        self.chamadas: list[dict] = []

    def set_image(self, image: np.ndarray) -> None:
        assert image.dtype == np.uint8 and image.ndim == 3 and image.shape[2] == 3
        self.imagem = image

    def predict(self, *, box, multimask_output):
        self.chamadas.append({"box": np.asarray(box).tolist(), "multimask": multimask_output})
        x1, y1, x2, y2 = (int(round(v)) for v in box)
        brilho = self.imagem.mean(axis=2) > 127
        certa = np.zeros(brilho.shape, dtype=np.float32)
        certa[y1:y2, x1:x2] = brilho[y1:y2, x1:x2]
        caixa_toda = np.zeros_like(certa)
        caixa_toda[y1:y2, x1:x2] = 1
        # a máscara certa não vem primeiro: o segmentador tem de escolher pelo score
        return np.stack([caixa_toda, certa]), np.array([0.40, 0.97], dtype=np.float32), None


# ---------------------------------------------------------------- metrologia


def test_retangulo_alinhado_area_e_eixos():
    medidas = DimensionEstimator().analyze_contour(mascara_verdade())
    # contorno pelos centros dos pixels da borda: (w-1) x (h-1)
    assert medidas["area_px"] == pytest.approx((W - 1) * (H - 1))
    assert medidas["pixel_count"] == W * H
    assert medidas["length_px"] == pytest.approx(W - 1)
    assert medidas["width_px"] == pytest.approx(H - 1)
    assert medidas["mean_width_px"] == pytest.approx(H - 1)
    assert medidas["rotation_deg"] % 180 == pytest.approx(0, abs=1e-6)
    assert medidas["centroid_px"] == pytest.approx((X0 + (W - 1) / 2, Y0 + (H - 1) / 2))
    assert np.asarray(medidas["bbox_corners"]).shape == (4, 2)
    assert medidas["length_metric"] is None and medidas["unit"] is None


def test_retangulo_vertical_tem_eixo_maior_a_90_graus():
    mascara = np.zeros((ALTURA, LARGURA), dtype=np.uint8)
    mascara[20:220, 150:170] = 1  # 20 de largura x 200 de altura
    medidas = DimensionEstimator().analyze_contour(mascara)
    assert medidas["length_px"] == pytest.approx(199)
    assert medidas["width_px"] == pytest.approx(19)
    assert medidas["rotation_deg"] == pytest.approx(90, abs=1e-6)


@pytest.mark.parametrize("angulo", [15.0, 30.0, 60.0, 135.0])
def test_retangulo_inclinado_recupera_dimensoes_e_angulo(angulo):
    mascara = np.zeros((400, 400), dtype=np.uint8)
    cantos = cv2.boxPoints(((200.0, 200.0), (200.0, 40.0), angulo))
    cv2.fillPoly(mascara, [np.round(cantos).astype(np.int32)], 1)
    medidas = DimensionEstimator().analyze_contour(mascara)
    assert medidas["length_px"] == pytest.approx(200, abs=3)
    assert medidas["width_px"] == pytest.approx(40, abs=3)
    diferenca = abs((medidas["rotation_deg"] - angulo + 90) % 180 - 90)  # ângulo de eixo: 0 ≡ 180
    assert diferenca < 1.5


def test_escala_metrica():
    medidas = DimensionEstimator(unit="mm").analyze_contour(mascara_verdade(), metric_ratio=2.5)
    assert medidas["unit"] == "mm" and medidas["metric_ratio"] == 2.5
    assert medidas["length_metric"] == pytest.approx((W - 1) * 2.5)
    assert medidas["width_metric"] == pytest.approx((H - 1) * 2.5)
    assert medidas["area_metric"] == pytest.approx((W - 1) * (H - 1) * 2.5**2)


def test_mede_so_a_maior_ilha():
    mascara = mascara_verdade()
    mascara[5:10, 5:10] = 1  # ruído pequeno longe da peça
    medidas = DimensionEstimator().analyze_contour(mascara)
    assert medidas["pixel_count"] == W * H


def test_mascara_vazia_e_escala_invalida():
    with pytest.raises(MascaraVaziaError):
        DimensionEstimator().analyze_contour(np.zeros((10, 10), dtype=np.uint8))
    with pytest.raises(ValueError):
        DimensionEstimator().analyze_contour(mascara_verdade(), metric_ratio=0)
    with pytest.raises(ValueError):
        DimensionEstimator().analyze_contour(np.zeros((4, 4, 3), dtype=np.uint8))


# ---------------------------------------------------------------- segmentador (preditor falso)


def test_segmentador_escolhe_maior_score_e_devolve_uint8():
    preditor = PreditorFalso()
    seg = SAM2Segmentor(preditor=preditor)
    seg.set_frame(imagem_sintetica())
    mascara = seg.predict_mask_from_bbox([X0 - 10, Y0 - 10, X0 + W + 10, Y0 + H + 10])
    assert mascara.dtype == np.uint8 and mascara.shape == (ALTURA, LARGURA)
    assert set(np.unique(mascara)) <= {0, 1}
    assert iou(mascara, mascara_verdade()) == pytest.approx(1.0)
    assert preditor.chamadas[-1]["multimask"] is False


def test_segmentador_exige_quadro_e_caixa_valida():
    seg = SAM2Segmentor(preditor=PreditorFalso())
    with pytest.raises(RuntimeError):
        seg.predict_mask_from_bbox([0, 0, 10, 10])
    seg.set_frame(imagem_sintetica())
    for ruim in ([10, 10, 5, 20], [1, 2, 3], [0, 0, float("nan"), 5], [LARGURA + 5, 0, LARGURA + 50, 10]):
        with pytest.raises(ValueError):
            seg.predict_mask_from_bbox(ruim)


def test_caixa_recortada_a_imagem():
    assert validar_caixa(np.array([-20, -5, 400, 100]), LARGURA, ALTURA) == (0.0, 0.0, float(LARGURA), 100.0)


def test_matriz_termica_vira_rgb_uint8():
    matriz = np.linspace(10, 90, ALTURA * LARGURA, dtype=np.float32).reshape(ALTURA, LARGURA)
    matriz[0, 0] = np.nan
    rgb = para_rgb_uint8(matriz)
    assert rgb.shape == (ALTURA, LARGURA, 3) and rgb.dtype == np.uint8
    assert rgb[..., 0].max() == 255 and rgb[0, 1, 0] == 0 and rgb[0, 0, 0] == 0


def test_variante_desconhecida():
    with pytest.raises(ValueError):
        SAM2Segmentor(variante="nao_existe", preditor=PreditorFalso())


# ---------------------------------------------------------------- térmica e pipeline


def matriz_termica(forma=(ALTURA, LARGURA)) -> np.ndarray:
    """Fundo a 20 °C, peça a 45 °C com um ponto a 80 °C e um quente FORA da peça (vizinho) a 95 °C."""
    t = np.full(forma, FUNDO_C, dtype=np.float32)
    fy, fx = forma[0] / ALTURA, forma[1] / LARGURA
    t[int(Y0 * fy):int((Y0 + H) * fy), int(X0 * fx):int((X0 + W) * fx)] = PECA_C
    t[int(110 * fy), int(150 * fx)] = QUENTE_C
    t[int(70 * fy), int(150 * fx)] = 95.0  # dentro da caixa, fora da peça
    return t


def test_estatisticas_so_no_corpo_do_ativo_e_ignora_nan():
    t = matriz_termica()
    t[Y0 + 1, X0 + 1] = np.nan
    est = estatisticas_termicas(t, mascara_verdade())
    assert est.t_max == QUENTE_C and est.t_min == PECA_C
    assert (est.x_max, est.y_max) == (150, 110)
    assert est.pixels == W * H - 1
    valores = np.full(W * H - 1, PECA_C)
    valores[0] = QUENTE_C
    assert est.t_med == pytest.approx(valores.mean(), rel=1e-5)
    assert est.t_desvio == pytest.approx(valores.std(), rel=1e-4)


def test_sem_pixel_valido_devolve_none():
    assert estatisticas_termicas(np.full((ALTURA, LARGURA), np.nan, np.float32), mascara_verdade()) is None


def test_mascara_redimensionada_para_matriz_menor():
    pequena = ajustar_mascara(mascara_verdade(), (ALTURA // 2, LARGURA // 2))
    assert pequena.shape == (ALTURA // 2, LARGURA // 2)
    assert set(np.unique(pequena)) <= {0, 1}
    assert pequena.sum() == pytest.approx(W * H / 4, rel=0.05)


def test_pipeline_ponta_a_ponta_com_preditor_falso(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    seg = SAM2Segmentor(preditor=PreditorFalso())
    caixa = [X0 - 10, Y0 - 25, X0 + W + 10, Y0 + H + 10]  # pega o ponto de 95 °C do vizinho
    resultado = analisar_ativo(seg, imagem_sintetica(), matriz_termica(), caixa, metric_ratio=1.5)

    assert resultado.score == pytest.approx(0.97)
    assert resultado.termica.t_max == QUENTE_C  # o vizinho a 95 °C ficou fora pela máscara
    assert resultado.geometria["length_metric"] == pytest.approx((W - 1) * 1.5)
    resumo = resultado.resumo()
    json.dumps(resumo)  # serializável para laudo/banco
    assert set(resumo["tempos_ms"]) == {"embeddings", "mascara", "geometria", "termica"}

    eventos = [json.loads(r.getMessage())["evento"] for r in caplog.records if r.getMessage().startswith("{")]
    assert {"sam2.set_frame", "sam2.predict", "pyron.ativo_analisado"} <= set(eventos)

    png = exportar_mascara(resultado.mascara, tmp_path / "máscaras" / "ativo.png")
    lida = cv2.imdecode(np.frombuffer(png.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
    assert np.array_equal(lida > 0, resultado.mascara > 0)


def test_pipeline_com_matriz_em_outra_resolucao():
    seg = SAM2Segmentor(preditor=PreditorFalso())
    caixa = [X0 - 10, Y0 - 10, X0 + W + 10, Y0 + H + 10]
    resultado = analisar_ativo(seg, imagem_sintetica(), matriz_termica((ALTURA // 2, LARGURA // 2)), caixa)
    assert resultado.mascara_termica.shape == (ALTURA // 2, LARGURA // 2)
    assert resultado.termica.t_max == QUENTE_C and resultado.termica.t_min == PECA_C


# ---------------------------------------------------------------- integração com o SAM 2 real


def _sam2_disponivel() -> str | None:
    try:
        import sam2  # noqa: F401
        import torch  # noqa: F401
    except ImportError as erro:
        return f"dependência ausente: {erro.name}"
    if not caminho_checkpoint().is_file():
        return f"checkpoint ausente ({caminho_checkpoint()}); rode ferramentas/baixar_sam2.py"
    return None


MOTIVO_SEM_SAM2 = _sam2_disponivel()
requer_sam2 = pytest.mark.skipif(MOTIVO_SEM_SAM2 is not None, reason=MOTIVO_SEM_SAM2 or "")


@pytest.fixture(scope="module")
def sam2_real():
    return SAM2Segmentor()  # variante padrão, GPU se houver


@requer_sam2
def test_sam2_real_instancia_e_aloca_no_dispositivo(sam2_real):
    import torch

    from sam2.sam2_image_predictor import SAM2ImagePredictor

    assert isinstance(sam2_real.preditor, SAM2ImagePredictor)
    parametro = next(sam2_real.preditor.model.parameters())
    assert parametro.device.type == sam2_real.dispositivo.type
    if sam2_real.dispositivo.type == "cuda":
        assert torch.cuda.memory_allocated(sam2_real.dispositivo) > 0


@requer_sam2
def test_sam2_real_segmenta_retangulo_pela_caixa(sam2_real):
    sam2_real.set_frame(imagem_sintetica())
    segmentacao = sam2_real.segmentar([X0 - 12, Y0 - 12, X0 + W + 12, Y0 + H + 12])
    assert segmentacao.mascara.dtype == np.uint8 and segmentacao.mascara.shape == (ALTURA, LARGURA)
    assert iou(segmentacao.mascara, mascara_verdade()) > 0.95
    medidas = DimensionEstimator().analyze_contour(segmentacao.mascara)
    assert medidas["length_px"] == pytest.approx(W - 1, abs=4)
    assert medidas["width_px"] == pytest.approx(H - 1, abs=4)
    assert medidas["pixel_count"] == pytest.approx(W * H, rel=0.05)


@requer_sam2
def test_sam2_real_pipeline_termico(sam2_real):
    caixa = [X0 - 10, Y0 - 25, X0 + W + 10, Y0 + H + 10]
    resultado = analisar_ativo(sam2_real, imagem_sintetica(), matriz_termica(), caixa, metric_ratio=2.0)
    assert resultado.termica.t_max == QUENTE_C
    assert resultado.termica.t_med == pytest.approx(PECA_C, abs=1.0)
    assert resultado.geometria["length_metric"] == pytest.approx((W - 1) * 2.0, abs=8)
