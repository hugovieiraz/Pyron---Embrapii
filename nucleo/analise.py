"""Medição por região e classificação de severidade.

Segue a ABNT NBR 15866: cada anomalia é avaliada contra referências explícitas.

- **Absoluta:** a temperatura projetada para plena carga, T_amb + (T_medida − T_amb)·(100/carga)^n,
  comparada com a máxima temperatura admissível (MTA) do componente (``referencias.py``).
  Informa também quanto de carga cabe até a MTA: sqrt((MTA − T_amb) / (T_medida − T_amb)).
- **Relativa:** ΔT contra o componente semelhante (mesma classe, outras fases), corrigido pela
  carga nas partes resistivas. Para-raios e isoladores têm faixa própria, sem correção de carga.
- **Ar ambiente (opcional, NETA MTS):** ΔT sobre o ambiente.

A severidade final é a pior das avaliações aplicáveis e registra qual critério a disparou. A
comparação com o entorno imediato é mostrada, mas não classifica: não é critério de norma.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from nucleo import referencias

NIVEIS = {
    "normal": {"ordem": 0, "rotulo": "Normal", "acao": "Nenhuma ação."},
    "atencao": {"ordem": 1, "rotulo": "Atenção", "acao": "Corrigir na próxima manutenção periódica."},
    "programar": {"ordem": 2, "rotulo": "Programar reparo", "acao": "Agendar a correção e reinspecionar."},
    "urgente": {"ordem": 3, "rotulo": "Urgente", "acao": "Corrigir o mais rápido possível."},
    "imediato": {"ordem": 4, "rotulo": "Imediato", "acao": "Corrigir imediatamente."},
}

# Faixas brasileiras (NBR 15866 + Infraspection Institute, conforme prática de concessionárias).
CRITERIOS_PADRAO = {
    "nome": "Brasil: NBR 15866 (MTA e ΔT entre semelhantes)",
    # ΔT contra o semelhante em partes que conduzem corrente (°C; nível vale a partir do limite)
    "similares": [[5.0, "atencao"], [10.1, "programar"], [20.1, "urgente"], [40.1, "imediato"]],
    # ΔT contra o semelhante em para-raios e isoladores (°C)
    "dieletrico": [[2.0, "atencao"], [5.0, "programar"], [10.0, "urgente"]],
    # temperatura projetada em % da MTA
    "mta_faixas": [[60.1, "atencao"], [70.1, "programar"], [80.1, "urgente"], [100.1, "imediato"]],
    # ΔT sobre o ar ambiente (NETA MTS); desligado no modelo brasileiro
    "usar_ambiente": False,
    "ambiente": [[1.0, "atencao"], [11.0, "programar"], [21.0, "urgente"], [40.1, "imediato"]],
    "expoente_carga": 2.0,
    "carga_minima_pct": 40.0,
}

CRITERIOS_NETA = {
    "nome": "NETA MTS (ΔT entre semelhantes e sobre o ambiente)",
    "similares": [[1.0, "atencao"], [4.0, "programar"], [15.1, "imediato"]],
    "dieletrico": [[1.0, "atencao"], [4.0, "programar"], [15.1, "imediato"]],
    "mta_faixas": [[100.1, "imediato"]],
    "usar_ambiente": True,
    "ambiente": [[1.0, "atencao"], [11.0, "programar"], [21.0, "urgente"], [40.1, "imediato"]],
    "expoente_carga": 2.0,
    "carga_minima_pct": 40.0,
}

ROTULOS_CRITERIO = {"semelhantes": "ΔT entre semelhantes", "mta": "% da MTA", "ambiente": "ΔT sobre o ambiente"}


@dataclass
class Medida:
    t_max: float
    t_med: float
    t_min: float
    x_max: int
    y_max: int
    pixels: int


def medir(temperatura: np.ndarray, caixa: list[float]) -> Medida | None:
    """Estatísticas dentro da caixa (x0, y0, x1, y1), em pixels da matriz."""
    h, w = temperatura.shape
    x0, y0, x1, y1 = caixa
    xa, ya = max(0, int(np.floor(x0))), max(0, int(np.floor(y0)))
    xb, yb = min(w, int(np.ceil(x1))), min(h, int(np.ceil(y1)))
    if xb <= xa or yb <= ya:
        return None
    recorte = temperatura[ya:yb, xa:xb]
    ok = np.isfinite(recorte)
    if not ok.any():
        return None
    iy, ix = np.unravel_index(np.nanargmax(recorte), recorte.shape)
    return Medida(
        t_max=float(np.nanmax(recorte)),
        t_med=float(np.nanmean(recorte)),
        t_min=float(np.nanmin(recorte)),
        x_max=int(xa + ix),
        y_max=int(ya + iy),
        pixels=int(ok.sum()),
    )


def otsu(valores: np.ndarray, caixas: int = 256) -> float:
    """Limiar que melhor separa dois grupos de valores (fundo frio × objetos)."""
    hist, bordas = np.histogram(valores, bins=caixas)
    centros = (bordas[:-1] + bordas[1:]) / 2
    peso = np.cumsum(hist)
    peso_fim = peso[-1] - peso
    soma = np.cumsum(hist * centros)
    media_ini = soma / np.maximum(peso, 1)
    media_fim = (soma[-1] - soma) / np.maximum(peso_fim, 1)
    variancia = peso * peso_fim * (media_ini - media_fim) ** 2
    return float(centros[int(np.argmax(variancia[:-1]))])


def mascara_objetos(temperatura: np.ndarray) -> np.ndarray:
    """Pixels de equipamento, separados do fundo frio (céu) pelo limiar de Otsu."""
    ok = np.isfinite(temperatura)
    if ok.sum() < 50:
        return ok
    return ok & (np.nan_to_num(temperatura, nan=-1e9) > otsu(temperatura[ok]))


def temperatura_entorno(
    temperatura: np.ndarray, caixa: list[float], largura: int = 4, outras=(), objetos: np.ndarray | None = None
) -> float | None:
    """Mediana de um anel em volta da caixa (só pixels de equipamento, nunca o céu)."""
    h, w = temperatura.shape
    x0, y0, x1, y1 = (int(round(v)) for v in caixa)
    anel = np.zeros((h, w), dtype=bool)
    anel[max(0, y0 - largura) : min(h, y1 + largura), max(0, x0 - largura) : min(w, x1 + largura)] = True
    anel[max(0, y0) : min(h, y1), max(0, x0) : min(w, x1)] = False
    for c in outras:
        a0, b0, a1, b1 = (int(round(v)) for v in c)
        anel[max(0, b0) : min(h, b1), max(0, a0) : min(w, a1)] = False
    base = np.isfinite(temperatura) if objetos is None else objetos
    valores = temperatura[anel & base]
    if valores.size >= 5:
        return float(np.median(valores))
    todos = temperatura[base]
    return float(np.median(todos)) if todos.size >= 5 else None


def nivel_por_limites(valor: float | None, limites: list) -> str:
    nivel = "normal"
    if valor is None:
        return nivel
    for limite, nome in limites:
        if valor >= limite:
            nivel = nome
    return nivel


def pior(niveis) -> str:
    niveis = list(niveis) or ["normal"]
    return max(niveis, key=lambda n: NIVEIS[n]["ordem"])


def _mensagem(sev: str, criticos: list[dict]) -> str:
    """Resumo em uma frase: onde, por qual critério e o que fazer. Com muitas regiões, só a pior."""

    def nome(i: dict) -> str:
        return i.get("nome") or i.get("classe") or "região"

    def quanto(i: dict) -> str:
        if i["niveis"].get("mta") == sev and i.get("pct_mta") is not None:
            return f"{i['pct_mta']:.0f}% da MTA"
        if i["niveis"].get("semelhantes") == sev and i.get("dt_corrigido") is not None:
            return f"ΔT {i['dt_corrigido']:.1f} °C entre fases".replace(".", ",")
        return ""

    n = NIVEIS[sev]
    motivo = " e ".join(sorted({c for i in criticos for c in (i["criterio_disparo"] or [])}))
    if len(criticos) <= 2:
        onde = " e ".join(f"{nome(i)} ({quanto(i)})" if quanto(i) else nome(i) for i in criticos)
        return f"{n['rotulo']} em {onde}, por {motivo}. {n['acao']}"
    piores = max(criticos, key=lambda i: (i.get("pct_mta") or 0.0, i.get("dt_corrigido") or 0.0))
    detalhe = f" ({quanto(piores)})" if quanto(piores) else ""
    return f"{len(criticos)} regiões em nível {n['rotulo'].lower()}, por {motivo}. A mais crítica é {nome(piores)}{detalhe}. {n['acao']}"


def _referencia_semelhantes(itens: list[dict]) -> float:
    maximos = sorted(i["medida"]["t_max"] for i in itens)
    return float(np.median(maximos)) if len(maximos) >= 3 else maximos[0]


def analisar_regioes(
    temperatura: np.ndarray,
    regioes: list[dict],
    ambiente_c: float | None = None,
    carga_pct: float | None = None,
    criterios: dict | None = None,
    componentes: dict | None = None,
) -> tuple[list[dict], dict]:
    """Mede cada região, avalia contra as referências e classifica.

    Cada região é um dicionário com ao menos ``caixa`` e ``classe``.
    """
    crit = {**CRITERIOS_PADRAO, **(criterios or {})}
    biblioteca = componentes or referencias.componentes()
    avisos: list[str] = []
    carga_conhecida = carga_pct is not None and carga_pct > 0
    fator_carga = (100.0 / carga_pct) ** crit["expoente_carga"] if carga_conhecida and carga_pct < 100 else 1.0
    if carga_conhecida and carga_pct < crit["carga_minima_pct"]:
        avisos.append(
            f"Carga de {carga_pct:.0f}% abaixo de {crit['carga_minima_pct']:.0f}%: a projeção para plena carga é pouco confiável."
        )

    saida = []
    caixas = [r["caixa"] for r in regioes]
    objetos = mascara_objetos(temperatura)
    for i, r in enumerate(regioes):
        m = medir(temperatura, r["caixa"])
        item = dict(r)
        ref = referencias.do_componente(item.get("classe", "componente"), biblioteca)
        item["referencia"] = {"nome": ref["nome"], "aquecimento": ref["aquecimento"], "mta_c": ref["mta_c"], "fonte": ref["fonte"]}
        item["medida"] = asdict(m) if m else None
        outras = [c for j, c in enumerate(caixas) if j != i]
        item["entorno_c"] = temperatura_entorno(temperatura, r["caixa"], outras=outras, objetos=objetos) if m else None
        saida.append(item)

    grupos: dict[str, list[dict]] = {}
    for item in saida:
        if item["medida"] and item.get("classe") not in (None, "", "ponto_quente", "componente"):
            grupos.setdefault(item["classe"], []).append(item)

    for item in saida:
        m = item["medida"]
        ref = item["referencia"]
        dieletrico = ref["aquecimento"] == "dieletrico"
        item.update(
            dt_ref=None, ref_tipo=None, dt_corrigido=None, dt_ambiente=None, dt_entorno=None,
            t_projetada=None, pct_mta=None, margem_mta_c=None, carga_limite=None, avaliacao_absoluta=None,
            niveis={}, criterio_disparo=None,
        )
        if not m:
            item["severidade"] = "normal"
            continue
        if item["entorno_c"] is not None:
            item["dt_entorno"] = m["t_max"] - item["entorno_c"]

        # Relativa: contra o semelhante
        grupo = grupos.get(item.get("classe"), [])
        if len(grupo) >= 2:
            item["dt_ref"], item["ref_tipo"] = m["t_max"] - _referencia_semelhantes(grupo), "semelhantes"
            item["dt_corrigido"] = max(item["dt_ref"], 0.0) * (1.0 if dieletrico else fator_carga)
            faixas = crit["dieletrico"] if dieletrico else crit["similares"]
            item["niveis"]["semelhantes"] = nivel_por_limites(item["dt_corrigido"], faixas)
        elif item["dt_entorno"] is not None:
            item["ref_tipo"] = "entorno"

        # Absoluta: contra a MTA
        mta = ref["mta_c"]
        if mta and not dieletrico:
            if ambiente_c is not None:
                elevacao = max(m["t_max"] - ambiente_c, 0.0)
                item["t_projetada"] = ambiente_c + elevacao * fator_carga
                item["avaliacao_absoluta"] = "completa" if carga_conhecida else "sem_carga"
                if elevacao > 0.5 and mta > ambiente_c:
                    fator_corrente = math.sqrt((mta - ambiente_c) / elevacao)
                    item["carga_limite"] = {
                        "vezes_corrente_atual": round(fator_corrente, 2),
                        "pct_nominal": round(fator_corrente * carga_pct, 0) if carga_conhecida else None,
                    }
            else:
                item["t_projetada"] = m["t_max"]
                item["avaliacao_absoluta"] = "sem_ambiente"
            item["pct_mta"] = 100.0 * item["t_projetada"] / mta
            item["margem_mta_c"] = mta - item["t_projetada"]
            item["niveis"]["mta"] = nivel_por_limites(item["pct_mta"], crit["mta_faixas"])

        # Ar ambiente (NETA), se ligado
        if ambiente_c is not None:
            item["dt_ambiente"] = m["t_max"] - ambiente_c
            if crit.get("usar_ambiente"):
                item["niveis"]["ambiente"] = nivel_por_limites(item["dt_ambiente"], crit["ambiente"])

        item["severidade"] = pior(item["niveis"].values())
        if item["severidade"] != "normal":
            item["criterio_disparo"] = [ROTULOS_CRITERIO[k] for k, v in item["niveis"].items() if v == item["severidade"]]

    for item in saida:
        n = NIVEIS[item["severidade"]]
        item["severidade_rotulo"], item["acao"] = n["rotulo"], n["acao"]
        # Indicativa: sem semelhante para comparar e sem projeção para plena carga.
        item["indicativa"] = "semelhantes" not in item.get("niveis", {}) and item.get("avaliacao_absoluta") in (None, "sem_ambiente")

    validos = temperatura[np.isfinite(temperatura)]
    sev = pior(i["severidade"] for i in saida)
    criticos = [i for i in saida if i["severidade"] == sev and sev != "normal"]
    if sev == "normal":
        mensagem = "Nenhuma região acima dos limites do critério."
    else:
        mensagem = _mensagem(sev, criticos)
    if saida and ambiente_c is None and any(i["referencia"]["mta_c"] and i["referencia"]["aquecimento"] != "dieletrico" for i in saida):
        avisos.append(
            "Sem temperatura ambiente, a comparação com a MTA usa a temperatura medida, sem projeção para plena carga. "
            "Informe ambiente e carga na aba Condições."
        )
    elif saida and not carga_conhecida and ambiente_c is not None:
        avisos.append("Sem a carga do momento, a projeção considera que a medição foi feita em plena carga.")
    if any(i["indicativa"] for i in saida):
        avisos.append(
            "Regiões sem componente semelhante e sem projeção têm classificação indicativa. "
            "Dê a mesma classe às regiões das três fases para comparar semelhantes."
        )
    pcts = [i["pct_mta"] for i in saida if i.get("pct_mta") is not None]
    resumo = {
        "severidade": sev,
        "severidade_rotulo": NIVEIS[sev]["rotulo"],
        "mensagem": mensagem,
        "regioes": len(saida),
        "t_max_cena": float(validos.max()) if validos.size else None,
        "t_min_cena": float(validos.min()) if validos.size else None,
        "maior_pct_mta": max(pcts) if pcts else None,
        "fator_carga": fator_carga,
        "avisos": avisos,
        "criterio": crit["nome"],
    }
    return saida, resumo
