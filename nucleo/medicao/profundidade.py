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


def _registrar_heif() -> None:
    """HEIC/HEIF (padrão de muitos celulares) pelo ``pillow-heif`` (BSD-3), se estiver instalado."""
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except ImportError:
        pass


_registrar_heif()


def abrir(imagem) -> Image.Image:
    """Abre (caminho, bytes ou PIL; JPEG, PNG ou HEIC) já na orientação certa do EXIF, em RGB."""
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

    Equivalente em 35 mm mede pela diagonal: f_px = f35 · diagonal_px / 43,27 mm. A diagonal é a do quadro 4:3
    do sensor (lado maior da foto × 5/4), não a da foto: o celular grava 16:9 ou 19,5:9 cortando o sensor 4:3 e
    mantém o equivalente do quadro inteiro (Galaxy S23, 1848 × 4000: 23 mm → 2658 px, o mesmo que f = 5,4 mm com
    pixel de 2,04 µm; pela diagonal da foto cortada daria 2342 px, 12 % a menos). Em foto 4:3 dá o mesmo.
    """
    exif = imagem.info.get("exif_pyron") or imagem.getexif()
    try:
        f35 = exif.get_ifd(0x8769).get(0xA405)
    except Exception:
        f35 = None
    if not f35:
        return None
    w, h = imagem.size
    diagonal_43 = max(w, h) * 5 / 4
    f_px = float(f35) * diagonal_43 / DIAGONAL_35MM
    return math.degrees(2 * math.atan(w / (2 * f_px)))


def _fp16_do_ambiente() -> bool | None:
    """``PYRON_MEDICAO_FP16``: ``0`` desliga, ``1`` força; ausente = automático (None)."""
    import os

    valor = os.environ.get("PYRON_MEDICAO_FP16", "").strip().lower()
    if valor in ("0", "false", "nao", "não", "off"):
        return False
    if valor in ("1", "true", "sim", "on"):
        return True
    return None


class Profundidade:
    """MoGe-2 sob demanda. ``variante``: ``vits``, ``vitb`` ou ``vitl``. ``num_tokens``: resolução de entrada
    (o MoGe-2 usa de 1200 a 3600; padrão 3600). Na CPU de 4 núcleos da nuvem, o ViT-L levou ~19 s com 3600
    e ~4,5 s com 1200 numa foto de 900 × 1600."""

    def __init__(self, variante: str = modelos.MOGE_PADRAO, dispositivo: str | None = None, num_tokens: int | None = None,
                 usar_exif: bool = True, meia_precisao: bool | None = None):
        if variante not in modelos.MOGE:
            raise ValueError(f"variante do MoGe-2 desconhecida: {variante}")
        self.variante = variante
        self.dispositivo = dispositivo
        self.num_tokens = num_tokens
        self.usar_exif = usar_exif
        # meia precisão (fp16) na placa de vídeo: None = automático (tenta e cai para fp32 se a saída vier vazia;
        # na GTX 1650 o fp16 devolve máscara toda falsa). PYRON_MEDICAO_FP16=0/1 força.
        self.meia_precisao = meia_precisao if meia_precisao is not None else _fp16_do_ambiente()
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

    def estimar(self, imagem, usar_exif: bool | None = None, num_tokens: int | None = None) -> Geometria:
        import torch

        img = abrir(imagem)
        modelo = self.carregar()
        fov = fov_do_exif(img) if (self.usar_exif if usar_exif is None else usar_exif) else None
        t0 = time.perf_counter()
        x = torch.from_numpy(np.asarray(img, dtype=np.float32) / 255.0).permute(2, 0, 1).to(self.dispositivo)
        tokens = num_tokens or self.num_tokens

        def rodar(fp16: bool):
            with torch.inference_mode():
                saida = modelo.infer(x, fov_x=fov, num_tokens=tokens, use_fp16=fp16)
            pontos = saida["points"].float().cpu().numpy()
            validos = saida["mask"].cpu().numpy().astype(bool) & np.all(np.isfinite(pontos), axis=-1)
            return saida, pontos, validos

        fp16 = self.dispositivo == "cuda" and self.meia_precisao is not False
        saida, pontos, validos = rodar(fp16)
        if fp16 and not validos.any() and self.meia_precisao is None:
            # placa sem fp16 confiável (GTX 16xx): refaz em fp32 e não tenta fp16 de novo nesta instância
            self.meia_precisao = False
            saida, pontos, validos = rodar(False)
        elif fp16 and self.meia_precisao is None:
            self.meia_precisao = True
        focal = float(saida["intrinsics"][0, 0].cpu()) * img.width
        return Geometria(
            pontos=pontos,
            validos=validos,
            focal_px=focal,
            lente="exif" if fov is not None else "estimada",
            tempo_ms=(time.perf_counter() - t0) * 1000,
            modelo=self.nome,
        )


# ---------------------------------------------------------------- Depth Anything 3 Metric (alternativa ao MoGe-2)
FOV_PADRAO = 65.0  # graus no lado maior, quando a foto não traz a lente (câmera principal típica de celular)


def focal_px(imagem: Image.Image) -> tuple[float, str]:
    """Focal em pixels pelo EXIF (quadro 4:3, ver ``fov_do_exif``) ou, sem EXIF, por um campo de visão padrão."""
    fov = fov_do_exif(imagem)
    if fov is not None:
        return imagem.width / (2 * math.tan(math.radians(fov) / 2)), "exif"
    return max(imagem.size) / (2 * math.tan(math.radians(FOV_PADRAO) / 2)), "padrão"


class ProfundidadeDA3:
    """Depth Anything 3 Metric Large (ByteDance, Apache 2.0; ``depth-anything/DA3METRIC-LARGE``).

    Só a rede (``depth_anything_3.model``), sem a API do pacote, que puxa open3d, pycolmap e o ``evo`` (GPL). A rede dá
    a profundidade relativa à focal: metros = saída · focal / 300, com a focal em pixels na resolução processada
    (lado maior 504, múltiplo de 14). Não estima a lente: usa a do EXIF ou ``FOV_PADRAO``.
    Instalar: ``pip install --no-deps --ignore-requires-python git+https://github.com/ByteDance-Seed/Depth-Anything-3.git``
    e ``einops omegaconf addict safetensors``; pesos em ``modelos/medicao/DA3METRIC-LARGE``.
    """

    nome = "depth-anything/DA3METRIC-LARGE"

    def __init__(self, dispositivo: str | None = None, resolucao: int = 504, usar_exif: bool = True):
        self.dispositivo = dispositivo
        self.resolucao = resolucao
        self.usar_exif = usar_exif
        self._modelo = None
        self._trava = threading.Lock()

    def carregar(self):
        with self._trava:
            if self._modelo is None:
                import torch
                from depth_anything_3.cfg import create_object, load_config
                from depth_anything_3.registry import MODEL_REGISTRY
                from safetensors.torch import load_file

                self.dispositivo = self.dispositivo or modelos.dispositivo()
                rede = create_object(load_config(MODEL_REGISTRY["da3metric-large"]))
                pesos = load_file(str(modelos.pasta() / "DA3METRIC-LARGE" / "model.safetensors"))
                rede.load_state_dict({k.removeprefix("model."): v for k, v in pesos.items()}, strict=True)
                torch.set_grad_enabled(False)
                self._modelo = rede.to(self.dispositivo).eval()
        return self._modelo

    def estimar(self, imagem, **_) -> Geometria:
        import cv2
        import torch

        img = abrir(imagem)
        rede = self.carregar()
        w, h = img.size
        fx, lente = focal_px(img) if self.usar_exif else (max(w, h) / (2 * math.tan(math.radians(FOV_PADRAO) / 2)), "padrão")
        t0 = time.perf_counter()
        escala = self.resolucao / max(w, h)
        wp = max(14, int(round(w * escala / 14)) * 14)
        hp = max(14, int(round(h * escala / 14)) * 14)
        x = cv2.resize(np.asarray(img), (wp, hp), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
        x = torch.from_numpy(x).permute(2, 0, 1)[None, None].to(self.dispositivo)
        with torch.inference_mode():
            saida = rede(x)
        f_proc = (fx * wp / w + fx * hp / h) / 2
        prof = saida["depth"].float().reshape(hp, wp).cpu().numpy() * f_proc / 300.0
        z = cv2.resize(prof, (w, h), interpolation=cv2.INTER_LINEAR)
        xs = (np.arange(w, dtype=np.float32) + 0.5 - w / 2) / fx
        ys = (np.arange(h, dtype=np.float32) + 0.5 - h / 2) / fx
        pontos = np.stack([xs[None, :] * z, ys[:, None] * z, z], axis=-1)
        validos = np.isfinite(z) & (z > 0)
        return Geometria(pontos=pontos, validos=validos, focal_px=float(fx), lente=lente,
                         tempo_ms=(time.perf_counter() - t0) * 1000, modelo=self.nome)
