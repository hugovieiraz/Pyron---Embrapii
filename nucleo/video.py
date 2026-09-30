"""Vídeo térmico analisado quadro a quadro, como se a câmera estivesse ao vivo.

O vídeo é a tela da câmera gravada: termograma colorido com a barra de escala. Cada quadro passa
pelo mesmo caminho de uma foto sem dados radiométricos (barra de cores, temperatura estimada,
detector, medição e severidade). Duas coisas deixam isso rápido o bastante para vídeo:

- os números da escala só vão para o OCR quando a imagem deles muda; no resto do tempo vale a
  leitura anterior;
- a conversão cor → posição na barra vira uma tabela de consulta, montada uma vez por paleta, em
  vez de uma busca de vizinho mais próximo em cada pixel de cada quadro.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nucleo import paleta
from nucleo.entrada import _reduzir

EXTENSOES = (".mp4", ".avi", ".mov", ".mkv", ".m4v", ".wmv", ".webm")
LARGURA = 640  # leiaute da tela da câmera que a leitura da barra conhece (FLIR C5, 640×480)
BITS_TABELA = 6  # 64 níveis por canal: 262 mil cores na tabela, erro menor que 0,1 da escala em Lab
LIMIAR_DISTANCIA = 12.0  # como em paleta.inverter
TOLERANCIA_TEXTO = 0.2  # fração dos pixels de texto que muda sem ser outro número (fundo sob a caixa, compressão)
REVALIDAR_S = 10.0  # relê a escala a cada 10 s de vídeo, mesmo parecendo igual (troca de um só decimal)


@dataclass
class InfoVideo:
    fps: float
    quadros: int
    duracao_s: float
    largura: int
    altura: int


def _cv2():
    import cv2

    return cv2


def abrir(caminho) -> tuple[object, InfoVideo]:
    """Abre o vídeo e devolve (captura, informações). ValueError se não for um vídeo legível."""
    cv2 = _cv2()
    cap = cv2.VideoCapture(str(caminho))
    if not cap.isOpened():
        raise ValueError("Não consegui abrir o arquivo como vídeo. Envie MP4, AVI, MOV ou MKV.")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    if not 1 <= fps <= 240:
        fps = 30.0  # alguns arquivos não trazem a taxa; 30 é o mais comum
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    ok, bgr = cap.read()
    if not ok or bgr is None:
        cap.release()
        raise ValueError("O vídeo abriu, mas não tem nenhum quadro legível.")
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    h, w = bgr.shape[:2]
    return cap, InfoVideo(round(fps, 3), max(n, 1), round(max(n, 1) / fps, 2), int(w), int(h))


def ajustar(bgr: np.ndarray) -> np.ndarray:
    """BGR do OpenCV para RGB na largura que a leitura da barra espera."""
    cv2 = _cv2()
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    if w != LARGURA:
        rgb = cv2.resize(rgb, (LARGURA, round(h * LARGURA / w)), interpolation=cv2.INTER_AREA if w > LARGURA else cv2.INTER_LINEAR)
    return np.ascontiguousarray(rgb)


class Leitor:
    """Entrega o quadro de um instante pedido, pulando os anteriores sem decodificar a imagem."""

    def __init__(self, caminho):
        self.cap, self.info = abrir(caminho)
        self._proximo = 0  # índice do próximo quadro a sair da captura

    def em(self, tempo_s: float) -> tuple[int, float, np.ndarray] | None:
        """(índice, tempo, RGB) do primeiro quadro no instante pedido ou depois; None no fim."""
        alvo = max(self._proximo, int(np.ceil(tempo_s * self.info.fps - 1e-6)))
        while self._proximo < alvo:
            if not self.cap.grab():
                return None
            self._proximo += 1
        ok, bgr = self.cap.read()
        if not ok or bgr is None:
            return None
        indice = self._proximo
        self._proximo += 1
        return indice, indice / self.info.fps, ajustar(bgr)

    def fechar(self) -> None:
        self.cap.release()


class _Tabela:
    """Cor (RGB quantizado) → posição na barra, distância à barra e luminosidade, pré-calculadas."""

    def __init__(self, cores: np.ndarray):
        q = 2**BITS_TABELA
        eixo = (np.arange(q) + 0.5) * (256 / q)
        grade = np.stack(np.meshgrid(eixo, eixo, eixo, indexing="ij"), axis=-1).reshape(-1, 3)
        lab = paleta.rgb_para_lab(grade)
        pos, dist = paleta.projetar_na_barra(lab, paleta.rgb_para_lab(cores))
        self.cores = cores
        self.n = len(cores)
        self.pos = pos.astype(np.float32)
        self.dist = dist.astype(np.float32)
        self.luz = lab[:, 0].astype(np.float32)

    def serve(self, cores: np.ndarray) -> bool:
        return len(cores) == self.n and float(np.abs(cores - self.cores).mean()) < 6.0

    def consultar(self, rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        d = 8 - BITS_TABELA
        k = ((rgb[..., 0].astype(np.int32) >> d) << (2 * BITS_TABELA)) | ((rgb[..., 1].astype(np.int32) >> d) << BITS_TABELA) | (rgb[..., 2].astype(np.int32) >> d)
        return self.pos[k], self.dist[k], self.luz[k]


@dataclass
class Medicao:
    temperatura_c: np.ndarray | None  # matriz na mesma resolução de uma foto (metade da tela); None sem escala
    escala: tuple[float, float] | None  # (mínimo, máximo) usados
    fonte: str  # "informada", "lida", "repetida", "anterior" ou "sem_escala"
    saturado: float = 0.0  # fração da cena no topo ou no fundo da barra


def assinatura_texto(rgb: np.ndarray, caixa) -> np.ndarray:
    """Pixels do número da escala: cinza claro dentro da caixa escura do rótulo.

    O número da FLIR é cinza sobre uma caixa escura semitransparente; o que fica fora da caixa é
    cena e muda a cada quadro. Nas fotos do conjunto, o mesmo número em cenas diferentes difere em
    até 10% dos pixels; números diferentes, em 31% ou mais.
    """
    from scipy import ndimage

    x0, y0, x1, y1 = caixa
    c = rgb[y0:y1, x0:x1].astype(np.int16)
    maior, media = c.max(axis=2), c.mean(axis=2)
    escuro = maior < 60
    rotulos, n = ndimage.label(ndimage.binary_closing(escuro, iterations=2))
    saida = np.zeros(escuro.shape, dtype=bool)
    if n:
        k = int(np.argmax(ndimage.sum(escuro, rotulos, range(1, n + 1))))
        fatia = ndimage.find_objects(rotulos)[k]
        texto = (maior - c.min(axis=2) < 35) & (media > 80)
        saida[fatia] = texto[fatia]
    return saida


def _parecidas(a: np.ndarray, b: np.ndarray) -> bool:
    return a.shape == b.shape and (a != b).sum() <= TOLERANCIA_TEXTO * max(a.sum(), b.sum(), 1)


class Termometro:
    """Temperatura estimada de cada quadro, lembrando a escala e a tabela de cores entre quadros."""

    def __init__(self, ocr=None, limites: tuple[float, float] | None = None):
        self.ocr = ocr
        self.limites = tuple(sorted(limites)) if limites else None
        self._leituras: list[dict] = []  # {"textos", "limites", "lido_em"}: as últimas leituras da escala
        self._tabelas: list[_Tabela] = []
        self._ultima: tuple[float, float] | None = None
        self.leituras_ocr = 0

    def _tabela(self, cores: np.ndarray) -> _Tabela:
        for t in self._tabelas:
            if t.serve(cores):
                return t
        t = _Tabela(cores)
        self._tabelas = [t, *self._tabelas][:4]
        return t

    def _limites(self, rgb: np.ndarray, barra: paleta.Barra, tempo_s: float | None) -> tuple[tuple[float, float] | None, str]:
        if self.limites:
            return self.limites, "informada"
        caixas = list(paleta.regioes_rotulo(barra, rgb.shape[:2]).values())
        textos = [assinatura_texto(rgb, c) for c in caixas]
        igual = next((l for l in self._leituras if all(_parecidas(a, b) for a, b in zip(l["textos"], textos))), None)
        vencida = igual is not None and tempo_s is not None and tempo_s - igual["lido_em"] > REVALIDAR_S
        if igual is not None and not vencida:
            if igual["limites"]:
                return igual["limites"], "repetida"
        elif self.ocr is not None:
            limites = None
            for rapido in (True, False):  # o reconhecimento direto resolve quase sempre; na dúvida, o completo
                t_max, t_min, _ = paleta.ler_limites(rgb, barra, self.ocr, rapido=rapido)
                self.leituras_ocr += 1
                if t_max is not None and t_min is not None and t_max > t_min:
                    limites = (t_min, t_max)
                    break
            outras = [l for l in self._leituras if l is not igual]  # por identidade: dicionários com matrizes
            self._leituras = [{"textos": textos, "limites": limites, "lido_em": tempo_s or 0.0}, *outras][:32]
            if limites:
                return limites, "lida"
        return (self._ultima, "anterior") if self._ultima else (None, "sem_escala")

    def medir(self, rgb: np.ndarray, tempo_s: float | None = None) -> Medicao:
        try:
            barra = paleta.localizar_barra(rgb)
        except ValueError:
            return Medicao(None, None, "sem_escala")
        limites, fonte = self._limites(rgb, barra, tempo_s)
        if not limites:
            return Medicao(None, None, "sem_escala")
        self._ultima = limites
        tabela = self._tabela(paleta.cores_da_barra(rgb, barra))
        pos, dist, luz = tabela.consultar(rgb)
        valido = (dist <= LIMIAR_DISTANCIA) & ~paleta.mascara_sobreposicao(barra, rgb.shape[:2])
        # Contornos finos do MSX clareiam a cor e virariam falsos pontos quentes (como em paleta.inverter).
        from scipy.ndimage import median_filter

        valido &= np.abs(luz - median_filter(luz, size=5)) <= 18.0
        t_min, t_max = limites
        temp = np.where(valido, paleta.posicao_para_temperatura(pos, t_max, t_min), np.nan).astype(np.float32)
        passo = 1.0 / (tabela.n - 1)
        saturado = valido & ((pos <= passo) | (pos >= 1 - passo))
        cena = max(int(valido.sum()), 1)
        return Medicao(_reduzir(temp, 2), limites, fonte, round(float(saturado.sum()) / cena, 3))
