"""Modelo do Colab no Pyron: detector RF-DETR (ONNX) e a aba de avaliação dos modelos.

O onnxruntime é trocado por uma sessão falsa que devolve saídas no formato da exportação oficial do
RF-DETR (``dets`` e ``labels``): assim o teste confere a leitura das caixas sem precisar do PyTorch.
"""

from __future__ import annotations

import io
import json
import types
import zipfile

import numpy as np
import pytest

from nucleo.detectores.onnx_modelo import DetectorONNX
from testes.test_servidor import _termograma_flir

CLASSES = ["para_raio", "aletas_isoladoras", "terminal_superior", "terminal_inferior"]


def _cartao(id_: str = "para-raios-rfdetr-teste") -> dict:
    return {
        "id": id_,
        "nome": "Para-raios (RF-DETR Medium)",
        "arquitetura": "RF-DETR Medium (DETR com base DINOv2)",
        "classes": CLASSES,
        "nomes": {"para_raio": "Para-raio", "aletas_isoladoras": "Aletas isoladoras"},
        "arquivo": "modelo.onnx",
        "entrada": {"fonte": "imagem_exibida", "largura": 64, "altura": 64,
                    "media": [0.485, 0.456, 0.406], "desvio": [0.229, 0.224, 0.225]},
        "saida": {"formato": "rfdetr", "fundo_ultima_coluna": True, "deslocamento_classe": 0},
        "limiar_confianca": 0.5,
    }


def _saidas_rfdetr() -> tuple[np.ndarray, np.ndarray]:
    """3 consultas: aletas no centro (confiante), fundo (ignorada) e terminal fraco (abaixo do limiar)."""
    dets = np.array([[[0.5, 0.5, 0.2, 0.4], [0.1, 0.1, 0.1, 0.1], [0.8, 0.2, 0.1, 0.1]]], dtype=np.float32)
    notas = np.full((1, 3, len(CLASSES) + 1), -8.0, dtype=np.float32)
    notas[0, 0, 1] = 4.0     # aletas_isoladoras, sigmoide ≈ 0,98
    notas[0, 1, -1] = 6.0    # só a coluna de fundo: não é peça
    notas[0, 2, 2] = -1.0    # terminal_superior, sigmoide ≈ 0,27 (abaixo do limiar 0,5)
    return dets, notas


class SessaoFalsa:
    def __init__(self):
        self.dets, self.notas = _saidas_rfdetr()
        self.entrada = None

    def get_inputs(self):
        return [types.SimpleNamespace(name="input", shape=[1, 3, 64, 64])]

    def get_outputs(self):
        return [types.SimpleNamespace(name="labels"), types.SimpleNamespace(name="dets")]  # fora de ordem de propósito

    def run(self, _nomes, entradas):
        (self.entrada,) = entradas.values()
        return [self.notas, self.dets]


@pytest.fixture()
def sessao_falsa(monkeypatch):
    sessao = SessaoFalsa()
    monkeypatch.setattr(DetectorONNX, "_sessao_onnx", lambda self: sessao)
    return sessao


def _pasta_modelo(tmp_path, cartao=None):
    pasta = tmp_path / "modelo"
    pasta.mkdir()
    (pasta / "cartao.json").write_text(json.dumps(cartao or _cartao()), encoding="utf-8")
    (pasta / "modelo.onnx").write_bytes(b"onnx falso")
    return pasta


def test_rfdetr_le_caixas_da_imagem_colorida(tmp_path, sessao_falsa) -> None:
    det = DetectorONNX(_pasta_modelo(tmp_path))
    assert det.precisa_imagem
    temperatura = np.zeros((120, 160), dtype=np.float32)
    imagem = np.full((480, 640, 3), 128, dtype=np.uint8)

    achados = det.detectar(temperatura, imagem)

    assert sessao_falsa.entrada.shape == (1, 3, 64, 64)
    assert sessao_falsa.entrada[0, 0, 0, 0] == pytest.approx((128 / 255 - 0.485) / 0.229, abs=1e-4)
    assert [d.classe for d in achados] == ["aletas_isoladoras"]
    # centro (0,5; 0,5), 0,2 × 0,4 da imagem -> pixels da matriz 160 × 120
    assert achados[0].caixa == pytest.approx([64, 36, 96, 84], abs=1e-3)
    assert achados[0].confianca > 0.95


def test_rfdetr_sem_imagem_explica_o_motivo(tmp_path, sessao_falsa) -> None:
    det = DetectorONNX(_pasta_modelo(tmp_path))
    with pytest.raises(ValueError, match="imagem colorida"):
        det.detectar(np.zeros((120, 160), dtype=np.float32))


def test_deslocamento_de_classe(tmp_path, sessao_falsa) -> None:
    cartao = _cartao()
    cartao["saida"]["deslocamento_classe"] = -1  # colunas numeradas de 1 a K
    det = DetectorONNX(_pasta_modelo(tmp_path, cartao))
    achados = det.detectar(np.zeros((120, 160)), np.zeros((480, 640, 3), dtype=np.uint8))
    assert [d.classe for d in achados] == ["para_raio"]


def test_formato_desconhecido_vira_erro_legivel(tmp_path) -> None:
    cartao = _cartao()
    cartao["saida"]["formato"] = "yolo-antigo"
    with pytest.raises(ValueError, match="saida.formato"):
        DetectorONNX(_pasta_modelo(tmp_path, cartao))


# ---------------------------------------------------------------- aba de avaliação


