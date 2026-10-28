"""Entrada única de imagens térmicas.

Aceita um JPEG radiométrico FLIR (temperatura medida) ou uma imagem colorida com a barra de
escala visível (temperatura estimada pela paleta). O resto do sistema recebe sempre o mesmo
objeto, com a matriz de temperatura e a indicação de como ela foi obtida.

Quando não há como chegar à temperatura (sem dados radiométricos e sem escala legível), a imagem
entra assim mesmo, com a matriz vazia (NaN): os componentes ainda podem ser identificados pela
imagem colorida, e a escala pode ser informada depois.
"""

from __future__ import annotations

import hashlib
import io
import warnings
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from nucleo import barra as barra_livre
from nucleo import flir, paleta

FATOR_ESTIMADA = 2  # a matriz estimada tem metade da resolução da imagem exibida


class OCRPreguicoso:
    """Leitor de texto carregado só na primeira imagem sem dados radiométricos (leva alguns segundos).

    A detecção de texto vai até 320 pixels, como no ao vivo (o padrão do RapidOCR amplia cada recorte para
    736 e leva o dobro): nas 19 imagens estimadas de ``app/dados_app`` a temperatura saiu idêntica, com a
    leitura caindo de ~1,4 s para ~0,9 s. Recorte igual ao de uma imagem anterior (câmera fixa com a escala
    travada, o mesmo rótulo de novo) devolve a leitura guardada sem rodar o OCR.
    """

    GUARDAR = 64  # leituras de recortes guardadas (cada rótulo de escala é um recorte pequeno)

    def __init__(self):
        self._ocr = None
        self._lidos: dict[tuple, object] = {}

    def __call__(self, imagem, **opcoes):
        imagem = np.ascontiguousarray(imagem)
        chave = (imagem.shape, hashlib.blake2b(imagem.tobytes(), digest_size=16).digest(), tuple(sorted(opcoes.items())))
        if chave in self._lidos:
            return self._lidos[chave]
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR

            self._ocr = RapidOCR(det_limit_side_len=320, det_limit_type="max")
        resultado = self._ocr(imagem, **opcoes)
        if len(self._lidos) >= self.GUARDAR:
            self._lidos.pop(next(iter(self._lidos)))
        self._lidos[chave] = resultado
        return resultado


@dataclass
class ImagemTermica:
    temperatura_c: np.ndarray  # float32; NaN onde não há medida (textos e ícones, na estimada)
    radiometrica: bool
    exibida_rgb: np.ndarray  # a imagem colorida como a câmera gravou
    foto_visivel: bytes | None
    metadados: dict = field(default_factory=dict)

    @property
    def tem_temperatura(self) -> bool:
        return bool(np.isfinite(self.temperatura_c).any())

    @property
    def origem(self) -> str:
        if self.radiometrica:
            return "medida (radiométrica)"
        return "estimada pela paleta de cores" if self.tem_temperatura else "sem temperatura"


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


def exibida(dados: bytes) -> np.ndarray:
    """A imagem colorida como foi gravada, já no sentido da marca EXIF (fundo das imagens sem temperatura)."""
    img = Image.open(io.BytesIO(dados))
    return orientar(np.array(img.convert("RGB")), int(img.getexif().get(274, 1) or 1))


