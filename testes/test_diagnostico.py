"""Diagnóstico honesto: peça sem com quem comparar não é "normal", e calor fora das peças pede conferência."""

from __future__ import annotations

import numpy as np

from nucleo import analise


def _para_raios(n: int) -> tuple[np.ndarray, list[dict]]:
    """``n`` para-raios lado a lado num céu frio; o primeiro 3 °C mais quente que os outros."""
    t = np.full((120, 160), -10.0)
    regioes = []
    for fase, x0 in enumerate((20, 70, 120)[:n], start=1):
        t[15:105, x0:x0 + 20] = 28.0 if fase == 1 else 25.0
        regioes.append({"id": f"pr{fase}", "nome": f"Para-raio {fase}", "classe": "para_raio", "caixa": [x0, 15, x0 + 20, 105]})
    return t, regioes


def test_para_raio_sozinho_nao_e_avaliado() -> None:
    t, regioes = _para_raios(1)
    itens, resumo = analise.analisar_regioes(t, regioes)
    assert itens[0]["severidade"] == "nao_avaliado" and itens[0]["indicativa"] is False
    assert resumo["severidade"] == "nao_avaliado" and resumo["nao_avaliadas"] == 1
    assert "falta a peça igual" in resumo["mensagem"]
    assert any("Para-raio 1" in a and "três" in a for a in resumo["avisos"])


def test_tres_para_raios_sao_comparados() -> None:
    t, regioes = _para_raios(3)
    itens, resumo = analise.analisar_regioes(t, regioes)
    sev = {i["id"]: i["severidade"] for i in itens}
    assert sev["pr1"] == "atencao"  # 3 °C acima dos irmãos: dielétrico, atenção a partir de 2 °C
    assert sev["pr2"] == sev["pr3"] == "normal"
    assert resumo["severidade"] == "atencao" and "nao_avaliadas" not in resumo


def _com_ponto_fora(dentro: bool) -> tuple[np.ndarray, list[dict]]:
    """Três para-raios normais e um ponto muito quente, dentro do primeiro ou longe deles (uma lâmpada)."""
    t, regioes = _para_raios(3)
    t[:, :] = np.where(t > 0, 25.0, t)  # os três iguais: nada de anormal nas peças
    y, x = (40, 28) if dentro else (60, 100)
    t[y:y + 3, x:x + 3] = 85.0
    regioes.append({"id": "pq1", "nome": "Ponto quente 1", "classe": "ponto_quente", "caixa": [x - 2, y - 2, x + 5, y + 5]})
    return t, regioes


def test_calor_fora_das_pecas_pede_conferencia_sem_sumir_da_classificacao() -> None:
    itens, resumo = analise.analisar_regioes(*_com_ponto_fora(dentro=False))
    pq = next(i for i in itens if i["id"] == "pq1")
    assert pq["componente"] is None and pq["severidade"] not in analise.SEM_CLASSIFICACAO
    assert resumo["severidade"] == pq["severidade"]  # não some: pode ser defeito em outro equipamento
    assert resumo["conferir"] is True
    assert resumo["avisos"][0].startswith("Confira antes de agir")


def test_calor_dentro_da_peca_nao_pede_conferencia() -> None:
    itens, resumo = analise.analisar_regioes(*_com_ponto_fora(dentro=True))
    assert next(i for i in itens if i["id"] == "pq1")["componente"]["id"] == "pr1"
    assert "conferir" not in resumo
