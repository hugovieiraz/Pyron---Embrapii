"""Testes da inversão de paleta com imagens sintéticas de temperatura conhecida."""

from __future__ import annotations

import numpy as np
import pytest

from nucleo import paleta


def _paleta_arco_iris(n: int = 256) -> np.ndarray:
    """Paleta sintética parecida com a arco-íris da FLIR, do quente (claro) para o frio (escuro)."""
    nos = np.array(
        [[255, 250, 245], [240, 40, 60], [250, 150, 20], [240, 230, 20], [40, 200, 60], [20, 170, 230], [10, 60, 180], [0, 5, 60]],
        dtype=np.float64,
    )
    t = np.linspace(0, len(nos) - 1, n)
    i = np.clip(t.astype(int), 0, len(nos) - 2)
    f = (t - i)[:, None]
    return (nos[i] * (1 - f) + nos[i + 1] * f).round()


def _imagem_sintetica(t_max: float, t_min: float, cena: np.ndarray) -> np.ndarray:
    """640×480 no leiaute vertical da C5: barra com moldura branca à esquerda e a cena colorida."""
    cores = _paleta_arco_iris()
    n = len(cores)
    img = np.zeros((480, 640, 3), dtype=np.float64)
    img[:] = (0, 5, 60)
    # Barra: interior x 20..27, y 122..415; moldura branca em x 18, 19, 28, 29 e em y 120/121, 416/417.
    y0, y1 = 122, 415
    linhas = np.linspace(0, n - 1, y1 - y0 + 1).round().astype(int)
    img[y0 : y1 + 1, 20:28] = cores[linhas][:, None, :]
    img[120:418, [18, 19, 28, 29]] = 255
    img[[120, 121, 416, 417], 18:30] = 255
    # Cena: temperatura -> posição na barra pelo modelo de radiância -> cor.
    r_max, r_min = paleta._radiancia(t_max), paleta._radiancia(t_min)
    pos = np.clip((r_max - paleta._radiancia(cena)) / (r_max - r_min), 0, 1)
    img[:, 40:] = cores[(pos * (n - 1)).round().astype(int)][:, 40:]
    return img.astype(np.uint8)


def _cena() -> np.ndarray:
    yy, xx = np.mgrid[0:480, 0:640]
    return 15 + 30 * (xx / 640) + 5 * np.sin(yy / 40.0)  # 10 a 50 °C, suave


def test_lab_do_branco_e_do_preto() -> None:
    lab = paleta.rgb_para_lab(np.array([[255, 255, 255], [0, 0, 0]]))
    assert lab[0, 0] == pytest.approx(100, abs=0.1)
    assert lab[1, 0] == pytest.approx(0, abs=0.1)


def test_localiza_barra_vertical() -> None:
    img = _imagem_sintetica(50.0, 10.0, _cena())
    barra = paleta.localizar_barra(img)
    assert barra.orientacao == "V"
    assert barra.faixa == (20, 27)
    assert 120 <= barra.inicio <= 124 and 413 <= barra.fim <= 417


def test_cores_da_barra_vao_do_quente_para_o_frio() -> None:
    img = _imagem_sintetica(50.0, 10.0, _cena())
    cores = paleta.cores_da_barra(img, paleta.localizar_barra(img))
    lab = paleta.rgb_para_lab(cores)
    assert lab[0, 0] > lab[-1, 0]


@pytest.mark.parametrize("espaco", ["lab", "ab"])
def test_inversao_recupera_a_temperatura(espaco: str) -> None:
    cena = _cena()
    img = _imagem_sintetica(50.0, 10.0, cena)
    esc = paleta.escala(img, t_max=50.0, t_min=10.0)
    inv = paleta.inverter(img, esc, espaco=espaco, remover_finas=False)
    ok = inv.valido & (cena > 11) & (cena < 49)
    ok[:, :210] = False  # a máscara de sobreposição cobre essa faixa no leiaute vertical
    erro = np.abs(inv.temperatura_c[ok] - cena[ok])
    assert ok.sum() > 100_000
    assert np.median(erro) < 0.3


def test_modelo_linear_erra_mais_que_radiancia() -> None:
    cena = _cena()
    img = _imagem_sintetica(50.0, 10.0, cena)
    esc = paleta.escala(img, t_max=50.0, t_min=10.0)
    ok_base = np.zeros(cena.shape, bool)
    ok_base[:, 210:] = True
    erros = {}
    for modelo in ("radiancia", "linear"):
        inv = paleta.inverter(img, esc, modelo=modelo, remover_finas=False)
        ok = inv.valido & ok_base
        erros[modelo] = float(np.median(np.abs(inv.temperatura_c[ok] - cena[ok])))
    assert erros["radiancia"] < erros["linear"]


def test_estruturas_finas_sao_removidas_e_blocos_ficam() -> None:
    cena = np.full((480, 640), 20.0)
    cena[200:208, 300:308] = 48.0  # ponto quente de 8×8 pixels exibidos (2×2 do sensor)
    img = _imagem_sintetica(50.0, 10.0, cena)
    img[100, 250:600] = 255  # linha branca fina, como o retângulo de medição
    esc = paleta.escala(img, t_max=50.0, t_min=10.0)
    inv = paleta.inverter(img, esc)
    assert not inv.valido[100, 300:500].any()
    assert np.nanmax(inv.temperatura_c[200:208, 300:308]) == pytest.approx(48.0, abs=1.0)


def test_interpreta_numero_partido_pelo_ocr() -> None:
    caixa = lambda x: [[x, 0], [x + 10, 0], [x + 10, 10], [x, 10]]  # noqa: E731
    assert paleta._interpretar([(caixa(0), "B", 0.6), (caixa(20), "19.", 0.99), (caixa(40), ".4", 0.97)])[0] == 19.4
    assert paleta._interpretar([(caixa(0), "51.3", 0.94), (caixa(30), "3", 1.0)])[0] == 51.3
    assert paleta._interpretar([(caixa(0), "-19.5", 0.99)])[0] == -19.5
