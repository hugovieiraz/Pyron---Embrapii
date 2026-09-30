"""Modelo treinado instalado como pasta (``cartao.json`` + ``modelo.onnx``).

O cartão diz o que o modelo olha (``entrada.fonte``) e como ler o que ele devolve (``saida.formato``).

Entrada (``entrada.fonte``):

- ``temperatura`` (padrão): a matriz em °C, normalizada para 0..1 (``entrada.normalizacao``:
  ``por_imagem`` ou ``fixa`` entre ``t_min`` e ``t_max``; ver ``preparo.py``), repetida nos 3 canais
  e padronizada com ``entrada.media`` e ``entrada.desvio``;
- ``imagem_exibida``: a imagem colorida que a câmera gravou (a paleta), no mesmo sentido da matriz,
  redimensionada para ``largura`` × ``altura``, de 0 a 1 e padronizada com ``media`` e ``desvio``.
  É o caso dos modelos treinados no Colab com os JPEG rotulados no CVAT.

Saída (``saida.formato``):

- ``contrato`` (padrão): ``caixas`` [1, N, 4] (x0, y0, x1, y1 de 0 a 1), ``pontuacoes`` [1, N] e
  ``classes`` [1, N] (índice em ``classes`` do cartão), com o pós-processamento embutido no ONNX;
- ``rfdetr``: a exportação oficial do RF-DETR. ``dets`` [1, Q, 4] (centro x, centro y, largura,
  altura, de 0 a 1) e ``labels`` [1, Q, K+1] (notas antes da sigmoide; a última coluna é o fundo).
  ``saida.deslocamento_classe`` soma um valor ao índice da coluna (0 quando as classes vêm de 0 a K-1).

Em qualquer caso as caixas saem de 0 a 1 e viram pixels da matriz de temperatura: a imagem
colorida e a matriz cobrem o mesmo campo de visão.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from nucleo.detectores import Deteccao, Detector, preparo

FONTES = ("temperatura", "imagem_exibida")
FORMATOS = ("contrato", "rfdetr")
MAXIMO_DETECCOES = 100


class DetectorONNX(Detector):
    def __init__(self, pasta: Path):
        cartao = json.loads((pasta / "cartao.json").read_text(encoding="utf-8"))
        arquivo = pasta / cartao.get("arquivo", "modelo.onnx")
        if not arquivo.exists():
            raise ValueError(f"arquivo do modelo não encontrado: {arquivo.name}")
        super().__init__(
            id=cartao["id"],
            nome=cartao["nome"],
            tipo="aprendizado",
            arquitetura=cartao["arquitetura"],
            descricao=cartao.get("descricao", ""),
            classes=list(cartao["classes"]),
            versao=str(cartao.get("versao", "1.0")),
            cartao=cartao,
            nomes=dict(cartao.get("nomes", {})),
        )
        self.arquivo = arquivo
        self.entrada = cartao["entrada"]
        self.saida = cartao.get("saida", {})
        self.fonte = self.entrada.get("fonte", "temperatura")
        self.formato = self.saida.get("formato", "contrato")
        if self.fonte not in FONTES:
            raise ValueError(f"entrada.fonte desconhecida: {self.fonte}")
        if self.formato not in FORMATOS:
            raise ValueError(f"saida.formato desconhecido: {self.formato}")
        self.precisa_imagem = self.fonte == "imagem_exibida"
        self.limiar = float(cartao.get("limiar_confianca", 0.4))
        self._sessao = None

    def _sessao_onnx(self):
        if self._sessao is None:
            import onnxruntime as ort

            self._sessao = ort.InferenceSession(str(self.arquivo), providers=["CPUExecutionProvider"])
        return self._sessao

    # ---------------------------------------------------------------- entrada

    def preparar(self, temperatura: np.ndarray) -> np.ndarray:
        e = self.entrada
        norm = preparo.para_rede(
            temperatura,
            e["largura"],
            e["altura"],
            modo=e.get("normalizacao", "fixa"),
            t_min=e.get("t_min", -20.0),
            t_max=e.get("t_max", 80.0),
        )
        return preparo.tensor_entrada(norm, e.get("media", (0.0, 0.0, 0.0)), e.get("desvio", (1.0, 1.0, 1.0)))

    def preparar_imagem(self, imagem: np.ndarray) -> np.ndarray:
        """Imagem RGB [A, L, 3] de 0 a 255 -> [1, 3, altura, largura] padronizada."""
        e = self.entrada
        rgb = Image.fromarray(np.ascontiguousarray(imagem[..., :3]).astype(np.uint8))
        rgb = rgb.resize((int(e["largura"]), int(e["altura"])), Image.BILINEAR)
        x = np.asarray(rgb, dtype=np.float32) / 255.0
        media = np.asarray(e.get("media", (0.485, 0.456, 0.406)), dtype=np.float32)
        desvio = np.asarray(e.get("desvio", (0.229, 0.224, 0.225)), dtype=np.float32)
        return ((x - media) / desvio).transpose(2, 0, 1)[None].astype(np.float32)

    # ---------------------------------------------------------------- saída

    def _ler_contrato(self, saidas: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return tuple(np.asarray(saidas[n])[0] for n in ("caixas", "pontuacoes", "classes"))

    def _ler_rfdetr(self, saidas: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Caixas (x0, y0, x1, y1 de 0 a 1), confiança e classe de cada consulta do DETR."""
        nomes = self.saida.get("nomes", {})
        dets = np.asarray(saidas[nomes.get("caixas", "dets")], dtype=np.float32)
        notas = np.asarray(saidas[nomes.get("notas", "labels")], dtype=np.float32)
        dets = dets[0] if dets.ndim == 3 else dets
        notas = notas[0] if notas.ndim == 3 else notas
        if self.saida.get("fundo_ultima_coluna", True):
            notas = notas[:, :-1]
        prob = 1.0 / (1.0 + np.exp(-np.clip(notas, -88, 88)))
        classes = prob.argmax(axis=1) + int(self.saida.get("deslocamento_classe", 0))
        confianca = prob.max(axis=1)
        cx, cy, w, h = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3]
        caixas = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
        return caixas, confianca, classes

    # ---------------------------------------------------------------- detecção

    def detectar(self, temperatura: np.ndarray, imagem: np.ndarray | None = None) -> list[Deteccao]:
        h, w = temperatura.shape
        if self.precisa_imagem:
            if imagem is None:
                raise ValueError("este modelo olha a imagem colorida da câmera, que não veio junto com a temperatura")
            x = self.preparar_imagem(imagem)
        else:
            x = self.preparar(temperatura)
        sessao = self._sessao_onnx()
        brutas = sessao.run(None, {sessao.get_inputs()[0].name: x})
        saidas = dict(zip((o.name for o in sessao.get_outputs()), brutas))
        caixas, pontuacoes, classes = self._ler_rfdetr(saidas) if self.formato == "rfdetr" else self._ler_contrato(saidas)
        resultado = []
        for caixa, p, c in zip(caixas, pontuacoes, classes):
            if float(p) < self.limiar or not 0 <= int(c) < len(self.classes):
                continue
            x0, y0, x1, y1 = (float(v) for v in np.clip(caixa, 0, 1))
            if x1 - x0 <= 0 or y1 - y0 <= 0:
                continue
            resultado.append(Deteccao(self.classes[int(c)], [x0 * w, y0 * h, x1 * w, y1 * h], round(float(p), 3)))
        return sorted(resultado, key=lambda d: -d.confianca)[:MAXIMO_DETECCOES]
