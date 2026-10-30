"""Gera os arquivos da marca Pyron a partir dos vetores de marca/vetor/ (logo nova, aprovada em 25/10/2026).

Saídas:
    marca/vetor/pyron-logo-vertical-cor.svg  símbolo sobre a palavra, montado dos vetores (sem redesenho)
    app/estatico/marca/simbolo.png           símbolo, 512 px, fundo transparente
    app/estatico/marca/logo.png              logo vertical, 720 px de largura, fundo transparente (README, manual)
    marca/vetor/pyron-logo-vertical-escuro.svg  a mesma logo vertical para fundo escuro
    app/estatico/marca/abertura.png          tela de abertura do Pyron.exe: logo vertical clara com sombra
                                             suave, fundo transparente (aparece solta sobre a área de trabalho)
    marca/vetor/pyron-icone-sem-fundo.svg    ícone do Windows: só o símbolo, sem ladrilho
    app/estatico/marca/logo-cor.svg          logo horizontal para fundo claro (barra da interface nova)
    app/estatico/marca/logo-escuro.svg       logo horizontal para fundo escuro
    app/estatico/marca/icone-janela-*.png    ícone da página da interface (barra de título e de tarefas), sem fundo
    app/estatico/marca/icone-64.png          ícone com ladrilho: favicon da interface anterior
    app/estatico/marca/icone-192.png         ícone do aplicativo: atalhos e página do celular
    marca/pyron.ico e <destino_ico>          ícone do Windows multi-tamanho (atalhos e Pyron.exe), sem fundo
    apresentacao/estatico/marca/             cópias usadas pela apresentação
    marca/vetor/pyron-icone-mascara.svg      ícone do aplicativo instalado (tablet): ladrilho sem cantos, símbolo
                                             dentro da zona segura (círculo de 80 %), para o sistema recortar
    app/estatico/marca/icone-app-192.png     ícones do aplicativo instalado (PWA, manifest.webmanifest): ladrilho
    app/estatico/marca/icone-app-512.png
    app/estatico/marca/icone-app-mascara-512.png   "maskable" do Android
    app/estatico/marca/icone-app-180.png     ícone da tela de início do iPad e do iPhone (apple-touch-icon, sem transparência)

Os SVG viram PNG no Edge sem janela, com fundo transparente: o Edge é assinado pela Microsoft e passa pelo
Controle Inteligente de Aplicativos, e assim nada precisa ser instalado. Cada tamanho do .ico é desenhado
no próprio tamanho, para a chama continuar nítida em 16 px.

Uso: python marca/gerar_marca.py [destino.ico]
     python marca/gerar_marca.py --pwa      só os ícones do aplicativo instalado (não mexe nos outros arquivos)
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter

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


def montar_vertical(versao: str = "cor") -> Path:
    """Símbolo centrado sobre a palavra PYRON, na largura da palavra (mesmas peças da logo horizontal).
    versao "escuro": mão e palavra claras, para fundo escuro."""
    caixa_s, simbolo = _conteudo(VETOR / f"pyron-simbolo-{versao}.svg")
    caixa_p, palavra = _conteudo(VETOR / "pyron-palavra.svg")
    if versao == "escuro":
        palavra = palavra.replace('fill="#0A0A0A"', 'fill="#E6EAF0"')
    _, _, sw, sh = (float(v) for v in caixa_s.split())
    _, _, pw, ph = (float(v) for v in caixa_p.split())
    alto_s = 220.0
    largo_s = alto_s * sw / sh
    vao = 26.0
    total = alto_s + vao + ph
    saida = VETOR / f"pyron-logo-vertical-{versao}.svg"
    saida.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {pw:.1f} {total:.1f}" role="img" aria-label="Pyron">'
        f'<svg x="{(pw - largo_s) / 2:.2f}" y="0" width="{largo_s:.2f}" height="{alto_s:.2f}" viewBox="{caixa_s}">{simbolo}</svg>'
        f'<svg x="0" y="{alto_s + vao:.2f}" width="{pw:.2f}" height="{ph:.2f}" viewBox="{caixa_p}">{palavra}</svg>'
        "</svg>\n",
        encoding="utf-8",
    )
    return saida


def montar_icone_sem_fundo() -> Path:
    """Ícone do Windows só com o símbolo, sem ladrilho. A mão vem clara (a versão da marca para fundo escuro,
    como o tema escuro do Windows e a barra de tarefas) com um contorno escuro fino por baixo, para continuar
    visível quando o papel de parede é claro. O quadro é justo no desenho, para o símbolo encher o ícone."""
    _, miolo = _conteudo(VETOR / "pyron-simbolo-escuro.svg")
    miolo = miolo.replace('fill="#E6EAF0"', 'fill="#E6EAF0" stroke="#0A0A0A" stroke-width="6" stroke-linejoin="round" paint-order="stroke"')
    x0, y0, x1, y1 = 25.73, 7.25, 171.75, 173.69  # extremos do desenho do símbolo
    lado = max(x1 - x0, y1 - y0) + 8  # folga para o contorno
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    saida = VETOR / "pyron-icone-sem-fundo.svg"
    saida.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{cx - lado / 2:.2f} {cy - lado / 2:.2f} {lado:.2f} {lado:.2f}" '
        f'role="img" aria-label="Pyron">{miolo}</svg>\n',
        encoding="utf-8",
    )
    return saida


def montar_icone_mascara() -> Path:
    """Ladrilho escuro de ponta a ponta (sem cantos arredondados: quem arredonda é o sistema) com o símbolo
    reduzido para caber no círculo de 80 % que o Android e o iPadOS nunca cortam."""
    texto = (VETOR / "pyron-icone.svg").read_text(encoding="utf-8")
    texto = texto.replace('rx="56" ', "").replace("scale(1.12)", "scale(0.86)")
    saida = VETOR / "pyron-icone-mascara.svg"
    saida.write_text(texto, encoding="utf-8")
    return saida


def gerar_pwa() -> None:
    """Ícones do aplicativo instalado pelo navegador (manifest.webmanifest e apple-touch-icon)."""
    ESTATICO.mkdir(parents=True, exist_ok=True)
    icone = VETOR / "pyron-icone.svg"
    for lado in (192, 512):
        rasterizar(icone, lado, lado).save(ESTATICO / f"icone-app-{lado}.png", optimize=True)
    mascara = montar_icone_mascara()
    rasterizar(mascara, 512, 512).save(ESTATICO / "icone-app-mascara-512.png", optimize=True)
    rasterizar(mascara, 180, 180).convert("RGB").save(ESTATICO / "icone-app-180.png", optimize=True)


def montar_abertura(vertical_escuro: Path) -> Image.Image:
    """Logo vertical clara com uma sombra suave em volta: a tela de abertura não tem fundo, e a sombra deixa a
    logo legível sobre qualquer papel de parede (claro ou escuro)."""
    largura = 560
    logo = rasterizar(vertical_escuro, largura, round(largura / _proporcao(vertical_escuro)))
    folga = 72
    quadro = Image.new("RGBA", (logo.width + 2 * folga, logo.height + 2 * folga), (0, 0, 0, 0))
    alfa = Image.new("L", quadro.size, 0)
    alfa.paste(logo.getchannel("A"), (folga, folga))
    # duas sombras: uma larga e suave, que separa a logo do fundo, e uma justa e mais escura, que dá o contorno
    # das letras claras quando o papel de parede também é claro
    larga = alfa.filter(ImageFilter.MaxFilter(21)).filter(ImageFilter.GaussianBlur(28)).point(lambda v: round(v * 0.55))
    justa = alfa.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(5)).point(lambda v: round(v * 0.8))
    escuro = Image.new("RGBA", quadro.size, (10, 10, 10, 255))
    quadro.paste(escuro, (0, 0), larga)
    quadro.alpha_composite(Image.composite(escuro, Image.new("RGBA", quadro.size, (0, 0, 0, 0)), justa))
    quadro.alpha_composite(logo, (folga, folga))
    return quadro


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
    if sys.argv[1:] == ["--pwa"]:
        gerar_pwa()
        print("ícones do aplicativo instalado gerados em", ESTATICO)
        return
    destino_ico = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJETO / "lancador" / "obj" / "pyron.ico"
    ESTATICO.mkdir(parents=True, exist_ok=True)
    destino_ico.parent.mkdir(parents=True, exist_ok=True)

    vertical = montar_vertical()
    simbolo = VETOR / "pyron-simbolo-cor.svg"
    icone = VETOR / "pyron-icone.svg"           # ladrilho escuro: favicon e página do celular
    icone_janela = montar_icone_sem_fundo()     # só o símbolo: Pyron.exe e atalhos

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

    montar_abertura(montar_vertical("escuro")).save(ESTATICO / "abertura.png", optimize=True)
    gerar_pwa()

    camadas = [rasterizar(icone_janela, t, t) for t in TAMANHOS_ICO]
    # o mesmo símbolo sem fundo como ícone da página: é ele que aparece na barra de título e na barra de
    # tarefas da janela do aplicativo (nome novo, para o Edge não reaproveitar o ícone antigo guardado)
    for lado in (32, 64, 256):
        camadas[TAMANHOS_ICO.index(lado)].save(ESTATICO / f"icone-janela-{lado}.png", optimize=True)
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
