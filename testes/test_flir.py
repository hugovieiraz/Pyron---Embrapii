"""Testes do leitor radiométrico FLIR.

Os testes principais montam um JPEG FLIR sintético (bloco FFF com imagem bruta e parâmetros),
então não dependem do dataset. O último usa uma imagem real e é pulado se ela não estiver em
``dados/``.
"""

from __future__ import annotations

import io
import math
import struct
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from nucleo import flir

# Constantes da FLIR C5 lidas de uma imagem real.
PLANCK = dict(r1=16683.015625, r2=0.019716521725058556, b=1430.300048828125, f=1.0, o=-2099.0)


def _parametros(**extra) -> flir.ParametrosCamera:
    base = dict(
        emissividade=0.95,
        distancia_m=10.0,
        temp_refletida_c=20.0,
        temp_atmosfera_c=20.0,
        temp_janela_c=20.0,
        transmissao_janela=1.0,
        umidade_relativa=0.5,
        planck_r1=PLANCK["r1"],
        planck_r2=PLANCK["r2"],
        planck_b=PLANCK["b"],
        planck_f=PLANCK["f"],
        planck_o=PLANCK["o"],
        atm_alpha1=5.4052069486942855e-08,
        atm_alpha2=7.026450930425199e-06,
        atm_beta1=0.0026142739225178957,
        atm_beta2=0.003576884977519512,
        atm_x=0.9999899864196777,
        faixa_camera_min_c=-20.0,
        faixa_camera_max_c=150.0,
        modelo="FLIR C5",
    )
    base.update(extra)
    return flir.ParametrosCamera(**base)


def _bruto_de(temp_c: np.ndarray, p: flir.ParametrosCamera) -> np.ndarray:
    """Inverso numérico de bruto_para_temperatura, por busca numa grade de valores brutos."""
    grade = np.arange(0, 65535, dtype=np.float64)
    t = flir.bruto_para_temperatura(grade, p).astype(np.float64)
    ok = np.isfinite(t)
    return np.interp(temp_c, t[ok], grade[ok]).round().astype(np.uint16)


def _jpeg_flir(bruto: np.ndarray, p: flir.ParametrosCamera, png: bool) -> bytes:
    """Monta um JPEG com o bloco FFF dividido em dois segmentos APP1, como a câmera faz."""
    h, w = bruto.shape
    # Registro RawData
    if png:
        buf = io.BytesIO()
        Image.fromarray(bruto.byteswap().astype(np.uint16)).save(buf, format="PNG")
        corpo = buf.getvalue()
    else:
        corpo = bruto.astype("<u2").tobytes()
    raw = struct.pack("<HHH", 2, w, h) + b"\x00" * (0x20 - 6) + corpo
    # Registro CameraInfo
    cam = bytearray(0x340)
    struct.pack_into("<H", cam, 0, 2)
    k = flir.KELVIN
    for pos, val in (
        (0x20, p.emissividade), (0x24, p.distancia_m), (0x28, p.temp_refletida_c + k), (0x2C, p.temp_atmosfera_c + k),
        (0x30, p.temp_janela_c + k), (0x34, p.transmissao_janela), (0x3C, p.umidade_relativa), (0x58, p.planck_r1),
        (0x5C, p.planck_b), (0x60, p.planck_f), (0x70, p.atm_alpha1), (0x74, p.atm_alpha2), (0x78, p.atm_beta1),
        (0x7C, p.atm_beta2), (0x80, p.atm_x), (0x90, p.faixa_camera_max_c + k), (0x94, p.faixa_camera_min_c + k),
        (0x30C, p.planck_r2),
    ):
        struct.pack_into("<f", cam, pos, val)
    struct.pack_into("<i", cam, 0x308, int(p.planck_o))
    cam[0xD4 : 0xD4 + len(p.modelo)] = p.modelo.encode()
    # Bloco FFF: cabeçalho (big-endian, versão 100), diretório e registros
    registros = [(flir.REG_RAW, raw), (flir.REG_CAMERA, bytes(cam))]
    cab = 0x40
    dir_ini = cab
    dados_ini = dir_ini + 32 * len(registros)
    fff = bytearray(b"FFF\x00" + b"teste".ljust(16, b"\x00"))
    fff += struct.pack(">III", 100, dir_ini, len(registros))
    fff += b"\x00" * (cab - len(fff))
    corpos = b""
    for tipo, conteudo in registros:
        fff += struct.pack(">HHIIII", tipo, 0, 100, 1, dados_ini + len(corpos), len(conteudo)) + b"\x00" * 12
        corpos += conteudo
    fff += corpos
    # JPEG mínimo: imagem colorida qualquer + segmentos APP1 FLIR inseridos após o SOI
    base = io.BytesIO()
    Image.new("RGB", (w, h), (0, 0, 128)).save(base, format="JPEG")
    jpg = base.getvalue()
    metade = len(fff) // 2
    segmentos = b""
    for i, parte in enumerate((fff[:metade], fff[metade:])):
        carga = b"FLIR\x00\x01" + bytes([i, 1]) + parte
        segmentos += b"\xff\xe1" + struct.pack(">H", len(carga) + 2) + carga
    return jpg[:2] + segmentos + jpg[2:]


