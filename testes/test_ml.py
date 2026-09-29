"""Testes da preparação dos rótulos e da avaliação (não dependem do PyTorch)."""

from __future__ import annotations

import io
import json
import struct
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ml import avaliacao, dados
from nucleo.detectores import preparo
from testes.test_flir import _bruto_de, _jpeg_flir, _parametros


def _com_data(jpeg: bytes, quando: str) -> bytes:
    """Regrava o JPEG com a data EXIF, mantendo os segmentos FLIR."""
    img = Image.open(io.BytesIO(jpeg))
    exif = Image.Exif()
    exif[306] = quando
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    base = buf.getvalue()
    # recoloca os segmentos APP1 FLIR (a regravação pelo PIL os perde)
    i, segmentos = 2, b""
    while i + 4 <= len(jpeg) and jpeg[i] == 0xFF and jpeg[i + 1] != 0xDA:
        (tam,) = struct.unpack(">H", jpeg[i + 2 : i + 4])
        if jpeg[i + 1] == 0xE1 and jpeg[i + 4 : i + 9] == b"FLIR\x00":
            segmentos += jpeg[i : i + 2 + tam]
        i += 2 + tam
    return base[:2] + segmentos + base[2:]


@pytest.fixture()
def pasta_rotulada(tmp_path: Path) -> tuple[Path, Path]:
    p = _parametros()
    t = np.full((120, 160), 20.0)
    t[30:60, 40:50] = 35.0
    jpeg = _jpeg_flir(_bruto_de(t, p), p, png=False)
    imagens = tmp_path / "imagens"
    imagens.mkdir()
    horarios = ["2024:02:23 10:00:00", "2024:02:23 10:02:00", "2024:02:23 14:00:00", "2024:02:25 09:00:00"]
    coco = {"images": [], "annotations": [], "categories": [{"id": 1, "name": "Para-raio"}, {"id": 2, "name": "Terminal superior"}, {"id": 3, "name": "Não usada"}]}
    for k, quando in enumerate(horarios, start=1):
        nome = f"FLIR{1000 + k}.jpg"
        (imagens / nome).write_bytes(_com_data(jpeg, quando))
        # O CVAT trabalha na imagem exibida; aqui a imagem sintética tem 160×120, como a matriz.
        coco["images"].append({"id": k, "file_name": f"images/{nome}", "width": 160, "height": 120})
        coco["annotations"].append({"id": 10 * k, "image_id": k, "category_id": 1, "bbox": [40, 30, 10, 30]})
        coco["annotations"].append({"id": 10 * k + 1, "image_id": k, "category_id": 2, "bbox": [40, 30, 10, 5]})
    arq = tmp_path / "instances_default.json"
    arq.write_text(json.dumps(coco), encoding="utf-8")
    return arq, imagens


def test_nome_de_classe() -> None:
    assert dados.nome_classe("Para-raio") == "para_raio"
    assert dados.nome_classe("Terminal superior") == "terminal_superior"
    assert dados.nome_classe("Parte isoladora ") == "parte_isoladora"


def test_le_coco_e_leva_caixas_para_a_matriz(pasta_rotulada) -> None:
    arq, imagens = pasta_rotulada
    amostras, classes, nomes = dados.ler_coco(arq, imagens)
    assert classes == ["para_raio", "terminal_superior"]  # categoria sem rótulo fica de fora
    assert nomes["terminal_superior"] == "Terminal superior"
    assert len(amostras) == 4
    a = amostras[0]
    assert a.temperatura.shape == (120, 160)
    assert a.caixas[0].tolist() == pytest.approx([40, 30, 50, 60])
    assert a.data_hora == datetime(2024, 2, 23, 10, 0, 0)


def test_escala_da_imagem_exibida_para_a_matriz(pasta_rotulada, tmp_path) -> None:
    arq, imagens = pasta_rotulada
    coco = json.loads(arq.read_text(encoding="utf-8"))
    for img in coco["images"]:
        img["width"], img["height"] = 640, 480  # caixas desenhadas na imagem de 640×480
    for a in coco["annotations"]:
        a["bbox"] = [v * 4 for v in a["bbox"]]
    arq2 = tmp_path / "exibida.json"
    arq2.write_text(json.dumps(coco), encoding="utf-8")
    amostras, _, _ = dados.ler_coco(arq2, imagens)
    assert amostras[0].caixas[0].tolist() == pytest.approx([40, 30, 50, 60])


def test_sessoes_e_divisao_nao_misturam_sessao(pasta_rotulada) -> None:
    arq, imagens = pasta_rotulada
    amostras, _, _ = dados.ler_coco(arq, imagens)
    s = dados.sessoes(amostras)
    assert s[0] == s[1]  # 2 minutos de intervalo: mesma sessão
    assert len(set(s)) == 3
    treino, teste, info = dados.dividir(amostras)
    assert treino and teste
    assert info["sessoes"] == 3
    nomes_teste = {a.nome for a in teste}
    assert ("FLIR1001.jpg" in nomes_teste) == ("FLIR1002.jpg" in nomes_teste)


def test_iou_e_precisao_media() -> None:
    a = np.array([[0, 0, 10, 10]], dtype=float)
    b = np.array([[5, 0, 15, 10], [0, 0, 10, 10]], dtype=float)
    assert avaliacao.iou(a, b)[0].tolist() == pytest.approx([1 / 3, 1.0])
    assert avaliacao.precisao_media([True, True], [0.9, 0.8], 2) == pytest.approx(1.0)
    assert avaliacao.precisao_media([False, True], [0.9, 0.8], 1) == pytest.approx(0.5)
    assert avaliacao.precisao_media([], [], 3) == 0.0


def test_avaliacao_mede_erro_de_temperatura(pasta_rotulada) -> None:
    arq, imagens = pasta_rotulada
    amostras, classes, _ = dados.ler_coco(arq, imagens)
    perfeitas = [(a.caixas.copy(), np.ones(len(a.caixas)), a.classes.copy()) for a in amostras]
    r = avaliacao.avaliar(amostras, perfeitas, classes)
    assert r["mAP50"] == pytest.approx(1.0)
    assert r["erro_tmax_mediano_c"] == pytest.approx(0.0, abs=0.01)
    vazias = [(np.zeros((0, 4)), np.zeros(0), np.zeros(0, dtype=int)) for _ in amostras]
    assert avaliacao.avaliar(amostras, vazias, classes)["mAP50"] == 0.0


def test_preparo_igual_no_treino_e_no_uso() -> None:
    t = np.full((120, 160), 20.0)
    t[40:60, 40:60] = 40.0
    norm = preparo.para_rede(t, 640, 480)
    assert norm.shape == (480, 640)
    assert norm.min() >= 0 and norm.max() <= 1
    x = preparo.tensor_entrada(norm)
    assert x.shape == (1, 3, 480, 640)
