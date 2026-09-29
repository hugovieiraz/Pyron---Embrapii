"""Temperatura estimada a partir de um termograma colorido (sem dados radiométricos).

O caminho é uma inversão direta, sem aprendizado:

1. achar a barra de cores e a orientação dela;
2. ler as cores da barra, do quente para o frio;
3. ler os limites da escala escritos junto da barra (OCR);
4. para cada pixel, achar a cor mais próxima da barra no espaço CIELAB e interpolar a
   temperatura;
5. descartar o que não é cena (textos, ícones, a própria barra) e marcar os pixels cuja cor
   está longe de qualquer cor da barra.

Os leiautes suportados são os da FLIR C5 em 640×480 com paleta arco-íris: barra vertical à
esquerda (câmera deitada) ou horizontal embaixo (câmera em pé, textos girados).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

LIMIAR_BRANCO = 200  # canal mínimo para contar como borda branca da barra
COMPRIMENTO_MINIMO = 150  # pixels de borda branca contínua para aceitar como barra


@dataclass
class Barra:
    orientacao: str  # "V" (vertical, quente em cima) ou "H" (horizontal, quente à esquerda)
    inicio: int  # primeira linha (V) ou coluna (H) do interior, no lado quente
    fim: int  # última linha (V) ou coluna (H) do interior, no lado frio
    faixa: tuple[int, int]  # colunas (V) ou linhas (H) do interior, sem as bordas


@dataclass
class Escala:
    barra: Barra
    cores: np.ndarray  # N x 3 (RGB, float), do quente para o frio
    t_max: float | None
    t_min: float | None
    textos: dict = field(default_factory=dict)  # texto lido em cada rótulo, para auditoria


# ---------------------------------------------------------------- cor


def rgb_para_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (0 a 255) para CIELAB (D65)."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


# ---------------------------------------------------------------- barra


def _maior_sequencia(linha: np.ndarray) -> tuple[int, int]:
    """(comprimento, início) da maior sequência de True."""
    if not linha.any():
        return 0, 0
    d = np.diff(np.concatenate([[0], linha.astype(np.int8), [0]]))
    ini, fim = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    k = int(np.argmax(fim - ini))
    return int(fim[k] - ini[k]), int(ini[k])


def localizar_barra(rgb: np.ndarray) -> Barra:
    """Acha a barra pela moldura branca: duas linhas paralelas longas perto da borda da imagem."""
    branco = rgb.min(axis=2) > LIMIAR_BRANCO
    h, w = branco.shape
    verticais = [(x, *_maior_sequencia(branco[:, x])) for x in range(0, min(80, w))]
    verticais = [v for v in verticais if v[1] >= COMPRIMENTO_MINIMO]
    horizontais = [(y, *_maior_sequencia(branco[y, :])) for y in range(max(0, h - 80), h)]
    horizontais = [v for v in horizontais if v[1] >= COMPRIMENTO_MINIMO]
    if verticais and len({v[0] for v in verticais}) >= 2:
        xs = sorted({v[0] for v in verticais})
        comp, ini = max((v[1], v[2]) for v in verticais)
        return Barra("V", ini + 2, ini + comp - 3, (xs[0] + 2, xs[-1] - 2))
    if horizontais and len({v[0] for v in horizontais}) >= 2:
        ys = sorted({v[0] for v in horizontais})
        comp, ini = max((v[1], v[2]) for v in horizontais)
        return Barra("H", ini + 2, ini + comp - 3, (ys[0] + 2, ys[-1] - 2))
    raise ValueError("barra de cores não encontrada")


def cores_da_barra(rgb: np.ndarray, barra: Barra) -> np.ndarray:
    """Média das cores ao longo da barra, do lado quente para o frio."""
    a, b = barra.faixa
    if barra.orientacao == "V":
        faixa = rgb[barra.inicio : barra.fim + 1, a : b + 1].astype(np.float64).mean(axis=1)
    else:
        faixa = rgb[a : b + 1, barra.inicio : barra.fim + 1].astype(np.float64).mean(axis=0)
    # Confere o sentido: o lado quente da paleta arco-íris é o mais claro.
    lab = rgb_para_lab(faixa)
    if lab[:5, 0].mean() < lab[-5:, 0].mean():
        faixa = faixa[::-1]
    return faixa


# ---------------------------------------------------------------- rótulos


def regioes_rotulo(barra: Barra, forma: tuple[int, int]) -> dict[str, tuple[int, int, int, int]]:
    """Caixas (x0, y0, x1, y1) onde ficam os números de máximo e mínimo."""
    h, w = forma
    if barra.orientacao == "V":
        return {
            "max": (10, max(0, barra.inicio - 50), 140, barra.inicio - 3),
            "min": (10, barra.fim + 4, 140, min(h, barra.fim + 52)),
        }
    return {
        "max": (70, 340, barra.inicio - 3, h),
        "min": (barra.fim + 4, 340, w, h),
    }


_NUMERO_COMPLETO = re.compile(r"^-?\d{1,3}\.\d$")
_NUMERO = re.compile(r"-?\d{1,3}(?:\.\d)?")


def _limpar(texto: str) -> str:
    """Deixa só dígitos, ponto e sinal; o ícone de cadeado costuma virar uma letra."""
    t = re.sub(r"[^0-9.\-]", "", texto.replace(",", "."))
    return re.sub(r"\.+", ".", t)


def _interpretar(resultado) -> tuple[float | None, str, float]:
    """Número de um rótulo a partir dos pedaços devolvidos pelo OCR."""
    pedacos = [(float(np.mean([p[0] for p in caixa])), _limpar(texto), float(conf)) for caixa, texto, conf in resultado or []]
    completos = [p for p in pedacos if _NUMERO_COMPLETO.match(p[1])]
    if completos:
        _, texto, conf = max(completos, key=lambda p: p[2])
        return float(texto), texto, conf
    # O OCR às vezes parte o número ("19." e ".4"): junta na ordem da esquerda para a direita.
    junto = _limpar("".join(p[1] for p in sorted(pedacos)))
    achado = _NUMERO.search(junto)
    if not achado:
        return None, junto, 0.0
    conf = min((p[2] for p in pedacos), default=0.0)
    return float(achado.group()), junto, conf


def _variantes(recorte):
    """Três preparações do recorte para o OCR votar.

    O cinza com autocontraste ampliado 4× com Lanczos, que parecia a melhor preparação, perdia
    o "1" inicial (traço fino) em algumas sessões ("15.0" virava "5.0"); por isso não entra.
    """
    from PIL import Image, ImageOps

    cinza = ImageOps.grayscale(recorte)
    yield ImageOps.expand(recorte.resize((recorte.width * 4, recorte.height * 4), Image.LANCZOS), 20, (0, 0, 0))
    yield ImageOps.expand(
        ImageOps.invert(ImageOps.autocontrast(cinza.resize((cinza.width * 3, cinza.height * 3), Image.BICUBIC))), 30, 255
    ).convert("RGB")
    realce = (np.clip((np.asarray(cinza, dtype=np.float64) - 60) / 110, 0, 1) * 255).astype(np.uint8)
    realce_img = Image.fromarray(realce).resize((cinza.width * 4, cinza.height * 4), Image.LANCZOS)
    yield ImageOps.expand(ImageOps.invert(realce_img), 30, 255).convert("RGB")


def ler_limites(rgb: np.ndarray, barra: Barra, ocr) -> tuple[float | None, float | None, dict]:
    """Lê máximo e mínimo da escala. ``ocr`` é um RapidOCR (ou algo com a mesma chamada).

    Na câmera em pé o texto sobe de baixo para cima, então o recorte é girado 90° no sentido
    horário. As três preparações votam: vence o valor mais frequente e, no empate, o de maior
    confiança.
    """
    from PIL import Image

    valores: dict[str, float | None] = {}
    textos: dict[str, str] = {}
    for nome, (x0, y0, x1, y1) in regioes_rotulo(barra, rgb.shape[:2]).items():
        recorte = Image.fromarray(rgb[y0:y1, x0:x1])
        if barra.orientacao == "H":
            recorte = recorte.rotate(-90, expand=True)
        leituras = []
        for img in _variantes(recorte):
            resultado, _ = ocr(np.array(img))
            valor, texto, conf = _interpretar(resultado)
            if valor is not None:
                leituras.append((valor, texto, conf))
        if not leituras:
            valores[nome], textos[nome] = None, ""
            continue
        votos = {l[0]: sum(abs(l[0] - m[0]) < 1e-6 for m in leituras) for l in leituras}
        valor, texto, _ = max(leituras, key=lambda l: (votos[l[0]], l[2]))
        valores[nome], textos[nome] = valor, texto
    return valores.get("max"), valores.get("min"), textos


def escala(rgb: np.ndarray, ocr=None, t_max: float | None = None, t_min: float | None = None) -> Escala:
    """Monta a escala da imagem. Limites informados à mão têm prioridade sobre o OCR."""
    barra = localizar_barra(rgb)
    cores = cores_da_barra(rgb, barra)
    textos: dict = {}
    if (t_max is None or t_min is None) and ocr is not None:
        lido_max, lido_min, textos = ler_limites(rgb, barra, ocr)
        t_max = lido_max if t_max is None else t_max
        t_min = lido_min if t_min is None else t_min
    return Escala(barra, cores, t_max, t_min, textos)


# ---------------------------------------------------------------- máscara e inversão


def mascara_sobreposicao(barra: Barra, forma: tuple[int, int]) -> np.ndarray:
    """True onde há texto, ícone ou a barra desenhados pela câmera (fora da cena)."""
    h, w = forma
    m = np.zeros((h, w), dtype=bool)
    if barra.orientacao == "V":
        m[: barra.inicio, :210] = True  # leituras pontuais e rótulo do máximo
        m[barra.fim :, :140] = True  # rótulo do mínimo
        m[:, :38] = True  # barra e moldura
        m[10:70, 500:635] = True  # logotipo
    else:
        m[:135, :70] = True  # logotipo girado
        m[265:, : barra.inicio] = True  # leituras pontuais e rótulo do máximo
        m[340:, barra.fim :] = True  # rótulo do mínimo
        m[barra.faixa[0] - 12 :, :] = True  # barra e moldura
    return m


def mascara_estruturas_finas(lab: np.ndarray, limiar: float = 18.0, janela: int = 5) -> np.ndarray:
    """True em linhas e contornos finos: bordas do MSX, marcadores, retângulo de medição.

    Compara cada pixel com a mediana da vizinhança. Um ponto quente real ocupa ao menos 4×4
    pixels exibidos (1 pixel do sensor), então sobrevive à mediana 5×5; linhas de 1 a 3 pixels
    não sobrevivem.
    """
    from scipy.ndimage import median_filter

    mediana = np.stack([median_filter(lab[..., k], size=janela) for k in range(3)], axis=-1)
    return np.sqrt(((lab - mediana) ** 2).sum(axis=-1)) > limiar


# Constante B de Planck típica de câmeras de onda longa (7,5 a 14 µm), em kelvin.
PLANCK_B_TIPICO = 1430.0


def _radiancia(t_c, b: float = PLANCK_B_TIPICO):
    return 1.0 / (np.exp(b / (np.asarray(t_c, dtype=np.float64) + 273.15)) - 1.0)


def _temperatura(radiancia, b: float = PLANCK_B_TIPICO):
    with np.errstate(invalid="ignore", divide="ignore"):
        return b / np.log(1.0 / np.asarray(radiancia) + 1.0) - 273.15


def posicao_para_temperatura(pos: np.ndarray, t_max: float, t_min: float, modelo: str = "radiancia") -> np.ndarray:
    """Posição na barra (0 quente, 1 frio) para temperatura.

    A FLIR distribui as cores de forma linear no sinal do sensor, que acompanha a radiância e
    não a temperatura. ``modelo="linear"`` supõe distribuição linear na temperatura.
    """
    if modelo == "linear":
        return t_max - pos * (t_max - t_min)
    r_max, r_min = _radiancia(t_max), _radiancia(t_min)
    return _temperatura(r_max - pos * (r_max - r_min))


@dataclass
class Inversao:
    temperatura_c: np.ndarray  # float32, NaN fora da cena ou onde a cor não pertence à paleta
    distancia: np.ndarray  # distância até a cor mais próxima da barra
    posicao: np.ndarray  # posição na barra, 0 (quente) a 1 (frio)
    saturado: np.ndarray  # cor no extremo da barra: a temperatura real pode estar além da escala
    valido: np.ndarray


def inverter(
    rgb: np.ndarray,
    esc: Escala,
    limiar_distancia: float = 12.0,
    espaco: str = "lab",
    modelo: str = "radiancia",
    remover_finas: bool = True,
) -> Inversao:
    """Converte cada pixel em temperatura pela cor mais próxima da barra.

    ``espaco="ab"`` compara só a cromaticidade (ignora a luminosidade), o que reduz o efeito do
    clareamento dos contornos do MSX.
    """
    if esc.t_max is None or esc.t_min is None:
        raise ValueError("limites da escala desconhecidos")
    canais = slice(0, 3) if espaco == "lab" else slice(1, 3)
    lab_barra_total = rgb_para_lab(esc.cores)
    lab_barra = lab_barra_total[:, canais]
    n = len(lab_barra)
    arvore = cKDTree(lab_barra)
    forma = rgb.shape[:2]
    lab_total = rgb_para_lab(rgb.reshape(-1, 3))
    lab = lab_total[:, canais]
    dist, idx = arvore.query(lab)

    # Refino: projeta o pixel no segmento até o vizinho mais próximo na barra.
    viz = np.clip(np.where(idx + 1 < n, idx + 1, idx - 1), 0, n - 1)
    seg = lab_barra[viz] - lab_barra[idx]
    comp2 = np.maximum((seg**2).sum(axis=1), 1e-9)
    frac = np.clip(((lab - lab_barra[idx]) * seg).sum(axis=1) / comp2, 0, 1)
    pos = (idx + frac * (viz - idx)) / (n - 1)

    temp = posicao_para_temperatura(pos, esc.t_max, esc.t_min, modelo)
    valido = (dist.reshape(forma) <= limiar_distancia) & ~mascara_sobreposicao(esc.barra, forma)
    if remover_finas:
        valido &= ~mascara_estruturas_finas(lab_total.reshape(*forma, 3))
    temp = np.where(valido, temp.reshape(forma), np.nan).astype(np.float32)
    posicao = pos.reshape(forma)
    saturado = valido & ((posicao <= 1.0 / (n - 1)) | (posicao >= 1 - 1.0 / (n - 1)))
    return Inversao(temp, dist.reshape(forma), posicao, saturado, valido)
