"""Versão rápida (INT8) de um modelo instalado: os pesos dos MatMul em 8 bits, sem treinar de novo.

Uso:
    python -m ml.otimizar modelos/<id>                                   (só gera e mede a velocidade)
    python -m ml.otimizar modelos/<id> --dados dados/para_raios_dataset_v2   (mede também o acerto no teste)

Quantização dinâmica do ONNX Runtime só nos MatMul (a maior parte da conta do RF-DETR): os pesos são
guardados em 8 bits e as ativações são quantizadas na hora. Detectores do tipo DETR podem perder muito
acerto com quantização estática; a dinâmica dos MatMul manteve o acerto no modelo de para-raios
(mAP50 0,859 × 0,859 no teste) e ficou 1,5 vez mais rápida no processador (245 × 368 ms), com um
arquivo três vezes menor. Por isso o acerto é medido de novo quando há dados: confira antes de usar.

O modelo novo fica ao lado do original, em ``modelos/<id>-int8``, com ``otimizacao`` no cartão; a
câmera do celular passa a usá-lo no lugar do original (``app/servidor.py``, ``_detector_imagem``).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

SUFIXO = "-int8"
RODADAS = 12  # medições alternadas entre o original e o INT8 (o notebook esquenta: alternar é mais justo)


def quantizar(origem: Path, destino: Path) -> None:
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from onnxruntime.quantization.shape_inference import quant_pre_process

    with tempfile.TemporaryDirectory() as tmp:
        pre = Path(tmp) / "pre.onnx"
        quant_pre_process(str(origem), str(pre), skip_symbolic_shape=True)
        quantize_dynamic(str(pre), str(destino), weight_type=QuantType.QInt8, op_types_to_quantize=["MatMul"])


def medir_tempos(original: Path, otimizado: Path) -> tuple[float, float]:
    """Mediana em ms de cada modelo, rodadas alternadas, com as opções de sessão do Pyron."""
    from nucleo.detectores.onnx_modelo import DetectorONNX

    sessoes = [DetectorONNX(original)._sessao_onnx(), DetectorONNX(otimizado)._sessao_onnx()]
    forma = [d if isinstance(d, int) else 1 for d in sessoes[0].get_inputs()[0].shape]
    x = np.random.default_rng(0).random(forma, dtype=np.float32)
    tempos: list[list[float]] = [[], []]
    for s in sessoes:  # aquecimento
        s.run(None, {s.get_inputs()[0].name: x})
    for _ in range(RODADAS):
        for k, s in enumerate(sessoes):
            t = time.perf_counter()
            s.run(None, {s.get_inputs()[0].name: x})
            tempos[k].append((time.perf_counter() - t) * 1000)
    return float(np.median(tempos[0])), float(np.median(tempos[1]))


def medir_acerto(pasta: Path, dados: Path, limiar: float) -> dict:
    from ml import rfdetr_local as rl

    conj = rl.ler_dataset(dados)
    previstas = rl.prever_com_pyron(pasta, conj["teste"], conj["classes"])
    return rl.avaliar(conj["teste"], previstas, conj["classes"], limiar)


def otimizar(pasta: Path, dados: Path | None = None) -> Path:
    cartao = json.loads((pasta / "cartao.json").read_text(encoding="utf-8"))
    if cartao.get("otimizacao"):
        raise SystemExit(f"{pasta.name} já é uma versão otimizada.")
    destino = pasta.parent / f"{pasta.name}{SUFIXO}"
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir()
    arquivo = cartao.get("arquivo", "modelo.onnx")
    print(f"Quantizando {pasta.name} (INT8 dinâmico nos MatMul)…", flush=True)
    quantizar(pasta / arquivo, destino / arquivo)
    novo = {
        **cartao,
        "id": f"{cartao['id']}{SUFIXO}",
        "nome": f"{cartao['nome']} · rápido (INT8)",
        "descricao": f"{cartao.get('descricao', '')} Versão rápida: pesos em 8 bits (quantização dinâmica).".strip(),
    }
    (destino / "cartao.json").write_text(json.dumps(novo, ensure_ascii=False, indent=1), encoding="utf-8")
    t_orig, t_novo = medir_tempos(pasta, destino)
    otimizacao = {
        "tipo": "int8_dinamico_matmul",
        "origem": cartao["id"],
        "tempo_ms": round(t_novo),
        "tempo_original_ms": round(t_orig),
        "tamanho_mb": round((destino / arquivo).stat().st_size / 2**20, 1),
        "tamanho_original_mb": round((pasta / arquivo).stat().st_size / 2**20, 1),
    }
    print(f"Tempo: {t_orig:.0f} ms → {t_novo:.0f} ms | tamanho: {otimizacao['tamanho_original_mb']} → {otimizacao['tamanho_mb']} MB", flush=True)
    relatorio_orig = pasta / "relatorio.json"
    relatorio = json.loads(relatorio_orig.read_text(encoding="utf-8")) if relatorio_orig.exists() else {}
    if dados:
        limiar = float(cartao.get("limiar_confianca", relatorio.get("limiar", 0.5)))
        print("Medindo o acerto no conjunto de teste…", flush=True)
        otimizacao["teste_original"] = medir_acerto(pasta, dados, limiar)
        otimizacao["teste"] = medir_acerto(destino, dados, limiar)
        relatorio["teste"] = otimizacao["teste"]
        a, b = otimizacao["teste_original"], otimizacao["teste"]
        print(f"mAP50 {a['mAP50']} → {b['mAP50']} | mAP50-95 {a['mAP50-95']} → {b['mAP50-95']} | revocação {a['revocacao']} → {b['revocacao']}")
    novo["otimizacao"] = otimizacao
    (destino / "cartao.json").write_text(json.dumps(novo, ensure_ascii=False, indent=1), encoding="utf-8")
    if relatorio:
        relatorio["otimizacao"] = otimizacao
        (destino / "relatorio.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Instalado em {destino}", flush=True)
    return destino


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Gera a versão rápida (INT8) de um modelo instalado.")
    ap.add_argument("modelo", type=Path, help="pasta do modelo em modelos/")
    ap.add_argument("--dados", type=Path, help="dataset rotulado (pasta ou .zip) para medir o acerto no teste")
    args = ap.parse_args(argv)
    otimizar(args.modelo, args.dados)


if __name__ == "__main__":
    main()
