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
VERSAO = "0.8.0"

# Cores dos tokens da interface (app/interface/tokens.css): neutros ardósia, cobalto só onde a tela usa
# (ação e seleção; aqui, os marcadores de lista), grafite do palco do termograma na capa.
TINTA = colors.HexColor("#161B22")       # --n-900
TEXTO_2 = colors.HexColor("#424B59")     # --n-700
TEXTO_3 = colors.HexColor("#5A6474")     # --n-600
ARDOSIA = colors.HexColor("#2A313C")     # --n-800
COBALTO = colors.HexColor("#1F5BC4")     # --acao
LINHA_FORTE = colors.HexColor("#8B95A5")  # --n-500
BORDA = colors.HexColor("#DDE2E8")       # --n-300
FUNDO = colors.HexColor("#F7F8FA")       # --n-100 (--fundo-trabalho)
PALCO = colors.HexColor("#121418")       # --palco
SEVERIDADE = {
    "Normal": ("#1E9E63", "#E3F6EE"), "Atenção": ("#B58900", "#FBF1D3"), "Programar": ("#E07012", "#FDEBDC"),
    "Urgente": ("#D63A22", "#FCE6E1"), "Imediato": ("#A3123A", "#FAE3EA"),
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
    "sobre": ParagraphStyle("sobre", fontName="Pyron-Bold", fontSize=8, leading=11, textColor=TEXTO_3, spaceAfter=2),
    "h1": ParagraphStyle("h1", fontName="Pyron-Bold", fontSize=20, leading=26, textColor=TINTA, spaceAfter=10),
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
        bulletType="bullet", bulletColor=COBALTO, bulletFontName="Pyron-Bold", leftIndent=12, spaceAfter=6,
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
        ("BACKGROUND", (0, 0), (-1, 0), ARDOSIA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
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


def destaque(titulo: str, texto: str, cor=ARDOSIA, fundo=FUNDO) -> Table:
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
        # faixa grafite, a cor do palco onde o termograma aparece no aplicativo
        canvas.setFillColor(PALCO)
        canvas.rect(0, 0, w, 70 * mm, stroke=0, fill=1)
        lado = 118 * mm
        canvas.drawImage(str(LOGO), (w - lado * 0.85) / 2, h - 40 * mm - lado, width=lado * 0.85, height=lado, mask="auto", preserveAspectRatio=True)
        canvas.setFillColor(TINTA)
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
        canvas.setFillColor(TINTA)
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
            "<b>Interface industrial e clara.</b> Fundo claro e neutros frios; o azul marca só a ação principal e a seleção. A cor forte fica para os dados: termograma e severidade.",
        ]),
        p("Mapa das funcionalidades", "h2"),
        tabela(["Área", "O que faz"], [
            ["<b>Painel</b>", "Críticas agora, pendências e inspeções vencidas, a situação de cada equipamento, distribuição por severidade e próximas inspeções."],
            ["<b>Inspeções</b>", "Histórico com filtros e busca, <b>Importar termogramas</b>, várias marcadas para definir o equipamento ou gerar um relatório, e a planilha."],
            ["<b>Análise</b>", "Abre de cada inspeção: visualizador térmico, regiões, ponto e linha de medição, escala, isoterma, condições, identificação e pendência."],
            ["<b>Equipamentos</b>", "Histórico de cada equipamento, tendência em °C por mês, projeção até o limite e próxima inspeção."],
            ["<b>Pendências</b>", "Cada anomalia com prazo, ordem de serviço, responsável e histórico até a correção verificada."],
            ["<b>Captura</b>", "Pasta monitorada com alerta para o WhatsApp, vídeo da câmera analisado quadro a quadro, câmera do celular e a lista de alertas."],
            ["<b>Modelos</b>", "Detectores instalados com o recomendado marcado, treino com as anotações do CVAT e avaliação dos modelos."],
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
        p("Todas as telas têm a mesma estrutura: a <b>barra de navegação no topo</b>, com as seções, a busca, os alertas e as "
          "configurações, e a área de trabalho embaixo. As telas de trabalho (a análise, por exemplo) têm uma barra de ferramentas, "
          "a área principal e um painel de detalhe à direita."),
        p("Navegação", "h2"),
        lista([
            "<b>Seções:</b> Painel, Inspeções, Equipamentos, Pendências (com o número das de prazo vencido), Captura e Modelos. "
            "Alt + 1 a 6 levam a cada uma; Alt + 0 abre as Configurações (ícone no canto direito).",
            "<b>Sino:</b> alertas da pasta monitorada ainda não resolvidos; leva a Captura › Alertas.",
            "Captura, Modelos e Configurações têm abas logo abaixo do título; o endereço acompanha a aba.",
        ]),
        p("Busca rápida", "h2"),
        lista([
            "<b>Buscar</b> (ou Ctrl + K): acha telas, inspeções pelo arquivo, equipamento, instalação ou data, equipamentos e ações como "
            "exportar a planilha ou trocar o tema. Setas para escolher, Enter para abrir.",
            "A tecla <b>?</b> mostra os atalhos de teclado.",
        ]),
    ]
    c += figura("m_busca.png", "Busca rápida (Ctrl + K) com “CS-12” digitado: o equipamento e as inspeções dele no mesmo lugar.")
    c += [
        p("Comportamento de todas as telas", "h2"),
        lista([
            "<b>Carregando:</b> a tela mostra a forma do conteúdo (esqueleto) enquanto os dados chegam.",
            "<b>Vazio:</b> uma ilustração, o que vai aparecer ali e o botão da próxima ação.",
            "<b>Erro:</b> o que aconteceu e o botão Tentar de novo. <b>Sem conexão:</b> uma faixa no topo, se o servidor parar de responder.",
            "Avisos rápidos no canto inferior confirmam cada ação. Apagar tem <b>Desfazer</b> no aviso, em vez de pedir confirmação; "
            "só o que não volta (restaurar backup, apagar a inspeção) pergunta antes.",
            "<b>Salvamento automático</b> na análise, na empresa e na pasta monitorada (“Salvo às 14:32” ao lado do título). Critério e "
            "componentes têm o botão Salvar, porque recalculam todas as inspeções; sair com mudança sem salvar pergunta antes.",
            "Tema claro (padrão) ou escuro, em Configurações › Aparência ou pela busca. O termograma fica sempre sobre fundo grafite.",
            "A interface anterior continua disponível nesta versão: Configurações › Sobre › Abrir a interface anterior.",
        ]),
    ]

    # 4
    c += secao(4, "Painel", "Operação")
    c += figura("m_painel.png", "Painel com indicadores, a situação atual de cada equipamento, distribuição por severidade e próximas inspeções.")
    c += [
        lista([
            "<b>Indicadores:</b> inspeções, críticas agora (urgente ou imediato na situação atual), <b>pendências vencidas</b>, "
            "<b>inspeções vencidas</b> por equipamento e alertas pendentes do monitoramento. Cada indicador leva à lista já filtrada.",
            "<b>Atenção agora:</b> a <b>situação atual</b>: de cada equipamento, só a inspeção mais recente (uma inspeção normal depois de uma "
            "grave quer dizer que ele está normal agora; a anomalia antiga segue em Pendências). Mostra a região crítica e o valor que decidiu.",
            "<b>Distribuição por severidade:</b> barra empilhada e contagem de cada nível.",
            "<b>Próximas inspeções:</b> os equipamentos pela data da próxima inspeção, vencidos primeiro.",
            "<b>Aviso de configuração:</b> enquanto faltar o nome da empresa ou um responsável técnico, o painel avisa e leva às Configurações.",
        ]),
    ]

    # 5
    c += secao(5, "Importar termogramas", "Operação")
    c += [
        lista([
            "Em <b>Inspeções › Importar termogramas</b> (ou Ctrl + O, em qualquer tela), escolha uma ou várias imagens. Também dá para "
            "soltar as imagens em qualquer lugar da janela; um vídeo solto vai para Captura › Vídeo.",
            "Uma faixa acima da lista mostra o andamento (Importando 3 de 5) e o aviso do fim leva às inspeções novas. "
            "<b>Uma imagem</b> só abre direto na análise.",
            "Para as imagens entrarem no histórico de um equipamento, importe pela página dele (<b>Adicionar imagens</b>) ou defina o "
            "equipamento depois, na análise ou com várias inspeções marcadas.",
        ]),
        p("Três tipos de imagem", "h2"),
        tabela(["Tipo", "Como o Pyron lê", "Como aparece"], [
            ["JPEG radiométrico (FLIR)", "Lê os dados brutos da câmera e converte em temperatura com emissividade, distância, temperatura refletida, "
             "umidade e as constantes da própria câmera.", "Etiqueta verde <b>Temperatura medida</b>."],
            ["Imagem colorida com escala", "Lê os números da escala por OCR e converte cada cor na temperatura da paleta. "
             "Testado em 893 imagens: erro mediano de 0,5 °C e escala lida em 100% delas.", "Etiqueta amarela <b>Temperatura estimada pelas cores</b>."],
            ["Sem dados nem escala legível", "Imagem da internet, feita por IA, cortada ou mandada como foto pelo WhatsApp. A análise não trava: "
             "os componentes são identificados pela imagem colorida e as etapas de temperatura ficam como sem dado. Se a imagem tem a barra "
             "de cores, informe o mínimo e o máximo dela na análise e a temperatura é estimada.", "Etiqueta <b>Sem temperatura</b>; inspeção "
             "<b>Sem medida</b>, que não conta como normal, não vira pendência e não gera laudo."],
        ], [38, 90, LARGURA / mm - 128]),
        Spacer(1, 6),
        p("Aceita JPEG, PNG, WebP e BMP. Para medir de verdade, use o arquivo original da câmera (FLIRxxxx.jpg). No WhatsApp, mande como "
          "documento: como foto, ele recomprime e apaga os dados de temperatura.", "nota"),
    ]

    # 6
    c += secao(6, "Análise de uma imagem", "Operação")
    c += figura("m_analise.png", "Análise aberta: barra de ferramentas, termograma com as regiões, a faixa de regiões embaixo e o painel "
                                 "de detalhe com o resumo da inspeção.")
    c += [
        p("Visualizador térmico", "h2"),
        lista([
            "<b>Paleta</b> (Ferro, Arco-íris ou Cinza) e <b>Escala</b>: Equipamento (realça o equipamento), Cena inteira ou Manual (clique "
            "no máximo ou no mínimo da barra de cores e digite). Paleta e escala ficam guardadas e o laudo sai igual à tela.",
            "<b>Temperatura sob o cursor</b>, junto da mira e marcada na barra de cores. <b>Isoterma</b> (no menu Escala ou tecla I): "
            "destaca o que está acima de uma temperatura; clique na barra de cores para escolher o valor.",
            "<b>Camadas:</b> regiões, rótulos, pontos quentes e contornos, cada um liga e desliga. <b>Foto</b> (tecla F) troca para a foto "
            "visível da câmera.",
            "<b>Zoom</b> pela roda do mouse, no ponto do cursor; espaço + arrastar move; 0 encaixa a imagem. Acima de 300% cada pixel fica nítido.",
        ]),
        p("Ferramentas de medição", "h2"),
        tabela(["Ferramenta", "Tecla", "O que faz"], [
            ["Selecionar", "V", "Escolhe uma região na imagem ou na faixa de regiões; arrastar move a caixa e as alças mudam o tamanho."],
            ["Região", "R", "Arraste uma caixa: a região é medida e classificada como as do detector."],
            ["Ponto", "P", "Clique: lê a temperatura daquele pixel (P1, P2…)."],
            ["Linha", "L", "Arraste: mostra o perfil de temperatura ao longo da linha, com máxima, mínima e média (L1, L2…)."],
        ], [30, 16, LARGURA / mm - 46]),
        Spacer(1, 6),
        p("Pontos e linhas ficam guardados na inspeção, aparecem no painel e vão para o laudo. Delete apaga a região selecionada, "
          "com Desfazer no aviso.", "nota"),
    ]
    c += figura("m_camadas.png", "Menu Camadas aberto: cada camada liga e desliga; a Foto troca o termograma pela imagem visível.")
    c += figura("m_isoterma.png", "Isoterma ligada: só o que está acima da temperatura escolhida mantém a cor.")
    c += [
        p("Regiões e painel de detalhe", "h2"),
        lista([
            "<b>Faixa de regiões</b> embaixo do termograma: uma ficha por região, da mais grave para a mais fria. Clicar na ficha ou na "
            "caixa seleciona; ← e → percorrem.",
            "<b>Resumo</b> (sem região selecionada): o nível mais grave, onde está, por qual critério e o que fazer; a máxima da cena, a "
            "região mais perto do limite (% da MTA) ou o maior ΔT entre fases, e a comparação entre peças iguais das três fases.",
            "<b>Região selecionada:</b> leituras, diagnóstico e, com o SAM 2 instalado, <b>Dimensões estimadas</b> (botão Medir).",
            "<b>Condições</b>, <b>Identificação</b> e <b>Pendência</b> ficam no trilho de ícones do painel.",
            "<b>Cabeçalho:</b> equipamento, severidade, data e arquivo; setas (por exemplo, 2 de 3) para andar pelas inspeções do mesmo "
            "equipamento; Detectar de novo, Mais e <b>Gerar laudo</b>. As edições salvam sozinhas.",
        ]),
    ]
    c += figura("m_condicoes.png", "Painel Condições: ambiente e carga, e os parâmetros da câmera (emissividade, temperatura refletida, distância, umidade e ar).")
    c += [
        lista([
            "<b>Condições:</b> com a temperatura ambiente e a carga no momento, cada região é projetada para plena carga e comparada com a MTA.",
            "<b>Parâmetros da câmera</b> (só termograma radiométrico): emissividade, temperatura refletida, distância, umidade e temperatura "
            "do ar. <b>Aplicar</b> recalcula a temperatura a partir do arquivo original; <b>Voltar aos da câmera</b> desfaz.",
            "<b>Identificação:</b> instalação, equipamento, ART e observações do laudo.",
            "<b>Mais › Exportar:</b> imagem PNG com regiões, pontos e linhas, ou as temperaturas de todos os pixels em CSV (abre no Excel).",
            "<b>Detectar de novo:</b> escolha outro detector; as regiões desenhadas à mão são mantidas.",
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
                 LINHA_FORTE, FUNDO),
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
            "<b>Não avaliado:</b> para-raio e isolador não têm MTA e só se comparam com a mesma peça das outras fases. Sozinhos na imagem, "
            "ficam Não avaliado (e não Normal), com o aviso de fotografar as três fases juntas.",
            "<b>Conferir:</b> quando a severidade vem só de um ponto quente fora das peças que o modelo achou, a inspeção ganha o selo Conferir. "
            "O ponto continua na classificação (pode ser defeito em outro equipamento), mas pode ser lâmpada, estrutura ou reflexo: olhe antes de agir.",
            "<b>NETA MTS:</b> o critério americano (ΔT sobre o ar ambiente) pode ser carregado como modelo em Configurações.",
            "Mudou o critério ou a biblioteca? Todas as inspeções salvas são recalculadas.",
        ]),
        p("Máximas admissíveis de partida (biblioteca de componentes)", "h2"),
        tabela(["Componente", "MTA", "Fonte"], [
            ["Conexões, terminais, pontos quentes", "90 °C", "Prática brasileira para componentes metálicos; IEC 62271-1: conexão nua no ar 90 °C, estanhada 105 °C, prateada 115 °C."],
            ["Terminal de bucha", "95 °C", "IEC 60137: 55 K de elevação sobre 40 °C de ambiente."],
            ["Cabo isolado (PVC)", "70 °C", "NBR 5410 (XLPE/EPR: 90 °C)."],
            ["Tanque e radiador (óleo no topo)", "100 °C", "NBR 5356-2 / IEC 60076-2: 60 K sobre 40 °C."],
            ["Para-raio, isolador, parte isoladora", "não se aplica", "Comparar as fases (IEC 60099-5)."],
        ], [52, 24, LARGURA / mm - 76]),
        Spacer(1, 6),
        p("Os valores são de partida e ficam editáveis. Confira sempre com o dado do fabricante, a edição vigente da NBR 15866 e o termografista responsável.", "nota"),
    ]
    c += figura("m_nao_avaliado.png", "Para-raio sozinho na imagem: a região fica Não avaliado e o diagnóstico pede para fotografar junto a mesma peça das outras fases.")

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
            "<b>Tabela</b> com miniatura, arquivo e data da captura, equipamento (link para a página dele), região crítica, máxima e "
            "severidade; a pendência vencida aparece embaixo do selo. Clique no cabeçalho de uma coluna para ordenar.",
            "<b>Filtros</b> Todas, Críticas, Programar, Atenção, Normais e <b>Sem medida</b>, com a contagem de cada um; <b>busca</b> por "
            "arquivo, instalação ou equipamento. Quando a severidade vem de calor fora das peças identificadas, o selo aparece marcado "
            "para conferir.",
            "<b>Marque várias</b> (caixa de seleção) para <b>Definir equipamento</b> de todas de uma vez ou <b>Gerar relatório</b> com todas.",
            "<b>Exportar planilha</b>: todas as inspeções em CSV, que abre direto no Excel.",
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
            "30 em programar, 7 em urgente e 1 em imediato. Filtros na lista: Todos, Com anomalia, Inspeção vencida e Esquentando.",
            "<b>Peças:</b> a máxima de cada tipo de peça ao longo do tempo, para ver qual está esquentando.",
            "<b>Adicionar imagens</b> analisa imagens novas já como inspeções do equipamento; <b>Relatório do equipamento</b> junta todas.",
        ]),
    ]
    c += figura("m_equipamento.png", "Página do equipamento TR-01: estado, máxima, tendência a plena carga, próxima inspeção, gráfico, peças e histórico.")

    # 11
    c += secao(11, "Pendências", "Da anomalia à correção")
    c += figura("m_pendencias.png", "Pendências: a lista e, ao lado, a escolhida com situação, prazo, ordem de serviço, responsável e o histórico.")
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
        p("Cada mudança vai para o histórico, com data e nota. Filtros: Em andamento, Vencidas, Aguardando reinspeção, Concluídas e "
          "Todas; ↑ e ↓ passam de uma pendência para a outra. As vencidas aparecem no Painel e na navegação.", "nota"),
    ]

    # 12
    c += secao(12, "Vídeo da câmera", "Captura")
    c += figura("m_video.png", "Vídeo analisado: o quadro com as caixas, a leitura acima dele, o gráfico da máxima no tempo e os momentos com anomalia.")
    c += [
        lista([
            "Em <b>Captura › Vídeo</b>, envie a gravação da tela da câmera (MP4, AVI, MOV ou MKV, com a barra de escala visível). Cada quadro passa pelo mesmo caminho "
            "de uma foto: escala, temperatura, detector, medição e severidade.",
            "<b>Ao vivo:</b> o vídeo corre no relógio, como a câmera; enquanto o detector trabalha, os quadros que passam se perdem. "
            "Mostra o que o sistema acompanharia de verdade neste computador. <b>Um quadro a cada intervalo:</b> analisa sem perder nenhum.",
            "Depois, reproduza no ritmo em que os quadros foram analisados (espaço, setas), pule pelo gráfico ou pelos momentos com anomalia "
            "e use <b>Salvar quadro como inspeção</b> para ter o laudo daquele instante.",
            "Os números da escala só passam pelo OCR quando mudam; com a escala travada na câmera, informe os limites e a leitura fica exata.",
            "Usa a <b>versão rápida (INT8)</b> do modelo escolhido, quando ela existe: mais quadros analisados por segundo, com o mesmo acerto.",
        ]),
    ]

    # 13
    c += secao(13, "Câmera do celular", "Captura")
    c += [
        p("Aponte a câmera do celular para uma imagem térmica (na tela do computador, por exemplo) e o Pyron marca os componentes ao vivo, "
          "sem instalar nada no celular. A foto do celular não traz os números do sensor; <b>com a barra de cores no quadro</b>, o Pyron "
          "estima a temperatura de cada peça pelas cores dela."),
        tabela(["Passo", "O que fazer"], [
            ["1", "Celular e computador no mesmo Wi-Fi."],
            ["2", "No Pyron, <b>Captura › Celular › Ligar</b> e leia o QR code com o celular."],
            ["3", "O celular avisa que a conexão não é particular (o certificado é do próprio Pyron): <b>Avançado › Continuar</b>."],
            ["4", "Permita a câmera e aponte, com a barra de cores no quadro. <b>Capturar</b> salva o quadro como inspeção: com a temperatura "
                  "estimada quando a barra foi lida, Sem medida quando não."],
        ], [16, LARGURA / mm - 16]),
        Spacer(1, 6),
    ]
    c += figura("m_celular_pc.png", "Captura › Celular antes de ligar. Ligado, a tela mostra o QR code, o link e o vídeo do celular "
                "com as peças, a máxima estimada de cada uma e o ritmo.")
    c += figura("m_celular.png", "No celular: área do termograma tracejada, a barra de cores achada, peças com a máxima estimada e a escala lida.", 70 * mm)
    c += [
        lista([
            "<b>Só olha o termograma:</b> antes de detectar, o Pyron acha no quadro a área com cara de paleta (cores fortes de várias matizes) "
            "e manda só ela ao modelo. Sem termograma no quadro, nada é procurado. Em 76 fotos comuns, nenhuma peça falsa (olhando o quadro "
            "inteiro, eram 367); no celular simulado filmando a tela, 79 de 79 peças.",
            "Uma peça só aparece se surgir em <b>dois quadros seguidos</b>, com confiança de 50% ou mais. Segure o celular na mesma orientação da imagem.",
            "<b>Zoom</b> 1×, 2× ou 3× (quando o celular permite) para encher a tela com o termograma sem chegar perto.",
            "Segurança: um servidor à parte, só com as rotas do celular, em HTTPS, ouvindo a rede local só enquanto o modo está ligado e com um "
            "código novo no link a cada vez. Na primeira vez o Windows pergunta se o Pyron pode usar a rede: permita em redes privadas.",
            "<b>Placa de vídeo:</b> o detector do ao vivo roda nela pelo DirectML, da Microsoft (~54 ms por quadro na RTX 3050, "
            "8 a 9 análises por segundo no teste, contra 2 a 3 na CPU), com as mesmas peças da CPU. Carrega em cerca de 1 s; até lá, "
            "vai a versão rápida (INT8) na CPU. O computador mostra onde o detector está rodando, ao lado do ritmo, e o que o "
            "celular está gastando (câmera, envio, JPEG).",
            "<b>Vídeo fluido:</b> o celular transmite uns 12 quadros por segundo (WebSocket) e o computador mostra esse vídeo. Entre uma análise "
            "e outra, o celular acompanha o movimento da câmera e leva as caixas junto (erro de 0,3 pixel na tela num teste com a câmera "
            "passeando, contra cerca de 100 sem isso). Se a cena muda demais, as caixas somem até a próxima análise.",
            "<b>Temperatura pela barra:</b> o Pyron acha a barra em qualquer lugar do quadro, lê os números das pontas e converte cada cor "
            "na temperatura da cor mais parecida da barra, com as cores medidas no próprio quadro. Contra a temperatura radiométrica dos "
            "arquivos originais, com o celular simulado filmando a tela: erro de 0,5 a 0,7 °C na mediana e até 1,4 °C em 9 de cada 10 peças. "
            "<b>≥</b> no rótulo: a peça bate no topo da escala e pode estar mais quente. Desligue a medição de ponto da câmera ao filmar: a mira "
            "vermelha em cima da peça aumenta a máxima. É estimativa; para medir, o arquivo original da câmera.",
        ]),
    ]

    # 14
    c += secao(14, "Pasta monitorada e alertas", "Captura")
    c += figura("m_monitor.png", "Captura › Pasta monitorada: estado, pasta, equipamento por subpasta, regra de alerta e responsáveis.")
    c += [
        lista([
            "<b>Pasta:</b> onde a câmera, o cartão sincronizado, o FTP da câmera fixa ou o FLIR Thermal Studio gravam. A configuração "
            "salva sozinha; <b>Ligar</b> começa a vigiar e o que já estava na pasta fica de fora. <b>Verificar agora</b> não espera o intervalo.",
            "<b>Cada subpasta é um equipamento:</b> com a opção marcada, uma imagem em Entrada\\TR-01 entra no histórico do TR-01. "
            "Bom para câmeras fixas, uma pasta por câmera.",
            "<b>Regra de alerta:</b> severidade mínima e intervalo para não repetir o mesmo nível; se piorar, o alerta sai na hora.",
            "<b>Responsáveis:</b> nome e WhatsApp. O Pyron prepara a mensagem e um clique abre o WhatsApp com ela pronta.",
            "<b>Captura › Alertas:</b> pendentes, enviados e resolvidos; <b>Resolver</b> tem Desfazer. O sino do topo mostra os pendentes.",
        ]),
    ]
    c += figura("m_alertas.png", "Captura › Alertas: cada alerta com a inspeção, a severidade, o WhatsApp e Resolver.")

    # 15
    c += secao(15, "Modelos", "Sistema")
    c += figura("m_modelos.png", "Modelos › Em uso: os detectores, com o recomendado marcado, e ao lado o detalhe do escolhido.")
    c += [
        lista([
            "<b>Pontos quentes (regra):</b> embutido, sem IA. Aponta trechos mais quentes que o equipamento em volta.",
            "<b>Modelos treinados (IA):</b> por exemplo, o RF-DETR de para-raios (terminal superior, aletas isoladoras, terminal inferior), "
            "com mAP50 de 0,89 no teste. <b>Modelo + pontos quentes</b> junta os dois: diz em qual peça está o calor e compara as fases.",
            "<b>Recomendado</b> (marcado na lista): o combinado, peças e pontos quentes. A regra sozinha não sabe o que é cada coisa e marca "
            "lâmpadas e estruturas. <b>Usar este modelo</b> fica no detalhe do escolhido.",
            "<b>Versão rápida (INT8):</b> os pesos do modelo em 8 bits ({0}), sem treinar de novo: 1,5 vez mais rápida no processador, com o "
            "mesmo acerto no teste (mAP50 0,859 nas duas). Aparece no detalhe do modelo original; a câmera do celular e o vídeo já a usam.".format(
                mono("python -m ml.otimizar modelos/&lt;id&gt; --dados &lt;dataset&gt;")),
            "<b>Treino:</b> rotule com caixas no CVAT, exporte em COCO 1.0 e envie o .zip: o Pyron confere imagens e rótulos por classe, "
            "avisa o que falta e monta o pacote para o Colab (o passo a passo vai no LEIA-ME do pacote). Com placa NVIDIA, dá para treinar aqui.",
            "<b>Avaliação:</b> importe os resultados do caderno do Colab: o melhor modelo no teste, as peças que escaparam, a comparação com o "
            "melhor de cada coluna em negrito e o AP50 por componente.",
        ]),
    ]
    c += figura("m_avaliacao.png", "Modelos › Avaliação: três detectores comparados no mesmo conjunto de teste.")

    # 16
    c += secao(16, "Configurações", "Sistema")
    c += figura("m_identidade.png", "Configurações › Empresa e responsáveis: salva sozinho; o marcado à esquerda é o responsável padrão do laudo.")
    c += [
        tabela(["Aba", "O que dá para ajustar"], [
            ["Empresa e responsáveis", "Nome, subtítulo e <b>logotipo</b> no cabeçalho dos laudos; <b>responsáveis técnicos</b> (nome, função, registro) "
             "e o padrão. O laudo só sai com um responsável deste cadastro, para o nome e o registro nunca saírem digitados errado."],
            ["Critério", "Limites de % da MTA, ΔT entre semelhantes (condutores e dielétricos), ΔT sobre o ambiente (NETA, opcional), "
             "expoente da correção de carga e carga mínima; partir dos modelos Brasil ou NETA; <b>Salvar critério</b> recalcula tudo."],
            ["Componentes", "MTA de cada classe de componente, com a fonte do valor e o padrão ao lado quando mudou."],
            ["Aparência", "Tema claro (padrão), escuro ou seguir o Windows."],
            ["Dados e backup", "Onde ficam os dados, número de inspeções, espaço ocupado, <b>backup</b> e restauração."],
            ["Sobre", "Versão, detector em uso, pastas de dados e de modelos, créditos e o link para a interface anterior."],
        ], [44, LARGURA / mm - 44]),
    ]
    c += figura("m_criterio.png", "Configurações › Critério: quatro grupos, um valor por nível, e os modelos Brasil (NBR 15866) e NETA MTS.")
    c += figura("m_componentes.png", "Configurações › Componentes: tipo de aquecimento, MTA editável e a fonte de cada valor.")

    # 17
    c += secao(17, "Dados, backup e instalação", "Sistema")
    c += figura("m_dados.png", "Configurações › Dados e backup: pasta, inspeções, espaço ocupado e o backup.")
    c += [
        lista([
            f"Inspeções, imagens, equipamentos, pendências, alertas e configurações ficam em {mono('app/dados_app')}, na pasta do projeto.",
            "<b>Baixar backup:</b> um .zip com tudo isso (vídeos enviados e treinos ficam de fora). Guarde fora do computador.",
            "<b>Restaurar backup:</b> troca os dados atuais pelos do .zip. Antes, uma cópia do que existe hoje fica na pasta de dados, em backups.",
            "O Pyron não envia nada para a internet. A única saída é quando o usuário clica em Abrir WhatsApp.",
            "Instalação do zero, atualização e geração do executável: README do projeto. Código: github.com/hugovieiraz/Pyron---Embrapii.",
        ]),
    ]

    # 18
    c += secao(18, "Limitações e próximos passos", "Roteiro", nova_pagina=False)
    c += [
        p("Limitações desta versão", "h2"),
        lista([
            "Detector de IA só para para-raios, treinado com fotos de uma só subestação; falta validar com termografistas em outros lugares.",
            "Para os outros equipamentos, a regra de pontos quentes dá uma classificação indicativa.",
            "Pela câmera do celular, a temperatura é estimada pelas cores da barra (erro típico de 0,5 °C, às vezes bem mais): não substitui o arquivo original.",
            "As máximas admissíveis e as faixas precisam ser conferidas na edição vigente da NBR 15866, com os fabricantes e com termografista certificado.",
            "A tendência só é confiável comparando inspeções em condições parecidas, ou com ambiente e carga informados (série a plena carga).",
            "Na imagem só colorida, o ponto quente precisa estar dentro da escala de cores.",
            "O monitoramento depende do Pyron aberto e o envio do WhatsApp é manual.",
        ]),
        p("Próximos passos", "h2"),
        lista([
            "<b>Validação em campo:</b> comparar com laudos de termografistas em outras subestações.",
            "<b>Detectores</b> para transformador, disjuntor e seccionadora.",
            "<b>Previsão com carga e clima</b> integrados (histórico de carga do SCADA) e tempo até ficar crítico com intervalo de confiança.",
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
              ["Ctrl + K", "Qualquer tela", "Busca rápida: telas, inspeções, equipamentos e ações."],
              ["Ctrl + O", "Qualquer tela", "Importar termogramas."],
              ["Alt + 1 a 6", "Qualquer tela", "Painel, Inspeções, Equipamentos, Pendências, Captura, Modelos."],
              ["Alt + 0", "Qualquer tela", "Configurações."],
              ["?", "Qualquer tela", "Lista de atalhos."],
              ["Esc", "Qualquer tela", "Fechar menu, diálogo ou busca; na análise, voltar a Selecionar."],
              ["V, R, P, L", "Análise", "Selecionar, desenhar região, medir ponto, traçar linha."],
              ["I, F", "Análise", "Isoterma; foto visível."],
              ["0, + e −", "Análise", "Encaixar a imagem; aproximar e afastar (também pela roda do mouse)."],
              ["← →", "Análise", "Região anterior e seguinte."],
              ["Delete", "Análise", "Apagar a região selecionada (com Desfazer)."],
              ["↑ ↓", "Pendências", "Pendência anterior e seguinte."],
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
              ["Não avaliado", "Peça que só se compara com a igual de outra fase (para-raio, isolador), sozinha na imagem."],
              ["Sem medida", "Inspeção sem temperatura: imagem sem dados radiométricos nem escala legível, ou foto do celular."],
              ["Conferir", "A severidade vem de calor fora das peças identificadas: confirme na imagem antes de agir."],
              ["INT8", "Versão rápida de um modelo, com os pesos em 8 bits."],
          ], [32, LARGURA / mm - 32])]
    return c


def main() -> None:
    doc = Documento(str(SAIDA))
    doc.multiBuild(conteudo())
    print("manual:", SAIDA, f"({SAIDA.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
