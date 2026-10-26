"""Fase 1 da medição em foto comum: geometria pura nas cenas sintéticas (docs/07_roteiro_medicao_geral.md)."""

import numpy as np
import pytest

from nucleo.medicao import geometria as g
from nucleo.medicao import sintetico as s

LIMITE_SEM_RUIDO = 0.005  # erro relativo máximo (0,5 %) nas cenas sem ruído


def _medir(cena, objeto, real):
    m = cena.mascaras[objeto]
    if "altura" in real:
        return {"altura": g.altura(cena.pontos, m)}
    pl = g.plano(cena.pontos, m)
    return {"comprimento": pl.comprimento, "largura": pl.largura}


@pytest.fixture(scope="module")
def cenas_limpas():
    return s.cenas_padrao(ruido=0.0)


@pytest.fixture(scope="module")
def cenas_ruido():
    return s.cenas_padrao(ruido=0.01)


@pytest.mark.parametrize(
    "nome", ["porta de frente a 3 m", "porta girada 30° a 3 m", "régua de 30 cm a 0,5 m", "armário em pé no chão a 4 m"]
)
def test_erro_abaixo_de_meio_por_cento_sem_ruido(cenas_limpas, nome):
    cena, objeto, real = cenas_limpas[nome]
    medidas = _medir(cena, objeto, real)
    for chave, valor in real.items():
        erro = abs(medidas[chave].valor - valor) / valor
        assert erro < LIMITE_SEM_RUIDO, f"{nome} {chave}: {medidas[chave].valor:.4f} m (real {valor} m)"


@pytest.mark.parametrize(
    "nome", ["porta de frente a 3 m", "porta girada 30° a 3 m", "régua de 30 cm a 0,5 m", "armário em pé no chão a 4 m"]
)
def test_incerteza_cobre_o_erro_com_ruido(cenas_ruido, nome):
    cena, objeto, real = cenas_ruido[nome]
    medidas = _medir(cena, objeto, real)
    for chave, valor in real.items():
        m = medidas[chave]
        assert abs(m.valor - valor) <= m.incerteza(), f"{nome} {chave}: erro {m.valor - valor:+.4f} > ±{m.incerteza():.4f}"


def test_incerteza_cresce_com_o_ruido(cenas_limpas, cenas_ruido):
    nome = "porta de frente a 3 m"
    limpa = _medir(*cenas_limpas[nome])["comprimento"].incerteza()
    ruido = _medir(*cenas_ruido[nome])["comprimento"].incerteza()
    assert ruido > limpa


def test_extensoes_pca_numa_caixa():
    caixa = s.Objeto("caixa", (0.0, 0.0, 2.0), (0.60, 0.40, 0.0), s.rotacao("z", 25))
    cena = s.cena([caixa], fundo=4.0)
    ext = g.extensoes(cena.pontos, cena.mascaras["caixa"])
    assert ext.comprimento.valor == pytest.approx(0.60, rel=LIMITE_SEM_RUIDO)
    assert ext.largura.valor == pytest.approx(0.40, rel=LIMITE_SEM_RUIDO)
    assert ext.espessura.valor < 0.01


def test_plano_reconhece_objeto_plano(cenas_limpas):
    cena, objeto, _ = cenas_limpas["porta girada 30° a 3 m"]
    pl = g.plano(cena.pontos, cena.mascaras[objeto])
    ext = g.extensoes(cena.pontos, cena.mascaras[objeto])
    assert pl.fracao_dentro > 0.99
    assert g.eh_plano(pl, ext)
    # normal da porta girada 30° em torno do eixo vertical, apontando para a câmera
    assert pl.normal @ np.array([0.0, 0.0, -1.0]) == pytest.approx(np.cos(np.radians(30)), abs=1e-3)


def test_armario_nao_e_plano_e_acha_o_chao(cenas_limpas):
    cena, objeto, _ = cenas_limpas["armário em pé no chão a 4 m"]
    m = cena.mascaras[objeto]
    para_cima, origem = g.vertical(cena.pontos, m)
    assert origem == "apoio"
    assert para_cima @ np.array([0.0, -1.0, 0.0]) == pytest.approx(1.0, abs=1e-3)
    assert not g.eh_plano(g.plano(cena.pontos, m), g.extensoes(cena.pontos, m))


def test_vertical_sem_apoio_usa_a_camera(cenas_limpas):
    cena, objeto, _ = cenas_limpas["régua de 30 cm a 0,5 m"]
    m = cena.mascaras[objeto]
    # tudo abaixo da régua é a parede do fundo (vertical): não serve de apoio
    para_cima, origem = g.vertical(cena.pontos, m)
    assert origem == "câmera"
    assert list(para_cima) == [0.0, -1.0, 0.0]


def test_distancia_entre_dois_pixels():
    porta = s.Objeto("porta", (0.0, 0.0, 3.0), (0.90, 2.10, 0.0))
    cena = s.cena([porta], largura=1000, altura=800, focal=900.0)
    # pixels das bordas de cima e de baixo, no meio da porta (2,10 m a 3 m com focal 900 = 630 px)
    topo = (500, 400 - 315 + 3)
    base = (500, 400 + 315 - 3)
    d = g.distancia(cena.pontos, topo, base)
    esperado = (630 - 6) * 3.0 / 900.0
    assert d.valor == pytest.approx(esperado, rel=1e-3)
    assert d.incerteza() > 0


def test_distancia_fora_da_imagem():
    cena = s.cena([s.Objeto("p", (0.0, 0.0, 1.0), (0.2, 0.2, 0.0))], largura=100, altura=80, focal=100.0)
    with pytest.raises(ValueError):
        g.distancia(cena.pontos, (-5, 10), (50, 40))


def test_corrigir_escala():
    medidas, fator = g.corrigir_escala({"altura": 2.0, "largura": 1.0, "espessura": None}, 0.33, 0.30)
    assert fator == pytest.approx(0.30 / 0.33)
    assert medidas["altura"] == pytest.approx(2.0 * 0.30 / 0.33)
    assert medidas["espessura"] is None
    with pytest.raises(ValueError):
        g.corrigir_escala({"altura": 1.0}, 0.0, 0.3)


def test_escala_errada_da_cena_e_corrigida_pela_referencia():
    """Cena inteira 8 % maior (o que um modelo de profundidade faz): a régua corrige a porta."""
    porta = s.Objeto("porta", (-0.6, 0.0, 3.0), (0.90, 2.10, 0.0))
    regua = s.Objeto("regua", (0.5, 0.3, 2.9), (0.30, 0.035, 0.0))
    cena = s.cena([porta, regua])
    pontos = cena.pontos * 1.08
    alt_porta = g.plano(pontos, cena.mascaras["porta"]).comprimento.valor
    ref = g.plano(pontos, cena.mascaras["regua"]).comprimento.valor
    corrigida, _ = g.corrigir_escala({"porta": alt_porta}, ref, 0.30)
    assert alt_porta == pytest.approx(2.10 * 1.08, rel=0.005)
    assert corrigida["porta"] == pytest.approx(2.10, rel=0.01)


def test_incerteza_com_erro_de_escala():
    assert g.incerteza(2.0, 0.003, 0.0, erro_escala=0.1) == pytest.approx(0.006 + 0.2)


def test_poucos_pontos():
    pontos = np.zeros((10, 10, 3))
    mascara = np.zeros((10, 10), dtype=bool)
    mascara[0, :5] = True
    with pytest.raises(ValueError):
        g.extensoes(pontos, mascara)
    with pytest.raises(ValueError):
        g.plano(pontos, mascara)
