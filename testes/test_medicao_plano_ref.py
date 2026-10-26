"""Medir sem modelo: retângulo de referência (A4) no mesmo plano do objeto, por homografia."""

import numpy as np
import pytest

from nucleo.medicao import plano_ref as pr
from nucleo.medicao import sintetico as s

F, W, H = 900.0, 1000, 800


def _projetar(pontos):
    p = np.asarray(pontos, dtype=float)
    return np.c_[F * p[:, 0] / p[:, 2] + W / 2, F * p[:, 1] / p[:, 2] + H / 2]


def _na_parede(u, v, rot, centro=(0.0, 0.0, 3.0)):
    """Ponto (u, v) metros no plano de uma parede girada ``rot`` graus em torno da vertical."""
    r = s.rotacao("y", rot)
    return np.asarray(centro) + r @ np.array([u, v, 0.0])


@pytest.mark.parametrize("rot", [0, 30, 55])
def test_porta_medida_pela_a4_na_mesma_parede(rot):
    # A4 em pé (29,7 de altura) colada na parede ao lado da porta; porta de 2,10 m
    a4 = [_na_parede(u, v, rot) for u, v in ((0.30, -0.10), (0.51, -0.10), (0.51, 0.197), (0.30, 0.197))]
    porta = [_na_parede(-0.45, -1.05, rot), _na_parede(-0.45, 1.05, rot)]
    r = pr.medir(_projetar(a4), (29.7, 21.0), _projetar(porta))
    assert r["distancia_cm"] == pytest.approx(210.0, rel=0.002)
    assert r["incerteza_cm"] > 0
    assert r["extrapolacao"] > 1  # a porta passa do tamanho da folha: medida extrapolada


def test_ordem_dos_cantos_nao_importa():
    a4 = _projetar([_na_parede(u, v, 20) for u, v in ((0, 0), (0.21, 0), (0.21, 0.297), (0, 0.297))])
    pontos = _projetar([_na_parede(0, 0, 20), _na_parede(0.21, 0.297, 20)])
    d1 = pr.medir(a4, (29.7, 21.0), pontos)["distancia_cm"]
    d2 = pr.medir(a4[[2, 0, 3, 1]], (21.0, 29.7), pontos)["distancia_cm"]
    assert d1 == pytest.approx(d2) == pytest.approx(np.hypot(21.0, 29.7), rel=1e-3)


def test_incerteza_cobre_o_erro_do_clique():
    rng = np.random.default_rng(3)
    a4 = _projetar([_na_parede(u, v, 35) for u, v in ((0.3, -0.1), (0.51, -0.1), (0.51, 0.197), (0.3, 0.197))])
    porta = _projetar([_na_parede(-0.45, -1.05, 35), _na_parede(-0.45, 1.05, 35)])
    cobertos = 0
    for _ in range(40):
        r = pr.medir(a4 + rng.normal(0, 1, a4.shape), (29.7, 21.0), porta + rng.normal(0, 1, porta.shape))
        cobertos += abs(r["distancia_cm"] - 210) <= r["incerteza_cm"]
    assert cobertos >= 36  # ~95 % (a margem é 2 desvios)


@pytest.mark.parametrize("cantos", [
    [[0, 0], [10, 0], [0, 10], [10, 10.5]],  # ordem cruzada ainda é convexa depois de ordenar
])
def test_cantos_em_qualquer_ordem_viram_convexo(cantos):
    assert pr.ordenar_cantos(cantos).shape == (4, 2)


@pytest.mark.parametrize("cantos", [
    [[0, 0], [10, 0], [20, 0], [30, 0]],  # alinhados
    [[0, 0], [10, 0], [10, 10]],          # só 3
])
def test_cantos_invalidos(cantos):
    with pytest.raises(ValueError):
        pr.medir(cantos, (29.7, 21.0), [[0, 0], [1, 1]])
