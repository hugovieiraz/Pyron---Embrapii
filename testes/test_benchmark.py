"""Contas do benchmark e da paridade entre provedores (0.9, F4), com detecções simuladas."""

from __future__ import annotations

import numpy as np
from PIL import Image

from nucleo.detectores import Deteccao
from nucleo.detectores import benchmark as b


def test_iou() -> None:
    assert b.iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert b.iou([0, 0, 10, 10], [10, 10, 20, 20]) == 0.0
    assert abs(b.iou([0, 0, 10, 10], [5, 0, 15, 10]) - 1 / 3) < 1e-9


def test_comparar_casa_pela_classe_e_confere_tmax_na_matriz() -> None:
    t = np.zeros((40, 40), np.float32)
    t[5:15, 5:15] = 50.0
    ref = [Deteccao("bucha", [5, 5, 15, 15], 0.90), Deteccao("conexao", [20, 20, 30, 30], 0.60)]
    igual = [Deteccao("conexao", [20.2, 20.1, 30.0, 30.0], 0.61), Deteccao("bucha", [5.1, 4.9, 15.0, 15.0], 0.895)]
    r = b.comparar(ref, igual, t)
    assert r["mesmas_classes"] and r["iou_min"] > 0.95 and r["dnota_max"] <= 0.011
    assert r["caixas_iguais"] == 2 and r["tmax_iguais"] == 2
    outra = [Deteccao("bucha", [5, 5, 15, 15], 0.90)]  # a placa perdeu uma detecção
    assert not b.comparar(ref, outra, t)["mesmas_classes"]


def test_paridade_passa_e_reprova() -> None:
    class Falso:
        def __init__(self, deteccoes):
            self.deteccoes = deteccoes

        def detectar(self, _t, _rgb):
            return self.deteccoes

    t = np.zeros((20, 20), np.float32)
    imagens = [("a", t, None), ("b", t, None)]
    ref = Falso([Deteccao("x", [0, 0, 10, 10], 0.8)])
    assert b.paridade(ref, Falso([Deteccao("x", [0, 0, 10, 10], 0.81)]), imagens)["resumo"]["passa"]
    assert not b.paridade(ref, Falso([Deteccao("x", [0, 0, 10, 10], 0.75)]), imagens)["resumo"]["passa"]  # nota fora
    assert not b.paridade(ref, Falso([Deteccao("x", [0, 0, 10, 9], 0.8)]), imagens)["resumo"]["passa"]  # IoU 0,90


def test_conjunto_le_matriz_e_imagem_e_pula_o_que_nao_abre(tmp_path) -> None:
    for sub in ("imagens", "matrizes"):
        (tmp_path / sub).mkdir()
    np.save(tmp_path / "matrizes" / "boa.npy", np.ones((8, 10), np.float32))
    Image.new("RGB", (10, 8), "red").save(tmp_path / "imagens" / "boa.jpg")
    np.save(tmp_path / "matrizes" / "vazia.npy", np.ones((8, 10), np.float32))
    (tmp_path / "imagens" / "vazia.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\0" * 100)
    imagens = b.conjunto([tmp_path])
    assert [n for n, _, _ in imagens] == [f"{tmp_path.name}/boa"]
    assert imagens[0][1].shape == (8, 10) and imagens[0][2].shape == (8, 10, 3)
    assert b.PULADAS == [f"{tmp_path.name}/vazia.jpg"]


def test_tmax_sem_temperatura_conta_como_igual() -> None:
    t = np.full((20, 20), np.nan, np.float32)  # imagem sem matriz de temperatura
    r = b.comparar([Deteccao("x", [2, 2, 8, 8], 0.5)], [Deteccao("x", [2, 2, 8, 8], 0.5)], t)
    assert r["caixas_iguais"] == 1 and r["tmax_iguais"] == 1
