"""Medidas de um detector de componentes em termogramas.

- **AP50 por classe**: precisão média com sobreposição (IoU) de pelo menos 0,5 entre a caixa
  prevista e a rotulada; é a medida padrão de detecção (interpolação de todos os pontos, VOC).
- **Revocação no limiar de uso**: fração dos componentes rotulados que o modelo encontra com a
  confiança que o aplicativo usa.
- **Erro da temperatura máxima**: para cada componente encontrado, a diferença entre a Tmáx
  medida dentro da caixa prevista e dentro da caixa rotulada. É a medida que importa para o
  produto: uma caixa um pouco torta que mede a temperatura certa serve.
"""

from __future__ import annotations

import numpy as np

from nucleo.analise import medir


def iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU entre cada caixa de ``a`` [N,4] e cada caixa de ``b`` [M,4] -> [N, M]."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x0 = np.maximum(a[:, None, 0], b[None, :, 0])
    y0 = np.maximum(a[:, None, 1], b[None, :, 1])
    x1 = np.minimum(a[:, None, 2], b[None, :, 2])
    y1 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / np.maximum(area_a[:, None] + area_b[None, :] - inter, 1e-9)


def precisao_media(acertos: list[bool], pontuacoes: list[float], total_rotulos: int) -> float | None:
    """AP com interpolação de todos os pontos."""
    if total_rotulos == 0:
        return None
    if not pontuacoes:
        return 0.0
    ordem = np.argsort(-np.asarray(pontuacoes))
    tp = np.asarray(acertos, dtype=float)[ordem]
    tp_acum, fp_acum = np.cumsum(tp), np.cumsum(1 - tp)
    revocacao = tp_acum / total_rotulos
    precisao = tp_acum / np.maximum(tp_acum + fp_acum, 1e-9)
    r = np.concatenate([[0.0], revocacao, [1.0]])
    p = np.concatenate([[0.0], precisao, [0.0]])
    for i in range(len(p) - 2, -1, -1):
        p[i] = max(p[i], p[i + 1])
    passos = np.flatnonzero(r[1:] != r[:-1])
    return float(np.sum((r[passos + 1] - r[passos]) * p[passos + 1]))


def avaliar(amostras, previsoes, classes: list[str], limiar_uso: float = 0.5, limiar_iou: float = 0.5) -> dict:
    """``previsoes[i]`` = (caixas [N,4], pontuacoes [N], classes [N]) na grade da matriz da amostra i."""
    por_classe = {k: {"acertos": [], "pontuacoes": [], "rotulos": 0, "achados_uso": 0} for k in range(len(classes))}
    erros_tmax: list[float] = []
    for amostra, (p_caixas, p_pont, p_cls) in zip(amostras, previsoes):
        temp = amostra.temperatura
        for k in range(len(classes)):
            g = amostra.caixas[amostra.classes == k]
            sel = p_cls == k
            pc, pp = p_caixas[sel], p_pont[sel]
            por_classe[k]["rotulos"] += len(g)
            usado = np.zeros(len(g), dtype=bool)
            ious = iou(pc, g)
            for j in np.argsort(-pp):
                melhor = int(np.argmax(ious[j])) if len(g) else -1
                acerto = melhor >= 0 and ious[j, melhor] >= limiar_iou and not usado[melhor]
                if acerto:
                    usado[melhor] = True
                    if pp[j] >= limiar_uso:
                        por_classe[k]["achados_uso"] += 1
                        m_prev, m_rot = medir(temp, list(pc[j])), medir(temp, list(g[melhor]))
                        if m_prev and m_rot:
                            erros_tmax.append(abs(m_prev.t_max - m_rot.t_max))
                por_classe[k]["acertos"].append(bool(acerto))
                por_classe[k]["pontuacoes"].append(float(pp[j]))

    resultado = {"por_classe": {}}
    aps = []
    for k, nome in enumerate(classes):
        c = por_classe[k]
        ap = precisao_media(c["acertos"], c["pontuacoes"], c["rotulos"])
        if ap is not None:
            aps.append(ap)
        resultado["por_classe"][nome] = {
            "rotulos": c["rotulos"],
            "AP50": None if ap is None else round(ap, 3),
            "revocacao_no_limiar": round(c["achados_uso"] / c["rotulos"], 3) if c["rotulos"] else None,
        }
    resultado["mAP50"] = round(float(np.mean(aps)), 3) if aps else None
    resultado["erro_tmax_mediano_c"] = round(float(np.median(erros_tmax)), 2) if erros_tmax else None
    resultado["erro_tmax_p90_c"] = round(float(np.percentile(erros_tmax, 90)), 2) if erros_tmax else None
    resultado["componentes_medidos"] = len(erros_tmax)
    total = sum(c["rotulos"] for c in por_classe.values())
    resultado["revocacao_no_limiar"] = round(sum(c["achados_uso"] for c in por_classe.values()) / total, 3) if total else None
    return resultado
