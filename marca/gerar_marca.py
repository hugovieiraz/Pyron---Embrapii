"""Gera os arquivos da marca Pyron a partir da logo original (marca/pyron_logo.png).

Saídas:
    app/estatico/marca/simbolo.png    mão e chama, fundo transparente (para fundos claros)
    app/estatico/marca/logo.png       logo completa (símbolo, PYRON e slogan), fundo transparente
    app/estatico/marca/icone-64.png   ladrilho claro com o símbolo: favicon
    app/estatico/marca/icone-192.png  ladrilho claro com o símbolo: barra lateral e atalhos
    <destino_ico>                     ícone do Windows multi-tamanho (padrão: lancador/obj/pyron.ico)

Uso: python marca/gerar_marca.py [destino.ico]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

AQUI = Path(__file__).resolve().parent
PROJETO = AQUI.parent
ORIGINAL = AQUI / "pyron_logo.png"
ESTATICO = PROJETO / "app" / "estatico" / "marca"

# Caixas na imagem original de 1024 × 1024 (x0, y0, x1, y1).
CAIXA_SIMBOLO = (303, 152, 725, 670)
CAIXA_LOGO = (206, 152, 819, 883)
TAMANHOS_ICO = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
BORDA_LADRILHO = (214, 220, 228)


def fundo_estimado(rgb: np.ndarray) -> np.ndarray:
    """O fundo da logo é um cinza-claro com leve vinheta: ajusta uma superfície quadrática por canal."""
    satur = rgb.max(2) - rgb.min(2)
    claro = rgb.mean(2)
    amostra = (satur < 8) & (claro > 225)
    ys, xs = np.nonzero(amostra[::8, ::8])
    ys, xs = ys * 8, xs * 8
    h, w = claro.shape
    def termos(x, y):
        x, y = x / w - 0.5, y / h - 0.5
        return np.stack([np.ones_like(x), x, y, x * x, y * y, x * y], -1)
    coef = np.linalg.lstsq(termos(xs.astype(float), ys.astype(float)), rgb[ys, xs], rcond=None)[0]
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    return termos(xx, yy) @ coef


def transparente(original: Image.Image) -> Image.Image:
    """Tira o fundo claro: opacidade pela saturação ou pelo escurecimento em relação ao fundo local.

    O contorno branco entre a chama e a mão também some (é fundo no desenho original).
    A cor das bordas é descontaminada do fundo para não deixar halo cinza.
    """
    rgb = np.asarray(original.convert("RGB")).astype(float)
    fundo = fundo_estimado(rgb)
    satur = rgb.max(2) - rgb.min(2) - (fundo.max(2) - fundo.min(2))
    escurecimento = fundo.mean(2) - rgb.mean(2)
    d = np.maximum(satur, escurecimento)
    alfa = np.clip((d - 8.0) / (90.0 - 8.0), 0.0, 1.0)
    cor = fundo + (rgb - fundo) / np.maximum(alfa, 1e-3)[..., None]
    cor = np.clip(np.where(alfa[..., None] > 0, cor, 0), 0, 255)
    rgba = np.dstack([cor, alfa * 255]).round().astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def com_margem(img: Image.Image, caixa: tuple[int, int, int, int], margem: float, quadrado: bool) -> Image.Image:
    x0, y0, x1, y1 = caixa
    recorte = img.crop(caixa)
    w, h = x1 - x0, y1 - y0
    lado_w = lado_h = None
    if quadrado:
        lado_w = lado_h = round(max(w, h) * (1 + 2 * margem))
    else:
        lado_w, lado_h = round(w + 2 * margem * max(w, h)), round(h + 2 * margem * max(w, h))
    tela = Image.new("RGBA", (lado_w, lado_h), (0, 0, 0, 0))
    tela.paste(recorte, ((lado_w - w) // 2, (lado_h - h) // 2), recorte)
    return tela


def ladrilho(simbolo: Image.Image, lado: int) -> Image.Image:
    """Quadrado claro de cantos arredondados com o símbolo: lê bem na barra de tarefas clara ou escura."""
    k = 8  # desenha grande e reduz, para bordas suaves
    L = lado * k
    tela = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(tela)
    raio = L * 0.22
    borda = max(k, round(L * 0.012)) if lado >= 32 else k
    d.rounded_rectangle([0, 0, L - 1, L - 1], radius=raio, fill=BORDA_LADRILHO)
    d.rounded_rectangle([borda, borda, L - 1 - borda, L - 1 - borda], radius=raio - borda, fill=(255, 255, 255))
    # Tamanhos pequenos: o símbolo ocupa mais do ladrilho para a chama continuar legível.
    ocupacao = 0.92 if lado <= 24 else 0.86 if lado <= 48 else 0.8
    s = round(L * ocupacao)
    simb = simbolo.resize((s, s), Image.LANCZOS)
    tela.alpha_composite(simb, ((L - s) // 2, (L - s) // 2 + round(L * 0.01)))
    return tela.resize((lado, lado), Image.LANCZOS)


def main() -> None:
    destino_ico = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJETO / "lancador" / "obj" / "pyron.ico"
    ESTATICO.mkdir(parents=True, exist_ok=True)
    destino_ico.parent.mkdir(parents=True, exist_ok=True)

    sem_fundo = transparente(Image.open(ORIGINAL))
    simbolo = com_margem(sem_fundo, CAIXA_SIMBOLO, 0.02, quadrado=True)
    logo = com_margem(sem_fundo, CAIXA_LOGO, 0.03, quadrado=False)

    simbolo.resize((512, 512), Image.LANCZOS).save(ESTATICO / "simbolo.png", optimize=True)
    largura = 720
    logo.resize((largura, round(logo.height * largura / logo.width)), Image.LANCZOS).save(ESTATICO / "logo.png", optimize=True)
    ladrilho(simbolo, 64).save(ESTATICO / "icone-64.png", optimize=True)
    ladrilho(simbolo, 192).save(ESTATICO / "icone-192.png", optimize=True)

    camadas = [ladrilho(simbolo, t) for t in TAMANHOS_ICO]
    camadas[-1].save(destino_ico, format="ICO", sizes=[(t, t) for t in TAMANHOS_ICO], append_images=camadas[:-1])
    print("marca gerada em", ESTATICO, "e", destino_ico)


if __name__ == "__main__":
    main()
