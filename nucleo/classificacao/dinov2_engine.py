"""Classificação de ativos elétricos e anomalias com base em representações fundacionais DINOv2.

O DINOv2 (Meta AI) extrai representações visuais ricas sem supervisão através de arquiteturas Vision
Transformer (ViT). O modelo opera com patches de 14x14 pixels e gera vetores semânticos densos e
invariantes a rotações parciais, iluminação e ruído térmico.

Este módulo implementa o classificador zero-shot/few-shot baseado em galeria de protótipos de
embeddings característicos do setor elétrico:
- Isolador (textura periódica de aletas cerâmicas/poliméricas)
- Bucha (corpo alongado vertical com terminal superior e discos)
- Para-raio (coluna esguia de anéis de varistor de óxido de zinco/silicone)
- Conexão (junções aparafusadas metálicas com reflexos especulares)
- Radiador (painéis verticais de aletas de troca térmica)
- Tanque (superfície plana metálica maciça de transformador)
- Cabo (condutor contínuo/trançado cilíndrico)
- Ponto quente (concentração radial de gradiente térmico de alta energia)
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Sequence

import cv2
import numpy as np
import torch

log = logging.getLogger(__name__)

TAMANHO_PATCH = 14
TAMANHO_MINIMO = 224
IMAGENET_MEDIA = (0.485, 0.456, 0.406)
IMAGENET_DESVIO = (0.229, 0.224, 0.225)
COR_FUNDO_NEUTRO = (128, 128, 128)
TEMPERATURA_SOFTMAX_PADRAO = 0.07
CONFIANCA_MINIMA_AJUSTE = 0.60

CLASSES_PYRON: tuple[str, ...] = (
    "isolador",
    "bucha",
    "para_raio",
    "conexao",
    "radiador",
    "tanque",
    "transformador",
    "cabo",
    "estrutura",
)

NOMES_CLASSES: dict[str, str] = {
    "isolador": "Isolador",
    "bucha": "Bucha",
    "para_raio": "Para-raio",
    "conexao": "Conexão",
    "radiador": "Radiador",
    "tanque": "Tanque",
    "transformador": "Transformador",
    "cabo": "Cabo",
    "estrutura": "Estrutura",
}


def escolher_dispositivo(preferido: str | torch.device | None = None) -> torch.device:
    """Seleciona GPU CUDA se disponível, senão fallback automático para CPU."""
    if preferido:
        return torch.device(preferido)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def recortar_e_mascarar(
    imagem_rgb: np.ndarray,
    bbox: Sequence[float] | None = None,
    mascara: np.ndarray | None = None,
) -> np.ndarray:
    """Recorta a região de interesse (caixa delimitadora) e aplica máscara com fundo neutro se fornecida."""
    img = np.asarray(imagem_rgb)
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"Imagem RGB deve possuir formato H x W x 3; recebido {img.shape}")

    altura, largura = img.shape[:2]

    if bbox is not None:
        caixa = [float(v) for v in bbox]
        if len(caixa) != 4:
            raise ValueError(f"Caixa deve possuir 4 valores [x0, y0, x1, y1]; recebido {bbox!r}")
        x0 = max(0, min(int(round(caixa[0])), largura - 1))
        y0 = max(0, min(int(round(caixa[1])), altura - 1))
        x1 = max(x0 + 1, min(int(round(caixa[2])), largura))
        y1 = max(y0 + 1, min(int(round(caixa[3])), altura))
        recorte = img[y0:y1, x0:x1].copy()

        if mascara is not None:
            m = np.asarray(mascara)
            if m.shape == (altura, largura):
                m_recorte = m[y0:y1, x0:x1]
            elif m.shape == recorte.shape[:2]:
                m_recorte = m
            else:
                m_recorte = cv2.resize(m.astype(np.uint8), (recorte.shape[1], recorte.shape[0]), interpolation=cv2.INTER_NEAREST)
            fundo_neutro = np.full_like(recorte, COR_FUNDO_NEUTRO, dtype=np.uint8)
            fora = (m_recorte <= 0)
            recorte[fora] = fundo_neutro[fora]
        return recorte

    if mascara is not None:
        m = np.asarray(mascara)
        if m.shape[:2] != (altura, largura):
            m = cv2.resize(m.astype(np.uint8), (largura, altura), interpolation=cv2.INTER_NEAREST)
        recorte = img.copy()
        fundo_neutro = np.full_like(recorte, COR_FUNDO_NEUTRO, dtype=np.uint8)
        fora = (m <= 0)
        recorte[fora] = fundo_neutro[fora]
        return recorte

    return img.copy()


def ajustar_resolucao_vit(imagem_rgb: np.ndarray) -> np.ndarray:
    """Ajusta a imagem para que dimensões sejam estritamente divisíveis por 14 px e no mínimo 224x224."""
    altura, largura = imagem_rgb.shape[:2]
    # Mínimo absoluto de 224 pixels (16 * 14)
    h_alvo = max(TAMANHO_MINIMO, (altura // TAMANHO_PATCH) * TAMANHO_PATCH)
    w_alvo = max(TAMANHO_MINIMO, (largura // TAMANHO_PATCH) * TAMANHO_PATCH)

    # Garantia estrita de divisibilidade pelo patch size de 14 px
    if h_alvo % TAMANHO_PATCH != 0:
        h_alvo = ((h_alvo + TAMANHO_PATCH - 1) // TAMANHO_PATCH) * TAMANHO_PATCH
    if w_alvo % TAMANHO_PATCH != 0:
        w_alvo = ((w_alvo + TAMANHO_PATCH - 1) // TAMANHO_PATCH) * TAMANHO_PATCH

    if (altura, largura) != (h_alvo, w_alvo):
        return cv2.resize(imagem_rgb, (w_alvo, h_alvo), interpolation=cv2.INTER_CUBIC)
    return imagem_rgb


def normalizar_tensor_imagenet(imagem_rgb: np.ndarray, dispositivo: torch.device) -> torch.Tensor:
    """Converte array numpy RGB para tensor float32 normalizado segundo padrões ImageNet (média e desvio)."""
    # Converte para float32 [0.0, 1.0]
    arr = imagem_rgb.astype(np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(dispositivo)

    media = torch.tensor(IMAGENET_MEDIA, dtype=torch.float32, device=dispositivo).view(1, 3, 1, 1)
    desvio = torch.tensor(IMAGENET_DESVIO, dtype=torch.float32, device=dispositivo).view(1, 3, 1, 1)
    return (tensor - media) / desvio


def gerar_padrao_sintetico(classe: str) -> np.ndarray:
    """Gera padrão visual sintético determinístico representativo da classe para a galeria de protótipos."""
    tam = TAMANHO_MINIMO

    if classe == "isolador":
        img = np.full((tam, tam, 3), 160, dtype=np.uint8)
        for y in range(14, 210, 28):
            cv2.rectangle(img, (40, y), (184, y + 10), (90, 80, 70), -1)
            cv2.rectangle(img, (28, y + 10), (196, y + 16), (210, 200, 190), -1)
            cv2.rectangle(img, (98, y + 16), (126, y + 28), (110, 100, 90), -1)
        return img

    if classe == "bucha":
        img = np.full((tam, tam, 3), 140, dtype=np.uint8)
        cv2.rectangle(img, (98, 14), (126, 42), (200, 200, 210), -1)
        pts = np.array([[70, 210], [154, 210], [130, 42], [94, 42]], np.int32)
        cv2.fillPoly(img, [pts], (120, 115, 110))
        for y in range(56, 196, 20):
            cv2.ellipse(img, (112, y), (35, 6), 0, 0, 360, (70, 65, 60), 2)
        return img

    if classe == "para_raio":
        img = np.full((tam, tam, 3), 150, dtype=np.uint8)
        cv2.rectangle(img, (90, 14), (134, 210), (130, 125, 120), -1)
        for y in range(20, 205, 14):
            cv2.rectangle(img, (75, y), (149, y + 5), (60, 60, 65), -1)
            cv2.rectangle(img, (70, y + 5), (154, y + 8), (220, 215, 210), -1)
        return img

    if classe == "conexao":
        img = np.full((tam, tam, 3), 120, dtype=np.uint8)
        cv2.rectangle(img, (42, 60), (182, 164), (190, 175, 140), -1)
        for cx, cy in [(75, 90), (149, 90), (75, 134), (149, 134)]:
            cv2.circle(img, (cx, cy), 16, (80, 80, 85), -1)
            cv2.circle(img, (cx, cy), 10, (230, 230, 240), -1)
        return img

    if classe == "radiador":
        img = np.full((tam, tam, 3), 130, dtype=np.uint8)
        for x in range(28, 200, 14):
            cv2.rectangle(img, (x, 28), (x + 6, 196), (70, 75, 80), -1)
            cv2.rectangle(img, (x + 6, 28), (x + 10, 196), (190, 195, 200), -1)
        return img

    if classe == "transformador":
        img = np.full((tam, tam, 3), 105, dtype=np.uint8)
        cv2.rectangle(img, (40, 60), (184, 200), (130, 135, 130), -1)
        cv2.rectangle(img, (40, 60), (184, 200), (70, 75, 70), 3)
        for bx in (70, 112, 154):
            cv2.rectangle(img, (bx - 6, 25), (bx + 6, 60), (190, 185, 180), -1)
            cv2.ellipse(img, (bx, 25), (8, 4), 0, 0, 360, (220, 220, 230), -1)
        for rx in (20, 28, 196, 204):
            cv2.rectangle(img, (rx - 3, 75), (rx + 3, 185), (85, 90, 95), -1)
        return img

    if classe == "tanque":
        img = np.full((tam, tam, 3), 110, dtype=np.uint8)
        cv2.rectangle(img, (20, 20), (204, 204), (135, 140, 135), -1)
        cv2.rectangle(img, (20, 20), (204, 204), (70, 75, 70), 4)
        for bx in range(35, 195, 30):
            cv2.circle(img, (bx, 28), 5, (50, 50, 50), -1)
            cv2.circle(img, (bx, 196), 5, (50, 50, 50), -1)
        return img

    if classe == "cabo":
        img = np.full((tam, tam, 3), 160, dtype=np.uint8)
        cv2.line(img, (14, 180), (210, 44), (40, 40, 40), 24)
        cv2.line(img, (14, 180), (210, 44), (170, 170, 175), 14)
        cv2.line(img, (14, 180), (210, 44), (230, 230, 235), 4)
        return img

    if classe == "estrutura":
        img = np.full((tam, tam, 3), 60, dtype=np.uint8)
        cv2.line(img, (20, 20), (204, 204), (190, 195, 200), 6)
        cv2.line(img, (204, 20), (20, 204), (190, 195, 200), 6)
        cv2.line(img, (20, 20), (20, 204), (160, 165, 170), 8)
        cv2.line(img, (204, 20), (204, 204), (160, 165, 170), 8)
        return img

    return np.full((tam, tam, 3), 128, dtype=np.uint8)


class DINOv2Classifier:
    """Classificador de alta precisão baseado em embeddings DINOv2 e galeria prototípica.

    Implementado sob padrão Singleton thread-safe com lazy loading dos pesos da rede.
    """

    _instancia: DINOv2Classifier | None = None
    _trava_singleton: threading.Lock = threading.Lock()

    @classmethod
    def obter_instancia(
        cls,
        modelo: Any | None = None,
        dispositivo: str | torch.device | None = None,
        prototipos: dict[str, np.ndarray] | None = None,
        temperatura: float = TEMPERATURA_SOFTMAX_PADRAO,
    ) -> DINOv2Classifier:
        """Garante acesso à instância global única do classificador de maneira thread-safe."""
        if cls._instancia is None:
            with cls._trava_singleton:
                if cls._instancia is None:
                    cls._instancia = cls(
                        modelo=modelo,
                        dispositivo=dispositivo,
                        prototipos=prototipos,
                        temperatura=temperatura,
                    )
        return cls._instancia

    def __init__(
        self,
        modelo: Any | None = None,
        dispositivo: str | torch.device | None = None,
        prototipos: dict[str, np.ndarray] | None = None,
        temperatura: float = TEMPERATURA_SOFTMAX_PADRAO,
    ) -> None:
        self.dispositivo = escolher_dispositivo(dispositivo)
        self.temperatura = float(temperatura)
        self._trava_operacao = threading.Lock()
        self._modelo = modelo
        self._prototipos: dict[str, np.ndarray] = dict(prototipos) if prototipos is not None else {}

        if self._modelo is not None and not self._prototipos:
            self._inicializar_prototipos()

    def _garantir_modelo(self) -> Any:
        """Carrega o modelo DINOv2 via torch.hub sob demanda (lazy loading) e inicializa protótipos."""
        if self._modelo is not None:
            return self._modelo

        with self._trava_operacao:
            if self._modelo is not None:
                return self._modelo

            log.info("Carregando modelo DINOv2 (dinov2_vits14) no dispositivo %s...", self.dispositivo)
            try:
                # Carrega o modelo ViT-S/14 oficial do repositório da Meta
                modelo_carregado = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14")
                modelo_carregado.to(self.dispositivo)
                modelo_carregado.eval()
                self._modelo = modelo_carregado
            except Exception as erro:
                raise RuntimeError(f"Falha ao carregar pesos do DINOv2: {erro}") from erro

            if not self._prototipos:
                self._inicializar_prototipos()

            return self._modelo

    def _inicializar_prototipos(self) -> None:
        """Gera a galeria inicial de vetores representativos para as classes elétricas."""
        for classe in CLASSES_PYRON:
            padrao = gerar_padrao_sintetico(classe)
            emb = self._inferir_embedding_bruto(padrao)
            self._prototipos[classe] = emb

    def _inferir_embedding_bruto(self, imagem_rgb: np.ndarray) -> np.ndarray:
        """Processa imagem pré-formatada pelo ViT e extrai embedding com L2 norm."""
        ajustada = ajustar_resolucao_vit(imagem_rgb)
        tensor = normalizar_tensor_imagenet(ajustada, self.dispositivo)
        modelo = self._modelo if self._modelo is not None else self._garantir_modelo()

        with torch.no_grad():
            saida = modelo(tensor)
            if hasattr(saida, "shape") and len(saida.shape) > 2:
                saida = saida[:, 0]
            # Normalização Euclidiana (L2 norm)
            norm = torch.norm(saida, p=2, dim=-1, keepdim=True)
            saida_l2 = saida / torch.clamp(norm, min=1e-12)
            emb_np = saida_l2.squeeze(0).detach().cpu().numpy().astype(np.float32)

        return emb_np

    def extrair_embedding(
        self,
        imagem_rgb: np.ndarray,
        bbox: Sequence[float] | None = None,
        mascara: np.ndarray | None = None,
    ) -> np.ndarray:
        """Recorta, aplica máscara se presente e extrai o embedding unitário (L2 norm) via DINOv2."""
        self._garantir_modelo()
        recorte = recortar_e_mascarar(imagem_rgb, bbox=bbox, mascara=mascara)
        return self._inferir_embedding_bruto(recorte)

    def registrar_prototipo(self, classe: str, embedding: np.ndarray, peso: float = 1.0) -> None:
        """Atualiza a galeria de protótipos incorporando novo vetor por média móvel L2-normalizada."""
        vetor = np.asarray(embedding, dtype=np.float32).ravel()
        norm = np.linalg.norm(vetor)
        if norm > 0:
            vetor = vetor / norm

        with self._trava_operacao:
            if classe in self._prototipos:
                atual = self._prototipos[classe]
                novo_centro = atual + float(peso) * vetor
                self._prototipos[classe] = novo_centro / max(np.linalg.norm(novo_centro), 1e-12)
            else:
                self._prototipos[classe] = vetor

    @property
    def prototipos(self) -> dict[str, np.ndarray]:
        """Dicionário imutável de leitura dos protótipos cadastrados."""
        self._garantir_modelo()
        return dict(self._prototipos)

    def classificar(
        self,
        imagem_rgb: np.ndarray,
        bbox: Sequence[float] | None = None,
        mascara: np.ndarray | None = None,
    ) -> dict:
        """Classifica a região calculando similaridade de cosseno contra os protótipos e softmax calibrado.

        Retorna:
            dict com formato {"classe": str, "confianca": float, "nome": str, "scores": dict[str, float]}
        """
        self._garantir_modelo()
        embedding = self.extrair_embedding(imagem_rgb, bbox=bbox, mascara=mascara)

        # Similaridade de cosseno entre vetores L2-normalizados (produto escalar)
        scores_cosseno: dict[str, float] = {}
        for classe, proto in self._prototipos.items():
            sim = float(np.dot(embedding, proto))
            scores_cosseno[classe] = sim

        classes = list(scores_cosseno.keys())
        sims = np.array([scores_cosseno[c] for c in classes], dtype=np.float64)

        # Softmax calibrado com temperatura Boltzmann
        temperatura = max(self.temperatura, 1e-4)
        logits = sims / temperatura
        logits_estabilizados = logits - np.max(logits)
        exp_logits = np.exp(logits_estabilizados)
        probabilidades = exp_logits / np.sum(exp_logits)

        scores_calibrados = {c: float(round(p, 4)) for c, p in zip(classes, probabilidades)}

        melhor_idx = int(np.argmax(probabilidades))
        melhor_classe = classes[melhor_idx]
        melhor_confianca = float(round(probabilidades[melhor_idx], 4))
        nome_legivel = NOMES_CLASSES.get(melhor_classe, melhor_classe)

        return {
            "classe": melhor_classe,
            "confianca": melhor_confianca,
            "nome": nome_legivel,
            "scores": scores_calibrados,
        }
