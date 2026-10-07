"""Pendências: o acompanhamento de cada anomalia até a correção ser verificada.

Toda inspeção fora do normal vira uma pendência. O fluxo é o de uma equipe de manutenção:

    aberta → programada (com nº da ordem de serviço) → corrigida → verificada
                                                   ↘ descartada (falso alarme, peça já trocada…)

O prazo padrão sai da severidade (imediato 1 dia, urgente 7, programar 30, atenção 90, contados
da data da captura) e pode ser trocado. "Corrigida" ainda aguarda a reinspeção; quando uma
inspeção mais nova do mesmo equipamento sai normal, ela é sugerida como a verificação.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app import equipamentos as eq

STATUS = {
    "aberta": "Aberta",
    "programada": "Programada",
    "corrigida": "Corrigida, aguarda reinspeção",
    "verificada": "Verificada",
    "descartada": "Descartada",
}
EM_ANDAMENTO = ("aberta", "programada")  # contam para "vencida"
PENDENTES = ("aberta", "programada", "corrigida")


def prazo_padrao(severidade: str, detectada: datetime) -> date:
    return (detectada + timedelta(days=eq.PRAZO_DIAS.get(severidade, 90))).date()


def montar(it: dict, reinspecao: dict | None = None, hoje: date | None = None) -> dict:
    """Pendência a partir de um item da lista de inspeções (que traz o acompanhamento)."""
    hoje = hoje or date.today()
    ac = it.get("acompanhamento") or {}
    ident = it.get("identificacao") or {}
    detectada = eq._data(it)
    severidade = it["resumo"]["severidade"]
    prazo = date.fromisoformat(ac["prazo"]) if ac.get("prazo") else prazo_padrao(severidade, detectada)
    status = ac.get("status") or "aberta"
    d = it.get("destaque") or {}
    return {
        "id": it["id"],
        "arquivo": it["arquivo"],
        "instalacao": ident.get("instalacao", ""),
        "equipamento": ident.get("equipamento", ""),
        "equipamento_chave": eq.chave(ident.get("instalacao"), ident.get("equipamento")),
        "severidade": severidade,
        "regiao": d.get("nome"),
        "t_max": d.get("t_max"),
        "detectada_em": detectada.isoformat(timespec="seconds"),
        "prazo": prazo.isoformat(),
        "prazo_padrao": not ac.get("prazo"),
        "dias": (prazo - hoje).days,
        "vencida": status in EM_ANDAMENTO and prazo < hoje,
        "status": status,
        "ordem_servico": ac.get("ordem_servico", ""),
        "responsavel": ac.get("responsavel", ""),
        "nota": ac.get("nota", ""),
        "historico": ac.get("historico", []),
        "reinspecao": reinspecao if status in PENDENTES else None,
    }


def listar(itens: list[dict], hoje: date | None = None) -> list[dict]:
    """Uma pendência por inspeção fora do normal; vencidas e mais graves primeiro."""
    por_equipamento: dict[str, list[dict]] = {}
    for it in itens:
        k = eq.chave((it.get("identificacao") or {}).get("instalacao"), (it.get("identificacao") or {}).get("equipamento"))
        por_equipamento.setdefault(k, []).append(it)
    saida = []
    for it in itens:
        if it["resumo"]["severidade"] == "normal":
            continue
        k = eq.chave((it.get("identificacao") or {}).get("instalacao"), (it.get("identificacao") or {}).get("equipamento"))
        reinspecao = None
        if k != eq.SEM_EQUIPAMENTO:
            depois = [o for o in por_equipamento[k] if eq._data(o) > eq._data(it) and o["resumo"]["severidade"] == "normal"]
            if depois:
                primeira = min(depois, key=eq._data)
                reinspecao = {"id": primeira["id"], "data": eq._data(primeira).isoformat(timespec="seconds")}
        saida.append(montar(it, reinspecao, hoje))
    ordem = {s: i for i, s in enumerate(STATUS)}
    return sorted(saida, key=lambda p: (not p["vencida"], ordem[p["status"]], -eq.ORDEM.index(p["severidade"]), p["prazo"]))


def atualizar(analise: dict, corpo: dict, agora: datetime | None = None) -> dict:
    """Troca status, prazo, OS, responsável ou nota e registra a mudança no histórico."""
    agora = agora or datetime.now()
    ac = dict(analise.get("acompanhamento") or {})
    status = corpo.get("status", ac.get("status", "aberta"))
    if status not in STATUS:
        raise ValueError("Situação desconhecida.")
    if "prazo" in corpo:
        if corpo["prazo"] in (None, ""):
            ac.pop("prazo", None)
        else:
            try:
                ac["prazo"] = date.fromisoformat(str(corpo["prazo"])[:10]).isoformat()
            except ValueError as erro:
                raise ValueError("Prazo inválido.") from erro
    for campo, limite in (("ordem_servico", 40), ("responsavel", 80), ("nota", 500)):
        if campo in corpo:
            ac[campo] = str(corpo[campo] or "").strip()[:limite]
    mudou = status != ac.get("status", "aberta") or bool(str(corpo.get("nota") or "").strip())
    ac["status"] = status
    if mudou:
        ac["historico"] = [*ac.get("historico", []), {"quando": agora.isoformat(timespec="seconds"), "status": status,
                                                       "nota": str(corpo.get("nota") or "").strip()[:500]}][-50:]
    analise["acompanhamento"] = ac
    return analise
