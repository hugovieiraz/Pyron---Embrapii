"""Onde está o termograma numa foto comum (o celular filmando a tela do computador, por exemplo).

Um termograma colorido tem cores fortes de várias matizes juntas (a paleta: azul, verde, amarelo e
vermelho no arco-íris; roxo, laranja e amarelo no ferro). Uma sala, um móvel ou um objeto de casa
tem cores mais apagadas, ou de uma matiz só. O detector de peças foi treinado só com termogramas:
olhando a foto inteira ele procura para-raios em qualquer coisa. Recortar a área do termograma tira
esses enganos e entrega ao detector a imagem grande e na proporção em que ele aprendeu.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Escolhidos nos 151 termogramas e nas 151 fotos visíveis do conjunto ScienceDB 10185 (um a cada 6):
# aceita 100% dos termogramas e 0% das fotos. A saturação mediana separa bem: termogramas 0,87 ou
# mais (5º percentil), fotos 0,52 ou menos (95º percentil).
SATURACAO_MIN = 0.45  # cor forte (0 a 1)
BRILHO_MIN = 0.20  # o fundo quase preto da paleta ferro não conta; as partes coloridas, sim
AREA_MIN = 0.03  # o termograma ocupa ao menos isso do quadro
MATIZES_MIN = 3  # faixas de matiz (de 30°) com ao menos FRACAO_MATIZ dos pixels coloridos
FRACAO_MATIZ = 0.01  # baixo: num fundo azul dominante, a peça quente ocupa pouco
SATURACAO_AREA_MIN = 0.6  # saturação mediana da área (paleta é cor pura; foto comum é mais apagada)
MARGEM = 0.12  # folga em volta da área colorida, para não cortar as partes frias da peça


@dataclass
class Area:
    x0: int
    y0: int
    x1: int
    y1: int
    matizes: int  # quantas faixas de matiz a área tem (quanto mais, mais cara de paleta)

    def caixa(self) -> list[int]:
        return [self.x0, self.y0, self.x1, self.y1]


def _matizes(h: np.ndarray) -> int:
    """Faixas de 30° de matiz com presença real (h do OpenCV vai de 0 a 179)."""
    if not h.size:
        return 0
    contagem = np.bincount((h.astype(np.int32) // 15) % 12, minlength=12)
    return int((contagem / h.size >= FRACAO_MATIZ).sum())


def achar_termograma(rgb: np.ndarray) -> Area | None:
    """Caixa (em pixels de ``rgb``) da área que parece um termograma, ou None se não há nenhuma."""
    import cv2

    h, w = rgb.shape[:2]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    colorido = (hsv[..., 1] > SATURACAO_MIN * 255) & (hsv[..., 2] > BRILHO_MIN * 255)
    # Tira o chiado: no escuro, o ruído da câmera do celular faz pixels soltos parecerem cor forte.
    colorido = cv2.morphologyEx(colorido.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)).astype(bool)
    lado = max(9, int(round(min(h, w) * 0.04)) | 1)  # junta as manchas da paleta separadas por texto e contornos
    junto = cv2.morphologyEx(colorido.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((lado, lado), np.uint8))
    n, rotulos, estat, _ = cv2.connectedComponentsWithStats(junto)
    for k in sorted(range(1, n), key=lambda i: -estat[i, cv2.CC_STAT_AREA]):
        x, y, bw, bh, area = (int(v) for v in estat[k])
        if area < AREA_MIN * h * w:
            break
        regiao = rotulos == k
        matizes = _matizes(hsv[..., 0][regiao & colorido])
        if matizes < MATIZES_MIN or np.median(hsv[..., 1][regiao]) < SATURACAO_AREA_MIN * 255:
            continue
        mx, my = int(bw * MARGEM), int(bh * MARGEM)
        return Area(max(0, x - mx), max(0, y - my), min(w, x + bw + mx), min(h, y + bh + my), matizes)
    return None
