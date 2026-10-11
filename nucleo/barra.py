"""Barra de cores em qualquer termograma: achar, ler os limites e converter cor em temperatura.

``paleta.py`` cuida do leiaute fixo da FLIR C5 (arquivo original da câmera). Aqui é o caso geral: o
termograma filmado pelo celular na tela do computador, com perspectiva, moiré e a cor puxada pela
câmera do celular, a barra em qualquer lugar e um pouco inclinada.

1. mapa de candidatos: cor igual dos dois lados (através da barra) e mudando devagar ao longo dela,
   sem borda no meio (a moldura da barra é borda; um trecho íngreme da paleta, não);
2. caminhos mais longos quase retos pelo mapa (programação dinâmica: segue a barra inclinada);
3. reta pelo caminho, estendida nas pontas enquanto a faixa continua uniforme (pontas lisas da paleta);
4. perfil de cores ao longo da reta e a conferência: percorre muita cor, pontas distantes, sem voltar
   atrás (a mesma cor em dois lugares), liso e fino;
5. os números junto das pontas (OCR) dizem qual ponta é a quente e os limites;
6. cada cor da imagem vira posição na barra (a cor mais parecida) e a posição vira temperatura.

As cores da barra são medidas no próprio quadro: a cor puxada pela câmera do celular puxa a barra do
mesmo jeito, e a comparação continua valendo. No acervo do ScienceDB (299 termogramas de 5 tipos de
equipamento) a barra foi achada em 298, no lugar certo; em 149 fotos comuns, nenhuma barra falsa.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

from nucleo import paleta

UNIFORME = 6.0  # diferença de cor através da barra (Lab), na média de JANELA pixels ao longo
JANELA = 25
PASSO = 8  # pixels para medir a variação ao longo da barra
VARIA = 3.0  # variação mínima ao longo, em PASSO pixels (Lab)
BORDA = 14.0  # mudança entre pixels a 2 de distância acima disso pode ser borda
DEGRAU = 0.5  # ... e é, se for ao menos isso da mudança em 10 pixels (degrau, não rampa da paleta)
COMPRIMENTO_MINIMO = 0.3  # da altura (barra vertical) ou largura (horizontal) da imagem
INCLINACAO_MAXIMA = 0.08  # ~4,5°
PULO = 4  # linhas por passo do caminho: inclinação de no máximo 1 coluna a cada 4 linhas
CANDIDATOS = 10  # caminhos avaliados por orientação
AMOSTRAS = 64  # cores lidas ao longo da barra
CAMINHO_MINIMO = 100.0  # cor percorrida ao longo da barra, medida em 24 pontos (Lab)
PONTAS_MINIMO = 40.0  # distância de cor entre as duas pontas
REVISITAS_MAXIMO = 0.1  # barras: 0 a 0,05; faixas da cena: 0,47 na mediana
RUGAS_MAXIMO = 1.25  # caminho fino / grosso. Barras: 1,03 a 1,10 (95%); faixas da cena: 1,16 para cima
BEIRA = 3  # pixels: barra com a ponta encostada na beira da imagem está cortada
FALHA_PONTA = 6  # pixels de ruído tolerados ao estender as pontas da barra
UNIFORME_PONTA = 9.0  # diferença através tolerada ao estender (a reta já é da barra; quem para é a borda)
SALTO_MAXIMO = 0.35  # o maior passo do perfil sobre o caminho todo
LARGURA_RELATIVA = 0.03  # largura da faixa uniforme sobre o comprimento: a barra é fina
VAO_ABSURDO = 300.0  # escala mais larga que isso com um "8" na frente: o "8" é o cadeado da FLIR
CLARIDADE_PONTAS = 15.0  # diferença de L entre as pontas para dizer qual é a quente pela cor
LIMIAR_COR = 15.0  # cor mais longe que isso de qualquer cor da barra não vira temperatura (Lab)
LADO_BUSCA = 960  # a busca da barra roda com o lado maior da imagem perto disso (ampliando, se pequena)
AMPLIAR_MAXIMO = 2.5
MEDIANA = 5  # janela da mediana que apaga linhas finas desenhadas pela câmera antes da máxima
PERCENTIL_MAXIMO = 99  # "máxima" de uma peça: robusta a um pixel de ruído


@dataclass
class Barra:
    """A barra achada, em pixels da imagem. ``cores`` (Lab) vão da ponta ``p0`` para a ``p1``."""

    p0: np.ndarray
    p1: np.ndarray
    largura: float
    cores: np.ndarray
    caminho: float
    rugas: float

    def caixa(self, margem: float = 0.0) -> list[int]:
        x0, x1 = sorted((self.p0[0], self.p1[0]))
        y0, y1 = sorted((self.p0[1], self.p1[1]))
        m = self.largura / 2 + margem
        return [int(round(x0 - m)), int(round(y0 - m)), int(round(x1 + m)), int(round(y1 + m))]


@dataclass
class Escala:
    """Barra com a ponta quente conhecida e os limites lidos."""

    barra: Barra
    cores: np.ndarray  # Lab, do quente para o frio
    t_max: float
    t_min: float


# ---------------------------------------------------------------- achar a barra


def lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (0 a 255) para CIELAB (D65), pelo OpenCV: o mesmo de ``paleta.rgb_para_lab``, bem mais rápido."""
    return cv2.cvtColor(np.ascontiguousarray(rgb, dtype=np.float32) / 255, cv2.COLOR_RGB2Lab)


