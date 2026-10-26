"""Cenas sintéticas para testar a medição sem modelo: câmera pinhole conhecida, objetos com medida exata.

Cada cena devolve o mesmo que o MoGe-2 devolveria (``pontos`` H × W × 3 em metros, referencial da câmera
com y para baixo) e as máscaras dos objetos. Usada pelos testes e por ``ml/avaliar_medicao.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


def rotacao(eixo: str, graus: float) -> np.ndarray:
    a = math.radians(graus)
    c, s = math.cos(a), math.sin(a)
    if eixo == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=float)
    if eixo == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=float)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)


@dataclass
class Objeto:
    """Caixa orientada: centro (m), rotação (colunas = eixos da caixa) e tamanhos (m) por eixo.
    Um retângulo plano é uma caixa de espessura zero."""

    nome: str
    centro: tuple[float, float, float]
    tamanhos: tuple[float, float, float]
    rotacao: np.ndarray = field(default_factory=lambda: np.eye(3))


@dataclass
class Cena:
    pontos: np.ndarray
    mascaras: dict[str, np.ndarray]
    focal: float
    objetos: dict[str, Objeto]


def _raios(largura: int, altura: int, focal: float) -> np.ndarray:
    xs = (np.arange(largura) + 0.5 - largura / 2) / focal
    ys = (np.arange(altura) + 0.5 - altura / 2) / focal
    gx, gy = np.meshgrid(xs, ys)
    return np.stack([gx, gy, np.ones_like(gx)], axis=-1)


def _t_caixa(raios: np.ndarray, obj: Objeto) -> np.ndarray:
    """Distância (em unidades do raio, isto é, profundidade z) até a caixa; inf onde não acerta."""
    r = obj.rotacao
    c = np.asarray(obj.centro, dtype=float)
    meio = np.asarray(obj.tamanhos, dtype=float) / 2
    o = r.T @ (-c)
    d = raios @ r  # cada raio no referencial da caixa
    with np.errstate(divide="ignore", invalid="ignore"):
        t1 = (-meio - o) / d
        t2 = (meio - o) / d
    tmin = np.minimum(t1, t2)
    tmax = np.maximum(t1, t2)
    # eixo de espessura zero (ou raio paralelo): trata o slab à parte
    for i in range(3):
        paralelo = np.abs(d[..., i]) < 1e-12
        dentro = np.abs(o[i]) <= meio[i]
        tmin[..., i] = np.where(paralelo, np.where(dentro, -np.inf, np.inf), tmin[..., i])
        tmax[..., i] = np.where(paralelo, np.where(dentro, np.inf, -np.inf), tmax[..., i])
    entra = tmin.max(axis=-1)
    sai = tmax.min(axis=-1)
    acerta = (entra <= sai + 1e-12) & (sai > 0)
    return np.where(acerta, np.where(entra > 0, entra, sai), np.inf)


def cena(
    objetos: list[Objeto],
    largura: int = 1000,
    altura: int = 800,
    focal: float = 900.0,
    fundo: float = 6.0,
    chao: float | None = None,
    ruido: float = 0.0,
    semente: int = 0,
) -> Cena:
    """Renderiza a cena. ``fundo``: parede em z = fundo; ``chao``: piso em y = chao (abaixo da câmera);
    ``ruido``: desvio relativo gaussiano da profundidade, por pixel."""
    raios = _raios(largura, altura, focal)
    t = np.full((altura, largura), float(fundo))
    rotulo = np.full((altura, largura), -1)
    if chao is not None:
        with np.errstate(divide="ignore", invalid="ignore"):
            tc = np.where(raios[..., 1] > 0, chao / raios[..., 1], np.inf)
        t = np.minimum(t, tc)
    for i, obj in enumerate(objetos):
        ti = _t_caixa(raios, obj)
        perto = ti < t
        t = np.where(perto, ti, t)
        rotulo = np.where(perto, i, rotulo)
    if ruido:
        t = t * (1 + ruido * np.random.default_rng(semente).standard_normal(t.shape))
    pontos = raios * t[..., None]
    mascaras = {obj.nome: rotulo == i for i, obj in enumerate(objetos)}
    return Cena(pontos=pontos, mascaras=mascaras, focal=focal, objetos={o.nome: o for o in objetos})


def cenas_padrao(ruido: float = 0.0) -> dict[str, tuple[Cena, str, dict[str, float]]]:
    """As cenas do roteiro (fase 1): nome → (cena, objeto, medidas reais em metros)."""
    porta = (2.10, 0.90)
    return {
        "porta de frente a 3 m": (
            cena([Objeto("porta", (0.0, 0.0, 3.0), (porta[1], porta[0], 0.0))], ruido=ruido, semente=1),
            "porta",
            {"comprimento": porta[0], "largura": porta[1]},
        ),
        "porta girada 30° a 3 m": (
            cena(
                [Objeto("porta", (0.0, 0.0, 3.0), (porta[1], porta[0], 0.0), rotacao("y", 30))],
                ruido=ruido,
                semente=2,
            ),
            "porta",
            {"comprimento": porta[0], "largura": porta[1]},
        ),
        "régua de 30 cm a 0,5 m": (
            cena(
                [Objeto("regua", (0.0, 0.0, 0.5), (0.30, 0.035, 0.0), rotacao("z", 10))],
                fundo=0.8,
                ruido=ruido,
                semente=3,
            ),
            "regua",
            {"comprimento": 0.30, "largura": 0.035},
        ),
        "armário em pé no chão a 4 m": (
            cena(
                [Objeto("armario", (0.2, 1.4 - 1.05, 4.0), (1.20, 2.10, 0.55), rotacao("y", 20))],
                chao=1.4,
                fundo=8.0,
                ruido=ruido,
                semente=4,
            ),
            "armario",
            {"altura": 2.10},
        ),
    }
