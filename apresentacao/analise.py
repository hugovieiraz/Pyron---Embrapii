"""A análise de uma foto: abrir o JPEG da câmera, identificar as peças e achar o ponto mais quente.

1. Do arquivo da FLIR saem duas coisas: a imagem colorida (a que se vê) e a temperatura de cada
   pixel do sensor (os dados radiométricos gravados junto).
2. O detector olha a imagem colorida e marca as peças.
3. Dentro da caixa de cada para-raio, o pixel mais quente da matriz de temperatura é o ponto mais
   quente; diz-se em qual peça ele caiu (terminal superior, aletas ou terminal inferior).

Foto sem dados radiométricos (print, foto de tela): só a identificação, sem temperatura.
"""

from __future__ import annotations

import base64
import io
import time

import numpy as np
from PIL import Image

from apresentacao import flir

PARTES = ("terminal_superior", "aletas_isoladoras", "terminal_inferior")


def orientar(mapa: np.ndarray, orientacao: int) -> np.ndarray:
    """Gira a matriz como a marca EXIF manda exibir a foto (câmera na vertical: Orientation = 6)."""
    operacoes = {
        2: lambda m: m[:, ::-1],
        3: lambda m: np.rot90(m, 2),
        4: lambda m: m[::-1, :],
        5: lambda m: m.T,
        6: lambda m: np.rot90(m, -1),
        7: lambda m: np.rot90(m, 2).T,
        8: lambda m: np.rot90(m, 1),
    }
    op = operacoes.get(int(orientacao or 1))
    return np.ascontiguousarray(op(mapa)) if op else mapa


def abrir(dados: bytes) -> tuple[np.ndarray, np.ndarray | None, dict]:
    """(imagem colorida, temperatura em °C ou None, informações da câmera), já no sentido de exibir."""
    try:
        img = Image.open(io.BytesIO(dados))
        img.load()
    except OSError as erro:
        raise ValueError("Não consegui abrir o arquivo como imagem.") from erro
    exif = img.getexif()
    orientacao = int(exif.get(274, 1) or 1)
    rgb = orientar(np.asarray(img.convert("RGB")), orientacao)
    info = {"camera": str(exif.get(272, "") or "").strip(), "data": str(exif.get(306, "") or "").strip()}
    try:
        termo = flir.ler_bytes(dados)
    except ValueError:
        return rgb, None, info
    info["camera"] = termo.parametros.modelo or info["camera"]
    info["sensor"] = f"{termo.bruto.shape[1]} × {termo.bruto.shape[0]}"
    info["emissividade"] = round(termo.parametros.emissividade, 2)
    return rgb, orientar(termo.temperatura_c, orientacao).astype(np.float32), info


def _regiao(temp: np.ndarray, caixa: list[float]) -> tuple[slice, slice]:
    h, w = temp.shape
    x0, y0, x1, y1 = caixa
    linhas = slice(max(0, int(y0 * h)), min(h, max(int(y0 * h) + 1, int(np.ceil(y1 * h)))))
    colunas = slice(max(0, int(x0 * w)), min(w, max(int(x0 * w) + 1, int(np.ceil(x1 * w)))))
    return linhas, colunas


def ponto_mais_quente(temp: np.ndarray, caixa: list[float]) -> tuple[float, list[float]]:
    """Temperatura e posição (fração da imagem) do pixel mais quente dentro da caixa."""
    linhas, colunas = _regiao(temp, caixa)
    pedaco = temp[linhas, colunas]
    i, j = np.unravel_index(int(np.nanargmax(pedaco)), pedaco.shape)
    h, w = temp.shape
    return float(pedaco[i, j]), [round(float((colunas.start + j + 0.5) / w), 4), round(float((linhas.start + i + 0.5) / h), 4)]


def _dentro(ponto: list[float], caixa: list[float]) -> bool:
    return caixa[0] <= ponto[0] <= caixa[2] and caixa[1] <= ponto[1] <= caixa[3]


def _contida(peca: list[float], caixa: list[float]) -> float:
    """Quanto da caixa ``peca`` está dentro de ``caixa`` (0 a 1)."""
    ix = max(0.0, min(peca[2], caixa[2]) - max(peca[0], caixa[0]))
    iy = max(0.0, min(peca[3], caixa[3]) - max(peca[1], caixa[1]))
    area = (peca[2] - peca[0]) * (peca[3] - peca[1])
    return ix * iy / area if area > 0 else 0.0


def analisar(dados: bytes, nome: str, detector) -> dict:
    t0 = time.perf_counter()
    rgb, temp, info = abrir(dados)
    t1 = time.perf_counter()
    pecas = detector.detectar(rgb)
    t2 = time.perf_counter()
    if temp is not None:
        for p in pecas:
            tmax, ponto = ponto_mais_quente(temp, p["caixa"])
            p["tmax"], p["ponto"] = round(tmax, 1), ponto
    para_raios = []
    # numerados da esquerda para a direita, como se vê na foto
    for n, p in enumerate(sorted((p for p in pecas if p["classe"] == "para_raio"), key=lambda p: p["caixa"][0]), start=1):
        p["nome"] = f"Para-raio {n}"
        item = {"numero": n, "caixa": p["caixa"], "confianca": p["confianca"]}
        if temp is not None:
            item["tmax"], item["ponto"] = p["tmax"], p["ponto"]
            # a peça onde o ponto caiu: entre as partes deste para-raio (caixa quase toda dentro da dele),
            # a menor que contém o ponto; se nenhuma, o corpo do para-raio
            partes = [q for q in pecas if q["classe"] in PARTES and _contida(q["caixa"], p["caixa"]) > 0.6 and _dentro(p["ponto"], q["caixa"])]
            menor = min(partes, key=lambda q: (q["caixa"][2] - q["caixa"][0]) * (q["caixa"][3] - q["caixa"][1]), default=None)
            item["onde"] = menor["nome"] if menor else "corpo do para-raio"
            item["partes"] = [{"nome": q["nome"], "tmax": q["tmax"]} for q in pecas
                              if q["classe"] in PARTES and _contida(q["caixa"], p["caixa"]) > 0.6]
        para_raios.append(item)
    t3 = time.perf_counter()
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=92)
    resultado = {
        "arquivo": nome,
        "imagem": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii"),
        "largura": int(rgb.shape[1]),
        "altura": int(rgb.shape[0]),
        "radiometrica": temp is not None,
        "info": info,
        "pecas": pecas,
        "para_raios": para_raios,
        "motor": detector.motor,
        "ms": {"leitura": round((t1 - t0) * 1000), "deteccao": round((t2 - t1) * 1000), "temperatura": round((t3 - t2) * 1000)},
    }
    if temp is not None:
        resultado["matriz"] = {"largura": int(temp.shape[1]), "altura": int(temp.shape[0]),
                               "valores": np.round(temp, 1).ravel().tolist(),
                               "min": round(float(np.nanmin(temp)), 1), "max": round(float(np.nanmax(temp)), 1)}
    return resultado
