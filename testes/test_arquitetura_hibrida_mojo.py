"""Testes da Arquitetura Híbrida de Aceleração (Mojo SIMD + C/LAPACK Batch).

Valida:
1. Arquivo de kernels em Mojo com decorators C-ABI.
2. Formato e diagnóstico de estado_acelerador().
3. Resiliência a bloqueios do Windows 11 Smart App Control (SAC) e falhas nativas.
4. Despacho FFI para chamadas nativas mockadas.
5. Exatidão matemática de RANSAC 3D, Monte Carlo DLT Batched e Planck Radiométrico.
6. Calibre rotativo 2D e cosseno em lote.
7. Execução do benchmark híbrido.
8. Endpoints da API FastAPI no servidor (/api/medicao/acelerador*).
"""

from __future__ import annotations

import ctypes
import math
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

import nucleo.aceleradores as ac
from app.servidor import app

CLIENTE = TestClient(app)


def test_kernels_mojo_arquivo_e_declaracoes():
    """Valida a existência e a declaração de símbolos C-ABI em kernels.mojo."""
    caminho = Path("nucleo/aceleradores/kernels.mojo")
    assert caminho.exists(), "kernels.mojo deve existir em nucleo/aceleradores/"
    conteudo = caminho.read_text(encoding="utf-8")

    # Verifica os 4 kernels exportados para a C-ABI
    assert '@export("ransac_plano_3d_mojo", ABI="C")' in conteudo
    assert '@export("calibre_rotativo_2d_mojo", ABI="C")' in conteudo
    assert '@export("planck_raw_para_celsius_mojo", ABI="C")' in conteudo
    assert '@export("cosseno_lote_contexto_mojo", ABI="C")' in conteudo

    # Verifica estruturas essenciais de Mojo
    assert "UnsafePointer" in conteudo
    assert "simdwidthof" in conteudo
    assert "from math import" in conteudo


def test_estado_acelerador_formato_e_chaves():
    """Valida o dicionário retornado por estado_acelerador()."""
    estado = ac.estado_acelerador()

    chaves_esperadas = {
        "arquitetura",
        "backend_ativo",
        "mojo_codigo_fonte",
        "mojo_cli_disponivel",
        "mojo_binario_carregado",
        "motivo_fallback",
        "kernels_disponiveis",
    }
    assert set(estado.keys()) == chaves_esperadas
    assert estado["arquitetura"] == "hibrida"
    assert estado["backend_ativo"] in ("mojo_simd", "c_lapack_batch")
    assert estado["mojo_codigo_fonte"] is True
    assert isinstance(estado["mojo_cli_disponivel"], bool)
    assert isinstance(estado["mojo_binario_carregado"], bool)

    kernels_obrigatorios = [
        "ransac_plano_3d",
        "calibre_rotativo_2d",
        "monte_carlo_homografia_dlt",
        "planck_radiometrico",
        "cosseno_lote_contexto",
    ]
    for k in kernels_obrigatorios:
        assert k in estado["kernels_disponiveis"]


def test_compilar_kernels_mojo_sem_cli(monkeypatch):
    """Garante que a compilação falhe defensivamente com instrução quando Mojo não está no PATH."""
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    res = ac.compilar_kernels_mojo()

    assert res["sucesso"] is False
    assert res["mojo_cli_disponivel"] is False
    assert "modular" in res["comando_sugerido"]


def test_fallback_resiliente_sac_windows_11(monkeypatch, tmp_path):
    """Simula bloqueio do Windows Smart App Control (WinError 4551 / OSError) e valida o fallback seguro."""
    dll_falsa = tmp_path / "kernels_mojo.dll"
    dll_falsa.write_bytes(b"MZ_DUMMY_DLL_HEADER")

    def cdll_bloqueado_sac(caminho):
        raise OSError(4551, "Controle Inteligente de Aplicativos bloqueou este binário não assinado.")

    monkeypatch.setattr(ctypes, "CDLL", cdll_bloqueado_sac)

    # Executa a tentativa de carregamento
    sucesso = ac.carregar_biblioteca_mojo(dll_falsa)

    assert sucesso is False
    estado = ac.estado_acelerador()
    assert estado["backend_ativo"] == "c_lapack_batch"
    assert estado["mojo_binario_carregado"] is False
    assert "SAC" in estado["motivo_fallback"] or "4551" in estado["motivo_fallback"]