def _mapas(img: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Candidatos a barra vertical, a diferença através (por pixel) e as mudanças fortes ao longo."""
    h, w = img.shape[:2]
    atr = np.zeros((h, w), np.float32)
    atr[:, 1:-1] = np.sqrt(((img[:, 2:] - img[:, :-2]) ** 2).sum(-1))
    suave = cv2.blur(img, (1, PASSO + 1))
    ao_longo = np.zeros((h, w), np.float32)
    ao_longo[PASSO:-PASSO] = np.sqrt(((suave[2 * PASSO:] - suave[: -2 * PASSO]) ** 2).sum(-1)) / 2
    cand = ((cv2.blur(atr, (1, JANELA)) < UNIFORME) & (cv2.blur(ao_longo, (1, JANELA)) > VARIA)).astype(np.uint8)
    cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE, np.ones((9, 1), np.uint8))
    perto = np.zeros((h, w), np.float32)
    perto[1:-1] = np.sqrt(((img[2:] - img[:-2]) ** 2).sum(-1))
    longe = np.zeros((h, w), np.float32)
    longe[5:-5] = np.sqrt(((img[10:] - img[:-10]) ** 2).sum(-1))
    # linha fina (moldura de 2 pixels): o pixel foge da média dos vizinhos a 3 pixels; numa rampa, não foge
    linha = np.zeros((h, w), np.float32)
    linha[3:-3] = np.sqrt(((img[3:-3] - (img[6:] + img[:-6]) / 2) ** 2).sum(-1))
    borda = ((perto > BORDA) & ((perto > DEGRAU * longe) | (linha > BORDA))).astype(np.uint8)
    borda = cv2.dilate(borda, np.ones((3, 1), np.uint8)).astype(bool)
    return cand.astype(bool) & ~borda, atr, perto > BORDA


def _caminhos(cand: np.ndarray) -> np.ndarray:
    """Comprimento do caminho mais longo que desce pelo mapa terminando em cada ponto (±1 coluna por passo)."""
    h, w = cand.shape
    comp = np.zeros((h, w), np.int32)
    antes = np.zeros(w, np.int32)
    for y in range(h):
        m = antes.copy()
        np.maximum(m[1:], antes[:-1], out=m[1:])
        np.maximum(m[:-1], antes[1:], out=m[:-1])
        antes = np.where(cand[y], m + 1, 0)
        comp[y] = antes
    return comp


def _voltar(comp: np.ndarray, y: int, x: int) -> np.ndarray:
    """Pontos (linha, coluna) do caminho que termina em (y, x), de cima para baixo."""
    pts = [(y, x)]
    while comp[y, x] > 1:
        alvo = comp[y, x] - 1
        y -= 1
        x = next(xx for xx in (x, x - 1, x + 1) if 0 <= xx < comp.shape[1] and comp[y, xx] == alvo)
        pts.append((y, x))
    return np.array(pts[::-1])


def _dentro(p: np.ndarray, forma: tuple[int, ...], folga: float = BEIRA) -> bool:
    """O ponto (x, y) longe da beira da imagem."""
    return folga <= p[0] <= forma[1] - 1 - folga and folga <= p[1] <= forma[0] - 1 - folga


def _largura_em(linha: np.ndarray, x: int) -> int:
    e = d = x
    while e > 0 and linha[e - 1]:
        e -= 1
    while d < len(linha) - 1 and linha[d + 1]:
        d += 1
    return d - e + 1


def _centrar(pts: np.ndarray, atr_media: np.ndarray) -> tuple[float, float]:
    """Reta x = a·y + b pelo meio da barra: em cada ponto, a coluna vizinha mais uniforme através.

    O caminho anda pela faixa de candidatos, que numa barra estreita e borrada pode encostar numa
    beira; fora do meio, as pontas da barra se perdem.
    """
    h, w = atr_media.shape
    a, b = np.polyfit(pts[:, 0], pts[:, 1], 1)
    ys = np.arange(int(pts[0, 0]), int(pts[-1, 0]) + 1, 2)
    xs = np.clip(np.round(a * ys + b).astype(int), 3, w - 4)
    vizinhos = np.stack([atr_media[ys, xs + d] for d in range(-3, 4)], axis=1)
    meio = xs + vizinhos.argmin(axis=1) - 3
    return tuple(np.polyfit(ys, meio, 1))


def _estender(y0: int, y1: int, a: float, b: float, atr: np.ndarray, salto: np.ndarray) -> tuple[int, int]:
    """Leva as pontas adiante enquanto a faixa continua uniforme e sem mudança forte (pontas lisas da paleta).

    Olha as três colunas do meio (a reta pode estar meio pixel fora) e aceita até FALHA_PONTA pixels de
    ruído na uniformidade; mudança forte (a moldura) encerra na hora. A ponta fica no último pixel bom.
    """
    h, w = atr.shape

    def coluna(y: int) -> int:
        return int(round(a * y + b))

    def andar(y: int, passo: int) -> int:
        falhas = 0
        proximo = y + passo
        while 0 <= proximo < h and 1 < coluna(proximo) < w - 2:
            x = coluna(proximo)
            if salto[proximo, x - 1:x + 2].any():
                break
            if atr[proximo, x - 1:x + 2].min() < UNIFORME_PONTA:
                y, falhas = proximo, 0
            else:
                falhas += 1
                if falhas > FALHA_PONTA:
                    break
            proximo += passo
        return y

    return andar(y0, -1), andar(y1, 1)


def perfil(img: np.ndarray, p0, p1, meia_largura: float, n: int = AMOSTRAS) -> np.ndarray:
    """Cores ao longo do segmento p0→p1 (mediana através da largura), ``n`` pontos."""
    t = np.linspace(0, 1, n, dtype=np.float32)
    p0 = np.asarray(p0, np.float32)
    eixo = np.asarray(p1, np.float32) - p0
    normal = np.array([-eixo[1], eixo[0]], np.float32) / max(float(np.linalg.norm(eixo)), 1e-6)
    deslocs = np.linspace(-meia_largura, meia_largura, max(1, int(2 * meia_largura) + 1), dtype=np.float32)
    pts = p0 + t[:, None] * eixo
    mx = pts[:, None, 0] + deslocs[None, :] * normal[0]
    my = pts[:, None, 1] + deslocs[None, :] * normal[1]
    amostra = cv2.remap(img, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return np.median(amostra, axis=1)


def _conferir(cores: np.ndarray) -> tuple[float, float, float, float, float]:
    """Caminho percorrido, distância entre as pontas, revisitas, maior salto e rugosidade do perfil."""
    passos = np.sqrt((np.diff(cores[:: AMOSTRAS // 24], axis=0) ** 2).sum(-1))
    caminho = float(passos.sum())
    pontas = float(np.linalg.norm(cores[:3].mean(0) - cores[-3:].mean(0)))
    d = np.sqrt(((cores[:, None] - cores[None]) ** 2).sum(-1))
    idx = np.arange(len(cores))
    longe = np.abs(idx[:, None] - idx[None]) > AMOSTRAS // 6
    revisitas = float(((d < 5) & longe).any(axis=1).mean())
    salto = float(passos.max() / max(caminho, 1e-6))
    fino = float(np.sqrt((np.diff(cores, axis=0) ** 2).sum(-1)).sum())
    grosso = float(np.sqrt((np.diff(cores[::4], axis=0) ** 2).sum(-1)).sum())
    return caminho, pontas, revisitas, salto, fino / max(grosso, 1e-6)


def achar(rgb: np.ndarray, img_lab: np.ndarray | None = None) -> Barra | None:
    """A barra de cores da imagem, ou None. Procura vertical e horizontal; fica com a mais lisa e longa.

    Termograma pequeno no quadro (celular longe da tela) deixa a barra com 3 pixels de largura, pouco
    para ver o meio uniforme: se a busca no tamanho original não acha, ela roda de novo na imagem
    ampliada até ``LADO_BUSCA`` e volta para a escala dela.
    """
    img_lab = lab(rgb) if img_lab is None else img_lab
    achada = _achar(img_lab)
    k = min(AMPLIAR_MAXIMO, LADO_BUSCA / max(img_lab.shape[:2]))
    if achada is not None or k <= 1.2:
        return achada
    grande = cv2.resize(img_lab, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    achada = _achar(grande)
    if achada is None:
        return None
    return Barra(achada.p0 / k, achada.p1 / k, achada.largura / k, achada.cores, achada.caminho, achada.rugas)


def conferir_de_novo(img_lab: np.ndarray, anterior: Barra, escala_xy: tuple[float, float]) -> Barra | None:
    """A barra deste quadro procurada só em volta de onde estava no anterior (bem mais rápido que achar).

    ``escala_xy`` leva as coordenadas do quadro anterior para este (o recorte muda de tamanho e de
    origem entre quadros, então a posição antiga é só um palpite). A busca completa roda numa janela
    em volta do palpite, folgada ao longo da barra: as pontas saem da imagem nova, não da antiga (uma
    ponta deslocada estica ou encolhe a escala).
    """
    k = np.asarray(escala_xy, np.float64)
    p0, p1 = anterior.p0 * k, anterior.p1 * k
    vertical = abs(p1[1] - p0[1]) >= abs(p1[0] - p0[0])
    comprimento = float(np.hypot(*(p1 - p0)))
    folga_longo, folga_lado = 0.2 * comprimento + 10, anterior.largura * float(np.mean(k)) + 30
    x0, x1 = sorted((p0[0], p1[0]))
    y0, y1 = sorted((p0[1], p1[1]))
    if vertical:
        x0, x1, y0, y1 = x0 - folga_lado, x1 + folga_lado, y0 - folga_longo, y1 + folga_longo
    else:
        x0, x1, y0, y1 = x0 - folga_longo, x1 + folga_longo, y0 - folga_lado, y1 + folga_lado
    h, w = img_lab.shape[:2]
    x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))
    if x1 - x0 < 10 or y1 - y0 < 10:
        return None
    achada = _achar(np.ascontiguousarray(img_lab[y0:y1, x0:x1]), (vertical,))
    if achada is None or abs(float(np.hypot(*(achada.p1 - achada.p0))) / comprimento - 1) > 0.25:
        return None
    origem = np.array([x0, y0], np.float64)
    return Barra(achada.p0 + origem, achada.p1 + origem, achada.largura, achada.cores, achada.caminho, achada.rugas)


def _achar(img_lab: np.ndarray, orientacoes: tuple[bool, ...] = (True, False)) -> Barra | None:
    base = cv2.GaussianBlur(img_lab, (0, 0), 1.0)
    melhor: tuple[float, Barra] | None = None
    for vertical in orientacoes:
        img = base if vertical else np.ascontiguousarray(base.transpose(1, 0, 2))
        h = img.shape[0]
        cand, atr, salto = _mapas(img)
        atr_media = cv2.blur(atr, (1, 9))
        comp = _caminhos(cand[::PULO])
        livres = comp.max(axis=0).astype(np.float64)
        avaliadas = 0
        while avaliadas < CANDIDATOS:
            x = int(np.argmax(livres))
            if livres[x] * PULO < COMPRIMENTO_MINIMO * h:
                break
            livres[max(0, x - 6):x + 7] = 0  # o mesmo caminho termina em colunas vizinhas
            y = int(np.argmax(comp[:, x]))
            # filtro barato antes da conta toda: a barra é fina (faixas largas da cena gastariam as vagas)
            if _largura_em(cand[y * PULO], x) > max(6.0, LARGURA_RELATIVA * comp[y, x] * PULO):
                continue
            avaliadas += 1
            pts = _voltar(comp, y, x) * np.array([PULO, 1])
            a, b = _centrar(pts, atr_media)
            if abs(a) > INCLINACAO_MAXIMA:
                continue
            largura = float(np.median([_largura_em(cand[yy], xx) for yy, xx in pts[:: max(1, len(pts) // 20)]]))
            y0, y1 = _estender(int(pts[0, 0]), int(pts[-1, 0]), a, b, atr, salto)
            p0, p1 = np.array([a * y0 + b, y0], np.float64), np.array([a * y1 + b, y1], np.float64)
            if not (_dentro(p0, img.shape) and _dentro(p1, img.shape)):
                continue  # barra cortada pela beira do quadro: a ponta cortada não é o limite da escala
            cores = perfil(img, p0, p1, max(0.0, (largura - 1) / 2))
            caminho, pontas, revisitas, maior_salto, rugas = _conferir(cores)
            comprimento = float(np.hypot(*(p1 - p0)))
            if not (caminho >= CAMINHO_MINIMO and pontas >= PONTAS_MINIMO and revisitas <= REVISITAS_MAXIMO
                    and maior_salto <= SALTO_MAXIMO and rugas <= RUGAS_MAXIMO
                    and largura <= max(6.0, LARGURA_RELATIVA * comprimento)):
                continue
            if not vertical:
                p0, p1 = p0[::-1].copy(), p1[::-1].copy()
            nota = caminho / rugas**2
            if melhor is None or nota > melhor[0]:
                melhor = (nota, Barra(p0, p1, largura, cores, caminho, rugas))
    return melhor[1] if melhor else None


# ---------------------------------------------------------------- números das pontas


def regioes_rotulos(barra: Barra, forma: tuple[int, ...]) -> list[tuple[int, int, int, int]]:
    """Caixas (x0, y0, x1, y1) junto de cada ponta (p0, p1), para fora da barra: onde ficam os números.

    Barra vertical: o número fica acima ou abaixo da ponta e escrito para o lado (mais para a direita,
    onde cabe o texto quando a barra está na borda esquerda). Horizontal: antes ou depois da ponta.
    """
    h, w = forma[:2]
    comprimento = float(np.hypot(*(barra.p1 - barra.p0)))
    eixo = (barra.p1 - barra.p0) / comprimento
    vertical = abs(eixo[1]) > abs(eixo[0])
    caixas = []
    for ponta, sentido in ((barra.p0, -eixo), (barra.p1, eixo)):
        c = ponta + sentido * 0.09 * comprimento
        ao_longo, ao_lado = 0.12 * comprimento, 0.42 * comprimento
        if vertical:
            x0, x1, y0, y1 = c[0] - ao_lado / 2, c[0] + ao_lado, c[1] - ao_longo, c[1] + ao_longo
        else:
            x0, x1, y0, y1 = c[0] - ao_longo, c[0] + ao_longo, c[1] - ao_lado / 2, c[1] + ao_lado
        caixas.append((max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))))
    return caixas


def ler_numeros(rgb: np.ndarray, barra: Barra, ocr) -> tuple[float | None, float | None]:
    """Os números junto das pontas p0 e p1 (OCR), ou None onde não deu para ler."""
    valores = []
    for ponta, (x0, y0, x1, y1) in zip((barra.p0, barra.p1), regioes_rotulos(barra, rgb.shape)):
        recorte = np.ascontiguousarray(rgb[y0:y1, x0:x1])
        if recorte.size == 0:
            valores.append(None)
            continue
        ponta_local = np.asarray(ponta, np.float64) - (x0, y0)
        valor = _ler_rotulo(recorte, ponta_local, ocr)
        if valor is None or abs(valor) >= 100:
            # Escala travada na FLIR: um cadeado branco ao lado do número cinza, que de longe o OCR lê
            # como "8" ("830.0" no lugar de "30.0"). Apaga o tom mais claro e lê de novo; se ainda
            # sobrar o "8" (ou "6") na frente, ele é o cadeado.
            sem_cadeado = _sem_tom_mais_claro(recorte)
            if sem_cadeado is not None:
                outro = _ler_rotulo(sem_cadeado, ponta_local, ocr)
                valor = outro if outro is not None else valor
                if valor is not None and 100 <= valor < 1000 and str(valor)[0] in "86":
                    valor = float(str(valor)[1:])
        valores.append(valor)
    return valores[0], valores[1]


def _ler_rotulo(recorte: np.ndarray, ponta: np.ndarray, ocr) -> float | None:
    """O número completo (uma casa decimal) mais perto da ponta da barra.

    Perto da ponta pode haver outro número (a leitura do ponto central, "26.9°C"): vale o mais perto.
    """
    k = max(1.0, 48 / recorte.shape[0])  # texto pequeno (celular longe da tela): amplia antes de ler
    if k > 1:
        recorte = cv2.resize(recorte, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    resultado, _ = ocr(np.ascontiguousarray(recorte), use_cls=False)
    completos = []
    for caixa, texto, _conf in resultado or []:
        limpo = paleta._limpar(texto)
        if paleta._NUMERO_COMPLETO.match(limpo):
            centro = np.mean(np.asarray(caixa, np.float64), axis=0) / k
            completos.append((float(np.hypot(*(centro - ponta))), float(limpo)))
    return min(completos)[1] if completos else paleta._interpretar(resultado)[0]


def _sem_tom_mais_claro(recorte: np.ndarray) -> np.ndarray | None:
    """O recorte com o tom mais claro do texto trocado pelo fundo, se o texto tem dois tons; senão None."""
    cinza = cv2.cvtColor(recorte, cv2.COLOR_RGB2GRAY).astype(np.float32)
    fundo = float(np.median(cinza))
    texto = cinza > fundo + 40
    if texto.sum() < 20:
        return None
    alto, medio = np.percentile(cinza[texto], [95, 50])
    if alto - medio < 35:
        return None  # um tom só (números brancos, sem cadeado)
    limpo = recorte.copy()
    limpo[cinza > (alto + medio) / 2] = np.median(recorte.reshape(-1, 3), axis=0).astype(recorte.dtype)
    return limpo


def montar_escala(barra: Barra, v0: float | None, v1: float | None) -> Escala | None:
    """Escala com a ponta quente onde está o número maior; None se a leitura não faz sentido.

    Nas paletas usuais (arco-íris, ferro, cinza) a ponta quente é a mais clara: se os números dizem o
    contrário, um deles foi mal lido e a escala não é usada.
    """
    if v0 is None or v1 is None or abs(v0 - v1) < 0.5 or max(abs(v0), abs(v1)) > 2000:
        return None
    v0, v1 = _sem_cadeado_na_frente(v0, v1)
    claridade = float(barra.cores[:3, 0].mean() - barra.cores[-3:, 0].mean())  # p0 menos p1
    if abs(claridade) > CLARIDADE_PONTAS and (claridade > 0) != (v0 > v1):
        return None
    if v0 > v1:
        return Escala(barra, barra.cores, float(v0), float(v1))
    return Escala(barra, barra.cores[::-1].copy(), float(v1), float(v0))


def _sem_cadeado_na_frente(v0: float, v1: float) -> tuple[float, float]:
    """Tira o "8" (ou "6") que sobrou do cadeado quando a escala ficaria absurda com ele.

    "830.0" com "19.8" do outro lado é uma escala de 810 °C; sem o primeiro algarismo, 30.0 a 19.8.
    Só vale para números de três algarismos começando por 8 ou 6 e quando, sem ele, o número continua
    do mesmo lado do outro.
    """
    def tirar(v: float, outro: float) -> float:
        texto = f"{v:.1f}"
        if 100 <= v < 1000 and texto[0] in "86" and abs(v - outro) > VAO_ABSURDO:
            sem = float(texto[1:])
            if (sem > outro) == (v > outro):
                return sem
        return v

    return tirar(v0, v1), tirar(v1, v0)


def escala_informada(barra: Barra, t_min: float, t_max: float) -> Escala:
    """Escala com os limites informados à mão: a ponta quente é a mais clara (na dúvida, a de cima/esquerda)."""
    claridade = float(barra.cores[:3, 0].mean() - barra.cores[-3:, 0].mean())
    if claridade >= -CLARIDADE_PONTAS:
        return Escala(barra, barra.cores, float(t_max), float(t_min))
    return Escala(barra, barra.cores[::-1].copy(), float(t_max), float(t_min))


def mascara_sobreposicao(barra: Barra, forma: tuple[int, ...]) -> np.ndarray:
    """True na barra e onde ficam os números dela: não é cena."""
    h, w = forma[:2]
    m = np.zeros((h, w), bool)
    x0, y0, x1, y1 = barra.caixa(margem=3)
    m[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
    for x0, y0, x1, y1 in regioes_rotulos(barra, forma):
        m[y0:y1, x0:x1] = True
    return m


# ---------------------------------------------------------------- cor → temperatura


def temperaturas(img_lab: np.ndarray, escala: Escala) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Temperatura de cada pixel (NaN onde a cor não é da barra), se está no extremo quente e a distância."""
    forma = img_lab.shape[:2]
    pos, dist = paleta.projetar_na_barra(img_lab.reshape(-1, 3), escala.cores)
    temp = paleta.posicao_para_temperatura(pos, escala.t_max, escala.t_min)
    valido = dist <= LIMIAR_COR
    quente = valido & (pos <= 1.0 / (len(escala.cores) - 1))
    return np.where(valido, temp, np.nan).reshape(forma), quente.reshape(forma), dist.reshape(forma)


def _mediana_lab(img_lab: np.ndarray, janela: int) -> np.ndarray:
    """Mediana de cada canal Lab (o OpenCV só faz janela maior que 5 em 8 bits: perde ~0,4 de Lab, nada aqui)."""
    escala, desvio = np.float32([2.55, 1.0, 1.0]), np.float32([0.0, 128.0, 128.0])
    oito = np.clip(img_lab * escala + desvio, 0, 255).astype(np.uint8)
    return (cv2.medianBlur(oito, janela).astype(np.float32) - desvio) / escala


def maxima(img_lab: np.ndarray, escala: Escala, caixa) -> tuple[float | None, bool]:
    """Máxima estimada dentro da caixa (x0, y0, x1, y1) e se ela bate no topo da escala (pode ser mais)."""
    x0, y0, x1, y1 = (int(round(v)) for v in caixa)
    h, w = img_lab.shape[:2]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    # a própria barra e seus números não são peça
    bx0, by0, bx1, by1 = escala.barra.caixa(margem=2)
    pedaco = np.ascontiguousarray(img_lab[y0:y1, x0:x1])
    if pedaco.shape[0] < 5 or pedaco.shape[1] < 5:
        return None, False
    # Linhas finas desenhadas pela câmera (moldura da área de medição, mira do ponto central) são brancas
    # como a ponta quente da barra: a mediana 5×5 apaga linhas de até 2 pixels; um ponto quente de
    # verdade (um pixel do sensor ocupa 4×4 na tela) sobrevive.
    pedaco = _mediana_lab(pedaco, MEDIANA)
    temp, quente, _ = temperaturas(pedaco, escala)
    sobre = np.zeros(temp.shape, bool)
    sobre[max(0, by0 - y0):max(0, by1 - y0), max(0, bx0 - x0):max(0, bx1 - x0)] = True
    validos = temp[np.isfinite(temp) & ~sobre]
    if validos.size < 20:
        return None, False
    return float(np.percentile(validos, PERCENTIL_MAXIMO)), bool((quente & ~sobre).mean() > 0.005)


# ---------------------------------------------------------------- ao vivo (quadros do celular)


class LeitorAoVivo:
    """Escala de quadros seguidos: acha a barra em todo quadro e lê os números só quando precisa.

    O OCR leva ~30 ms por número com a detecção de texto limitada a 320 pixels (o padrão do RapidOCR
    amplia o recorte para 736 e leva ~700 ms). Um quadro tremido às vezes lê errado ("-1995" no lugar de
    "-19.5") ou deixa um número de fora; por isso uma leitura só vale quando aparece duas vezes entre as
    últimas três completas. Depois disso é reaproveitada enquanto os números parecerem os mesmos e
    conferida de novo a cada ``RELER_S``; números com cara bem diferente (outra imagem) recomeçam a conta.
    """

    RELER_S = 3.0
    PROCURAR_S = 2.0  # a barra do quadro anterior é reaproveitada; a busca completa roda a cada tanto
    SEM_BARRA_S = 1.5  # sem barra no quadro anterior: espera isso antes de procurar de novo (a busca pesa ~100 ms)
    RELER_MUDANCA = 0.3  # mudança nas miniaturas dos números acima disso: relê
    OUTRA_IMAGEM = 0.6  # acima disso: outra escala na tela, esquece as leituras

    def __init__(self, fabrica_ocr=None):
        self._fabrica = fabrica_ocr or _ocr_rapido
        self._ocr = None
        self._trava = threading.Lock()
        self._leituras: list[tuple[float, float]] = []  # últimas leituras completas
        self._miniaturas: np.ndarray | None = None
        self._quando = 0.0
        self._barra: Barra | None = None  # a do quadro anterior, no tamanho daquele recorte
        self._forma: tuple[int, int] = (0, 0)
        self._procurou = -1e9

    def reiniciar(self) -> None:
        """Esquece barra e leituras (outra sessão do celular, talvez outra câmera)."""
        with self._trava:
            self._leituras.clear()
            self._miniaturas = None
            self._barra = None
            self._procurou = -1e9

    @property
    def _aceita(self) -> tuple[float, float] | None:
        for leitura in reversed(self._leituras):
            if self._leituras.count(leitura) >= 2:
                return leitura
        return None

    def ler(self, rgb: np.ndarray, img_lab: np.ndarray | None = None) -> tuple[Escala | None, Barra | None, str]:
        """(escala, barra, estado). Estado: "sem_barra", "lendo" (achou a barra, números ainda não) ou "lida"."""
        img_lab = lab(rgb) if img_lab is None else img_lab
        with self._trava:
            barra = self._achar(rgb, img_lab)
            if barra is None:
                return None, None, "sem_barra"
            minis = self._miniaturas_dos_numeros(rgb, barra)
            mudanca = 0.0 if self._miniaturas is None else _mudanca(minis, self._miniaturas)
            if mudanca > self.OUTRA_IMAGEM:
                self._leituras.clear()
            self._miniaturas = minis
            if self._aceita is None or mudanca > self.RELER_MUDANCA or time.monotonic() - self._quando > self.RELER_S:
                if self._ocr is None:
                    self._ocr = self._fabrica()
                lido = ler_numeros(rgb, barra, self._ocr)
                self._quando = time.monotonic()
                if None not in lido:
                    self._leituras = (self._leituras + [lido])[-3:]
            aceita = self._aceita
            escala = montar_escala(barra, *aceita) if aceita else None
            return escala, barra, "lida" if escala else "lendo"

    def _achar(self, rgb: np.ndarray, img_lab: np.ndarray) -> Barra | None:
        h, w = img_lab.shape[:2]
        achada = None
        desde = time.monotonic() - self._procurou
        if self._barra is None and desde < self.SEM_BARRA_S:
            return None
        if self._barra is not None and desde < self.PROCURAR_S:
            achada = conferir_de_novo(img_lab, self._barra, (w / self._forma[1], h / self._forma[0]))
        if achada is None:
            achada = achar(rgb, img_lab)
            self._procurou = time.monotonic()
        self._barra, self._forma = achada, (h, w)
        return achada

    @staticmethod
    def _miniaturas_dos_numeros(rgb: np.ndarray, barra: Barra) -> np.ndarray:
        partes = []
        for x0, y0, x1, y1 in regioes_rotulos(barra, rgb.shape):
            recorte = rgb[y0:y1, x0:x1]
            cinza = cv2.cvtColor(recorte, cv2.COLOR_RGB2GRAY) if recorte.size else np.zeros((1, 1), np.uint8)
            partes.append(cv2.resize(cinza, (48, 16), interpolation=cv2.INTER_AREA).astype(np.float32))
        return np.stack(partes)


def _mudanca(a: np.ndarray, b: np.ndarray) -> float:
    """Quanto os números mudaram entre duas miniaturas: o percentil 95 da diferença sobre o contraste do texto.

    Moiré e ruído mexem pouco em muitos pixels; outro número mexe muito nos pixels dos algarismos. A
    correlação, que parecia o natural, não serve: a miniatura é quase toda fundo liso e o ruído manda nela.
    """
    contraste = max(float(np.percentile(a, 98) - np.percentile(a, 2)), 30.0)
    return float(np.percentile(np.abs(a - b), 95)) / contraste


def _ocr_rapido():
    from rapidocr_onnxruntime import RapidOCR

    # detecção de texto em até 320 pixels e 2 fios: o detector de peças continua com o resto da CPU
    return RapidOCR(det_limit_side_len=320, det_limit_type="max", intra_op_num_threads=2)
