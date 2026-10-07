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

    def __call__(self, imagem, **opcoes):
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR

            self._ocr = RapidOCR()
        return self._ocr(imagem, **opcoes)


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


def orientar(mapa: np.ndarray, orientacao: int) -> np.ndarray:
    """Gira/espelha a matriz como a marca EXIF manda exibir a foto (mesma regra do PIL exif_transpose).

    A câmera guarda o sensor sempre deitado; com a câmera na vertical, o JPEG ganha Orientation = 6
    (girar 90° no sentido horário). O CVAT e o Windows mostram a foto já girada, e as caixas dos
    rótulos ficam nesse sentido: a matriz de temperatura tem de ficar igual.
    """
    operacoes = {
        2: lambda m: m[:, ::-1],
        3: lambda m: np.rot90(m, 2),
        4: lambda m: m[::-1, :],
        5: lambda m: m.T,
        6: lambda m: np.rot90(m, -1),
        7: lambda m: np.rot90(m, 2).T,
        8: lambda m: np.rot90(m, 1),
    }
    op = operacoes.get(int(orientacao or 1))
    return np.ascontiguousarray(op(mapa)) if op else mapa


def _orientar_foto(foto: bytes | None, orientacao: int) -> bytes | None:
    """A foto visível embutida vem no sentido do sensor: gira igual ao termograma."""
    if not foto or int(orientacao or 1) == 1:
        return foto
    try:
        img = Image.open(io.BytesIO(foto))
        girada = Image.fromarray(orientar(np.asarray(img.convert("RGB")), orientacao))
        buf = io.BytesIO()
        girada.save(buf, format="JPEG", quality=92)
        return buf.getvalue()
    except OSError:
        return foto


def _reduzir(mapa: np.ndarray, fator: int) -> np.ndarray:
    h, w = mapa.shape[0] // fator, mapa.shape[1] // fator
    blocos = mapa[: h * fator, : w * fator].reshape(h, fator, w, fator).transpose(0, 2, 1, 3).reshape(h, w, -1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(blocos, axis=2).astype(np.float32)


def carregar(dados: bytes, ocr=None, limites: tuple[float, float] | None = None, ajustes: dict | None = None) -> ImagemTermica:
    """Abre a imagem e devolve a temperatura de cada pixel.

    ``ocr`` só é usado quando a imagem não é radiométrica (para ler os limites da escala).
    ``limites`` (mínimo, máximo) já conhecidos da escala dispensam o OCR, como num quadro de vídeo.
    ``ajustes`` troca parâmetros de medição do termograma radiométrico (emissividade, distância,
    temperaturas refletida e atmosférica, umidade) antes da conversão, como os softwares das câmeras.
    """
    try:
        img = Image.open(io.BytesIO(dados))
        img.load()
    except OSError as erro:
        raise ValueError("Não consegui abrir o arquivo como imagem. Envie um JPEG ou PNG.") from erro
    rgb = np.array(img.convert("RGB"))
    data = _data_exif(img)
    modelo_exif = str(img.getexif().get(272, "") or "")
    orientacao = int(img.getexif().get(274, 1) or 1)

    try:
        termo = flir.ler_bytes(dados, **(ajustes or {}))
    except ValueError:
        termo = None

    if termo is not None:
        p = termo.parametros
        return ImagemTermica(
            temperatura_c=orientar(termo.temperatura_c, orientacao),
            radiometrica=True,
            exibida_rgb=orientar(rgb, orientacao),
            foto_visivel=_orientar_foto(flir.foto_visivel(dados), orientacao),
            metadados={
                "camera": p.modelo or modelo_exif,
                "data_hora": data,
                "emissividade": round(p.emissividade, 3),
                "distancia_m": round(p.distancia_m, 2),
                "temp_refletida_c": round(p.temp_refletida_c, 1),
                "temp_atmosfera_c": round(p.temp_atmosfera_c, 1),
                "umidade_relativa": round(p.umidade_relativa, 2),
                "resolucao_sensor": f"{termo.bruto.shape[1]}×{termo.bruto.shape[0]}",
                **({"orientacao_exif": orientacao} if orientacao != 1 else {}),
            },
        )

    try:
        t_min, t_max = limites if limites else (None, None)
        esc = paleta.escala(rgb, ocr, t_max=t_max, t_min=t_min)
    except ValueError as erro:
        raise ValueError(
            "A imagem não tem dados radiométricos e não encontrei a barra de cores com a escala. "
            "Envie o JPEG original da câmera."
        ) from erro
    if esc.t_max is None or esc.t_min is None:
        raise ValueError("Encontrei a barra de cores, mas não consegui ler os limites da escala.")
    # A leitura da escala e da paleta foi validada nos pixels como estão gravados; o giro vem no fim.
    inv = paleta.inverter(rgb, esc)
    return ImagemTermica(
        temperatura_c=orientar(_reduzir(inv.temperatura_c, 2), orientacao),
        radiometrica=False,
        exibida_rgb=orientar(rgb, orientacao),
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
