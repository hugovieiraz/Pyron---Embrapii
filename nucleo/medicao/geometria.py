"""Geometria da medição em foto comum: só NumPy, sem modelo nenhum.

Entrada comum: ``pontos`` (H × W × 3, metros, no referencial da câmera: x para a direita, y para baixo,
z para a frente), como devolve o MoGe-2, e uma ``mascara`` (H × W, bool) com os pixels do objeto.

As pontas de cada medida saem de percentis (descartam pontas soltas) estendidos até a borda: com a
densidade de pontos uniforme perto da ponta, a borda fica em ``2·p(q) − p(2q)``. Depois soma-se meio
pixel de cada lado, porque o ponto de cada pixel está no centro dele e o objeto cobre o pixel inteiro.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# fração descartada em cada ponta (pontos soltos na borda da máscara)
FRACAO_PONTA = 0.02


@dataclass
class Extensao:
    """Uma medida ao longo de um eixo, em metros."""

    valor: float
    eixo: np.ndarray
    passo: float  # tamanho de 1 pixel ao longo do eixo, em metros (mediana no objeto)
    dispersao: float  # desvio robusto dos pontos ao longo do eixo (ruído local), em metros

    def incerteza(self, erro_escala: float = 0.0) -> float:
        return incerteza(self.valor, self.passo, self.dispersao, erro_escala)


@dataclass
class Plano:
    normal: np.ndarray
    centro: np.ndarray
    fracao_dentro: float  # fração dos pontos do objeto a menos de ``tolerancia`` do plano
    residuo: float  # desvio padrão da distância ao plano dos pontos de dentro, em metros
    tolerancia: float
    comprimento: Extensao | None = None
    largura: Extensao | None = None


@dataclass
class Extensoes:
    comprimento: Extensao
    largura: Extensao
    espessura: Extensao
    plano: Plano | None = None
    extras: dict = field(default_factory=dict)


def _validos(pontos: np.ndarray, mascara: np.ndarray) -> np.ndarray:
    return mascara & np.isfinite(pontos[..., 2])


def _passos_pixel(pontos: np.ndarray, mascara: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Vetores 3D de 1 pixel para a direita (dx) e para baixo (dy) em cada pixel do objeto."""
    ok = _validos(pontos, mascara)
    dx = np.full_like(pontos, np.nan)
    dy = np.full_like(pontos, np.nan)
    par_x = ok[:, 1:] & ok[:, :-1]
    par_y = ok[1:, :] & ok[:-1, :]
    dx[:, :-1][par_x] = (pontos[:, 1:] - pontos[:, :-1])[par_x]
    dy[:-1, :][par_y] = (pontos[1:, :] - pontos[:-1, :])[par_y]
    return dx[ok], dy[ok]


def _passo_ao_longo(dx: np.ndarray, dy: np.ndarray, eixo: np.ndarray) -> float:
    """Tamanho do pixel ao longo de ``eixo``: a projeção do paralelogramo (dx, dy) é |dx·e| + |dy·e|."""
    px = np.abs(dx @ eixo)
    py = np.abs(dy @ eixo)
    vx = np.nanmedian(px) if np.isfinite(px).any() else np.nan
    vy = np.nanmedian(py) if np.isfinite(py).any() else np.nan
    if not np.isfinite(vx) and not np.isfinite(vy):
        return 0.0
    return float(np.nansum([vx, vy]))


def _rugosidade(pontos: np.ndarray, mascara: np.ndarray, eixo: np.ndarray) -> float:
    """Ruído local ao longo do eixo: ponto menos a média dos 4 vizinhos, desvio robusto (MAD)."""
    ok = _validos(pontos, mascara)
    interior = ok.copy()
    interior[1:-1, 1:-1] &= ok[:-2, 1:-1] & ok[2:, 1:-1] & ok[1:-1, :-2] & ok[1:-1, 2:]
    interior[0, :] = interior[-1, :] = False
    interior[:, 0] = interior[:, -1] = False
    if interior.sum() < 10:
        return 0.0
    vizinhos = (pontos[:-2, 1:-1] + pontos[2:, 1:-1] + pontos[1:-1, :-2] + pontos[1:-1, 2:]) / 4.0
    residuo = (pontos[1:-1, 1:-1] - vizinhos)[interior[1:-1, 1:-1]] @ eixo
    mad = np.median(np.abs(residuo - np.median(residuo)))
    # ponto − média de 4 vizinhos independentes tem variância 1,25 σ²
    return float(1.4826 * mad / math.sqrt(1.25))