def test_despacho_ffi_mojo_simd_mockado(monkeypatch):
    """Simula biblioteca nativa Mojo carregada com sucesso e valida o roteamento pelo Tier 1 FFI."""
    mock_lib = MagicMock()

    # Mock de ransac_plano_3d_mojo
    def mock_ransac(pts, n_pts, normais, origens, k_cand, tol, out_inliers, out_melhor):
        # Simula seleção do primeiro candidato com 500 inliers
        c_inliers = ctypes.cast(ctypes.c_void_p(out_inliers), ctypes.POINTER(ctypes.c_longlong))
        c_inliers[0] = 500
        c_melhor = ctypes.cast(ctypes.c_void_p(out_melhor), ctypes.POINTER(ctypes.c_longlong))
        c_melhor[0] = 0
        return 500

    mock_lib.ransac_plano_3d_mojo = MagicMock(side_effect=mock_ransac)

    # Mock de calibre_rotativo_2d_mojo
    def mock_calibre(pts, m_pts, angs, a_angs, out_areas, out_melhor):
        c_areas = ctypes.cast(ctypes.c_void_p(out_areas), ctypes.POINTER(ctypes.c_double))
        c_areas[0] = 42.0
        c_melhor = ctypes.cast(ctypes.c_void_p(out_melhor), ctypes.POINTER(ctypes.c_longlong))
        c_melhor[0] = 0
        return 42.0

    mock_lib.calibre_rotativo_2d_mojo = MagicMock(side_effect=mock_calibre)

    # Mock de planck_raw_para_celsius_mojo
    def mock_planck(bruto, n_pix, r1, r2, b, f, o, fator_miss, offset_atm, saida):
        c_saida = ctypes.cast(ctypes.c_void_p(saida), ctypes.POINTER(ctypes.c_float))
        n = int(getattr(n_pix, "value", n_pix))
        for i in range(n):
            c_saida[i] = 25.5
        return 0

    mock_lib.planck_raw_para_celsius_mojo = MagicMock(side_effect=mock_planck)

    # Mock de cosseno_lote_contexto_mojo
    def mock_cosseno(q, m, k, d, out_scores, out_melhor):
        c_scores = ctypes.cast(ctypes.c_void_p(out_scores), ctypes.POINTER(ctypes.c_float))
        linhas = int(getattr(k, "value", k))
        for i in range(linhas):
            c_scores[i] = 0.99
        c_melhor = ctypes.cast(ctypes.c_void_p(out_melhor), ctypes.POINTER(ctypes.c_longlong))
        c_melhor[0] = 0
        return 0.99

    mock_lib.cosseno_lote_contexto_mojo = MagicMock(side_effect=mock_cosseno)

    # Injeta a mock lib e ativa Tier 1
    monkeypatch.setattr(ac, "_mojo_lib", mock_lib)
    monkeypatch.setattr(ac, "_mojo_binario_carregado", True)
    monkeypatch.setattr(ac, "_motivo_fallback", None)

    estado = ac.estado_acelerador()
    assert estado["backend_ativo"] == "mojo_simd"
    assert estado["mojo_binario_carregado"] is True

    # 1. RANSAC via FFI
    pts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
    normal, origem, contagem = ac.ransac_plano_3d(pts, iteracoes=10, tolerancia=0.01)
    assert contagem == 500
    mock_lib.ransac_plano_3d_mojo.assert_called_once()

    # 2. Calibre rotativo via FFI
    uv = np.array([[0.0, 0.0], [1.0, 1.0]], dtype=np.float64)
    angs = np.array([0.0, 0.5], dtype=np.float64)
    melhor_ang, menor_area = ac.calibre_rotativo_2d(uv, angs)
    assert menor_area == 42.0
    mock_lib.calibre_rotativo_2d_mojo.assert_called_once()

    # 3. Planck via FFI
    raw = np.array([20000, 20100], dtype=np.uint16)
    temp = ac.planck_raw_para_celsius(raw, 21106.0, 0.0125, 1430.0, 1.0, -7340.0)
    assert temp[0] == pytest.approx(25.5, abs=1e-3)
    mock_lib.planck_raw_para_celsius_mojo.assert_called_once()

    # 4. Cosseno via FFI
    q = np.ones(8, dtype=np.float32) / math.sqrt(8)
    m = np.ones((3, 8), dtype=np.float32) / math.sqrt(8)
    scores = ac.cosseno_lote_contexto(q, m)
    assert scores[0] == pytest.approx(0.99, abs=1e-3)
    mock_lib.cosseno_lote_contexto_mojo.assert_called_once()


