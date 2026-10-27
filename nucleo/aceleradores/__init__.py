"""Módulo de Aceleração Híbrida do Pyron.

Arquitetura Híbrida em 3 Camadas:
- Tier 1: Mojo Native SIMD via ctypes/FFI
- Tier 2: C/LAPACK/BLAS Batched Vectorization (NumPy / SciPy C-Runtime)
- Tier 3: Python Sequencial Legado (referência analítica e benchmarks)

Resiliência nativa contra bloqueios do Smart App Control (SAC) do Windows 11
e outros controles de integridade de código através de detecção defensiva e
fallback dinâmico seguro.
"""

from __future__ import annotations

import ctypes
import math
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np

# Diretório base deste pacote e arquivos de código-fonte/binários
DIRETORIO_ATUAL = Path(__file__).resolve().parent
ARQUIVO_MOJO = DIRETORIO_ATUAL / "kernels.mojo"
PASTA_BIN = DIRETORIO_ATUAL / "bin"

# Nomes de biblioteca por sistema operacional
NOME_LIB_MAPA = {
    "Windows": "kernels_mojo.dll",
    "Linux": "libkernels_mojo.so",
    "Darwin": "libkernels_mojo.dylib",
}

# Constantes Radiométricas e de Geometria
KELVIN = 273.15
EPSILON_NORMA = 1e-12
TAMANHO_BLOCO_BLAS = 64

# Estado global da arquitetura de aceleração
_mojo_lib: ctypes.CDLL | None = None
_mojo_binario_carregado: bool = False
_motivo_fallback: str | None = None


def obter_caminho_binario_padrao() -> Path:
    """Retorna o caminho canônico esperado para o binário compilado no SO atual."""
    sistema = platform.system()
    nome_lib = NOME_LIB_MAPA.get(sistema, "kernels_mojo.dll")
    return PASTA_BIN / nome_lib


def carregar_biblioteca_mojo(caminho_customizado: Path | str | None = None) -> bool:
    """Tenta carregar a biblioteca nativa compilada com proteção defensiva ao Windows SAC."""
    global _mojo_lib, _mojo_binario_carregado, _motivo_fallback

    caminho = Path(caminho_customizado) if caminho_customizado else obter_caminho_padrao()
    if not caminho.exists():
        _mojo_lib = None
        _mojo_binario_carregado = False
        _motivo_fallback = (
            f"Binário nativo não encontrado em '{caminho.name}'. "
            "Operando em Tier 2 (C/LAPACK/BLAS Batch)."
        )
        return False

    try:
        # Carregamento via ctypes com tratamento de WinError 4551 (Windows 11 SAC) e OSErrors
        lib = ctypes.CDLL(str(caminho))

        # Configuração de assinaturas das funções exportadas C-ABI
        # 1. ransac_plano_3d_mojo
        if hasattr(lib, "ransac_plano_3d_mojo"):
            lib.ransac_plano_3d_mojo.argtypes = [
                ctypes.c_void_p,  # pontos (Float64*)
                ctypes.c_longlong,  # n_pontos
                ctypes.c_void_p,  # normais (Float64*)
                ctypes.c_void_p,  # origens (Float64*)
                ctypes.c_longlong,  # k_candidatos
                ctypes.c_double,  # tolerancia
                ctypes.c_void_p,  # out_inliers (Int64*)
                ctypes.c_void_p,  # out_melhor_indice (Int64*)
            ]
            lib.ransac_plano_3d_mojo.restype = ctypes.c_longlong

        # 2. calibre_rotativo_2d_mojo
        if hasattr(lib, "calibre_rotativo_2d_mojo"):
            lib.calibre_rotativo_2d_mojo.argtypes = [
                ctypes.c_void_p,  # pontos_uv (Float64*)
                ctypes.c_longlong,  # m_pontos
                ctypes.c_void_p,  # angulos (Float64*)
                ctypes.c_longlong,  # a_angulos
                ctypes.c_void_p,  # out_areas (Float64*)
                ctypes.c_void_p,  # out_melhor_indice (Int64*)
            ]
            lib.calibre_rotativo_2d_mojo.restype = ctypes.c_double

        # 3. planck_raw_para_celsius_mojo
        if hasattr(lib, "planck_raw_para_celsius_mojo"):
            lib.planck_raw_para_celsius_mojo.argtypes = [
                ctypes.c_void_p,  # bruto (UInt16*)
                ctypes.c_longlong,  # n_pixels
                ctypes.c_float,  # r1
                ctypes.c_float,  # r2
                ctypes.c_float,  # b
                ctypes.c_float,  # f
                ctypes.c_float,  # o
                ctypes.c_float,  # fator_miss
                ctypes.c_float,  # offset_atm
                ctypes.c_void_p,  # saida_celsius (Float32*)
            ]
            lib.planck_raw_para_celsius_mojo.restype = ctypes.c_int

        # 4. cosseno_lote_contexto_mojo
        if hasattr(lib, "cosseno_lote_contexto_mojo"):
            lib.cosseno_lote_contexto_mojo.argtypes = [
                ctypes.c_void_p,  # vetor_consulta (Float32*)
                ctypes.c_void_p,  # matriz_pesos (Float32*)
                ctypes.c_longlong,  # k_linhas
                ctypes.c_longlong,  # d_dimensoes
                ctypes.c_void_p,  # out_scores (Float32*)
                ctypes.c_void_p,  # out_melhor_indice (Int64*)
            ]
            lib.cosseno_lote_contexto_mojo.restype = ctypes.c_float

        _mojo_lib = lib
        _mojo_binario_carregado = True
        _motivo_fallback = None
        return True

    except OSError as erro:
        _mojo_lib = None
        _mojo_binario_carregado = False
        _motivo_fallback = (
            f"Bloqueio de segurança (Windows SAC/Antivírus) ou falha ao carregar DLL nativa: {erro}. "
            "Operando em Tier 2 (C/LAPACK/BLAS Batch)."
        )
        return False
    except Exception as erro:
        _mojo_lib = None
        _mojo_binario_carregado = False
        _motivo_fallback = f"Erro inesperado na inicialização FFI Mojo: {erro}"
        return False