def _resumo() -> dict:
    return {
        "configuracao": {"epocas_rfdetr": 100},
        "classes": ["Para-raio", "Aletas Isoladoras", "Terminal Superior", "Terminal Inferior"],
        "fotos": {"treino": ["a.jpg"] * 111, "validacao": ["b.jpg"] * 25, "teste": ["c.jpg"] * 27},
        "teste": {
            "Faster R-CNN": {"mAP50": 0.893, "mAP50-95": 0.506, "precisao": 0.911, "revocacao": 0.864, "F1": 0.887,
                             "acertos": 153, "falsos": 15, "perdidos": 24, "por_classe": {"Para-raio": {"AP50": 0.99}}},
            "RF-DETR Medium": {"mAP50": 0.911, "mAP50-95": 0.549, "precisao": 0.895, "revocacao": 0.915, "F1": 0.905,
                               "acertos": 162, "falsos": 19, "perdidos": 15, "por_classe": {"Para-raio": {"AP50": 0.99}}},
        },
        "limiares": {"Faster R-CNN": 0.6, "RF-DETR Medium": 0.55},
        "ms_por_foto": {"Faster R-CNN": 25.0, "RF-DETR Medium": 53.1},
        "historico": {"Faster R-CNN": {"perda_treino": [1.0, 0.5], "perda_validacao": [1.1, 0.7],
                                       "epocas_map": [2], "map50_validacao": [0.8], "melhor_epoca": 2}},
        "gpu": "Tesla T4",
    }


def _zip(arquivos: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, conteudo in arquivos.items():
            z.writestr(nome, conteudo)
    return buf.getvalue()


def _resultados() -> dict[str, bytes]:
    return {
        "resumo.json": json.dumps(_resumo()).encode(),
        "curvas.png": b"\x89PNG falso",
        "efeito_do_limiar.csv": "limiar,acertos,caixas falsas\n0.3,160,25\n0.5,153,15\n".encode(),
        "recuperar/annotations/instances_Train.json": b"{}",
    }


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    return TestClient(servidor.app)


def test_importa_resultados_do_colab(cliente) -> None:
    r = cliente.post("/api/avaliacoes", files={"arquivo": ("resultados_comparacao.zip", _zip(_resultados()), "application/zip")})
    assert r.status_code == 200, r.text
    id_ = r.json()["avaliacao"]
    assert r.json()["modelo"] is None

    lista = cliente.get("/api/avaliacoes").json()
    assert [a["id"] for a in lista] == [id_]
    assert lista[0]["melhor"] == "RF-DETR Medium" and lista[0]["fotos"]["teste"] == 27

    d = cliente.get(f"/api/avaliacoes/{id_}").json()
    assert d["resumo"]["teste"]["Faster R-CNN"]["perdidos"] == 24
    assert d["meta"]["figuras"] == ["curvas.png"]
    assert d["tabelas"]["efeito_do_limiar.csv"]["linhas"][0] == [0.3, 160, 25]
    assert cliente.get(f"/api/avaliacoes/{id_}/arquivos/curvas.png").content == b"\x89PNG falso"
    assert cliente.get(f"/api/avaliacoes/{id_}/arquivos/..%2Fmeta.json").status_code == 404

    assert cliente.delete(f"/api/avaliacoes/{id_}").status_code == 200
    assert cliente.get("/api/avaliacoes").json() == []


def test_zip_sem_resultados_nem_modelo(cliente) -> None:
    r = cliente.post("/api/avaliacoes", files={"arquivo": ("x.zip", _zip({"leia.txt": b"oi"}), "application/zip")})
    assert r.status_code == 422 and "resumo.json" in r.json()["erro"]


def test_pacote_do_colab_instala_o_modelo_e_ele_analisa(cliente, sessao_falsa) -> None:
    """O pacote exportado pelo caderno traz o modelo e os resultados; a análise usa a imagem colorida."""
    cartao = _cartao()
    pacote = {f"{cartao['id']}/cartao.json": json.dumps(cartao).encode(), f"{cartao['id']}/modelo.onnx": b"onnx falso"}
    pacote.update({f"resultados/{k}": v for k, v in _resultados().items()})
    r = cliente.post("/api/avaliacoes", files={"arquivo": ("pyron_modelo.zip", _zip(pacote), "application/zip")})
    assert r.status_code == 200, r.text
    assert r.json()["modelo"] == cartao["id"]
    d = cliente.get(f"/api/avaliacoes/{r.json()['avaliacao']}").json()
    assert d["modelo_disponivel"] is True

    assert cliente.put("/api/modelos/ativo", json={"id": cartao["id"]}).status_code == 200
    a = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _termograma_flir(), "image/jpeg")}).json()
    assert a["modelo"]["id"] == cartao["id"]
    assert [x["classe"] for x in a["regioes"]] == ["aletas_isoladoras"]
    assert a["regioes"][0]["caixa"] == pytest.approx([64, 36, 96, 84], abs=0.01)
    assert sessao_falsa.entrada.shape == (1, 3, 64, 64)  # veio da imagem colorida, não da matriz

    r = cliente.post(f"/api/analises/{a['id']}/detectar", json={})  # redetecção reabre o JPEG original
    assert r.status_code == 200, r.text
    assert [x["classe"] for x in r.json()["regioes"]] == ["aletas_isoladoras"]

    # instalar o mesmo pacote de novo: a avaliação entra, o modelo repetido vira aviso
    r = cliente.post("/api/avaliacoes", files={"arquivo": ("pyron_modelo.zip", _zip(pacote), "application/zip")})
    assert r.status_code == 200 and r.json()["modelo"] is None and r.json()["avisos"]
