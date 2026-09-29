"""Entrada única de imagens térmicas.

Aceita um JPEG radiométrico FLIR (temperatura medida) ou uma imagem colorida com a barra de
escala visível (temperatura estimada pela paleta). O resto do sistema recebe sempre o mesmo
objeto, com a matriz de temperatura e a indicação de como ela foi obtida.
"""

from __future__ import annotations

import io
import warnings
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from nucleo import flir, paleta


class OCRPreguicoso:
    """Leitor de texto carregado só na primeira imagem sem dados radiométricos (leva alguns segundos)."""

    def __init__(self):
        self._ocr = None

    def __call__(self, imagem):
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR

            self._ocr = RapidOCR()
        return self._ocr(imagem)


@dataclass
class ImagemTermica:
    temperatura_c: np.ndarray  # float32; NaN onde não há medida (textos e ícones, na estimada)
    radiometrica: bool
    exibida_rgb: np.ndarray  # a imagem colorida como a câmera gravou
    foto_visivel: bytes | None
    metadados: dict = field(default_factory=dict)

    @property
    def origem(self) -> str:
        return "medida (radiométrica)" if self.radiometrica else "estimada pela paleta de cores"


def _data_exif(img: Image.Image) -> str:
    valor = str(img.getexif().get(306, "") or "")
    # "2022:12:03 14:11:28" -> "2022-12-03 14:11:28"
    return valor.replace(":", "-", 2) if len(valor) >= 10 else ""


def _reduzir(mapa: np.ndarray, fator: int) -> np.ndarray:
    h, w = mapa.shape[0] // fator, mapa.shape[1] // fator
    blocos = mapa[: h * fator, : w * fator].reshape(h, fator, w, fator).transpose(0, 2, 1, 3).reshape(h, w, -1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(blocos, axis=2).astype(np.float32)


def carregar(dados: bytes, ocr=None) -> ImagemTermica:
    """Abre a imagem e devolve a temperatura de cada pixel.

    ``ocr`` só é usado quando a imagem não é radiométrica (para ler os limites da escala).
    """
    try:
        img = Image.open(io.BytesIO(dados))
        img.load()
    except OSError as erro:
        raise ValueError("Não consegui abrir o arquivo como imagem. Envie um JPEG ou PNG.") from erro
    rgb = np.array(img.convert("RGB"))
    data = _data_exif(img)
    modelo_exif = str(img.getexif().get(272, "") or "")

    try:
        termo = flir.ler_bytes(dados)
    except ValueError:
        termo = None

    if termo is not None:
        p = termo.parametros
        return ImagemTermica(
            temperatura_c=termo.temperatura_c,
            radiometrica=True,
            exibida_rgb=rgb,
            foto_visivel=flir.foto_visivel(dados),
            metadados={
                "camera": p.modelo or modelo_exif,
                "data_hora": data,
                "emissividade": round(p.emissividade, 3),
                "distancia_m": round(p.distancia_m, 2),
                "temp_refletida_c": round(p.temp_refletida_c, 1),
                "temp_atmosfera_c": round(p.temp_atmosfera_c, 1),
                "umidade_relativa": round(p.umidade_relativa, 2),
                "resolucao_sensor": f"{termo.bruto.shape[1]}×{termo.bruto.shape[0]}",
            },
        )

    try:
        esc = paleta.escala(rgb, ocr)
    except ValueError as erro:
        raise ValueError(
            "A imagem não tem dados radiométricos e não encontrei a barra de cores com a escala. "
            "Envie o JPEG original da câmera."
        ) from erro
    if esc.t_max is None or esc.t_min is None:
        raise ValueError("Encontrei a barra de cores, mas não consegui ler os limites da escala.")
    inv = paleta.inverter(rgb, esc)
    return ImagemTermica(
        temperatura_c=_reduzir(inv.temperatura_c, 2),
        radiometrica=False,
        exibida_rgb=rgb,
        foto_visivel=None,
        metadados={
            "camera": modelo_exif or "desconhecida",
            "data_hora": data,
            "escala_lida_c": [esc.t_min, esc.t_max],
            "pixels_saturados": round(float(inv.saturado.mean()), 3),
            "aviso": "Temperatura estimada pelas cores. Erro típico de 0,5 °C na mediana; "
            "acima do topo da escala a temperatura real não pode ser recuperada.",
        },
    )
