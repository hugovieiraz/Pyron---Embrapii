"""Modelo treinado instalado como pasta (``cartao.json`` + ``modelo.onnx``).

Contrato do arquivo ONNX, igual para qualquer arquitetura (RF-DETR, SSD MobileNet...):

- entrada ``imagem``: float32 [1, 3, A, L]. A temperatura é normalizada para 0..1 (modo
  ``entrada.normalizacao``: ``por_imagem`` ou ``fixa`` entre ``t_min`` e ``t_max``; ver
  ``preparo.py``), repetida nos 3 canais e padronizada com ``entrada.media`` e ``entrada.desvio``;
- saídas ``caixas`` [1, N, 4] (x0, y0, x1, y1 normalizados 0..1), ``pontuacoes`` [1, N] e
  ``classes`` [1, N] (índice em ``classes`` do cartão).

O script de treino exporta o modelo já neste formato, com o pós-processamento embutido.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from nucleo.detectores import Deteccao, Detector, preparo


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
        self.limiar = float(cartao.get("limiar_confianca", 0.4))
        self._sessao = None

    def _sessao_onnx(self):
        if self._sessao is None:
            import onnxruntime as ort

            self._sessao = ort.InferenceSession(str(self.arquivo), providers=["CPUExecutionProvider"])
        return self._sessao

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

    def detectar(self, temperatura: np.ndarray) -> list[Deteccao]:
        h, w = temperatura.shape
        saidas = self._sessao_onnx().run(["caixas", "pontuacoes", "classes"], {"imagem": self.preparar(temperatura)})
        caixas, pontuacoes, classes = (np.asarray(s)[0] for s in saidas)
        resultado = []
        for caixa, p, c in zip(caixas, pontuacoes, classes):
            if float(p) < self.limiar or not 0 <= int(c) < len(self.classes):
                continue
            x0, y0, x1, y1 = (float(v) for v in np.clip(caixa, 0, 1))
            resultado.append(Deteccao(self.classes[int(c)], [x0 * w, y0 * h, x1 * w, y1 * h], round(float(p), 3)))
        return sorted(resultado, key=lambda d: -d.confianca)
