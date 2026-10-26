"""Referência achada sozinha (post-it rosa) e medida pelo plano dela, sem profundidade."""

import numpy as np
import pytest
from PIL import Image

cv2 = pytest.importorskip("cv2")

from nucleo.medicao import Medidor, referencia_auto  # noqa: E402
from nucleo.medicao import sintetico as s  # noqa: E402

ROSA = (236, 64, 150)  # post-it rosa: H ≈ 165 no HSV do OpenCV
F, W, H = 900.0, 1000, 800


def _foto_com_postit(cantos, fundo=(120, 100, 80)):
    rng = np.random.default_rng(0)
    img = np.clip(np.array(fundo) + rng.normal(0, 12, (H, W, 3)), 0, 255).astype(np.uint8)
    cv2.rectangle(img, (600, 100), (800, 300), (190, 60, 40), -1)  # vermelho: não pode ser confundido
    cv2.circle(img, (150, 650), 60, (225, 180, 160), -1)             # tom de pele
    cv2.fillConvexPoly(img, np.round(np.asarray(cantos)).astype(np.int32), ROSA)
    return Image.fromarray(img)


def test_acha_o_postit_inclinado():
    cantos = np.array([[400.3, 300.2], [520.7, 318.4], [505.1, 431.6], [388.2, 410.9]])
    a = referencia_auto.achar(_foto_com_postit(cantos))
    assert a is not None
    assert np.max(np.linalg.norm(a.cantos - cantos, axis=1)) < 2.0
    assert a.retangularidade > 0.95


def test_sem_postit_devolve_nada():
    assert referencia_auto.achar(_foto_com_postit(np.zeros((4, 2)) + 1)) is None


def _px(x, y, z):
    return (x / z * F + W / 2, y / z * F + H / 2)


def _cena(z, tamanho):
    """Objeto plano (tamanho em m) e post-it de 7,6 cm colados na mesma parede, girada 25°, a ``z`` m."""
    rot = s.rotacao("y", 25)
    c0 = np.array([-0.15, 0.0, z])
    obj = s.Objeto("quadro", tuple(c0), (*tamanho, 0.0), rot)
    postit = s.Objeto("postit", tuple(c0 + rot @ np.array([tamanho[0] / 2 + 0.1, -0.2, -0.001])), (0.076, 0.076, 0.0), rot)
    return s.cena([obj, postit], largura=W, altura=H, focal=F)


def _medir(cena, escala=1.10, referencia=None, checar=False):
    """``checar=False``: a conta da escala sem a regra que ignora post-it pequeno (aqui ele tem ≈ 25 a 69 px)."""
    med = Medidor(s.ProfundidadeSintetica(cena, escala), s.SegmentadorSintetico(cena))
    ys, xs = np.nonzero(cena.mascaras["quadro"])
    pista = {"ponto": (float(np.median(xs)), float(np.median(ys)))}
    return med.medir(s.imagem_da_cena(cena, {"postit": ROSA}), pista, referencia, checar_referencia=checar)


def test_postit_corrige_a_escala_da_profundidade():
    """Quadro de 60 × 40 cm a 1,2 m, profundidade 10 % maior: o post-it (≈ 69 px) corrige."""
    cena = _cena(1.2, (0.40, 0.60))
    assert _medir(cena).comprimento_cm == pytest.approx(60 * 1.10, rel=0.01)
    com = _medir(cena, referencia={"auto": "postit_rosa", "tamanho_cm": 7.6})  # o post-it da cena tem 7,6 cm
    assert com.metodo == "referência: post-it rosa (7,6 cm)"
    assert com.comprimento_cm == pytest.approx(60, rel=0.03)
    assert com.largura_cm == pytest.approx(40, rel=0.03)
    assert abs(com.comprimento_cm - 60) <= com.incerteza_cm["comprimento"]
    assert com.contorno_referencia
    # só pelo plano do post-it (sem profundidade): o centro acerta, mas a margem é larga (referência 8× menor)
    p = com.no_plano_da_referencia
    assert p["comprimento_cm"] == pytest.approx(60, rel=0.05)
    assert abs(p["comprimento_cm"] - 60) <= p["incerteza_cm"]["comprimento"]
    assert p["incerteza_cm"]["comprimento"] > com.incerteza_cm["comprimento"]


