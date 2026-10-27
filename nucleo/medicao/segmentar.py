"""Contorno do objeto com o SAM 2.1 (Meta, Apache 2.0) pelo ``transformers`` (``Sam2Model``).

O codificador da imagem roda uma vez por foto (guardado pela chave da foto); cada clique depois só passa
pelo decodificador.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

import numpy as np

from nucleo.medicao import modelos


class Segmentador:
    """SAM 2.1 sob demanda. ``variante``: ``small`` ou ``base-plus``."""

    def __init__(self, variante: str = modelos.SAM_PADRAO, dispositivo: str | None = None, cache: int = 4):
        if variante not in modelos.SAM:
            raise ValueError(f"variante do SAM 2.1 desconhecida: {variante}")
        self.variante = variante
        self.dispositivo = dispositivo
        self._modelo = None
        self._processador = None
        self._trava = threading.Lock()
        self._cache: OrderedDict = OrderedDict()
        self._tamanho_cache = cache
        self.tempos_ms: dict[str, float] = {}

    @property
    def nome(self) -> str:
        return modelos.SAM[self.variante]

    def carregar(self):
        with self._trava:
            if self._modelo is None:
                from transformers import Sam2Model, Sam2Processor

                self.dispositivo = self.dispositivo or modelos.dispositivo()
                caminho = modelos.caminho_sam(self.variante)
                origem = str(caminho) if modelos.sam_instalado(self.variante) else self.nome
                self._processador = Sam2Processor.from_pretrained(origem)
                self._modelo = Sam2Model.from_pretrained(origem).to(self.dispositivo).eval()
        return self._modelo, self._processador

    def _codificar(self, imagem, chave):
        """Embeddings da imagem, do cache quando a mesma foto (``chave``) já passou."""
        import torch

        if chave is not None and chave in self._cache:
            self._cache.move_to_end(chave)
            self.tempos_ms["codificador"] = 0.0
            return self._cache[chave]
        modelo, proc = self.carregar()
        t0 = time.perf_counter()
        entrada = proc(images=imagem, return_tensors="pt").to(self.dispositivo)
        with torch.inference_mode():
            emb = modelo.get_image_embeddings(entrada["pixel_values"])
        item = (emb, entrada["original_sizes"])
        self.tempos_ms["codificador"] = (time.perf_counter() - t0) * 1000
        if chave is not None:
            self._cache[chave] = item
            while len(self._cache) > self._tamanho_cache:
                self._cache.popitem(last=False)
        return item

    @modelos.com_reserva_cpu
    def _decodificar(self, imagem, chave, multiplas: bool, **pistas) -> tuple[np.ndarray, float]:
        import torch

        modelo, proc = self.carregar()
        emb, tamanhos = self._codificar(imagem, chave)
        t0 = time.perf_counter()
        entrada = proc(images=imagem, return_tensors="pt", **pistas)
        entrada = {k: v.to(self.dispositivo) for k, v in entrada.items() if k != "pixel_values"}
        entrada.pop("original_sizes", None)
        entrada.pop("reshaped_input_sizes", None)
        with torch.inference_mode():
            saida = modelo(image_embeddings=emb, multimask_output=multiplas, **entrada)
        mascaras = proc.post_process_masks(saida.pred_masks.cpu(), tamanhos.cpu())[0][0]  # (n, H, W)
        notas = saida.iou_scores[0, 0].float().cpu().numpy()
        i = int(np.argmax(notas))
        self.tempos_ms["decodificador"] = (time.perf_counter() - t0) * 1000
        return mascaras[i].numpy().astype(bool), float(notas[i])

    def mascara_por_ponto(self, imagem, ponto, negativos=(), chave=None) -> tuple[np.ndarray, float]:
        """Máscara do objeto sob ``ponto`` (x, y). Pede 3 máscaras e fica com a de maior nota."""
        pontos = [[float(ponto[0]), float(ponto[1])]] + [[float(x), float(y)] for x, y in negativos]
        rotulos = [1] + [0] * len(negativos)
        return self._decodificar(
            imagem, chave, multiplas=not negativos, input_points=[[pontos]], input_labels=[[rotulos]]
        )

    def mascara_por_caixa(self, imagem, caixa, chave=None) -> tuple[np.ndarray, float]:
        """Máscara do objeto dentro de ``caixa`` (x0, y0, x1, y1)."""
        return self._decodificar(imagem, chave, multiplas=False, input_boxes=[[[float(c) for c in caixa]]])
