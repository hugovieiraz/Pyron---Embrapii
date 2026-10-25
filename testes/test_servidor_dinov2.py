"""Testes das rotas de classificação DINOv2 e Metodologia Completa no servidor FastAPI do Pyron."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import servidor
from app.armazenamento import Armazenamento
from nucleo.classificacao.dinov2_engine import DINOv2Classifier
from nucleo.segmentacao.sam2_engine import SAM2Segmentor
from testes.test_flir import _bruto_de, _jpeg_flir, _parametros


class PreditorMock:
    """Preditor SAM 2 simulado para testes rápidos com máscara válida."""

    def __init__(self):
        self.imagem = None

    def set_image(self, image: np.ndarray) -> None:
        self.imagem = image

    def predict(self, *, box, multimask_output):
        x1, y1, x2, y2 = (int(round(v)) for v in box)
        h, w = self.imagem.shape[:2]
        mascara = np.zeros((h, w), dtype=np.float32)
        mx1 = max(0, min(w, x1 + 2))
        my1 = max(0, min(h, y1 + 2))
        mx2 = max(mx1 + 2, min(w, x2 - 2))
        my2 = max(my1 + 2, min(h, y2 - 2))
        mascara[my1:my2, mx1:mx2] = 1.0
        return np.stack([mascara]), np.array([0.96], dtype=np.float32), None


class ClassificadorMock:
    """Classificador DINOv2 simulado com predição determinística."""

    def __init__(self, classe: str = "isolador", confianca: float = 0.88):
        self.classe = classe
        self.confianca = confianca

    def classificar(self, imagem_rgb: np.ndarray, bbox=None, mascara=None) -> dict:
        return {
            "classe": self.classe,
            "confianca": self.confianca,
            "nome": "Isolador",
            "scores": {
                self.classe: self.confianca,
                "bucha": 0.05,
                "para_raio": 0.05,
                "conexao": 0.02,
            },
        }


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    monkeypatch.setattr(servidor, "_segmentador_sam2", None)
    monkeypatch.setattr(servidor, "_classificador_dinov2", None)
    return TestClient(servidor.app)


def _criar_termograma() -> bytes:
    p = _parametros()
    t = np.full((120, 160), 22.0)
    t[30:70, 40:90] = 55.0
    return _jpeg_flir(_bruto_de(t, p), p, png=False)


def test_classificar_sem_modelo_instalado_retorna_503(cliente, monkeypatch):
    """Quando as dependências do DINOv2 falham, a API responde 503 com mensagem clara."""
    def _falha_construcao(*args, **kwargs):
        raise ImportError("Dependência 'dinov2' ausente")

    monkeypatch.setattr(servidor, "_classificador_dinov2", None)
    monkeypatch.setattr(DINOv2Classifier, "obter_instancia", _falha_construcao)

    r_post = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _criar_termograma(), "image/jpeg")})
    assert r_post.status_code == 200
    id_ = r_post.json()["id"]

    r = cliente.post(f"/api/analises/{id_}/classificar", json={"caixa": [40, 30, 90, 70]})
    assert r.status_code == 503
    assert "DINOv2 ausentes" in r.json()["erro"] or "dinov2" in r.json()["erro"].lower()


def test_classificar_regiao_existente(cliente, monkeypatch):
    """Classificação usando o regiao_id de uma região existente e ajuste automático de classe."""
    clf = ClassificadorMock(classe="isolador", confianca=0.85)
    monkeypatch.setattr(servidor, "_classificador_dinov2", clf)

    r_post = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _criar_termograma(), "image/jpeg")})
    assert r_post.status_code == 200
    id_ = r_post.json()["id"]

    # Adiciona região genérica
    r_put = cliente.put(
        f"/api/analises/{id_}",
        json={"regioes": [{"nome": "Ativo 1", "classe": "componente", "caixa": [40.0, 30.0, 90.0, 70.0], "origem": "manual"}]},
    )
    assert r_put.status_code == 200
    regiao_id = r_put.json()["regioes"][0]["id"]

    r_class = cliente.post(
        f"/api/analises/{id_}/classificar",
        json={"regiao_id": regiao_id},
    )
    assert r_class.status_code == 200, r_class.text
    resp = r_class.json()
    assert resp["ok"] is True
    assert "classificacao" in resp
    c_info = resp["classificacao"]
    assert c_info["classe"] == "isolador"
    assert c_info["confianca"] == pytest.approx(0.85, abs=1e-4)
    assert c_info["nome"] == "Isolador"

    # Como a confiança > 0.60, a classe da região deve ter sido ajustada para "isolador"
    r_get = cliente.get(f"/api/analises/{id_}")
    assert r_get.status_code == 200
    analise_atualizada = r_get.json()
    regiao_atualizada = next(r for r in analise_atualizada["regioes"] if r["id"] == regiao_id)
    assert regiao_atualizada["classe"] == "isolador"
    assert "classificacao_dinov2" in regiao_atualizada
    assert regiao_atualizada["classificacao_dinov2"]["classe"] == "isolador"


def test_classificar_caixa_avulsa_cria_nova_regiao(cliente, monkeypatch):
    """Classificação passando caixa avulsa sem regiao_id deve criar nova região na análise."""
    clf = ClassificadorMock(classe="bucha", confianca=0.72)
    monkeypatch.setattr(servidor, "_classificador_dinov2", clf)

    r_post = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _criar_termograma(), "image/jpeg")})
    assert r_post.status_code == 200
    id_ = r_post.json()["id"]
    qtd_inicial = len(r_post.json()["regioes"])

    caixa_nova = [42.0, 32.0, 88.0, 68.0]
    r_class = cliente.post(f"/api/analises/{id_}/classificar", json={"caixa": caixa_nova})
    assert r_class.status_code == 200, r_class.text
    resp = r_class.json()
    assert resp["ok"] is True
    assert resp["classificacao"]["classe"] == "bucha"

    r_get = cliente.get(f"/api/analises/{id_}")
    assert r_get.status_code == 200
    regioes = r_get.json()["regioes"]
    assert len(regioes) == qtd_inicial + 1
    criada = regioes[-1]
    assert criada["origem"] == "classificacao:dinov2"
    assert criada["classe"] == "bucha"
    assert "classificacao_dinov2" in criada


def test_classificar_validacoes(cliente, monkeypatch):
    """Testa validações de parâmetros para caixa e região."""
    clf = ClassificadorMock()
    monkeypatch.setattr(servidor, "_classificador_dinov2", clf)

    r_post = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _criar_termograma(), "image/jpeg")})
    id_ = r_post.json()["id"]

    # Região inexistente
    r_404 = cliente.post(f"/api/analises/{id_}/classificar", json={"regiao_id": "nao_existe"})
    assert r_404.status_code == 404

    # Caixa invertida
    r_inv = cliente.post(f"/api/analises/{id_}/classificar", json={"caixa": [90, 70, 40, 30]})
    assert r_inv.status_code == 422

    # Caixa sem valores suficientes
    r_incompleta = cliente.post(f"/api/analises/{id_}/classificar", json={"caixa": [10, 20]})
    assert r_incompleta.status_code == 422


def test_preservacao_classificacao_dinov2_em_atualizar(cliente, monkeypatch):
    """Garante que PUT /api/analises/{id_} preserva o campo classificacao_dinov2."""
    clf = ClassificadorMock(classe="para_raio", confianca=0.91)
    monkeypatch.setattr(servidor, "_classificador_dinov2", clf)

    r_post = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _criar_termograma(), "image/jpeg")})
    id_ = r_post.json()["id"]

    # Cria região e classifica
    r_class = cliente.post(f"/api/analises/{id_}/classificar", json={"caixa": [40.0, 30.0, 90.0, 70.0]})
    assert r_class.status_code == 200
    analise = r_class.json()["analise"]
    regiao = analise["regioes"][-1]
    regiao_id = regiao["id"]
    assert "classificacao_dinov2" in regiao

    # Atualiza análise com PUT mantendo a região
    r_put = cliente.put(
        f"/api/analises/{id_}",
        json={
            "regioes": [
                {
                    "id": regiao_id,
                    "nome": "Para-raio Fase B",
                    "classe": "para_raio",
                    "caixa": [40.0, 30.0, 90.0, 70.0],
                    "classificacao_dinov2": regiao["classificacao_dinov2"],
                }
            ]
        },
    )
    assert r_put.status_code == 200
    analise_atualizada = r_put.json()
    reg_atualizada = next(r for r in analise_atualizada["regioes"] if r["id"] == regiao_id)
    assert "classificacao_dinov2" in reg_atualizada
    assert reg_atualizada["classificacao_dinov2"]["classe"] == "para_raio"


def test_metodologia_completa(cliente, monkeypatch):
    """Executa a tríade metodológica do Pyron: SAM 2 + Metrologia + DINOv2."""
    seg = SAM2Segmentor(preditor=PreditorMock())
    clf = ClassificadorMock(classe="isolador", confianca=0.92)
    monkeypatch.setattr(servidor, "_segmentador_sam2", seg)
    monkeypatch.setattr(servidor, "_classificador_dinov2", clf)

    r_post = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _criar_termograma(), "image/jpeg")})
    assert r_post.status_code == 200
    id_ = r_post.json()["id"]

    caixa = [40.0, 30.0, 90.0, 70.0]
    r_metodologia = cliente.post(
        f"/api/analises/{id_}/metodologia_completa",
        json={"caixa": caixa, "metric_ratio": 0.5},
    )
    assert r_metodologia.status_code == 200, r_metodologia.text
    dados = r_metodologia.json()
    assert dados["ok"] is True
    assert "segmentacao" in dados
    assert "classificacao" in dados
    assert "analise" in dados

    seg_info = dados["segmentacao"]
    assert seg_info["score"] == pytest.approx(0.96, abs=0.01)
    assert "geometria" in seg_info
    assert seg_info["geometria"]["length_metric"] is not None
    assert "termica_isolada" in seg_info

    class_info = dados["classificacao"]
    assert class_info["classe"] == "isolador"
    assert class_info["confianca"] == pytest.approx(0.92, abs=1e-4)

    # Confere na análise persistida
    r_get = cliente.get(f"/api/analises/{id_}")
    regioes = r_get.json()["regioes"]
    reg = regioes[-1]
    assert "segmentacao" in reg
    assert "classificacao_dinov2" in reg
    assert reg["classe"] == "isolador"


def test_metodologia_completa_validacao_metric_ratio(cliente, monkeypatch):
    """Testa validação de metric_ratio negativo ou zero."""
    seg = SAM2Segmentor(preditor=PreditorMock())
    clf = ClassificadorMock()
    monkeypatch.setattr(servidor, "_segmentador_sam2", seg)
    monkeypatch.setattr(servidor, "_classificador_dinov2", clf)

    r_post = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _criar_termograma(), "image/jpeg")})
    id_ = r_post.json()["id"]

    r = cliente.post(
        f"/api/analises/{id_}/metodologia_completa",
        json={"caixa": [40, 30, 90, 70], "metric_ratio": -1.0},
    )
    assert r.status_code == 422
