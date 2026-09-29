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

CORES_SEVERIDADE = {
    "normal": (46, 160, 110),
    "atencao": (230, 190, 40),
    "programar": (240, 140, 30),
    "urgente": (230, 80, 40),
    "imediato": (220, 30, 50),
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


def desenhar(temperatura: np.ndarray, regioes: list[dict], largura: int = 960, nome: str = "ferro") -> Image.Image:
    """Termograma ampliado com as caixas, o nome e a temperatura máxima de cada região."""
    h, w = temperatura.shape
    escala = largura / w
    img = Image.fromarray(colorir(temperatura, nome=nome)).resize((largura, int(h * escala)), Image.BICUBIC)
    d = ImageDraw.Draw(img)
    fonte = _fonte(max(12, largura // 42))
    for r in regioes:
        x0, y0, x1, y1 = (v * escala for v in r["caixa"])
        cor = CORES_SEVERIDADE.get(r.get("severidade", "normal"), (255, 255, 255))
        d.rectangle([x0, y0, x1, y1], outline=cor, width=max(2, largura // 320))
        m = r.get("medida")
        texto = f"{r.get('nome') or r.get('classe', '')}"
        if m:
            texto += f"  {m['t_max']:.1f} °C"
        caixa_txt = d.textbbox((x0, y0), texto, font=fonte)
        ty = y0 - (caixa_txt[3] - caixa_txt[1]) - 6
        if ty < 0:
            ty = y1 + 2
        d.rectangle([x0, ty, x0 + caixa_txt[2] - caixa_txt[0] + 8, ty + caixa_txt[3] - caixa_txt[1] + 6], fill=(15, 23, 36))
        d.text((x0 + 4, ty + 1), texto, fill=(255, 255, 255), font=fonte)
        if m:
            cx, cy = (m["x_max"] + 0.5) * escala, (m["y_max"] + 0.5) * escala
            d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], outline=(255, 255, 255), width=2)
    return img
