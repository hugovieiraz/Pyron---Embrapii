"""Medir sem modelo nenhum: um retângulo de tamanho conhecido na foto (folha A4, cartão) define o plano.

Os 4 cantos clicados e o tamanho real dão a homografia imagem → plano (em cm); qualquer par de pontos no mesmo
plano vira uma distância real, mesmo com a foto inclinada (perspectiva). Só vale para o que está no plano do
retângulo (a parede da porta, o tampo da mesa); fora dele, a medida sai errada.

A incerteza vem de Monte Carlo: cada canto e cada ponta com erro de clique de 1 pixel (desvio padrão), e a
margem é o dobro do desvio das distâncias sorteadas.
"""

from __future__ import annotations

import math

import numpy as np

ERRO_CLIQUE_PX = 1.0
SORTEIOS = 400


def ordenar_cantos(cantos) -> np.ndarray:
    """Cantos em volta do centro, começando no de cima à esquerda, no sentido horário (na imagem, y para baixo)."""
    c = np.asarray(cantos, dtype=float)
    if c.shape != (4, 2):
        raise ValueError("são 4 cantos, cada um com x e y")
    centro = c.mean(axis=0)
    ang = np.arctan2(c[:, 1] - centro[1], c[:, 0] - centro[0])
    c = c[np.argsort(ang)]  # sentido horário na imagem
    inicio = int(np.argmin(c.sum(axis=1)))  # menor x + y: em cima à esquerda
    c = np.roll(c, -inicio, axis=0)
    # quadrilátero convexo e com área: senão os cliques não formam um retângulo visto em perspectiva
    lados = np.roll(c, -1, axis=0) - c
    cruz = lados[:, 0] * np.roll(lados, -1, axis=0)[:, 1] - lados[:, 1] * np.roll(lados, -1, axis=0)[:, 0]
    if not (np.all(cruz > 0) or np.all(cruz < 0)):
        raise ValueError("os 4 cantos não formam um quadrilátero convexo")
    if abs(cruz).min() < 1.0:
        raise ValueError("cantos alinhados ou repetidos")
    return c


def homografia(origem: np.ndarray, destino: np.ndarray) -> np.ndarray:
    """Homografia 3 × 3 de 4 pares de pontos (DLT com normalização)."""

    def normalizar(p):
        m = p.mean(axis=0)
        s = math.sqrt(2) / max(np.mean(np.linalg.norm(p - m, axis=1)), 1e-12)
        t = np.array([[s, 0, -s * m[0]], [0, s, -s * m[1]], [0, 0, 1]])
        return (np.c_[p, np.ones(len(p))] @ t.T)[:, :2], t

    a, ta = normalizar(np.asarray(origem, dtype=float))
    b, tb = normalizar(np.asarray(destino, dtype=float))
    linhas = []
    for (x, y), (u, v) in zip(a, b):
        linhas.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        linhas.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    h = np.linalg.svd(np.asarray(linhas))[2][-1].reshape(3, 3)
    h = np.linalg.inv(tb) @ h @ ta
    return h / h[2, 2]


def aplicar(h: np.ndarray, pontos) -> np.ndarray:
    p = np.c_[np.asarray(pontos, dtype=float).reshape(-1, 2), np.ones(len(np.asarray(pontos).reshape(-1, 2)))] @ h.T
    return p[:, :2] / p[:, 2:3]


def _retangulo(cantos_ord: np.ndarray, comprimento: float, largura: float) -> np.ndarray:
    """Cantos reais (cm) na mesma ordem dos da imagem: o lado maior real vai para o par de lados que aparece
    maior na foto."""
    lados = np.linalg.norm(np.roll(cantos_ord, -1, axis=0) - cantos_ord, axis=1)
    horizontal = (lados[0] + lados[2]) / 2  # lados 0-1 e 2-3
    vertical = (lados[1] + lados[3]) / 2
    w, h = (comprimento, largura) if horizontal >= vertical else (largura, comprimento)
    return np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=float)


def medir(cantos, tamanho_cm, pontos, erro_px: float = ERRO_CLIQUE_PX, semente: int = 0) -> dict:
    """Distância real (cm) entre dois pixels no plano do retângulo de referência.

    ``cantos``: 4 pixels (qualquer ordem); ``tamanho_cm``: (comprimento, largura) do retângulo; ``pontos``: os
    dois pixels a medir. Devolve distância, incerteza, a razão de aspecto que a foto sugere para o retângulo e
    se os pontos caem longe do retângulo (a medida piora longe dele).
    """
    comprimento, largura = sorted((float(tamanho_cm[0]), float(tamanho_cm[1])), reverse=True)
    if largura <= 0:
        raise ValueError("tamanho da referência com lado zero ou negativo")
    c = ordenar_cantos(cantos)
    real = _retangulo(c, comprimento, largura)
    p = np.asarray(pontos, dtype=float)
    if p.shape != (2, 2):
        raise ValueError("são 2 pontos para medir")
    h = homografia(c, real)
    a, b = aplicar(h, p)
    distancia = float(np.linalg.norm(b - a))

    rng = np.random.default_rng(semente)
    amostras = np.empty(SORTEIOS)
    for i in range(SORTEIOS):
        hc = homografia(c + rng.normal(0, erro_px, c.shape), real)
        aa, bb = aplicar(hc, p + rng.normal(0, erro_px, p.shape))
        amostras[i] = np.linalg.norm(bb - aa)
    incerteza = 2.0 * float(np.std(amostras))

    # pontos fora do retângulo: distância ao centro dele em múltiplos do lado maior (extrapolação)
    centro = real.mean(axis=0)
    longe = float(max(np.linalg.norm(a - centro), np.linalg.norm(b - centro)) / comprimento)
    return {
        "distancia_cm": round(distancia, 2),
        "incerteza_cm": round(incerteza, 2),
        "extrapolacao": round(longe, 2),
        "pontos_no_plano_cm": [[round(float(v), 2) for v in a], [round(float(v), 2) for v in b]],
        "metodo": "plano da referência (sem modelo)",
    }