def test_ransac_plano_3d_precisao_numerica():
    """Gera um plano conhecido com ruído e valida que a normal ajustada coincide com a teórica."""
    rng = np.random.default_rng(123)
    n_pontos = 5000

    # Plano verdadeiro: 2*x - 3*y + 1*z + 4 = 0  => z = -2*x + 3*y - 4
    # Normal unitária teórica: (2, -3, 1) / sqrt(14)
    x = rng.uniform(-1.0, 1.0, n_pontos)
    y = rng.uniform(-1.0, 1.0, n_pontos)
    z = -2.0 * x + 3.0 * y - 4.0 + rng.normal(0, 0.002, n_pontos)

    # Injeta 15% de outliers espalhados aleatoriamente
    n_outliers = int(0.15 * n_pontos)
    z[:n_outliers] += rng.uniform(-1.0, 1.0, n_outliers)

    amostra = np.stack([x, y, z], axis=1)

    normal_hib, origem_hib, inliers_hib = ac.ransac_plano_3d(amostra, iteracoes=250, tolerancia=0.01, semente=123)

    normal_teorica = np.array([2.0, -3.0, 1.0])
    normal_teorica /= np.linalg.norm(normal_teorica)

    # Alinhamento da normal (independente do sentido)
    alinhamento = abs(float(np.dot(normal_hib, normal_teorica)))
    assert alinhamento > 0.99, f"Normal ajustada {normal_hib} diverge da teórica {normal_teorica}"
    assert inliers_hib > (0.80 * n_pontos)


def test_monte_carlo_homografia_pontos_equivalencia():
    """Garante que a formulação batched SVD em C/LAPACK produz resultados equivalentes ao loop legado."""
    cantos = np.array([[120.0, 80.0], [480.0, 95.0], [510.0, 390.0], [105.0, 370.0]])
    real = np.array([[0.0, 0.0], [29.7, 0.0], [29.7, 21.0], [0.0, 21.0]])
    pontos = np.array([[200.0, 200.0], [400.0, 300.0]])

    sorteios = 200
    semente = 42

    dist_legada = ac._monte_carlo_homografia_legado(
        cantos=cantos,
        real=real,
        pontos=pontos,
        sorteios=sorteios,
        erro_px=1.0,
        semente=semente,
    )

    dist_hibrida = ac.monte_carlo_homografia_pontos(
        cantos_ordenados=cantos,
        real=real,
        pontos=pontos,
        sorteios=sorteios,
        erro_px=1.0,
        semente=semente,
    )

    assert dist_hibrida.shape == (sorteios,)
    # Médias e percentis (incerteza de meia-faixa) devem ser idênticos
    assert np.mean(dist_hibrida) == pytest.approx(np.mean(dist_legada), abs=1e-3)
    assert np.median(dist_hibrida) == pytest.approx(np.median(dist_legada), abs=1e-3)

    lo_leg, hi_leg = np.percentile(dist_legada, [2.5, 97.5])
    lo_hib, hi_hib = np.percentile(dist_hibrida, [2.5, 97.5])
    assert (hi_hib - lo_hib) == pytest.approx(hi_leg - lo_leg, abs=1e-3)


