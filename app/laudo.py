"""Laudo de inspeção termográfica em PDF (estrutura inspirada na ABNT NBR 15572)."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as RLImage
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from nucleo import render

AZUL = colors.HexColor("#0F1B2D")
LARANJA = colors.HexColor("#E8590C")
CINZA = colors.HexColor("#5B6572")
LINHA = colors.HexColor("#D5DAE1")
FUNDO = colors.HexColor("#F4F6F8")
COR_SEV = {k: colors.Color(*(c / 255 for c in v)) for k, v in render.CORES_SEVERIDADE.items()}


def _fontes() -> tuple[str, str]:
    """Arial do Windows tem Δ e °; sem ela, cai para Helvetica (sem Δ)."""
    candidatas = [("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf")]
    for normal, negrito in candidatas:
        if Path(normal).exists() and Path(negrito).exists():
            if "TV" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("TV", normal))
                pdfmetrics.registerFont(TTFont("TV-B", negrito))
            return "TV", "TV-B"
    return "Helvetica", "Helvetica-Bold"


def _num(v, casas: int = 1, sufixo: str = "") -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "–"
    return f"{v:.{casas}f}".replace(".", ",") + sufixo


def _imagem(pil: Image.Image, largura_mm: float) -> RLImage:
    buf = io.BytesIO()
    pil.convert("RGB").save(buf, format="JPEG", quality=88)
    buf.seek(0)
    altura = largura_mm * pil.height / pil.width
    return RLImage(buf, width=largura_mm * mm, height=altura * mm)


def gerar(analise: dict, matriz: np.ndarray, foto: bytes | None, versao: str, empresa: dict | None = None) -> bytes:
    fonte, negrito = _fontes()
    empresa = empresa or {}
    nome_empresa = (empresa.get("nome") or "").strip()
    subtitulo_empresa = (empresa.get("subtitulo") or "").strip()
    delta = "Δ" if fonte == "TV" else "Delta "
    est = {
        "titulo": ParagraphStyle("t", fontName=negrito, fontSize=16, textColor=AZUL, leading=20),
        "sub": ParagraphStyle("s", fontName=fonte, fontSize=9, textColor=CINZA, leading=12),
        "h": ParagraphStyle("h", fontName=negrito, fontSize=11, textColor=AZUL, spaceBefore=8, spaceAfter=4, leading=14),
        "p": ParagraphStyle("p", fontName=fonte, fontSize=9, leading=12.5, alignment=TA_LEFT),
        "pequeno": ParagraphStyle("pq", fontName=fonte, fontSize=7.5, textColor=CINZA, leading=10),
        "cel": ParagraphStyle("c", fontName=fonte, fontSize=8, leading=10),
        "celb": ParagraphStyle("cb", fontName=negrito, fontSize=8, leading=10, textColor=colors.white),
    }
    ident = analise.get("identificacao", {})
    cond = analise.get("condicoes", {})
    meta = analise["metadados"]
    resumo = analise["resumo"]
    regioes = analise["regioes"]

    def tabela_chave_valor(pares):
        t = Table([[Paragraph(k, est["pequeno"]), Paragraph(str(v), est["p"])] for k, v in pares], colWidths=[42 * mm, 134 * mm])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, LINHA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        return t

    def _esc(texto: str) -> str:
        return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    marca = f'<font color="#E8590C">●</font> {_esc(nome_empresa) if nome_empresa else "Pyron"}'
    if subtitulo_empresa:
        marca += f'<br/><font size="8" color="#5B6572">{_esc(subtitulo_empresa)}</font>'
    corpo = []
    cab = Table(
        [
            [
                Paragraph(marca, ParagraphStyle("m", fontName=negrito, fontSize=13, textColor=AZUL, leading=16)),
                Paragraph(f"Laudo nº {analise['id'][:8].upper()}<br/>Emitido em {datetime.now():%d/%m/%Y %H:%M}", ParagraphStyle("r", fontName=fonte, fontSize=8, textColor=CINZA, alignment=2)),
            ]
        ],
        colWidths=[100 * mm, 76 * mm],
    )
    cab.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 1.2, LARANJA), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    corpo += [cab, Spacer(1, 6 * mm), Paragraph("Laudo de inspeção termográfica", est["titulo"])]
    corpo.append(Paragraph("Rascunho gerado automaticamente. Deve ser revisado e assinado por profissional habilitado antes da emissão.", est["sub"]))

    corpo.append(Paragraph("1. Identificação", est["h"]))
    corpo.append(
        tabela_chave_valor(
            [
                ("Instalação", ident.get("instalacao") or "–"),
                ("Equipamento", ident.get("equipamento") or "–"),
                ("Arquivo", analise["arquivo"]),
                ("Data da captura", meta.get("data_hora") or "–"),
                ("Câmera", meta.get("camera") or "–"),
            ]
        )
    )

    corpo.append(Paragraph("2. Condições de medição", est["h"]))
    amb = cond.get("ambiente_c")
    carga = cond.get("carga_pct")
    pares = [
        ("Origem da temperatura", "Medida (dados radiométricos da câmera)" if analise["radiometrica"] else "Estimada pela paleta de cores"),
        ("Emissividade", _num(meta.get("emissividade"), 2) if meta.get("emissividade") is not None else "–"),
        ("Distância", _num(meta.get("distancia_m"), 1, " m") if meta.get("distancia_m") is not None else "–"),
        ("Temperatura refletida", _num(meta.get("temp_refletida_c"), 1, " °C") if meta.get("temp_refletida_c") is not None else "–"),
        ("Temperatura ambiente", _num(amb, 1, " °C (informada)") if amb is not None else "não informada"),
        ("Carga no momento", _num(carga, 0, " %") if carga is not None else "não informada"),
    ]
    corpo.append(tabela_chave_valor(pares))

    corpo.append(Paragraph("3. Termograma", est["h"]))
    termo = render.desenhar(matriz, regioes, largura=1100)
    if foto:
        visivel = Image.open(io.BytesIO(foto)).convert("RGB")
        imgs = Table([[_imagem(termo, 86), _imagem(visivel, 86)]], colWidths=[88 * mm, 88 * mm])
        imgs.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        corpo.append(imgs)
        corpo.append(Paragraph("À esquerda, o termograma com as regiões analisadas; à direita, a foto visível da câmera.", est["pequeno"]))
    else:
        corpo.append(_imagem(termo, 120))
    t_lo, t_hi = render.faixa_exibicao(matriz)
    corpo.append(Paragraph(f"Escala de cores de {_num(t_lo)} °C a {_num(t_hi)} °C. Detector: {analise['modelo']['nome']}.", est["pequeno"]))

    corpo.append(Paragraph("4. Resultados por região", est["h"]))
    cab_tabela = ("Região", "Tmáx medida", "T projetada", "MTA", "% da MTA", f"{delta}T fases", "Severidade", "Ação")
    linhas = [[Paragraph(x, est["celb"]) for x in cab_tabela]]
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINHA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i, r in enumerate(regioes, start=1):
        m = r.get("medida") or {}
        ref = r.get("referencia") or {}
        sev = r.get("severidade_rotulo", "–")
        if r.get("criterio_disparo"):
            sev += f" ({', '.join(r['criterio_disparo'])})"
        if r.get("indicativa"):
            sev += ", indicativa"
        dt_fases = r.get("dt_corrigido") if r.get("ref_tipo") == "semelhantes" else None
        linhas.append(
            [
                Paragraph(f"{r.get('nome') or r.get('classe', '')}<br/><font size='6.5' color='#5B6572'>{ref.get('nome', '')}</font>", est["cel"]),
                Paragraph(_num(m.get("t_max"), 1, " °C"), est["cel"]),
                Paragraph(_num(r.get("t_projetada"), 1, " °C"), est["cel"]),
                Paragraph(_num(ref.get("mta_c"), 0, " °C") if ref.get("mta_c") else "–", est["cel"]),
                Paragraph(_num(r.get("pct_mta"), 0, " %"), est["cel"]),
                Paragraph(_num(dt_fases, 1, " °C"), est["cel"]),
                Paragraph(sev, est["cel"]),
                Paragraph(r.get("acao", ""), est["cel"]),
            ]
        )
        estilo.append(("LINEBEFORE", (0, i), (0, i), 3, COR_SEV.get(r.get("severidade"), CINZA)))
    if len(linhas) == 1:
        linhas.append([Paragraph("Nenhuma região analisada.", est["cel"])] + [""] * 7)
    tab = Table(linhas, colWidths=[27 * mm, 16 * mm, 16 * mm, 13 * mm, 14 * mm, 15 * mm, 33 * mm, 42 * mm], repeatRows=1)
    tab.setStyle(TableStyle(estilo))
    corpo.append(tab)

    corpo.append(Paragraph("5. Conclusão", est["h"]))
    conclusao = Table([[Paragraph(f"<b>{resumo['severidade_rotulo']}.</b> {resumo['mensagem']}", est["p"])]], colWidths=[176 * mm])
    conclusao.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), FUNDO),
                ("LINEBEFORE", (0, 0), (0, 0), 4, COR_SEV.get(resumo["severidade"], CINZA)),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    corpo.append(conclusao)
    for aviso in resumo.get("avisos", []):
        corpo.append(Paragraph("• " + aviso, est["pequeno"]))
    if ident.get("observacoes"):
        corpo.append(Paragraph("Observações: " + ident["observacoes"], est["p"]))

    corpo.append(Paragraph("6. Referências e critério", est["h"]))
    corpo.append(
        Paragraph(
            f"Critério: {resumo['criterio']}. Conforme a ABNT NBR 15866, cada região é avaliada contra a máxima temperatura "
            f"admissível (MTA) do componente e contra o componente semelhante de outra fase. Temperatura projetada para plena "
            f"carga: T<sub>amb</sub> + (T<sub>medida</sub> − T<sub>amb</sub>) × (100 / carga)². {delta}T entre fases: diferença para a "
            "mediana das fases semelhantes, projetada para plena carga nas partes que conduzem corrente; em para-raios e "
            "isoladores, sem projeção e com faixa própria. A inspeção termográfica reflete o instante da medição e não "
            "substitui outros ensaios.",
            est["p"],
        )
    )
    usadas = {}
    for r in regioes:
        ref = r.get("referencia") or {}
        if ref.get("nome"):
            usadas[ref["nome"]] = ref
    if usadas:
        linhas_ref = [[Paragraph("Componente", est["celb"]), Paragraph("MTA", est["celb"]), Paragraph("Fonte", est["celb"])]]
        for nome, ref in usadas.items():
            linhas_ref.append(
                [
                    Paragraph(nome, est["cel"]),
                    Paragraph(_num(ref.get("mta_c"), 0, " °C") if ref.get("mta_c") else "não se aplica", est["cel"]),
                    Paragraph(ref.get("fonte", ""), est["cel"]),
                ]
            )
        t_ref = Table(linhas_ref, colWidths=[40 * mm, 22 * mm, 114 * mm])
        t_ref.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), AZUL), ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINHA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        corpo.append(Spacer(1, 3 * mm))
        corpo.append(t_ref)

    assinatura = Table(
        [
            [Paragraph("Responsável técnico", est["pequeno"]), Paragraph("Registro profissional / ART", est["pequeno"])],
            [Paragraph(ident.get("responsavel") or " ", est["p"]), Paragraph(ident.get("art") or " ", est["p"])],
            [Paragraph("Assinatura: ______________________________", est["p"]), Paragraph("Data: ____/____/______", est["p"])],
        ],
        colWidths=[88 * mm, 88 * mm],
    )
    assinatura.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 5)]))
    corpo += [Spacer(1, 6 * mm), KeepTogether([Paragraph("7. Responsabilidade técnica", est["h"]), assinatura])]

    simbolo = Path(__file__).parent / "estatico" / "marca" / "simbolo.png"

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont(fonte, 7)
        canvas.setFillColor(CINZA)
        x_texto = 17 * mm
        if simbolo.exists():
            canvas.drawImage(str(simbolo), 17 * mm, 8.6 * mm, width=4.4 * mm, height=4.4 * mm, mask="auto")
            x_texto += 5.6 * mm
        canvas.drawString(x_texto, 10 * mm, f"Gerado com Pyron {versao} · análise {analise['id'][:8]} · revisar antes de emitir")
        canvas.drawRightString(193 * mm, 10 * mm, f"Página {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm, topMargin=14 * mm, bottomMargin=16 * mm, title="Laudo de inspeção termográfica", author="Pyron")
    doc.build(corpo, onFirstPage=rodape, onLaterPages=rodape)
    return buf.getvalue()
