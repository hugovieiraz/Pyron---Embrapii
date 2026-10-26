"""Perfil de câmera: a calibração feita uma vez e usada em todas as fotos daquela câmera, fixa ou na mão.

O perfil guarda os parâmetros da lente (focal, centro óptico e distorção) medidos com a folha ChArUco em várias
fotos, ou tirados da ficha técnica, no caso da câmera térmica, que não enxerga a folha impressa. Não há rede
neural nem treino: os "pesos" de uma câmera são estes parâmetros, e valem para qualquer foto dela. Numa resolução
diferente (o mesmo sensor gravando menor), o perfil é reescalado.

Câmera fixa: além do perfil, guarda a **posição** (a folha vista uma vez pela câmera instalada, que dá o plano de
referência e o mapa de escala) e pontos de referência da cena. Cada foto nova é comparada com eles: se a câmera
mexeu além do limite, a posição deixa de valer e o programa pede nova calibração.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

from nucleo.medicao import mapa_escala

# câmera fixa: a cena pode andar até este tanto (px, mediana dos pontos) antes de pedir nova calibração
LIMITE_DESLOCAMENTO_PX = 2.0
MINIMO_FOTOS = 5


@dataclass
class PerfilCamera:
    nome: str
    largura: int
    altura: int
    focal_px: float
    cx: float
    cy: float
    distorcao: list = field(default_factory=lambda: [0.0] * 5)
    fonte: str = ""  # "folha" (calibrada), "ficha" (ficha técnica) ou "exif"
    erro_reprojecao_px: float | None = None
    n_fotos: int = 0
    tipo: str = "visual"  # "visual" ou "termica"
    modelo: str = ""

    def K(self) -> np.ndarray:
        return np.array([[self.focal_px, 0, self.cx], [0, self.focal_px, self.cy], [0, 0, 1]], float)

    def para_resolucao(self, largura: int, altura: int) -> "PerfilCamera":
        """O mesmo sensor gravando em outra resolução, com a mesma proporção: escala focal e centro."""
        if abs(largura / altura - self.largura / self.altura) > 0.01:
            if abs(altura / largura - self.largura / self.altura) <= 0.01:  # foto em pé de câmera deitada
                p = PerfilCamera(**{**asdict(self), "largura": self.altura, "altura": self.largura,
                                    "cx": self.cy, "cy": self.cx})
                return p.para_resolucao(largura, altura)
            raise ValueError(
                f"proporção {largura}×{altura} diferente da calibrada ({self.largura}×{self.altura}): "
                "a foto foi cortada; calibre nesta proporção"
            )
        s = largura / self.largura
        return PerfilCamera(**{**asdict(self), "largura": largura, "altura": altura, "focal_px": self.focal_px * s,
                               "cx": self.cx * s, "cy": self.cy * s})

    def angulo_pixel_graus(self) -> float:
        """Ângulo que um pixel cobre no centro da imagem."""
        return math.degrees(math.atan(1.0 / self.focal_px))

    def tamanho_pixel_cm(self, distancia_m: float) -> float:
        """Tamanho de um pixel, em cm, num plano de frente para a câmera a ``distancia_m``."""
        return distancia_m * 100.0 / self.focal_px

    def para_dict(self) -> dict:
        return asdict(self)


def perfil_da_ficha(nome: str, largura: int, altura: int, fov_horizontal_graus: float, tipo: str = "termica",
                    modelo: str = "") -> PerfilCamera:
    """Perfil pelo campo de visão da ficha técnica (câmera térmica, que não enxerga a folha impressa).

    Conferir em bancada: um objeto de tamanho conhecido a uma distância medida com trena."""
    f = largura / (2 * math.tan(math.radians(fov_horizontal_graus) / 2))
    return PerfilCamera(nome=nome, largura=largura, altura=altura, focal_px=f, cx=largura / 2, cy=altura / 2,
                        fonte="ficha", tipo=tipo, modelo=modelo)


def calibrar(nome: str, fotos: list, modelo: str = "", **cfg_folha) -> PerfilCamera:
    """Calibra a lente com a folha ChArUco em várias fotos (de 5 a 20, com a folha em ângulos e lugares
    diferentes da imagem). Todas as fotos precisam ter o mesmo tamanho."""
    import cv2

    from nucleo.medicao.profundidade import abrir

    b = mapa_escala.tabuleiro(**{**{k: mapa_escala.PADRAO[k] for k in mapa_escala.PADRAO}, **cfg_folha})
    objs, imgs, tamanho = [], [], None
    for f in fotos:
        img = abrir(f)
        if tamanho is None:
            tamanho = img.size
        elif img.size != tamanho:
            raise ValueError(f"fotos com tamanhos diferentes: {tamanho} e {img.size}")
        cantos, obj = mapa_escala._detectar(np.asarray(img.convert("L")), b)
        if cantos is None or len(cantos) < 12:
            continue
        objs.append(np.c_[obj, np.zeros(len(obj))].astype(np.float32))
        imgs.append(cantos.astype(np.float32))
    if len(objs) < MINIMO_FOTOS:
        raise ValueError(f"a folha foi achada em {len(objs)} foto(s); são precisas pelo menos {MINIMO_FOTOS}")
    w, h = tamanho
    K0 = np.array([[max(w, h), 0, w / 2], [0, max(w, h), h / 2], [0, 0, 1]], np.float64)
    flags = cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_ASPECT_RATIO | cv2.CALIB_ZERO_TANGENT_DIST | cv2.CALIB_FIX_K3
    rms, K, dist, _, _ = cv2.calibrateCamera(objs, imgs, (w, h), K0, np.zeros(5), flags=flags)
    return PerfilCamera(nome=nome, largura=w, altura=h, focal_px=float(K[0, 0]), cx=float(K[0, 2]),
                        cy=float(K[1, 2]), distorcao=[float(x) for x in np.ravel(dist)[:5]], fonte="folha",
                        erro_reprojecao_px=round(float(rms), 3), n_fotos=len(objs), modelo=modelo)


# ---------------------------------------------------------------- câmera fixa


@dataclass
class PosicaoFixa:
    """A câmera instalada vendo a folha uma vez: o plano de referência e os pontos da cena para conferir."""

    camera: str
    homografia: list  # mm da folha → px
    distancia_cm: dict
    inclinacao_graus: float
    quadrado_mm: float
    pontos_cena: list  # [[x, y], ...] px, pontos fortes da cena (fora da folha também)
    descritores: bytes  # ORB, para achar os mesmos pontos depois

    def para_dict(self) -> dict:
        d = asdict(self)
        d.pop("descritores")
        d["n_pontos_cena"] = len(self.pontos_cena)
        return d


def _orb(cinza, n=3000):
    import cv2

    orb = cv2.ORB_create(nfeatures=n)
    kp, des = orb.detectAndCompute(cinza, None)
    return np.array([k.pt for k in kp], np.float32), des


def registrar_posicao(perfil: PerfilCamera, foto, **cfg_folha) -> PosicaoFixa:
    from nucleo.medicao.profundidade import abrir

    img = abrir(foto)
    p = perfil.para_resolucao(*img.size)
    m = mapa_escala.mapear(img, focal_px=p.focal_px, **cfg_folha)
    if not m.achou:
        raise ValueError("a folha não foi achada na foto de instalação")
    pts, des = _orb(np.asarray(img.convert("L")))
    if des is None or len(pts) < 50:
        raise ValueError("a cena tem pouca textura para conferir se a câmera mexeu")
    return PosicaoFixa(camera=perfil.nome, homografia=m.homografia, distancia_cm=m.distancia_cm,
                       inclinacao_graus=m.inclinacao_graus or 0.0,
                       quadrado_mm=float(cfg_folha.get("quadrado_mm", mapa_escala.PADRAO["quadrado_mm"])),
                       pontos_cena=pts.tolist(), descritores=des.tobytes())


def conferir_posicao(posicao: PosicaoFixa, foto, limite_px: float = LIMITE_DESLOCAMENTO_PX) -> dict:
    """A câmera continua onde foi calibrada? Compara os pontos da cena com os da instalação.

    Devolve o deslocamento (mediana, px) e se a posição ainda vale. Só a parte parada da cena conta: a homografia
    por RANSAC descarta o que se mexeu (pessoas, veículos)."""
    import cv2

    from nucleo.medicao.profundidade import abrir

    cinza = np.asarray(abrir(foto).convert("L"))
    pts, des = _orb(cinza)
    des0 = np.frombuffer(posicao.descritores, np.uint8).reshape(-1, 32)
    pts0 = np.asarray(posicao.pontos_cena, np.float32)
    if des is None or len(pts) < 20:
        return {"vale": False, "deslocamento_px": None, "pares": 0, "motivo": "a foto tem pouca textura"}
    pares = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(des0, des)
    if len(pares) < 20:
        return {"vale": False, "deslocamento_px": None, "pares": len(pares), "motivo": "a cena não é a mesma"}
    a = pts0[[p.queryIdx for p in pares]]
    b = pts[[p.trainIdx for p in pares]]
    H, dentro = cv2.findHomography(a, b, cv2.RANSAC, 3.0)
    if H is None:
        return {"vale": False, "deslocamento_px": None, "pares": len(pares), "motivo": "a cena não é a mesma"}
    dentro = dentro.ravel().astype(bool)
    # quanto a homografia move os pontos da cena (0 se a câmera não mexeu)
    q = cv2.perspectiveTransform(a[dentro].reshape(-1, 1, 2), H).reshape(-1, 2)
    desloc = float(np.median(np.linalg.norm(q - a[dentro], axis=1)))
    vale = desloc <= limite_px and dentro.sum() >= 20
    return {"vale": bool(vale), "deslocamento_px": round(desloc, 2), "pares": int(dentro.sum()),
            "motivo": "" if vale else f"a câmera mexeu {desloc:.1f} px (limite {limite_px:g}): calibrar de novo"}


# ---------------------------------------------------------------- escala por equipamento de medida conhecida


def escala_por_referencia(perfil: PerfilCamera, comprimento_px: float, medida_cm: float,
                          incerteza_cm: float = 0.0, erro_px: float = 1.0) -> dict:
    """Um equipamento cadastrado (medida validada) visto de frente na foto: distância e escala ali.

    ``comprimento_px``: o tamanho dele na foto (entre as pontas, na mesma direção da medida). A incerteza soma a
    da medida cadastrada e ``erro_px`` em cada ponta."""
    if comprimento_px <= 0 or medida_cm <= 0:
        raise ValueError("tamanho em pixels e medida precisam ser positivos")
    px_cm = comprimento_px / medida_cm
    distancia_m = perfil.focal_px * medida_cm / comprimento_px / 100.0
    rel = math.hypot(incerteza_cm / medida_cm, 2 * erro_px / comprimento_px)
    return {"px_por_cm": round(px_cm, 4), "cm_por_px": round(1 / px_cm, 4), "distancia_m": round(distancia_m, 3),
            "incerteza_rel": round(rel, 4)}
