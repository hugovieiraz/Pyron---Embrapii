"""Gera os arquivos da marca Pyron a partir dos vetores de marca/vetor/ (logo nova, aprovada em 25/10/2026).

Saídas:
    marca/vetor/pyron-logo-vertical-cor.svg  símbolo sobre a palavra, montado dos vetores (sem redesenho)
    app/estatico/marca/simbolo.png           símbolo, 512 px, fundo transparente
    app/estatico/marca/logo.png              logo vertical, 720 px de largura, fundo transparente
                                             (tela de abertura do Pyron.exe, Sobre e README)
    app/estatico/marca/logo-cor.svg          logo horizontal para fundo claro (barra da interface nova)
    app/estatico/marca/logo-escuro.svg       logo horizontal para fundo escuro
    app/estatico/marca/icone-64.png          ícone do aplicativo: favicon
    app/estatico/marca/icone-192.png         ícone do aplicativo: atalhos e página do celular
    marca/pyron.ico e <destino_ico>          ícone do Windows multi-tamanho (atalhos e Pyron.exe)
    apresentacao/estatico/marca/             cópias usadas pela apresentação

Os SVG viram PNG no Edge sem janela, com fundo transparente: o Edge é assinado pela Microsoft e passa pelo
Controle Inteligente de Aplicativos, e assim nada precisa ser instalado. Cada tamanho do .ico é desenhado
no próprio tamanho, para a chama continuar nítida em 16 px.

Uso: python marca/gerar_marca.py [destino.ico]
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

AQUI = Path(__file__).resolve().parent
PROJETO = AQUI.parent
VETOR = AQUI / "vetor"
ESTATICO = PROJETO / "app" / "estatico" / "marca"
APRESENTACAO = PROJETO / "apresentacao" / "estatico" / "marca"
TAMANHOS_ICO = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
EDGE = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"), Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")]


def _conteudo(svg: Path) -> tuple[str, str]:
    """viewBox e o desenho de dentro de um SVG de uma peça só."""
    texto = svg.read_text(encoding="utf-8")
    caixa = re.search(r'viewBox="([^"]+)"', texto).group(1)
    miolo = texto[texto.index(">") + 1 : texto.rindex("</svg>")]
    return caixa, miolo


def montar_vertical() -> Path:
    """Símbolo centrado sobre a palavra PYRON, na largura da palavra (mesmas peças da logo horizontal)."""
    caixa_s, simbolo = _conteudo(VETOR / "pyron-simbolo-cor.svg")
    caixa_p, palavra = _conteudo(VETOR / "pyron-palavra.svg")
    _, _, sw, sh = (float(v) for v in caixa_s.split())
    _, _, pw, ph = (float(v) for v in caixa_p.split())
    alto_s = 220.0
    largo_s = alto_s * sw / sh
    vao = 26.0
    total = alto_s + vao + ph
    saida = VETOR / "pyron-logo-vertical-cor.svg"
    saida.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {pw:.1f} {total:.1f}" role="img" aria-label="Pyron">'
        f'<svg x="{(pw - largo_s) / 2:.2f}" y="0" width="{largo_s:.2f}" height="{alto_s:.2f}" viewBox="{caixa_s}">{simbolo}</svg>'
        f'<svg x="0" y="{alto_s + vao:.2f}" width="{pw:.2f}" height="{ph:.2f}" viewBox="{caixa_p}">{palavra}</svg>'
        "</svg>\n",
        encoding="utf-8",
    )
    return saida


def _edge() -> Path:
    for e in EDGE:
        if e.exists():
            return e
    sys.exit("Edge não encontrado: ele é usado para transformar os SVG da marca em PNG.")


def rasterizar(svg: Path, largura: int, altura: int) -> Image.Image:
    """Desenha o SVG em largura × altura px, com fundo transparente."""
    with tempfile.TemporaryDirectory() as pasta:
        pasta = Path(pasta)
        pagina = pasta / "marca.html"
        pagina.write_text(
            "<!doctype html><html><head><style>html,body{margin:0;background:transparent}"
            f"img{{display:block;width:{largura}px;height:{altura}px}}</style></head>"
            f'<body><img src="{svg.as_uri()}"></body></html>',
            encoding="utf-8",
        )
        png = pasta / "saida.png"
        subprocess.run(
            [str(_edge()), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
             "--default-background-color=00000000", f"--user-data-dir={pasta / 'perfil'}",
             f"--window-size={largura},{altura}", f"--screenshot={png}", pagina.as_uri()],
            check=True, capture_output=True, timeout=120,
        )
        with Image.open(png) as im:
            return im.convert("RGBA").copy()


def _proporcao(svg: Path) -> float:
    _, _, w, h = (float(v) for v in _conteudo(svg)[0].split())
    return w / h


def main() -> None:
    destino_ico = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJETO / "lancador" / "obj" / "pyron.ico"
    ESTATICO.mkdir(parents=True, exist_ok=True)
    destino_ico.parent.mkdir(parents=True, exist_ok=True)

    vertical = montar_vertical()
    simbolo = VETOR / "pyron-simbolo-cor.svg"
    icone = VETOR / "pyron-icone.svg"

    # símbolo quadrado com o desenho centrado
    s = rasterizar(simbolo, round(512 * _proporcao(simbolo)), 512)
    quadro = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    quadro.alpha_composite(s, ((512 - s.width) // 2, 0))
    quadro.save(ESTATICO / "simbolo.png", optimize=True)

    rasterizar(vertical, 720, round(720 / _proporcao(vertical))).save(ESTATICO / "logo.png", optimize=True)
    for lado in (64, 192):
        rasterizar(icone, lado, lado).save(ESTATICO / f"icone-{lado}.png", optimize=True)
    shutil.copyfile(VETOR / "pyron-logo-cor.svg", ESTATICO / "logo-cor.svg")
    shutil.copyfile(VETOR / "pyron-logo-escuro.svg", ESTATICO / "logo-escuro.svg")

    camadas = [rasterizar(icone, t, t) for t in TAMANHOS_ICO]
    camadas[-1].save(destino_ico, format="ICO", sizes=[(t, t) for t in TAMANHOS_ICO], append_images=camadas[:-1])
    if destino_ico.resolve() != (AQUI / "pyron.ico").resolve():
        shutil.copyfile(destino_ico, AQUI / "pyron.ico")

    APRESENTACAO.mkdir(parents=True, exist_ok=True)
    for nome in ("icone-64.png", "icone-192.png", "logo.png"):
        shutil.copyfile(ESTATICO / nome, APRESENTACAO / nome)
    shutil.copyfile(AQUI / "pyron.ico", APRESENTACAO / "pyron.ico")
    print("marca gerada em", ESTATICO, ",", AQUI / "pyron.ico", "e", APRESENTACAO)


if __name__ == "__main__":
    main()
