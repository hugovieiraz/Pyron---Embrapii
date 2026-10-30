"""Tempo e paridade do detector ONNX em cada provedor (0.9, F4).

    python -m nucleo.detectores.benchmark --modelo modelos/<id> [--aceleradores cpu,directml,cuda,tensorrt-fp32,tensorrt-fp16]
    python -m nucleo.detectores.benchmark --modelo modelos/<id> --paridade

Conjunto fixo: as inspeções gravadas em ``app/dados_app`` e em ``saida/dados_demo`` (imagem original e matriz de
temperatura de cada uma; nada é escrito nelas). Outras pastas de dados com ``--dados``.

Tempo: ``detectar()`` inteiro (preparo da imagem, rede e leitura da saída), depois de 3 rodadas de aquecimento;
mediana (p50), percentil 95 e imagens por segundo. A montagem do provedor (``carregar``) é medida à parte: no
TensorRT a primeira montagem cria o motor (minutos) e as seguintes leem do cache (``<dados>/cache_trt``).

Paridade contra a CPU (a referência): mesmas classes; cada caixa casada com IoU >= 0,95 e diferença de nota
<= 0,02; quando a caixa arredondada para pixels é a mesma, a Tmáx da região (lida na matriz, não no modelo) é a mesma.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from nucleo.detectores import provedores
from nucleo.detectores.onnx_modelo import DetectorONNX

RAIZ = Path(__file__).resolve().parents[2]
DADOS_PADRAO = [RAIZ / "app" / "dados_app", RAIZ / "saida" / "dados_demo"]
IOU_MINIMO = 0.95
NOTA_MAXIMA = 0.02
CONFIGURACOES = {
    "cpu": ("cpu", None),
    "directml": ("directml", None),
    "cuda": ("cuda", None),
    "tensorrt-fp32": ("tensorrt", False),
    "tensorrt-fp16": ("tensorrt", True),
}


def conjunto(pastas: list[Path], limite: int | None = None) -> list[tuple[str, np.ndarray, np.ndarray]]:
    """(nome, temperatura, imagem RGB) de cada inspeção gravada nas pastas de dados (só leitura)."""
    saida = []
    for pasta in pastas:
        for npy in sorted((pasta / "matrizes").glob("*.npy")):
            jpg = pasta / "imagens" / f"{npy.stem}.jpg"
            if not jpg.exists():
                continue
            with Image.open(jpg) as im:
                rgb = np.asarray(im.convert("RGB"))
            saida.append((f"{pasta.name}/{npy.stem[:8]}", np.load(npy, allow_pickle=False).astype(np.float32), rgb))
    return saida[:limite] if limite else saida


def montar(pasta_modelo: Path, configuracao: str):
    """(detector, segundos para montar). CPU: a sessão de referência; placa: o detector acelerado."""
    acelerador, meia = CONFIGURACOES[configuracao]
    base = DetectorONNX(pasta_modelo)
    t0 = time.perf_counter()
    if acelerador == "cpu":
        base._sessao_onnx()
        e = base.entrada
        base._rodar(np.zeros((1, 3, int(e["altura"]), int(e["largura"])), np.float32))
        return base, time.perf_counter() - t0
    from nucleo.detectores.placa import DetectorAcelerado

    det = DetectorAcelerado(base, acelerador, meia_precisao=meia)
    det.carregar()
    return det, time.perf_counter() - t0


def medir(det, imagens, repeticoes: int = 1, aquecimento: int = 3) -> dict:
    for nome, t, rgb in imagens[:aquecimento]:
        det.detectar(t, rgb)
    tempos = []
    for _ in range(repeticoes):
        for _nome, t, rgb in imagens:
            t0 = time.perf_counter()
            det.detectar(t, rgb)
            tempos.append(time.perf_counter() - t0)
    tempos.sort()
    p95 = tempos[min(len(tempos) - 1, int(round(0.95 * (len(tempos) - 1))))]
    return {"p50_ms": statistics.median(tempos) * 1000, "p95_ms": p95 * 1000, "imagens_por_s": len(tempos) / sum(tempos), "n": len(tempos)}


def iou(a, b) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    uniao = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / uniao if uniao > 0 else 1.0


def _pixels(caixa) -> tuple[int, int, int, int]:
    return tuple(int(round(v)) for v in caixa)


def tmax(t: np.ndarray, caixa) -> float | None:
    x0, y0, x1, y1 = _pixels(caixa)
    recorte = t[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
    return float(np.nanmax(recorte)) if recorte.size else None


def comparar(ref: list, outro: list, t: np.ndarray) -> dict:
    """Casa as detecções pela classe e pela maior IoU; devolve o pior caso desta imagem."""
    livres = list(outro)
    ious, notas, tmax_iguais, caixas_iguais = [], [], 0, 0
    for d in ref:
        candidatos = [o for o in livres if o.classe == d.classe]
        if not candidatos:
            continue
        melhor = max(candidatos, key=lambda o: iou(d.caixa, o.caixa))
        livres.remove(melhor)
        ious.append(iou(d.caixa, melhor.caixa))
        notas.append(abs(d.confianca - melhor.confianca))
        if _pixels(d.caixa) == _pixels(melhor.caixa):
            caixas_iguais += 1
            tmax_iguais += int(tmax(t, d.caixa) == tmax(t, melhor.caixa))
    mesmas = sorted(d.classe for d in ref) == sorted(o.classe for o in outro)
    return {"n_ref": len(ref), "n_outro": len(outro), "mesmas_classes": mesmas,
            "iou_min": min(ious) if ious else 1.0, "dnota_max": max(notas) if notas else 0.0,
            "caixas_iguais": caixas_iguais, "tmax_iguais": tmax_iguais}


def paridade(ref_det, det, imagens) -> dict:
    por_imagem = []
    for nome, t, rgb in imagens:
        por_imagem.append({"imagem": nome, **comparar(ref_det.detectar(t, rgb), det.detectar(t, rgb), t)})
    resumo = {
        "imagens": len(por_imagem),
        "deteccoes_ref": sum(p["n_ref"] for p in por_imagem),
        "classes_iguais": sum(p["mesmas_classes"] for p in por_imagem),
        "iou_min": min(p["iou_min"] for p in por_imagem) if por_imagem else 1.0,
        "dnota_max": max(p["dnota_max"] for p in por_imagem) if por_imagem else 0.0,
        "caixas_iguais": sum(p["caixas_iguais"] for p in por_imagem),
        "tmax_iguais": sum(p["tmax_iguais"] for p in por_imagem),
    }
    resumo["passa"] = (resumo["classes_iguais"] == resumo["imagens"] and resumo["iou_min"] >= IOU_MINIMO
                       and resumo["dnota_max"] <= NOTA_MAXIMA and resumo["tmax_iguais"] == resumo["caixas_iguais"])
    return {"resumo": resumo, "por_imagem": por_imagem}


def maquina() -> dict:
    info = {"sistema": platform.platform(), "processador": platform.processor(), "python": platform.python_version()}
    try:
        import onnxruntime as ort

        info["onnxruntime"] = ort.__version__
        info["provedores"] = ort.get_available_providers()
    except (ImportError, OSError):
        pass
    try:
        import subprocess

        r = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=10)
        info["placa"] = r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        info["placa"] = None
    return info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m nucleo.detectores.benchmark", description=__doc__.split("\n\n")[0])
    ap.add_argument("--modelo", type=Path, required=True, help="pasta do modelo (cartao.json + modelo.onnx)")
    ap.add_argument("--aceleradores", default="", help="lista separada por vírgula; padrão: a CPU e os que este ONNX Runtime oferece")
    ap.add_argument("--dados", type=Path, action="append", help="pasta de dados (padrão: app/dados_app e saida/dados_demo)")
    ap.add_argument("--limite", type=int, help="usar só as N primeiras imagens")
    ap.add_argument("--repeticoes", type=int, default=3, help="passadas pelo conjunto no tempo (padrão 3)")
    ap.add_argument("--paridade", action="store_true", help="comparar cada provedor com a CPU (sem medir tempo)")
    ap.add_argument("--saida", type=Path, help="gravar o resultado em JSON")
    args = ap.parse_args(argv)

    imagens = conjunto(args.dados or DADOS_PADRAO, args.limite)
    if not imagens:
        print("Nenhuma imagem com matriz nas pastas de dados.")
        return 2
    oferecidos = provedores.disponiveis()
    if args.aceleradores:
        lista = [a.strip() for a in args.aceleradores.split(",") if a.strip()]
    else:
        lista = ["cpu"] + [c for c in ("directml", "cuda", "tensorrt-fp32", "tensorrt-fp16") if CONFIGURACOES[c][0] in oferecidos]
    resultado = {"quando": datetime.now().isoformat(timespec="seconds"), "maquina": maquina(), "modelo": str(args.modelo),
                 "imagens": len(imagens), "cache_trt": str(provedores.pasta_cache_trt()), "configuracoes": {}}
    print(f"{len(imagens)} imagens · {resultado['maquina'].get('placa') or 'sem placa NVIDIA'} · onnxruntime {resultado['maquina'].get('onnxruntime')}")
    referencia = montar(args.modelo, "cpu")[0] if args.paridade else None
    for nome in lista:
        try:
            det, montagem = montar(args.modelo, nome)
        except Exception as erro:  # noqa: BLE001 — provedor indisponível ou falhou ao montar: registra e segue
            resultado["configuracoes"][nome] = {"erro": f"{type(erro).__name__}: {erro}"[:400]}
            print(f"{nome:14} não montou: {resultado['configuracoes'][nome]['erro']}")
            continue
        item = {"montagem_s": round(montagem, 2)}
        if args.paridade:
            if nome != "cpu":
                item["paridade"] = paridade(referencia, det, imagens)
                r = item["paridade"]["resumo"]
                print(f"{nome:14} classes iguais {r['classes_iguais']}/{r['imagens']} · IoU mín {r['iou_min']:.4f} · "
                      f"Δnota máx {r['dnota_max']:.4f} · Tmáx igual {r['tmax_iguais']}/{r['caixas_iguais']} · "
                      f"{'PASSA' if r['passa'] else 'FORA DA TOLERÂNCIA'}")
        else:
            item.update({k: round(v, 2) for k, v in medir(det, imagens, args.repeticoes).items()})
            print(f"{nome:14} montagem {item['montagem_s']:7.2f} s · p50 {item['p50_ms']:7.1f} ms · p95 {item['p95_ms']:7.1f} ms · "
                  f"{item['imagens_por_s']:6.1f} imagens/s (n={item['n']})")
        resultado["configuracoes"][nome] = item
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    raise SystemExit(main())