def _extensao_1d(coord: np.ndarray, q: float = FRACAO_PONTA) -> tuple[float, float]:
    """Pontas de uma distribuição 1D, estendidas até a borda (ver o cabeçalho do módulo)."""
    p_q, p_2q, p_hi2q, p_hiq = np.quantile(coord, [q, 2 * q, 1 - 2 * q, 1 - q])
    return float(2 * p_q - p_2q), float(2 * p_hiq - p_hi2q)


def _extensao_eixo(pontos: np.ndarray, mascara: np.ndarray, eixo: np.ndarray) -> Extensao:
    """Extensão ao longo de ``eixo``. Cada ponto é espalhado de forma uniforme (e fixa) sobre o próprio
    pixel antes dos percentis: sem isso, os valores repetidos por linha de pixels fazem o percentil andar
    em degraus e a ponta estimada erra até 1 pixel."""
    ok = _validos(pontos, mascara)
    dx, dy = _passos_pixel(pontos, mascara)
    coords = pontos[ok] @ eixo
    px, py = dx @ eixo, dy @ eixo
    px = np.where(np.isfinite(px), px, np.nanmedian(px) if np.isfinite(px).any() else 0.0)
    py = np.where(np.isfinite(py), py, np.nanmedian(py) if np.isfinite(py).any() else 0.0)
    u = np.random.default_rng(0).random((2, len(coords))) - 0.5
    lo, hi = _extensao_1d(coords + u[0] * px + u[1] * py)
    return Extensao(
        valor=hi - lo,
        eixo=eixo,
        passo=_passo_ao_longo(dx, dy, eixo),
        dispersao=_rugosidade(pontos, mascara, eixo),
    )


def incerteza(valor: float, passo: float, dispersao: float, erro_escala: float = 0.0) -> float:
    """Incerteza (metros) de uma medida: 1 pixel em cada ponta, o ruído dos pontos nas duas pontas e,
    se informado, o erro relativo da escala (do modelo ou da referência). Soma simples, conservadora."""
    return 2.0 * passo + 2.0 * 2.0 * dispersao + abs(erro_escala) * valor


