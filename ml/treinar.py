"""Treina um detector de componentes com rótulos do CVAT e instala no Pyron.

Uso (na pasta do projeto):

    python -m ml.treinar --coco dados/rotulos/para_raios.zip --id para-raios-mobilenet-v1 \
        --nome "Para-raios (MobileNet)" --epocas 60

Etapas:
1. lê o COCO do CVAT e liga cada caixa à temperatura verdadeira da imagem (``ml/dados.py``);
2. separa treino e teste por sessão de captura;
3. faz o ajuste fino de um Faster R-CNN com MobileNetV3 pré-treinado (torchvision, BSD);
4. mede AP50, revocação e erro da temperatura máxima no teste (``ml/avaliacao.py``);
5. exporta ``modelo.onnx`` no contrato do aplicativo, confere o ONNX contra o PyTorch e grava
   ``cartao.json``, ``relatorio.json`` e uma figura com as previsões do teste em ``modelos/<id>/``.

A imagem que a rede vê é a temperatura normalizada (``nucleo/detectores/preparo.py``), a mesma
preparação que o aplicativo usa na hora de detectar.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from ml import avaliacao, dados  # noqa: E402
from nucleo.detectores import preparo  # noqa: E402

LARGURA, ALTURA = 640, 480
NORMALIZACAO = "por_imagem"


# ---------------------------------------------------------------- conjunto de dados


def _recorte_aleatorio(norm: np.ndarray, caixas: np.ndarray, rng, escala_max: float = 1.3):
    """Aproxima (zoom) uma região aleatória; descarta caixas que ficam quase todas de fora."""
    from PIL import Image

    h, w = norm.shape
    s = rng.uniform(1.0, escala_max)
    cw, ch = w / s, h / s
    x0, y0 = rng.uniform(0, w - cw), rng.uniform(0, h - ch)
    img = np.asarray(Image.fromarray(norm, mode="F").crop((x0, y0, x0 + cw, y0 + ch)).resize((w, h), Image.BILINEAR), dtype=np.float32)
    nov = (caixas - [x0, y0, x0, y0]) * s
    area_antes = (nov[:, 2] - nov[:, 0]) * (nov[:, 3] - nov[:, 1])
    nov = np.clip(nov, 0, [w, h, w, h])
    area_depois = (nov[:, 2] - nov[:, 0]) * (nov[:, 3] - nov[:, 1])
    manter = area_depois >= 0.4 * np.maximum(area_antes, 1e-9)
    return img, nov, manter


class ConjuntoTermico:
    """Amostras prontas para o PyTorch: imagem [3, A, L] e alvos no formato do torchvision."""

    def __init__(self, amostras, aumentar: bool, semente: int = 2026):
        self.amostras, self.aumentar = amostras, aumentar
        self.rng = np.random.default_rng(semente)

    def __len__(self) -> int:
        return len(self.amostras)

    def __getitem__(self, i):
        import torch

        a = self.amostras[i]
        h_m, w_m = a.temperatura.shape
        ajuste = (0.0, 0.0)
        if self.aumentar:
            ajuste = (self.rng.uniform(-0.08, 0.08), self.rng.uniform(-0.08, 0.08))
        norm = preparo.para_rede(a.temperatura, LARGURA, ALTURA, modo=NORMALIZACAO, ajuste_faixa=ajuste)
        caixas = a.caixas * [LARGURA / w_m, ALTURA / h_m, LARGURA / w_m, ALTURA / h_m]
        classes = a.classes.copy()
        if self.aumentar:
            if self.rng.random() < 0.5:
                norm = norm[:, ::-1].copy()
                caixas = caixas[:, [2, 1, 0, 3]] * [-1, 1, -1, 1] + [LARGURA, 0, LARGURA, 0]
            if self.rng.random() < 0.5 and len(caixas):
                norm, caixas, manter = _recorte_aleatorio(norm, caixas, self.rng)
                caixas, classes = caixas[manter], classes[manter]
            norm = np.clip(norm + self.rng.normal(0, 0.01, norm.shape).astype(np.float32), 0, 1)
        imagem = torch.from_numpy(np.stack([norm] * 3, axis=0).astype(np.float32))
        alvo = {
            "boxes": torch.as_tensor(np.asarray(caixas, dtype=np.float32).reshape(-1, 4)),
            "labels": torch.as_tensor(np.asarray(classes, dtype=np.int64) + 1),  # 0 é o fundo no torchvision
        }
        return imagem, alvo


# ---------------------------------------------------------------- modelo


def criar_modelo(n_classes: int, pre_treinado: bool = True):
    from torchvision.models.detection import fasterrcnn_mobilenet_v3_large_fpn
    from torchvision.models.detection.anchor_utils import AnchorGenerator
    from torchvision.models.detection.faster_rcnn import FastRCNNPredictor

    modelo = fasterrcnn_mobilenet_v3_large_fpn(
        weights="DEFAULT" if pre_treinado else None,
        weights_backbone="DEFAULT" if pre_treinado else None,
        min_size=ALTURA,
        max_size=LARGURA,
        box_detections_per_img=100,
    )
    # Âncoras menores: terminais e conexões ocupam poucos pixels no sensor de 160×120.
    modelo.rpn.anchor_generator = AnchorGenerator(sizes=((16, 32, 64, 128, 256),) * 3, aspect_ratios=((0.5, 1.0, 2.0),) * 3)
    entrada = modelo.roi_heads.box_predictor.cls_score.in_features
    modelo.roi_heads.box_predictor = FastRCNNPredictor(entrada, n_classes + 1)
    return modelo


def _juntar(lote):
    return tuple(zip(*lote))


class Progresso:
    """Grava o andamento num .json que o aplicativo lê (tela Modelos › Treinamentos) e mostra no console."""

    def __init__(self, arquivo: Path | None):
        self.arquivo = arquivo
        self.estado = {"etapa": "iniciando", "mensagem": "Preparando", "epoca": 0, "epocas": 0, "perda": [], "inicio": time.time(), "pid": os.getpid()}
        self._ultimo = 0.0

    def atualizar(self, forcar: bool = True, **campos) -> None:
        self.estado.update(campos)
        self.estado["atualizado_em"] = time.time()
        agora = time.time()
        if self.arquivo and (forcar or agora - self._ultimo > 5):
            self._ultimo = agora
            temporario = self.arquivo.with_suffix(".tmp")
            temporario.write_text(json.dumps(self.estado, ensure_ascii=False), encoding="utf-8")
            os.replace(temporario, self.arquivo)


def _restante(inicio: float, feitas: int, total: int) -> str:
    if feitas == 0:
        return ""
    s = (time.time() - inicio) / feitas * (total - feitas)
    return f"{int(s // 60)} min {int(s % 60):02d} s" if s >= 60 else f"{int(s)} s"


def treinar_modelo(modelo, treino, epocas: int, lote: int, dispositivo, registrar=print, progresso: Progresso | None = None):
    import torch

    carregador = torch.utils.data.DataLoader(ConjuntoTermico(treino, aumentar=True), batch_size=lote, shuffle=True, collate_fn=_juntar)
    parametros = [p for p in modelo.parameters() if p.requires_grad]
    otimizador = torch.optim.SGD(parametros, lr=0.01, momentum=0.9, weight_decay=1e-4)
    passos_total = max(1, epocas * len(carregador))
    aquecimento = min(100, passos_total // 10 + 1)
    agenda = torch.optim.lr_scheduler.LambdaLR(
        otimizador,
        lambda p: (p + 1) / aquecimento if p < aquecimento else 0.5 * (1 + math.cos(math.pi * (p - aquecimento) / max(1, passos_total - aquecimento))),
    )
    modelo.to(dispositivo).train()
    historico = []
    inicio = time.time()
    for epoca in range(1, epocas + 1):
        soma, n = 0.0, 0
        for imagens, alvos in carregador:
            imagens = [im.to(dispositivo) for im in imagens]
            alvos = [{k: v.to(dispositivo) for k, v in t.items()} for t in alvos]
            perdas = modelo(imagens, alvos)
            total = sum(perdas.values())
            otimizador.zero_grad()
            total.backward()
            torch.nn.utils.clip_grad_norm_(parametros, 10.0)
            otimizador.step()
            agenda.step()
            soma += float(total)
            n += 1
            if progresso:
                progresso.atualizar(forcar=False)  # sinal de vida durante épocas longas (CPU)
        historico.append(round(soma / max(n, 1), 4))
        restante = _restante(inicio, epoca, epocas)
        if progresso:
            progresso.atualizar(etapa="treinando", mensagem=f"Época {epoca} de {epocas}", epoca=epoca, perda=historico, restante=restante)
        registrar(f"  época {epoca:3d}/{epocas}  perda {historico[-1]:.4f}" + (f"  faltam ~{restante}" if restante and epoca < epocas else ""))
    return historico


def prever(modelo, amostras, dispositivo):
    """Previsões na grade da matriz de temperatura de cada amostra."""
    import torch

    modelo.eval()
    saida = []
    with torch.no_grad():
        for a in amostras:
            h_m, w_m = a.temperatura.shape
            norm = preparo.para_rede(a.temperatura, LARGURA, ALTURA, modo=NORMALIZACAO)
            img = torch.from_numpy(np.stack([norm] * 3, axis=0)).to(dispositivo)
            r = modelo([img])[0]
            caixas = r["boxes"].cpu().numpy() * [w_m / LARGURA, h_m / ALTURA, w_m / LARGURA, h_m / ALTURA]
            saida.append((caixas, r["scores"].cpu().numpy(), r["labels"].cpu().numpy() - 1))
    return saida


# ---------------------------------------------------------------- exportação


def exportar_onnx(modelo, caminho: Path) -> None:
    """ONNX no contrato do aplicativo: caixas normalizadas, pontuações e classes (sem o fundo)."""
    import torch

    class Exportavel(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, imagem):
            r = self.m([imagem[0]])[0]
            escala = torch.tensor([LARGURA, ALTURA, LARGURA, ALTURA], dtype=r["boxes"].dtype)
            return (r["boxes"] / escala).unsqueeze(0), r["scores"].unsqueeze(0), (r["labels"] - 1).unsqueeze(0)

    modelo = modelo.to("cpu").eval()
    exemplo = torch.rand(1, 3, ALTURA, LARGURA)
    argumentos = dict(
        input_names=["imagem"],
        output_names=["caixas", "pontuacoes", "classes"],
        opset_version=17,
        dynamic_axes={"caixas": {1: "n"}, "pontuacoes": {1: "n"}, "classes": {1: "n"}},
    )
    try:
        torch.onnx.export(Exportavel(modelo), (exemplo,), str(caminho), dynamo=False, **argumentos)
    except TypeError:  # versões antigas do PyTorch não têm o parâmetro dynamo
        torch.onnx.export(Exportavel(modelo), (exemplo,), str(caminho), **argumentos)


def conferir_onnx(caminho: Path, modelo, amostras, limiar: float) -> dict:
    """O ONNX tem de dar as mesmas detecções que o PyTorch (mesmas caixas acima do limiar)."""
    import onnxruntime as ort
    import torch

    sessao = ort.InferenceSession(str(caminho), providers=["CPUExecutionProvider"])
    modelo = modelo.to("cpu").eval()
    diferencas, contagens = [], []
    for a in amostras[:5]:
        norm = preparo.para_rede(a.temperatura, LARGURA, ALTURA, modo=NORMALIZACAO)
        entrada = preparo.tensor_entrada(norm)
        caixas_o, pont_o, _ = sessao.run(["caixas", "pontuacoes", "classes"], {"imagem": entrada})
        with torch.no_grad():
            r = modelo([torch.from_numpy(entrada[0])])[0]
        caixas_t = r["boxes"].numpy() / [LARGURA, ALTURA, LARGURA, ALTURA]
        so, st = pont_o[0] >= limiar, r["scores"].numpy() >= limiar
        contagens.append((int(so.sum()), int(st.sum())))
        if so.sum() and so.sum() == st.sum():
            diferencas.append(float(np.abs(caixas_o[0][so] - caixas_t[st]).max()))
    return {"deteccoes_onnx_vs_torch": contagens, "maior_diferenca_caixa": max(diferencas) if diferencas else None}


def figura_previsoes(amostras, previsoes, classes, limiar: float, caminho: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = min(6, len(amostras))
    if n == 0:
        return
    fig, eixos = plt.subplots(1, n, figsize=(4 * n, 3.4), squeeze=False)
    for ax, a, (cx, pt, cl) in zip(eixos[0], amostras, previsoes):
        lo, hi = preparo.faixa(a.temperatura)
        ax.imshow(a.temperatura, cmap="inferno", vmin=lo, vmax=hi)
        for c in a.caixas:
            ax.add_patch(plt.Rectangle((c[0], c[1]), c[2] - c[0], c[3] - c[1], fill=False, ec="#35d0a0", lw=1.2, ls="--"))
        for c, p, k in zip(cx, pt, cl):
            if p >= limiar:
                ax.add_patch(plt.Rectangle((c[0], c[1]), c[2] - c[0], c[3] - c[1], fill=False, ec="#ff7a3c", lw=1.4))
                ax.text(c[0], c[1] - 1, f"{classes[int(k)]} {p:.2f}", color="white", fontsize=6, backgroundcolor="#000000aa")
        ax.set_title(a.nome, fontsize=8)
        ax.axis("off")
    fig.suptitle("Tracejado verde: rótulo  ·  laranja: previsão do modelo", fontsize=9)
    fig.tight_layout()
    fig.savefig(caminho, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------- principal


def imprimir_analise(r: dict) -> None:
    """O relatório de ``dados.analisar`` em texto, para o console."""
    print(f"\nArquivo de rótulos: {r['arquivo']}")
    print(f"  imagens no arquivo: {r['imagens_no_arquivo']}   rotuladas: {r['imagens_rotuladas']}   "
          f"achadas na pasta: {r['imagens_encontradas']}   prontas para treinar: {r['imagens_utilizaveis']}")
    tipos = ", ".join(f"{v} {k}{'s' if v != 1 else ''}" for k, v in r["tipos"].items() if v)
    print(f"  rótulos: {r['rotulos']} ({tipos})   sessões de fotos: {r['sessoes']}")
    if r["subconjuntos"]:
        print("  divisão do CVAT: " + ", ".join(f"{k} {v}" for k, v in r["subconjuntos"].items()))
    print("  por classe:")
    for c in r["classes"]:
        print(f"    {c['nome']:<28} {c['rotulos']:>5} rótulos em {c['imagens']:>4} imagens")
    for aviso in r["avisos"]:
        print(f"  ! {aviso}")


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--coco", required=True, type=Path, help="COCO 1.0 exportado do CVAT (.json ou .zip)")
    ap.add_argument("--imagens", type=Path, default=RAIZ / "dados" / "sciencedb_10185", help="pasta com as imagens rotuladas")
    ap.add_argument("--id", help="identificador do modelo (nome da pasta)")
    ap.add_argument("--nome", help="nome exibido no aplicativo")
    ap.add_argument("--epocas", type=int, default=60)
    ap.add_argument("--lote", type=int, default=4)
    ap.add_argument("--limiar", type=float, default=0.5, help="confiança mínima usada pelo aplicativo")
    ap.add_argument("--divisao", choices=["sessao", "cvat"], default="sessao", help="sessao (padrão, mais honesta) ou a divisão feita no CVAT")
    ap.add_argument("--destino", type=Path, default=RAIZ / "modelos", help="pasta de modelos do aplicativo")
    ap.add_argument("--progresso", type=Path, help="arquivo .json de andamento (usado pelo aplicativo)")
    ap.add_argument("--so-analisar", action="store_true", help="só mostrar o relatório dos rótulos, sem treinar")
    ap.add_argument("--sem-pre-treino", action="store_true", help="não baixar pesos pré-treinados (só para testes)")
    args = ap.parse_args(argv)

    if args.so_analisar:
        relatorio = dados.analisar(args.coco, args.imagens)
        imprimir_analise(relatorio)
        return relatorio
    if not args.id or not args.nome:
        ap.error("--id e --nome são obrigatórios para treinar")

    progresso = Progresso(args.progresso)
    try:
        return _treinar(args, progresso)
    except Exception as erro:
        progresso.atualizar(etapa="erro", mensagem=str(erro) or erro.__class__.__name__)
        raise


def _treinar(args, progresso: Progresso) -> dict:
    import torch

    torch.manual_seed(2026)
    dispositivo = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    inicio = time.time()
    nome_disp = torch.cuda.get_device_name(0) if dispositivo.type == "cuda" else "processador (sem GPU)"
    print(f"Dispositivo: {nome_disp}")
    progresso.atualizar(etapa="lendo", mensagem="Lendo rótulos e temperaturas", dispositivo=nome_disp, epocas=args.epocas)

    amostras, classes, nomes = dados.ler_coco(args.coco, args.imagens)
    treino, teste, divisao = dados.dividir(amostras, modo=args.divisao)
    n_rotulos = {nomes[c]: int(sum((a.classes == k).sum() for a in amostras)) for k, c in enumerate(classes)}
    print(f"{len(amostras)} imagens rotuladas ({len(treino)} treino, {len(teste)} teste; {divisao['criterio']})")
    print(f"Rótulos por classe: {n_rotulos}")
    progresso.atualizar(etapa="treinando", mensagem=f"Treinando com {len(treino)} imagens", imagens_treino=len(treino), imagens_teste=len(teste),
                        divisao=divisao["criterio"], rotulos_por_classe=n_rotulos)

    modelo = criar_modelo(len(classes), pre_treinado=not args.sem_pre_treino)
    historico = treinar_modelo(modelo, treino, args.epocas, args.lote, dispositivo, progresso=progresso)

    progresso.atualizar(etapa="avaliando", mensagem=f"Avaliando em {len(teste)} imagens que o modelo não viu")
    previsoes = prever(modelo.to(dispositivo), teste, dispositivo) if teste else []
    metricas = avaliacao.avaliar(teste, previsoes, classes, limiar_uso=args.limiar) if teste else {}
    print(f"Teste: mAP50 {metricas.get('mAP50')}, erro Tmáx mediano {metricas.get('erro_tmax_mediano_c')} °C")

    progresso.atualizar(etapa="exportando", mensagem="Exportando e conferindo o modelo")
    pasta = args.destino / args.id
    pasta.mkdir(parents=True, exist_ok=True)
    torch.save(modelo.state_dict(), pasta / "pesos.pt")
    exportar_onnx(modelo, pasta / "modelo.onnx")
    conferencia = conferir_onnx(pasta / "modelo.onnx", modelo, teste or treino, args.limiar)
    print(f"Conferência ONNX × PyTorch: {conferencia}")
    figura_previsoes(teste, previsoes, [nomes[c] for c in classes], args.limiar, pasta / "previsoes_teste.png")

    pequeno = len(amostras) < 60
    cartao = {
        "id": args.id,
        "nome": args.nome,
        "arquitetura": "Faster R-CNN, MobileNetV3-Large FPN (torchvision)",
        "versao": "1.0",
        "descricao": f"Detecta {', '.join(nomes[c] for c in classes)} em termogramas. Treinado com rótulos do CVAT sobre a temperatura medida.",
        "classes": classes,
        "nomes": nomes,
        "arquivo": "modelo.onnx",
        "entrada": {"largura": LARGURA, "altura": ALTURA, "normalizacao": NORMALIZACAO, "media": [0, 0, 0], "desvio": [1, 1, 1]},
        "limiar_confianca": args.limiar,
        "treino": {
            "imagens": f"{len(treino)} treino, {len(teste)} teste",
            "separacao": divisao["criterio"],
            "epocas": args.epocas,
            "data": date.today().isoformat(),
        },
        "metricas": {
            "mAP50 (teste)": metricas.get("mAP50"),
            "erro Tmáx mediano (°C)": metricas.get("erro_tmax_mediano_c"),
        },
        "limitacoes": [
            "Treinado com imagens de uma única subestação e uma única câmera (FLIR C5).",
            "Dataset de estudo com licença não comercial: não usar este modelo em produto vendido.",
        ]
        + (["Poucas imagens rotuladas: métricas apenas indicativas."] if pequeno else []),
    }
    (pasta / "cartao.json").write_text(json.dumps(cartao, ensure_ascii=False, indent=2), encoding="utf-8")
    relatorio = {
        "rotulos_por_classe": n_rotulos,
        "divisao": divisao,
        "perda_por_epoca": historico,
        "metricas_teste": metricas,
        "conferencia_onnx": conferencia,
        "dispositivo": str(dispositivo),
        "duracao_s": round(time.time() - inicio, 1),
    }
    (pasta / "relatorio.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    progresso.atualizar(etapa="pronto", mensagem="Modelo instalado", metricas=metricas_resumo(metricas), pasta=str(pasta), duracao_s=relatorio["duracao_s"])
    print(f"Modelo instalado em {pasta} ({relatorio['duracao_s']} s). Abra o aplicativo, aba Modelos.")
    return relatorio


def metricas_resumo(metricas: dict) -> dict:
    """O que a tela mostra ao fim do treino."""
    return {
        "mAP50": metricas.get("mAP50"),
        "revocacao": metricas.get("revocacao_no_limiar"),
        "erro_tmax_mediano_c": metricas.get("erro_tmax_mediano_c"),
        "erro_tmax_p90_c": metricas.get("erro_tmax_p90_c"),
        "por_classe": metricas.get("por_classe"),
    }


if __name__ == "__main__":
    main()
