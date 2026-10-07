"""Equipamentos: as inspeções agrupadas por instalação e equipamento, com histórico e tendência.

É o que transforma fotos soltas em manutenção preditiva. Cada equipamento tem:

- a série da temperatura máxima ao longo das inspeções (data da captura, não do envio);
- a tendência dessa série, em °C por mês, por mínimos quadrados (só com 3 inspeções ou mais,
  espalhadas por pelo menos um mês: em poucos dias, a diferença é de carga e de horário);
- a projeção até a MTA, quando as regiões têm máxima admissível: em quantos dias o % da MTA
  chegaria a 100% se a tendência continuar (é uma estimativa e aparece como tal);
- a próxima inspeção, pela severidade atual: anual quando está normal (a NFPA 70B pede ao menos
  uma vez por ano) e mais cedo quanto pior estiver.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

import numpy as np

ORDEM = ["normal", "atencao", "programar", "urgente", "imediato"]
# Dias até reinspecionar, pela severidade da última inspeção.
PRAZO_DIAS = {"normal": 365, "atencao": 90, "programar": 30, "urgente": 7, "imediato": 1}
SEM_EQUIPAMENTO = "sem-equipamento"
MINIMO_PONTOS = 3
MINIMO_DIAS = 30  # em poucos dias a diferença é de carga e horário, não de desgaste


def chave(instalacao: str | None, equipamento: str | None) -> str:
    """Identificador estável e legível na URL: 'SE Campina Grande II' + 'TR-01' → 'se-campina-grande-ii--tr-01'."""
    if not (equipamento or "").strip():
        return SEM_EQUIPAMENTO

    def slug(t: str) -> str:
        t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", "-", t).strip("-")

    return f"{slug(instalacao)}--{slug(equipamento)}"


def _data(item: dict) -> datetime:
    """Data da captura (EXIF da câmera); sem ela, a data em que a imagem entrou no Pyron."""
    for valor in (item.get("data_captura"), (item.get("metadados") or {}).get("data_hora"), item.get("criado_em")):
        if valor:
            try:
                return datetime.fromisoformat(str(valor).replace(" ", "T")[:19])
            except ValueError:
                continue
    return datetime.now()


def ponto(item: dict) -> dict:
    """Um ponto da série a partir de um item da lista de inspeções (ou de uma análise completa)."""
    r = item.get("resumo") or {}
    d = item.get("destaque") or {}
    t_max = d.get("t_max") if d.get("t_max") is not None else r.get("t_max_cena")
    return {
        "id": item["id"],
        "data": _data(item).isoformat(timespec="seconds"),
        "t_max": None if t_max is None else round(float(t_max), 1),
        "pct_mta": None if r.get("maior_pct_mta") is None else round(float(r["maior_pct_mta"]), 1),
        "dt": None if d.get("dt") is None else round(float(d["dt"]), 1),
        "severidade": r.get("severidade", "normal"),
        "regiao": d.get("nome"),
    }


def tendencia(pontos: list[dict], campo: str = "t_max") -> dict | None:
    """Inclinação por mês (30 dias) da série, com o ajuste (R²). None com poucos pontos."""
    validos = [(datetime.fromisoformat(p["data"]), p[campo]) for p in pontos if p.get(campo) is not None]
    if len(validos) < MINIMO_PONTOS:
        return None
    t0 = min(d for d, _ in validos)
    x = np.array([(d - t0).total_seconds() / 86400 for d, _ in validos])
    y = np.array([v for _, v in validos], dtype=float)
    if x.max() - x.min() < MINIMO_DIAS:
        return None
    inclinacao, intercepto = np.polyfit(x, y, 1)
    previsto = inclinacao * x + intercepto
    total = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ((y - previsto) ** 2).sum() / total if total > 1e-9 else 0.0
    return {
        "por_mes": round(float(inclinacao * 30), 2),
        "por_dia": float(inclinacao),
        "r2": round(float(max(r2, 0.0)), 2),
        "n": len(validos),
        "ultimo_ajustado": float(inclinacao * x.max() + intercepto),
        "ultima_data": max(d for d, _ in validos).isoformat(timespec="seconds"),
    }


def projecao_mta(pontos: list[dict]) -> dict | None:
    """Se o % da MTA sobe, em quantos dias chegaria a 100% mantida a tendência (estimativa)."""
    t = tendencia(pontos, "pct_mta")
    if not t or t["por_dia"] <= 0 or t["ultimo_ajustado"] >= 100:
        return None
    dias = (100 - t["ultimo_ajustado"]) / t["por_dia"]
    if dias > 1825:  # mais de cinco anos à frente: não é uma previsão útil
        return None
    data = datetime.fromisoformat(t["ultima_data"]) + timedelta(days=dias)
    return {"dias": round(dias), "data": data.date().isoformat(), "r2": t["r2"], "confiavel": t["r2"] >= 0.5 and t["n"] >= 4}


def proxima_inspecao(ultima: dict, hoje: datetime | None = None) -> dict:
    data = datetime.fromisoformat(ultima["data"]) + timedelta(days=PRAZO_DIAS.get(ultima["severidade"], 365))
    hoje = hoje or datetime.now()
    return {"data": data.date().isoformat(), "vencida": data < hoje, "dias": (data.date() - hoje.date()).days,
            "prazo_dias": PRAZO_DIAS.get(ultima["severidade"], 365)}


def _grupos(itens: list[dict]) -> dict[str, dict]:
    grupos: dict[str, dict] = {}
    for it in itens:
        ident = it.get("identificacao") or {}
        k = chave(ident.get("instalacao"), ident.get("equipamento"))
        g = grupos.setdefault(k, {
            "chave": k,
            "instalacao": (ident.get("instalacao") or "").strip() if k != SEM_EQUIPAMENTO else "",
            "equipamento": (ident.get("equipamento") or "").strip() if k != SEM_EQUIPAMENTO else "",
            "itens": [],
        })
        g["itens"].append(it)
    return grupos


def resumir(g: dict, hoje: datetime | None = None) -> dict:
    pontos = sorted((ponto(it) for it in g["itens"]), key=lambda p: p["data"])
    ultima = pontos[-1]
    pior = max(pontos, key=lambda p: ORDEM.index(p["severidade"]) if p["severidade"] in ORDEM else 0)
    saida = {
        "chave": g["chave"],
        "instalacao": g["instalacao"],
        "equipamento": g["equipamento"],
        "inspecoes": len(pontos),
        "primeira": pontos[0]["data"],
        "ultima": ultima["data"],
        "ultima_id": ultima["id"],
        "severidade": ultima["severidade"],
        "pior": pior["severidade"],
        "t_max": ultima["t_max"],
        "serie": pontos,
        "tendencia": tendencia(pontos),
        "projecao_mta": projecao_mta(pontos),
    }
    if g["chave"] != SEM_EQUIPAMENTO:
        saida["proxima_inspecao"] = proxima_inspecao(ultima, hoje)
    for campo in ("por_dia", "ultimo_ajustado", "ultima_data"):
        if saida["tendencia"]:
            saida["tendencia"].pop(campo, None)
    return saida


def listar(itens: list[dict], hoje: datetime | None = None) -> list[dict]:
    """Equipamentos do pior estado para o melhor; os sem equipamento definido no fim."""
    lista = [resumir(g, hoje) for g in _grupos(itens).values()]
    return sorted(lista, key=lambda e: (e["chave"] == SEM_EQUIPAMENTO, -ORDEM.index(e["severidade"]), e["instalacao"].lower(), e["equipamento"].lower()))


def componentes(analises: list[dict]) -> list[dict]:
    """Por classe de componente, a máxima de cada inspeção: dá para ver qual peça está esquentando."""
    series: dict[str, dict] = {}
    for a in sorted(analises, key=_data):
        data = _data(a).isoformat(timespec="seconds")
        por_classe: dict[str, dict] = {}
        for r in a.get("regioes", []):
            t = (r.get("medida") or {}).get("t_max")
            if t is None:
                continue
            atual = por_classe.get(r.get("classe", "componente"))
            if atual is None or t > atual["t_max"]:
                por_classe[r.get("classe", "componente")] = {"t_max": round(float(t), 1), "nome": r.get("nome"),
                                                            "severidade": r.get("severidade", "normal"), "dt": r.get("dt_corrigido")}
        for classe, v in por_classe.items():
            s = series.setdefault(classe, {"classe": classe, "pontos": []})
            s["pontos"].append({"id": a["id"], "data": data, **v})
    saida = []
    for s in series.values():
        t = tendencia(s["pontos"])
        if t:
            t = {k: t[k] for k in ("por_mes", "r2", "n")}
        ultimo = s["pontos"][-1]
        saida.append({**s, "tendencia": t, "t_max": ultimo["t_max"], "severidade": ultimo["severidade"]})
    return sorted(saida, key=lambda s: -(s["t_max"] or 0))
