"""Testes da seleção de keyframes em vídeo e consenso multi-frame (nucleo/medicao/video_keyframes.py)."""

import math
import tempfile
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from nucleo.medicao import Medida
from nucleo.medicao import video_keyframes as vk


def _criar_padrao_nitido(w: int = 320, h: int = 240) -> np.ndarray:
    """Cria uma imagem com alto contraste e bordas nítidas (tabuleiro/linhas)."""
    img = np.full((h, w, 3), 200, dtype=np.uint8)
    for y in range(0, h, 20):
        for x in range(0, w, 20):
            if (x // 20 + y // 20) % 2 == 0:
                img[y : y + 20, x : x + 20] = 30
    cv2.rectangle(img, (50, 50), (150, 150), (0, 0, 255), 3)
    cv2.putText(img, "PYRON", (60, 110), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    return img


def _criar_video_teste(caminho: Path, duracao_s: float = 2.0, fps: int = 20) -> Path:
    """Gera um vídeo sintético alternando quadros nítidos e quadros com desfoque forte."""
    padrao = _criar_padrao_nitido()
    h, w = padrao.shape[:2]

    quatrocc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(caminho), quatrocc, float(fps), (w, h))

    total = int(duracao_s * fps)
    for i in range(total):
        # A cada segundo, insere um trecho nítido e trechos borrados
        fase = (i / fps) % 1.0
        if 0.3 <= fase <= 0.6:
            # Quadro nítido com leve deslocamento para simular movimento de câmera
            dx = int(10 * math.sin(i * 0.2))
            M = np.float32([[1, 0, dx], [0, 1, 0]])
            frame = cv2.warpAffine(padrao, M, (w, h))
        else:
            # Quadro borrado (motion blur / fora de foco)
            frame = cv2.GaussianBlur(padrao, (45, 45), 0)

        out.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

    out.release()
    return caminho


def test_calcular_nitidez_distingue_nitido_e_borrado():
    nitido = _criar_padrao_nitido()
    borrado = cv2.GaussianBlur(nitido, (35, 35), 0)

    score_nitido = vk.calcular_nitidez(nitido)
    score_borrado = vk.calcular_nitidez(borrado)

    assert score_nitido > 500.0
    assert score_borrado < 50.0
    assert score_nitido > 10 * score_borrado


def test_selecionar_keyframes_filtra_borrados(tmp_path):
    video_path = tmp_path / "video_teste.mp4"
    _criar_video_teste(video_path, duracao_s=2.5, fps=20)

    keyframes = vk.selecionar_keyframes(video_path, max_keyframes=3, limiar_nitidez=100.0)

    assert len(keyframes) >= 1
    assert len(keyframes) <= 3

    # Todos os keyframes selecionados devem ter alta nitidez
    for kf in keyframes:
        assert kf.nitidez > 100.0
        assert kf.largura == 320
        assert kf.altura == 240
        assert len(kf.bytes_jpeg) > 1000

    # Ordenação cronológica garantida
    tempos = [kf.tempo_s for kf in keyframes]
    assert tempos == sorted(tempos)


def test_selecionar_keyframes_por_bytes(tmp_path):
    video_path = tmp_path / "video_bytes.mp4"
    _criar_video_teste(video_path, duracao_s=1.5, fps=15)
    dados = video_path.read_bytes()

    keyframes = vk.selecionar_keyframes(dados, max_keyframes=2)
    assert len(keyframes) >= 1
    assert isinstance(keyframes[0].bytes_jpeg, bytes)


def test_propagar_pista_translacao():
    img1 = np.zeros((200, 200, 3), dtype=np.uint8)
    cv2.circle(img1, (60, 60), 20, (255, 255, 255), -1)

    img2 = np.zeros((200, 200, 3), dtype=np.uint8)
    # Círculo transladado +30px em X e +10px em Y
    cv2.circle(img2, (90, 70), 20, (255, 255, 255), -1)

    pista = {"ponto": [60.0, 60.0]}
    propagada = vk.propagar_pista(pista, img1, img2)

    assert "ponto" in propagada
    # Esperado próximo a (90, 70)
    assert propagada["ponto"][0] == pytest.approx(90.0, abs=5.0)
    assert propagada["ponto"][1] == pytest.approx(70.0, abs=5.0)


def test_agregar_medicoes_consenso():
    # 4 medições simulando estimativas em ângulos diferentes
    m1 = Medida(comprimento_cm=50.2, largura_cm=20.1, altura_cm=80.0, distancia_cm=210.0, metodo="MoGe-2")
    m2 = Medida(comprimento_cm=51.0, largura_cm=19.8, altura_cm=81.2, distancia_cm=212.0, metodo="MoGe-2")
    m3 = Medida(comprimento_cm=49.8, largura_cm=20.5, altura_cm=79.5, distancia_cm=208.0, metodo="MoGe-2")
    m4 = Medida(comprimento_cm=50.5, largura_cm=20.0, altura_cm=80.8, distancia_cm=211.0, metodo="MoGe-2")

    consenso = vk.agregar_medicoes([m1, m2, m3, m4])

    assert consenso["total_quadros"] == 4
    assert consenso["metodo"] == "MoGe-2"

    c = consenso["comprimento_cm"]
    # Mediana em torno de 50.35 cm
    assert c["valor"] == pytest.approx(50.35, abs=0.5)
    assert c["desvio_padrao"] < 1.0
    assert c["minimo"] == 49.8
    assert c["maximo"] == 51.0
    assert c["n_quadros"] == 4
    # Redução percentual da incerteza por 4 amostras: 1 - 1/sqrt(4) = 50%
    assert c["reducao_incerteza_pct"] == pytest.approx(50.0, abs=0.1)


class _MedidorFalso:
    def __init__(self, valor_base: float = 30.0):
        self.valor_base = valor_base
        self.chamadas = 0

    def medir(self, imagem, pista, referencia=None):
        self.chamadas += 1
        # Leve variação para simular pequenas incertezas de ponto de vista
        var = 0.5 * math.sin(self.chamadas)
        return Medida(
            comprimento_cm=round(self.valor_base + var, 2),
            largura_cm=15.0,
            distancia_cm=150.0,
            metodo="teste_sintetico",
        )


def test_medir_video_ponta_a_ponta(tmp_path):
    video_path = tmp_path / "video_completo.mp4"
    _criar_video_teste(video_path, duracao_s=2.0, fps=15)

    falso = _MedidorFalso(valor_base=42.0)
    pista_inicial = {"caixa": [40, 40, 160, 160]}

    resultado = vk.medir_video(
        video_path,
        pista_inicial,
        max_keyframes=3,
        medidor=falso,
    )

    assert resultado["n_keyframes"] >= 1
    assert "consenso" in resultado
    assert "comprimento_cm" in resultado["consenso"]
    assert resultado["consenso"]["comprimento_cm"]["valor"] == pytest.approx(42.0, abs=1.0)
    assert len(resultado["quadros"]) == resultado["n_keyframes"]
    assert falso.chamadas == resultado["n_keyframes"]
