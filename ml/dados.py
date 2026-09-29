"""Rótulos do CVAT (COCO 1.0) ligados à temperatura verdadeira de cada imagem.

O CVAT desenha as caixas sobre a imagem exibida (640×480 na FLIR C5); a temperatura vem do
sensor (160×120). As caixas são levadas para a grade da matriz de temperatura, que é o que o
modelo recebe.

A separação treino/teste é por sessão de captura (fotos tiradas com poucos minutos de
intervalo), não por imagem: fotos quase iguais do mesmo equipamento não podem ficar dos dois
lados, senão o teste mede memória, não generalização.
"""

from __future__ import annotations

import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from nucleo import entrada


def nome_classe(texto: str) -> str:
    """ "Terminal superior" -> "terminal_superior"; "Para-raio" -> "para_raio"."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_") or "classe"


@dataclass
class Amostra:
    arquivo: Path
    caixas: np.ndarray  # [N, 4] x0, y0, x1, y1 na grade da matriz de temperatura
    classes: np.ndarray  # [N] índice na lista de classes (0 a K-1)
    data_hora: datetime | None = None
    _temperatura: np.ndarray | None = field(default=None, repr=False)

    @property
    def nome(self) -> str:
        return self.arquivo.name

    @property
    def temperatura(self) -> np.ndarray:
        if self._temperatura is None:
            self._temperatura = entrada.carregar(self.arquivo.read_bytes(), ocr=entrada.OCRPreguicoso()).temperatura_c
        return self._temperatura


def _ler_json_coco(caminho: Path) -> dict:
    if caminho.suffix.lower() == ".zip":
        with zipfile.ZipFile(caminho) as z:
            nomes = [n for n in z.namelist() if n.lower().endswith(".json")]
            if not nomes:
                raise ValueError("O .zip não tem arquivo .json de anotações (exporte em COCO 1.0).")
            return json.loads(z.read(sorted(nomes)[0]).decode("utf-8"))
    return json.loads(caminho.read_text(encoding="utf-8"))


def _data_hora(arquivo: Path) -> datetime | None:
    try:
        valor = str(Image.open(arquivo).getexif().get(306, "") or "")
        return datetime.strptime(valor, "%Y:%m:%d %H:%M:%S")
    except (OSError, ValueError):
        return None


def ler_coco(caminho: Path, pasta_imagens: Path) -> tuple[list[Amostra], list[str], dict[str, str]]:
    """Amostras rotuladas, lista de classes (nomes internos) e nomes para exibir."""
    coco = _ler_json_coco(caminho)
    categorias = sorted(coco["categories"], key=lambda c: c["id"])
    usadas = {a["category_id"] for a in coco.get("annotations", [])}
    categorias = [c for c in categorias if c["id"] in usadas]
    classes = [nome_classe(c["name"]) for c in categorias]
    nomes = {nome_classe(c["name"]): c["name"].strip() for c in categorias}
    indice = {c["id"]: i for i, c in enumerate(categorias)}

    mapa = {p.name: p for p in pasta_imagens.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")}
    por_imagem: dict[int, list[dict]] = {}
    for a in coco.get("annotations", []):
        por_imagem.setdefault(a["image_id"], []).append(a)

    amostras, faltando = [], []
    for img in coco["images"]:
        nome = Path(img["file_name"]).name
        arquivo = mapa.get(nome)
        if arquivo is None:
            faltando.append(nome)
            continue
        anots = por_imagem.get(img["id"], [])
        if not anots:
            continue  # imagem sem rótulo: não entra (não sabemos se está vazia ou esquecida)
        amostra = Amostra(arquivo=arquivo, caixas=np.zeros((0, 4)), classes=np.zeros(0, dtype=np.int64), data_hora=_data_hora(arquivo))
        h_m, w_m = amostra.temperatura.shape
        sx, sy = w_m / float(img["width"]), h_m / float(img["height"])
        caixas, rotulos = [], []
        for a in anots:
            x, y, w, h = a["bbox"]
            if w < 1 or h < 1:
                continue
            caixas.append([x * sx, y * sy, (x + w) * sx, (y + h) * sy])
            rotulos.append(indice[a["category_id"]])
        amostra.caixas = np.asarray(caixas, dtype=np.float32).reshape(-1, 4)
        amostra.classes = np.asarray(rotulos, dtype=np.int64)
        amostras.append(amostra)
    if faltando:
        print(f"aviso: {len(faltando)} imagens do COCO não foram encontradas em {pasta_imagens} (ex.: {faltando[:3]})")
    if not amostras:
        raise ValueError("Nenhuma imagem rotulada foi encontrada. Confira a pasta das imagens e o arquivo COCO.")
    return amostras, classes, nomes


def sessoes(amostras: list[Amostra], intervalo_min: float = 15.0) -> list[int]:
    """Número da sessão de cada amostra: nova sessão quando o intervalo entre fotos passa do limite."""
    ordem = sorted(range(len(amostras)), key=lambda i: (amostras[i].data_hora or datetime.min, amostras[i].nome))
    rotulo = [0] * len(amostras)
    atual, anterior = 0, None
    for i in ordem:
        t = amostras[i].data_hora
        if anterior is not None and (t is None or anterior is None or (t - anterior).total_seconds() > intervalo_min * 60):
            atual += 1
        rotulo[i] = atual
        anterior = t
    return rotulo


def dividir(amostras: list[Amostra], frac_teste: float = 0.25, semente: int = 2026) -> tuple[list[Amostra], list[Amostra], dict]:
    """Treino e teste separados por sessão. Com uma sessão só, o teste são as últimas fotos no tempo."""
    s = sessoes(amostras)
    ids = sorted(set(s))
    rng = np.random.default_rng(semente)
    if len(ids) >= 2:
        embaralhadas = list(rng.permutation(ids))
        teste_ids, n = set(), 0
        alvo = max(1, round(frac_teste * len(amostras)))
        for sid in embaralhadas:
            if n >= alvo or len(teste_ids) == len(ids) - 1:
                break
            teste_ids.add(sid)
            n += s.count(sid)
        treino = [a for a, sid in zip(amostras, s) if sid not in teste_ids]
        teste = [a for a, sid in zip(amostras, s) if sid in teste_ids]
        criterio = f"{len(ids)} sessões; {len(teste_ids)} no teste"
    else:
        ordem = sorted(amostras, key=lambda a: (a.data_hora or datetime.min, a.nome))
        corte = max(1, len(ordem) - max(1, round(frac_teste * len(ordem))))
        treino, teste = ordem[:corte], ordem[corte:]
        criterio = "uma sessão só: teste com as últimas fotos no tempo"
    info = {"sessoes": len(ids), "criterio": criterio, "treino": [a.nome for a in treino], "teste": [a.nome for a in teste]}
    return treino, teste, info