def _reduzir(mapa: np.ndarray, fator: int) -> np.ndarray:
    h, w = mapa.shape[0] // fator, mapa.shape[1] // fator
    blocos = mapa[: h * fator, : w * fator].reshape(h, fator, w, fator).transpose(0, 2, 1, 3).reshape(h, w, -1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(blocos, axis=2).astype(np.float32)


AVISO_CELULAR = ("Foto da câmera do celular sem a barra de cores no quadro: o Pyron identifica os componentes, mas "
                 "sem a barra não há como estimar a temperatura. Enquadre a barra junto ou use o arquivo original da câmera.")
AVISO_CELULAR_SEM_NUMEROS = ("Foto da câmera do celular: achei a barra de cores, mas não consegui ler os números da "
                             "escala. Informe o mínimo e o máximo da escala para estimar a temperatura.")
AVISO_ESTIMADA = ("Temperatura estimada pelas cores. Erro típico de 0,5 °C na mediana; "
                  "acima do topo da escala a temperatura real não pode ser recuperada.")
AVISO_ESTIMADA_FOTO = ("Temperatura estimada pelas cores da barra, numa foto da imagem térmica. Em testes com termogramas "
                       "filmados na tela, o erro ficou em 0,5 °C na mediana e até 1,3 °C em 9 de 10 peças; reflexo, "
                       "brilho da tela e moiré pioram. Acima do topo da escala a temperatura real não pode ser recuperada.")


def carregar(dados: bytes, ocr=None, limites: tuple[float, float] | None = None, ajustes: dict | None = None,
             somente_imagem: bool = False) -> ImagemTermica:
    """Abre a imagem e devolve a temperatura de cada pixel.

    ``somente_imagem`` (câmera do celular) não procura dados radiométricos nem o leiaute fixo da FLIR:
    a temperatura, se houver, vem da barra de cores achada em qualquer lugar da foto, com as cores dela
    medidas na própria foto (``nucleo.barra``).

    ``ocr`` só é usado quando a imagem não é radiométrica (para ler os limites da escala).
    ``limites`` (mínimo, máximo) já conhecidos da escala dispensam o OCR, como num quadro de vídeo.
    ``ajustes`` troca parâmetros de medição do termograma radiométrico (emissividade, distância,
    temperaturas refletida e atmosférica, umidade) antes da conversão, como os softwares das câmeras.
    """
    try:
        img = Image.open(io.BytesIO(dados))
        img.load()
    except OSError as erro:
        raise ValueError("Não consegui abrir o arquivo como imagem. Envie um JPEG, PNG ou WebP.") from erro
    rgb = np.array(img.convert("RGB"))
    data = _data_exif(img)
    modelo_exif = str(img.getexif().get(272, "") or "")
    orientacao = int(img.getexif().get(274, 1) or 1)
    if somente_imagem:
        livre = _pela_barra_livre(rgb, ocr, limites, data, modelo_exif, orientacao, foto=True)
        return livre or _sem_temperatura(rgb, data, modelo_exif, orientacao, barra=False, aviso=AVISO_CELULAR)

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

    t_min, t_max = limites if limites else (None, None)
    try:
        esc = paleta.escala(rgb, ocr, t_max=t_max, t_min=t_min)
    except ValueError:
        # Fora do leiaute da FLIR C5 (outra câmera, captura de tela, foto da tela): a barra em qualquer lugar.
        livre = _pela_barra_livre(rgb, ocr, limites, data, modelo_exif, orientacao, foto=False)
        if livre is not None:
            return livre
        if limites:
            raise ValueError("Não encontrei a barra de cores nesta imagem; sem ela, as cores não viram temperatura.") from None
        return _sem_temperatura(rgb, data, modelo_exif, orientacao, barra=False)
    if esc.t_max is None or esc.t_min is None:
        livre = _pela_barra_livre(rgb, ocr, None, data, modelo_exif, orientacao, foto=False, so_lida=True)
        return livre or _sem_temperatura(rgb, data, modelo_exif, orientacao, barra=True, lidos=(esc.t_min, esc.t_max))
    if esc.t_max <= esc.t_min:
        raise ValueError("Escala inválida: o máximo precisa ser maior que o mínimo.")
    # A leitura da escala e da paleta foi validada nos pixels como estão gravados; o giro vem no fim.
    inv = paleta.inverter(rgb, esc)
    return ImagemTermica(
        temperatura_c=orientar(_reduzir(inv.temperatura_c, FATOR_ESTIMADA), orientacao),
        radiometrica=False,
        exibida_rgb=orientar(rgb, orientacao),
        foto_visivel=None,
        metadados={
            "camera": modelo_exif or "desconhecida",
            "data_hora": data,
            "escala_lida_c": [esc.t_min, esc.t_max],
            **({"escala_informada": True} if limites else {}),
            "pixels_saturados": round(float(inv.saturado.mean()), 3),
            "aviso": AVISO_ESTIMADA,
        },
    )


def _pela_barra_livre(rgb: np.ndarray, ocr, limites, data: str, modelo_exif: str, orientacao: int, foto: bool,
                      so_lida: bool = False) -> ImagemTermica | None:
    """Temperatura pela barra achada em qualquer lugar da imagem (``nucleo.barra``), ou None sem barra.

    Achou a barra mas não leu os números: imagem sem temperatura que pede a escala (ou None com
    ``so_lida``, para quem chamou decidir).
    """
    achada = barra_livre.achar(rgb)
    if achada is None:
        return None
    if limites:
        escala = barra_livre.escala_informada(achada, limites[0], limites[1])
    else:
        lidos = barra_livre.ler_numeros(rgb, achada, ocr) if ocr is not None else (None, None)
        escala = barra_livre.montar_escala(achada, *lidos)
    if escala is None:
        if so_lida:
            return None
        return _sem_temperatura(rgb, data, modelo_exif, orientacao, barra=True,
                                aviso=AVISO_CELULAR_SEM_NUMEROS if foto else None)
    img_lab = barra_livre.lab(rgb)
    temp, quente, _ = barra_livre.temperaturas(img_lab, escala)
    fora = barra_livre.mascara_sobreposicao(achada, rgb.shape) | paleta.mascara_estruturas_finas(img_lab)
    temp = np.where(fora, np.nan, temp).astype(np.float32)
    return ImagemTermica(
        temperatura_c=orientar(_reduzir(temp, FATOR_ESTIMADA), orientacao),
        radiometrica=False,
        exibida_rgb=orientar(rgb, orientacao),
        foto_visivel=None,
        metadados={
            "camera": modelo_exif or "desconhecida",
            "data_hora": data,
            "escala_lida_c": [escala.t_min, escala.t_max],
            **({"escala_informada": True} if limites else {}),
            "barra_livre": True,
            "pixels_saturados": round(float((quente & ~fora).mean()), 3),
            "aviso": AVISO_ESTIMADA_FOTO if foto else AVISO_ESTIMADA,
        },
    )


def _sem_temperatura(rgb: np.ndarray, data: str, modelo_exif: str, orientacao: int, barra: bool,
                     lidos: tuple[float | None, float | None] = (None, None), aviso: str | None = None) -> ImagemTermica:
    """Imagem sem caminho até a temperatura: segue só com a identificação dos componentes.

    A matriz tem o mesmo tamanho da estimada pela paleta, para que as caixas continuem valendo se
    a escala for informada depois.
    """
    h, w = rgb.shape[0] // FATOR_ESTIMADA, rgb.shape[1] // FATOR_ESTIMADA
    if barra:
        motivo = ("Encontrei a barra de cores, mas não consegui ler os limites da escala. "
                  "Informe o mínimo e o máximo da escala para estimar a temperatura.")
    else:
        motivo = ("A imagem não tem dados radiométricos nem barra de cores com escala. Os componentes foram "
                  "identificados, mas a temperatura só vem do JPEG original da câmera.")
    motivo = aviso or motivo
    return ImagemTermica(
        temperatura_c=orientar(np.full((h, w), np.nan, dtype=np.float32), orientacao),
        radiometrica=False,
        exibida_rgb=orientar(rgb, orientacao),
        foto_visivel=None,
        metadados={
            "camera": modelo_exif or "desconhecida",
            "data_hora": data,
            "sem_temperatura": True,
            "barra_encontrada": barra,
            **({"escala_lida_c": [lidos[0], lidos[1]]} if barra else {}),
            "aviso": motivo,
        },
    )
