"""Detectores para a comparação: MobileNet ajustado × DINOv2 congelado (PyTorch).

Os dois usam a mesma cabeça de detecção (Faster R-CNN: propostas de região + classificador de caixas)
e o mesmo treino. A diferença é a base visual ("os olhos"):

- MobileNetV3: pré-treinado no COCO e ajustado com os nossos rótulos (as últimas camadas aprendem).
- DINOv2: modelo da Meta treinado sem rótulos em 142 milhões de imagens. Fica congelado: para cada
  pedaço de 14×14 pixels ele entrega um vetor de características (o "contexto" do pedaço), e só a
  cabeça de detecção aprende a transformar essas características em caixas.

As imagens mantêm o sentido da foto (em pé 480×640, deitada 640×480) e a rede vê a temperatura
normalizada, a mesma preparação do Pyron (``nucleo/detectores/preparo.py``).
"""

from __future__ import annotations

import copy
import math
import time
from collections import OrderedDict

import numpy as np
import torch
import torch.nn.functional as F

from ml import comparacao
from ml.treinar import _recorte_aleatorio, criar_modelo
from nucleo.detectores import preparo

NORMALIZACAO = "por_imagem"


def tamanho_entrada(temperatura: np.ndarray) -> tuple[int, int]:
    """(largura, altura) da entrada da rede, no mesmo sentido da foto."""
    h, w = temperatura.shape
    return (480, 640) if h > w else (640, 480)


class Termico(torch.utils.data.Dataset):
    """Imagem [3, A, L] e alvos no formato do torchvision, com aumentos de dados no treino."""

    def __init__(self, amostras, aumentar: bool, semente: int = 2026):
        self.amostras, self.aumentar = amostras, aumentar
        self.rng = np.random.default_rng(semente)

    def __len__(self) -> int:
        return len(self.amostras)

    def __getitem__(self, i):
        a = self.amostras[i]
        h_m, w_m = a.temperatura.shape
        largura, altura = tamanho_entrada(a.temperatura)
        ajuste = (self.rng.uniform(-0.08, 0.08), self.rng.uniform(-0.08, 0.08)) if self.aumentar else (0.0, 0.0)
        norm = preparo.para_rede(a.temperatura, largura, altura, modo=NORMALIZACAO, ajuste_faixa=ajuste)
        caixas = a.caixas * [largura / w_m, altura / h_m, largura / w_m, altura / h_m]
        classes = a.classes.copy()
        if self.aumentar:
            if self.rng.random() < 0.5:  # espelho horizontal
                norm = norm[:, ::-1].copy()
                caixas = caixas[:, [2, 1, 0, 3]] * [-1, 1, -1, 1] + [largura, 0, largura, 0]
            if self.rng.random() < 0.5 and len(caixas):  # aproximação de um pedaço da imagem
                norm, caixas, manter = _recorte_aleatorio(norm, caixas, self.rng)
                caixas, classes = caixas[manter], classes[manter]
            norm = np.clip(norm + self.rng.normal(0, 0.01, norm.shape).astype(np.float32), 0, 1)  # ruído do sensor
        imagem = torch.from_numpy(np.ascontiguousarray(np.stack([norm] * 3, axis=0), dtype=np.float32))
        alvo = {
            "boxes": torch.as_tensor(np.asarray(caixas, dtype=np.float32).reshape(-1, 4)),
            "labels": torch.as_tensor(np.asarray(classes, dtype=np.int64) + 1),  # 0 é o fundo no torchvision
        }
        return imagem, alvo


def _juntar(lote):
    return tuple(zip(*lote))


# ---------------------------------------------------------------- modelos

def criar_mobilenet(n_classes: int):
    """Faster R-CNN com MobileNetV3-Large FPN pré-treinado no COCO (o mesmo do Pyron)."""
    return criar_modelo(n_classes, pre_treinado=True)


