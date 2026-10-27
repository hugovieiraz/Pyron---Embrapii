"""Ponto de entrada CLI para diagnóstico e benchmark do acelerador híbrido.

Uso:
    python -m nucleo.aceleradores
"""

from __future__ import annotations

import json
import sys

from nucleo.aceleradores import benchmark_hibrido, estado_acelerador


def main() -> None:
    print("=" * 65)
    print("  PYRON - SUBSISTEMA DE ACELERAÇÃO HÍBRIDA (MOJO + C/LAPACK)")
    print("=" * 65)

    estado = estado_acelerador()
    print(f"Arquitetura:          {estado['arquitetura']}")
    print(f"Backend Ativo:        {estado['backend_ativo'].upper()}")
    print(f"Código-fonte Mojo:    {'SIM' if estado['mojo_codigo_fonte'] else 'NÃO'}")
    print(f"Compilador Mojo CLI:  {'DISPONÍVEL' if estado['mojo_cli_disponivel'] else 'NÃO INSTALADO'}")
    print(f"Binário DLL Nativo:   {'CARREGADO (Tier 1)' if estado['mojo_binario_carregado'] else 'NÃO CARREGADO (Tier 2 Ativo)'}")
    if estado["motivo_fallback"]:
        print(f"Diagnóstico/Fallback: {estado['motivo_fallback']}")

    print("\nKernels Registrados:")
    for k in estado["kernels_disponiveis"]:
        print(f"  • {k}")

    print("\nExecutando Benchmark de Alta Resolução...")
    resultado = benchmark_hibrido(n_pontos=10000, iteracoes_ransac=200, sorteios_mc=400)

    print("-" * 65)
    print("RESULTADOS DO BENCHMARK HÍBRIDO:")
    print("-" * 65)
    print(f"RANSAC Plano 3D (10.000 pts, 200 iterações):")
    print(f"  • Legado (Python loop):      {resultado['ransac_legado_ms']:.2f} ms")
    print(f"  • Híbrido ({resultado['backend_ativo']}): {resultado['ransac_hibrido_ms']:.2f} ms")
    print(f"  • Aceleração (Speedup):      {resultado['ransac_speedup_x']:.2f}x")

    print(f"\nMonte Carlo Homografia DLT (400 sorteios SVD):")
    print(f"  • Legado (Python loop):      {resultado['monte_carlo_legado_ms']:.2f} ms")
    print(f"  • Híbrido ({resultado['backend_ativo']}): {resultado['monte_carlo_hibrido_ms']:.2f} ms")
    print(f"  • Aceleração (Speedup):      {resultado['monte_carlo_speedup_x']:.2f}x")
    print("=" * 65)


if __name__ == "__main__":
    main()
