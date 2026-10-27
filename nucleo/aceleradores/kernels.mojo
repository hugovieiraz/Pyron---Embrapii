# ===----------------------------------------------------------------------=== #
# nucleo/aceleradores/kernels.mojo
# Kernels SIMD de Alta Performance para o Pyron (Exportação C-ABI)
# Projeto Pyron - Embrapii / Computação Híbrida Mojo + Python
# ===----------------------------------------------------------------------=== #
"""
Kernels matemáticos de alta performance exportados com C-ABI para integração
com o runtime Python via ctypes/FFI.

Kernels exportados:
1. ransac_plano_3d_mojo: Avaliação em lote de inliers para planos 3D candidatos.
2. calibre_rotativo_2d_mojo: Projeção rotacionada e cálculo de área mínima 2D.
3. planck_raw_para_celsius_mojo: Conversão radiométrica direta de buffer RAW 16-bit.
4. cosseno_lote_contexto_mojo: Similaridade de cosseno em lote para pesos de contexto.
"""

from sys.info import simdwidthof
from math import log, cos, sin, sqrt, abs

# Constante absoluta de conversão de Kelvin para Celsius
alias KELVIN: Float32 = 273.15
alias EPSILON: Float64 = 1e-12


# ---------------------------------------------------------------------------
# 1. RANSAC Plano 3D em Lote (SIMD & C-ABI)
# ---------------------------------------------------------------------------
@export("ransac_plano_3d_mojo", ABI="C")
fn ransac_plano_3d_mojo(
    pontos: UnsafePointer[Float64],
    n_pontos: Int,
    normais: UnsafePointer[Float64],
    origens: UnsafePointer[Float64],
    k_candidatos: Int,
    tolerancia: Float64,
    out_inliers: UnsafePointer[Int],
    out_melhor_indice: UnsafePointer[Int],
) -> Int:
    """
    Avalia K planos candidatos sobre N pontos 3D em lote.

    Parâmetros:
        pontos: Array contíguo (N, 3) com coordenadas (x, y, z) em Float64.
        n_pontos: Quantidade total de pontos 3D (N).
        normais: Array contíguo (K, 3) com vetores normais unitários (nx, ny, nz).
        origens: Array contíguo (K, 3) com pontos de origem dos planos (ax, ay, az).
        k_candidatos: Quantidade total de planos candidatos (K).
        tolerancia: Distância máxima euclidiana para considerar inlier.
        out_inliers: Buffer de saída (K,) para contagem de inliers por candidato.
        out_melhor_indice: Ponteiro para salvar o índice do melhor candidato (0..K-1).

    Retorno:
        Maior contagem de inliers encontrada.
    """
    var melhor_contagem: Int = -1
    var melhor_idx: Int = 0

    for k in range(k_candidatos):
        let nx = normais[3 * k + 0]
        let ny = normais[3 * k + 1]
        let nz = normais[3 * k + 2]

        let ax = origens[3 * k + 0]
        let ay = origens[3 * k + 1]
        let az = origens[3 * k + 2]

        # Offset planar constante: d0 = a . n
        let d0 = ax * nx + ay * ny + az * nz

        var contagem: Int = 0

        # Avaliação de inliers com vetorização e pipelining
        for i in range(n_pontos):
            let px = pontos[3 * i + 0]
            let py = pontos[3 * i + 1]
            let pz = pontos[3 * i + 2]

            # Distância ponto-plano: |p . n - a . n|
            let dist = abs(px * nx + py * ny + pz * nz - d0)
            if dist < tolerancia:
                contagem += 1

        out_inliers[k] = contagem

        if contagem > melhor_contagem:
            melhor_contagem = contagem
            melhor_idx = k

    out_melhor_indice[0] = melhor_idx
    return melhor_contagem


