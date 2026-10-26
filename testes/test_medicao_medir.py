"""medir() de ponta a ponta com modelos falsos (cena sintética no lugar do MoGe-2 e do SAM 2)."""

import io

import pytest

from nucleo.medicao import Medidor, contorno
from nucleo.medicao import sintetico as s

FOCAL, W, H = 900.0, 1000, 800


def _px(x, y, z):
    return (x / z * FOCAL + W / 2, y / z * FOCAL + H / 2)


@pytest.fixture(scope="module")
def cena():
    porta = s.Objeto("porta", (-0.6, 0.0, 3.0), (0.90, 2.10, 0.0))
    regua = s.Objeto("regua", (0.5, 0.3, 2.9), (0.30, 0.035, 0.0))
    return s.cena([porta, regua], largura=W, altura=H, focal=FOCAL)


def _medidor(cena, escala=1.0):
    return Medidor(s.ProfundidadeSintetica(cena, escala), s.SegmentadorSintetico(cena))


def test_sem_referencia_mostra_a_escala_do_modelo(cena):
    m = _medidor(cena, 1.08).medir(s.imagem_da_cena(cena), {"ponto": _px(-0.6, 0.0, 3.0)})
    assert m.forma == "plano"
    assert m.comprimento_cm == pytest.approx(210 * 1.08, rel=0.005)
    assert m.largura_cm == pytest.approx(90 * 1.08, rel=0.005)
    assert m.metodo == "sem referência"
    # a incerteza sem referência inclui o erro de escala provisório do modelo
    assert m.incerteza_cm["comprimento"] > 0.08 * m.comprimento_cm
    assert m.contorno and len(m.contorno[0]) >= 4
    assert m.tamanho_imagem == [W, H]
    assert set(m.tempos_ms) >= {"profundidade", "contorno", "geometria", "total"}


def test_referencia_corrige_a_escala(cena):
    ref = {"ponto": _px(0.5, 0.3, 2.9), "tamanho_cm": 30.0, "nome": "régua"}
    m = _medidor(cena, 1.08).medir(s.imagem_da_cena(cena), {"ponto": _px(-0.6, 0.0, 3.0)}, ref)
    assert m.comprimento_cm == pytest.approx(210, rel=0.01)
    assert abs(m.comprimento_cm - 210) <= m.incerteza_cm["comprimento"]
    assert m.fator_escala == pytest.approx(1 / 1.08, rel=0.01)
    assert m.metodo.startswith("referência: régua")
    assert m.contorno_referencia and m.contorno


def test_caixa_e_dois_pontos(cena):
    med = _medidor(cena)
    img = s.imagem_da_cena(cena)
    x0, y0 = _px(-1.05, -1.05, 3.0)
    x1, y1 = _px(-0.15, 1.05, 3.0)
    m = med.medir(img, {"caixa": (x0, y0, x1, y1)})
    assert m.comprimento_cm == pytest.approx(210, rel=0.005)
    d = med.medir(img, {"pontos": (_px(-0.6, -1.0, 3.0), _px(-0.6, 1.0, 3.0))})
    assert d.forma == "distância"
    assert d.distancia_cm == pytest.approx(200, rel=0.01)
    assert d.contorno == []


def test_profundidade_vem_do_cache_na_mesma_foto(cena):
    med = _medidor(cena)
    img = s.imagem_da_cena(cena)
    med.medir(img, {"ponto": _px(-0.6, 0.0, 3.0)})
    m = med.medir(img, {"ponto": _px(0.5, 0.3, 2.9)})
    assert m.tempos_ms["profundidade"] == 0.0


def test_volume_tem_altura_pelo_chao():
    armario = s.Objeto("armario", (0.2, 0.35, 4.0), (1.20, 2.10, 0.55), s.rotacao("y", 20))
    c = s.cena([armario], chao=1.4, fundo=8.0, largura=W, altura=H, focal=FOCAL)
    m = _medidor(c).medir(s.imagem_da_cena(c), {"ponto": _px(0.2, 0.35, 4.0)})
    assert m.forma == "volume"
    assert m.vertical == "apoio"
    assert m.altura_cm == pytest.approx(210, rel=0.005)


def test_imagem_em_bytes(cena):
    buf = io.BytesIO()
    s.imagem_da_cena(cena).save(buf, format="PNG")
    m = _medidor(cena).medir(buf.getvalue(), {"ponto": _px(-0.6, 0.0, 3.0)})
    assert m.comprimento_cm == pytest.approx(210, rel=0.005)


def test_pista_errada(cena):
    with pytest.raises(ValueError):
        _medidor(cena).medir(s.imagem_da_cena(cena), {"nada": 1})
    with pytest.raises(ValueError):  # ponto no fundo: o falso não acha objeto
        _medidor(cena).medir(s.imagem_da_cena(cena), {"ponto": (5, 5)})


def test_contorno_de_um_retangulo():
    import numpy as np

    m = np.zeros((50, 60), dtype=bool)
    m[10:40, 5:50] = True
    poli = contorno(m)
    assert len(poli) == 1
    xs = [p[0] for p in poli[0]]
    ys = [p[1] for p in poli[0]]
    assert (min(xs), max(xs), min(ys), max(ys)) == (5, 49, 10, 39)