def obter_caminho_padrao() -> Path:
    """Alias para obter_caminho_binario_padrao."""
    return obter_caminho_binario_padrao()


# Tentativa automática de inicialização segura no import
carregar_biblioteca_mojo()


def compilar_kernels_mojo(destino: Path | None = None) -> dict[str, Any]:
    """Compila kernels.mojo para biblioteca compartilhada se o CLI mojo estiver disponível."""
    mojo_bin = shutil.which("mojo")
    destino_final = destino or obter_caminho_binario_padrao()
    destino_final.parent.mkdir(parents=True, exist_ok=True)

    if not mojo_bin:
        return {
            "sucesso": False,
            "mojo_cli_disponivel": False,
            "mensagem": "Compilador Mojo não encontrado no PATH do sistema.",
            "comando_sugerido": (
                "pixi global install modular && "
                f"mojo build --emit shared-lib {ARQUIVO_MOJO} -o {destino_final}"
            ),
            "destino_esperado": str(destino_final),
        }

    try:
        resultado = subprocess.run(
            [mojo_bin, "build", "--emit", "shared-lib", str(ARQUIVO_MOJO), "-o", str(destino_final)],
            capture_output=True,
            text=True,
            check=False,
        )
        if resultado.returncode == 0:
            carregado = carregar_biblioteca_mojo(destino_final)
            return {
                "sucesso": True,
                "mojo_cli_disponivel": True,
                "mensagem": "Kernels Mojo compilados com sucesso.",
                "destino": str(destino_final),
                "binario_carregado": carregado,
            }
        return {
            "sucesso": False,
            "mojo_cli_disponivel": True,
            "mensagem": f"Erro na compilação do Mojo: {resultado.stderr}",
            "codigo_saida": resultado.returncode,
        }
    except Exception as erro:
        return {
            "sucesso": False,
            "mojo_cli_disponivel": True,
            "mensagem": f"Falha na execução do processo de compilação: {erro}",
        }