def extensoes(pontos: np.ndarray, mascara: np.ndarray) -> Extensoes:
    """Comprimento, largura e espessura do objeto pelos eixos principais (PCA) dos pontos dele."""
    ok = _validos(pontos, mascara)
    p = pontos[ok]
    if len(p) < 20:
        raise ValueError("objeto com menos de 20 pontos válidos")
    centro = np.median(p, axis=0)
    q = p - centro
    _, _, vt = np.linalg.svd(q[:: max(1, len(q) // 50000)] - q.mean(axis=0), full_matrices=False)
    medidas = [_extensao_eixo(pontos, mascara, e) for e in vt]
    medidas.sort(key=lambda m: -m.valor)
    return Extensoes(*medidas)


def plano(
    pontos: np.ndarray,
    mascara: np.ndarray,
    tolerancia: float | None = None,
    iteracoes: int = 200,
    semente: int = 0,
) -> Plano:
    """Ajuste de plano por RANSAC simples (3 pontos por tentativa) e refinamento por mínimos quadrados.

    Também mede comprimento e largura dentro do plano pelo menor retângulo que envolve os pontos
    (calibre rotativo sobre a casca convexa), que acerta os lados mesmo em objeto quase quadrado.
    ``tolerancia`` padrão: 1 % da maior extensão ou 4 pixels, o que for maior.
    """
    ok = _validos(pontos, mascara)
    p = pontos[ok]
    if len(p) < 20:
        raise ValueError("objeto com menos de 20 pontos válidos")
    dx, dy = _passos_pixel(pontos, mascara)
    passo_medio = float(np.nanmedian(np.linalg.norm(np.concatenate([dx, dy]), axis=1)))
    if tolerancia is None:
        tamanho = float(np.linalg.norm(np.quantile(p, 0.98, axis=0) - np.quantile(p, 0.02, axis=0)))
        tolerancia = max(0.01 * tamanho, 4 * passo_medio)

    rng = np.random.default_rng(semente)
    amostra = p[rng.choice(len(p), size=min(len(p), 20000), replace=False)]
    melhor_n, melhor = -1, None
    for _ in range(iteracoes):
        a, b, c = amostra[rng.choice(len(amostra), 3, replace=False)]
        n = np.cross(b - a, c - a)
        norma = np.linalg.norm(n)
        if norma < 1e-12:
            continue
        n /= norma
        dentro = np.abs((amostra - a) @ n) < tolerancia
        if dentro.sum() > melhor_n:
            melhor_n, melhor = int(dentro.sum()), (n, a)
    n, a = melhor
    for _ in range(3):  # refino: SVD dos pontos de dentro
        dentro = np.abs((p - a) @ n) < tolerancia
        q = p[dentro]
        a = q.mean(axis=0)
        n = np.linalg.svd(q - a, full_matrices=False)[2][2]
    dist = (p - a) @ n
    dentro = np.abs(dist) < tolerancia
    if n[2] > 0:  # normal apontando para a câmera
        n = -n
    resultado = Plano(
        normal=n,
        centro=a,
        fracao_dentro=float(dentro.mean()),
        residuo=float(np.std(dist[dentro])),
        tolerancia=float(tolerancia),
    )

    # base do plano e retângulo mínimo
    u = np.linalg.svd(p[dentro] - a, full_matrices=False)[2][0]
    u -= (u @ n) * n
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    uv = np.stack([(p[dentro] - a) @ u, (p[dentro] - a) @ v], axis=1)
    melhor_area, melhor_ang = math.inf, 0.0
    for ang in _angulos_casca(uv):
        e1 = np.array([math.cos(ang), math.sin(ang)])
        e2 = np.array([-e1[1], e1[0]])
        l1 = _extensao_1d(uv @ e1)
        l2 = _extensao_1d(uv @ e2)
        area = (l1[1] - l1[0]) * (l2[1] - l2[0])
        if area < melhor_area:
            melhor_area, melhor_ang = area, ang
    e1_2d = np.array([math.cos(melhor_ang), math.sin(melhor_ang)])
    e2_2d = np.array([-e1_2d[1], e1_2d[0]])
    mascara_dentro = np.zeros_like(mascara)
    mascara_dentro[ok] = dentro
    lados = []
    for e2d in (e1_2d, e2_2d):
        eixo = e2d[0] * u + e2d[1] * v
        lados.append(_extensao_eixo(pontos, mascara_dentro, eixo))
    lados.sort(key=lambda m: -m.valor)
    resultado.comprimento, resultado.largura = lados
    return resultado


def projetar_no_plano(pontos: np.ndarray, mascara: np.ndarray, pl: Plano) -> np.ndarray:
    """Troca cada ponto da máscara pelo encontro do raio dele com o plano.

    O raio de um pixel é a direção do próprio ponto (a câmera fica na origem), então a borda do objeto,
    onde a profundidade estimada mistura objeto e fundo, cai no lugar certo do plano."""
    saida = pontos.copy()
    ok = _validos(pontos, mascara)
    p = pontos[ok]
    den = p @ pl.normal
    t = np.where(np.abs(den) > 1e-9, (pl.centro @ pl.normal) / den, np.nan)
    saida[ok] = p * t[:, None]
    return saida


def _angulos_casca(uv: np.ndarray, maximo: int = 180) -> np.ndarray:
    """Ângulos das arestas da casca convexa (candidatos a lado do retângulo mínimo)."""
    try:
        from scipy.spatial import ConvexHull

        sub = uv[:: max(1, len(uv) // 50000)]
        casca = sub[ConvexHull(sub).vertices]
        arestas = np.roll(casca, -1, axis=0) - casca
        ang = np.mod(np.arctan2(arestas[:, 1], arestas[:, 0]), math.pi / 2)
        ang = np.unique(np.round(ang, 3))
        if len(ang) > maximo:
            ang = ang[np.linspace(0, len(ang) - 1, maximo).astype(int)]
        return ang
    except Exception:
        return np.linspace(0, math.pi / 2, 90, endpoint=False)


def eh_plano(pl: Plano, ext: Extensoes) -> bool:
    """Objeto plano: quase todos os pontos no plano e espessura pequena perto do tamanho."""
    return pl.fracao_dentro >= 0.9 and ext.espessura.valor <= 0.15 * ext.comprimento.valor


def vertical(
    pontos: np.ndarray, mascara: np.ndarray, faixa: int = 40, minimo: int = 200
) -> tuple[np.ndarray, str]:
    """Direção "para cima" da cena (metros, referencial da câmera).

    Tenta o plano de apoio: a faixa de pixels logo abaixo do objeto (mesa ou chão). Sem apoio que
    se ajuste, usa o eixo vertical da câmera (−y), que vale para foto tirada com o celular em pé.
    Devolve o vetor e a origem ("apoio" ou "câmera").
    """
    camera = np.array([0.0, -1.0, 0.0])
    ys, xs = np.nonzero(mascara)
    if len(ys) == 0:
        return camera, "câmera"
    h, w = mascara.shape
    abaixo = np.zeros_like(mascara)
    for x in np.unique(xs):
        y_fim = ys[xs == x].max()
        abaixo[y_fim + 1 : min(h, y_fim + 1 + faixa), x] = True
    abaixo &= ~mascara
    if _validos(pontos, abaixo).sum() < minimo:
        return camera, "câmera"
    try:
        pl = plano(pontos, abaixo, iteracoes=100)
    except ValueError:
        return camera, "câmera"
    n = pl.normal if pl.normal @ camera >= 0 else -pl.normal
    # só aceita apoio razoavelmente horizontal em relação à câmera (até 60° do −y)
    if pl.fracao_dentro < 0.7 or n @ camera < 0.5:
        return camera, "câmera"
    return n, "apoio"


def altura(pontos: np.ndarray, mascara: np.ndarray, para_cima: np.ndarray | None = None) -> Extensao:
    """Extensão do objeto ao longo da vertical (``para_cima`` ou a de ``vertical()``)."""
    if para_cima is None:
        para_cima, _ = vertical(pontos, mascara)
    para_cima = np.asarray(para_cima, dtype=float)
    para_cima = para_cima / np.linalg.norm(para_cima)
    ok = _validos(pontos, mascara)
    p = pontos[ok]
    if len(p) < 20:
        raise ValueError("objeto com menos de 20 pontos válidos")
    return _extensao_eixo(pontos, mascara, para_cima)


def ponto_robusto(pontos: np.ndarray, pixel: tuple[float, float], raio: int = 2) -> np.ndarray:
    """Ponto 3D de um pixel (x, y): mediana da vizinhança (2·raio + 1)², só pontos válidos."""
    h, w = pontos.shape[:2]
    x, y = int(round(pixel[0])), int(round(pixel[1]))
    if not (0 <= x < w and 0 <= y < h):
        raise ValueError(f"pixel fora da imagem: {pixel}")
    viz = pontos[max(0, y - raio) : y + raio + 1, max(0, x - raio) : x + raio + 1].reshape(-1, 3)
    viz = viz[np.all(np.isfinite(viz), axis=1)]
    if len(viz) == 0:
        raise ValueError(f"sem ponto válido perto de {pixel}")
    return np.median(viz, axis=0)


def distancia(pontos: np.ndarray, p1: tuple[float, float], p2: tuple[float, float]) -> Extensao:
    """Distância 3D entre dois pixels clicados (mediana de uma vizinhança de 5 × 5 em cada um)."""
    a = ponto_robusto(pontos, p1)
    b = ponto_robusto(pontos, p2)
    d = b - a
    valor = float(np.linalg.norm(d))
    eixo = d / valor if valor > 0 else np.array([1.0, 0.0, 0.0])
    # 1 pixel nas duas pontas: tamanho local do pixel ao longo da linha; ruído local numa janela 11 × 11
    passos, disps = [], []
    for (x, y) in (p1, p2):
        yi, xi = int(round(y)), int(round(x))
        janela = np.zeros(pontos.shape[:2], dtype=bool)
        janela[max(0, yi - 5) : yi + 6, max(0, xi - 5) : xi + 6] = True
        dx, dy = _passos_pixel(pontos, janela)
        passos.append(_passo_ao_longo(dx, dy, eixo))
        disps.append(_rugosidade(pontos, janela, eixo))
    # a mediana de 25 pontos reduz o ruído de cada ponta em ~1/sqrt(25)
    return Extensao(valor=valor, eixo=eixo, passo=float(np.mean(passos)), dispersao=float(np.mean(disps)) / 5.0)


def fator_escala(referencia_estimada: float, referencia_real: float) -> float:
    if referencia_estimada <= 0 or referencia_real <= 0:
        raise ValueError("referência com tamanho zero ou negativo")
    return referencia_real / referencia_estimada


def corrigir_escala(medidas: dict, referencia_estimada: float, referencia_real: float) -> tuple[dict, float]:
    """Aplica um fator único à cena: ``real / estimada`` da referência multiplica todas as medidas.

    ``medidas``: dicionário nome → valor (números; ``None`` passa direto). Devolve (medidas, fator).
    """
    fator = fator_escala(referencia_estimada, referencia_real)
    return {k: (None if v is None else v * fator) for k, v in medidas.items()}, fator
