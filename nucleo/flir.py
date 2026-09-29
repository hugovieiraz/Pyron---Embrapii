"""Leitura de termogramas radiométricos FLIR (JPEG com bloco FFF embutido).

As câmeras FLIR gravam, dentro do JPEG colorido, um bloco no formato FFF espalhado por
segmentos APP1 que começam com ``FLIR\\0``. Esse bloco tem, entre outros registros, a imagem
bruta do sensor (``RawData``) e os parâmetros da câmera (``CameraInfo``): constantes de Planck,
emissividade, distância, temperaturas refletida e atmosférica, umidade e transmissão da janela.

A conversão de valor bruto para temperatura segue a mesma formulação usada pelo exiftool e
pelo pacote R Thermimage (Tattersall, 2017).
"""

from __future__ import annotations

import io
import math
import struct
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from PIL import Image

KELVIN = 273.15

# Tipos de registro do diretório FFF que usamos.
REG_RAW = 0x01
REG_VISIVEL = 0x0E
REG_CAMERA = 0x20
REG_PALETA = 0x21


@dataclass(frozen=True)
class ParametrosCamera:
    """Parâmetros de medição e calibração gravados pela câmera."""

    emissividade: float
    distancia_m: float
    temp_refletida_c: float
    temp_atmosfera_c: float
    temp_janela_c: float
    transmissao_janela: float
    umidade_relativa: float  # fração, 0 a 1
    planck_r1: float
    planck_r2: float
    planck_b: float
    planck_f: float
    planck_o: float
    atm_alpha1: float
    atm_alpha2: float
    atm_beta1: float
    atm_beta2: float
    atm_x: float
    faixa_camera_min_c: float
    faixa_camera_max_c: float
    modelo: str


@dataclass(frozen=True)
class Termograma:
    """Imagem térmica com a temperatura de cada pixel e a origem dos dados."""

    temperatura_c: np.ndarray  # float32, altura x largura
    bruto: np.ndarray  # uint16, valores do sensor
    parametros: ParametrosCamera
    arquivo: str


def _pedacos_fff(dados: bytes) -> bytes:
    """Junta, na ordem, os pedaços do bloco FFF guardados nos segmentos APP1 ``FLIR``."""
    if dados[:2] != b"\xff\xd8":
        raise ValueError("o arquivo não é um JPEG")
    i = 2
    pedacos: dict[int, bytes] = {}
    while i + 4 <= len(dados) and dados[i] == 0xFF:
        marcador = dados[i + 1]
        if marcador == 0xDA:  # início dos dados comprimidos: não há mais cabeçalhos
            break
        (tamanho,) = struct.unpack(">H", dados[i + 2 : i + 4])
        carga = dados[i + 4 : i + 2 + tamanho]
        if marcador == 0xE1 and carga[:5] == b"FLIR\x00":
            pedacos[carga[6]] = carga[8:]
        i += 2 + tamanho
    if not pedacos:
        raise ValueError("o JPEG não tem dados radiométricos FLIR")
    return b"".join(pedacos[k] for k in sorted(pedacos))


def _registros(fff: bytes) -> dict[int, bytes]:
    """Lê o diretório do bloco FFF e devolve o conteúdo de cada tipo de registro."""
    if fff[:4] not in (b"FFF\x00", b"AFF\x00"):
        raise ValueError("bloco FFF inválido")
    versao = struct.unpack(">I", fff[0x14:0x18])[0]
    ordem = ">" if 100 <= versao < 200 else "<"
    inicio, quantidade = struct.unpack(ordem + "II", fff[0x18:0x20])
    registros: dict[int, bytes] = {}
    for k in range(quantidade):
        entrada = fff[inicio + 32 * k : inicio + 32 * (k + 1)]
        tipo, _sub, _ver, _id, deslocamento, tamanho = struct.unpack(ordem + "HHIIII", entrada[:20])
        if tipo and tipo not in registros:
            registros[tipo] = fff[deslocamento : deslocamento + tamanho]
    return registros


def _ordem(registro: bytes) -> str:
    """A primeira palavra de cada registro vale 2; ela indica a ordem dos bytes."""
    return "<" if struct.unpack("<H", registro[:2])[0] == 2 else ">"


def _parametros(reg: bytes) -> ParametrosCamera:
    o = _ordem(reg)

    def f(pos: int) -> float:
        return struct.unpack(o + "f", reg[pos : pos + 4])[0]

    umidade = f(0x3C)
    if umidade > 2:  # algumas câmeras gravam em porcentagem
        umidade /= 100.0
    modelo = reg[0xD4 : 0xD4 + 32].split(b"\x00", 1)[0].decode("latin-1")
    return ParametrosCamera(
        emissividade=f(0x20),
        distancia_m=f(0x24),
        temp_refletida_c=f(0x28) - KELVIN,
        temp_atmosfera_c=f(0x2C) - KELVIN,
        temp_janela_c=f(0x30) - KELVIN,
        transmissao_janela=f(0x34),
        umidade_relativa=umidade,
        planck_r1=f(0x58),
        planck_b=f(0x5C),
        planck_f=f(0x60),
        atm_alpha1=f(0x70),
        atm_alpha2=f(0x74),
        atm_beta1=f(0x78),
        atm_beta2=f(0x7C),
        atm_x=f(0x80),
        faixa_camera_max_c=f(0x90) - KELVIN,
        faixa_camera_min_c=f(0x94) - KELVIN,
        planck_o=float(struct.unpack(o + "i", reg[0x308:0x30C])[0]),
        planck_r2=f(0x30C),
        modelo=modelo,
    )


