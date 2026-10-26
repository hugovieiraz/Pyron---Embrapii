"""Mapa de escala por folha ChArUco: quantos pixels vale 1 cm em cada ponto da foto, e a que distância.

A escala vem de uma folha impressa e conferida, não de modelo. Os cantos do xadrez ChArUco são achados com precisão
de fração de pixel e cada um tem posição conhecida em mm na folha. Disso saem:

- a homografia folha (mm) → foto (px) e, dela, a escala local (px por cm) em qualquer ponto do plano da folha, nas
  duas direções;
- com a lente (EXIF ou estimada pela própria folha), a pose da folha: distância de cada ponto à câmera e a
  inclinação.

Escolha do tamanho (``tamanho_quadrado_mm``): o quadrado precisa ter pelo menos ``QUADRADO_MIN_PX`` na foto. No
experimento sintético (desfoque, ruído e JPEG de celular, até 50°+25° de inclinação), com 50 px a folha foi achada
em todos os casos e o erro mediano de 1 cm ficou abaixo de 0,1 %. Com 20 a 30 px, só de frente ou com a foto boa.

Uso::

    python -m nucleo.medicao.mapa_escala --folha saida/folha.png --quadrado 25
    python -m nucleo.medicao.mapa_escala foto.jpg --saida mapa.jpg
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

QUADRADO_MIN_PX = 50.0  # lado do quadrado na foto para achar a folha em quase toda condição
QUADRADO_FRENTE_PX = 20.0  # mínimo só com foto de frente e boa
DPI = 300

# folha padrão: cabe numa A4 (210 × 297 mm) com margem de impressão
PADRAO = {"nx": 7, "ny": 10, "quadrado_mm": 25.0, "marcador_mm": 18.0, "dicionario": "DICT_5X5_250"}


def _aruco():
    import cv2

    return cv2, cv2.aruco


def tabuleiro(nx=PADRAO["nx"], ny=PADRAO["ny"], quadrado_mm=PADRAO["quadrado_mm"],
              marcador_mm=PADRAO["marcador_mm"], dicionario=PADRAO["dicionario"]):
    _, ar = _aruco()
    dic = ar.getPredefinedDictionary(getattr(ar, dicionario))
    return ar.CharucoBoard((nx, ny), quadrado_mm, marcador_mm, dic)


def tamanho_quadrado_mm(distancia_m: float, focal_px: float, minimo_px: float = QUADRADO_MIN_PX) -> float:
    """Lado do quadrado (mm) para dar ``minimo_px`` na foto a ``distancia_m`` (de frente)."""
    return minimo_px * distancia_m * 1000.0 / focal_px


def distancia_maxima_m(quadrado_mm: float, focal_px: float, minimo_px: float = QUADRADO_MIN_PX) -> float:
    return quadrado_mm * focal_px / (minimo_px * 1000.0)


def gerar_folha(caminho: Path, **kw) -> dict:
    """PNG a 300 dpi, em tamanho real, com régua de conferência de 100 mm. Depois de imprimir, medir o quadrado
    com paquímetro e informar o valor medido (impressora costuma escalar 1 a 3 %)."""
    cv2, _ = _aruco()
    cfg = {**PADRAO, **kw}
    b = tabuleiro(**cfg)
    px_mm = DPI / 25.4
    w = int(round(cfg["nx"] * cfg["quadrado_mm"] * px_mm))
    h = int(round(cfg["ny"] * cfg["quadrado_mm"] * px_mm))
    im = b.generateImage((w, h), marginSize=0)
    margem = int(round(12 * px_mm))
    folha = np.full((h + 2 * margem + int(14 * px_mm), w + 2 * margem), 255, np.uint8)
    folha[margem:margem + h, margem:margem + w] = im
    y = margem + h + int(6 * px_mm)
    x0 = margem
    for mm in range(0, 101):
        x = x0 + int(round(mm * px_mm))
        comp = 5 if mm % 10 == 0 else 3 if mm % 5 == 0 else 2
        cv2.line(folha, (x, y), (x, y + int(comp * px_mm)), 0, 2)
    cv2.putText(folha, f"conferir: 100 mm | quadrado {cfg['quadrado_mm']:g} mm | {cfg['nx']}x{cfg['ny']} {cfg['dicionario']}",
                (x0 + int(105 * px_mm), y + int(4 * px_mm)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image

    Image.fromarray(folha).save(caminho, dpi=(DPI, DPI))
    if caminho.suffix.lower() == ".png":
        Image.fromarray(folha).convert("RGB").save(caminho.with_suffix(".pdf"), resolution=DPI)
    return cfg


@dataclass
class MapaEscala:
    tamanho_imagem: list  # [largura, altura] em px, lido da própria foto
    achou: bool
    n_cantos: int = 0
    quadrado_px: float = 0.0  # lado mediano do quadrado na foto
    erro_reprojecao_px: float = 0.0  # RMS dos cantos contra a homografia
    homografia: list = field(default_factory=list)  # mm da folha → px da foto
    focal_px: float | None = None
    lente: str = ""  # "exif", "folha" ou "informada"
    distancia_cm: dict = field(default_factory=dict)  # mínima, mediana e máxima dos cantos
    inclinacao_graus: float | None = None
    grade: list = field(default_factory=list)  # [{x, y, px_cm_x, px_cm_y, distancia_cm}]
    aviso: str = ""

    def para_dict(self):
        return asdict(self)


def _detectar(cinza, b):
    _, ar = _aruco()
    det = ar.CharucoDetector(b)
    cantos, ids, _, _ = det.detectBoard(cinza)
    if cantos is None or len(cantos) < 6:
        return None, None
    obj = b.getChessboardCorners()[ids.ravel()][:, :2].astype(np.float64)
    return cantos.reshape(-1, 2).astype(np.float64), obj


def _escala_local(Hm, xy_mm):
    """Jacobiana da homografia em cada ponto: px por mm nas direções x e y da folha."""
    x, y = xy_mm[:, 0], xy_mm[:, 1]
    u = Hm[0, 0] * x + Hm[0, 1] * y + Hm[0, 2]
    v = Hm[1, 0] * x + Hm[1, 1] * y + Hm[1, 2]
    w = Hm[2, 0] * x + Hm[2, 1] * y + Hm[2, 2]
    jx = np.stack([(Hm[0, 0] * w - u * Hm[2, 0]) / w**2, (Hm[1, 0] * w - v * Hm[2, 0]) / w**2], 1)
    jy = np.stack([(Hm[0, 1] * w - u * Hm[2, 1]) / w**2, (Hm[1, 1] * w - v * Hm[2, 1]) / w**2], 1)
    return np.linalg.norm(jx, axis=1), np.linalg.norm(jy, axis=1), np.stack([u / w, v / w], 1)


def _focal_pela_folha(cantos, obj, tamanho):
    """Focal de uma vista só, com centro óptico no meio e pixel quadrado. Só vale com a folha inclinada."""
    cv2, _ = _aruco()
    w, h = tamanho
    K0 = np.array([[max(w, h), 0, w / 2], [0, max(w, h), h / 2], [0, 0, 1]], np.float64)
    flags = (cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_PRINCIPAL_POINT | cv2.CALIB_FIX_ASPECT_RATIO
             | cv2.CALIB_ZERO_TANGENT_DIST | cv2.CALIB_FIX_K1 | cv2.CALIB_FIX_K2 | cv2.CALIB_FIX_K3)
    obj3 = np.c_[obj, np.zeros(len(obj))].astype(np.float32)
    _, K, _, _, _ = cv2.calibrateCamera([obj3], [cantos.astype(np.float32)], (w, h), K0, np.zeros(5), flags=flags)
    return float(K[0, 0])


def mapear(imagem, focal_px: float | None = None, passo_mm: float = 25.0, **cfg) -> MapaEscala:
    """Acha a folha e monta o mapa. ``focal_px``: lente informada; senão EXIF; senão estimada pela folha."""
    cv2, _ = _aruco()
    from nucleo.medicao.profundidade import abrir, fov_do_exif

    img = abrir(imagem)
    tamanho = [img.width, img.height]
    cinza = np.asarray(img.convert("L"))
    b = tabuleiro(**{**{k: PADRAO[k] for k in PADRAO}, **cfg})
    cantos, obj = _detectar(cinza, b)
    if cantos is None:
        return MapaEscala(tamanho_imagem=tamanho, achou=False, aviso="folha não encontrada na foto")
    Hm, _ = cv2.findHomography(obj, cantos, 0)
    rep = cantos - _escala_local(Hm, obj)[2]
    rms = float(np.sqrt((rep**2).sum(1).mean()))
    q = float(cfg.get("quadrado_mm", PADRAO["quadrado_mm"]))
    sx, sy, _ = _escala_local(Hm, obj)
    quad_px = float(np.median(np.r_[sx, sy]) * q)

    lente = "informada"
    if focal_px is None:
        fov = fov_do_exif(img)
        if fov is not None:
            focal_px, lente = img.width / (2 * math.tan(math.radians(fov) / 2)), "exif"
        else:
            focal_px, lente = _focal_pela_folha(cantos, obj, tamanho), "folha"
    K = np.array([[focal_px, 0, img.width / 2], [0, focal_px, img.height / 2], [0, 0, 1]], np.float64)
    ok, rvec, tvec = cv2.solvePnP(np.c_[obj, np.zeros(len(obj))], cantos, K, None, flags=cv2.SOLVEPNP_IPPE)
    R = cv2.Rodrigues(rvec)[0]
    inclin = float(math.degrees(math.acos(abs(R[2, 2]))))

    nx, ny = int(cfg.get("nx", PADRAO["nx"])), int(cfg.get("ny", PADRAO["ny"]))
    gx = np.arange(0, nx * q + 1e-6, passo_mm)
    gy = np.arange(0, ny * q + 1e-6, passo_mm)
    xy = np.array([(x, y) for y in gy for x in gx], float)
    ex, ey, uv = _escala_local(Hm, xy)
    P = (R @ np.c_[xy, np.zeros(len(xy))].T + tvec).T  # mm, câmera
    dist = np.linalg.norm(P, axis=1) / 10.0
    grade = [{"x": float(u), "y": float(v), "px_cm_x": float(a * 10), "px_cm_y": float(c * 10), "distancia_cm": float(d)}
             for (u, v), a, c, d in zip(uv, ex, ey, dist)]
    dc = dist  # faixa de distância da folha inteira (a grade inclui as bordas)
    aviso = []
    if quad_px < QUADRADO_MIN_PX:
        aviso.append(f"quadrado com {quad_px:.0f} px (mínimo recomendado {QUADRADO_MIN_PX:.0f}): chegue mais perto")
    if lente == "folha" and inclin < 15:
        aviso.append("lente estimada com a folha quase de frente: a distância não é confiável (use o EXIF)")
    return MapaEscala(
        tamanho_imagem=tamanho, achou=True, n_cantos=len(cantos), quadrado_px=round(quad_px, 2),
        erro_reprojecao_px=round(rms, 3), homografia=Hm.tolist(), focal_px=round(float(focal_px), 1), lente=lente,
        distancia_cm={"min": round(float(dc.min()), 1), "mediana": round(float(np.median(dc)), 1), "max": round(float(dc.max()), 1)},
        inclinacao_graus=round(inclin, 1), grade=grade, aviso="; ".join(aviso),
    )


def medir_no_plano(mapa: MapaEscala, p1, p2) -> float:
    """Distância em cm entre dois pixels no plano da folha."""
    Hi = np.linalg.inv(np.array(mapa.homografia))
    a = Hi @ [p1[0], p1[1], 1.0]
    b = Hi @ [p2[0], p2[1], 1.0]
    return float(np.linalg.norm(a[:2] / a[2] - b[:2] / b[2]) / 10.0)


def desenhar(imagem, mapa: MapaEscala, caminho: Path) -> None:
    """Foto com um traço de 1 cm em cada direção em cada ponto da grade, o valor em px e a distância."""
    from PIL import ImageDraw, ImageFont

    from nucleo.medicao.profundidade import abrir

    im = abrir(imagem).convert("RGB")
    d = ImageDraw.Draw(im)
    e = max(1, im.width // 600)
    try:
        fonte = ImageFont.truetype("arial.ttf", max(12, im.width // 70))
        titulo = ImageFont.truetype("arial.ttf", max(14, im.width // 50))
    except OSError:
        fonte = titulo = None
    w, h = mapa.tamanho_imagem
    if not mapa.achou:
        d.text((10, 10), f"{w} x {h} px | {mapa.aviso}", fill=(255, 60, 60), font=titulo, stroke_width=2, stroke_fill=(0, 0, 0))
        im.save(caminho, quality=90)
        return
    Hm = np.array(mapa.homografia)
    Hi = np.linalg.inv(Hm)
    # traço de 1 cm em todos os pontos; rótulo só onde houver espaço (texto ~6 caracteres de largura)
    alt_txt = max(12, im.width // 70)
    espaco = 6 * alt_txt
    rotulados: list = []
    textos: list = []
    for g in mapa.grade:
        c = Hi @ [g["x"], g["y"], 1.0]
        c = c[:2] / c[2]
        for dv, cor in (((0, 10), (0, 200, 255)), ((10, 0), (255, 70, 0))):  # laranja por cima
            a = Hm @ [c[0] - dv[0] / 2, c[1] - dv[1] / 2, 1]
            b = Hm @ [c[0] + dv[0] / 2, c[1] + dv[1] / 2, 1]
            d.line([tuple(a[:2] / a[2]), tuple(b[:2] / b[2])], fill=cor, width=3 * e)
        if all(abs(g["x"] - x) > espaco or abs(g["y"] - y) > 2.6 * alt_txt for x, y in rotulados):
            rotulados.append((g["x"], g["y"]))
            textos.append(((g["x"] + 6 * e, g["y"] + 4 * e), f"{(g['px_cm_x'] + g['px_cm_y']) / 2:.1f} px\n{g['distancia_cm']:.0f} cm"))
    for pos, t in textos:  # rótulos por último, em caixa escura, para ler sobre o xadrez
        caixa = d.multiline_textbbox(pos, t, font=fonte)
        d.rectangle([caixa[0] - 2, caixa[1] - 2, caixa[2] + 2, caixa[3] + 2], fill=(0, 0, 0))
        d.multiline_text(pos, t, fill=(255, 235, 0), font=fonte)
    linhas = [
        f"imagem {w} x {h} px | {mapa.n_cantos} cantos | quadrado {mapa.quadrado_px:.0f} px | reprojeção {mapa.erro_reprojecao_px:.2f} px",
        f"traços de 1 cm (laranja: x da folha, azul: y); rótulo = px por cm e distância",
        f"lente {mapa.lente} {mapa.focal_px:.0f} px | distância {mapa.distancia_cm['min']:.0f}-{mapa.distancia_cm['max']:.0f} cm | inclinação {mapa.inclinacao_graus:.0f}°",
    ]
    if mapa.aviso:
        linhas.append("aviso: " + mapa.aviso)
    for i, t in enumerate(linhas):
        d.text((10, 10 + i * (im.width // 40 + 4)), t, fill=(255, 255, 255), font=titulo, stroke_width=3, stroke_fill=(0, 0, 0))
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    im.save(caminho, quality=90)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mapa de escala por folha ChArUco")
    ap.add_argument("foto", nargs="?", type=Path)
    ap.add_argument("--saida", type=Path)
    ap.add_argument("--folha", type=Path, help="gerar a folha para imprimir (PNG e PDF)")
    ap.add_argument("--quadrado", type=float, default=PADRAO["quadrado_mm"], help="lado do quadrado em mm (o medido, depois de impresso)")
    ap.add_argument("--focal", type=float, help="focal em px, se souber")
    a = ap.parse_args(argv)
    cfg = {"quadrado_mm": a.quadrado, "marcador_mm": a.quadrado * PADRAO["marcador_mm"] / PADRAO["quadrado_mm"]}
    if a.folha:
        print(json.dumps(gerar_folha(a.folha, **cfg), ensure_ascii=False))
    if a.foto:
        m = mapear(a.foto, focal_px=a.focal, **cfg)
        desenhar(a.foto, m, a.saida or a.foto.with_name(a.foto.stem + "_escala.jpg"))
        r = m.para_dict()
        r.pop("grade")
        print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
