"""Métricas e modelo trivial da comparação de detectores (sem PyTorch)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from ml import comparacao, dados


def _amostra(nome: str, caixas, classes, quando: datetime, subconjunto: str | None = None, forma=(120, 160)) -> dados.Amostra:
    a = dados.Amostra(arquivo=Path(nome), caixas=np.asarray(caixas, dtype=np.float32), classes=np.asarray(classes, dtype=np.int64),
                      data_hora=quando, subconjunto=subconjunto)
    t = np.full(forma, 20.0, dtype=np.float32)
    for c in a.caixas:
        t[int(c[1]):int(c[3]), int(c[0]):int(c[2])] = 30.0
    a._temperatura = t
    return a


@pytest.fixture()
def conjunto():
    t0 = datetime(2024, 2, 23, 10, 0)
    return [
        _amostra(f"F{i}.jpg", [[40 + i, 20, 60 + i, 90], [45 + i, 15, 55 + i, 20]], [0, 1], t0 + timedelta(minutes=i), "teste" if i >= 8 else "treino")
        for i in range(10)
    ]


def test_previsao_perfeita_da_nota_maxima(conjunto) -> None:
    perfeitas = [(a.caixas.copy(), np.ones(len(a.caixas)), a.classes.copy()) for a in conjunto]
    r = comparacao.avaliar(conjunto, perfeitas, ["para_raio", "terminal_superior"], {"para_raio": "Para-raio"})
    assert r["mAP50"] == 1.0 and r["mAP50-95"] == 1.0
    assert r["precisao"] == r["revocacao"] == r["F1"] == 1.0
    assert r["acertos"] == 20 and r["falsos"] == 0 and r["perdidos"] == 0
    assert r["por_classe"]["Para-raio"]["AP50"] == 1.0
    assert r["erro_Tmax_mediano_C"] == pytest.approx(0.0, abs=0.01)


def test_casar_separa_acerto_falso_e_perdido() -> None:
    gt = np.array([[0, 0, 10, 10], [50, 50, 60, 60]], dtype=float)
    gt_k = np.array([0, 1])
    prev = np.array([[0, 0, 10, 10], [80, 80, 90, 90], [50, 50, 60, 60]], dtype=float)
    pont = np.array([0.9, 0.8, 0.3])  # a terceira fica abaixo do limiar
    prev_k = np.array([0, 0, 1])
    acertos, falsos, perdidos = comparacao.casar(gt, gt_k, prev, pont, prev_k, limiar=0.5)
    assert [(i, j) for i, j, _ in acertos] == [(0, 0)]
    assert falsos == [1] and perdidos == [1]


def test_caixa_um_pouco_torta_passa_no_ap50_e_perde_no_ap50_95(conjunto) -> None:
    tortas = [(a.caixas + [2, 2, 2, 2], np.ones(len(a.caixas)), a.classes.copy()) for a in conjunto]
    r = comparacao.avaliar(conjunto, tortas, ["a", "b"], {})
    assert r["mAP50"] > r["mAP50-95"]


def test_modelo_trivial_preve_a_caixa_media(conjunto) -> None:
    treino, validacao, teste = comparacao.dividir(conjunto, modo="cvat", frac_validacao=0.25)
    assert [a.nome for a in teste] == ["F8.jpg", "F9.jpg"]
    assert len(validacao) == 2 and validacao[-1].nome == "F7.jpg"  # bloco final no tempo
    trivial = comparacao.ModeloTrivial().ajustar(treino)
    caixas, pont, classes = trivial.prever(teste[:1])[0]
    assert classes.tolist() == [0, 1]
    esperado = np.mean([a.caixas[0] for a in treino], axis=0)
    assert caixas[0] == pytest.approx(esperado, abs=1e-4)
    # vale para foto em pé: a caixa média é relativa ao tamanho da imagem
    em_pe = _amostra("P.jpg", [[10, 10, 20, 40]], [0], datetime(2024, 1, 1), forma=(160, 120))
    c_pe, _, _ = trivial.prever([em_pe])[0]
    assert c_pe[0][2] <= 120 and c_pe[0][3] <= 160