def estado_acelerador() -> dict[str, Any]:
    """Retorna o estado e diagnóstico do subsistema de aceleração híbrida."""
    backend_ativo = "mojo_simd" if _mojo_binario_carregado else "c_lapack_batch"
    mojo_cli = shutil.which("mojo") is not None
    return {
        "arquitetura": "hibrida",
        "backend_ativo": backend_ativo,
        "mojo_codigo_fonte": ARQUIVO_MOJO.exists(),
        "mojo_cli_disponivel": mojo_cli,
        "mojo_binario_carregado": _mojo_binario_carregado,
        "motivo_fallback": _motivo_fallback,
        "kernels_disponiveis": [
            "ransac_plano_3d",
            "calibre_rotativo_2d",
            "monte_carlo_homografia_dlt",
            "planck_radiometrico",
            "cosseno_lote_contexto",
        ],
    }


# ---------------------------------------------------------------------------
# Kernels Híbridos de Alta Performance
# ---------------------------------------------------------------------------

def ransac_plano_3d(
    amostra: np.ndarray,
    iteracoes: int = 200,
    tolerancia: float = 0.01,
    semente: int = 0,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Ajusta o melhor plano 3D por RANSAC em lote de alto desempenho.

    Camadas:
    - Tier 1: FFI C-ABI para kernel Mojo SIMD nativo se carregado.
    - Tier 2: Avaliação vetorizada em C/BLAS GEMM por blocos para máxima
      eficiência em cache L2/L3.

    Retorna: (melhor_normal, melhor_origem, melhor_contagem_inliers).
    """
    amostra = np.asarray(amostra, dtype=np.float64)
    n_pontos = len(amostra)
    if n_pontos < 3:
        raise ValueError("Amostra deve conter pelo menos 3 pontos 3D.")

    rng = np.random.default_rng(semente)

    # Geração dos triângulos candidatos determinísticos
    tri_indices = np.empty((iteracoes, 3), dtype=np.int64)
    for i in range(iteracoes):
        tri_indices[i] = rng.choice(n_pontos, 3, replace=False)

    tri = amostra[tri_indices]  # (iteracoes, 3, 3)
    v1 = tri[:, 1] - tri[:, 0]
    v2 = tri[:, 2] - tri[:, 0]
    normais = np.cross(v1, v2)
    origens = tri[:, 0]

    normas = np.linalg.norm(normais, axis=1, keepdims=True)
    validos = (normas[:, 0] >= EPSILON_NORMA)

    if not np.any(validos):
        # Fallback de segurança se todos forem colineares
        return np.array([0.0, 0.0, 1.0], dtype=np.float64), amostra[0], 0

    normais_val = np.ascontiguousarray(normais[validos] / normas[validos], dtype=np.float64)
    origens_val = np.ascontiguousarray(origens[validos], dtype=np.float64)
    k_candidatos = len(normais_val)

    # Tier 1: Mojo FFI nativo
    if _mojo_binario_carregado and _mojo_lib and hasattr(_mojo_lib, "ransac_plano_3d_mojo"):
        try:
            amostra_contig = np.ascontiguousarray(amostra, dtype=np.float64)
            out_inliers = np.empty(k_candidatos, dtype=np.int64)
            out_melhor_idx = np.zeros(1, dtype=np.int64)

            _mojo_lib.ransac_plano_3d_mojo(
                amostra_contig.ctypes.data,
                ctypes.c_longlong(n_pontos),
                normais_val.ctypes.data,
                origens_val.ctypes.data,
                ctypes.c_longlong(k_candidatos),
                ctypes.c_double(tolerancia),
                out_inliers.ctypes.data,
                out_melhor_idx.ctypes.data,
            )
            melhor_idx = int(out_melhor_idx[0])
            melhor_contagem = int(out_inliers[melhor_idx])
            return normais_val[melhor_idx], origens_val[melhor_idx], melhor_contagem
        except Exception:
            # Fallback transparente para Tier 2 em caso de falha de execução FFI
            pass

    # Tier 2: C/BLAS GEMM em Blocos de Cache L2/L3
    inliers_totais = np.empty(k_candidatos, dtype=np.int32)
    for ini in range(0, k_candidatos, TAMANHO_BLOCO_BLAS):
        fim = min(ini + TAMANHO_BLOCO_BLAS, k_candidatos)
        n_bloco = normais_val[ini:fim]  # (B, 3)
        a_bloco = origens_val[ini:fim]  # (B, 3)

        # Projeção matricial BLAS GEMM: (N, 3) @ (3, B) -> (N, B)
        proj = amostra @ n_bloco.T
        offsets = np.sum(a_bloco * n_bloco, axis=1)  # (B,)
        dist = np.abs(proj - offsets)
        inliers_totais[ini:fim] = np.count_nonzero(dist < tolerancia, axis=0)

    melhor_idx = int(np.argmax(inliers_totais))
    melhor_contagem = int(inliers_totais[melhor_idx])
    return normais_val[melhor_idx], origens_val[melhor_idx], melhor_contagem


def monte_carlo_homografia_pontos(
    cantos_ordenados: np.ndarray,
    real: np.ndarray,
    pontos: np.ndarray,
    sorteios: int = 400,
    erro_px: float = 1.0,
    semente: int = 0,
) -> np.ndarray:
    """Simulação de Monte Carlo para incerteza métrica planar via DLT Batched SVD.

    Em vez de iterar em loops Python individuais, constrói o tensor tridimensional
    do sistema DLT A (S, 8, 9) e resolve todas as decomposições SVD simultaneamente
    via chamadas vetorizadas em C/LAPACK.

    Retorna:
        Array 1D (sorteios,) contendo as distâncias medidas em cada realização.
    """
    c = np.asarray(cantos_ordenados, dtype=np.float64)
    r = np.asarray(real, dtype=np.float64)
    p = np.asarray(pontos, dtype=np.float64)

    rng = np.random.default_rng(semente)
    if erro_px > 0:
        c_pert = np.empty((sorteios, 4, 2), dtype=np.float64)
        p_pert = np.empty((sorteios, 2, 2), dtype=np.float64)
        for s in range(sorteios):
            c_pert[s] = c + rng.normal(0, erro_px, c.shape)
            p_pert[s] = p + rng.normal(0, erro_px, p.shape)
    else:
        c_pert = np.tile(c, (sorteios, 1, 1))
        p_pert = np.tile(p, (sorteios, 1, 1))

    # 1. Normalização Hartley DLT dos cantos perturbados de origem em lote: (S, 4, 2)
    m_c = c_pert.mean(axis=1, keepdims=True)  # (S, 1, 2)
    diff_c = c_pert - m_c
    dist_c = np.linalg.norm(diff_c, axis=2)  # (S, 4)
    mean_dist_c = dist_c.mean(axis=1)  # (S,)
    s_c = math.sqrt(2.0) / np.maximum(mean_dist_c, 1e-12)  # (S,)
    a_norm = diff_c * s_c[:, None, None]  # (S, 4, 2)

    Ta = np.zeros((sorteios, 3, 3), dtype=np.float64)
    Ta[:, 0, 0] = s_c
    Ta[:, 1, 1] = s_c
    Ta[:, 0, 2] = -s_c * m_c[:, 0, 0]
    Ta[:, 1, 2] = -s_c * m_c[:, 0, 1]
    Ta[:, 2, 2] = 1.0

    # 2. Normalização dos cantos reais de destino (constante para todos os sorteios)
    m_r = r.mean(axis=0)
    diff_r = r - m_r
    s_r = math.sqrt(2.0) / max(float(np.mean(np.linalg.norm(diff_r, axis=1))), 1e-12)
    b_norm = diff_r * s_r  # (4, 2)

    Tb = np.array([
        [s_r, 0.0, -s_r * m_r[0]],
        [0.0, s_r, -s_r * m_r[1]],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)
    inv_Tb = np.linalg.inv(Tb)

    # 3. Montagem do tensor DLT 3D A (sorteios, 8, 9) sem loops de sorteio
    A = np.zeros((sorteios, 8, 9), dtype=np.float64)
    for i in range(4):
        x = a_norm[:, i, 0]
        y = a_norm[:, i, 1]
        u = b_norm[i, 0]
        v = b_norm[i, 1]

        # Linha 2*i
        A[:, 2 * i, 0] = -x
        A[:, 2 * i, 1] = -y
        A[:, 2 * i, 2] = -1.0
        A[:, 2 * i, 6] = u * x
        A[:, 2 * i, 7] = u * y
        A[:, 2 * i, 8] = u

        # Linha 2*i + 1
        A[:, 2 * i + 1, 3] = -x
        A[:, 2 * i + 1, 4] = -y
        A[:, 2 * i + 1, 5] = -1.0
        A[:, 2 * i + 1, 6] = v * x
        A[:, 2 * i + 1, 7] = v * y
        A[:, 2 * i + 1, 8] = v

    # 4. Resolução de todas as 400 homografias em 1 chamada C/LAPACK SVD em batch
    _, _, vt = np.linalg.svd(A)
    H_norm = vt[:, -1, :].reshape(sorteios, 3, 3)

    # Desnormalização: H = inv(Tb) @ H_norm @ Ta
    H = inv_Tb @ H_norm @ Ta
    denominador = H[:, 2:3, 2:3]
    denominador = np.where(np.abs(denominador) > 1e-15, denominador, 1e-15)
    H = H / denominador

    # 5. Aplicação das homografias sobre os pontos de interesse em lote
    P_homog = np.ones((sorteios, 2, 3), dtype=np.float64)
    P_homog[:, :, :2] = p_pert
    P_proj = np.matmul(P_homog, H.transpose(0, 2, 1))

    den_proj = P_proj[:, :, 2:3]
    den_proj = np.where(np.abs(den_proj) > 1e-15, den_proj, 1e-15)
    P_cart = P_proj[:, :, :2] / den_proj

    distancias = np.linalg.norm(P_cart[:, 1, :] - P_cart[:, 0, :], axis=1)
    return distancias


def planck_raw_para_celsius(
    bruto: np.ndarray,
    r1: float,
    r2: float,
    b: float,
    f: float,
    o: float,
    fator_miss: float = 1.0,
    offset_atm: float = 0.0,
) -> np.ndarray:
    """Converte buffer RAW de sensor térmico FLIR para graus Celsius.

    Fórmula: T = B / ln(R1 / (R2 * (S_obj + O)) + F) - 273.15
    """
    # Tier 1: Mojo FFI nativo se carregado e tipos compatíveis
    if _mojo_binario_carregado and _mojo_lib and hasattr(_mojo_lib, "planck_raw_para_celsius_mojo"):
        try:
            bruto_u16 = np.ascontiguousarray(bruto, dtype=np.uint16)
            n_pixels = bruto_u16.size
            saida = np.empty(n_pixels, dtype=np.float32)
            _mojo_lib.planck_raw_para_celsius_mojo(
                bruto_u16.ctypes.data,
                ctypes.c_longlong(n_pixels),
                ctypes.c_float(r1),
                ctypes.c_float(r2),
                ctypes.c_float(b),
                ctypes.c_float(f),
                ctypes.c_float(o),
                ctypes.c_float(fator_miss),
                ctypes.c_float(offset_atm),
                saida.ctypes.data,
            )
            return saida.reshape(bruto.shape)
        except Exception:
            pass

    # Tier 2: Vetorização in-place de alta performance em C/NumPy
    bruto_f = np.asarray(bruto, dtype=np.float32)
    fator_miss_safe = fator_miss if abs(fator_miss) > 1e-9 else 1.0
    s_obj = (bruto_f - offset_atm) / fator_miss_safe

    with np.errstate(invalid="ignore", divide="ignore"):
        denominador = r2 * (s_obj + o)
        argumento = (r1 / np.maximum(denominador, 1e-12)) + f
        argumento = np.maximum(argumento, 1e-12)
        temperatura_c = (b / np.log(argumento)) - KELVIN

    return temperatura_c.astype(np.float32)


def calibre_rotativo_2d(uv: np.ndarray, angulos: np.ndarray) -> tuple[float, float]:
    """Calcula o ângulo e menor área para uma nuvem 2D sobre os ângulos candidatos."""
    uv = np.asarray(uv, dtype=np.float64)
    angulos = np.asarray(angulos, dtype=np.float64)

    if _mojo_binario_carregado and _mojo_lib and hasattr(_mojo_lib, "calibre_rotativo_2d_mojo"):
        try:
            m_pontos = len(uv)
            a_angulos = len(angulos)
            out_areas = np.empty(a_angulos, dtype=np.float64)
            out_melhor_idx = np.zeros(1, dtype=np.int64)

            _mojo_lib.calibre_rotativo_2d_mojo(
                uv.ctypes.data,
                ctypes.c_longlong(m_pontos),
                angulos.ctypes.data,
                ctypes.c_longlong(a_angulos),
                out_areas.ctypes.data,
                out_melhor_idx.ctypes.data,
            )
            melhor_idx = int(out_melhor_idx[0])
            return float(angulos[melhor_idx]), float(out_areas[melhor_idx])
        except Exception:
            pass

    # Tier 2: Avaliação C/BLAS em lote
    # Matriz de projeção: (A, 2) para cada eixo
    cos_a = np.cos(angulos)
    sin_a = np.sin(angulos)
    e1 = np.stack([cos_a, sin_a], axis=1)  # (A, 2)
    e2 = np.stack([-sin_a, cos_a], axis=1)  # (A, 2)

    # Projeção de todos os pontos: (M, 2) @ (2, A) -> (M, A)
    p1 = uv @ e1.T
    p2 = uv @ e2.T

    largura = p1.max(axis=0) - p1.min(axis=0)
    altura = p2.max(axis=0) - p2.min(axis=0)
    areas = largura * altura

    melhor_idx = int(np.argmin(areas))
    return float(angulos[melhor_idx]), float(areas[melhor_idx])


def cosseno_lote_contexto(vetor_consulta: np.ndarray, matriz_pesos: np.ndarray) -> np.ndarray:
    """Calcula similaridade de cosseno em lote para vetores normalizados L2."""
    q = np.asarray(vetor_consulta, dtype=np.float32)
    m = np.asarray(matriz_pesos, dtype=np.float32)

    if _mojo_binario_carregado and _mojo_lib and hasattr(_mojo_lib, "cosseno_lote_contexto_mojo"):
        try:
            k_linhas, d_dim = m.shape
            out_scores = np.empty(k_linhas, dtype=np.float32)
            out_melhor_idx = np.zeros(1, dtype=np.int64)

            _mojo_lib.cosseno_lote_contexto_mojo(
                q.ctypes.data,
                m.ctypes.data,
                ctypes.c_longlong(k_linhas),
                ctypes.c_longlong(d_dim),
                out_scores.ctypes.data,
                out_melhor_idx.ctypes.data,
            )
            return out_scores
        except Exception:
            pass

    return m @ q


# ---------------------------------------------------------------------------
# Implementações Legadas (Tier 3) para Validação e Benchmarking Comparativo
# ---------------------------------------------------------------------------

def _ransac_plano_3d_legado(
    amostra: np.ndarray,
    iteracoes: int = 200,
    tolerancia: float = 0.01,
    semente: int = 0,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Implementação sequencial legada de RANSAC (como em nucleo/medicao/geometria.py)."""
    rng = np.random.default_rng(semente)
    melhor_n, melhor = -1, None
    for _ in range(iteracoes):
        a, b, c = amostra[rng.choice(len(amostra), 3, replace=False)]
        n = np.cross(b - a, c - a)
        norma = np.linalg.norm(n)
        if norma < 1e-12:
            continue
        n /= norma
        dentro = np.abs((amostra - a) @ n) < tolerancia
        soma = int(dentro.sum())
        if soma > melhor_n:
            melhor_n, melhor = soma, (n, a)
    n, a = melhor
    return n, a, melhor_n


def _monte_carlo_homografia_legado(
    cantos: np.ndarray,
    real: np.ndarray,
    pontos: np.ndarray,
    sorteios: int = 400,
    erro_px: float = 1.0,
    semente: int = 0,
) -> np.ndarray:
    """Implementação sequencial legada com 400 iterações em Python puro (plano_ref.py)."""
    def normalizar(p):
        m = p.mean(axis=0)
        s = math.sqrt(2) / max(np.mean(np.linalg.norm(p - m, axis=1)), 1e-12)
        t = np.array([[s, 0, -s * m[0]], [0, s, -s * m[1]], [0, 0, 1]])
        return (np.c_[p, np.ones(len(p))] @ t.T)[:, :2], t

    def homografia(origem, destino):
        a, ta = normalizar(np.asarray(origem, dtype=float))
        b, tb = normalizar(np.asarray(destino, dtype=float))
        linhas = []
        for (x, y), (u, v) in zip(a, b):
            linhas.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
            linhas.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
        h = np.linalg.svd(np.asarray(linhas))[2][-1].reshape(3, 3)
        h = np.linalg.inv(tb) @ h @ ta
        return h / h[2, 2]

    def aplicar(h, pts):
        p_hom = np.c_[np.asarray(pts, dtype=float).reshape(-1, 2), np.ones(len(np.asarray(pts).reshape(-1, 2)))] @ h.T
        return p_hom[:, :2] / p_hom[:, 2:3]

    rng = np.random.default_rng(semente)
    amostras = np.empty(sorteios)
    for i in range(sorteios):
        hc = homografia(cantos + rng.normal(0, erro_px, cantos.shape), real)
        aa, bb = aplicar(hc, pontos + rng.normal(0, erro_px, pontos.shape))
        amostras[i] = np.linalg.norm(bb - aa)
    return amostras


# ---------------------------------------------------------------------------
# Benchmark Híbrido Comparativo
# ---------------------------------------------------------------------------

def benchmark_hibrido(
    n_pontos: int = 10000,
    iteracoes_ransac: int = 200,
    sorteios_mc: int = 400,
) -> dict[str, Any]:
    """Compara o desempenho real do motor legado contra a arquitetura híbrida ativa.

    Métricas retornadas em milissegundos e fatores de aceleração relativa (speedup).
    """
    # 1. Dataset de teste RANSAC: plano z = 0.5x - 0.2y + 1.0 com ruído e outliers
    rng = np.random.default_rng(42)
    x = rng.uniform(-2.0, 2.0, n_pontos)
    y = rng.uniform(-2.0, 2.0, n_pontos)
    z = 0.5 * x - 0.2 * y + 1.0 + rng.normal(0, 0.005, n_pontos)
    # 20% outliers
    n_outliers = int(n_pontos * 0.20)
    z[:n_outliers] += rng.uniform(-0.5, 0.5, n_outliers)
    nuvem_teste = np.stack([x, y, z], axis=1)

    # Benchmark RANSAC Legado
    t0 = time.perf_counter()
    _ransac_plano_3d_legado(nuvem_teste, iteracoes=iteracoes_ransac, tolerancia=0.02, semente=42)
    t_ransac_leg_ms = (time.perf_counter() - t0) * 1000.0

    # Benchmark RANSAC Híbrido (Tier 1 Mojo ou Tier 2 BLAS Batch)
    t0 = time.perf_counter()
    ransac_plano_3d(nuvem_teste, iteracoes=iteracoes_ransac, tolerancia=0.02, semente=42)
    t_ransac_hib_ms = (time.perf_counter() - t0) * 1000.0

    # 2. Dataset de teste Monte Carlo Homografia
    cantos = np.array([[100.0, 150.0], [500.0, 140.0], [520.0, 420.0], [90.0, 400.0]])
    real = np.array([[0.0, 0.0], [29.7, 0.0], [29.7, 21.0], [0.0, 21.0]])
    pontos_medir = np.array([[200.0, 250.0], [450.0, 280.0]])

    # Benchmark Monte Carlo Legado
    t0 = time.perf_counter()
    _monte_carlo_homografia_legado(cantos, real, pontos_medir, sorteios=sorteios_mc, erro_px=1.0, semente=42)
    t_mc_leg_ms = (time.perf_counter() - t0) * 1000.0

    # Benchmark Monte Carlo Híbrido (DLT Batched LAPACK)
    t0 = time.perf_counter()
    monte_carlo_homografia_pontos(cantos, real, pontos_medir, sorteios=sorteios_mc, erro_px=1.0, semente=42)
    t_mc_hib_ms = (time.perf_counter() - t0) * 1000.0

    speedup_ransac = round(t_ransac_leg_ms / max(t_ransac_hib_ms, 1e-4), 2)
    speedup_mc = round(t_mc_leg_ms / max(t_mc_hib_ms, 1e-4), 2)

    return {
        "ransac_legado_ms": round(t_ransac_leg_ms, 2),
        "ransac_hibrido_ms": round(t_ransac_hib_ms, 2),
        "ransac_speedup_x": speedup_ransac,
        "monte_carlo_legado_ms": round(t_mc_leg_ms, 2),
        "monte_carlo_hibrido_ms": round(t_mc_hib_ms, 2),
        "monte_carlo_speedup_x": speedup_mc,
        "backend_ativo": estado_acelerador()["backend_ativo"],
    }
