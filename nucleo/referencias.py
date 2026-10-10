"""Biblioteca de componentes: quanto cada um aguenta e como ele esquenta.

A NBR 15866 manda avaliar uma anomalia contra (i) a máxima temperatura admissível (MTA) do
fabricante, (ii) um elemento semelhante adjacente, (iii) o histórico do usuário ou (iv) critério do
responsável técnico. Esta tabela dá a MTA padrão de cada classe quando não há dado do fabricante,
com a fonte de cada valor; o usuário pode trocar qualquer um (Configurações).

Tipos de aquecimento:
- ``resistivo``: conduz corrente; a elevação cresce com I² (conexões, terminais, cabos);
- ``dieletrico``: esquenta por corrente de fuga, não pela carga (para-raios, isoladores). Não tem
  MTA útil: a avaliação é contra as outras fases, com diferenças pequenas já relevantes;
- ``oleo``: temperatura do óleo do transformador (tanque, radiadores).
"""

from __future__ import annotations

COMPONENTES_PADRAO: dict[str, dict] = {
    "componente": {
        "nome": "Componente (genérico)", "aquecimento": "resistivo", "mta_c": 90.0,
        "fonte": "Sem dado do fabricante: 90 °C para componentes metálicos (prática brasileira).",
    },
    "ponto_quente": {
        "nome": "Ponto quente", "aquecimento": "resistivo", "mta_c": 90.0,
        "fonte": "Sem dado do fabricante: 90 °C para componentes metálicos (prática brasileira).",
    },
    "conexao": {
        "nome": "Conexão", "aquecimento": "resistivo", "mta_c": 90.0,
        "fonte": "90 °C (prática brasileira). IEC 62271-1: conexão aparafusada no ar 90 °C nua, 105 °C estanhada, 115 °C prateada (conferir na edição vigente).",
    },
    "terminal_superior": {
        "nome": "Terminal superior", "aquecimento": "resistivo", "mta_c": 90.0,
        "fonte": "90 °C (prática brasileira). IEC 62271-1: terminal nu 90 °C, revestido 105 °C (conferir na edição vigente).",
    },
    "terminal_inferior": {
        "nome": "Terminal inferior", "aquecimento": "resistivo", "mta_c": 90.0,
        "fonte": "90 °C (prática brasileira). IEC 62271-1: terminal nu 90 °C, revestido 105 °C (conferir na edição vigente).",
    },
    "bucha": {
        "nome": "Bucha (terminal)", "aquecimento": "resistivo", "mta_c": 95.0,
        "fonte": "IEC 60137: terminal com 55 K de elevação sobre 40 °C de ambiente.",
    },
    "cabo": {
        "nome": "Cabo isolado", "aquecimento": "resistivo", "mta_c": 70.0,
        "fonte": "NBR 5410: isolação de PVC 70 °C (XLPE/EPR 90 °C).",
    },
    "para_raio": {
        "nome": "Para-raio", "aquecimento": "dieletrico", "mta_c": None,
        "fonte": "Aquecimento por corrente de fuga: comparar as três fases (IEC 60099-5).",
    },
    "parte_isoladora": {
        "nome": "Parte isoladora", "aquecimento": "dieletrico", "mta_c": None,
        "fonte": "Aquecimento em isolador indica fuga ou trinca: comparar com os semelhantes.",
    },
    "isolador": {
        "nome": "Isolador", "aquecimento": "dieletrico", "mta_c": None,
        "fonte": "Aquecimento em isolador indica fuga ou trinca: comparar com os semelhantes.",
    },
    "tanque": {
        "nome": "Tanque (óleo no topo)", "aquecimento": "oleo", "mta_c": 100.0,
        "fonte": "NBR 5356-2 / IEC 60076-2: óleo no topo com 60 K sobre 40 °C.",
    },
    "radiador": {
        "nome": "Radiador", "aquecimento": "oleo", "mta_c": 100.0,
        "fonte": "NBR 5356-2 / IEC 60076-2: óleo no topo com 60 K sobre 40 °C.",
    },
}


# Nomes que aparecem nos rótulos do CVAT e nos modelos treinados, levados à classe da biblioteca.
# Sem isso, "para-raio inteiro" cairia na classe genérica (resistiva, 90 °C) em vez de dielétrica.
SINONIMOS: dict[str, str] = {
    "para_raio_inteiro": "para_raio",
    "para_raios": "para_raio",
    "pararaio": "para_raio",
    "pararaios": "para_raio",
    "surge_arrester": "para_raio",
    "corpo_do_para_raio": "para_raio",
    "isoladora": "parte_isoladora",
    "aletas_isoladoras": "parte_isoladora",
    "aletas": "parte_isoladora",
    "parte_isolante": "parte_isoladora",
    "corpo_isolante": "parte_isoladora",
    "terminal_de_linha": "terminal_superior",
    "terminal_de_terra": "terminal_inferior",
    "conector": "conexao",
    "conexoes": "conexao",
    "buchas": "bucha",
}


def classe_da_biblioteca(classe: str) -> str:
    """Classe canônica da biblioteca para um nome vindo de rótulo ou modelo."""
    return SINONIMOS.get(classe, classe)


def componentes(personalizados: dict | None = None) -> dict[str, dict]:
    """Biblioteca em uso: padrão com as trocas do usuário por cima."""
    saida = {k: dict(v) for k, v in COMPONENTES_PADRAO.items()}
    for classe, valores in (personalizados or {}).items():
        base = saida.get(classe, dict(COMPONENTES_PADRAO["componente"], nome=classe))
        base.update({k: v for k, v in valores.items() if k in ("nome", "aquecimento", "mta_c", "fonte")})
        saida[classe] = base
    return saida


def do_componente(classe: str, biblioteca: dict[str, dict]) -> dict:
    """Referência da classe (ou do seu sinônimo); classes desconhecidas usam a genérica (90 °C, resistiva)."""
    return biblioteca.get(classe) or biblioteca.get(classe_da_biblioteca(classe)) or biblioteca["componente"]
