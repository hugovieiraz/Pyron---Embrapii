"""Paletas de exibição e desenho do termograma com as regiões (para laudos e miniaturas)."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Pontos de controle (posição 0 a 1, cor RGB) das paletas; o front-end usa as mesmas tabelas.
PALETAS = {
    "ferro": [(0.0, (0, 0, 16)), (0.18, (46, 0, 110)), (0.38, (150, 0, 130)), (0.55, (220, 50, 40)), (0.72, (250, 140, 0)), (0.88, (255, 215, 60)), (1.0, (255, 255, 230))],
    "arco-iris": [(0.0, (0, 5, 60)), (0.15, (10, 60, 180)), (0.32, (20, 170, 230)), (0.48, (40, 200, 60)), (0.62, (240, 230, 20)), (0.76, (250, 150, 20)), (0.9, (240, 40, 60)), (1.0, (255, 250, 245))],
    "cinza": [(0.0, (0, 0, 0)), (1.0, (255, 255, 255))],
}

# Mesmas cores dos tokens da interface (app/estatico/tokens.css: --normal … --imediato).
CORES_SEVERIDADE = {
    "normal": (0x17, 0x9B, 0x67),
    "atencao": (0xD9, 0xA4, 0x0B),
    "programar": (0xE8, 0x75, 0x1A),
    "urgente": (0xDC, 0x3F, 0x26),
    "imediato": (0xB0, 0x12, 0x3A),
}


def tabela(nome: str = "ferro", n: int = 256) -> np.ndarray:
    pontos = PALETAS[nome]
    pos = np.array([p for p, _ in pontos])
    cores = np.array([c for _, c in pontos], dtype=np.float64)
    x = np.linspace(0, 1, n)
    return np.stack([np.interp(x, pos, cores[:, k]) for k in range(3)], axis=1).round().astype(np.uint8)


def faixa_exibicao(temperatura: np.ndarray) -> tuple[float, float]:
    """Faixa de cores que realça o equipamento: do 1º percentil do equipamento ao máximo.

    O céu, muito mais frio, fica todo na cor mais escura em vez de comprimir o equipamento no
    topo da escala.
    """
    from nucleo.analise import mascara_objetos

    ok = np.isfinite(temperatura)
    objetos = mascara_objetos(temperatura)
    base = temperatura[objetos] if objetos.sum() >= 30 else temperatura[ok]
    lo = float(np.percentile(base, 1))
    hi = float(np.nanmax(temperatura))
    return (lo, hi) if hi > lo else (lo, lo + 1.0)


def colorir(temperatura: np.ndarray, t_min: float | None = None, t_max: float | None = None, nome: str = "ferro") -> np.ndarray:
    ok = np.isfinite(temperatura)
    if t_min is None or t_max is None:
        auto_min, auto_max = faixa_exibicao(temperatura)
        t_min = auto_min if t_min is None else t_min
        t_max = auto_max if t_max is None else t_max
    esc = np.clip((np.nan_to_num(temperatura, nan=t_min) - t_min) / max(t_max - t_min, 1e-6), 0, 1)
    rgb = tabela(nome)[(esc * 255).astype(int)]
    rgb[~ok] = (40, 44, 52)
    return rgb


def _fonte(tamanho: int):
    for caminho in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(caminho, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def _sobrepoe(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def posicionar_rotulo(largura: float, altura: float, caixa, ocupadas: list, limite: tuple[float, float]):
    """Lugar livre para um rótulo junto da caixa: acima, abaixo ou dentro, à esquerda ou à direita.

    Devolve o retângulo (x0, y0, x1, y1) do rótulo, ou None se todos os lugares cobrirem outro rótulo.
    """
    x0, y0, x1, y1 = caixa
    W, H = limite
    folga = 3
    candidatos = [
        (x0, y0 - altura - folga), (x1 - largura, y0 - altura - folga),  # acima
        (x0, y1 + folga), (x1 - largura, y1 + folga),                    # abaixo
        (x0 + folga, y0 + folga), (x1 - largura - folga, y0 + folga),    # dentro, em cima
        (x0 + folga, y1 - altura - folga),                                # dentro, embaixo
        (x1 + folga, y0), (x0 - largura - folga, y0),                     # ao lado
    ]
    for x, y in candidatos:
        x = min(max(x, 0.0), W - largura)
        y = min(max(y, 0.0), H - altura)
        r = (x, y, x + largura, y + altura)
        if not any(_sobrepoe(r, o) for o in ocupadas):
            return r
    return None


def desenhar(temperatura: np.ndarray, regioes: list[dict], largura: int = 960, nome: str = "ferro", numerar: bool = False) -> Image.Image:
    """Termograma ampliado com as caixas e o ponto de máxima de cada região.

    ``numerar=True`` (laudo): cada caixa ganha só o número da linha da tabela, num selo da cor da
    severidade. Sem numerar: nome e temperatura máxima. Em qualquer caso, os rótulos não se cobrem;
    sem lugar livre, o rótulo vira só o número (e, em último caso, fica por cima do mais próximo).
    """
    h, w = temperatura.shape
    escala = largura / w
    img = Image.fromarray(colorir(temperatura, nome=nome)).resize((largura, int(h * escala)), Image.BICUBIC)
    d = ImageDraw.Draw(img)
    fonte = _fonte(max(12, largura // (48 if numerar else 42)))
    limite = (img.width, img.height)
    traco = max(2, largura // 320)
    caixas = []
    for r in regioes:
        x0, y0, x1, y1 = (v * escala for v in r["caixa"])
        cor = CORES_SEVERIDADE.get(r.get("severidade", "normal"), (255, 255, 255))
        d.rectangle([x0, y0, x1, y1], outline=cor, width=traco)
        caixas.append(((x0, y0, x1, y1), cor))
    ocupadas: list = []
    for i, (r, (caixa, cor)) in enumerate(zip(regioes, caixas), start=1):
        m = r.get("medida")
        if m:  # o ponto de máxima também é lugar ocupado
            cx, cy = (m["x_max"] + 0.5) * escala, (m["y_max"] + 0.5) * escala
            d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], outline=(255, 255, 255), width=2)
            ocupadas.append((cx - 6, cy - 6, cx + 6, cy + 6))
    for i, (r, (caixa, cor)) in enumerate(zip(regioes, caixas), start=1):
        m = r.get("medida")
        opcoes = [str(i)] if numerar else [f"{r.get('nome') or r.get('classe', '')}" + (f"  {m['t_max']:.1f} °C" if m else ""), str(i)]
        for texto in opcoes:
            b = d.textbbox((0, 0), texto, font=fonte)
            tw, th = b[2] - b[0] + 10, b[3] - b[1] + 6
            lugar = posicionar_rotulo(tw, th, caixa, ocupadas, limite)
            if lugar:
                break
        if lugar is None:  # sem lugar livre: número colado no canto da caixa
            lugar = (min(max(caixa[0], 0), limite[0] - tw), min(max(caixa[1], 0), limite[1] - th))
            lugar = (*lugar, lugar[0] + tw, lugar[1] + th)
        ocupadas.append(lugar)
        fundo = cor if numerar or texto == str(i) else (15, 23, 36)
        d.rounded_rectangle(lugar, radius=3, fill=fundo, outline=(255, 255, 255) if numerar else None, width=1)
        d.text((lugar[0] + 5, lugar[1] + 2 - b[1]), texto, fill=(255, 255, 255), font=fonte)
    return img
