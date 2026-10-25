"""Testes da rota de segmentação SAM 2 no servidor FastAPI do Pyron."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import servidor
from app.armazenamento import Armazenamento
from nucleo.segmentacao.sam2_engine import SAM2Segmentor
from testes.test_flir import _bruto_de, _jpeg_flir, _parametros


class PreditorMock:
    """Preditor simulado para testes unitários com máscara válida."""

    def __init__(self):
        self.imagem = None
        self.chamadas: list[dict] = []

    def set_image(self, image: np.ndarray) -> None:
        assert image.ndim == 3 and image.shape[2] == 3
        self.imagem = image

    def predict(self, *, box, multimask_output):
        self.chamadas.append({"box": np.asarray(box).tolist(), "multimask": multimask_output})
        x1, y1, x2, y2 = (int(round(v)) for v in box)
        h, w = self.imagem.shape[:2]
        mascara = np.zeros((h, w), dtype=np.float32)
        # Cria uma máscara retangular preenchida dentro da caixa
        mx1 = max(0, min(w, x1 + 2))
        my1 = max(0, min(h, y1 + 2))
        mx2 = max(mx1 + 2, min(w, x2 - 2))
        my2 = max(my1 + 2, min(h, y2 - 2))
        mascara[my1:my2, mx1:mx2] = 1.0
        return np.stack([mascara]), np.array([0.95], dtype=np.float32), None


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    monkeypatch.setattr(servidor, "_segmentador_sam2", None)
    return TestClient(servidor.app)


def _criar_termograma() -> bytes:
    p = _parametros()
    t = np.full((120, 160), 20.0)
    t[30:70, 40:90] = 48.0
    return _jpeg_flir(_bruto_de(t, p), p, png=False)


def _termograma_com_ponto_quente() -> bytes:
    p = _parametros()
    t = np.full((120, 160), -15.0)
    t[40:110, 30:130] = 30.0
    t[60:64, 78:82] = 45.0
    return _jpeg_flir(_bruto_de(t, p), p, png=False)


def test_segmentar_sem_modelo_instalado_retorna_503(cliente, monkeypatch):
    """Quando o pacote SAM 2 não está disponível, a API responde 503 com mensagem clara."""
    def _falha_construcao(*args, **kwargs):
        raise ImportError("pacote 'sam2' ausente; instale com: pip install -e .[segmentacao]")

    monkeypatch.setattr(servidor, "_segmentador_sam2", None)
    monkeypatch.setattr(SAM2Segmentor, "_construir", _falha_construcao)

    r_post = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _criar_termograma(), "image/jpeg")})
    assert r_post.status_code == 200
    id_ = r_post.json()["id"]

    r = cliente.post(f"/api/analises/{id_}/segmentar", json={"caixa": [40, 30, 90, 70]})
    assert r.status_code == 503
    assert "Dependências do SAM 2 ausentes" in r.json()["erro"] or "sam2" in r.json()["erro"]


def test_segmentar_com_regiao_existente(cliente, monkeypatch):
    """Segmentação usando o regiao_id de uma região já existente."""
    seg = SAM2Segmentor(preditor=PreditorMock())
    monkeypatch.setattr(servidor, "_segmentador_sam2", seg)

    r_post = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _criar_termograma(), "image/jpeg")})
    assert r_post.status_code == 200
    dados = r_post.json()
    id_ = dados["id"]

    # Cria região manual para testar a rota com regiao_id
    r_put = cliente.put(
        f"/api/analises/{id_}",
        json={"regioes": [{"nome": "Bucha A", "classe": "bucha", "caixa": [40.0, 30.0, 90.0, 70.0], "origem": "manual"}]},
    )
    assert r_put.status_code == 200
    regiao_id = r_put.json()["regioes"][0]["id"]

    r_seg = cliente.post(
        f"/api/analises/{id_}/segmentar",
        json={"regiao_id": regiao_id, "metric_ratio": 0.5},
    )
    assert r_seg.status_code == 200, r_seg.text
    resp = r_seg.json()
    assert resp["ok"] is True
    assert "segmentacao" in resp
    seg_info = resp["segmentacao"]
    assert seg_info["score"] == pytest.approx(0.95, abs=0.01)
    assert "geometria" in seg_info
    assert seg_info["geometria"]["length_metric"] is not None
    assert "termica_isolada" in seg_info
    assert isinstance(seg_info["contorno"], list)
    assert len(seg_info["contorno"]) > 0

    # Cada ponto deve ser [float, float]
    pt0 = seg_info["contorno"][0]
    assert len(pt0) == 2
    assert isinstance(pt0[0], float) and isinstance(pt0[1], float)

    # Verifica se persistiu no backend e se obter retorna a segmentação
    r_get = cliente.get(f"/api/analises/{id_}")
    assert r_get.status_code == 200
    analise_atualizada = r_get.json()
    regiao_atualizada = next(r for r in analise_atualizada["regioes"] if r["id"] == regiao_id)
    assert "segmentacao" in regiao_atualizada
    assert regiao_atualizada["segmentacao"]["score"] == pytest.approx(seg_info["score"], abs=1e-5)


def test_segmentar_caixa_avulsa_cria_nova_regiao(cliente, monkeypatch):
    """Segmentação passando caixa direta sem regiao_id cria nova região na análise."""
    seg = SAM2Segmentor(preditor=PreditorMock())
    monkeypatch.setattr(servidor, "_segmentador_sam2", seg)

    r_post = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _criar_termograma(), "image/jpeg")})
    assert r_post.status_code == 200
    id_ = r_post.json()["id"]
    qtd_inicial = len(r_post.json()["regioes"])

    caixa_nova = [42.0, 32.0, 88.0, 68.0]
    r_seg = cliente.post(f"/api/analises/{id_}/segmentar", json={"caixa": caixa_nova})
    assert r_seg.status_code == 200, r_seg.text
    resp = r_seg.json()
    assert resp["ok"] is True
    assert len(resp["analise"]["regioes"]) == qtd_inicial + 1
    nova = resp["analise"]["regioes"][-1]
    assert "segmentacao" in nova
    assert nova["origem"] == "segmentacao:sam2"


def test_segmentar_erros_validacao(cliente, monkeypatch):
    """Validações de entrada: caixa inválida, região inexistente, inspeção 404."""
    seg = SAM2Segmentor(preditor=PreditorMock())
    monkeypatch.setattr(servidor, "_segmentador_sam2", seg)

    # 404 em inspeção inexistente
    r = cliente.post("/api/analises/inexistente/segmentar", json={"caixa": [10, 10, 50, 50]})
    assert r.status_code == 404

    r_post = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _criar_termograma(), "image/jpeg")})
    id_ = r_post.json()["id"]

    # 404 em regiao_id inexistente
    r = cliente.post(f"/api/analises/{id_}/segmentar", json={"regiao_id": "r_fantasma"})
    assert r.status_code == 404

    # 422 sem caixa e sem regiao_id
    r = cliente.post(f"/api/analises/{id_}/segmentar", json={})
    assert r.status_code == 422

    # 422 caixa invertida
    r = cliente.post(f"/api/analises/{id_}/segmentar", json={"caixa": [50, 50, 10, 10]})
    assert r.status_code == 422

    # 422 metric_ratio inválido
    r = cliente.post(f"/api/analises/{id_}/segmentar", json={"caixa": [10, 10, 50, 50], "metric_ratio": -1.0})
    assert r.status_code == 422


def test_modelo_pontos_quentes_sam2_listado_e_ativavel(cliente):
    """Verifica se o modelo pontos-quentes-sam2 aparece na lista e pode ser ativado via PUT."""
    r = cliente.get("/api/modelos")
    assert r.status_code == 200
    dados = r.json()
    modelos = dados["modelos"]
    ids = [m["id"] for m in modelos]
    assert "pontos-quentes-sam2" in ids

    sam2_meta = next(m for m in modelos if m["id"] == "pontos-quentes-sam2")
    assert sam2_meta["nome"] == "Pontos quentes + SAM 2 (Segmentação Fundacional)"
    assert sam2_meta["tipo"] == "combinado"
    assert "Hiera" in sam2_meta["arquitetura"]
    assert "treino" in sam2_meta["cartao"]
    assert "vantagens" in sam2_meta["cartao"]
    assert "limitacoes" in sam2_meta["cartao"]

    # Ativa o modelo pontos-quentes-sam2
    r_put = cliente.put("/api/modelos/ativo", json={"id": "pontos-quentes-sam2"})
    assert r_put.status_code == 200
    assert r_put.json()["ativo"] == "pontos-quentes-sam2"

    # Confere se persistiu
    r_get = cliente.get("/api/modelos")
    assert r_get.json()["ativo"] == "pontos-quentes-sam2"


def test_nova_analise_com_modelo_sam2_segmenta_automaticamente(cliente, monkeypatch):
    """Criar análise com modelo pontos-quentes-sam2 executa segmentação automática em todas as regiões."""
    preditor_mock = PreditorMock()
    seg = SAM2Segmentor(preditor=preditor_mock)
    monkeypatch.setattr(servidor, "_segmentador_sam2", seg)

    # Envia análise solicitando explicitamente o modelo pontos-quentes-sam2
    r = cliente.post(
        "/api/analises",
        data={"modelo": "pontos-quentes-sam2"},
        files={"arquivo": ("teste.jpg", _termograma_com_ponto_quente(), "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    analise = r.json()

    assert analise["modelo"]["id"] == "pontos-quentes-sam2"
    assert len(analise["regioes"]) >= 1

    # Todas as regiões detectadas devem vir com segmentacao preenchida
    for reg in analise["regioes"]:
        assert "segmentacao" in reg
        s = reg["segmentacao"]
        assert "score" in s
        assert "geometria" in s
        assert "termica_isolada" in s
        assert "contorno" in s
        assert isinstance(s["contorno"], list)
        assert len(s["contorno"]) > 2
        assert s["termica_isolada"]["t_max"] is not None

    # Deve conter a etapa "Segmentação SAM 2" nas etapas da análise
    nomes_etapas = [e["nome"] for e in analise["etapas"]]
    assert "Segmentação SAM 2" in nomes_etapas

    # O mock de predição deve ter sido chamado para cada região
    assert len(preditor_mock.chamadas) >= 1

    # Quando o modelo já é o ativo, não precisa passar no data do formulário
    cliente.put("/api/modelos/ativo", json={"id": "pontos-quentes-sam2"})
    preditor_mock.chamadas.clear()

    r2 = cliente.post(
        "/api/analises",
        files={"arquivo": ("teste2.jpg", _termograma_com_ponto_quente(), "image/jpeg")},
    )
    assert r2.status_code == 200
    analise2 = r2.json()
    assert analise2["modelo"]["id"] == "pontos-quentes-sam2"
    assert len(analise2["regioes"]) >= 1
    assert "segmentacao" in analise2["regioes"][0]
    assert len(preditor_mock.chamadas) >= 1

