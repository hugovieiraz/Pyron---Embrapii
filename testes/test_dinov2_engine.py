"""Testes unitários e de integração para o motor de classificação DINOv2."""

from __future__ import annotations

import threading
import numpy as np
import pytest
import torch

from nucleo.classificacao.dinov2_engine import (
    CLASSES_PYRON,
    COR_FUNDO_NEUTRO,
    NOMES_CLASSES,
    TAMANHO_MINIMO,
    TAMANHO_PATCH,
    DINOv2Classifier,
    ajustar_resolucao_vit,
    escolher_dispositivo,
    gerar_padrao_sintetico,
    normalizar_tensor_imagenet,
    recortar_e_mascarar,
)


class MockDINOModel(torch.nn.Module):
    """Modelo simulado determinístico para testes unitários rápidos sem carregar rede neural pesada."""

    def __init__(self, dim: int = 384):
        super().__init__()
        self.dim = dim

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size = x.shape[0]
        # Gera embedding fixo baseado no valor médio da entrada para diferenciar imagens
        media_val = float(x.mean().item())
        vetor = torch.zeros((batch_size, self.dim), dtype=torch.float32)
        vetor[:, 0] = media_val
        vetor[:, 1] = 1.0 - media_val
        # Normalização
        return vetor


@pytest.fixture(autouse=True)
def _limpar_singleton():
    DINOv2Classifier._instancia = None
    yield
    DINOv2Classifier._instancia = None


def test_escolher_dispositivo():
    dev_cpu = escolher_dispositivo("cpu")
    assert dev_cpu.type == "cpu"
    dev_auto = escolher_dispositivo()
    assert dev_auto.type in ("cuda", "cpu")


def test_recortar_e_mascarar_com_bbox():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[20:60, 30:70] = 255
    recorte = recortar_e_mascarar(img, bbox=[30, 20, 70, 60])
    assert recorte.shape == (40, 40, 3)
    assert np.all(recorte == 255)


def test_recortar_e_mascarar_com_fundo_neutro():
    img = np.full((50, 50, 3), 200, dtype=np.uint8)
    mascara = np.zeros((50, 50), dtype=np.uint8)
    mascara[10:30, 10:30] = 1

    recorte = recortar_e_mascarar(img, mascara=mascara)
    assert recorte.shape == (50, 50, 3)
    # Dentro da máscara mantém 200
    assert np.all(recorte[15, 15] == 200)
    # Fora da máscara vira o fundo neutro
    assert np.all(recorte[0, 0] == COR_FUNDO_NEUTRO)


def test_recortar_e_mascarar_erros():
    with pytest.raises(ValueError, match="formato H x W x 3"):
        recortar_e_mascarar(np.zeros((50, 50), dtype=np.uint8))

    with pytest.raises(ValueError, match="Caixa deve possuir 4 valores"):
        recortar_e_mascarar(np.zeros((50, 50, 3), dtype=np.uint8), bbox=[10, 20])


def test_ajustar_resolucao_vit():
    # Caso 1: imagem pequena (100x150) deve crescer até pelo menos TAMANHO_MINIMO (224)
    pequena = np.zeros((100, 150, 3), dtype=np.uint8)
    ajustada = ajustar_resolucao_vit(pequena)
    h, w = ajustada.shape[:2]
    assert h >= TAMANHO_MINIMO
    assert w >= TAMANHO_MINIMO
    assert h % TAMANHO_PATCH == 0
    assert w % TAMANHO_PATCH == 0

    # Caso 2: imagem de 300x450 ajustada para múltiplos de 14
    media = np.zeros((300, 450, 3), dtype=np.uint8)
    ajustada_media = ajustar_resolucao_vit(media)
    hm, wm = ajustada_media.shape[:2]
    assert hm % TAMANHO_PATCH == 0
    assert wm % TAMANHO_PATCH == 0


def test_normalizar_tensor_imagenet():
    img = np.full((224, 224, 3), 128, dtype=np.uint8)
    dispositivo = torch.device("cpu")
    tensor = normalizar_tensor_imagenet(img, dispositivo)
    assert tensor.shape == (1, 3, 224, 224)
    assert tensor.device == dispositivo
    assert tensor.dtype == torch.float32


def test_gerar_padroes_sinteticos():
    for classe in CLASSES_PYRON:
        padrao = gerar_padrao_sintetico(classe)
        assert padrao.shape == (TAMANHO_MINIMO, TAMANHO_MINIMO, 3)
        assert padrao.dtype == np.uint8
        assert padrao.mean() > 0


def test_classifier_mock_determinismo():
    # Cria protótipos unitários sintéticos
    dim = 384
    prototipos = {}
    for i, c in enumerate(CLASSES_PYRON):
        v = np.zeros(dim, dtype=np.float32)
        v[i] = 1.0
        prototipos[c] = v

    mock_model = MockDINOModel(dim=dim)
    clf = DINOv2Classifier(modelo=mock_model, dispositivo="cpu", prototipos=prototipos, temperatura=0.1)

    # Imagem simulada
    img = np.full((224, 224, 3), 100, dtype=np.uint8)
    emb = clf.extrair_embedding(img)
    assert emb.shape == (dim,)
    assert pytest.approx(np.linalg.norm(emb), abs=1e-4) == 1.0

    res = clf.classificar(img)
    assert "classe" in res
    assert "confianca" in res
    assert "nome" in res
    assert "scores" in res
    assert res["classe"] in CLASSES_PYRON
    assert res["nome"] == NOMES_CLASSES[res["classe"]]
    assert pytest.approx(sum(res["scores"].values()), abs=1e-2) == 1.0


def test_classifier_registrar_prototipo():
    dim = 64
    v_inicial = np.zeros(dim, dtype=np.float32)
    v_inicial[0] = 1.0
    prototipos = {"isolador": v_inicial}

    clf = DINOv2Classifier(modelo=MockDINOModel(dim=dim), dispositivo="cpu", prototipos=prototipos)

    v_novo = np.zeros(dim, dtype=np.float32)
    v_novo[1] = 1.0
    clf.registrar_prototipo("isolador", v_novo, peso=1.0)

    atualizado = clf.prototipos["isolador"]
    assert pytest.approx(np.linalg.norm(atualizado), abs=1e-4) == 1.0
    assert atualizado[0] > 0
    assert atualizado[1] > 0


def test_singleton_thread_safe():
    instancias = []

    def instanciar():
        c = DINOv2Classifier.obter_instancia(modelo=MockDINOModel(384), dispositivo="cpu")
        instancias.append(c)

    threads = [threading.Thread(target=instanciar) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(instancias) == 10
    primeira = instancias[0]
    for inst in instancias[1:]:
        assert inst is primeira


def test_integracao_real_dinov2():
    """Teste usando os pesos reais do DINOv2 já cacheados localmente."""
    clf = DINOv2Classifier.obter_instancia()
    padrao = gerar_padrao_sintetico("isolador")
    res = clf.classificar(padrao)

    assert res["classe"] == "isolador"
    assert res["confianca"] >= 0.60
    assert res["nome"] == "Isolador"
    assert len(res["scores"]) == len(CLASSES_PYRON)
