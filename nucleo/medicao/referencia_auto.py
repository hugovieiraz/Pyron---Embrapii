"""Referência achada sozinha na foto: um quadrado de cor forte e tamanho conhecido (post-it rosa; o do Hugo tem 8 cm).

Sem modelo: cor em HSV → maior mancha que vira um quadrilátero convexo → uma reta ajustada em cada lado com
todos os pixels da borda (precisão de fração de pixel) → os 4 cantos são os cruzamentos das retas. Os
cantos servem para os dois modos: a escala da profundidade (``medir()`` com ``referencia={"auto": ...}``) e a
homografia do plano (``plano_ref``), sem clique nenhum.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# faixas em HSV do OpenCV (H de 0 a 179). Rosa/magenta de post-it: ~320 a 350° → H 160 a 175; o neon puxa
# para o roxo (H ~145). Pele, madeira e vermelho ficam abaixo de H 10 e não entram.
CORES = {
    "postit_rosa": {"h": (140, 179), "s_min": 70, "v_min": 90},
    "postit_amarelo": {"h": (20, 35), "s_min": 90, "v_min": 120},
}
REFERENCIAS_AUTO = {
    "postit_rosa": {"nome": "post-it rosa", "cor": "postit_rosa", "lado_cm": 8.0},  # medido pelo Hugo (8 × 8)
    "postit_amarelo": {"nome": "post-it amarelo", "cor": "postit_amarelo", "lado_cm": 7.6},
}


@dataclass
class Achado:
    cantos: np.ndarray  # 4 × 2, pixels, sentido horário a partir do de cima à esquerda
    mascara: np.ndarray  # H × W, bool: o quadrilátero preenchido
    area_px: float
    retangularidade: float  # área da mancha / área do quadrilátero (1 = quadrilátero perfeito)


def achar(imagem, cor: str = "postit_rosa", area_minima: float = 0.0004) -> Achado | None:
    """Acha o quadrado de ``cor`` na imagem (PIL ou array RGB). ``None`` se não houver um convincente."""
    import cv2

    from nucleo.medicao.plano_ref import ordenar_cantos

    rgb = np.asarray(imagem.convert("RGB") if hasattr(imagem, "convert") else imagem)
    h, w = rgb.shape[:2]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    faixa = CORES[cor]
    # nota contínua de "quanto é desta cor" (a* do Lab para rosa, b* para amarelo): a borda fica onde ela cruza a
    # metade entre dentro e fora, o que anula o borrão do JPEG e do foco
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    nota = lab[..., 1] if cor == "postit_rosa" else lab[..., 2]
    m = ((hsv[..., 0] >= faixa["h"][0]) & (hsv[..., 0] <= faixa["h"][1])
         & (hsv[..., 1] >= faixa["s_min"]) & (hsv[..., 2] >= faixa["v_min"])).astype(np.uint8)
    k = max(3, (min(h, w) // 300) | 1)
    nucleo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    m = cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_OPEN, nucleo), cv2.MORPH_CLOSE, nucleo)
    contornos, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    melhor = None
    for c in sorted(contornos, key=cv2.contourArea, reverse=True)[:5]:
        area = cv2.contourArea(c)
        if area < area_minima * h * w:
            break
        casca = cv2.convexHull(c)
        quad = None
        for eps in (0.02, 0.03, 0.04, 0.06):
            a = cv2.approxPolyDP(casca, eps * cv2.arcLength(casca, True), True)
            if len(a) == 4:
                quad = a.reshape(4, 2).astype(np.float32)
                break
        if quad is None:
            continue
        area_quad = cv2.contourArea(quad)
        ret = area / max(area_quad, 1.0)
        if ret < 0.85:  # mancha que não preenche o quadrilátero: não é o post-it
            continue
        refinado = _cantos_por_retas(c.reshape(-1, 2).astype(float), quad, nota)
        try:
            cantos = ordenar_cantos(refinado)
        except ValueError:
            continue
        mascara = np.zeros((h, w), np.uint8)
        cv2.fillConvexPoly(mascara, np.round(cantos).astype(np.int32), 1)
        melhor = Achado(cantos=cantos, mascara=mascara.astype(bool), area_px=float(area_quad), retangularidade=round(float(ret), 3))
        break
    return melhor


def _cantos_por_retas(borda: np.ndarray, quad: np.ndarray, nota: np.ndarray | None = None) -> np.ndarray:
    """Cantos pelo cruzamento de 4 retas ajustadas à borda (cada ponto da borda vai para o lado mais próximo do
    quadrilátero aproximado; as pontas perto dos cantos ficam de fora). Com ``nota`` (imagem contínua da cor), cada
    ponto da borda anda pela normal até onde a nota cruza a metade entre dentro e fora (borda em fração de pixel);
    sem ela, a reta anda meio pixel para fora (o contorno passa pelo centro dos pixels de dentro)."""
    from scipy.ndimage import map_coordinates

    q = ordenar(quad)
    centro = q.mean(axis=0)
    passos = np.arange(-4.0, 4.01, 0.25)
    retas = []
    for i in range(4):
        a, b = q[i], q[(i + 1) % 4]
        ab = b - a
        comp = np.linalg.norm(ab)
        rel = borda - a
        t = (rel @ ab) / comp**2
        dist = np.abs(ab[0] * rel[:, 1] - ab[1] * rel[:, 0]) / comp
        sel = (t > 0.12) & (t < 0.88) & (dist < max(2.0, 0.05 * comp))
        if sel.sum() < 4:
            return quad
        p = borda[sel]
        d = ab / comp
        n = np.array([-d[1], d[0]])
        if (p.mean(axis=0) - centro) @ n < 0:
            n = -n
        if nota is not None:
            amostras = p[:, None, :] + passos[None, :, None] * n[None, None, :]  # pontos × passos × (x, y)
            perfil = map_coordinates(nota, [amostras[..., 1].ravel(), amostras[..., 0].ravel()], order=1, mode="nearest")
            perfil = perfil.reshape(len(p), len(passos))
            dentro, fora = perfil[:, :4].mean(axis=1), perfil[:, -4:].mean(axis=1)
            nivel = (dentro + fora) / 2
            novos = []
            for k in range(len(p)):
                if abs(dentro[k] - fora[k]) < 8:  # sem contraste neste trecho: fica de fora
                    continue
                acima = (perfil[k] - nivel[k]) * np.sign(dentro[k] - fora[k]) > 0
                cruza = np.nonzero(acima[:-1] & ~acima[1:])[0]
                if len(cruza) == 0:
                    continue
                j = cruza[0]
                v0, v1 = perfil[k, j] - nivel[k], perfil[k, j + 1] - nivel[k]
                tt = passos[j] + (passos[j + 1] - passos[j]) * v0 / (v0 - v1)
                novos.append(p[k] + tt * n)
            if len(novos) >= 4:
                p = np.array(novos)
                desloca = 0.0
            else:
                desloca = 0.5
        else:
            desloca = 0.5
        m = p.mean(axis=0)
        d = np.linalg.svd(p - m)[2][0]
        retas.append((m + desloca * n, d))
    cantos = []
    for i in range(4):
        (p1, d1), (p2, d2) = retas[i - 1], retas[i]
        mat = np.array([d1, -d2]).T
        if abs(np.linalg.det(mat)) < 1e-9:
            return quad
        t = np.linalg.solve(mat, p2 - p1)
        cantos.append(p1 + t[0] * d1)
    return np.array(cantos)


def ordenar(c: np.ndarray) -> np.ndarray:
    from nucleo.medicao.plano_ref import ordenar_cantos

    return ordenar_cantos(c)
