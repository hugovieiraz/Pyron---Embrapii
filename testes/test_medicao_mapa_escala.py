"""Mapa de escala por folha ChArUco (nucleo/medicao/mapa_escala.py), com fotos sintéticas de verdade exata."""

import math

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
if not hasattr(cv2, "aruco"):
    pytest.skip("OpenCV sem o módulo aruco", allow_module_level=True)

from PIL import Image  # noqa: E402

from nucleo.medicao import mapa_escala as M  # noqa: E402

NX, NY, Q = M.PADRAO["nx"], M.PADRAO["ny"], M.PADRAO["quadrado_mm"]


def _foto(W, H, f, rx, ry, dist_m, desfoque=0.8, ruido=2.0, jpeg=90):
    """Folha projetada por câmera pinhole conhecida, com desfoque, ruído e JPEG. Devolve a foto e a homografia
    verdadeira (mm da folha → px) e a pose."""
    mestre = M.tabuleiro().generateImage((NX * 250, NY * 250), marginSize=0)
    K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1]])
    R = cv2.Rodrigues(np.array([math.radians(rx), 0, 0]))[0] @ cv2.Rodrigues(np.array([0, math.radians(ry), 0]))[0]
    t = np.array([0, 0, dist_m * 1000.0])
    C = np.array([[1, 0, -NX * Q / 2], [0, 1, -NY * Q / 2], [0, 0, 1]])
    Hpl = K @ np.c_[R[:, 0], R[:, 1], t] @ C
    Hm = np.diag([2, 2, 1]) @ Hpl @ np.diag([0.1, 0.1, 1])
    im = cv2.warpPerspective(mestre, Hm, (2 * W, 2 * H), borderValue=140)
    im = cv2.resize(im, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32)
    rng = np.random.default_rng(0)
    im = np.clip(cv2.GaussianBlur(im, (0, 0), desfoque) + rng.normal(0, ruido, im.shape), 0, 255).astype(np.uint8)
    _, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, jpeg])
    return Image.fromarray(cv2.imdecode(buf, 0)).convert("RGB"), Hpl, R, t


def _px_cm_real(Hpl, c, dv):
    a = Hpl @ [c[0] - dv[0], c[1] - dv[1], 1]
    b = Hpl @ [c[0] + dv[0], c[1] + dv[1], 1]
    return np.linalg.norm(a[:2] / a[2] - b[:2] / b[2])


@pytest.mark.parametrize("W,H,f", [(1200, 1600, 1202), (3000, 4000, 3005), (640, 480, 520)])
def test_le_o_tamanho_da_imagem_e_mapeia(W, H, f):
    dist = Q * f / (80 * 1000)  # quadrado de 80 px na foto
    img, Hpl, R, t = _foto(W, H, f, 30, 10, dist)
    m = M.mapear(img, focal_px=f)
    assert m.tamanho_imagem == [W, H]
    assert m.achou and m.n_cantos >= 20  # em 640 × 480 parte da folha sai do quadro
    Hi = np.linalg.inv(np.array(m.homografia))
    erros, erros_d = [], []
    for g in m.grade:
        c = Hi @ [g["x"], g["y"], 1]
        c = c[:2] / c[2]
        erros.append(g["px_cm_x"] / _px_cm_real(Hpl, c, (5, 0)) - 1)
        erros.append(g["px_cm_y"] / _px_cm_real(Hpl, c, (0, 5)) - 1)
        P = R @ [c[0] - NX * Q / 2, c[1] - NY * Q / 2, 0] + t
        erros_d.append(g["distancia_cm"] / (np.linalg.norm(P) / 10) - 1)
    assert np.median(np.abs(erros)) < 0.002  # 0,2 %
    assert np.median(np.abs(erros_d)) < 0.005  # distância de cada ponto


def test_medida_de_10_cm_no_plano_inclinado():
    f = 1202
    img, Hpl, _, _ = _foto(1200, 1600, f, 45, 25, 0.5, desfoque=1.5, ruido=5, jpeg=60)
    m = M.mapear(img, focal_px=f)
    assert m.achou
    for ang in np.linspace(0, math.pi, 7):
        c = np.array([NX * Q / 2, NY * Q / 2])
        d = 50 * np.array([math.cos(ang), math.sin(ang)])
        a = Hpl @ [*(c - d), 1]
        b = Hpl @ [*(c + d), 1]
        assert M.medir_no_plano(m, a[:2] / a[2], b[:2] / b[2]) == pytest.approx(10.0, rel=0.005)


def test_lente_pela_folha_inclinada_e_aviso_de_frente():
    f = 1202
    img, _, _, t = _foto(1200, 1600, f, 40, 15, 0.6)
    m = M.mapear(img)  # sem EXIF e sem focal: estima pela folha
    assert m.lente == "folha"
    assert m.focal_px == pytest.approx(f, rel=0.02)
    img, _, _, _ = _foto(1200, 1600, f, 0, 0, 0.6)
    assert "não é confiável" in M.mapear(img).aviso


def test_sem_folha_e_quadrado_pequeno():
    vazio = Image.fromarray(np.full((480, 640, 3), 128, np.uint8))
    m = M.mapear(vazio)
    assert not m.achou and m.tamanho_imagem == [640, 480]
    f = 1202
    img, _, _, _ = _foto(1200, 1600, f, 0, 0, Q * f / (40 * 1000))  # quadrado de 40 px
    m = M.mapear(img, focal_px=f)
    assert m.achou and "chegue mais perto" in m.aviso


def test_tamanho_do_quadrado():
    assert M.tamanho_quadrado_mm(1.0, 1200) == pytest.approx(50 * 1000 / 1200)
    assert M.distancia_maxima_m(25, 1202) == pytest.approx(0.601, abs=0.001)


def test_folha_para_imprimir_em_tamanho_real(tmp_path):
    M.gerar_folha(tmp_path / "folha.png")
    im = Image.open(tmp_path / "folha.png")
    assert (tmp_path / "folha.pdf").exists()
    assert im.size[0] / M.DPI * 25.4 < 210 and im.size[1] / M.DPI * 25.4 < 297  # cabe na A4