def test_planck_raw_para_celsius_exatidao():
    """Valida a conversão radiométrica de Planck contra a temperatura teórica esperada."""
    # Parâmetros reais FLIR
    r1 = 21106.77
    r2 = 0.01254
    b = 1430.0
    f = 1.0
    o = -7340.0

    # Temperatura teórica de 35 °C
    temp_celsius_esperada = 35.0
    temp_k = temp_celsius_esperada + 273.15
    # Radiação inversa de Planck
    s_obj = (r1 / (r2 * (math.exp(b / temp_k) - f))) - o
    raw_sintetico = np.array([round(s_obj)], dtype=np.uint16)

    temperatura_calculada = ac.planck_raw_para_celsius(raw_sintetico, r1, r2, b, f, o)

    assert temperatura_calculada[0] == pytest.approx(temp_celsius_esperada, abs=0.05)


def test_calibre_rotativo_2d_retangulo():
    """Valida a busca do retângulo mínimo em 2D."""
    # Retângulo 10.0 x 4.0 alinhado aos eixos
    pontos = np.array([
        [-5.0, -2.0],
        [5.0, -2.0],
        [5.0, 2.0],
        [-5.0, 2.0],
    ], dtype=np.float64)

    angulos = np.linspace(0, math.pi / 2, 45, endpoint=False)
    melhor_ang, menor_area = ac.calibre_rotativo_2d(pontos, angulos)

    assert melhor_ang == pytest.approx(0.0, abs=1e-3)
    assert menor_area == pytest.approx(40.0, abs=1e-3)


def test_cosseno_lote_contexto():
    """Valida o cálculo do produto escalar em lote para vetores unitários."""
    d = 32
    rng = np.random.default_rng(99)
    matriz = rng.normal(0, 1, size=(10, d)).astype(np.float32)
    matriz /= np.linalg.norm(matriz, axis=1, keepdims=True)

    # Consulta exatamente igual à linha 4
    consulta = matriz[4].copy()

    scores = ac.cosseno_lote_contexto(consulta, matriz)
    assert scores.shape == (10,)
    assert scores[4] == pytest.approx(1.0, abs=1e-5)
    assert np.argmax(scores) == 4


def test_benchmark_hibrido_estrutura_e_performance():
    """Valida a execução e o speedup do benchmark híbrido."""
    res = ac.benchmark_hibrido(n_pontos=2000, iteracoes_ransac=50, sorteios_mc=100)

    chaves_esperadas = {
        "ransac_legado_ms",
        "ransac_hibrido_ms",
        "ransac_speedup_x",
        "monte_carlo_legado_ms",
        "monte_carlo_hibrido_ms",
        "monte_carlo_speedup_x",
        "backend_ativo",
    }
    assert set(res.keys()) == chaves_esperadas
    assert res["ransac_hibrido_ms"] > 0
    assert res["monte_carlo_hibrido_ms"] > 0
    assert res["monte_carlo_speedup_x"] > 1.0  # Homografia DLT batched deve superar o loop sequencial


def test_rotas_api_acelerador():
    """Testa os endpoints HTTP expostos em app/servidor.py."""
    # 1. GET /api/medicao/acelerador
    resp = CLIENTE.get("/api/medicao/acelerador")
    assert resp.status_code == 200
    dados = resp.json()
    assert dados["arquitetura"] == "hibrida"
    assert "backend_ativo" in dados

    # 2. POST /api/medicao/acelerador/benchmark
    resp_bench = CLIENTE.post("/api/medicao/acelerador/benchmark")
    assert resp_bench.status_code == 200
    dados_bench = resp_bench.json()
    assert "ransac_speedup_x" in dados_bench
    assert "monte_carlo_speedup_x" in dados_bench

    # 3. GET /api/medicao/estado deve conter o objeto "acelerador"
    resp_estado = CLIENTE.get("/api/medicao/estado")
    assert resp_estado.status_code == 200
    dados_estado = resp_estado.json()
    assert "acelerador" in dados_estado
    assert dados_estado["acelerador"]["arquitetura"] == "hibrida"
