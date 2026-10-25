"""Vetoriza o símbolo (imagem 5): classifica cada pixel na cor mais próxima, traça os contornos e endireita as retas."""
import sys, json, math
import numpy as np, cv2
from PIL import Image

ORIG = sys.argv[1]
ESC = 8  # amplia para traçar com precisão de 1/8 de pixel

im = np.asarray(Image.open(ORIG).convert("RGB")).astype(np.float32)
H, W = im.shape[:2]
CLASSES = {"fundo": (254, 254, 254), "mao": (10, 10, 10), "laranja": (237, 92, 12), "amarelo": (250, 192, 28), "brasa": (164, 12, 58)}

# cor de cada classe = mediana dos pixels "puros" daquela classe (longe da borda)
nomes = list(CLASSES)
ref = np.array([CLASSES[n] for n in nomes], np.float32)
dist = ((im[:, :, None, :] - ref[None, None]) ** 2).sum(-1)
rot = dist.argmin(-1)
puro = np.sqrt(dist.min(-1)) < 30
medias = {n: tuple(int(v) for v in np.median(im[(rot == i) & puro], axis=0)) for i, n in enumerate(nomes)}

# amplia com interpolação suave e reclassifica: contornos sem serrilhado
grande = cv2.resize(im, (W * ESC, H * ESC), interpolation=cv2.INTER_CUBIC)
ref = np.array([medias[n] for n in nomes], np.float32)
rotG = ((grande[:, :, None, :] - ref[None, None]) ** 2).sum(-1).argmin(-1)
mask = {n: (rotG == i).astype(np.uint8) for i, n in enumerate(nomes)}
lim = lambda m: cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ESC * 2 + 1, ESC * 2 + 1)))

def endireitar(pts, tol=4.0):
    """Lados quase horizontais/verticais viram retos (alinha o vértice comum)."""
    pts = [list(p) for p in pts]
    n = len(pts)
    for _ in range(2):
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            dx, dy = b[0] - a[0], b[1] - a[1]
            ang = math.degrees(math.atan2(abs(dy), abs(dx)))
            if ang < tol: m = (a[1] + b[1]) / 2; a[1] = b[1] = m
            elif ang > 90 - tol: m = (a[0] + b[0]) / 2; a[0] = b[0] = m
    return pts

def limpar(pts, curto=1.8):
    """Funde vértices de lados curtos demais (resto do serrilhado) e volta a endireitar."""
    mudou = True
    while mudou and len(pts) > 3:
        mudou = False
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            if math.hypot(b[0] - a[0], b[1] - a[1]) < curto:
                m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
                pts[i] = m; del pts[(i + 1) % len(pts)]; mudou = True; break
    return endireitar(pts)

def tracar(m, eps, minimo=60):
    cs, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    caminhos = []
    for c in cs:
        if cv2.contourArea(c) < minimo * ESC: continue
        ap = cv2.approxPolyDP(c, eps * ESC, True)[:, 0, :].astype(float)
        pts = limpar(endireitar([(x / ESC, y / ESC) for x, y in ap]))
        caminhos.append(pts)
    return caminhos

def principal(caminhos):
    area = lambda p: abs(sum(p[i][0] * p[i - 1][1] - p[i - 1][0] * p[i][1] for i in range(len(p)))) / 2
    return [max(caminhos, key=area)]

def d(caminhos):
    return " ".join("M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + "Z" for pts in caminhos)

saida = {"cores": {n: "#%02X%02X%02X" % medias[n] for n in nomes}, "W": W, "H": H}
# chama em camadas cheias (a de fora inclui as de dentro): sem frestas entre as cores
fl = mask["laranja"] | mask["amarelo"] | mask["brasa"]
num, comp, stats, _ = cv2.connectedComponentsWithStats(lim(fl))
maior = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
chama = (comp == maior).astype(np.uint8)
saida["chama_ext"] = d(tracar(chama, 0.55))
fechar = lambda m: cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ESC * 3 + 1, ESC * 3 + 1)))
saida["chama_meio"] = d(principal(tracar(lim(fechar(mask["amarelo"] | mask["brasa"]) & chama), 0.5)))
saida["chama_nucleo"] = d(principal(tracar(lim(mask["brasa"] & chama), 0.5)))
saida["mao"] = d(tracar(lim(mask["mao"]), 0.5))
# pixels soltos: quadrados exatos pelo retângulo do contorno
px = []
for n in ("laranja", "amarelo", "brasa"):
    m = lim(mask[n]) & (1 - chama)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cs:
        x, y, w, h = cv2.boundingRect(c)
        if not (9 * ESC <= w <= 14 * ESC and 9 * ESC <= h <= 14 * ESC and 0.8 < w / h < 1.25): continue
        lado = (w + h) / 2 / ESC
        px.append({"cor": n, "x": round(x / ESC, 2), "y": round(y / ESC, 2), "lado": round(lado, 2)})
uni = []
for p in px:
    cx, cy = int(p["x"] + p["lado"] / 2), int(p["y"] + p["lado"] / 2)
    cor = im[cy - 2:cy + 3, cx - 2:cx + 3].reshape(-1, 3).mean(0)
    i = int(((ref - cor) ** 2).sum(1).argmin()); nome = nomes[i]
    if nome in ("fundo", "mao") or np.sqrt(((ref[i] - cor) ** 2).sum()) > 40: continue
    if any(abs(q["x"] - p["x"]) < 4 and abs(q["y"] - p["y"]) < 4 for q in uni): continue
    p["cor"] = nome; uni.append(p)
saida["pixels"] = uni
json.dump(saida, open("vetor.json", "w"), indent=1)
print(saida["cores"], len(px), "pixels")
for k in ("chama_ext", "chama_meio", "chama_nucleo", "mao"): print(k, saida[k].count("M"), "caminho(s),", saida[k].count("L") + saida[k].count("M"), "pontos")
