"""Profundidade métrica de uma foto com o MoGe-2 (Microsoft, MIT), carregado só quando usado.

Instalar: ``pip install --no-deps git+https://github.com/microsoft/MoGe.git`` e o ``utils3d_moge`` que ele
pede (o repositório traz também o MoGe-3, que precisa de FlexGEMM/Triton; o MoGe-2 não). Pesos: ver
``nucleo/medicao/modelos.py``.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from nucleo.medicao import modelos

# diagonal do filme de 35 mm (36 × 24 mm), base do "equivalente em 35 mm" do EXIF
DIAGONAL_35MM = math.hypot(36.0, 24.0)


@dataclass
class Geometria:
    """O que a profundidade devolve para a medição."""

    pontos: np.ndarray  # H × W × 3, metros, referencial da câmera (x direita, y baixo, z frente)
    validos: np.ndarray  # H × W, bool
    focal_px: float  # focal horizontal em pixels
    lente: str  # "exif" ou "estimada"
    tempo_ms: float
    modelo: str


def abrir(imagem) -> Image.Image:
    """Abre (caminho, bytes ou PIL) já na orientação certa do EXIF, em RGB."""
    if isinstance(imagem, (bytes, bytearray)):
        import io

        imagem = Image.open(io.BytesIO(imagem))
    elif not isinstance(imagem, Image.Image):
        imagem = Image.open(imagem)
    exif = imagem.getexif()
    imagem = ImageOps.exif_transpose(imagem)
    imagem.info["exif_pyron"] = exif
    return imagem.convert("RGB") if imagem.mode != "RGB" else imagem


def fov_do_exif(imagem: Image.Image) -> float | None:
    """Campo de visão horizontal (graus) pela focal equivalente em 35 mm do EXIF, se houver.

    Equivalente em 35 mm mede pela diagonal: f_px = f35 · diagonal_px / 43,27 mm.
    """
    exif = imagem.info.get("exif_pyron") or imagem.getexif()
    try:
        f35 = exif.get_ifd(0x8769).get(0xA405)
    except Exception:
        f35 = None
    if not f35:
        return None
    w, h = imagem.size
    f_px = float(f35) * math.hypot(w, h) / DIAGONAL_35MM
    return math.degrees(2 * math.atan(w / (2 * f_px)))


class Profundidade:
    """MoGe-2 sob demanda. ``variante``: ``vits``, ``vitb`` ou ``vitl``. ``num_tokens``: resolução de entrada
    (o MoGe-2 usa de 1200 a 3600; padrão 3600). Na CPU de 4 núcleos da nuvem, o ViT-L levou ~19 s com 3600
    e ~4,5 s com 1200 numa foto de 900 × 1600."""

    def __init__(self, variante: str = modelos.MOGE_PADRAO, dispositivo: str | None = None, num_tokens: int | None = None):
        if variante not in modelos.MOGE:
            raise ValueError(f"variante do MoGe-2 desconhecida: {variante}")
        self.variante = variante
        self.dispositivo = dispositivo
        self.num_tokens = num_tokens
        self._modelo = None
        self._trava = threading.Lock()

    @property
    def nome(self) -> str:
        return modelos.MOGE[self.variante]

    def carregar(self):
        with self._trava:
            if self._modelo is None:
                import torch
                from moge.model.v2 import MoGeModel

                self.dispositivo = self.dispositivo or modelos.dispositivo()
                caminho = modelos.caminho_moge(self.variante)
                origem = str(caminho) if caminho.exists() else self.nome
                modelo = MoGeModel.from_pretrained(origem).to(self.dispositivo).eval()
                torch.set_grad_enabled(False)
                self._modelo = modelo
        return self._modelo

    def estimar(self, imagem, usar_exif: bool = True, num_tokens: int | None = None) -> Geometria:
        import torch

        img = abrir(imagem)
        modelo = self.carregar()
        fov = fov_do_exif(img) if usar_exif else None
        t0 = time.perf_counter()
        x = torch.from_numpy(np.asarray(img, dtype=np.float32) / 255.0).permute(2, 0, 1).to(self.dispositivo)
        with torch.inference_mode():
            saida = modelo.infer(
                x, fov_x=fov, num_tokens=num_tokens or self.num_tokens, use_fp16=self.dispositivo == "cuda"
            )
        pontos = saida["points"].float().cpu().numpy()
        validos = saida["mask"].cpu().numpy().astype(bool) & np.all(np.isfinite(pontos), axis=-1)
        focal = float(saida["intrinsics"][0, 0].cpu()) * img.width
        return Geometria(
            pontos=pontos,
            validos=validos,
            focal_px=focal,
            lente="exif" if fov is not None else "estimada",
            tempo_ms=(time.perf_counter() - t0) * 1000,
            modelo=self.nome,
        )
