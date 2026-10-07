"""Relatório de inspeção termográfica em PDF.

Estrutura segundo a ABNT NBR 15572 (guia de inspeção) e avaliação segundo a ABNT NBR 15866
(metodologia de avaliação de temperatura de trabalho). Um relatório pode ter uma ou várias imagens:
identificação, normas e critério, resumo, um registro por imagem (termograma com marcadores
numerados, foto visível, condições de medição e tabela de pontos), conclusão, referências de
temperatura e responsável técnico, escolhido no cadastro de Configurações.
"""

from __future__ import annotations

import hashlib
import io
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Image as RLImage
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from nucleo import analise as nucleo_analise
from nucleo import render

# Cores dos tokens da interface (app/estatico/tokens.css): tinta --n-900, azul --azul-800/600.
AZUL = colors.HexColor("#171B33")      # títulos e texto forte
CABECALHO = colors.HexColor("#2A358F") # fundo do cabeçalho das tabelas
ACENTO = colors.HexColor("#3F50D6")    # fio do cabeçalho
CINZA = colors.HexColor("#5F6886")
LINHA = colors.HexColor("#DFE3EE")
FUNDO = colors.HexColor("#F6F7FB")
COR_SEV = {k: colors.Color(*(c / 255 for c in v)) for k, v in render.CORES_SEVERIDADE.items()}
LARGURA_UTIL = 176 * mm

NORMAS = [
    ("ABNT NBR 15572:2013", "Ensaios não destrutivos — Termografia — Guia para inspeção de equipamentos elétricos e mecânicos."),
    ("ABNT NBR 15866:2010", "Ensaios não destrutivos — Termografia — Metodologia de avaliação de temperatura de trabalho de equipamentos em sistemas elétricos."),
    ("ABNT NBR 15424", "Ensaios não destrutivos — Termografia — Terminologia."),
]

# Avisos da análise reescritos para o relatório (sem instruções de tela).
OBSERVACOES = [
    ("Sem temperatura ambiente", "Temperatura ambiente não informada: a comparação com a MTA considera a temperatura medida, sem projeção para plena carga."),
    ("Sem a carga do momento", "Carga no momento da medição não informada: a projeção considera medição em plena carga."),
    ("Regiões sem componente semelhante", "Pontos sem componente semelhante para comparação e sem projeção de carga têm classificação indicativa (assinalados com *)."),
    ("O ponto mais quente passa de", "Temperatura acima de 150 °C registrada: verificar se decorre de reflexo ou de radiação solar direta sobre o componente."),
]


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
    texto = f"{v:.{casas}f}"
    if texto.startswith("-") and float(texto) == 0:  # -0,0 vira 0,0
        texto = texto[1:]
    return texto.replace(".", ",") + sufixo


def _data(iso: str | None, com_hora: bool = False) -> str:
    """'2025-06-12T14:03:22' -> '12/06/2025' (ou '12/06/2025 14:03')."""
    if not iso:
        return "–"
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", ""))
    except ValueError:
        return str(iso)
    return d.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")


