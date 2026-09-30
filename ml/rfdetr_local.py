"""Treina o RF-DETR neste computador (GPU) e instala o modelo no Pyron, sem passar pelo Colab.

Uso:
    python -m ml.rfdetr_local --dados dados/para_raios_dataset_v2          (pasta ou .zip do dataset)
    python -m ml.rfdetr_local --dados ... --epocas 100 --lote 2 --acumular 2 --resolucao 640

Faz o mesmo que os passos 3, 9 e 17 do caderno Treino_para_raios_Colab.ipynb:

1. lê as anotações do CVAT (COCO 1.0) e as fotos no sentido em que foram rotuladas (EXIF);
   retângulos girados viram a caixa reta que os envolve e fotos com peças inclinadas mais de 15°
   ficam de fora (a caixa reta engoliria o para-raios vizinho);
2. usa a divisão do CVAT (treino, validação, teste);
3. ajusta o RF-DETR (pesos do COCO, base DINOv2) e fica com a melhor época pela validação;
4. exporta para ONNX e confere o ONNX com o **mesmo detector que o Pyron usa**
   (``nucleo/detectores/onnx_modelo.py``); a numeração das classes e o limiar de confiança são
   escolhidos nas fotos de validação, nunca no teste;
5. instala em ``modelos/<id>`` e grava a avaliação (métricas, curvas e fotos de teste marcadas)
   para a aba Avaliação.

O modelo olha a imagem colorida da câmera (``entrada.fonte = "imagem_exibida"``), como no Colab.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import shutil
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from ml import comparacao  # noqa: E402  (casamento e AP, sem PyTorch)

EXTENSOES = {".jpg", ".jpeg", ".png"}
MEDIA = [0.485, 0.456, 0.406]
DESVIO = [0.229, 0.224, 0.225]


def dizer(texto: str = "") -> None:
    print(texto, flush=True)


# ---------------------------------------------------------------- leitura do dataset (igual ao passo 3 do caderno)


@dataclass
class Foto:
    nome: str
    caminho: Path
    subconjunto: str
    caixas: np.ndarray  # [N, 4] x0, y0, x1, y1 em pixels da foto (no sentido rotulado)
    classes: np.ndarray  # [N] índice em classes
    largura: int
    altura: int
    _rgb: np.ndarray | None = field(default=None, repr=False)

    @property
    def rgb(self) -> np.ndarray:
        if self._rgb is None:
            foto = Image.open(self.caminho)
            try:
                girada = ImageOps.exif_transpose(foto)
            except Exception:  # noqa: BLE001 - EXIF estranho: fica como está
                girada = foto
            for f in (girada, foto):
                if f.size == (self.largura, self.altura):
                    self._rgb = np.asarray(f.convert("RGB"))
                    break
            else:
                self._rgb = np.asarray(girada.convert("RGB").resize((self.largura, self.altura)))
        return self._rgb


def caixa_reta(x: float, y: float, w: float, h: float, rotacao: float) -> list[float]:
    """Caixa reta que envolve um retângulo girado do CVAT (giro em graus em torno do centro)."""
    if not rotacao:
        return [x, y, x + w, y + h]
    t = math.radians(rotacao)
    cx, cy = x + w / 2, y + h / 2
    meia_l = (abs(w * math.cos(t)) + abs(h * math.sin(t))) / 2
    meia_a = (abs(w * math.sin(t)) + abs(h * math.cos(t))) / 2
    return [cx - meia_l, cy - meia_a, cx + meia_l, cy + meia_a]


def inclinacao(rotacao: float) -> float:
    r = float(rotacao or 0) % 90
    return min(r, 90 - r)


def subconjunto_do_nome(nome: str) -> str:
    n = nome.lower()
    return "teste" if "test" in n else "validacao" if "val" in n else "treino"


def ler_dataset(origem: Path, angulo_maximo: float = 15.0, frac_validacao: float = 0.15) -> dict:
    """Classes, fotos de treino/validação/teste e um relatório do que ficou de fora."""
    if origem.suffix.lower() == ".zip":
        pasta = Path(tempfile.mkdtemp(prefix="pyron_dataset_"))
        with zipfile.ZipFile(origem) as z:
            z.extractall(pasta)
    else:
        pasta = origem
    visivel = lambda p: not p.name.startswith(".") and "__MACOSX" not in p.parts  # noqa: E731
    jsons = sorted(p for p in pasta.rglob("*.json") if visivel(p))
    fotos = sorted(p for p in pasta.rglob("*") if p.suffix.lower() in EXTENSOES and visivel(p))
    por_nome = {p.name.lower(): p for p in fotos}
    por_radical = {p.stem.lower(): p for p in fotos}

    classes: list[str] = []
    amostras: list[Foto] = []
    inclinadas, sem_caixa, nao_achadas, giradas = [], 0, [], 0
    for arq in jsons:
        try:
            coco = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(coco, dict) or not {"images", "annotations", "categories"} <= set(coco):
            continue
        sub = subconjunto_do_nome(arq.name)
        cat = {}
        for c in sorted(coco["categories"], key=lambda c: c["id"]):
            if c["name"] not in classes:
                classes.append(c["name"])
            cat[c["id"]] = classes.index(c["name"])
        tamanho = {im["id"]: (im["width"], im["height"]) for im in coco["images"]}
        rotulos, fora_de_angulo, giradas_por_foto = {}, set(), {}
        for an in coco["annotations"]:
            if an.get("image_id") not in tamanho or not an.get("bbox"):
                continue
            W, H = tamanho[an["image_id"]]
            x, y, w, h = an["bbox"]
            rotacao = float((an.get("attributes") or {}).get("rotation", 0) or 0)
            if inclinacao(rotacao) > angulo_maximo:
                fora_de_angulo.add(an["image_id"])
            if rotacao:
                giradas_por_foto[an["image_id"]] = giradas_por_foto.get(an["image_id"], 0) + 1
            c = np.clip(caixa_reta(x, y, w, h, rotacao), 0, [W, H, W, H])
            if c[2] - c[0] > 1 and c[3] - c[1] > 1:
                rotulos.setdefault(an["image_id"], []).append((c, cat[an["category_id"]]))
        for im in coco["images"]:
            nome = im["file_name"].replace("\\", "/").split("/")[-1]
            if im["id"] in fora_de_angulo:
                inclinadas.append(nome)
                continue
            lista = rotulos.get(im["id"], [])
            if not lista:
                sem_caixa += 1
                continue
            caminho = por_nome.get(nome.lower()) or por_radical.get(Path(nome).stem.lower())
            if caminho is None:
                nao_achadas.append(nome)
                continue
            giradas += giradas_por_foto.get(im["id"], 0)
            amostras.append(Foto(caminho.name, caminho, sub, np.array([c for c, _ in lista], dtype=np.float32),
                                 np.array([k for _, k in lista], dtype=np.int64), int(im["width"]), int(im["height"])))
    if not amostras:
        raise ValueError("Nenhuma foto rotulada foi encontrada. Confira se a pasta tem as fotos e os .json do CVAT (COCO 1.0).")

    amostras.sort(key=lambda a: a.nome)  # a câmera numera em sequência: nome ≈ ordem no tempo
    treino = [a for a in amostras if a.subconjunto == "treino"]
    validacao = [a for a in amostras if a.subconjunto == "validacao"]
    teste = [a for a in amostras if a.subconjunto == "teste"]
    if not teste:
        n = max(1, round(0.2 * len(treino)))
        treino, teste = treino[:-n], treino[-n:]
    if len(validacao) < 5:
        n = max(1, round(frac_validacao * len(treino)))
        treino, validacao = treino[:-n], validacao + treino[-n:]
    return {
        "classes": classes, "treino": treino, "validacao": validacao, "teste": teste,
        "relatorio": {"inclinadas": sorted(inclinadas), "sem_caixa": sem_caixa, "nao_achadas": nao_achadas,
                      "giradas_convertidas": giradas, "caixas": int(sum(len(a.caixas) for a in amostras))},
    }


# ---------------------------------------------------------------- métricas (as mesmas do caderno)


def avaliar(conj: list[Foto], previstas: list, classes: list[str], limiar: float) -> dict:
    por_classe, aps50, aps5095 = {}, [], []
    for k, nome in enumerate(classes):
        aps = [comparacao._ap(conj, previstas, k, t) for t in comparacao.LIMIARES_IOU]
        validos = [v for v in aps if v is not None]
        if aps[0] is not None:
            aps50.append(aps[0])
            aps5095.append(float(np.mean(validos)))
        por_classe[nome] = {"AP50": comparacao._r(aps[0]), "AP50-95": comparacao._r(np.mean(validos)) if validos else None}
    tp = fp = fn = 0
    ious: list[float] = []
    tp_k, gt_k = np.zeros(len(classes)), np.zeros(len(classes))
    for a, (pc, pp, pk) in zip(conj, previstas):
        acertos, falsos, perdidos = comparacao.casar(a.caixas, a.classes, pc, pp, pk, limiar)
        tp, fp, fn = tp + len(acertos), fp + len(falsos), fn + len(perdidos)
        ious += [v for _, _, v in acertos]
        for _, j, _ in acertos:
            tp_k[a.classes[j]] += 1
        for k in a.classes:
            gt_k[k] += 1
    for k, nome in enumerate(classes):
        por_classe[nome]["revocacao"] = comparacao._r(tp_k[k] / gt_k[k]) if gt_k[k] else None
    precisao = tp / (tp + fp) if tp + fp else 0.0
    revocacao = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precisao * revocacao / (precisao + revocacao) if precisao + revocacao else 0.0
    return {"mAP50": comparacao._r(np.mean(aps50)) if aps50 else None,
            "mAP50-95": comparacao._r(np.mean(aps5095)) if aps5095 else None,
            "precisao": comparacao._r(precisao), "revocacao": comparacao._r(revocacao), "F1": comparacao._r(f1),
            "IoU_medio_acertos": comparacao._r(np.mean(ious)) if ious else None,
            "acertos": tp, "falsos": fp, "perdidos": fn, "por_classe": por_classe}


def erro_temperatura(conj: list[Foto], previstas: list, limiar: float) -> dict:
    """O que importa para o Pyron: a Tmáx medida na caixa do modelo × na caixa rotulada, em °C.

    A temperatura vem da matriz radiométrica do JPEG (a mesma que a análise do Pyron usa), no mesmo
    sentido da foto; as caixas em pixels da foto são levadas para a grade da matriz.
    """
    from nucleo import entrada

    erros: list[float] = []
    for a, (pc, pp, pk) in zip(conj, previstas):
        try:
            t = entrada.carregar(a.caminho.read_bytes()).temperatura_c
        except ValueError:
            continue
        h, w = t.shape
        sx, sy = w / a.largura, h / a.altura

        def tmax(c):
            x0, y0 = max(int(c[0] * sx), 0), max(int(c[1] * sy), 0)
            x1, y1 = max(math.ceil(c[2] * sx), x0 + 1), max(math.ceil(c[3] * sy), y0 + 1)
            regiao = t[y0:y1, x0:x1]
            return float(np.nanmax(regiao)) if regiao.size and np.isfinite(regiao).any() else None

        acertos, _, _ = comparacao.casar(a.caixas, a.classes, pc, pp, pk, limiar)
        for i, j, _ in acertos:
            prevista, rotulada = tmax(pc[i]), tmax(a.caixas[j])
            if prevista is not None and rotulada is not None:
                erros.append(abs(prevista - rotulada))
    if not erros:
        return {"erro_Tmax_mediano_C": None, "erro_Tmax_p90_C": None, "pecas_medidas": 0}
    return {"erro_Tmax_mediano_C": round(float(np.median(erros)), 2), "erro_Tmax_p90_C": round(float(np.percentile(erros, 90)), 2),
            "pecas_medidas": len(erros)}


def calibrar_limiar(validacao: list[Foto], previstas: list) -> float:
    """Limiar de confiança com o melhor F1 na validação."""
    melhor, melhor_f1 = 0.5, -1.0
    for t in np.round(np.arange(0.05, 0.951, 0.05), 2):
        tp = fp = fn = 0
        for a, (pc, pp, pk) in zip(validacao, previstas):
            ac, fa, pe = comparacao.casar(a.caixas, a.classes, pc, pp, pk, float(t))
            tp, fp, fn = tp + len(ac), fp + len(fa), fn + len(pe)
        f1 = 2 * tp / max(2 * tp + fp + fn, 1)
        if f1 > melhor_f1:
            melhor, melhor_f1 = float(t), f1
    return melhor


# ---------------------------------------------------------------- RF-DETR


def escrever_coco(conj: list[Foto], pasta: Path, classes: list[str]) -> None:
    """Formato do RF-DETR: fotos (sem EXIF, no sentido certo) e _annotations.coco.json, classes de 1 a K."""
    pasta.mkdir(parents=True, exist_ok=True)
    coco = {"images": [], "annotations": [],
            "categories": [{"id": k + 1, "name": c, "supercategory": "para_raios"} for k, c in enumerate(classes)]}
    for i, a in enumerate(conj, start=1):
        nome = Path(a.nome).stem + ".jpg"
        Image.fromarray(a.rgb).save(pasta / nome, quality=95)
        coco["images"].append({"id": i, "file_name": nome, "width": a.largura, "height": a.altura})
        for c, k in zip(a.caixas, a.classes):
            x0, y0, x1, y1 = (float(v) for v in c)
            coco["annotations"].append({"id": len(coco["annotations"]) + 1, "image_id": i, "category_id": int(k) + 1,
                                        "bbox": [x0, y0, x1 - x0, y1 - y0], "area": (x1 - x0) * (y1 - y0), "iscrowd": 0})
    (pasta / "_annotations.coco.json").write_text(json.dumps(coco), encoding="utf-8")


def historico_rfdetr(pasta: Path, duracao: float) -> dict | None:
    """Perda e mAP50 por época a partir do metrics.csv que o RF-DETR grava (uma linha de treino e uma de validação por época)."""
    import csv

    arquivos = sorted(pasta.rglob("metrics.csv"))
    if not arquivos:
        return None
    por_epoca: dict[int, dict[str, float]] = {}
    with arquivos[0].open(encoding="utf-8", newline="") as f:
        for linha in csv.DictReader(f):
            if not linha.get("epoch"):
                continue
            valores = por_epoca.setdefault(int(float(linha["epoch"])), {})
            for k, v in linha.items():
                try:
                    valores[k] = float(v)
                except (TypeError, ValueError):
                    continue
    epocas = sorted(por_epoca)
    if not epocas:
        return None

    def serie(preferidas, prefixo, contem):
        candidatas = preferidas + sorted({k for d in por_epoca.values() for k in d if k.startswith(prefixo) and contem in k})
        for c in candidatas:
            if any(c in por_epoca[e] for e in epocas):
                return [por_epoca[e].get(c) for e in epocas]
        return None

    perda_t = serie(["train/loss_epoch", "train/loss"], "train/", "loss")
    perda_v = serie(["val/loss_epoch", "val/loss"], "val/", "loss")
    mapa = serie(["val/mAP_50"], "val/", "mAP_50")
    h = {"epocas_perda": [e + 1 for e in epocas], "perda_treino": perda_t or [None] * len(epocas),
         "perda_validacao": perda_v or [None] * len(epocas), "epocas_map": [], "map50_validacao": [],
         "melhor_epoca": None, "melhor_map50_validacao": None, "duracao_min": duracao}
    if mapa:
        pares = [(e + 1, v) for e, v in zip(epocas, mapa) if v is not None]
        h["epocas_map"] = [e for e, _ in pares]
        h["map50_validacao"] = [v for _, v in pares]
        if pares:
            h["melhor_epoca"], h["melhor_map50_validacao"] = max(pares, key=lambda p: p[1])
    return h


def slug_classe(texto: str) -> str:
    import re
    import unicodedata

    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def cartao_modelo(id_: str, nome_modelo: str, classes: list[str], largura: int, altura: int, deslocamento: int,
                  limiar: float, nomes_saida: dict, extra: dict | None = None) -> dict:
    classes_pyron = [slug_classe(c) for c in classes]
    return {
        "id": id_,
        "nome": f"Para-raios ({nome_modelo})",
        "arquitetura": f"{nome_modelo} (detector DETR com base DINOv2)",
        "versao": "1.0",
        "descricao": "Acha o para-raios e as suas partes (" + ", ".join(classes) + ") em termogramas FLIR.",
        "classes": classes_pyron,
        "nomes": dict(zip(classes_pyron, classes)),
        "arquivo": "modelo.onnx",
        "entrada": {"fonte": "imagem_exibida", "largura": int(largura), "altura": int(altura), "media": MEDIA, "desvio": DESVIO},
        "saida": {"formato": "rfdetr", "fundo_ultima_coluna": True, "deslocamento_classe": int(deslocamento), "nomes": nomes_saida},
        "limiar_confianca": float(limiar),
        **(extra or {}),
    }


def prever_com_pyron(pasta_modelo: Path, conj: list[Foto], classes: list[str]) -> list:
    """Previsões pelo detector do próprio Pyron (DetectorONNX), no formato das métricas."""
    from nucleo.detectores.onnx_modelo import DetectorONNX

    det = DetectorONNX(pasta_modelo)
    indice = {c: k for k, c in enumerate(det.classes)}
    saida = []
    for a in conj:
        # "temperatura" do tamanho da foto: as caixas saem direto em pixels da foto
        achados = det.detectar(np.zeros((a.altura, a.largura), dtype=np.float32), a.rgb)
        saida.append((np.array([d.caixa for d in achados], dtype=float).reshape(-1, 4),
                      np.array([d.confianca for d in achados], dtype=float),
                      np.array([indice[d.classe] for d in achados], dtype=np.int64)))
    return saida


# ---------------------------------------------------------------- figuras de teste (verde, vermelho, amarelo)


def figura_teste(conj: list[Foto], previstas: list, classes: list[str], limiar: float, titulo: str) -> bytes:
    siglas = ["".join(p[0] for p in c.replace("-", " ").split()).upper()[:3] for c in classes]
    L, A, colunas = 400, 300, 3
    linhas = math.ceil(len(conj) / colunas)
    tela = Image.new("RGB", (L * colunas, 34 + (A + 26) * linhas), "white")
    d = ImageDraw.Draw(tela)
    d.text((10, 10), titulo + "   |   verde: acerto   vermelho: caixa falsa   amarelo: peça não encontrada", fill=(23, 27, 51))
    for i, (a, (pc, pp, pk)) in enumerate(zip(conj, previstas)):
        x0, y0 = (i % colunas) * L, 34 + (i // colunas) * (A + 26)
        escala = min(L / a.largura, A / a.altura)
        foto = Image.fromarray(a.rgb).resize((int(a.largura * escala), int(a.altura * escala)))
        tela.paste(foto, (x0, y0))
        acertos, falsos, perdidos = comparacao.casar(a.caixas, a.classes, pc, pp, pk, limiar)

        def caixa(c, cor, texto=""):
            q = [x0 + c[0] * escala, y0 + c[1] * escala, x0 + c[2] * escala, y0 + c[3] * escala]
            d.rectangle(q, outline=cor, width=2)
            if texto:
                d.text((q[0] + 2, max(y0, q[1] - 11)), texto, fill=cor)

        for j in perdidos:
            caixa(a.caixas[j], (255, 212, 0), siglas[int(a.classes[j])])
        for k, _, _ in acertos:
            caixa(pc[k], (43, 214, 123), f"{siglas[int(pk[k])]} {pp[k]:.2f}")
        for k in falsos:
            caixa(pc[k], (255, 77, 77), f"{siglas[int(pk[k])]} {pp[k]:.2f}")
        d.text((x0 + 4, y0 + A + 6), f"{a.nome}: {len(acertos)} acertos, {len(falsos)} falsos, {len(perdidos)} perdidos", fill=(23, 27, 51))
    buf = io.BytesIO()
    tela.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------- principal


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dados", type=Path, required=True, help="pasta ou .zip com as fotos e a pasta annotations do CVAT")
    ap.add_argument("--modelo", default="RFDETRMedium", help="RFDETRNano, RFDETRSmall, RFDETRMedium, RFDETRLarge")
    ap.add_argument("--resolucao", type=int, default=640, help="múltiplo de 32")
    ap.add_argument("--epocas", type=int, default=100)
    ap.add_argument("--lote", type=int, default=2)
    ap.add_argument("--acumular", type=int, default=2, help="lotes somados antes de cada passo (lote × acumular = lote efetivo)")
    ap.add_argument("--paciencia", type=int, default=20, help="para se passar este número de épocas sem melhorar")
    ap.add_argument("--multiescala", action="store_true", help="liga o treino em várias escalas (usa mais memória de vídeo)")
    ap.add_argument("--saida", type=Path, default=RAIZ / "saida" / "rfdetr_local")
    ap.add_argument("--instalar", type=Path, default=RAIZ / "modelos", help="pasta de modelos do Pyron")
    ap.add_argument("--dados-app", type=Path, default=RAIZ / "app" / "dados_app", help="onde a aba Avaliação guarda as avaliações")
    args = ap.parse_args(argv)

    import torch
    import rfdetr

    inicio = time.time()
    agora = datetime.now()
    id_ = f"para-raios-rfdetr-local-{agora:%Y%m%d-%H%M}"
    nome_modelo = args.modelo.replace("RFDETR", "RF-DETR ")
    saida = args.saida / id_
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    dizer(f"Pyron · treino local do {nome_modelo} ({gpu})")

    # 1. dados
    ds = ler_dataset(args.dados)
    classes, treino, validacao, teste = ds["classes"], ds["treino"], ds["validacao"], ds["teste"]
    r = ds["relatorio"]
    dizer(f"Classes: {' · '.join(classes)}")
    dizer(f"Divisão: treino {len(treino)} · validação {len(validacao)} · teste {len(teste)} fotos ({r['caixas']} caixas)")
    if r["inclinadas"]:
        dizer(f"Fotos inclinadas mais de 15° (fora): {', '.join(r['inclinadas'])}")
    if r["giradas_convertidas"]:
        dizer(f"Retângulos girados convertidos para caixa reta: {r['giradas_convertidas']}")
    pasta_ds = saida / "dataset"
    shutil.rmtree(saida, ignore_errors=True)
    for sub, conj in (("train", treino), ("valid", validacao), ("test", teste)):
        escrever_coco(conj, pasta_ds / sub, classes)

    # 2. treino
    Classe = getattr(rfdetr, args.modelo)
    modelo = Classe(resolution=args.resolucao)
    dizer(f"\nTreinando até {args.epocas} épocas (lote {args.lote} × {args.acumular}, entrada {args.resolucao} px)…")
    t0 = time.time()
    # eval_backend: o padrão (vernier) e o hotcoco têm DLLs que o Controle Inteligente de Aplicativos do
    # Windows bloqueia; o faster_coco_eval carrega e calcula o mesmo mAP do COCO.
    modelo.train(dataset_dir=str(pasta_ds), epochs=args.epocas, batch_size=args.lote, grad_accum_steps=args.acumular,
                 lr=1e-4, output_dir=str(saida / "treino"), early_stopping=True, early_stopping_patience=args.paciencia,
                 multi_scale="per-batch" if args.multiescala else "off", num_workers=0, seed=2026, tensorboard=False,
                 eval_backend="faster_coco_eval")
    duracao = round((time.time() - t0) / 60, 1)
    melhor_ckpt = saida / "treino" / "checkpoint_best_total.pth"
    if melhor_ckpt.exists():
        modelo = Classe(resolution=args.resolucao, pretrain_weights=str(melhor_ckpt), trust_checkpoint=True)
    historico = historico_rfdetr(saida / "treino", duracao)
    dizer(f"Treino: {duracao} min" + (f" · melhor época {historico['melhor_epoca']}" if historico and historico["melhor_epoca"] else ""))

    # 3. exportar e conferir com o detector do Pyron
    dizer("\nExportando para ONNX…")
    pasta_export = saida / "onnx"
    modelo.export(output_dir=str(pasta_export))
    gerados = [p for p in sorted(pasta_export.rglob("*.onnx")) if "backbone" not in p.name]
    if not gerados:
        raise RuntimeError("O RF-DETR não gerou o arquivo .onnx.")
    import onnxruntime as ort

    sessao = ort.InferenceSession(str(gerados[0]), providers=["CPUExecutionProvider"])
    _, _, altura_in, largura_in = sessao.get_inputs()[0].shape
    altura_in = altura_in if isinstance(altura_in, int) else args.resolucao
    largura_in = largura_in if isinstance(largura_in, int) else args.resolucao
    nomes = [o.name for o in sessao.get_outputs()]
    nomes_saida = {"caixas": "dets" if "dets" in nomes else nomes[0], "notas": "labels" if "labels" in nomes else nomes[-1]}
    del sessao

    pasta_modelo = saida / id_
    pasta_modelo.mkdir(parents=True)
    shutil.copy(gerados[0], pasta_modelo / "modelo.onnx")

    def gravar_cartao(deslocamento, limiar, extra=None):
        c = cartao_modelo(id_, nome_modelo, classes, largura_in, altura_in, deslocamento, limiar, nomes_saida, extra)
        (pasta_modelo / "cartao.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
        return c

    notas_deslocamento = {}
    for desl in (0, -1):  # qual coluna do ONNX é qual classe: decidido na validação
        gravar_cartao(desl, 0.01)
        notas_deslocamento[desl] = avaliar(validacao, prever_com_pyron(pasta_modelo, validacao, classes), classes, 0.5)["mAP50"] or 0.0
    deslocamento = max(notas_deslocamento, key=notas_deslocamento.get)
    gravar_cartao(deslocamento, 0.01)
    prev_val = prever_com_pyron(pasta_modelo, validacao, classes)
    limiar = calibrar_limiar(validacao, prev_val)
    t0 = time.time()
    prev_teste = prever_com_pyron(pasta_modelo, teste, classes)
    ms_foto = (time.time() - t0) / max(len(teste), 1) * 1000
    teste_m = avaliar(teste, prev_teste, classes, limiar)
    teste_m.update(erro_temperatura(teste, prev_teste, limiar))
    dizer(f"Numeração das classes (mAP50 na validação): {notas_deslocamento} → {deslocamento}")
    dizer(f"Limiar de confiança escolhido na validação: {limiar}")
    dizer(f"No teste (pelo detector do Pyron): mAP50 {teste_m['mAP50']} · mAP50-95 {teste_m['mAP50-95']} · "
          f"precisão {teste_m['precisao']} · revocação {teste_m['revocacao']} · "
          f"{teste_m['acertos']} acertos, {teste_m['falsos']} falsos, {teste_m['perdidos']} perdidos · {ms_foto:.0f} ms por foto na CPU")
    dizer(f"Temperatura: erro da Tmáx na caixa do modelo × na caixa rotulada: mediana {teste_m['erro_Tmax_mediano_C']} °C, "
          f"90% das peças até {teste_m['erro_Tmax_p90_C']} °C ({teste_m['pecas_medidas']} peças medidas)")

    # 4. cartão final, instalação e avaliação
    extra = {
        "treino": {"fotos": f"{len(treino)} treino · {len(validacao)} validação · {len(teste)} teste", "onde": f"este computador ({gpu})",
                   "data": f"{agora:%d/%m/%Y}", "duracao": f"{duracao} min"},
        "metricas": {"mAP50 (teste)": teste_m["mAP50"], "mAP50-95 (teste)": teste_m["mAP50-95"], "precisão": teste_m["precisao"],
                     "revocação": teste_m["revocacao"], "peças achadas": f"{teste_m['acertos']} de {teste_m['acertos'] + teste_m['perdidos']}",
                     "erro Tmáx mediano (°C)": teste_m["erro_Tmax_mediano_C"], "erro Tmáx p90 (°C)": teste_m["erro_Tmax_p90_C"]},
        "limitacoes": [
            "Olha a imagem colorida da câmera (a paleta), não a temperatura: fotografe com a mesma paleta e faixa usadas no treino.",
            "Treinado com fotos de uma única sessão (uma subestação, uma câmera FLIR): em outros locais o acerto pode cair.",
            "Fotos com o para-raios inclinado mais de 15° ficaram fora do treino.",
        ],
    }
    gravar_cartao(deslocamento, limiar, extra)
    relatorio = {"teste": teste_m, "limiar": limiar, "deslocamento_por_validacao": notas_deslocamento, "ms_por_foto_cpu": round(ms_foto, 1),
                 "dados": {k: v for k, v in r.items()}, "configuracao": vars(args) | {"dados": str(args.dados), "saida": str(args.saida),
                                                                                   "instalar": str(args.instalar), "dados_app": str(args.dados_app)}}
    (pasta_modelo / "relatorio.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    destino = args.instalar / id_
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(pasta_modelo, destino)
    dizer(f"\nModelo instalado no Pyron: {destino}")

    nome_aval = f"{nome_modelo} (local)"
    resumo = {
        "configuracao": {"epocas_rfdetr": args.epocas, "resolucao": args.resolucao, "lote": args.lote, "acumular": args.acumular},
        "limiares": {nome_aval: limiar},
        "formato_anotacoes": "COCO 1.0 (.json do CVAT)",
        "classes": classes,
        "fotos": {"treino": [a.nome for a in treino], "validacao": [a.nome for a in validacao], "teste": [a.nome for a in teste]},
        "teste": {nome_aval: teste_m},
        "ms_por_foto": {nome_aval: round(ms_foto, 1)},
        "historico": {nome_aval: historico} if historico else {},
        "gpu": gpu,
    }
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w") as z:
        z.writestr("resumo.json", json.dumps(resumo, ensure_ascii=False))
        for inicio_bloco in range(0, len(teste), 6):
            fim = min(inicio_bloco + 6, len(teste))
            png = figura_teste(teste[inicio_bloco:fim], prev_teste[inicio_bloco:fim], classes, limiar, f"{nome_modelo} · fotos de teste")
            z.writestr(f"teste_{inicio_bloco + 1:02d}_a_{fim:02d}.png", png)
    from app.avaliacoes import Avaliacoes

    def nao_instalar(_dados: bytes) -> str:
        raise ValueError("o modelo já foi instalado")

    id_aval = Avaliacoes(lambda: args.dados_app, nao_instalar).importar(pacote.getvalue(), f"treino local {agora:%d/%m/%Y %H:%M}")["avaliacao"]
    dizer(f"Avaliação gravada: aba Avaliação ({id_aval})")
    dizer(f"Tempo total: {(time.time() - inicio) / 60:.1f} min")
    return {"modelo": id_, "avaliacao": id_aval, "teste": teste_m, "limiar": limiar}


if __name__ == "__main__":
    main()
