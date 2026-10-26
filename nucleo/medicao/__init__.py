"""Medição de objetos em foto comum: profundidade métrica (MoGe-2) + contorno (SAM 2.1) + geometria 3D.

``medir(imagem, pista, referencia=None) -> Medida`` é a única função que o resto do Pyron usa.
Roteiro: ``docs/07_roteiro_medicao_geral.md``.

Pista (onde está o objeto), em pixels da imagem já na orientação do EXIF:
- ``{"ponto": (x, y)}``: um clique no objeto;
- ``{"caixa": (x0, y0, x1, y1)}``: uma caixa em volta;
- ``{"pontos": ((x1, y1), (x2, y2))}``: distância entre dois pontos.

Referência (opcional): uma pista do mesmo jeito mais ``tamanho_cm``, ``medida`` (``comprimento``, padrão,
``largura`` ou ``altura``) e ``nome``. Ela corrige a escala da cena inteira.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field

import numpy as np

from nucleo.medicao import geometria as g

# erro relativo da escala sem referência: provisório, até o gabarito medir o do MoGe-2 (fase 3)
ERRO_ESCALA_SEM_REFERENCIA = 0.10

REFERENCIAS_PRONTAS = {
    "folha_a4": {"nome": "folha A4", "comprimento": 29.7, "largura": 21.0},
    "cartao": {"nome": "cartão (ID-1)", "comprimento": 8.56, "largura": 5.40},
    "regua_30": {"nome": "régua de 30 cm", "comprimento": 30.0},
    "folha_carta": {"nome": "folha carta", "comprimento": 27.94, "largura": 21.59},
}


@dataclass
class Medida:
    comprimento_cm: float | None = None
    largura_cm: float | None = None
    espessura_cm: float | None = None
    altura_cm: float | None = None
    distancia_cm: float | None = None
    incerteza_cm: dict = field(default_factory=dict)
    metodo: str = "sem referência"
    forma: str = ""  # "plano", "volume" ou "distância"
    vertical: str = ""  # "apoio" ou "câmera"
    lente: str = ""  # "exif" ou "estimada"
    fator_escala: float = 1.0
    tamanho_imagem: list = field(default_factory=list)  # [largura, altura] em pixels, já na orientação do EXIF
    nota_contorno: float | None = None
    contorno: list = field(default_factory=list)  # polígonos [[x, y], ...] em pixels
    tempos_ms: dict = field(default_factory=dict)
    modelos: dict = field(default_factory=dict)

    def para_dict(self) -> dict:
        return asdict(self)


def contorno(mascara: np.ndarray, maximo_pontos: int = 200) -> list:
    """Polígonos da máscara (para desenhar), simplificados."""
    try:
        import cv2
    except ImportError:
        ys, xs = np.nonzero(mascara)
        if len(xs) == 0:
            return []
        x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]]
    cs, _ = cv2.findContours(mascara.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cs = sorted(cs, key=cv2.contourArea, reverse=True)[:3]
    saida = []
    for c in cs:
        eps = 0.002 * cv2.arcLength(c, True)
        a = cv2.approxPolyDP(c, eps, True)
        while len(a) > maximo_pontos:
            eps *= 1.5
            a = cv2.approxPolyDP(c, eps, True)
        saida.append(a.reshape(-1, 2).astype(int).tolist())
    return saida


def _erodir(mascara: np.ndarray, px: int = 2) -> np.ndarray:
    m = mascara.copy()
    for _ in range(px):
        m[1:, :] &= m[:-1, :]
        m[:-1, :] &= m[1:, :]
        m[:, 1:] &= m[:, :-1]
        m[:, :-1] &= m[:, 1:]
    return m


def medir_geometria(pontos: np.ndarray, mascara: np.ndarray) -> dict:
    """Medidas em metros de um objeto já recortado: decide se é plano e mede do jeito certo.

    Devolve ``{"forma", "vertical", "medidas": {nome: Extensao}}``.
    """
    # só a região do objeto (com folga embaixo para achar o apoio): as contas ficam proporcionais ao objeto
    ys, xs = np.nonzero(mascara)
    if len(ys) == 0:
        raise ValueError("máscara vazia")
    folga = 45
    y0, y1 = max(0, ys.min() - folga), min(mascara.shape[0], ys.max() + folga + 1)
    x0, x1 = max(0, xs.min() - folga), min(mascara.shape[1], xs.max() + folga + 1)
    pontos, mascara = pontos[y0:y1, x0:x1], mascara[y0:y1, x0:x1]
    interior = _erodir(mascara, 2)
    if g._validos(pontos, interior).sum() < 200:
        interior = mascara
    ext = g.extensoes(pontos, interior)
    pl = g.plano(pontos, interior)
    para_cima, origem = g.vertical(pontos, mascara)
    if g.eh_plano(pl, ext):
        # projetar no plano só se ele não estiver de lado para a câmera (ruído num objeto pequeno pode dar
        # um plano quase paralelo aos raios) e se a projeção não mudar muito o tamanho
        visada = np.median(pontos[g._validos(pontos, interior)], axis=0)
        visada = visada / np.linalg.norm(visada)
        pl2 = None
        if abs(pl.normal @ visada) >= 0.25:
            projetados = g.projetar_no_plano(pontos, mascara, pl)
            pl2 = g.plano(projetados, mascara)
            if not (0.8 <= pl2.comprimento.valor / max(ext.comprimento.valor, 1e-9) <= 1.25):
                pl2 = None
        if pl2 is None:
            projetados = pontos
            pl2 = g.plano(pontos, mascara)
        medidas = {"comprimento": pl2.comprimento, "largura": pl2.largura}
        # plano de pé (porta, parede, quadro): a altura é a extensão na vertical
        if abs(pl.normal @ para_cima) < 0.5:
            medidas["altura"] = g.altura(projetados, mascara, para_cima)
        return {"forma": "plano", "vertical": origem, "medidas": medidas}
    ext = g.extensoes(pontos, mascara)
    return {
        "forma": "volume",
        "vertical": origem,
        "medidas": {
            "comprimento": ext.comprimento,
            "largura": ext.largura,
            "espessura": ext.espessura,
            "altura": g.altura(pontos, mascara, para_cima),
        },
    }


class Medidor:
    """Junta profundidade, contorno e geometria. Os modelos entram por injeção (os testes usam falsos)."""

    def __init__(self, profundidade=None, segmentador=None, cache: int = 4):
        self._profundidade = profundidade
        self._segmentador = segmentador
        self._cache: OrderedDict = OrderedDict()
        self._tamanho_cache = cache

    @property
    def profundidade(self):
        if self._profundidade is None:
            from nucleo.medicao.profundidade import Profundidade

            self._profundidade = Profundidade()
        return self._profundidade

    @property
    def segmentador(self):
        if self._segmentador is None:
            from nucleo.medicao.segmentar import Segmentador

            self._segmentador = Segmentador()
        return self._segmentador

    def _geometria(self, img, chave, tempos):
        if chave in self._cache:
            self._cache.move_to_end(chave)
            tempos["profundidade"] = 0.0
            return self._cache[chave]
        geo = self.profundidade.estimar(img)
        tempos["profundidade"] = round(geo.tempo_ms, 1)
        self._cache[chave] = geo
        while len(self._cache) > self._tamanho_cache:
            self._cache.popitem(last=False)
        return geo

    def _mascara(self, img, pista, chave, tempos, rotulo=""):
        t0 = time.perf_counter()
        if "caixa" in pista:
            m, nota = self.segmentador.mascara_por_caixa(img, pista["caixa"], chave=chave)
        elif "ponto" in pista:
            m, nota = self.segmentador.mascara_por_ponto(img, pista["ponto"], chave=chave)
        else:
            raise ValueError("pista sem ponto, caixa ou dois pontos")
        tempos[f"contorno{rotulo}"] = round((time.perf_counter() - t0) * 1000, 1)
        return m, nota

    def _medir_pista(self, img, geo, pista, chave, tempos, rotulo=""):
        """Medidas em metros (``Extensao``) de uma pista, mais máscara e nota do contorno."""
        if "pontos" in pista:
            p1, p2 = pista["pontos"]
            return {"forma": "distância", "vertical": "", "medidas": {"distancia": g.distancia(geo.pontos, p1, p2)}}, None, None
        m, nota = self._mascara(img, pista, chave, tempos, rotulo)
        mascara = m & geo.validos
        if mascara.sum() < 20:
            raise ValueError("o contorno não pegou pontos com profundidade válida")
        t0 = time.perf_counter()
        r = medir_geometria(geo.pontos, mascara)
        tempos[f"geometria{rotulo}"] = round((time.perf_counter() - t0) * 1000, 1)
        return r, m, nota

    def medir(self, imagem, pista: dict, referencia: dict | None = None) -> Medida:
        from nucleo.medicao.profundidade import abrir

        tempos: dict = {}
        t_total = time.perf_counter()
        bruto = imagem if isinstance(imagem, (bytes, bytearray)) else None
        img = abrir(imagem)
        chave = hashlib.sha1(bruto if bruto is not None else img.tobytes()).hexdigest()
        geo = self._geometria(img, chave, tempos)
        r, mascara, nota = self._medir_pista(img, geo, pista, chave, tempos)

        fator, erro_escala, metodo = 1.0, ERRO_ESCALA_SEM_REFERENCIA, "sem referência"
        if referencia:
            rr, _, _ = self._medir_pista(img, geo, referencia, chave, tempos, rotulo="_referencia")
            qual = "distancia" if "pontos" in referencia else referencia.get("medida", "comprimento")
            ext_ref = rr["medidas"].get(qual)
            if ext_ref is None:
                raise ValueError(f"a referência não tem {qual} (forma {rr['forma']})")
            real_m = float(referencia["tamanho_cm"]) / 100.0
            fator = g.fator_escala(ext_ref.valor, real_m)
            # o erro que sobra é o da própria referência medida (pixels e ruído), relativo
            erro_escala = ext_ref.incerteza() / ext_ref.valor
            metodo = f"referência: {referencia.get('nome') or 'informada'} ({referencia['tamanho_cm']:g} cm)"

        saida = Medida(
            metodo=metodo,
            forma=r["forma"],
            vertical=r["vertical"],
            lente=geo.lente,
            fator_escala=round(fator, 5),
            tamanho_imagem=[img.width, img.height],
            nota_contorno=None if nota is None else round(nota, 3),
            contorno=[] if mascara is None else contorno(mascara),
            modelos={"profundidade": geo.modelo, "contorno": getattr(self._segmentador, "nome", "")},
        )
        for nome, ext in r["medidas"].items():
            setattr(saida, f"{nome}_cm", round(ext.valor * fator * 100, 2))
            saida.incerteza_cm[nome] = round(ext.incerteza(erro_escala) * fator * 100, 2)
        tempos["total"] = round((time.perf_counter() - t_total) * 1000, 1)
        saida.tempos_ms = tempos
        return saida


_padrao: Medidor | None = None


def medidor() -> Medidor:
    global _padrao
    if _padrao is None:
        _padrao = Medidor()
    return _padrao


def medir(imagem, pista: dict, referencia: dict | None = None) -> Medida:
    """Mede o objeto da ``pista`` na foto (caminho, bytes ou PIL). Ver o cabeçalho do módulo."""
    return medidor().medir(imagem, pista, referencia)
