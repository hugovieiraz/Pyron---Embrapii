"""Achar o termograma numa foto comum: aceita a paleta, recusa a sala."""

from __future__ import annotations

import numpy as np

from nucleo import enquadrar
from testes.test_paleta import _cena, _imagem_sintetica


def _sala(altura: int = 1280, largura: int = 720) -> np.ndarray:
    """Parede bege com degradê, um móvel marrom e um objeto azul: cores de casa, apagadas ou de uma matiz só."""
    yy = np.linspace(0, 1, altura)[:, None, None]
    sala = (np.array([205, 196, 180]) * (0.75 + 0.25 * yy)).repeat(largura, axis=1).astype(np.uint8)
    sala[1000:1200, 100:600] = (120, 78, 45)  # móvel de madeira
    sala[300:420, 450:620] = (30, 70, 200)  # objeto azul
    return sala


def test_termograma_inteiro_e_aceito() -> None:
    area = enquadrar.achar_termograma(_imagem_sintetica(50.0, 10.0, _cena()))
    assert area is not None and area.matizes >= enquadrar.MATIZES_MIN


def test_sala_sem_termograma_e_recusada() -> None:
    assert enquadrar.achar_termograma(_sala()) is None


def test_termograma_na_sala_e_recortado() -> None:
    """A moldura do monitor separa o termograma do resto (um objeto de cor forte encostado nele entraria junto)."""
    foto = _sala()
    foto[380:900, 20:700] = (25, 25, 28)  # moldura do monitor
    foto[400:880, 40:680] = _imagem_sintetica(50.0, 10.0, _cena())
    area = enquadrar.achar_termograma(foto)
    assert area is not None
    assert area.x0 <= 40 and area.y0 <= 400 and area.x1 >= 680 and area.y1 >= 880
    assert area.y0 > 200 and area.y1 < 1000  # a parede e o móvel ficam de fora