def _esc(texto) -> str:
    return str(texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _imagem(pil: Image.Image, largura_mm: float) -> RLImage:
    buf = io.BytesIO()
    pil.convert("RGB").save(buf, format="JPEG", quality=88)
    buf.seek(0)
    altura = largura_mm * pil.height / pil.width
    return RLImage(buf, width=largura_mm * mm, height=altura * mm)


def _observacoes(avisos: list[str]) -> list[str]:
    saida = []
    for aviso in avisos:
        troca = next((texto for inicio, texto in OBSERVACOES if aviso.startswith(inicio)), None)
        saida.append(troca or aviso)
    return list(dict.fromkeys(saida))


def numero_relatorio(ids: list[str], quando: datetime) -> str:
    base = hashlib.sha1("".join(sorted(ids)).encode()).hexdigest()[:4].upper()
    return f"RT-{quando:%Y%m%d}-{base}"


class _Paginas(rl_canvas.Canvas):
    """Canvas que conhece o total de páginas (para o "Página x de y")."""

    def __init__(self, *args, rodape=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas = []
        self._rodape = rodape

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            if self._rodape:
                self._rodape(self, total)
            super().showPage()
        super().save()


def gerar(analise: dict, matriz: np.ndarray, foto: bytes | None, versao: str, empresa: dict | None = None,
          responsavel: dict | None = None, art: str | None = None, criterios: dict | None = None, logo: bytes | None = None) -> bytes:
    """Relatório de uma imagem."""
    return gerar_relatorio([(analise, matriz, foto)], versao, empresa, responsavel, art, criterios, logo)


def gerar_relatorio(itens: list[tuple[dict, np.ndarray, bytes | None]], versao: str, empresa: dict | None = None,
                    responsavel: dict | None = None, art: str | None = None, criterios: dict | None = None,
                    logo: bytes | None = None) -> bytes:
    """Relatório de uma ou várias imagens, na ordem recebida. ``logo``: PNG da empresa para o cabeçalho."""
    if not itens:
        raise ValueError("Nenhuma imagem para o relatório.")
    fonte, negrito = _fontes()
    delta = "Δ" if fonte == "TV" else "Delta "
    empresa = empresa or {}
    responsavel = responsavel or {}
    crit = {**nucleo_analise.CRITERIOS_PADRAO, **(criterios or {})}
    agora = datetime.now()
    numero = numero_relatorio([a["id"] for a, _, _ in itens], agora)
    est = {
        "titulo": ParagraphStyle("t", fontName=negrito, fontSize=15, textColor=AZUL, leading=19),
        "sub": ParagraphStyle("s", fontName=fonte, fontSize=9, textColor=CINZA, leading=12),
        "h": ParagraphStyle("h", fontName=negrito, fontSize=11, textColor=AZUL, spaceBefore=9, spaceAfter=4, leading=14),
        "h2": ParagraphStyle("h2", fontName=negrito, fontSize=10, textColor=AZUL, spaceBefore=4, spaceAfter=3, leading=13),
        "p": ParagraphStyle("p", fontName=fonte, fontSize=9, leading=12.5, alignment=TA_LEFT),
        "pequeno": ParagraphStyle("pq", fontName=fonte, fontSize=7.5, textColor=CINZA, leading=10),
        "cel": ParagraphStyle("c", fontName=fonte, fontSize=8, leading=10),
        "celb": ParagraphStyle("cb", fontName=negrito, fontSize=8, leading=10, textColor=colors.white),
        "direita": ParagraphStyle("r", fontName=fonte, fontSize=8, textColor=CINZA, alignment=TA_RIGHT, leading=11),
    }

    def chave_valor(pares, largura_rotulo=46 * mm):
        t = Table([[Paragraph(k, est["pequeno"]), Paragraph(v if isinstance(v, str) else str(v), est["p"])] for k, v in pares],
                  colWidths=[largura_rotulo, LARGURA_UTIL - largura_rotulo])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, LINHA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        return t

    def tabela(cabecalho, linhas, larguras, faixas=None):
        dados = [[Paragraph(c, est["celb"]) for c in cabecalho]] + linhas
        estilo = [("BACKGROUND", (0, 0), (-1, 0), CABECALHO), ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINHA),
                  ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        for i, cor in (faixas or {}).items():
            estilo.append(("LINEBEFORE", (0, i), (0, i), 3, cor))
        t = Table(dados, colWidths=larguras, repeatRows=1)
        t.setStyle(TableStyle(estilo))
        return t

    corpo: list = []
    # ---------------------------------------------------------------- cabeçalho
    nome_empresa = _esc(empresa.get("nome", "").strip())
    marca = f"<b>{nome_empresa}</b>" if nome_empresa else "<b>Inspeção termográfica</b>"
    if empresa.get("subtitulo", "").strip():
        marca += f'<br/><font size="8" color="#5F6886">{_esc(empresa["subtitulo"].strip())}</font>'
    celulas = [Paragraph(marca, ParagraphStyle("m", fontName=negrito, fontSize=12, textColor=AZUL, leading=15)),
               Paragraph(f"Relatório nº <b>{numero}</b><br/>Emissão: {agora:%d/%m/%Y}", est["direita"])]
    larguras = [110 * mm, 66 * mm]
    if logo:
        try:
            img = Image.open(io.BytesIO(logo))
            img.load()
            altura_mm = 14
            largura_mm = min(40, altura_mm * img.width / img.height)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            celulas.insert(0, RLImage(buf, width=largura_mm * mm, height=largura_mm * img.height / img.width * mm))
            larguras = [largura_mm * mm + 4 * mm, 110 * mm - largura_mm * mm - 4 * mm, 66 * mm]
        except OSError:
            pass  # logotipo ilegível: o cabeçalho sai só com o nome
    cab = Table([celulas], colWidths=larguras)
    cab.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 1.2, ACENTO), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    corpo += [cab, Spacer(1, 5 * mm), Paragraph("Relatório de inspeção termográfica", est["titulo"])]
    n_img = len(itens)
    corpo.append(Paragraph(f"{n_img} {'registro termográfico' if n_img == 1 else 'registros termográficos'} · avaliação conforme ABNT NBR 15866", est["sub"]))

    # ---------------------------------------------------------------- 1. identificação
    def unicos(valores):
        return list(dict.fromkeys(v for v in valores if v))

    instalacoes = unicos(a.get("identificacao", {}).get("instalacao") for a, _, _ in itens)
    equipamentos = unicos(a.get("identificacao", {}).get("equipamento") for a, _, _ in itens)
    datas = sorted(unicos((a.get("metadados") or {}).get("data_hora") for a, _, _ in itens))
    # Quadro de vídeo ou imagem sem EXIF não sabe o termovisor: fica de fora em vez de "desconhecida".
    cameras = unicos(c for a, _, _ in itens if (c := (a.get("metadados") or {}).get("camera")) and c != "desconhecida")
    periodo = "–" if not datas else _data(datas[0]) if _data(datas[0]) == _data(datas[-1]) else f"{_data(datas[0])} a {_data(datas[-1])}"
    corpo.append(Paragraph("1. Identificação", est["h"]))
    corpo.append(chave_valor([
        ("Instalação", _esc(", ".join(instalacoes)) or "–"),
        ("Equipamentos", _esc(", ".join(equipamentos)) or "–"),
        ("Data da inspeção", _esc(periodo)),
        ("Termovisor", _esc(", ".join(cameras)) or "–"),
        ("Responsável técnico", _esc(responsavel.get("nome")) + (f" — {_esc(responsavel['registro'])}" if responsavel.get("registro") else "") if responsavel.get("nome") else "–"),
    ]))

    # ---------------------------------------------------------------- 2. normas e critério
    corpo.append(Paragraph("2. Normas e critério de avaliação", est["h"]))
    for codigo, titulo in NORMAS:
        corpo.append(Paragraph(f"<b>{codigo}</b> — {titulo}", est["p"]))
    corpo.append(Spacer(1, 2 * mm))
    corpo.append(Paragraph(
        "Cada componente é avaliado pela temperatura máxima medida em sua área. Em partes que conduzem corrente, a temperatura "
        "é comparada com a máxima temperatura admissível (MTA) do componente, após projeção para plena carga: "
        f"T<sub>proj</sub> = T<sub>amb</sub> + (T<sub>medida</sub> − T<sub>amb</sub>) × (100 / carga)<super>2</super>. Componentes "
        f"iguais de fases diferentes são comparados entre si ({delta}T para a mediana dos semelhantes). Em para-raios e isoladores, "
        f"cujo aquecimento é dielétrico, vale o {delta}T entre semelhantes, sem projeção de carga.", est["p"]))

    def faixas_texto(faixas, sufixo):
        return " · ".join(f"{nucleo_analise.NIVEIS[n]['rotulo']} ≥ {_num(v, 1 if v % 1 else 0)}{sufixo}" for v, n in faixas)

    linhas_crit = [
        [Paragraph(f"{delta}T entre semelhantes (partes condutoras)", est["cel"]), Paragraph(faixas_texto(crit["similares"], " °C"), est["cel"])],
        [Paragraph(f"{delta}T entre semelhantes (para-raios e isoladores)", est["cel"]), Paragraph(faixas_texto(crit["dieletrico"], " °C"), est["cel"])],
        [Paragraph("Temperatura projetada em relação à MTA", est["cel"]), Paragraph(faixas_texto(crit["mta_faixas"], " %"), est["cel"])],
    ]
    corpo.append(Spacer(1, 2 * mm))
    corpo.append(tabela(["Critério", "Classificação"], linhas_crit, [62 * mm, 114 * mm]))
    linhas_acao = [[Paragraph(n["rotulo"], est["cel"]), Paragraph(n["acao"], est["cel"])] for n in nucleo_analise.NIVEIS.values()]
    corpo.append(Spacer(1, 2 * mm))
    corpo.append(tabela(["Classificação", "Recomendação"], linhas_acao, [40 * mm, 136 * mm],
                        {i: COR_SEV[k] for i, k in enumerate(nucleo_analise.NIVEIS, start=1)}))

    # ---------------------------------------------------------------- 3. resumo (várias imagens)
    def rotulo_imagem(a):
        i = a.get("identificacao", {})
        return _esc(i.get("equipamento") or Path(a["arquivo"]).stem)

    if n_img > 1:
        corpo.append(Paragraph("3. Resumo dos resultados", est["h"]))
        linhas, faixas = [], {}
        for k, (a, _, _) in enumerate(itens, start=1):
            r = a["resumo"]
            p = r.get("ponto_mais_quente")
            onde = _esc(p["componente"]["nome"]) if p and p.get("componente") else "–"
            linhas.append([Paragraph(f"4.{k}", est["cel"]), Paragraph(f"{rotulo_imagem(a)}<br/><font size='6.5' color='#5F6886'>{_esc(a['arquivo'])}</font>", est["cel"]),
                           Paragraph(_num(p["t_max"], 1, " °C") if p else "–", est["cel"]), Paragraph(onde, est["cel"]),
                           Paragraph(_esc(r["severidade_rotulo"]), est["cel"])])
            faixas[k] = COR_SEV.get(r["severidade"], CINZA)
        corpo.append(tabela(["Item", "Equipamento / imagem", "Tmáx", "Local da Tmáx", "Classificação"], linhas,
                            [14 * mm, 62 * mm, 22 * mm, 46 * mm, 32 * mm], faixas))

    # ---------------------------------------------------------------- 4. registros termográficos
    referencias_usadas: dict[str, dict] = {}
    for k, (a, matriz, foto) in enumerate(itens, start=1):
        if n_img > 1:
            corpo.append(PageBreak())  # cada registro começa numa página: título, termograma e tabela juntos
        meta, cond, ident, resumo = a.get("metadados") or {}, a.get("condicoes") or {}, a.get("identificacao") or {}, a["resumo"]
        regioes = a["regioes"]
        prefixo = f"4.{k} " if n_img > 1 else ""
        titulos = [Paragraph("4. Registros termográficos" if n_img > 1 else "3. Registro termográfico", est["h"])] if k == 1 else []
        titulos.append(Paragraph(f"{prefixo}{rotulo_imagem(a)}", est["h2"]))

        exib = a.get("exibicao") or {}
        faixa_tela = tuple(exib["faixa"]) if exib.get("faixa") else None
        medicoes = a.get("medicoes") or []
        termo = render.desenhar(matriz, regioes, largura=1100, numerar=True, nome=exib.get("paleta") or "ferro",
                                medicoes=medicoes, faixa=faixa_tela)
        if foto:
            visivel = Image.open(io.BytesIO(foto)).convert("RGB")
            imgs = Table([[_imagem(termo, 86), _imagem(visivel, 86)]], colWidths=[88 * mm, 88 * mm])
            imgs.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            corpo.append(KeepTogether([*titulos, imgs]))
            legenda = "Termograma com os pontos numerados (à esquerda) e imagem visível (à direita)."
        else:
            corpo.append(KeepTogether([*titulos, _imagem(termo, 120)]))
            legenda = "Termograma com os pontos numerados."
        t_lo, t_hi = faixa_tela or render.faixa_exibicao(matriz)
        corpo.append(Paragraph(f"{legenda} Escala de {_num(t_lo)} °C a {_num(t_hi)} °C.", est["pequeno"]))
        corpo.append(Spacer(1, 2 * mm))

        amb, carga = cond.get("ambiente_c"), cond.get("carga_pct")
        corpo.append(chave_valor([
            ("Arquivo · data e hora", f"{_esc(a['arquivo'])} · {_esc(_data(meta.get('data_hora'), com_hora=True))}"),
            ("Temperatura", "medida (termograma radiométrico)" if a.get("radiometrica") else "estimada pela escala de cores da imagem"),
            ("Emissividade · distância", f"{_num(meta.get('emissividade'), 2)} · {_num(meta.get('distancia_m'), 1, ' m')}"),
            ("T. refletida · T. ambiente", f"{_num(meta.get('temp_refletida_c'), 1, ' °C')} · " + (_num(amb, 1, " °C") if amb is not None else "não informada")),
            ("Carga no momento", _num(carga, 0, " %") if carga is not None else "não informada"),
        ]))
        corpo.append(Spacer(1, 2 * mm))

        linhas, faixas = [], {}
        for i, r in enumerate(regioes, start=1):
            m, ref = r.get("medida") or {}, r.get("referencia") or {}
            if ref.get("nome"):
                referencias_usadas[ref["nome"]] = ref
            nome = _esc(r.get("nome") or r.get("classe", ""))
            if r.get("componente"):
                nome += f"<br/><font size='6.5' color='#5F6886'>em {_esc(r['componente']['nome'])}</font>"
            if r.get("ref_tipo") == "semelhantes":
                referencia, desvio = f"semelhantes ({_num(r['medida']['t_max'] - r['dt_ref'], 1, ' °C')})", _num(r.get("dt_corrigido"), 1, " °C")
            elif r.get("pct_mta") is not None:
                referencia, desvio = f"MTA {_num(ref.get('mta_c'), 0, ' °C')}", _num(r.get("pct_mta"), 0, " %")
            elif r.get("dt_entorno") is not None:
                referencia, desvio = "entorno", _num(r.get("dt_entorno"), 1, " °C")
            else:
                referencia, desvio = "–", "–"
            classe = _esc(r.get("severidade_rotulo", "–")) + (" *" if r.get("indicativa") else "")
            linhas.append([Paragraph(str(i), est["cel"]), Paragraph(nome, est["cel"]), Paragraph(_num(m.get("t_max"), 1, " °C"), est["cel"]),
                           Paragraph(referencia, est["cel"]), Paragraph(desvio, est["cel"]), Paragraph(classe, est["cel"]),
                           Paragraph(_esc(r.get("acao", "")), est["cel"])])
            faixas[i] = COR_SEV.get(r.get("severidade"), CINZA)
        if not linhas:
            linhas = [[Paragraph("–", est["cel"]), Paragraph("Nenhum ponto avaliado.", est["cel"])] + [""] * 5]
        corpo.append(tabela(["Nº", "Ponto", "Tmáx", "Referência", f"{delta}T / % MTA", "Classificação", "Recomendação"], linhas,
                            [9 * mm, 38 * mm, 17 * mm, 30 * mm, 19 * mm, 24 * mm, 39 * mm], faixas))

        if medicoes:
            linhas_med = []
            for med in medicoes:
                v = med.get("valor") or {}
                if med["tipo"] == "ponto":
                    linhas_med.append([Paragraph(med["nome"], est["cel"]), Paragraph("Ponto", est["cel"]), Paragraph(_num(v.get("t"), 1, " °C"), est["cel"]),
                                       Paragraph("–", est["cel"]), Paragraph("–", est["cel"])])
                else:
                    linhas_med.append([Paragraph(med["nome"], est["cel"]), Paragraph("Linha (perfil)", est["cel"]), Paragraph(_num(v.get("t_max"), 1, " °C"), est["cel"]),
                                       Paragraph(_num(v.get("t_min"), 1, " °C"), est["cel"]), Paragraph(_num(v.get("t_med"), 1, " °C"), est["cel"])])
            corpo.append(Spacer(1, 1.5 * mm))
            corpo.append(KeepTogether([Paragraph("Pontos e linhas de medição", est["pequeno"]),
                                       tabela(["Nome", "Tipo", "Máxima", "Mínima", "Média"], linhas_med, [20 * mm, 50 * mm, 35 * mm, 35 * mm, 36 * mm])]))

        ponto = resumo.get("ponto_mais_quente")
        if ponto:
            onde = f" em {_esc(ponto['componente']['nome'])}" if ponto.get("componente") else ""
            dentro = ", ".join(_esc(c["nome"]) for c in ponto.get("dentro_de") or [])
            corpo.append(Spacer(1, 2 * mm))
            corpo.append(Paragraph(f"<b>Temperatura máxima nos componentes:</b> {_num(ponto['t_max'], 1, ' °C')}{onde}" + (f" ({dentro})" if dentro else "") + ".", est["p"]))
        grupos = [g for g in resumo.get("comparacao_componentes") or [] if len(g["itens"]) >= 2]
        if grupos:
            corpo.append(Spacer(1, 1.5 * mm))
            linhas_comp = []
            for g in grupos:
                for j, it in enumerate(g["itens"]):
                    sinal = "+" if (it.get("dt") or 0) > 0 else ""
                    linhas_comp.append([Paragraph(_esc(g["nome"]) if j == 0 else "", est["cel"]), Paragraph(_esc(it["nome"]), est["cel"]),
                                        Paragraph(_num(it["t_max"], 1, " °C"), est["cel"]),
                                        Paragraph(sinal + _num(it.get("dt"), 1, " °C") if it.get("dt") is not None else "–", est["cel"])])
            corpo.append(KeepTogether([Paragraph("Comparação entre componentes semelhantes", est["pequeno"]),
                                       tabela(["Componente", "Fase / peça", "Tmáx", f"{delta}T para a referência"], linhas_comp,
                                              [48 * mm, 58 * mm, 30 * mm, 40 * mm])]))
        observacoes = _observacoes(resumo.get("avisos", []))
        if observacoes or ident.get("observacoes"):
            corpo.append(Spacer(1, 2 * mm))
            corpo.append(Paragraph("Observações", est["pequeno"]))
            for o in observacoes:
                corpo.append(Paragraph("• " + _esc(o), est["pequeno"]))
            if ident.get("observacoes"):
                corpo.append(Paragraph("• " + _esc(ident["observacoes"]), est["pequeno"]))

    # ---------------------------------------------------------------- conclusão
    corpo.append(Paragraph(f"{5 if n_img > 1 else 4}. Conclusão", est["h"]))
    pior = nucleo_analise.pior(a["resumo"]["severidade"] for a, _, _ in itens)
    achados = [(k, a, r) for k, (a, _, _) in enumerate(itens, start=1) for r in a["regioes"] if r.get("severidade", "normal") != "normal"]
    if not achados:
        texto = ("Não foram identificadas anomalias térmicas acima dos limites do critério nos componentes avaliados. "
                 "Recomenda-se manter a periodicidade de inspeção.")
    else:
        quantas = "Foi identificada 1 anomalia térmica que requer ação" if len(achados) == 1 else f"Foram identificadas {len(achados)} anomalias térmicas que requerem ação"
        texto = f"{quantas}, {'em' if len(achados) == 1 else 'a mais severa em'} nível {nucleo_analise.NIVEIS[pior]['rotulo'].lower()}:"
    conclusao = Table([[Paragraph(f"<b>{_esc(nucleo_analise.NIVEIS[pior]['rotulo'])}.</b> {texto}", est["p"])]], colWidths=[LARGURA_UTIL])
    conclusao.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), FUNDO), ("LINEBEFORE", (0, 0), (0, 0), 4, COR_SEV.get(pior, CINZA)),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    corpo.append(conclusao)
    if achados:
        linhas = []
        for k, a, r in sorted(achados, key=lambda x: -nucleo_analise.NIVEIS[x[2]["severidade"]]["ordem"]):
            item = f"4.{k} {rotulo_imagem(a)}" if n_img > 1 else rotulo_imagem(a)
            linhas.append([Paragraph(item, est["cel"]), Paragraph(_esc(r.get("nome")), est["cel"]), Paragraph(_esc(r.get("severidade_rotulo")), est["cel"]),
                           Paragraph(_esc(r.get("acao")), est["cel"])])
        corpo.append(Spacer(1, 2 * mm))
        corpo.append(tabela(["Equipamento", "Ponto", "Classificação", "Recomendação"], linhas, [46 * mm, 40 * mm, 32 * mm, 58 * mm]))
    corpo.append(Spacer(1, 2 * mm))
    corpo.append(Paragraph("A inspeção termográfica reflete as condições do instante da medição e não substitui outros ensaios.", est["pequeno"]))

    # ---------------------------------------------------------------- referências de temperatura
    if referencias_usadas:
        corpo.append(Paragraph(f"{6 if n_img > 1 else 5}. Referências de temperatura", est["h"]))
        linhas = [[Paragraph(_esc(nome), est["cel"]), Paragraph(_num(ref.get("mta_c"), 0, " °C") if ref.get("mta_c") else "não se aplica (comparação entre semelhantes)", est["cel"]),
                   Paragraph(_esc(ref.get("fonte", "")), est["cel"])] for nome, ref in referencias_usadas.items()]
        corpo.append(tabela(["Componente", "MTA", "Fonte"], linhas, [40 * mm, 46 * mm, 90 * mm]))

    # ---------------------------------------------------------------- responsável técnico
    secao = 7 if n_img > 1 else 6
    if not referencias_usadas:
        secao -= 1
    linhas_assin = [
        [Paragraph("Responsável técnico", est["pequeno"]), Paragraph("Registro profissional", est["pequeno"])],
        [Paragraph(f"<b>{_esc(responsavel.get('nome')) or '&nbsp;'}</b>" + (f"<br/>{_esc(responsavel['funcao'])}" if responsavel.get("funcao") else ""), est["p"]),
         Paragraph(_esc(responsavel.get("registro")) or "&nbsp;", est["p"])],
        [Paragraph("ART nº", est["pequeno"]), Paragraph("Local e data", est["pequeno"])],
        [Paragraph(_esc(art) or "&nbsp;", est["p"]), Paragraph("_________________________, ____/____/______", est["p"])],
        [Paragraph("<br/><br/>_______________________________________<br/>Assinatura", est["p"]), Paragraph("", est["p"])],
    ]
    assinatura = Table(linhas_assin, colWidths=[88 * mm, 88 * mm])
    assinatura.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 3), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    corpo += [Spacer(1, 4 * mm), KeepTogether([Paragraph(f"{secao}. Responsável técnico", est["h"]), assinatura])]

    rodape_empresa = empresa.get("nome", "").strip()

    def rodape(canvas, total):
        canvas.saveState()
        canvas.setFont(fonte, 7)
        canvas.setFillColor(CINZA)
        canvas.setStrokeColor(LINHA)
        canvas.line(17 * mm, 13.5 * mm, 193 * mm, 13.5 * mm)
        texto = f"Relatório nº {numero}" + (f" · {rodape_empresa}" if rodape_empresa else "")
        canvas.drawString(17 * mm, 10 * mm, texto)
        canvas.drawRightString(193 * mm, 10 * mm, f"Página {canvas.getPageNumber()} de {total}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm, topMargin=14 * mm, bottomMargin=18 * mm,
                            title=f"Relatório de inspeção termográfica {numero}", author=rodape_empresa or "Inspeção termográfica",
                            creator=f"Pyron {versao}")
    doc.build(corpo, canvasmaker=lambda *a, **k: _Paginas(*a, rodape=rodape, **k))
    return buf.getvalue()
