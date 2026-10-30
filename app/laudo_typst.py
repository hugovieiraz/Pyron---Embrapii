"""Relatório de inspeção termográfica em PDF pelo Typst (0.9, F3): o mesmo conteúdo de ``app.laudo``.

Mesmas assinaturas de ``laudo.gerar()`` e ``laudo.gerar_relatorio()``; a escolha entre os dois motores é a
configuração ``laudo.motor`` ("reportlab", o padrão até a aprovação do visual, ou "typst").

- **Motor:** o pacote ``typst`` do PyPI (Apache 2.0), com o compilador Typst em Rust embutido; não precisa de
  Rust instalado. Sem pacotes do Typst Universe: tudo é primitiva nativa (o servidor pode estar sem internet).
- **Segurança:** os dados entram só como JSON (``dados.json``, lido no modelo com ``json()``). Nenhum texto do
  usuário é colado no código Typst; no modelo, uma string do JSON vira texto literal, então ``#``, ``$``, ``@``,
  ``<``, ``]``, ``\\`` e crases não executam nada (``testes/test_laudo_typst.py``).
- **Fontes:** Noto Sans e, só para ≥, Noto Sans Math (SIL OFL 1.1, ``app/laudo/fontes/``), carregadas só da pasta do
  projeto, sem as fontes do sistema nem as embutidas no Typst: o PDF sai igual no Windows e no Linux.
- **Arquivos:** modelo, dados e imagens vão para uma pasta temporária por laudo, apagada no fim.
- **Código de conferência:** SHA-256 dos dados avaliados (inspeções, regiões, medidas, classificação e quem
  assina), impresso no laudo; quem tiver o banco refaz a conta e confere que o laudo descreve aqueles dados.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from app import laudo as base
from nucleo import analise as nucleo_analise
from nucleo import render

PASTA = Path(__file__).resolve().parent / "laudo"
FONTES = PASTA / "fontes"
MODELO = "modelo.typ"

_trava = threading.Lock()
_compilador = None


def _hex(cor) -> str:
    """Cor do reportlab (laudo.py) ou tupla RGB 0..255 em #rrggbb."""
    if hasattr(cor, "hexval"):
        return "#" + cor.hexval()[2:].lower()
    r, g, b = (int(v) for v in cor[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


CORES = {"azul": _hex(base.AZUL), "cabecalho": _hex(base.CABECALHO), "acento": _hex(base.ACENTO), "cinza": _hex(base.CINZA),
         "linha": _hex(base.LINHA), "fundo": _hex(base.FUNDO)}
COR_SEV = {k: _hex(v) for k, v in render.CORES_SEVERIDADE.items()}


def disponivel() -> str | None:
    """None se o Typst carrega; senão o motivo (pacote ausente ou DLL barrada pelo Windows)."""
    try:
        import typst  # noqa: F401
    except Exception as erro:  # noqa: BLE001 — ImportError, OSError (Controle Inteligente de Aplicativos)
        return f"{type(erro).__name__}: {erro}"[:300]
    return None


def _compilador_typst():
    """Um compilador só por processo (as fontes são lidas uma vez), só com as fontes do projeto."""
    global _compilador
    if _compilador is None:
        import typst

        fontes = typst.Fonts(include_system_fonts=False, include_embedded_fonts=False, font_paths=[str(FONTES)])
        _compilador = typst.Compiler(font_paths=fontes, ignore_system_fonts=True)
    return _compilador


# ---------------------------------------------------------------- dados do laudo (tudo já como texto)


def _sev(chave: str | None) -> str:
    return COR_SEV.get(chave or "", CORES["cinza"])


def _jpeg(pil: Image.Image, destino: Path) -> str:
    destino.parent.mkdir(parents=True, exist_ok=True)
    pil.convert("RGB").save(destino, format="JPEG", quality=88)
    return "/" + destino.relative_to(destino.parents[1]).as_posix()  # "/" = raiz do projeto Typst (vale dentro de partes/)


def codigo_conferencia(itens, responsavel: dict | None) -> str:
    """SHA-256 dos dados avaliados: o que muda o laudo muda o código."""
    dados = {
        "inspecoes": [{"id": a["id"], "arquivo": a.get("arquivo"), "resumo": a.get("resumo"),
                       "regioes": [{k: r.get(k) for k in ("id", "nome", "medida", "severidade", "pct_mta", "dt_corrigido")}
                                   for r in a.get("regioes") or []]} for a, _, _ in itens],
        "responsavel": {k: (responsavel or {}).get(k) for k in ("nome", "registro")},
    }
    return hashlib.sha256(json.dumps(dados, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _historico(itens, rotulo) -> dict | None:
    """Pontos do gráfico (0 a 1 nos dois eixos) e o texto, quando todas as imagens são do mesmo equipamento."""
    chaves = {((a.get("identificacao") or {}).get("instalacao", "").strip().lower(), (a.get("identificacao") or {}).get("equipamento", "").strip().lower())
              for a, _, _ in itens}
    pontos = sorted((base._quando(a), base._tmax(a), a["resumo"]["severidade"]) for a, _, _ in itens if base._tmax(a) is not None)
    if not (len(chaves) == 1 and next(iter(chaves))[1] and len(pontos) >= 2):
        return None
    texto = f"Máxima de cada inspeção de {rotulo(itens[0][0])} entre {pontos[0][0]:%d/%m/%Y} e {pontos[-1][0]:%d/%m/%Y}."
    ts = [p[0].timestamp() for p in pontos]
    vs = [p[1] for p in pontos]
    if len(pontos) >= 3 and (pontos[-1][0] - pontos[0][0]).days >= 30:
        k = np.polyfit(ts, vs, 1)[0] * 86400 * 30
        texto += f" Tendência: {'+' if k > 0 else ''}{base._num(float(k), 1)} °C por mês (reta tracejada, mínimos quadrados)."
    t0, t1 = min(ts), max(ts)
    if t1 - t0 < 86400:
        t0, t1 = t0 - 86400, t1 + 86400
    folga = max(1.0, (max(vs) - min(vs)) * 0.15)
    lo, hi = float(np.floor(min(vs) - folga)), float(np.ceil(max(vs) + folga))
    nx = lambda t: (t - t0) / (t1 - t0)  # noqa: E731
    ny = lambda v: (v - lo) / (hi - lo)  # noqa: E731
    tendencia = None
    if len(pontos) >= 3:
        k, b = np.polyfit(ts, vs, 1)
        tendencia = {"x0": nx(ts[0]), "y0": ny(k * ts[0] + b), "x1": nx(ts[-1]), "y1": ny(k * ts[-1] + b)}
    return {
        "texto": texto,
        "pontos": [{"x": nx(t), "y": ny(v), "cor": _sev(sev)} for t, v, sev in zip(ts, vs, (p[2] for p in pontos))],
        "eixo_y": [{"y": ny(v), "rotulo": base._num(float(v), 0)} for v in (lo, (lo + hi) / 2, hi)],
        "eixo_x": [{"x": nx(t), "rotulo": datetime.fromtimestamp(t).strftime("%d/%m/%Y"), "ancora": ancora}
                   for t, ancora in ((t0, "inicio"), ((t0 + t1) / 2, "meio"), (t1, "fim"))],
        "tendencia": tendencia,
    }


def montar_dados(itens, versao: str, empresa: dict | None, responsavel: dict | None, art: str | None,
                 criterios: dict | None, logo: bytes | None, pasta: Path, agora: datetime | None = None) -> dict:
    """O laudo como dados: os mesmos textos e números de ``laudo.gerar_relatorio``; as imagens vão para ``pasta``."""
    if not itens:
        raise ValueError("Nenhuma imagem para o relatório.")
    empresa = empresa or {}
    responsavel = responsavel or {}
    crit = {**nucleo_analise.CRITERIOS_PADRAO, **(criterios or {})}
    agora = agora or datetime.now()
    numero = base.numero_relatorio([a["id"] for a, _, _ in itens], agora)
    n_img = len(itens)
    delta = "Δ"
    nome_empresa = (empresa.get("nome") or "").strip()

    logo_arquivo = None
    if logo:
        try:
            img = Image.open(io.BytesIO(logo))
            img.load()
            (pasta / "img").mkdir(parents=True, exist_ok=True)
            img.save(pasta / "img" / "logo.png", format="PNG")
            logo_arquivo = {"arquivo": "/img/logo.png", "largura_mm": min(40.0, 14 * img.width / img.height)}
        except OSError:
            logo_arquivo = None  # logotipo ilegível: o cabeçalho sai só com o nome

    def unicos(valores):
        return list(dict.fromkeys(v for v in valores if v))

    def rotulo(a):
        return (a.get("identificacao") or {}).get("equipamento") or Path(a["arquivo"]).stem

    instalacoes = unicos((a.get("identificacao") or {}).get("instalacao") for a, _, _ in itens)
    equipamentos = unicos((a.get("identificacao") or {}).get("equipamento") for a, _, _ in itens)
    datas = sorted(unicos((a.get("metadados") or {}).get("data_hora") for a, _, _ in itens))
    cameras = unicos(c for a, _, _ in itens if (c := (a.get("metadados") or {}).get("camera")) and c != "desconhecida")
    periodo = "–" if not datas else base._data(datas[0]) if base._data(datas[0]) == base._data(datas[-1]) else f"{base._data(datas[0])} a {base._data(datas[-1])}"
    resp_texto = (responsavel.get("nome") + (f" — {responsavel['registro']}" if responsavel.get("registro") else "")) if responsavel.get("nome") else "–"

    def faixas_texto(faixas, sufixo):
        return " · ".join(f"{nucleo_analise.NIVEIS[n]['rotulo']} ≥ {base._num(v, 1 if v % 1 else 0)}{sufixo}" for v, n in faixas)

    niveis = [k for k in nucleo_analise.NIVEIS if k not in ("sem_medida", "nao_avaliado")]

    resumo = None
    historico = None
    if n_img > 1:
        resumo = []
        for k, (a, _, _) in enumerate(itens, start=1):
            r = a["resumo"]
            p = r.get("ponto_mais_quente")
            resumo.append({"item": f"4.{k}", "equipamento": rotulo(a), "arquivo": a["arquivo"],
                           "tmax": base._num(p["t_max"], 1, " °C") if p else "–",
                           "onde": p["componente"]["nome"] if p and p.get("componente") else "–",
                           "classe": r["severidade_rotulo"], "cor": _sev(r["severidade"])})
        historico = _historico(itens, rotulo)

    registros = []
    referencias_usadas: dict[str, dict] = {}
    for k, (a, matriz, foto) in enumerate(itens, start=1):
        meta, cond, ident, res = a.get("metadados") or {}, a.get("condicoes") or {}, a.get("identificacao") or {}, a["resumo"]
        regioes = a["regioes"]
        exib = a.get("exibicao") or {}
        faixa_tela = tuple(exib["faixa"]) if exib.get("faixa") else None
        medicoes = a.get("medicoes") or []
        termo = render.desenhar(matriz, regioes, largura=1100, numerar=True, nome=exib.get("paleta") or "ferro",
                                medicoes=medicoes, faixa=faixa_tela)
        termograma = _jpeg(termo, pasta / "img" / f"termograma-{k}.jpg")
        foto_arquivo = _jpeg(Image.open(io.BytesIO(foto)), pasta / "img" / f"foto-{k}.jpg") if foto else None
        legenda = ("Termograma com os pontos numerados (à esquerda) e imagem visível (à direita)." if foto
                   else "Termograma com os pontos numerados.")
        t_lo, t_hi = faixa_tela or render.faixa_exibicao(matriz)
        amb, carga = cond.get("ambiente_c"), cond.get("carga_pct")

        pontos = []
        for i, r in enumerate(regioes, start=1):
            m, ref = r.get("medida") or {}, r.get("referencia") or {}
            if ref.get("nome"):
                referencias_usadas[ref["nome"]] = ref
            if r.get("ref_tipo") == "semelhantes":
                referencia, desvio = f"semelhantes ({base._num(r['medida']['t_max'] - r['dt_ref'], 1, ' °C')})", base._num(r.get("dt_corrigido"), 1, " °C")
            elif r.get("pct_mta") is not None:
                referencia, desvio = f"MTA {base._num(ref.get('mta_c'), 0, ' °C')}", base._num(r.get("pct_mta"), 0, " %")
            elif r.get("dt_entorno") is not None:
                referencia, desvio = "entorno", base._num(r.get("dt_entorno"), 1, " °C")
            else:
                referencia, desvio = "–", "–"
            pontos.append({"n": str(i), "nome": r.get("nome") or r.get("classe", ""),
                           "em": f"em {r['componente']['nome']}" if r.get("componente") else "",
                           "tmax": base._num(m.get("t_max"), 1, " °C"), "referencia": referencia, "desvio": desvio,
                           "classe": (r.get("severidade_rotulo") or "–") + (" *" if r.get("indicativa") else ""),
                           "acao": r.get("acao") or "", "cor": _sev(r.get("severidade"))})

        linhas_med = []
        for med in medicoes:
            v = med.get("valor") or {}
            if med["tipo"] == "ponto":
                linhas_med.append([med["nome"], "Ponto", base._num(v.get("t"), 1, " °C"), "–", "–"])
            else:
                linhas_med.append([med["nome"], "Linha (perfil)", base._num(v.get("t_max"), 1, " °C"),
                                   base._num(v.get("t_min"), 1, " °C"), base._num(v.get("t_med"), 1, " °C")])

        ponto = res.get("ponto_mais_quente")
        tmax_texto = None
        if ponto:
            onde = f" em {ponto['componente']['nome']}" if ponto.get("componente") else ""
            dentro = ", ".join(c["nome"] for c in ponto.get("dentro_de") or [])
            tmax_texto = f"{base._num(ponto['t_max'], 1, ' °C')}{onde}" + (f" ({dentro})" if dentro else "") + "."
        comparacao = []
        for g in [g for g in res.get("comparacao_componentes") or [] if len(g["itens"]) >= 2]:
            for j, it in enumerate(g["itens"]):
                sinal = "+" if (it.get("dt") or 0) > 0 else ""
                comparacao.append([g["nome"] if j == 0 else "", it["nome"], base._num(it["t_max"], 1, " °C"),
                                   sinal + base._num(it.get("dt"), 1, " °C") if it.get("dt") is not None else "–"])
        observacoes = base._observacoes(res.get("avisos", []))
        if ident.get("observacoes"):
            observacoes.append(ident["observacoes"])

        registros.append({
            "secao": ("4. Registros termográficos" if n_img > 1 else "3. Registro termográfico") if k == 1 else None,
            "titulo": f"{f'4.{k} ' if n_img > 1 else ''}{rotulo(a)}",
            "termograma": termograma, "foto": foto_arquivo,
            "legenda": f"{legenda} Escala de {base._num(t_lo)} °C a {base._num(t_hi)} °C.",
            "dados": [
                ["Arquivo · data e hora", f"{a['arquivo']} · {base._data(meta.get('data_hora'), com_hora=True)}"],
                ["Temperatura", "medida (termograma radiométrico)" if a.get("radiometrica") else "estimada pela escala de cores da imagem"],
                ["Emissividade · distância", f"{base._num(meta.get('emissividade'), 2)} · {base._num(meta.get('distancia_m'), 1, ' m')}"],
                ["T. refletida · T. ambiente", f"{base._num(meta.get('temp_refletida_c'), 1, ' °C')} · " + (base._num(amb, 1, " °C") if amb is not None else "não informada")],
                ["Carga no momento", base._num(carga, 0, " %") if carga is not None else "não informada"],
            ],
            "pontos": pontos, "medicoes": linhas_med, "tmax": tmax_texto, "comparacao": comparacao, "observacoes": observacoes,
        })

    # ---------------------------------------------------------------- conclusão
    pior = nucleo_analise.pior(a["resumo"]["severidade"] for a, _, _ in itens)
    achados = [(k, a, r) for k, (a, _, _) in enumerate(itens, start=1) for r in a["regioes"]
               if r.get("severidade", "normal") not in nucleo_analise.SEM_CLASSIFICACAO]
    nao_avaliadas = [r.get("nome") for a, _, _ in itens for r in a["regioes"] if r.get("severidade") == "nao_avaliado"]
    if not achados and pior == "nao_avaliado":
        texto = ("Os componentes não puderam ser avaliados: para-raios e isoladores se comparam com a mesma peça das "
                 "outras fases, que não aparece nas imagens. Recomenda-se nova inspeção enquadrando as três fases.")
    elif not achados:
        texto = ("Não foram identificadas anomalias térmicas acima dos limites do critério nos componentes avaliados. "
                 "Recomenda-se manter a periodicidade de inspeção.")
    else:
        quantas = "Foi identificada 1 anomalia térmica que requer ação" if len(achados) == 1 else f"Foram identificadas {len(achados)} anomalias térmicas que requerem ação"
        texto = f"{quantas}, {'em' if len(achados) == 1 else 'a mais severa em'} nível {nucleo_analise.NIVEIS[pior]['rotulo'].lower()}:"
    conclusao = {
        "secao": f"{5 if n_img > 1 else 4}. Conclusão", "rotulo": nucleo_analise.NIVEIS[pior]["rotulo"], "texto": texto, "cor": _sev(pior),
        "achados": [[f"4.{k} {rotulo(a)}" if n_img > 1 else rotulo(a), r.get("nome") or "", r.get("severidade_rotulo") or "", r.get("acao") or ""]
                    for k, a, r in sorted(achados, key=lambda x: -nucleo_analise.NIVEIS[x[2]["severidade"]]["ordem"])],
        "nao_avaliadas": (", ".join(nao_avaliadas[:6]) + ("…" if len(nao_avaliadas) > 6 else "")) if nao_avaliadas and pior != "nao_avaliado" else None,
    }
    referencias = None
    if referencias_usadas:
        referencias = {"secao": f"{6 if n_img > 1 else 5}. Referências de temperatura",
                       "linhas": [[nome, base._num(ref.get("mta_c"), 0, " °C") if ref.get("mta_c") else "não se aplica (comparação entre semelhantes)",
                                   ref.get("fonte", "")] for nome, ref in referencias_usadas.items()]}
    secao_assinatura = (7 if n_img > 1 else 6) - (0 if referencias_usadas else 1)
    codigo = codigo_conferencia(itens, responsavel)

    return {
        "versao": versao, "numero": numero, "emissao": f"{agora:%d/%m/%Y}", "autor": nome_empresa or "Inspeção termográfica",
        "cores": CORES, "delta": delta,
        "empresa": {"nome": nome_empresa, "subtitulo": (empresa.get("subtitulo") or "").strip()}, "logo": logo_arquivo,
        "subtitulo": f"{n_img} {'registro termográfico' if n_img == 1 else 'registros termográficos'} · avaliação conforme ABNT NBR 15866",
        "identificacao": [["Instalação", ", ".join(instalacoes) or "–"], ["Equipamentos", ", ".join(equipamentos) or "–"],
                          ["Data da inspeção", periodo], ["Termovisor", ", ".join(cameras) or "–"], ["Responsável técnico", resp_texto]],
        "normas": [list(n) for n in base.NORMAS],
        "criterio": [[f"{delta}T entre semelhantes (partes condutoras)", faixas_texto(crit["similares"], " °C")],
                     [f"{delta}T entre semelhantes (para-raios e isoladores)", faixas_texto(crit["dieletrico"], " °C")],
                     ["Temperatura projetada em relação à MTA", faixas_texto(crit["mta_faixas"], " %")]],
        "acoes": [{"rotulo": nucleo_analise.NIVEIS[k]["rotulo"], "acao": nucleo_analise.NIVEIS[k]["acao"], "cor": _sev(k)} for k in niveis],
        "resumo": resumo, "historico": historico, "registros": registros, "conclusao": conclusao, "referencias": referencias,
        "assinatura": {"secao": f"{secao_assinatura}. Responsável técnico", "nome": responsavel.get("nome") or "",
                       "funcao": responsavel.get("funcao") or "", "registro": responsavel.get("registro") or "", "art": art or ""},
        "conferencia": " ".join(codigo[i:i + 4] for i in range(0, 32, 4)),
        "rodape": f"Relatório nº {numero}" + (f" · {nome_empresa}" if nome_empresa else ""),
    }


# ---------------------------------------------------------------- compilação


def gerar(analise: dict, matriz: np.ndarray, foto: bytes | None, versao: str, empresa: dict | None = None,
          responsavel: dict | None = None, art: str | None = None, criterios: dict | None = None, logo: bytes | None = None) -> bytes:
    """Relatório de uma imagem (mesma assinatura de ``laudo.gerar``)."""
    return gerar_relatorio([(analise, matriz, foto)], versao, empresa, responsavel, art, criterios, logo)


def gerar_relatorio(itens: list[tuple[dict, np.ndarray, bytes | None]], versao: str, empresa: dict | None = None,
                    responsavel: dict | None = None, art: str | None = None, criterios: dict | None = None,
                    logo: bytes | None = None) -> bytes:
    """Relatório de uma ou várias imagens (mesma assinatura de ``laudo.gerar_relatorio``)."""
    agora = datetime.now()
    with tempfile.TemporaryDirectory(prefix="pyron-laudo-") as tmp:
        pasta = Path(tmp)
        shutil.copy2(PASTA / MODELO, pasta / MODELO)
        shutil.copytree(PASTA / "partes", pasta / "partes")
        dados = montar_dados(itens, versao, empresa, responsavel, art, criterios, logo, pasta, agora)
        (pasta / "dados.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        with _trava:  # um compilador por processo: uma compilação por vez
            return _compilador_typst().compile(input=str(pasta / MODELO), root=str(pasta), format="pdf",
                                               timestamp=int(agora.astimezone(timezone.utc).timestamp()))
