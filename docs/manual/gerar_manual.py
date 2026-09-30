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
VERSAO = "0.2.0"

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
          "Com o monitoramento, analisa sozinho as imagens que chegam da câmera e prepara o aviso para o responsável."),
        p("Saber o ponto mais quente não basta: 55 °C numa conexão é normal ou grave dependendo do quanto ela aguenta, da carga no momento "
          "e de como estão as outras fases. Por isso cada região é comparada com uma referência, e o laudo mostra de onde veio cada número."),
        p("Para quem", "h2"),
        lista([
            "Equipes de manutenção de concessionárias, indústrias e subestações próprias.",
            "Empresas de termografia que inspecionam e emitem laudos para clientes.",
            "Engenharia de ativos, que precisa de histórico e prioridade de reparo.",
        ]),
        p("Princípios", "h2"),
        lista([
            "<b>Tudo local.</b> Imagens, inspeções e laudos ficam neste computador. Nada é enviado para a internet sem o usuário mandar.",
            "<b>Critério explícito.</b> Os limites vêm de normas e podem ser conferidos e ajustados em Configurações.",
            "<b>O laudo é um rascunho técnico.</b> O responsável habilitado revisa e assina (NR-10), o Pyron poupa o trabalho repetitivo.",
            "<b>Interface industrial e clara.</b> Fundo claro, azul nas ações, cor forte só para os dados: termograma e severidade.",
        ]),
        p("Mapa das funcionalidades", "h2"),
        tabela(["Área", "O que faz"], [
            ["<b>Painel</b>", "Situação dos equipamentos: críticos, reparos a programar, alertas e distribuição por severidade."],
            ["<b>Nova análise</b>", "Recebe um ou vários termogramas, mede, detecta, classifica e abre o resultado para revisão."],
            ["<b>Análise</b>", "Visualizador térmico, regiões editáveis, severidade por região, condições de medição e dados do laudo."],
            ["<b>Laudo PDF</b>", "Documento com identificação, termograma, resultados, conclusão, referências e responsabilidade técnica."],
            ["<b>Inspeções</b>", "Histórico com busca, filtros, ordenação, tabela ou miniaturas, laudo e exclusão."],
            ["<b>Monitoramento</b>", "Pasta vigiada da câmera, análise automática, regra de alerta e mensagem pronta para o WhatsApp."],
            ["<b>Modelos</b>", "Detector em uso, modelos de IA instalados e o caminho para treinar novos."],
            ["<b>Configurações</b>", "Empresa, responsável, critério de severidade, limites por componente, aparência e dados."],
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
            "Diagnóstico: <font name='Pyron-Mono'>Pyron.exe --verificar</font> sobe o servidor escondido, confere se respondeu e desliga. "
            "O resultado fica em <font name='Pyron-Mono'>app/dados_app/verificacao.txt</font>.",
        ]),
    ]
    c += figura("m_abertura.png", "Tela de abertura do Pyron.exe enquanto o motor de análise carrega.", 110 * mm)
    c += [
        p("Requisitos", "h2"),
        lista([
            "Windows 10 ou 11 com Microsoft Edge (a janela do aplicativo usa o Edge em modo aplicativo).",
            "O ambiente Python do projeto (pasta <font name='Pyron-Mono'>.venv</font>), criado pela instalação descrita no README.",
            "Para treinar modelos de IA: placa de vídeo NVIDIA (testado com RTX 3050, 4 GB).",
        ]),
    ]

    # 3
    c += secao(3, "A interface", "Como está organizada")
    c += [
        p("Todas as telas têm a mesma estrutura: a <b>barra lateral azul</b> à esquerda, a <b>barra de status</b> no topo e o conteúdo no centro "
          "(veja a imagem da seção 4)."),
        p("Barra lateral", "h2"),
        lista([
            "<b>Operação:</b> Painel, Nova análise, Inspeções (com a quantidade) e Monitoramento (com o ponto de estado e os alertas pendentes).",
            "<b>Sistema:</b> Modelos e Configurações.",
            "No rodapé, o detector em uso e o acesso à página Sobre, com a versão.",
        ]),
        p("Barra superior", "h2"),
        lista([
            "Trilha de navegação: onde você está (por exemplo, Operação › Inspeções › FLIR0158.jpg).",
            "Estado do servidor local e do monitoramento; clique no monitoramento para abrir a tela dele.",
            "Sino de alertas com a quantidade pendente. Quando chega um alerta novo, aparece um aviso com o botão Ver.",
            "Botão <b>Nova análise</b>, sempre à mão (some só na própria tela de nova análise).",
        ]),
        p("Comportamento de todas as telas", "h2"),
        lista([
            "<b>Carregando:</b> a tela mostra a forma do conteúdo (esqueleto) enquanto os dados chegam.",
            "<b>Vazio:</b> uma explicação do que vai aparecer ali e o botão da próxima ação.",
            "<b>Erro:</b> o que aconteceu e o botão Tentar de novo.",
            "<b>Sem conexão:</b> uma faixa vermelha no topo, com Tentar de novo, se o servidor parar de responder.",
            "Avisos rápidos no canto inferior direito confirmam cada ação; alguns têm Desfazer.",
            "Tema claro (padrão) ou escuro, em Configurações › Aparência. O termograma fica sempre sobre fundo índigo escuro.",
        ]),
    ]

    # 4
    c += secao(4, "Painel", "Operação")
    c += figura("m_painel.png", "Painel com indicadores, inspeções mais graves, distribuição por severidade e monitoramento.")
    c += [
        lista([
            "<b>Indicadores:</b> total de inspeções (e quantas vieram do monitoramento), críticas (urgente ou imediato), reparos a programar "
            "e alertas pendentes. Cada indicador é um atalho para a lista já filtrada.",
            "<b>Atenção agora:</b> as inspeções mais graves, da pior para a menos grave, com o equipamento, a região crítica e o valor "
            "que decidiu (por exemplo, 98% da MTA ou ΔT de 12 °C entre fases). Clique na linha para abrir.",
            "<b>Distribuição por severidade:</b> barra empilhada e contagem de cada nível.",
            "<b>Monitoramento:</b> estado, pasta vigiada, última verificação, última imagem e os alertas mais recentes.",
            "Na primeira vez, sem inspeções, o Painel mostra um roteiro de três passos: analisar uma imagem, configurar a empresa e ligar o monitoramento.",
        ]),
    ]

    # 5
    c += secao(5, "Nova análise", "Operação")
    c += figura("m_nova.png", "Área para soltar os termogramas, o fluxo da análise, as inspeções recentes e os exemplos.")
    c += [
        lista([
            "Arraste as imagens para a área tracejada, ou use <b>Escolher arquivos</b> (atalho Ctrl + O, que funciona em qualquer tela). "
            "Também é possível soltar imagens em qualquer lugar da janela.",
            "<b>Uma imagem</b> abre direto para revisão. Enquanto processa, a tela mostra as etapas andando e a forma do resultado.",
            "<b>Várias imagens</b> são analisadas em lote, com barra de progresso e a severidade de cada uma; no fim, dá para ir às Inspeções.",
            "<b>Exemplos:</b> imagens de uma subestação de 132 kV (dataset de estudo) para experimentar sem câmera.",
        ]),
        p("Dois tipos de imagem", "h2"),
        tabela(["Tipo", "Como o Pyron lê", "Como aparece"], [
            ["JPEG radiométrico (FLIR)", "Lê os dados brutos da câmera e converte em temperatura com emissividade, distância, temperatura refletida, "
             "umidade e as constantes da própria câmera.", "Etiqueta verde <b>Temperatura medida</b>."],
            ["Imagem colorida com escala", "Lê os números da escala por OCR e converte cada cor na temperatura correspondente da paleta. "
             "Testado em 893 imagens: erro mediano de 0,5 °C e escala lida em 100% delas.", "Etiqueta amarela <b>Temperatura estimada pelas cores</b>."],
        ], [38, 90, LARGURA / mm - 128]),
        Spacer(1, 6),
        p("Etapas mostradas no topo da análise: leitura da temperatura, detecção, medição e severidade, e laudo, com o tempo de cada uma.", "nota"),
    ]

    # 6
    c += secao(6, "Análise de uma imagem", "Operação")
    c += figura("m_analise.png", "Análise aberta: visualizador térmico à esquerda e o inspetor com resultado, condições e laudo à direita.")
    c += [
        p("Visualizador térmico", "h2"),
        lista([
            "<b>Paletas:</b> Ferro, Arco-íris e Cinza.",
            "<b>Escala:</b> Equipamento (realça o equipamento e deixa o céu na cor mais escura) ou Cena (da menor à maior temperatura).",
            "<b>Temperatura sob o cursor:</b> passe o mouse sobre a imagem; a posição também aparece marcada na barra de cores.",
            "<b>Isoterma:</b> destaca tudo acima de uma temperatura e mostra a porcentagem da imagem nessa faixa.",
            "<b>Foto:</b> mostra a foto visível da câmera ao lado do termograma, quando a câmera grava.",
            "<b>Regiões:</b> cada uma com a cor da severidade, o nome, a temperatura máxima e o ponto de máxima; as etiquetas desviam umas das outras.",
        ]),
    ]
    c += figura("m_isoterma.png", "Isoterma ligada acima de 50,2 °C, com a paleta Arco-íris: 19,3% da imagem está nessa faixa.")
    c += [
        p("Regiões", "h2"),
        lista([
            "Vêm do detector em uso ou são desenhadas à mão: <b>Desenhar região</b> (tecla D) e arraste sobre a imagem.",
            "Cada região pode ser renomeada e ter a <b>classe</b> trocada (conexão, bucha, terminal, para-raio, cabo, radiador...). "
            "A classe define o limite de temperatura (MTA) e como ela é comparada.",
            "Dê a mesma classe às regiões das três fases para comparar componentes semelhantes (ΔT entre fases).",
            "Remover: botão da lixeira ou tecla Delete, com <b>Desfazer</b>. Selecione na imagem ou na lista; Esc cancela.",
        ]),
        p("Resultado", "h2"),
        lista([
            "<b>Veredito:</b> o nível mais grave, onde está, por qual critério e o que fazer (por exemplo: corrigir o mais rápido possível).",
            "<b>Indicadores:</b> máxima da cena, a região mais perto do limite (% da MTA) ou o maior ΔT entre fases, e a quantidade de regiões.",
            "<b>Avisos:</b> o que falta para a avaliação completa, como a temperatura ambiente e a carga.",
            "<b>Cartão de cada região:</b> temperatura máxima, % da MTA, temperatura projetada para plena carga, ΔT entre fases, "
            "com quanto de carga o componente atinge a MTA, confiança do modelo e uma barra até o limite.",
        ]),
    ]
    c += figura("m_condicoes.png", "Aba Condições: temperatura ambiente e carga no momento, dados de medição da câmera e o critério em uso.")
    c += [
        lista([
            "<b>Condições:</b> com a temperatura ambiente e a carga no momento, cada região é projetada para plena carga e comparada com a MTA. "
            "Recalcular aplica na hora.",
            "<b>Medição da câmera:</b> emissividade, distância, temperatura refletida, umidade, sensor e escala lida.",
            "<b>Laudo:</b> instalação, equipamento, responsável técnico, registro/ART e observações. O responsável padrão já vem preenchido.",
            "<b>Detectar de novo:</b> escolha outro detector no topo e clique em Detectar; as regiões desenhadas à mão são mantidas.",
        ]),
    ]

    # 7
    c += secao(7, "Como a severidade é decidida", "Critério técnico")
    c += [
        p("Temperatura sozinha não diz nada. A NBR 15866 pede que cada ponto quente seja comparado com uma referência. "
          "O Pyron usa duas referências e fica com a <b>pior</b> das duas:"),
        destaque("1. Máxima temperatura admissível (MTA) do componente",
                 "A temperatura medida é projetada para plena carga: <font name='Pyron-Mono'>T_proj = T_amb + (T − T_amb) × (100 / carga)²</font>. "
                 "O resultado é comparado com quanto o componente aguenta."),
        Spacer(1, 6),
        destaque("2. ΔT entre componentes semelhantes",
                 "A mesma peça nas três fases, sob a mesma carga, deveria ter a mesma temperatura. A diferença para a mediana das fases indica defeito.",
                 VIOLETA, VIOLETA_50),
        p("Faixas de prioridade (modelo brasileiro)", "h2"),
        tabela(["Nível", "% da MTA", "ΔT entre fases (condutores)", "Para-raios e isoladores", "O que fazer"], [
            [selo("Atenção"), "acima de 60%", "5 a 10 °C", "2 a 5 °C", "Acompanhar na próxima rota."],
            [selo("Programar"), "acima de 70%", "acima de 10 a 20 °C", "5 a 10 °C", "Reparo com data marcada."],
            [selo("Urgente"), "acima de 80%", "acima de 20 a 40 °C", "acima de 10 °C", "Corrigir o mais rápido possível."],
            [selo("Imediato"), "acima de 100%", "acima de 40 °C", "–", "Intervenção imediata."],
        ], [26, 24, 42, 36, LARGURA / mm - 128]),
        Spacer(1, 6),
        lista([
            "<b>Para-raios e isoladores</b> aquecem por corrente de fuga, não por carga: têm faixas próprias e não recebem a correção de carga.",
            "<b>Carga limite:</b> o Pyron calcula com quanto de carga o componente chega à MTA (por exemplo, 102% da carga nominal).",
            "<b>Classificação indicativa:</b> sem ambiente, sem carga e sem fase semelhante para comparar, o nível aparece marcado como indicativo.",
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
    c += secao(8, "Laudo em PDF", "Documento técnico")
    c += [
        p("<b>Gerar laudo</b> (no topo da análise ou na aba Laudo) abre o PDF pronto para revisar, imprimir e assinar. Ele traz:"),
        lista([
            "Cabeçalho com o nome e o subtítulo da empresa (Configurações), número do laudo e data de emissão.",
            "1. Identificação: instalação, equipamento, arquivo, data da captura e câmera.",
            "2. Condições de medição: origem da temperatura, emissividade, distância, temperatura refletida, ambiente e carga.",
            "3. Termograma com as regiões e, ao lado, a foto visível; escala de cores e detector usado.",
            "4. Resultados por região: temperatura medida e projetada, MTA, % da MTA, ΔT entre fases, severidade (com o critério) e ação.",
            "5. Conclusão, 6. Referências e critério (normas, fórmula e MTAs usadas), 7. Responsabilidade técnica com assinatura e ART.",
        ]),
    ]
    c += figura("m_laudo1.png", "Primeira página de um laudo gerado pelo Pyron (dados de demonstração).", 104 * mm)

    # 9
    c += secao(9, "Inspeções", "Operação")
    c += figura("m_inspecoes.png", "Lista de inspeções em tabela, com indicadores que filtram, busca, filtro de severidade e ordenação.")
    c += [
        lista([
            "<b>Tabela</b> (padrão) ou <b>miniaturas</b>: o botão à direita dos filtros troca a forma e a escolha fica lembrada.",
            "Colunas: termograma, arquivo, data e regiões, local (instalação e equipamento), região crítica, máxima da cena e severidade.",
            "<b>Indicadores clicáveis:</b> Críticas, Programar reparo, Atenção e Normais filtram a lista.",
            "<b>Busca</b> por arquivo, instalação ou equipamento; <b>ordem</b> por mais recentes, mais graves ou nome.",
            "Em cada linha: abrir (clique na linha ou Enter), gerar o laudo e apagar (com confirmação).",
            "As imagens que vieram do monitoramento aparecem marcadas como Monitor.",
        ]),
    ]

    # 10
    c += secao(10, "Monitoramento e alertas", "Operação")
    c += [p("O monitoramento transforma o Pyron num vigia: as imagens que a câmera grava numa pasta são analisadas sozinhas e, "
            "quando algum equipamento passa do limite, nasce um alerta com a mensagem pronta para o WhatsApp do responsável.")]
    c += figura("m_monitor.png", "Estado do monitoramento, fonte das imagens, responsáveis e a prévia da mensagem.")
    c += [
        p("Configuração em quatro passos", "h2"),
        lista([
            "<b>1. Fonte das imagens.</b> Disponível: <b>pasta monitorada</b>, onde a câmera, o cartão sincronizado, o FTP da câmera fixa "
            "ou o FLIR Thermal Studio gravam os JPEG. Ao ligar, o que já estava na pasta fica de fora; só o que chegar depois é analisado. "
            "Instalação e equipamento informados aqui vão para as análises e para a mensagem.",
            "<b>2. Regra de alerta.</b> Severidade mínima (Atenção, Programar, Urgente ou Imediato) e o intervalo para não repetir o mesmo nível. "
            "Se o nível piorar, o alerta sai na hora.",
            "<b>3. Responsáveis.</b> Nome e WhatsApp com DDI e DDD (por exemplo, +55 83 99999-0000).",
            "<b>4. Envio da mensagem.</b> Disponível: <b>manual</b>. O Pyron prepara o texto e um clique abre o WhatsApp (celular ou computador) "
            "com a mensagem pronta para o responsável enviar. A prévia mostra como a mensagem vai chegar.",
        ]),
        p("Ligar monitoramento começa a vigiar a pasta; Verificar agora faz uma passada na hora.", "nota"),
    ]
    c += figura("m_monitor_alertas.png", "Lista de alertas com severidade, resumo e situação, e o que ainda está em desenvolvimento.")
    c += [
        p("Alertas", "h2"),
        lista([
            "Cada alerta tem data, imagem, local, severidade, resumo e situação: <b>pendente</b>, <b>enviado</b> ou <b>resolvido</b>.",
            "<b>WhatsApp</b> abre a lista de responsáveis com o botão Abrir WhatsApp e a opção de copiar a mensagem; ao abrir, o alerta passa a enviado.",
            "<b>Abrir</b> leva à análise da imagem; <b>Resolver</b> fecha o alerta.",
            "O sino do topo e o menu mostram quantos alertas estão pendentes, em qualquer tela.",
            "O monitoramento funciona enquanto o Pyron estiver aberto e volta sozinho ao abrir o programa.",
        ]),
        p("Em desenvolvimento (backlog)", "h2"),
        tabela(["Item", "O que vai fazer"], [
            ["Conexão direta com a câmera", "RTSP/ONVIF e FLIR Atlas SDK, sem depender de pasta."],
            ["WhatsApp automático", "Envio pela API oficial do WhatsApp Business, com confirmação de leitura."],
            ["Aviso no celular", "Aplicativo ou página instalável com notificação e acesso ao laudo."],
            ["Serviço do Windows", "Monitoramento rodando mesmo com a janela do Pyron fechada."],
            ["Escalonamento", "Se ninguém responder em X minutos, avisa o próximo da lista."],
        ], [52, LARGURA / mm - 52]),
    ]

    # 11
    c += secao(11, "Modelos", "Sistema")
    c += figura("m_modelos.png", "Detectores disponíveis e o passo a passo para treinar e instalar um modelo novo.")
    c += [
        lista([
            "<b>Pontos quentes (regra):</b> detector embutido, sem IA. Aponta trechos mais quentes que o equipamento em volta. "
            "É a base até o primeiro modelo treinado; não identifica o tipo de componente.",
            "<b>Modelos treinados (IA):</b> cada pasta em <font name='Pyron-Mono'>modelos/</font> com <font name='Pyron-Mono'>cartao.json</font> e "
            "<font name='Pyron-Mono'>modelo.onnx</font> aparece aqui, com classes, desempenho e limitações. <b>Usar este modelo</b> o torna o padrão.",
            "<b>Treino:</b> rotule com caixas no CVAT (por exemplo: para-raio inteiro, terminal superior, parte isoladora, terminal inferior), "
            "exporte em COCO 1.0 e rode o comando mostrado. A rede aprende com a temperatura verdadeira de cada imagem, é avaliada em "
            "sessões que não viu (AP50 e erro da temperatura máxima) e é instalada sozinha.",
        ]),
    ]

    # 12
    c += secao(12, "Configurações", "Sistema")
    c += figura("m_criterio.png", "Critério de severidade em quatro grupos, com os modelos Brasil (NBR 15866) e NETA MTS.")
    c += [
        tabela(["Aba", "O que dá para ajustar"], [
            ["Empresa e responsável", "Nome e subtítulo da empresa no cabeçalho dos laudos; responsável técnico e registro que vêm preenchidos em cada análise."],
            ["Critério de severidade", "Limites de % da MTA, ΔT entre semelhantes (condutores e dielétricos) e ΔT sobre o ambiente (NETA, opcional); "
             "expoente da correção de carga e carga mínima confiável; modelos Brasil e NETA; restaurar o padrão."],
            ["Biblioteca de componentes", "MTA de cada classe de componente, com a fonte do valor. Campos alterados ficam destacados em azul."],
            ["Aparência", "Tema claro (padrão), escuro ou seguir o Windows."],
            ["Dados e sistema", "Onde ficam as inspeções, os alertas, as configurações e os modelos; versão."],
        ], [44, LARGURA / mm - 44]),
        Spacer(1, 6),
        p("A biblioteca de componentes mostra, para cada classe, o tipo de aquecimento, a MTA editável e a fonte do valor "
          "(a mesma tabela da seção 7).", "nota"),
    ]

    # 13
    c += secao(13, "Dados, privacidade e instalação", "Sistema")
    c += [
        lista([
            "Inspeções, imagens, alertas e configurações ficam em <font name='Pyron-Mono'>app/dados_app</font>, na pasta do projeto. "
            "Para fazer cópia de segurança, copie essa pasta.",
            "O Pyron não envia nada para a internet. A única saída é quando o usuário clica em Abrir WhatsApp.",
            "Instalação do zero, atualização e geração do executável: README do projeto.",
            "O lançador Pyron.exe é pequeno e não é assinado digitalmente. Para distribuir a clientes, o caminho é assinar o executável.",
            "Código-fonte: github.com/hugovieiraz/Pyron---Embrapii.",
        ]),
    ]

    # 14
    c += secao(14, "Limitações e próximos passos", "Roteiro", nova_pagina=False)
    c += [
        p("Limitações desta versão", "h2"),
        lista([
            "O detector de componentes com IA ainda está sendo treinado com rótulos reais; até lá, a regra de pontos quentes dá uma classificação indicativa.",
            "As máximas admissíveis e faixas de severidade precisam ser conferidas na edição vigente da NBR 15866, com os fabricantes e com termografista certificado.",
            "Na imagem só colorida, o ponto quente precisa estar dentro da escala de cores; acima do topo da escala, a foto não mostra a temperatura real.",
            "O monitoramento depende do Pyron aberto e o envio do WhatsApp é manual.",
        ]),
        p("Próximos passos", "h2"),
        lista([
            "<b>Previsão:</b> tendência de cada componente ao longo das inspeções e tempo estimado até ficar crítico.",
            "<b>Câmeras fixas:</b> conexão direta RTSP/ONVIF e FLIR Atlas SDK.",
            "<b>Avisos:</b> WhatsApp Business automático, aviso no celular e escalonamento.",
            "<b>Gêmeo térmico do transformador</b> (IEC 60076-7) e perda de vida da isolação.",
            "<b>Assistente de laudo</b> com linguagem natural, a partir dos resultados medidos.",
        ]),
    ]

    # apêndices
    c += [PageBreak(), p("APÊNDICE", "sobre")]
    cab = Paragraph("Atalhos e glossário", E["h1"])
    cab.toc = "Apêndice: atalhos e glossário"
    c += [cab,
          tabela(["Atalho", "Onde", "O que faz"], [
              ["Ctrl + O", "Qualquer tela", "Escolher imagens para analisar."],
              ["D", "Análise aberta", "Desenhar região: arraste sobre a imagem."],
              ["S ou V", "Análise aberta", "Voltar para a ferramenta de seleção."],
              ["Esc", "Análise aberta", "Cancelar o desenho e tirar a seleção."],
              ["Delete", "Análise aberta", "Remover a região selecionada (com Desfazer)."],
              ["Enter", "Inspeções", "Abrir a inspeção da linha em foco."],
          ], [28, 34, LARGURA / mm - 62]),
          Spacer(1, 10),
          tabela(["Termo", "Significado"], [
              ["MTA", "Máxima temperatura admissível: quanto o componente aguenta em operação contínua."],
              ["ΔT", "Diferença de temperatura: entre fases semelhantes ou sobre o ar ambiente."],
              ["Radiométrico", "Imagem que guarda a temperatura de cada pixel, não só as cores."],
              ["Emissividade", "Quanto a superfície emite de radiação térmica; afeta a temperatura calculada."],
              ["Isoterma", "Destaque de tudo o que está acima de uma temperatura escolhida."],
              ["Plena carga", "Corrente nominal do equipamento; a projeção leva a medição feita com carga menor até ela."],
              ["Indicativa", "Classificação sem referência completa (ambiente, carga ou fase semelhante)."],
          ], [32, LARGURA / mm - 32])]
    return c


def main() -> None:
    doc = Documento(str(SAIDA))
    doc.multiBuild(conteudo())
    print("manual:", SAIDA, f"({SAIDA.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