def test_porta_longe_com_postit_pequeno():
    """Porta de 2,10 m a 3 m numa imagem de 1000 px: o post-it tem só ≈ 25 px e meio pixel já é 2 % da escala.
    Pela profundidade ainda dá, com a margem cobrindo o erro; só pelo plano dele, não (na foto do celular, com
    4000 px, o mesmo post-it a 3 m tem ≈ 70 px)."""
    com = _medir(_cena(3.0, (0.90, 2.10)), referencia={"auto": "postit_rosa", "tamanho_cm": 7.6})
    assert com.comprimento_cm == pytest.approx(210, rel=0.08)
    assert abs(com.comprimento_cm - 210) <= com.incerteza_cm["comprimento"]
    p = com.no_plano_da_referencia
    assert p["incerteza_cm"]["comprimento"] > 0.5 * p["comprimento_cm"]  # a margem avisa que não serve


def test_referencia_auto_que_nao_esta_na_foto():
    cena = _cena(1.2, (0.40, 0.60))
    med = Medidor(s.ProfundidadeSintetica(cena), s.SegmentadorSintetico(cena))
    ys, xs = np.nonzero(cena.mascaras["quadro"])
    with pytest.raises(ValueError, match="não achei"):
        med.medir(s.imagem_da_cena(cena), {"ponto": (float(np.median(xs)), float(np.median(ys)))}, {"auto": "postit_rosa"})


def test_referencia_retangular_por_cantos():
    """A4 (29,7 × 21) colada na parede ao lado do quadro, marcada pelos 4 cantos: cada lado com o seu."""
    rot = s.rotacao("y", 25)
    c0 = np.array([-0.15, 0.0, 1.2])
    quadro = s.Objeto("quadro", tuple(c0), (0.40, 0.60, 0.0), rot)
    a4c = c0 + rot @ np.array([0.40, -0.1, -0.001])
    a4 = s.Objeto("a4", tuple(a4c), (0.21, 0.297, 0.0), rot)
    cena = s.cena([quadro, a4], largura=W, altura=H, focal=F)
    cantos = [_px(*(a4c + rot @ np.array([u, v, 0.0]))) for u, v in ((-0.105, -0.1485), (0.105, -0.1485), (0.105, 0.1485), (-0.105, 0.1485))]
    ref = {"cantos": [list(c) for c in cantos], "tamanho_cm": 29.7, "outro_lado_cm": 21.0, "nome": "folha A4"}
    com = _medir(cena, referencia=ref)
    assert com.comprimento_cm == pytest.approx(60, rel=0.02)
    assert com.no_plano_da_referencia["comprimento_cm"] == pytest.approx(60, rel=0.02)


def test_regra_ignora_postit_pequeno_e_avisa():
    """Post-it de ≈ 69 px (menos que 100): a medida sai sem referência, com o motivo."""
    com = _medir(_cena(1.2, (0.40, 0.60)), referencia={"auto": "postit_rosa", "tamanho_cm": 7.6}, checar=True)
    assert com.metodo == "sem referência"
    assert "px de lado" in com.referencia_ignorada
    assert com.comprimento_cm == pytest.approx(60 * 1.10, rel=0.01)  # a escala do modelo, sem correção
    assert com.no_plano_da_referencia == {}


def test_regra_ignora_referencia_em_outra_profundidade():
    """Quadro a 1,2 m e post-it grande colado numa parede a 2,4 m: 100 % mais longe que o objeto."""
    rot = s.rotacao("y", 0)
    quadro = s.Objeto("quadro", (-0.2, 0.0, 1.2), (0.40, 0.60, 0.0), rot)
    postit = s.Objeto("postit", (0.5, -0.1, 2.4), (0.30, 0.30, 0.0), rot)  # post-it grande: passa no tamanho
    cena = s.cena([quadro, postit], largura=W, altura=H, focal=F, fundo=3.0)
    com = _medir(cena, referencia={"auto": "postit_rosa", "tamanho_cm": 30}, checar=True)
    assert "mais longe que o objeto" in com.referencia_ignorada
    assert com.metodo == "sem referência"
    ok = _medir(cena, referencia={"auto": "postit_rosa", "tamanho_cm": 30}, checar=False)
    assert ok.metodo.startswith("referência")
