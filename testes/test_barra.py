"""Barra de cores em qualquer termograma (a do quadro do celular): achar, ler os números e converter."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from nucleo import barra
from testes.test_paleta import _cena, _imagem_sintetica


def _girada(img: np.ndarray, graus: float, fundo=(40, 36, 32)) -> tuple[np.ndarray, np.ndarray]:
    """A imagem girada no meio de uma tela maior, e a matriz que leva pontos da original para ela."""
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), graus, 1.0)
    m[:, 2] += (60, 40)
    return cv2.warpAffine(img, m, (w + 120, h + 80), flags=cv2.INTER_LINEAR, borderValue=fundo), m


def _levar(m: np.ndarray, x: float, y: float) -> np.ndarray:
    return m @ np.array([x, y, 1.0])


def test_acha_a_barra_inclinada_fora_do_lugar_de_fabrica() -> None:
    img, m = _girada(_imagem_sintetica(50.0, 10.0, _cena()), 2.0)
    achada = barra.achar(img)
    assert achada is not None
    # interior da barra na original: x 20..27, y 122..415
    topo, base = _levar(m, 23.5, 122), _levar(m, 23.5, 415)
    assert np.hypot(*(achada.p0 - topo)) < 4 and np.hypot(*(achada.p1 - base)) < 4
    assert achada.cores[0, 0] > achada.cores[-1, 0]  # p0 é o topo, o lado claro (quente)


def test_acha_a_barra_horizontal() -> None:
    img = np.ascontiguousarray(_imagem_sintetica(50.0, 10.0, _cena()).transpose(1, 0, 2))
    achada = barra.achar(img)
    assert achada is not None
    assert abs(achada.p0[1] - 23.5) < 2 and abs(achada.p1[1] - 23.5) < 2
    assert abs(achada.p0[0] - 122) < 4 and abs(achada.p1[0] - 415) < 4


def test_nao_ve_barra_em_cena_com_listras_e_degrade() -> None:
    yy, xx = np.mgrid[0:480, 0:640]
    ceu = np.stack([40 + 150 * yy / 480, 80 + 60 * np.sin(xx / 90), 200 - 120 * yy / 480], -1)  # degradê largo
    aletas = ((yy // 12) % 2 == 0) & (np.abs(xx - 320) < 18)  # para-raio: listras que vão e voltam na cor
    ceu[aletas] = (250, 200, 40)
    ceu[(~aletas) & (np.abs(xx - 320) < 18)] = (220, 60, 30)
    ruido = np.random.default_rng(0).normal(0, 3, ceu.shape)
    assert barra.achar(np.clip(ceu + ruido, 0, 255).astype(np.uint8)) is None


def test_temperatura_pela_cor_mesmo_com_a_cor_puxada_pelo_celular() -> None:
    cena = _cena()
    img = _imagem_sintetica(50.0, 10.0, cena).astype(np.float32) / 255
    puxada = (np.clip(img ** 0.9 * np.float32([1.05, 1.0, 0.88]), 0, 1) * 255).astype(np.uint8)  # celular
    achada = barra.achar(puxada)
    escala = barra.montar_escala(achada, 50.0, 10.0)
    assert escala.t_max == 50.0 and escala.cores[0, 0] > escala.cores[-1, 0]
    caixa = (300, 100, 400, 300)
    t, acima = barra.maxima(barra.lab(puxada), escala, caixa)
    real = np.percentile(cena[100:300, 300:400], barra.PERCENTIL_MAXIMO)
    assert t == pytest.approx(real, abs=1.0) and not acima


class _OCRFalso:
    """Devolve, a cada chamada, o próximo resultado da lista (formato do RapidOCR)."""

    def __init__(self, *resultados):
        self.resultados = list(resultados)
        self.chamadas = 0

    def __call__(self, _img, **_opcoes):
        r = self.resultados[self.chamadas % len(self.resultados)]
        self.chamadas += 1
        return r, None


def _caixa(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def test_numero_mais_perto_da_ponta_vale_e_o_cadeado_sai() -> None:
    achada = barra.achar(_imagem_sintetica(50.0, 10.0, _cena()))
    (rx0, ry0, _, _), (sx0, sy0, _, _) = barra.regioes_rotulos(achada, (480, 640))
    p0 = achada.p0 - (rx0, ry0)
    longe = _caixa(p0[0] + 60, p0[1] - 80, p0[0] + 110, p0[1] - 60)  # "26.9°C", a leitura do ponto
    perto = _caixa(p0[0], p0[1] - 30, p0[0] + 40, p0[1] - 10)  # o máximo da escala
    ocr = _OCRFalso([(longe, "26.9°C", 0.99), (perto, "30.0", 0.95)], [(perto, "19.8", 0.99)])
    assert barra.ler_numeros(_imagem_sintetica(50.0, 10.0, _cena()), achada, ocr) == (30.0, 19.8)
    # "830.0": o cadeado da escala travada lido como "8"
    escala = barra.montar_escala(achada, 830.0, 19.8)
    assert (escala.t_max, escala.t_min) == (30.0, 19.8)
    assert barra.montar_escala(achada, 19.8, 30.0) is None  # números trocados: o claro é o quente


def test_leitor_ao_vivo_so_usa_leitura_repetida() -> None:
    img = _imagem_sintetica(50.0, 10.0, _cena())
    ocr = _OCRFalso([(_caixa(0, 0, 30, 15), "50.0", 0.9)], [(_caixa(0, 0, 30, 15), "10.0", 0.9)])
    leitor = barra.LeitorAoVivo(lambda: ocr)
    escala, achada, estado = leitor.ler(img)
    assert escala is None and achada is not None and estado == "lendo"  # uma leitura só ainda não vale
    escala, _, estado = leitor.ler(img)
    assert estado == "lida" and (escala.t_max, escala.t_min) == (50.0, 10.0)
    chamadas = ocr.chamadas
    leitor.ler(img)
    assert ocr.chamadas == chamadas  # mesmos números na tela: não lê de novo
    assert leitor.ler(np.full_like(img, 30)) == (None, None, "sem_barra")


def _png(img: np.ndarray) -> bytes:
    ok, dados = cv2.imencode(".png", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    return dados.tobytes()


def test_foto_com_a_barra_fora_do_leiaute_da_flir_vira_temperatura_estimada() -> None:
    from nucleo import entrada

    cena = _cena()
    img, m = _girada(_imagem_sintetica(50.0, 10.0, cena), 2.0)
    a = entrada.carregar(_png(img), ocr=None, limites=(10.0, 50.0))
    assert not a.radiometrica and a.metadados["barra_livre"] and a.metadados["escala_lida_c"] == [10.0, 50.0]
    x, y = _levar(m, 400, 240) / entrada.FATOR_ESTIMADA
    assert a.temperatura_c[int(y), int(x)] == pytest.approx(cena[240, 400], abs=1.5)

    # foto do celular: os números da barra lidos pelo OCR
    ocr = _OCRFalso([(_caixa(0, 0, 30, 15), "50.0", 0.9)], [(_caixa(0, 0, 30, 15), "10.0", 0.9)])
    b = entrada.carregar(_png(img), ocr=ocr, somente_imagem=True)
    assert b.tem_temperatura and "foto" in b.metadados["aviso"]
    sem = entrada.carregar(_png(np.full((480, 640, 3), 90, np.uint8)), ocr=ocr, somente_imagem=True)
    assert not sem.tem_temperatura and sem.metadados["aviso"] == entrada.AVISO_CELULAR


def test_barra_cortada_pela_beira_do_quadro_nao_vale() -> None:
    img = _imagem_sintetica(50.0, 10.0, _cena())
    assert barra.achar(img[200:, :]) is None  # o topo (o quente) ficou fora: a ponta de cima não é o máximo
    assert barra.achar(img) is not None