class DinoCongelado(torch.nn.Module):
    """DINOv2 congelado como base visual de um Faster R-CNN.

    A imagem é redimensionada para que cada pedaço de 14 pixels do ViT corresponda a ``passo`` pixels
    da imagem do detector (passo 8: grade fina, boa para os terminais pequenos). A saída é um mapa de
    características [B, C, A/passo, L/passo].
    """

    def __init__(self, nome: str = "dinov2_vits14", passo: int = 8):
        super().__init__()
        self.vit = torch.hub.load("facebookresearch/dinov2", nome, trust_repo=True)
        self.vit.requires_grad_(False)
        self.vit.eval()
        self.passo = passo
        self.out_channels = self.vit.embed_dim

    def train(self, modo: bool = True):
        super().train(modo)
        self.vit.eval()  # congelado: nunca em modo de treino
        return self

    def forward(self, x):
        b, _, h, w = x.shape
        gh, gw = math.ceil(h / self.passo), math.ceil(w / self.passo)
        x = F.interpolate(x, size=(gh * 14, gw * 14), mode="bilinear", align_corners=False)
        with torch.no_grad():
            f = self.vit.forward_features(x)["x_norm_patchtokens"]
        f = f.transpose(1, 2).reshape(b, self.out_channels, gh, gw)
        return OrderedDict([("0", f)])


def criar_dino(n_classes: int, nome: str = "dinov2_vits14", passo: int = 8):
    """Faster R-CNN sobre o DINOv2 congelado: só as propostas de região e o classificador aprendem."""
    from torchvision.models.detection import FasterRCNN
    from torchvision.models.detection.anchor_utils import AnchorGenerator
    from torchvision.ops import MultiScaleRoIAlign

    base = DinoCongelado(nome, passo)
    ancoras = AnchorGenerator(sizes=((16, 32, 64, 128, 256),), aspect_ratios=((0.5, 1.0, 2.0),))  # iguais às do MobileNet
    recorte = MultiScaleRoIAlign(featmap_names=["0"], output_size=7, sampling_ratio=2)
    return FasterRCNN(base, num_classes=n_classes + 1, rpn_anchor_generator=ancoras, box_roi_pool=recorte,
                      min_size=480, max_size=640, box_detections_per_img=100)


def parametros(modelo) -> dict:
    total = sum(p.numel() for p in modelo.parameters())
    treinaveis = sum(p.numel() for p in modelo.parameters() if p.requires_grad)
    return {"total": total, "treinaveis": treinaveis}


# ---------------------------------------------------------------- treino e previsão

def prever(modelo, amostras, dispositivo):
    """Previsões na grade da matriz de temperatura de cada amostra."""
    modelo.eval()
    saida = []
    with torch.no_grad():
        for a in amostras:
            h_m, w_m = a.temperatura.shape
            largura, altura = tamanho_entrada(a.temperatura)
            norm = preparo.para_rede(a.temperatura, largura, altura, modo=NORMALIZACAO)
            img = torch.from_numpy(np.ascontiguousarray(np.stack([norm] * 3, axis=0), dtype=np.float32)).to(dispositivo)
            r = modelo([img])[0]
            caixas = r["boxes"].cpu().numpy() * [w_m / largura, h_m / altura, w_m / largura, h_m / altura]
            saida.append((caixas, r["scores"].cpu().numpy(), r["labels"].cpu().numpy() - 1))
    return saida


