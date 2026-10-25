"""Logo final: símbolo vetorizado da imagem 5 + PYRON em Chakra Petch Bold (contornos, licença OFL)."""
import json
from pathlib import Path
from montar import simbolo, v

F = json.load(open("fontes.json"))["chakra"]
PRETO, CLARO, BRANCO = v["cores"]["mao"], "#E6EAF0", "#FFFFFF"
CAP = 78          # altura das maiúsculas: 0,47 da altura do símbolo (166)
X0, CENTRO = 194, 92   # texto começa depois da ponta dos dedos; centro um pouco abaixo do meio do símbolo

def texto(cor):
    s = CAP / 100; K = F["k"] * s; base = CENTRO + CAP / 2
    return "".join(f'<path fill="{cor}" transform="translate({X0 + px * s:.2f} {base:.2f}) scale({K:.5f} {-K:.5f})" d="{d}"/>' for px, d in F["letras"]), F["largura"] * s

def svg(vb, corpo, titulo="Pyron"):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" role="img" aria-label="{titulo}">{corpo}</svg>'

out = Path("pyron-logo"); out.mkdir(exist_ok=True)
VB_SIMB = "12 0 175 182"
for nome, cor, mono in (("cor", PRETO, None), ("escuro", CLARO, None), ("preto", "#000000", "#000000"), ("branco", BRANCO, BRANCO)):
    t, w = texto(cor)
    simb = simbolo(mao=cor, mono=mono)
    (out / f"pyron-logo-{nome}.svg").write_text(svg(f"14 -4 {X0 + w + 14 - 14:.1f} 190", simb + t))
    (out / f"pyron-simbolo-{nome}.svg").write_text(svg(VB_SIMB, simb))
t, w = texto(PRETO)
(out / "pyron-palavra.svg").write_text(svg(f"{X0 - 2} {CENTRO - CAP / 2 - 2} {w + 4:.1f} {CAP + 4}", t, "PYRON"))
# ícone do aplicativo: símbolo com a mão clara sobre ladrilho escuro
(out / "pyron-icone.svg").write_text(svg("0 0 256 256", f'<rect width="256" height="256" rx="56" fill="{PRETO}"/>'
    f'<g transform="translate(128 132) scale(1.12) translate(-99 -91)">{simbolo(mao=CLARO)}</g>'))
print("ok", round(w, 1))