def _bruto(reg: bytes) -> np.ndarray:
    o = _ordem(reg)
    largura, altura = struct.unpack(o + "HH", reg[2:6])
    corpo = reg[0x20:]
    if corpo[:8] == b"\x89PNG\r\n\x1a\n":
        # A FLIR grava o PNG de 16 bits com os bytes na ordem inversa da norma PNG.
        img = np.array(Image.open(io.BytesIO(corpo)), dtype=np.uint16)
        return img.byteswap()
    return np.frombuffer(corpo[: largura * altura * 2], dtype=o + "u2").reshape(altura, largura).astype(np.uint16)


def bruto_para_temperatura(bruto: np.ndarray, p: ParametrosCamera) -> np.ndarray:
    """Converte o valor bruto do sensor em temperatura (°C) do objeto.

    Desconta a radiação refletida, a da atmosfera e a da janela, e corrige pela emissividade
    e pela transmissão atmosférica (modelo de dois termos da FLIR).
    """
    e = p.emissividade
    t_atm = p.temp_atmosfera_c
    h2o = p.umidade_relativa * math.exp(
        1.5587 + 0.06939 * t_atm - 0.00027816 * t_atm**2 + 0.00000068455 * t_atm**3
    )
    meia = math.sqrt(p.distancia_m / 2.0)

    def tau(d: float) -> float:
        return p.atm_x * math.exp(-d * (p.atm_alpha1 + p.atm_beta1 * math.sqrt(h2o))) + (1 - p.atm_x) * math.exp(
            -d * (p.atm_alpha2 + p.atm_beta2 * math.sqrt(h2o))
        )

    tau1 = tau(meia)
    tau2 = tau(meia)
    irt = p.transmissao_janela
    emis_janela = 1.0 - irt

    def radiancia(t_c: float) -> float:
        return p.planck_r1 / (p.planck_r2 * (math.exp(p.planck_b / (t_c + KELVIN)) - p.planck_f)) - p.planck_o

    r_refl = radiancia(p.temp_refletida_c)
    r_atm = radiancia(t_atm)
    r_jan = radiancia(p.temp_janela_c)

    refl1 = (1 - e) / e * r_refl
    atm1 = (1 - tau1) / e / tau1 * r_atm
    jan = emis_janela / e / tau1 / irt * r_jan
    atm2 = (1 - tau2) / e / tau1 / irt / tau2 * r_atm
    # A reflexão na janela é zero porque tratamos a janela como não refletora.
    objeto = bruto.astype(np.float64) / e / tau1 / irt / tau2 - atm1 - atm2 - jan - refl1

    with np.errstate(invalid="ignore", divide="ignore"):
        t = p.planck_b / np.log(p.planck_r1 / (p.planck_r2 * (objeto + p.planck_o)) + p.planck_f) - KELVIN
    return t.astype(np.float32)


def ler(caminho: str | Path, **ajustes: float) -> Termograma:
    """Lê um JPEG radiométrico FLIR.

    ``ajustes`` substitui parâmetros de medição antes da conversão, por exemplo
    ``ler(arq, emissividade=0.9, distancia_m=12)``, como fazem os softwares dos fabricantes.
    """
    return ler_bytes(Path(caminho).read_bytes(), str(caminho), **ajustes)


def ler_bytes(dados: bytes, nome: str = "", **ajustes: float) -> Termograma:
    """Como ``ler``, a partir do conteúdo do arquivo."""
    registros = _registros(_pedacos_fff(dados))
    if REG_RAW not in registros or REG_CAMERA not in registros:
        raise ValueError("faltam os registros de imagem bruta ou de parâmetros da câmera")
    parametros = _parametros(registros[REG_CAMERA])
    if ajustes:
        parametros = replace(parametros, **ajustes)
    bruto = _bruto(registros[REG_RAW])
    return Termograma(
        temperatura_c=bruto_para_temperatura(bruto, parametros),
        bruto=bruto,
        parametros=parametros,
        arquivo=nome,
    )


def foto_visivel(dados: bytes) -> bytes | None:
    """JPEG da câmera visível embutido no arquivo, quando a câmera grava (a C5 grava)."""
    try:
        reg = _registros(_pedacos_fff(dados)).get(REG_VISIVEL)
    except ValueError:
        return None
    if reg is None or reg[0x20:0x22] != b"\xff\xd8":
        return None
    return bytes(reg[0x20:])


def paleta(caminho: str | Path) -> np.ndarray | None:
    """Devolve as cores (RGB, 0 a 255) da paleta gravada pela câmera, do frio para o quente."""
    registros = _registros(_pedacos_fff(Path(caminho).read_bytes()))
    reg = registros.get(REG_PALETA)
    if reg is None:
        return None
    n = reg[0]
    if n < 2 or len(reg) < 0x70 + 3 * n:  # algumas câmeras (a C5, por exemplo) não gravam as cores
        return None
    ycrcb = np.frombuffer(reg[0x70 : 0x70 + 3 * n], dtype=np.uint8).reshape(n, 3).astype(np.float64)
    y, cr, cb = ycrcb[:, 0], ycrcb[:, 1] - 128.0, ycrcb[:, 2] - 128.0
    rgb = np.stack([y + 1.402 * cr, y - 0.344136 * cb - 0.714136 * cr, y + 1.772 * cb], axis=1)
    return np.clip(rgb, 0, 255).astype(np.uint8)