@pytest.mark.parametrize("png", [False, True])
def test_le_jpeg_sintetico_e_recupera_temperatura(tmp_path: Path, png: bool) -> None:
    p = _parametros()
    yy, xx = np.mgrid[0:12, 0:16]
    temperatura = (10 + 3 * xx + 0.5 * yy).astype(np.float64)  # 10 a 60,5 °C
    bruto = _bruto_de(temperatura, p)
    arq = tmp_path / "sintetico.jpg"
    arq.write_bytes(_jpeg_flir(bruto, p, png))

    termo = flir.ler(arq)
    assert termo.bruto.shape == (12, 16)
    assert np.array_equal(termo.bruto, bruto)
    assert termo.parametros.modelo == "FLIR C5"
    assert termo.parametros.emissividade == pytest.approx(0.95, abs=1e-6)
    assert np.abs(termo.temperatura_c - temperatura).max() < 0.05


def test_ajuste_de_emissividade_muda_a_temperatura(tmp_path: Path) -> None:
    p = _parametros()
    bruto = _bruto_de(np.full((4, 4), 60.0), p)
    arq = tmp_path / "e.jpg"
    arq.write_bytes(_jpeg_flir(bruto, p, png=False))
    t95 = float(flir.ler(arq).temperatura_c.mean())
    t80 = float(flir.ler(arq, emissividade=0.80).temperatura_c.mean())
    # Emissividade menor: o mesmo sinal vem de um objeto mais quente.
    assert t80 > t95 + 3


def test_temperatura_igual_ao_ambiente_nao_depende_da_emissividade() -> None:
    # Objeto na mesma temperatura do entorno: emissividade não muda o resultado.
    p = _parametros()
    bruto = _bruto_de(np.array([20.0]), p)
    for e in (0.5, 0.8, 0.95):
        t = flir.bruto_para_temperatura(bruto.astype(np.float64), _parametros(emissividade=e))
        assert math.isclose(float(t[0]), 20.0, abs_tol=0.1)


def test_jpeg_sem_dados_flir_da_erro(tmp_path: Path) -> None:
    arq = tmp_path / "comum.jpg"
    Image.new("RGB", (8, 8)).save(arq)
    with pytest.raises(ValueError):
        flir.ler(arq)


IMAGEM_REAL = next(iter(Path(__file__).resolve().parents[1].glob("dados/sciencedb_10185/**/FLIR0150.jpg")), None)


@pytest.mark.skipif(IMAGEM_REAL is None, reason="dataset não baixado")
def test_imagem_real_bate_com_a_camera() -> None:
    termo = flir.ler(IMAGEM_REAL)
    assert termo.parametros.modelo == "FLIR C5"
    assert termo.temperatura_c.shape == (120, 160)
    # A câmera exibe 51,7 °C de máxima e −0,6 °C de mínima no retângulo de medição.
    caixa = termo.temperatura_c[48:71, 64:96]
    assert abs(float(caixa.max()) - 51.7) < 1.0
    assert abs(float(caixa.min()) - (-0.6)) < 1.0
