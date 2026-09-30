"""Comparação de detectores: modelo trivial, métricas completas e figuras (sem PyTorch).

Usado pelo caderno ``ml/notebooks/Pyron_comparar_modelos.ipynb``. Tudo aqui trabalha na grade
da matriz de temperatura (160×120 na FLIR C5) e com previsões no formato
``(caixas [N,4] x0,y0,x1,y1, pontuações [N], classes [N])`` por imagem.

Métricas
- IoU: sobreposição entre a caixa prevista e a rotulada (0 a 1).
- Acerto: mesma classe e IoU ≥ 0,5; cada rótulo casa com no máximo uma previsão.
- Precisão, revocação e F1 no limiar de confiança de uso.
- AP50 por classe e mAP50; mAP50-95 (média de IoU 0,50 a 0,95), que cobra caixas justas.
- Erro da Tmáx: diferença entre a temperatura máxima na caixa prevista e na rotulada (°C).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np

from ml import avaliacao

LIMIARES_IOU = np.round(np.arange(0.5, 0.96, 0.05), 2)


# ---------------------------------------------------------------- divisão

def dividir(amostras, modo: str = "cvat", frac_validacao: float = 0.15):
    """Treino, validação e teste.

    ``cvat``: teste = parte "teste" do CVAT; ``sessao``: teste pela divisão por sessão do Pyron.
    A validação (para escolher a melhor época) sai do treino como um bloco contínuo no tempo, para
    fotos quase iguais não ficarem dos dois lados.
    """
    from ml import dados

    if modo == "cvat" and any(a.subconjunto == "teste" for a in amostras):
        treino = [a for a in amostras if a.subconjunto != "teste"]
        teste = [a for a in amostras if a.subconjunto == "teste"]
    else:
        treino, teste, _ = dados.dividir(amostras)
    ordem = sorted(treino, key=lambda a: (a.data_hora or datetime.min, a.nome))
    n_val = max(1, round(frac_validacao * len(ordem)))
    return ordem[:-n_val], ordem[-n_val:], teste


# ---------------------------------------------------------------- modelo trivial

class ModeloTrivial:
    """Não olha a imagem: prevê, em toda foto, a caixa média de cada classe vista no treino.

    É o piso da comparação. Um modelo que aprende de verdade precisa ficar muito acima dele.
    As posições são guardadas em coordenadas relativas (0 a 1), então valem para fotos em pé e deitadas.
    """

    def __init__(self):
        self.caixas: dict[int, np.ndarray] = {}

    def ajustar(self, treino) -> "ModeloTrivial":
        por_classe: dict[int, list] = {}
        for a in treino:
            h, w = a.temperatura.shape
            for c, k in zip(a.caixas, a.classes):
                por_classe.setdefault(int(k), []).append(np.asarray(c, dtype=float) / [w, h, w, h])
        self.caixas = {k: np.mean(v, axis=0) for k, v in por_classe.items()}
        return self

    def prever(self, amostras):
        saida = []
        for a in amostras:
            h, w = a.temperatura.shape
            ks = sorted(self.caixas)
            caixas = np.array([self.caixas[k] * [w, h, w, h] for k in ks]).reshape(-1, 4)
            saida.append((caixas, np.full(len(ks), 0.5), np.array(ks, dtype=np.int64)))
        return saida


# ---------------------------------------------------------------- casamento e métricas

def casar(gt_caixas, gt_classes, p_caixas, p_pont, p_classes, limiar: float = 0.5, iou_min: float = 0.5):
    """Acertos, falsos e perdidos numa imagem, com as previsões acima do limiar de confiança.

    Devolve (acertos [(i_prev, i_rot, iou)], falsos [i_prev], perdidos [i_rot]).
    """
    usar = np.where(np.asarray(p_pont) >= limiar)[0]
    usar = usar[np.argsort(-np.asarray(p_pont)[usar])]
    livres = set(range(len(gt_caixas)))
    acertos, falsos = [], []
    for i in usar:
        candidatos = [j for j in livres if int(gt_classes[j]) == int(p_classes[i])]
        if candidatos:
            ious = avaliacao.iou(np.asarray(p_caixas[i:i + 1], dtype=float), np.asarray(gt_caixas[candidatos], dtype=float))[0]
            melhor = int(np.argmax(ious))
            if ious[melhor] >= iou_min:
                acertos.append((int(i), candidatos[melhor], float(ious[melhor])))
                livres.discard(candidatos[melhor])
                continue
        falsos.append(int(i))
    return acertos, falsos, sorted(livres)


def _ap(amostras, previsoes, k: int, iou_min: float) -> float | None:
    """AP de uma classe num limiar de IoU (todas as confianças, casamento guloso por pontuação)."""
    acertos, pontuacoes, total = [], [], 0
    for a, (pc, pp, pk) in zip(amostras, previsoes):
        gt = a.caixas[a.classes == k]
        total += len(gt)
        sel = np.where(np.asarray(pk) == k)[0]
        sel = sel[np.argsort(-np.asarray(pp)[sel])]
        livres = np.ones(len(gt), dtype=bool)
        for i in sel:
            ok = False
            if livres.any():
                ious = avaliacao.iou(np.asarray(pc[i:i + 1], dtype=float), np.asarray(gt, dtype=float))[0]
                ious[~livres] = -1
                j = int(np.argmax(ious))
                if ious[j] >= iou_min:
                    livres[j] = False
                    ok = True
            acertos.append(ok)
            pontuacoes.append(float(pp[i]))
    return avaliacao.precisao_media(acertos, pontuacoes, total)


def avaliar(amostras, previsoes, classes, nomes, limiar: float = 0.5) -> dict:
    """Todas as métricas de um modelo no conjunto de teste."""
    por_classe, aps50, aps5095 = {}, [], []
    for k, c in enumerate(classes):
        ap_limiares = [_ap(amostras, previsoes, k, t) for t in LIMIARES_IOU]
        ap50 = ap_limiares[0]
        validos = [v for v in ap_limiares if v is not None]
        ap5095 = float(np.mean(validos)) if validos else None
        if ap50 is not None:
            aps50.append(ap50)
            aps5095.append(ap5095)
        por_classe[nomes.get(c, c)] = {"AP50": _r(ap50), "AP50-95": _r(ap5095)}

    tp = fp = fn = 0
    ious = []
    tp_classe = {k: 0 for k in range(len(classes))}
    gt_classe = {k: 0 for k in range(len(classes))}
    for a, (pc, pp, pk) in zip(amostras, previsoes):
        acertos, falsos, perdidos = casar(a.caixas, a.classes, pc, pp, pk, limiar)
        tp, fp, fn = tp + len(acertos), fp + len(falsos), fn + len(perdidos)
        ious += [v for _, _, v in acertos]
        for _, j, _ in acertos:
            tp_classe[int(a.classes[j])] += 1
        for k in a.classes:
            gt_classe[int(k)] += 1
    for k, c in enumerate(classes):
        por_classe[nomes.get(c, c)]["revocacao"] = _r(tp_classe[k] / gt_classe[k]) if gt_classe[k] else None

    precisao = tp / (tp + fp) if tp + fp else 0.0
    revocacao = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precisao * revocacao / (precisao + revocacao) if precisao + revocacao else 0.0
    temp = avaliacao.avaliar(amostras, previsoes, classes, limiar_uso=limiar)
    return {
        "mAP50": _r(np.mean(aps50)) if aps50 else None,
        "mAP50-95": _r(np.mean(aps5095)) if aps5095 else None,
        "precisao": _r(precisao),
        "revocacao": _r(revocacao),
        "F1": _r(f1),
        "IoU_medio_acertos": _r(np.mean(ious)) if ious else None,
        "acertos": tp, "falsos": fp, "perdidos": fn,
        "erro_Tmax_mediano_C": temp.get("erro_tmax_mediano_c"),
        "erro_Tmax_p90_C": temp.get("erro_tmax_p90_c"),
        "por_classe": por_classe,
    }


def _r(v, casas: int = 3):
    return None if v is None else round(float(v), casas)


# ---------------------------------------------------------------- figuras

CORES_CLASSE = ["#35d0a0", "#ffb020", "#4da3ff", "#ff5d8f", "#c38bff", "#9be15d"]


def figura_comparacao(amostras, previsoes_por_modelo: dict, classes, nomes, limiar: float, caminho: Path | None = None, n: int = 8):
    """Uma linha por imagem de teste, uma coluna por modelo.

    Verde: acerto (classe certa e IoU ≥ 0,5). Vermelho: caixa falsa. Amarelo tracejado: componente
    rotulado que o modelo não achou.
    """
    import matplotlib.pyplot as plt

    from nucleo.detectores import preparo

    modelos = list(previsoes_por_modelo)
    n = min(n, len(amostras))
    sigla = {k: abreviar(nomes.get(c, c)) for k, c in enumerate(classes)}
    fig, eixos = plt.subplots(n, len(modelos), figsize=(4.2 * max(len(modelos), 2), 3.6 * n), squeeze=False)
    for linha in range(n):
        a = amostras[linha]
        lo, hi = preparo.faixa(a.temperatura)
        for col, modelo in enumerate(modelos):
            ax = eixos[linha][col]
            ax.imshow(a.temperatura, cmap="inferno", vmin=lo, vmax=hi)
            pc, pp, pk = previsoes_por_modelo[modelo][linha]
            acertos, falsos, perdidos = casar(a.caixas, a.classes, pc, pp, pk, limiar)
            for i, _, _ in acertos:
                _caixa(ax, pc[i], "#2bd67b", f"{sigla[int(pk[i])]} {pp[i]:.2f}")
            for i in falsos:
                _caixa(ax, pc[i], "#ff4d4d", f"{sigla[int(pk[i])]} {pp[i]:.2f}")
            for j in perdidos:
                _caixa(ax, a.caixas[j], "#ffd400", sigla[int(a.classes[j])], tracejado=True)
            ax.set_title(f"{modelo} · {a.nome}\n{len(acertos)} acertos · {len(falsos)} falsos · {len(perdidos)} perdidos", fontsize=8)
            ax.axis("off")
    legenda = "  ·  ".join(f"{s} = {nomes.get(classes[k], classes[k])}" for k, s in sigla.items())
    fig.suptitle("Verde: acerto (classe certa, IoU ≥ 0,5)   Vermelho: caixa falsa   Amarelo tracejado: não encontrado\n" + legenda, fontsize=9)
    fig.tight_layout()
    if caminho:
        fig.savefig(caminho, dpi=110)
    return fig


def abreviar(nome: str) -> str:
    """ "Terminal Superior" -> "TS"; "Para-raio" -> "PR"."""
    partes = [p for p in nome.replace("-", " ").split() if p]
    return "".join(p[0] for p in partes).upper()[:3] if len(partes) > 1 else nome[:3].upper()


def _caixa(ax, c, cor, texto, tracejado=False):
    import matplotlib.pyplot as plt

    ax.add_patch(plt.Rectangle((c[0], c[1]), c[2] - c[0], c[3] - c[1], fill=False, ec=cor, lw=1.4, ls="--" if tracejado else "-"))
    if texto:
        ax.text(c[0], c[1] - 1, texto, color="white", fontsize=5.5, backgroundcolor="#000000aa")


def figura_rotulos(amostras, classes, nomes, caminho: Path | None = None, n: int = 8):
    """Exemplos do conjunto com os rótulos, para conferir se as caixas caem no lugar certo."""
    import matplotlib.pyplot as plt

    from nucleo.detectores import preparo

    n = min(n, len(amostras))
    colunas = 4
    linhas = int(np.ceil(n / colunas))
    fig, eixos = plt.subplots(linhas, colunas, figsize=(4.2 * colunas, 3.8 * linhas), squeeze=False)
    for i, ax in enumerate(eixos.ravel()):
        ax.axis("off")
        if i >= n:
            continue
        a = amostras[i]
        lo, hi = preparo.faixa(a.temperatura)
        ax.imshow(a.temperatura, cmap="inferno", vmin=lo, vmax=hi)
        for c, k in zip(a.caixas, a.classes):
            _caixa(ax, c, CORES_CLASSE[int(k) % len(CORES_CLASSE)], "")
        ax.set_title(a.nome, fontsize=8)
    fig.legend(handles=[plt.Line2D([], [], color=CORES_CLASSE[k % len(CORES_CLASSE)], label=nomes.get(c, c)) for k, c in enumerate(classes)],
               loc="lower center", ncol=len(classes))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    if caminho:
        fig.savefig(caminho, dpi=100)
    return fig


def figura_curvas(historicos: dict, caminho: Path | None = None):
    """Perda de treino e de validação por época, e mAP50 na validação, lado a lado para cada modelo."""
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.2))
    cores = ["#3F50D6", "#E8751A", "#179B67", "#7D5CF0"]
    for cor, (nome, h) in zip(cores, historicos.items()):
        epocas = np.arange(1, len(h["perda_treino"]) + 1)
        ax1.plot(epocas, h["perda_treino"], color=cor, label=f"{nome}: treino")
        ax1.plot(epocas, h["perda_validacao"], color=cor, ls="--", label=f"{nome}: validação")
        ax2.plot(h["epocas_map"], h["map50_validacao"], color=cor, marker="o", ms=3, label=nome)
        if h.get("melhor_epoca"):
            ax2.axvline(h["melhor_epoca"], color=cor, ls=":", lw=1)
    ax1.set(title="Perda (loss): menor é melhor", xlabel="época", ylabel="perda")
    ax2.set(title="mAP50 na validação: maior é melhor", xlabel="época", ylabel="mAP50", ylim=(0, 1))
    for ax in (ax1, ax2):
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    if caminho:
        fig.savefig(caminho, dpi=110)
    return fig
