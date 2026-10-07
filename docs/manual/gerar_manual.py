"""Gera o PDF "Pyron: manual de funcionalidades" (docs/Pyron_Funcionalidades.pdf).

As imagens das telas ficam em docs/manual/imagens (capturadas do aplicativo com dados de
demonstração). Para atualizar depois de mudar a interface: capture as telas de novo e rode

    python docs/manual/gerar_manual.py
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, KeepTogether, ListFlowable, ListItem, NextPageTemplate, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

AQUI = Path(__file__).resolve().parent
PROJETO = AQUI.parents[1]
IMAGENS = AQUI / "imagens"
LOGO = PROJETO / "app" / "estatico" / "marca" / "logo.png"
SIMBOLO = PROJETO / "app" / "estatico" / "marca" / "simbolo.png"
SAIDA = PROJETO / "docs" / "Pyron_Funcionalidades.pdf"
VERSAO = "0.7.0"

# Cores dos tokens da interface (app/estatico/tokens.css).
TINTA = colors.HexColor("#171B33")
TEXTO_2 = colors.HexColor("#4A5270")
TEXTO_3 = colors.HexColor("#5F6886")
AZUL = colors.HexColor("#3F50D6")
AZUL_800 = colors.HexColor("#2A358F")
AZUL_700 = colors.HexColor("#3341B3")
AZUL_50 = colors.HexColor("#EEF1FF")
VIOLETA = colors.HexColor("#7D5CF0")
VIOLETA_50 = colors.HexColor("#F5F2FF")
VIOLETA_900 = colors.HexColor("#2C2787")
BORDA = colors.HexColor("#DFE3EE")
FUNDO = colors.HexColor("#F6F7FB")
SEVERIDADE = {
    "Normal": ("#179B67", "#E3F6EE"), "Atenção": ("#D9A40B", "#FDF4D6"), "Programar": ("#E8751A", "#FDEBDC"),
    "Urgente": ("#DC3F26", "#FCE6E1"), "Imediato": ("#B0123A", "#FAE3EA"),
}

LARGURA = A4[0] - 36 * mm


def _fontes() -> None:
    raiz = Path("C:/Windows/Fonts")
    pares = {"Pyron": "segoeui.ttf", "Pyron-Bold": "segoeuib.ttf", "Pyron-Semi": "seguisb.ttf", "Pyron-Mono": "consola.ttf"}
    for nome, arquivo in pares.items():
        pdfmetrics.registerFont(TTFont(nome, str(raiz / arquivo)))
    pdfmetrics.registerFontFamily("Pyron", normal="Pyron", bold="Pyron-Bold", italic="Pyron", boldItalic="Pyron-Bold")


_fontes()
E = {
    "corpo": ParagraphStyle("corpo", fontName="Pyron", fontSize=10, leading=15, textColor=TINTA, spaceAfter=6),
    "nota": ParagraphStyle("nota", fontName="Pyron", fontSize=8.5, leading=12, textColor=TEXTO_3),
    "legenda": ParagraphStyle("legenda", fontName="Pyron", fontSize=8.5, leading=12, textColor=TEXTO_3, spaceBefore=3, spaceAfter=12, alignment=TA_CENTER),
    "sobre": ParagraphStyle("sobre", fontName="Pyron-Bold", fontSize=8, leading=11, textColor=VIOLETA, spaceAfter=2),
    "h1": ParagraphStyle("h1", fontName="Pyron-Bold", fontSize=20, leading=26, textColor=AZUL_800, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="Pyron-Semi", fontSize=13, leading=18, textColor=TINTA, spaceBefore=10, spaceAfter=4),
    "cel": ParagraphStyle("cel", fontName="Pyron", fontSize=9, leading=12.5, textColor=TINTA),
    "celb": ParagraphStyle("celb", fontName="Pyron-Bold", fontSize=8.5, leading=11, textColor=colors.white),
    "celc": ParagraphStyle("celc", fontName="Pyron-Semi", fontSize=9, leading=12.5, textColor=TINTA),
    "mono": ParagraphStyle("mono", fontName="Pyron-Mono", fontSize=8.5, leading=12, textColor=TINTA),
    "toc1": ParagraphStyle("toc1", fontName="Pyron", fontSize=10.5, leading=20, textColor=TINTA),
}


# ---------------------------------------------------------------- blocos de conteúdo

def p(texto: str, estilo: str = "corpo") -> Paragraph:
    return Paragraph(texto, E[estilo])


def secao(numero: int, titulo: str, sobre: str, nova_pagina: bool = True) -> list:
    cabeca = Paragraph(f"{numero}. {titulo}", E["h1"])
    cabeca.toc = f"{numero}. {titulo}"
    return [PageBreak() if nova_pagina else Spacer(1, 16), p(sobre.upper(), "sobre"), cabeca]


def lista(itens: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(p(t), leftIndent=12, value="•") for t in itens],
        bulletType="bullet", bulletColor=AZUL, bulletFontName="Pyron-Bold", leftIndent=12, spaceAfter=6,
    )


def figura(arquivo: str, legenda: str, largura: float = LARGURA) -> list:
    caminho = IMAGENS / arquivo
    if not caminho.exists():
        return []
    # Captura em JPEG de boa qualidade: o PDF fica leve sem perder a leitura dos textos da tela.
    original = PILImage.open(caminho).convert("RGB")
    w, h = original.size
    buf = io.BytesIO()
    original.save(buf, format="JPEG", quality=88, optimize=True)
    buf.seek(0)
    img = Image(buf, width=largura, height=largura * h / w)
    moldura = Table([[img]], colWidths=[largura])
    moldura.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, BORDA), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                 ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return [KeepTogether([moldura, p(legenda, "legenda")])]


def tabela(cabecalho: list[str], linhas: list[list], larguras: list[float], cores_linha: dict | None = None) -> Table:
    dados = [[Paragraph(c, E["celb"]) for c in cabecalho]]
    for linha in linhas:
        dados.append([c if not isinstance(c, str) else Paragraph(c, E["cel"]) for c in linha])
    t = Table(dados, colWidths=[w * mm for w in larguras], repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL_800), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, BORDA), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]
    for i, cor in (cores_linha or {}).items():
        estilo.append(("LINEBEFORE", (0, i), (0, i), 3, colors.HexColor(cor)))
    t.setStyle(TableStyle(estilo))
    return t


def selo(nome: str) -> Paragraph:
    forte, fundo = SEVERIDADE[nome]
    return Paragraph(f'<font color="{forte}">●</font> <b>{nome}</b>', E["cel"])


def destaque(titulo: str, texto: str, cor=AZUL, fundo=AZUL_50) -> Table:
    t = Table([[Paragraph(f"<b>{titulo}</b><br/>{texto}", E["cel"])]], colWidths=[LARGURA])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fundo), ("LINEBEFORE", (0, 0), (0, -1), 3, cor),
                           ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                           ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    return t


# ---------------------------------------------------------------- páginas

class Documento(BaseDocTemplate):
    def __init__(self, arquivo: str):
        super().__init__(arquivo, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=18 * mm,
                         title="Pyron: manual de funcionalidades", author="Pyron", subject="Manutenção preditiva por termografia")
        quadro = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="corpo")
        self.addPageTemplates([
            PageTemplate(id="capa", frames=[quadro], onPage=self._capa),
            PageTemplate(id="miolo", frames=[quadro], onPage=self._miolo),
        ])

    def afterFlowable(self, flowable) -> None:
        if hasattr(flowable, "toc"):
            self.notify("TOCEntry", (0, flowable.toc, self.page))

    @staticmethod
    def _capa(canvas, doc) -> None:
        w, h = A4
        canvas.saveState()
        # faixa azul com subtom violeta, como a barra lateral do aplicativo
        passos = 60
        for i in range(passos):
            f = i / (passos - 1)
            cor = colors.Color(*(a + (b - a) * f for a, b in zip((0x33 / 255, 0x41 / 255, 0xB3 / 255), (0x2C / 255, 0x27 / 255, 0x87 / 255))))
            canvas.setFillColor(cor)
            canvas.rect(0, (i / passos) * 70 * mm, w, 70 * mm / passos + 0.5, stroke=0, fill=1)
        lado = 118 * mm
        canvas.drawImage(str(LOGO), (w - lado * 0.85) / 2, h - 40 * mm - lado, width=lado * 0.85, height=lado, mask="auto", preserveAspectRatio=True)
        canvas.setFillColor(AZUL_800)
        canvas.setFont("Pyron-Bold", 26)
        canvas.drawCentredString(w / 2, 108 * mm, "Manual de funcionalidades")
        canvas.setFillColor(TEXTO_3)
        canvas.setFont("Pyron", 12)
        canvas.drawCentredString(w / 2, 99 * mm, "Tudo o que o software apresenta, tela por tela")
        canvas.setFillColor(colors.white)
        canvas.setFont("Pyron-Semi", 11)
        canvas.drawString(18 * mm, 40 * mm, f"Pyron {VERSAO}")
        canvas.setFont("Pyron", 10)
        canvas.drawString(18 * mm, 33 * mm, "Manutenção preditiva por termografia para transformadores e subestações")
        canvas.drawString(18 * mm, 27 * mm, date.today().strftime("%d/%m/%Y"))
        canvas.restoreState()

    @staticmethod
    def _miolo(canvas, doc) -> None:
        w, h = A4
        canvas.saveState()
        canvas.drawImage(str(SIMBOLO), 18 * mm, h - 15 * mm, width=6 * mm, height=6 * mm, mask="auto")
        canvas.setFont("Pyron-Semi", 8.5)
        canvas.setFillColor(AZUL_800)
        canvas.drawString(26 * mm, h - 13 * mm, "PYRON")
        canvas.setFont("Pyron", 8.5)
        canvas.setFillColor(TEXTO_3)
        canvas.drawString(38 * mm, h - 13 * mm, "Manual de funcionalidades")
        canvas.setStrokeColor(BORDA)
        canvas.setLineWidth(0.6)
        canvas.line(18 * mm, h - 17 * mm, w - 18 * mm, h - 17 * mm)
        canvas.drawRightString(w - 18 * mm, 10 * mm, f"Página {doc.page}")
        canvas.drawString(18 * mm, 10 * mm, f"Pyron {VERSAO} · tudo roda neste computador")
        canvas.restoreState()


# ---------------------------------------------------------------- conteúdo

def conteudo() -> list:
    c: list = [NextPageTemplate("miolo"), PageBreak()]
    mono = lambda t: f"<font name='Pyron-Mono'>{t}</font>"  # noqa: E731

    # sumário
    toc = TableOfContents()
    toc.levelStyles = [E["toc1"]]
    toc.dotsMinLevel = 0
    c += [p("CONTEÚDO", "sobre"), Paragraph("Sumário", E["h1"]), toc]

    # 1
    c += secao(1, "O que é o Pyron", "Visão geral")
    c += [
        p("O Pyron é um software de <b>manutenção preditiva por termografia</b> para transformadores e equipamentos de subestação. "
          "Ele lê a temperatura de cada ponto da imagem da câmera térmica, encontra os pontos quentes e os componentes, compara cada um "
          "com o <b>limite do próprio componente</b> e com as <b>outras fases</b>, classifica a severidade pela NBR 15866 e entrega o laudo em PDF. "
          "Depois disso, acompanha cada equipamento ao longo do tempo: <b>histórico, tendência da temperatura, próxima inspeção</b> e as "
          "<b>pendências</b> até a correção ser verificada."),
        p("Saber o ponto mais quente não basta: 55 °C numa conexão é normal ou grave dependendo do quanto ela aguenta, da carga no momento "
          "e de como estão as outras fases. Por isso cada região é comparada com uma referência, e o laudo mostra de onde veio cada número."),
        p("Para quem", "h2"),
        lista([
            "Equipes de manutenção de concessionárias, indústrias e subestações próprias.",
            "Empresas de termografia que inspecionam e emitem laudos para clientes.",
            "Engenharia de ativos, que precisa de histórico, tendência e prioridade de reparo.",
        ]),
        p("Princípios", "h2"),
        lista([
            "<b>Tudo local.</b> Imagens, inspeções e laudos ficam neste computador. Nada é enviado para a internet sem o usuário mandar.",
            "<b>Critério explícito.</b> Os limites vêm de normas (ABNT NBR 15572, 15866 e 15424) e podem ser conferidos e ajustados.",
            "<b>O responsável assina.</b> O laudo sai pronto para revisar; o profissional habilitado revisa e assina com a ART.",
            "<b>Interface industrial e clara.</b> Fundo claro, azul nas ações, cor forte só para os dados: termograma e severidade.",
        ]),
        p("Mapa das funcionalidades", "h2"),
        tabela(["Área", "O que faz"], [
            ["<b>Painel</b>", "Críticas, pendências e inspeções vencidas, distribuição por severidade, próximas inspeções e monitoramento."],
            ["<b>Nova análise</b>", "Recebe um ou vários termogramas, já associados a um equipamento se quiser, e abre o resultado."],
            ["<b>Análise</b>", "Visualizador térmico, regiões, ponto e linha de medição, escala manual, emissividade, comparação com a inspeção anterior."],
            ["<b>Vídeo ao vivo</b>", "Analisa o vídeo da câmera quadro a quadro, como se estivesse ao vivo, e mede o ritmo do detector."],
            ["<b>Inspeções</b>", "Histórico com filtros, seleção de várias imagens, relatório conjunto, equipamento em lote e planilha."],
            ["<b>Equipamentos</b>", "Histórico de cada equipamento, tendência em °C por mês, projeção até o limite e próxima inspeção."],
            ["<b>Pendências</b>", "Cada anomalia com prazo, ordem de serviço, responsável e histórico até a correção verificada."],
            ["<b>Monitoramento</b>", "Pasta vigiada da câmera (ou uma subpasta por equipamento), análise automática e alerta para o WhatsApp."],
            ["<b>Modelos e Avaliação</b>", "Detectores instalados (regra, IA e combinado), treino e comparação de modelos."],
            ["<b>Configurações</b>", "Empresa, logotipo, responsáveis, critério, limites por componente, aparência, dados e backup."],
        ], [38, LARGURA / mm - 38]),
    ]

    # 2
    c += secao(2, "Como abrir e fechar", "Primeiros passos")
    c += [
        lista([
            "Dois cliques em <b>Pyron.exe</b> na área de trabalho. Aparece a tela de abertura com a logo e uma barra de progresso; "
            "em poucos segundos a interface abre numa janela própria, sem barra de endereço.",
            "Um novo clique com o Pyron aberto só abre outra janela; os dados são os mesmos.",
            "Para fechar, feche a janela. O servidor interno desliga sozinho quando a última janela é fechada.",
            f"Diagnóstico: {mono('Pyron.exe --verificar')} sobe o servidor escondido, confere se respondeu e desliga. "
            f"O resultado fica em {mono('app/dados_app/verificacao.txt')}.",
        ]),
    ]
    c += figura("m_abertura.png", "Tela de abertura do Pyron.exe enquanto o motor de análise carrega.", 110 * mm)
    c += [
        p("Requisitos", "h2"),
        lista([
            "Windows 10 ou 11 com Microsoft Edge (a janela do aplicativo usa o Edge em modo aplicativo).",
            f"O ambiente Python do projeto (pasta {mono('.venv')}), criado pela instalação descrita no README.",
            "Para treinar modelos de IA: placa de vídeo NVIDIA (testado com RTX 3050, 4 GB). Para usar um modelo pronto, não precisa.",
        ]),
    ]

    # 3
    c += secao(3, "A interface", "Como está organizada")
    c += [
        p("Todas as telas têm a mesma estrutura: a <b>barra lateral azul</b> à esquerda, a <b>barra superior</b> com a busca e o estado, e o conteúdo no centro."),
        p("Barra lateral", "h2"),
        lista([
            "<b>Operação:</b> Painel, Nova análise, Vídeo ao vivo, Inspeções (com a quantidade), Equipamentos (com as inspeções vencidas), "
            "Pendências (com as de prazo vencido) e Monitoramento (com o ponto de estado e os alertas pendentes).",
            "<b>Sistema:</b> Modelos, Avaliação e Configurações. No rodapé, o detector em uso e a página Sobre, com a versão.",
        ]),
        p("Barra superior e busca rápida", "h2"),
        lista([
            "Trilha de navegação: onde você está (por exemplo, Operação › Equipamentos › TR-01).",
            "<b>Buscar</b> (ou Ctrl + K): acha inspeções pelo arquivo, equipamento, instalação, data ou severidade, equipamentos, telas e ações "
            "como exportar a planilha ou trocar o tema. Setas para escolher, Enter para abrir.",
            "Estado do servidor local e do monitoramento, sino de alertas e o botão <b>Nova análise</b>.",
            "A tecla <b>?</b> mostra todos os atalhos de teclado.",
        ]),
    ]
    c += figura("m_busca.png", "Busca rápida (Ctrl + K) com o equipamento TR-01 digitado: telas, equipamentos e inspeções no mesmo lugar.")
    c += [
        p("Comportamento de todas as telas", "h2"),
        lista([
            "<b>Carregando:</b> a tela mostra a forma do conteúdo (esqueleto) enquanto os dados chegam.",
            "<b>Vazio:</b> uma explicação do que vai aparecer ali e o botão da próxima ação.",
            "<b>Erro:</b> o que aconteceu e o botão Tentar de novo. <b>Sem conexão:</b> uma faixa no topo, se o servidor parar de responder.",
            "Avisos rápidos no canto inferior direito confirmam cada ação; alguns têm Desfazer ou um atalho (Abrir, Ver equipamento).",
            "Tema claro (padrão) ou escuro, em Configurações › Aparência ou pela busca. O termograma fica sempre sobre fundo índigo escuro.",
        ]),
    ]

    # 4
    c += secao(4, "Painel", "Operação")
    c += figura("m_painel.png", "Painel com indicadores, inspeções mais graves, distribuição por severidade e próximas inspeções.")
    c += [
        lista([
            "<b>Indicadores:</b> inspeções, críticas (urgente ou imediato), <b>pendências vencidas</b>, <b>inspeções vencidas</b> por equipamento e "
            "alertas pendentes do monitoramento. Cada indicador leva à lista já filtrada.",
            "<b>Atenção agora:</b> as inspeções mais graves, com o equipamento, a região crítica e o valor que decidiu (por exemplo, 79% da MTA).",
            "<b>Distribuição por severidade:</b> barra empilhada e contagem de cada nível.",
            "<b>Próximas inspeções:</b> os equipamentos pela data da próxima inspeção, vencidos primeiro.",
            "<b>Monitoramento:</b> estado, pasta vigiada, última verificação e os alertas mais recentes.",
        ]),
    ]

    # 5
    c += secao(5, "Nova análise", "Operação")
    c += figura("m_nova.png", "Área para soltar os termogramas, o fluxo da análise, a instalação e o equipamento opcionais e as inspeções recentes.")
    c += [
        lista([
            "Arraste as imagens para a área tracejada ou use <b>Escolher arquivos</b> (Ctrl + O, em qualquer tela). Também dá para soltar "
            "imagens em qualquer lugar da janela; um vídeo solto vai para o Vídeo ao vivo.",
            "<b>Já sabe de onde são as imagens?</b> Preencha a instalação e o equipamento (com sugestões dos nomes já usados) e as imagens "
            "entram direto no histórico daquele equipamento.",
            "<b>Uma imagem</b> abre direto para revisão; <b>várias</b> são analisadas em lote, com a severidade de cada uma.",
        ]),
        p("Dois tipos de imagem", "h2"),
        tabela(["Tipo", "Como o Pyron lê", "Como aparece"], [
            ["JPEG radiométrico (FLIR)", "Lê os dados brutos da câmera e converte em temperatura com emissividade, distância, temperatura refletida, "
             "umidade e as constantes da própria câmera.", "Etiqueta verde <b>Temperatura medida</b>."],
            ["Imagem colorida com escala", "Lê os números da escala por OCR e converte cada cor na temperatura da paleta. "
             "Testado em 893 imagens: erro mediano de 0,5 °C e escala lida em 100% delas.", "Etiqueta amarela <b>Temperatura estimada pelas cores</b>."],
        ], [38, 90, LARGURA / mm - 128]),
    ]

    # 6
    c += secao(6, "Análise de uma imagem", "Operação")
    c += figura("m_analise.png", "Análise aberta: termograma com regiões, ponto P2, linha L1 e escala manual; à direita o resultado, "
                                 "o acompanhamento da anomalia e a comparação com a inspeção anterior.")
    c += [
        p("Visualizador térmico", "h2"),
        lista([
            "<b>Paletas:</b> Ferro, Arco-íris e Cinza. <b>Escala:</b> Equipamento (realça o equipamento), Cena (da menor à maior temperatura) "
            "ou <b>Manual</b> (você escolhe o mínimo e o máximo). A paleta e a escala ficam guardadas e o laudo sai igual à tela.",
            "<b>Temperatura sob o cursor</b>, marcada também na barra de cores. <b>Isoterma:</b> destaca tudo acima de uma temperatura. "
            "<b>Foto:</b> mostra a foto visível da câmera ao lado.",
            "<b>Camadas:</b> com peças (modelo de IA) e pontos quentes juntos, escolha Tudo, Peças ou Pontos quentes. "
            "<b>Rótulos</b> (tecla R) liga e desliga os nomes; eles nunca se sobrepõem.",
        ]),
        p("Ferramentas de medição", "h2"),
        tabela(["Ferramenta", "Tecla", "O que faz"], [
            ["Selecionar", "S", "Escolhe uma região na imagem ou na lista."],
            ["Região", "D", "Arraste uma caixa: a região é medida e classificada como as do detector."],
            ["Ponto", "P", "Clique: lê a temperatura daquele pixel (P1, P2...)."],
            ["Linha", "L", "Arraste: mostra o perfil de temperatura ao longo da linha, com máxima, mínima e média (L1, L2...)."],
        ], [30, 16, LARGURA / mm - 46]),
        Spacer(1, 6),
        p("Pontos e linhas ficam guardados na inspeção, aparecem na lista Pontos e linhas (com o gráfico do perfil) e vão para o laudo.", "nota"),
    ]
    c += figura("m_camadas.png", "Para-raios analisados pelo modelo de IA combinado com a regra de pontos quentes, mostrando só a camada Peças.")
    c += figura("m_isoterma.png", "Isoterma ligada: tudo abaixo da temperatura escolhida fica cinza.")
    c += [
        p("Resultado", "h2"),
        lista([
            "<b>Veredito:</b> o nível mais grave, onde está, por qual critério e o que fazer.",
            "<b>Indicadores:</b> máxima da cena, a região mais perto do limite (% da MTA) ou o maior ΔT entre fases, e a quantidade de regiões.",
            "<b>Ponto mais quente nas peças</b> e a <b>comparação entre peças iguais</b> das três fases.",
            "<b>Acompanhamento da anomalia:</b> situação, prazo e ordem de serviço (veja Pendências).",
            "<b>Inspeção anterior deste equipamento:</b> quanto a máxima mudou desde a última e o botão <b>Lado a lado</b>.",
            "<b>Setas no cabeçalho</b> (por exemplo, 5 de 7) para andar pelas inspeções do mesmo equipamento.",
        ]),
    ]
    c += figura("m_lado_a_lado.png", "Lado a lado: a inspeção anterior e a atual do mesmo equipamento, cada uma com a severidade e a máxima.")
    c += figura("m_condicoes.png", "Aba Condições: ambiente e carga, parâmetros de medição com a tabela de materiais e os dados da câmera.")
    c += [
        lista([
            "<b>Condições:</b> com a temperatura ambiente e a carga no momento, cada região é projetada para plena carga e comparada com a MTA.",
            "<b>Parâmetros de medição</b> (só termograma radiométrico): emissividade (com uma tabela de materiais: porcelana, polímero, cobre "
            "oxidado, aço galvanizado...), temperatura refletida, distância, umidade e temperatura do ar. A temperatura é recalculada a partir "
            "do arquivo original; <b>Voltar aos valores da câmera</b> desfaz.",
            "<b>Laudo:</b> instalação, equipamento, responsável (do cadastro), ART e observações.",
            "<b>Exportar</b> (botão com a seta para baixo): imagem PNG com regiões, pontos e linhas; temperaturas de todos os pixels em CSV "
            "(abre no Excel); ou o laudo.",
            "<b>Detectar de novo:</b> escolha outro detector no topo; as regiões desenhadas à mão são mantidas.",
        ]),
    ]

    # 7
    c += secao(7, "Como a severidade é decidida", "Critério técnico")
    c += [
        p("Temperatura sozinha não diz nada. A NBR 15866 pede que cada ponto quente seja comparado com uma referência. "
          "O Pyron usa duas referências e fica com a <b>pior</b> das duas:"),
        destaque("1. Máxima temperatura admissível (MTA) do componente",
                 f"A temperatura medida é projetada para plena carga: {mono('T_proj = T_amb + (T − T_amb) × (100 / carga)²')}. "
                 "O resultado é comparado com quanto o componente aguenta."),
        Spacer(1, 6),
        destaque("2. ΔT entre componentes semelhantes",
                 "A mesma peça nas três fases, sob a mesma carga, deveria ter a mesma temperatura. A diferença para a mediana das fases indica defeito.",
                 VIOLETA, VIOLETA_50),
        p("Faixas de prioridade (modelo brasileiro)", "h2"),
        tabela(["Nível", "% da MTA", "ΔT entre fases (condutores)", "Para-raios e isoladores", "O que fazer"], [
            [selo("Atenção"), "acima de 60%", "5 a 10 °C", "2 a 5 °C", "Corrigir na próxima manutenção."],
            [selo("Programar"), "acima de 70%", "acima de 10 a 20 °C", "5 a 10 °C", "Agendar a correção e reinspecionar."],
            [selo("Urgente"), "acima de 80%", "acima de 20 a 40 °C", "acima de 10 °C", "Corrigir o mais rápido possível."],
            [selo("Imediato"), "acima de 100%", "acima de 40 °C", "–", "Corrigir imediatamente."],
        ], [26, 24, 42, 36, LARGURA / mm - 128]),
        Spacer(1, 6),
        lista([
            "<b>Para-raios e isoladores</b> aquecem por corrente de fuga, não por carga: têm faixas próprias e não recebem a correção de carga.",
            "<b>Carga limite:</b> o Pyron calcula com quanto de carga o componente chega à MTA.",
            "<b>Classificação indicativa:</b> sem ambiente, sem carga e sem fase semelhante, o nível aparece marcado como indicativo.",
            "<b>NETA MTS:</b> o critério americano (ΔT sobre o ar ambiente) pode ser carregado como modelo em Configurações.",
            "Mudou o critério ou a biblioteca? Todas as inspeções salvas são recalculadas.",
        ]),
        p("Máximas admissíveis de partida (biblioteca de componentes)", "h2"),
        tabela(["Componente", "MTA", "Fonte"], [
            ["Conexões, terminais, pontos quentes", "90 °C", "Prática brasileira para componentes metálicos; IEC 62271-1 (100 a 115 °C conforme o contato)."],
            ["Terminal de bucha", "95 °C", "IEC 60137: 55 K de elevação sobre 40 °C de ambiente."],
            ["Cabo isolado (PVC)", "70 °C", "NBR 5410 (XLPE/EPR: 90 °C)."],
            ["Tanque e radiador (óleo no topo)", "100 °C", "NBR 5356-2 / IEC 60076-2: 60 K sobre 40 °C."],
            ["Para-raio, isolador, parte isoladora", "não se aplica", "Comparar as fases (IEC 60099-5)."],
        ], [52, 24, LARGURA / mm - 76]),
        Spacer(1, 6),
        p("Os valores são de partida e ficam editáveis. Confira sempre com o dado do fabricante, a edição vigente da NBR 15866 e o termografista responsável.", "nota"),
    ]

    # 8
    c += secao(8, "Relatório de inspeção (PDF)", "Documento técnico")
    c += [
        p("<b>Gerar laudo</b> (na análise) ou <b>Gerar relatório</b> (com várias inspeções marcadas, ou o relatório do equipamento) pede o "
          "<b>responsável técnico do cadastro</b> e a ART, e abre o PDF pronto para revisar, imprimir e assinar. Ele traz:"),
        lista([
            "Cabeçalho com o <b>logotipo</b>, o nome e o subtítulo da empresa, o número do relatório (RT-AAAAMMDD-XXXX) e a data de emissão.",
            "1. Identificação: instalação, equipamentos, período das inspeções, termovisor e responsável.",
            "2. Normas e critério: ABNT NBR 15572:2013, NBR 15866:2010 e NBR 15424, o método, as faixas e a recomendação de cada nível.",
            "3. Resumo dos resultados (com várias imagens) e, quando todas são do mesmo equipamento, o <b>histórico</b> com o gráfico da máxima "
            "por inspeção e a tendência em °C por mês.",
            "4. Um registro por imagem: termograma numerado na paleta e escala escolhidas, foto visível, condições de medição, tabela de pontos, "
            "pontos e linhas de medição, comparação entre peças semelhantes e observações.",
            "Conclusão com as anomalias, referências de temperatura e o bloco do responsável técnico com registro, ART, local, data e assinatura.",
        ]),
    ]
    c += figura("m_laudo1.png", "Primeira página do relatório do equipamento TR-01 (dados de demonstração).", 120 * mm)
    c += figura("m_laudo_historico.png", "Resumo e histórico do equipamento: a máxima de cada inspeção, na cor da severidade, com a tendência.", 120 * mm)
    c += figura("m_laudo2.png", "Registro de uma imagem: termograma numerado, foto visível, condições, pontos e comparação entre peças.", 120 * mm)

    # 9
    c += secao(9, "Inspeções", "Operação")
    c += figura("m_inspecoes.png", "Lista de inspeções com três marcadas: a barra de seleção oferece definir o equipamento e gerar o relatório.")
    c += [
        lista([
            "<b>Tabela</b> (padrão) ou <b>miniaturas</b>; colunas com termograma, arquivo, data da captura, equipamento (link para a página "
            "dele), região crítica, máxima e severidade.",
            "<b>Indicadores clicáveis</b> filtram por severidade; <b>busca</b> por arquivo, instalação ou equipamento; <b>ordem</b> por data da captura, "
            "gravidade ou nome.",
            "<b>Marque várias</b> (caixa de seleção) para <b>Definir equipamento</b> de todas de uma vez ou <b>Gerar relatório</b> com todas.",
            "<b>Exportar planilha</b>: todas as inspeções em CSV que abre direto no Excel.",
        ]),
    ]

    # 10
    c += secao(10, "Equipamentos", "Histórico e tendência")
    c += figura("m_equipamentos.png", "Equipamentos agrupados por instalação, com a máxima ao longo do tempo, a tendência e a próxima inspeção.")
    c += [
        p("Cada imagem pode pertencer a uma instalação e a um equipamento (no envio, na aba Laudo da análise ou em Inspeções). "
          "A partir daí o Pyron monta, para cada equipamento:"),
        lista([
            "<b>Histórico:</b> a máxima de cada inspeção pela data da captura, na cor da severidade; clique num ponto para abrir a inspeção.",
            "<b>Tendência em °C por mês</b>, por mínimos quadrados, a partir de 3 inspeções espalhadas por pelo menos um mês (em poucos dias, "
            "a diferença é de carga e horário, não de desgaste). A reta aparece tracejada no gráfico.",
            "<b>A plena carga:</b> quando as inspeções têm temperatura ambiente e carga, a série pode ser vista como a elevação sobre o ambiente "
            f"projetada para plena carga, {mono('ΔT × (100 / carga)²')}, que compara inspeções feitas com cargas diferentes.",
            "<b>Projeção até a MTA:</b> se o % da MTA sobe, em quanto tempo chegaria a 100% mantida a tendência (estimativa, até 5 anos).",
            "<b>Próxima inspeção</b> pela severidade atual: 1 ano quando normal (a NFPA 70B pede ao menos uma vez por ano), 90 dias em atenção, "
            "30 em programar, 7 em urgente e 1 em imediato. O menu mostra quantas estão vencidas.",
            "<b>Peças:</b> a máxima de cada tipo de peça ao longo do tempo, para ver qual está esquentando.",
            "<b>Adicionar imagens</b> analisa imagens novas já como inspeções do equipamento; <b>Relatório do equipamento</b> junta todas.",
        ]),
    ]
    c += figura("m_equipamento.png", "Página do equipamento TR-01: estado, máxima, tendência a plena carga, próxima inspeção, gráfico, peças e histórico.")

    # 11
    c += secao(11, "Pendências", "Da anomalia à correção")
    c += figura("m_pendencias.png", "Pendências com severidade, equipamento, data, prazo, situação e ordem de serviço.")
    c += [
        p("Toda inspeção fora do normal vira uma pendência. O fluxo é o de uma equipe de manutenção:"),
        tabela(["Situação", "Quando usar"], [
            ["<b>Aberta</b>", "Acabou de ser encontrada. O prazo sai da severidade (1, 7, 30 ou 90 dias depois da captura) e pode ser trocado."],
            ["<b>Programada</b>", "O reparo tem data e número de ordem de serviço."],
            ["<b>Corrigida</b>", "O reparo foi feito; aguarda a reinspeção."],
            ["<b>Verificada</b>", "A reinspeção mostrou o componente normal. Uma inspeção normal posterior do mesmo equipamento é sugerida."],
            ["<b>Descartada</b>", "Falso alarme (reflexo do sol, por exemplo) ou peça já substituída."],
        ], [32, LARGURA / mm - 32]),
        Spacer(1, 6),
        p("Cada mudança vai para o histórico, com data e nota. As pendências vencidas aparecem no Painel e no menu.", "nota"),
    ]
    c += figura("m_pendencia_dialogo.png", "Atualizar uma pendência: situação, prazo, ordem de serviço, responsável, nota e o histórico.", 130 * mm)

    # 12
    c += secao(12, "Vídeo ao vivo", "Simulação de câmera")
    c += figura("m_video.png", "Vídeo analisado quadro a quadro: caixas sobre a imagem, ritmo real, tempo por quadro, gráfico da máxima e anomalias.")
    c += [
        lista([
            "Envie a gravação da tela da câmera (MP4, AVI, MOV ou MKV, com a barra de escala visível). Cada quadro passa pelo mesmo caminho "
            "de uma foto: escala, temperatura, detector, medição e severidade.",
            "<b>Ao vivo:</b> o vídeo corre no relógio, como a câmera; enquanto o detector trabalha, os quadros que passam se perdem. "
            "Mostra o que o sistema acompanharia de verdade neste computador. <b>Um quadro a cada intervalo:</b> analisa sem perder nenhum.",
            "Depois, reproduza no ritmo em que os quadros foram analisados (espaço, setas), pule pelo gráfico ou pelos momentos com anomalia "
            "e use <b>Salvar quadro como inspeção</b> para ter o laudo daquele instante.",
            "Os números da escala só passam pelo OCR quando mudam; com a escala travada na câmera, informe os limites e a leitura fica exata.",
        ]),
    ]

    # 13
    c += secao(13, "Monitoramento e alertas", "Operação")
    c += figura("m_monitor.png", "Estado do monitoramento, fonte das imagens, regra de alerta, responsáveis e a prévia da mensagem.")
    c += [
        lista([
            "<b>Fonte das imagens:</b> a pasta onde a câmera, o cartão sincronizado, o FTP da câmera fixa ou o FLIR Thermal Studio gravam. "
            "Ao ligar, o que já estava na pasta fica de fora.",
            "<b>Cada subpasta é um equipamento:</b> com a opção marcada, uma imagem em Entrada\\TR-01 entra no histórico do TR-01. "
            "Bom para câmeras fixas, uma pasta por câmera.",
            "<b>Regra de alerta:</b> severidade mínima e intervalo para não repetir o mesmo nível; se piorar, o alerta sai na hora.",
            "<b>Responsáveis:</b> nome e WhatsApp. O Pyron prepara a mensagem e um clique abre o WhatsApp com ela pronta.",
            "Os alertas ficam com a situação pendente, enviado ou resolvido; o sino do topo mostra os pendentes.",
        ]),
        p("Em desenvolvimento", "h2"),
        tabela(["Item", "O que vai fazer"], [
            ["Conexão direta com a câmera", "RTSP/ONVIF e FLIR Atlas SDK, sem depender de pasta."],
            ["WhatsApp automático", "Envio pela API oficial do WhatsApp Business."],
            ["Serviço do Windows", "Monitoramento rodando mesmo com a janela do Pyron fechada."],
        ], [52, LARGURA / mm - 52]),
    ]

    # 14
    c += secao(14, "Modelos e avaliação", "Sistema")
    c += figura("m_modelos.png", "Detectores disponíveis: a regra de pontos quentes, o modelo de para-raios e o combinado dos dois.")
    c += [
        lista([
            "<b>Pontos quentes (regra):</b> embutido, sem IA. Aponta trechos mais quentes que o equipamento em volta.",
            "<b>Modelos treinados (IA):</b> por exemplo, o RF-DETR de para-raios (terminal superior, aletas isoladoras, terminal inferior), "
            "com mAP50 de 0,89 no teste. <b>Modelo + pontos quentes</b> junta os dois: diz em qual peça está o calor e compara as fases.",
            "<b>Treino:</b> rotule com caixas no CVAT, exporte em COCO 1.0 e siga o passo a passo da tela, aqui (com placa NVIDIA) ou no Colab.",
        ]),
    ]
    c += figura("m_avaliacao.png", "Avaliação: comparação dos detectores treinados (acertos, peças perdidas, curvas de treino e exemplos).")

    # 15
    c += secao(15, "Configurações", "Sistema")
    c += figura("m_identidade.png", "Empresa, logotipo e responsáveis técnicos cadastrados.")
    c += [
        tabela(["Aba", "O que dá para ajustar"], [
            ["Empresa e responsáveis", "Nome, subtítulo e <b>logotipo</b> no cabeçalho dos laudos; <b>responsáveis técnicos</b> (nome, função, registro). "
             "O laudo só sai com um responsável deste cadastro, para o nome e o registro nunca saírem digitados errado."],
            ["Critério de severidade", "Limites de % da MTA, ΔT entre semelhantes (condutores e dielétricos), ΔT sobre o ambiente (NETA, opcional), "
             "expoente da correção de carga e carga mínima; modelos Brasil e NETA."],
            ["Biblioteca de componentes", "MTA de cada classe de componente, com a fonte do valor."],
            ["Aparência", "Tema claro (padrão), escuro ou seguir o Windows."],
            ["Dados e sistema", "Onde ficam os dados, espaço ocupado, <b>backup</b> e restauração."],
        ], [44, LARGURA / mm - 44]),
    ]
    c += figura("m_criterio.png", "Critério de severidade em quatro grupos, com os modelos Brasil (NBR 15866) e NETA MTS.")
    c += figura("m_componentes.png", "Biblioteca de componentes: tipo de aquecimento, MTA editável e a fonte de cada valor.")

    # 16
    c += secao(16, "Dados, backup e instalação", "Sistema")
    c += figura("m_dados.png", "Dados e sistema: pastas, espaço ocupado, versão e o backup.")
    c += [
        lista([
            f"Inspeções, imagens, equipamentos, pendências, alertas e configurações ficam em {mono('app/dados_app')}, na pasta do projeto.",
            "<b>Baixar backup:</b> um .zip com tudo isso (vídeos enviados e treinos ficam de fora). Guarde fora do computador.",
            "<b>Restaurar backup:</b> troca os dados atuais pelos do .zip. Antes, uma cópia do que existe hoje fica na pasta de dados, em backups.",
            "O Pyron não envia nada para a internet. A única saída é quando o usuário clica em Abrir WhatsApp.",
            "Instalação do zero, atualização e geração do executável: README do projeto. Código: github.com/hugovieiraz/Pyron---Embrapii.",
        ]),
    ]

    # 17
    c += secao(17, "Limitações e próximos passos", "Roteiro", nova_pagina=False)
    c += [
        p("Limitações desta versão", "h2"),
        lista([
            "Detector de IA só para para-raios; para os outros equipamentos, a regra de pontos quentes dá uma classificação indicativa.",
            "As máximas admissíveis e as faixas precisam ser conferidas na edição vigente da NBR 15866, com os fabricantes e com termografista certificado.",
            "A tendência só é confiável comparando inspeções em condições parecidas, ou com ambiente e carga informados (série a plena carga).",
            "Na imagem só colorida, o ponto quente precisa estar dentro da escala de cores.",
            "O monitoramento depende do Pyron aberto e o envio do WhatsApp é manual.",
        ]),
        p("Próximos passos", "h2"),
        lista([
            "<b>Previsão com carga e clima</b> integrados (histórico de carga do SCADA) e tempo até ficar crítico com intervalo de confiança.",
            "<b>Detectores</b> para transformador, disjuntor e seccionadora.",
            "<b>Câmeras fixas:</b> conexão direta RTSP/ONVIF e FLIR Atlas SDK; <b>avisos</b> automáticos no WhatsApp e no celular.",
            "<b>Gêmeo térmico do transformador</b> (IEC 60076-7) e perda de vida da isolação.",
        ]),
    ]

    # apêndices
    c += [PageBreak(), p("APÊNDICE", "sobre")]
    cab = Paragraph("Atalhos e glossário", E["h1"])
    cab.toc = "Apêndice: atalhos e glossário"
    c += [cab,
          tabela(["Atalho", "Onde", "O que faz"], [
              ["Ctrl + K", "Qualquer tela", "Busca rápida: inspeções, equipamentos, telas e ações."],
              ["Ctrl + O", "Qualquer tela", "Escolher imagens para analisar."],
              ["?", "Qualquer tela", "Lista de atalhos."],
              ["S, D, P, L", "Análise aberta", "Selecionar, desenhar região, medir ponto, traçar linha."],
              ["R", "Análise e vídeo", "Rótulos sobre as caixas."],
              ["Esc", "Análise aberta", "Cancelar e voltar à seleção."],
              ["Delete", "Análise aberta", "Remover a região selecionada (com Desfazer)."],
              ["Espaço, ← →", "Vídeo", "Reproduzir ou pausar; quadro anterior e seguinte."],
          ], [28, 34, LARGURA / mm - 62]),
          Spacer(1, 10),
          tabela(["Termo", "Significado"], [
              ["MTA", "Máxima temperatura admissível: quanto o componente aguenta em operação contínua."],
              ["ΔT", "Diferença de temperatura: entre fases semelhantes ou sobre o ar ambiente."],
              ["Plena carga", "Corrente nominal do equipamento; a projeção leva a medição feita com carga menor até ela."],
              ["Tendência", "Quanto a temperatura sobe ou desce por mês, ajustada às inspeções do equipamento."],
              ["Radiométrico", "Imagem que guarda a temperatura de cada pixel, não só as cores."],
              ["Emissividade", "Quanto a superfície emite de radiação térmica; afeta a temperatura calculada."],
              ["Perfil", "Temperatura ao longo de uma linha traçada sobre o termograma."],
              ["Isoterma", "Destaque de tudo o que está acima de uma temperatura escolhida."],
              ["Pendência", "Anomalia em acompanhamento, com prazo, ordem de serviço e situação."],
              ["OS", "Ordem de serviço da manutenção que vai corrigir a anomalia."],
              ["Indicativa", "Classificação sem referência completa (ambiente, carga ou fase semelhante)."],
          ], [32, LARGURA / mm - 32])]
    return c


def main() -> None:
    doc = Documento(str(SAIDA))
    doc.multiBuild(conteudo())
    print("manual:", SAIDA, f"({SAIDA.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