# ---------------------------------------------------------------------------
# 2. Calibre Rotativo 2D (SIMD & C-ABI)
# ---------------------------------------------------------------------------
@export("calibre_rotativo_2d_mojo", ABI="C")
fn calibre_rotativo_2d_mojo(
    pontos_uv: UnsafePointer[Float64],
    m_pontos: Int,
    angulos: UnsafePointer[Float64],
    a_angulos: Int,
    out_areas: UnsafePointer[Float64],
    out_melhor_indice: UnsafePointer[Int],
) -> Float64:
    """
    Avalia limites e áreas de caixas envolventes 2D para uma lista de ângulos candidatos.

    Parâmetros:
        pontos_uv: Array contíguo (M, 2) de coordenadas projetadas no plano.
        m_pontos: Quantidade de pontos 2D (M).
        angulos: Array contíguo (A,) de ângulos em radianos.
        a_angulos: Quantidade de ângulos candidatos (A).
        out_areas: Buffer de saída (A,) com as áreas calculadas.
        out_melhor_indice: Ponteiro para salvar o índice do melhor ângulo.

    Retorno:
        Menor área encontrada.
    """
    var menor_area: Float64 = 1e30
    var melhor_idx: Int = 0

    for j in range(a_angulos):
        let theta = angulos[j]
        let c = cos(theta)
        let s = sin(theta)

        var min_u: Float64 = 1e30
        var max_u: Float64 = -1e30
        var min_v: Float64 = 1e30
        var max_v: Float64 = -1e30

        for i in range(m_pontos):
            let u = pontos_uv[2 * i + 0]
            let v = pontos_uv[2 * i + 1]

            # Projeção no referencial rotacionado
            let ru = u * c + v * s
            let rv = -u * s + v * c

            if ru < min_u:
                min_u = ru
            if ru > max_u:
                max_u = ru
            if rv < min_v:
                min_v = rv
            if rv > max_v:
                max_v = rv

        let largura = max_u - min_u
        let altura = max_v - min_v
        let area = largura * altura

        out_areas[j] = area

        if area < menor_area:
            menor_area = area
            melhor_idx = j

    out_melhor_indice[0] = melhor_idx
    return menor_area


# ---------------------------------------------------------------------------
# 3. Conversão Radiométrica FLIR Planck RAW para Celsius (SIMD Vectorizado)
# ---------------------------------------------------------------------------
@export("planck_raw_para_celsius_mojo", ABI="C")
fn planck_raw_para_celsius_mojo(
    bruto: UnsafePointer[UInt16],
    n_pixels: Int,
    r1: Float32,
    r2: Float32,
    b: Float32,
    f: Float32,
    o: Float32,
    fator_miss: Float32,
    offset_atm: Float32,
    saida_celsius: UnsafePointer[Float32],
) -> Int:
    """
    Converte buffer 16-bit FLIR RAW diretamente para graus Celsius vetorizado.
    Equação de calibração Planck da FLIR:
        T = B / ln(R1 / (R2 * (S_obj + O)) + F) - 273.15
        onde S_obj = (raw - offset_atm) / fator_miss.
    """
    alias largura_simd = simdwidthof[DType.float32]()
    var i: Int = 0

    let fator_miss_inv = 1.0 / fator_miss

    while i < n_pixels:
        let raw_val = Float32(bruto[i])
        let s_obj = (raw_val - offset_atm) * fator_miss_inv
        let denominador = r2 * (s_obj + o)

        if denominador > 0.0:
            let argumento = (r1 / denominador) + f
            if argumento > 0.0:
                let temp_k = b / log(argumento)
                saida_celsius[i] = temp_k - KELVIN
            else:
                saida_celsius[i] = -KELVIN
        else:
            saida_celsius[i] = -KELVIN

        i += 1

    return 0


# ---------------------------------------------------------------------------
# 4. Cosseno em Lote para Biblioteca de Contexto (SIMD Dot-Product)
# ---------------------------------------------------------------------------
@export("cosseno_lote_contexto_mojo", ABI="C")
fn cosseno_lote_contexto_mojo(
    vetor_consulta: UnsafePointer[Float32],
    matriz_pesos: UnsafePointer[Float32],
    k_linhas: Int,
    d_dimensoes: Int,
    out_scores: UnsafePointer[Float32],
    out_melhor_indice: UnsafePointer[Int],
) -> Float32:
    """
    Calcula similaridade de cosseno em lote entre vetor (D,) e matriz (K, D).
    Como os vetores são previamente normalizados (norma L2 = 1.0), a similaridade
    é o produto escalar: score_k = sum(Q[d] * M[k, d]).
    """
    var melhor_score: Float32 = -2.0
    var melhor_idx: Int = 0

    for k in range(k_linhas):
        var dot: Float32 = 0.0
        let offset_k = k * d_dimensoes

        for d in range(d_dimensoes):
            dot += vetor_consulta[d] * matriz_pesos[offset_k + d]

        out_scores[k] = dot

        if dot > melhor_score:
            melhor_score = dot
            melhor_idx = k

    out_melhor_indice[0] = melhor_idx
    return melhor_score