def treinar(modelo, treino, validacao, classes, epocas: int = 40, lote: int = 4, lr: float = 0.01,
            avaliar_cada: int = 2, limiar: float = 0.5, dispositivo=None, nome: str = "modelo") -> dict:
    """Treina e guarda a melhor época pelo mAP50 na validação. Devolve o histórico."""
    dispositivo = dispositivo or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    for a in treino + validacao:
        _ = a.temperatura  # lê todas as temperaturas antes (o primeiro acesso abre o JPEG)
    carregador = torch.utils.data.DataLoader(Termico(treino, aumentar=True), batch_size=lote, shuffle=True, collate_fn=_juntar)
    carregador_val = torch.utils.data.DataLoader(Termico(validacao, aumentar=False), batch_size=lote, shuffle=False, collate_fn=_juntar)
    treinaveis = [p for p in modelo.parameters() if p.requires_grad]
    otimizador = torch.optim.SGD(treinaveis, lr=lr, momentum=0.9, weight_decay=1e-4)
    passos = max(1, epocas * len(carregador))
    aquecimento = min(100, passos // 10 + 1)
    agenda = torch.optim.lr_scheduler.LambdaLR(
        otimizador,
        lambda p: (p + 1) / aquecimento if p < aquecimento else 0.5 * (1 + math.cos(math.pi * (p - aquecimento) / max(1, passos - aquecimento))),
    )
    modelo.to(dispositivo)
    h = {"perda_treino": [], "perda_validacao": [], "epocas_map": [], "map50_validacao": [], "partes_perda": []}
    melhor, melhor_estado, melhor_epoca = -1.0, None, None
    inicio = time.time()
    for epoca in range(1, epocas + 1):
        modelo.train()
        soma, n, partes = 0.0, 0, {}
        for imagens, alvos in carregador:
            imagens = [im.to(dispositivo) for im in imagens]
            alvos = [{k: v.to(dispositivo) for k, v in t.items()} for t in alvos]
            perdas = modelo(imagens, alvos)
            total = sum(perdas.values())
            otimizador.zero_grad()
            total.backward()
            torch.nn.utils.clip_grad_norm_(treinaveis, 10.0)
            otimizador.step()
            agenda.step()
            soma += float(total)
            n += 1
            for k, v in perdas.items():
                partes[k] = partes.get(k, 0.0) + float(v)
        h["perda_treino"].append(soma / max(n, 1))
        h["partes_perda"].append({k: v / max(n, 1) for k, v in partes.items()})

        # Perda na validação: as redes do torchvision só calculam perda em modo de treino (sem gradiente aqui).
        with torch.no_grad():
            soma_v, n_v = 0.0, 0
            for imagens, alvos in carregador_val:
                imagens = [im.to(dispositivo) for im in imagens]
                alvos = [{k: v.to(dispositivo) for k, v in t.items()} for t in alvos]
                soma_v += float(sum(modelo(imagens, alvos).values()))
                n_v += 1
        h["perda_validacao"].append(soma_v / max(n_v, 1))

        texto = ""
        if epoca % avaliar_cada == 0 or epoca == epocas:
            r = comparacao.avaliar(validacao, prever(modelo, validacao, dispositivo), classes, {}, limiar)
            m = r["mAP50"] or 0.0
            h["epocas_map"].append(epoca)
            h["map50_validacao"].append(m)
            texto = f"  mAP50 val {m:.3f}"
            if m > melhor:
                melhor, melhor_epoca = m, epoca
                melhor_estado = {k: v.detach().cpu().clone() for k, v in modelo.state_dict().items()}
                texto += "  (melhor até agora)"
        decorrido = time.time() - inicio
        falta = decorrido / epoca * (epocas - epoca)
        print(f"[{nome}] época {epoca:3d}/{epocas}  perda treino {h['perda_treino'][-1]:.3f}  validação {h['perda_validacao'][-1]:.3f}"
              f"{texto}  ({decorrido / 60:.1f} min, faltam ~{falta / 60:.1f} min)")
    if melhor_estado is not None:
        modelo.load_state_dict(melhor_estado)
    h["melhor_epoca"] = melhor_epoca
    h["melhor_map50_validacao"] = melhor
    h["duracao_min"] = round((time.time() - inicio) / 60, 1)
    return h


def copiar_pesos(modelo) -> dict:
    return copy.deepcopy({k: v.detach().cpu() for k, v in modelo.state_dict().items()})
