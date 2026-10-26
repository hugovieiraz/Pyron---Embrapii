"""Fase 2 da medição: adaptadores do MoGe-2 e do SAM 2.1.

Sem os pesos, os adaptadores rodam com modelos pequenos de pesos aleatórios (mesma arquitetura, nada
baixado): conferem formato, cache e tempos, não o acerto. Com os pesos em ``modelos/medicao/``, o teste
de ponta a ponta mede a régua do gabarito de verdade.
"""

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")

from nucleo.medicao import modelos  # noqa: E402

GABARITO = Path(__file__).parent / "gabarito"


def _foto(w=320, h=240):
    rng = np.random.default_rng(0)
    img = (rng.random((h, w, 3)) * 255).astype(np.uint8)
    img[60:180, 100:220] = (40, 90, 200)
    return Image.fromarray(img)


def _moge_pequeno():
    pytest.importorskip("moge")
    from moge.model.v2 import MoGeModel

    torch.manual_seed(0)
    cab = lambda saida: {  # noqa: E731
        "dim_in": [64, 32, 16, 8, 8],
        "dim_out": [None, None, None, None, saida],
        "dim_res_blocks": [64, 32, 16, 8, 8],
        "num_res_blocks": [0, 1, 1, 1, 0],
        "res_block_in_norm": "none",
        "res_block_hidden_norm": "none",
        "resamplers": ["conv_transpose", "conv_transpose", "conv_transpose", "bilinear"],
    }
    return MoGeModel(
        encoder={"backbone": "dinov2_vits14", "intermediate_layers": [2, 5, 8, 11], "dim_out": 64},
        neck={**cab(None), "dim_in": [66, 2, 2, 2, 2], "dim_out": None},
        points_head=cab(3),
        mask_head=cab(1),
        scale_head={"dims": [384, 64, 1]},
        remap_output="exp",
    ).eval()


def _sam_pequeno():
    from transformers import Sam2Config, Sam2ImageProcessor, Sam2Model, Sam2Processor

    torch.manual_seed(0)
    return Sam2Model(Sam2Config()).eval(), Sam2Processor(image_processor=Sam2ImageProcessor())


def test_profundidade_formato_e_lente_estimada():
    from nucleo.medicao.profundidade import Profundidade

    p = Profundidade("vits", dispositivo="cpu", num_tokens=300)
    p._modelo = _moge_pequeno()
    g = p.estimar(_foto())
    assert g.pontos.shape == (240, 320, 3)
    assert g.validos.shape == (240, 320) and g.validos.dtype == bool
    assert np.isfinite(g.focal_px)  # pesos aleatórios: só o formato
    assert g.lente == "estimada"
    assert g.tempo_ms > 0


def test_lente_do_exif():
    from nucleo.medicao.profundidade import abrir, fov_do_exif

    img = _foto(400, 300)
    exif = Image.Exif()
    exif.get_ifd(0x8769)[0xA405] = 26  # 26 mm equivalentes: lente principal típica de celular
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    fov = fov_do_exif(abrir(buf.getvalue()))
    # f_px = 26 · 500 / 43,27 = 300,4 px → fov = 2·atan(200 / 300,4) = 67,3°
    assert fov == pytest.approx(67.3, abs=0.2)
    assert fov_do_exif(abrir(_foto())) is None


def test_segmentador_ponto_caixa_e_cache():
    from nucleo.medicao.segmentar import Segmentador

    s = Segmentador(dispositivo="cpu")
    s._modelo, s._processador = _sam_pequeno()
    img = _foto()
    m, nota = s.mascara_por_ponto(img, (160, 120), chave="foto")
    assert m.shape == (240, 320) and m.dtype == bool
    assert isinstance(nota, float)
    assert s.tempos_ms["codificador"] > 0
    m, _ = s.mascara_por_caixa(img, (100, 60, 220, 180), chave="foto")
    assert m.shape == (240, 320)
    assert s.tempos_ms["codificador"] == 0.0  # mesma foto: codificador do cache
    m, _ = s.mascara_por_ponto(img, (160, 120), negativos=[(5, 5)], chave="foto")
    assert m.shape == (240, 320)


def test_estado_sem_pesos(tmp_path, monkeypatch):
    monkeypatch.setenv("PYRON_MODELOS_MEDICAO", str(tmp_path))
    e = modelos.estado()
    assert e["pronto"] is False
    assert e["dispositivo"] in ("cpu", "cuda")
    assert modelos.caminho_moge("vitl") == tmp_path / "moge-2-vitl-normal" / "model.pt"


@pytest.mark.skipif(not modelos.estado()["pronto"], reason="pesos da medição não instalados")
def test_regua_do_gabarito_de_ponta_a_ponta():
    """Com os pesos: a régua de 30 cm do gabarito, pela caixa. Só confere que a foto passa de ponta a ponta e que o
    contorno é o da régua (comprida e fina); o acerto da escala fica no relatório de ml/avaliar_medicao.py (nesta
    foto, de perto e sem nada em volta, o MoGe-2 erra a escala várias vezes)."""
    import json

    from nucleo.medicao import Medidor
    from nucleo.medicao.profundidade import Profundidade
    from nucleo.medicao.segmentar import Segmentador

    variante = next(v for v in ("vitb", "vits", "vitl") if modelos.caminho_moge(v).exists())
    sam = next(v for v in modelos.SAM if modelos.sam_instalado(v))
    pistas = json.loads((GABARITO / "pistas.json").read_text(encoding="utf-8"))
    m = Medidor(Profundidade(variante, num_tokens=1200), Segmentador(sam)).medir(
        GABARITO / "regua_30cm.jpg", {"caixa": pistas["regua_30cm.jpg"]["caixa"]}
    )
    assert m.forma == "plano"
    assert m.comprimento_cm > 5 * m.largura_cm  # régua de 30 × 3,5 cm: comprida e fina
    assert m.tempos_ms["total"] > 0


def test_lente_do_exif_em_foto_cortada_do_sensor_4_3():
    """Galaxy S23 grava 1848 × 4000 (19,5:9) cortando o sensor 4:3 e mantém o equivalente do quadro inteiro:
    23 mm → f = 23 · 5000 / 43,27 = 2658 px (o mesmo que 5,4 mm com pixel de 2,04 µm)."""
    import math

    from nucleo.medicao.profundidade import abrir, fov_do_exif

    img = Image.new("RGB", (1848, 4000), (90, 120, 200))
    exif = Image.Exif()
    exif.get_ifd(0x8769)[0xA405] = 23
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    fov = fov_do_exif(abrir(buf.getvalue()))
    f_px = 1848 / (2 * math.tan(math.radians(fov) / 2))
    assert f_px == pytest.approx(23 * 5000 / 43.267, rel=1e-3)
