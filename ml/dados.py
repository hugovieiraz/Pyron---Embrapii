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
    subconjunto: str | None = None  # "treino", "validacao" ou "teste" quando o projeto do CVAT separa
    poligonos: list = field(default_factory=list)  # por rótulo: lista de [K, 2] na grade da matriz, ou None (caixa)
    _temperatura: np.ndarray | None = field(default=None, repr=False)

    @property
    def nome(self) -> str:
        return self.arquivo.name

    @property
    def temperatura(self) -> np.ndarray:
        if self._temperatura is None:
            self._temperatura = entrada.carregar(self.arquivo.read_bytes(), ocr=entrada.OCRPreguicoso()).temperatura_c
        return self._temperatura


SUBCONJUNTOS = {"train": "treino", "training": "treino", "val": "validacao", "valid": "validacao", "validation": "validacao", "test": "teste"}


def _subconjunto(nome_json: str) -> str | None:
    """instances_train.json -> "treino"; instances_default.json -> None (tarefa sem divisão)."""
    base = Path(nome_json).stem.lower()
    for chave, valor in SUBCONJUNTOS.items():
        if base == chave or base.endswith("_" + chave):
            return valor
    return None


def _ler_cocos(caminho: Path) -> list[tuple[str | None, dict]]:
    """Todos os COCO do arquivo. Um projeto do CVAT com treino/validação/teste exporta um .json por parte.

    Aceita o .zip do CVAT, um .json ou uma pasta (por exemplo, a pasta do dataset com ``annotations/``).
    """
    if caminho.is_dir():
        arquivos = sorted(caminho.rglob("*.json"))
        if not arquivos:
            raise ValueError("A pasta não tem arquivos .json de anotações do CVAT (COCO 1.0).")
        return [(_subconjunto(a.name), json.loads(a.read_text(encoding="utf-8"))) for a in arquivos]
    if caminho.suffix.lower() == ".zip":
        with zipfile.ZipFile(caminho) as z:
            nomes = sorted(n for n in z.namelist() if n.lower().endswith(".json") and not n.startswith("__MACOSX"))
            if not nomes:
                raise ValueError("O .zip não tem arquivo .json de anotações. Exporte do CVAT no formato COCO 1.0.")
            return [(_subconjunto(n), json.loads(z.read(n).decode("utf-8"))) for n in nomes]
    return [(_subconjunto(caminho.name), json.loads(caminho.read_text(encoding="utf-8")))]


def _conteudo(caminho: Path) -> tuple[list[str], list[dict]]:
    """Categorias (nomes originais, na ordem) e imagens com seus rótulos, juntando todas as partes."""
    categorias: list[str] = []
    imagens: list[dict] = []
    vistas: set[str] = set()
    for subconj, coco in _ler_cocos(caminho):
        if "images" not in coco or "annotations" not in coco:
            continue  # outro json no zip (por exemplo, metadados)
        nome_cat = {c["id"]: str(c["name"]).strip() for c in coco.get("categories", [])}
        for c in sorted(coco.get("categories", []), key=lambda c: c["id"]):
            if str(c["name"]).strip() not in categorias:
                categorias.append(str(c["name"]).strip())
        por_imagem: dict[int, list[dict]] = {}
        for a in coco["annotations"]:
            por_imagem.setdefault(a["image_id"], []).append(a)
        for img in coco["images"]:
            nome = Path(str(img["file_name"]).replace("\\", "/")).name
            if nome in vistas:
                continue  # mesma imagem em duas partes: vale a primeira
            vistas.add(nome)
            imagens.append({
                "nome": nome, "largura": float(img["width"]), "altura": float(img["height"]), "subconjunto": subconj,
                "rotulos": [(nome_cat.get(a["category_id"], str(a["category_id"])), a.get("bbox"), a.get("segmentation")) for a in por_imagem.get(img["id"], [])],
            })
    if not imagens:
        raise ValueError("Nenhuma imagem no arquivo de rótulos. Exporte do CVAT no formato COCO 1.0.")
    return categorias, imagens


def _tipo(segmentacao) -> str:
    if isinstance(segmentacao, dict):
        return "mascara"
    if isinstance(segmentacao, list) and segmentacao and isinstance(segmentacao[0], list) and len(segmentacao[0]) >= 6:
        return "poligono"
    return "caixa"


def _caixa_e_poligonos(bbox, segmentacao, sx: float, sy: float):
    """Caixa [x0, y0, x1, y1] e polígonos na grade da matriz. Sem bbox, a caixa sai do polígono."""
    poligonos = None
    if _tipo(segmentacao) == "poligono":
        poligonos = [np.asarray(p, dtype=np.float32).reshape(-1, 2) * [sx, sy] for p in segmentacao if len(p) >= 6]
    if bbox and bbox[2] >= 1 and bbox[3] >= 1:
        x, y, w, h = bbox
        caixa = [x * sx, y * sy, (x + w) * sx, (y + h) * sy]
    elif poligonos:
        pts = np.concatenate(poligonos)
        caixa = [*pts.min(0), *pts.max(0)]
    else:
        return None, None
    return caixa, poligonos


def _data_hora(arquivo: Path) -> datetime | None:
    try:
        valor = str(Image.open(arquivo).getexif().get(306, "") or "")
        return datetime.strptime(valor, "%Y:%m:%d %H:%M:%S")
    except (OSError, ValueError):
        return None


def _mapa_imagens(pasta_imagens: Path) -> dict[str, Path]:
    return {p.name: p for p in pasta_imagens.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")}


def ler_coco(caminho: Path, pasta_imagens: Path) -> tuple[list[Amostra], list[str], dict[str, str]]:
    """Amostras rotuladas, lista de classes (nomes internos) e nomes para exibir.

    Aceita o .zip ou o .json do CVAT em COCO 1.0, com caixas, polígonos ou máscaras (a caixa de
    cada rótulo é sempre usada; os polígonos ficam guardados para medir só os pixels do objeto).
    """
    categorias, imagens = _conteudo(caminho)
    usadas = {nome_classe(n) for img in imagens for n, _, _ in img["rotulos"]}
    classes, nomes = [], {}
    for n in categorias:
        c = nome_classe(n)
        if c in usadas and c not in nomes:
            classes.append(c)
            nomes[c] = n
    indice = {c: i for i, c in enumerate(classes)}

    mapa = _mapa_imagens(pasta_imagens)
    amostras, faltando = [], []
    for img in imagens:
        arquivo = mapa.get(img["nome"])
        if arquivo is None:
            faltando.append(img["nome"])
            continue
        if not img["rotulos"]:
            continue  # imagem sem rótulo: não entra (não sabemos se está vazia ou esquecida)
        amostra = Amostra(arquivo=arquivo, caixas=np.zeros((0, 4)), classes=np.zeros(0, dtype=np.int64),
                          data_hora=_data_hora(arquivo), subconjunto=img["subconjunto"])
        h_m, w_m = amostra.temperatura.shape
        sx, sy = w_m / img["largura"], h_m / img["altura"]
        caixas, rotulos, poligonos = [], [], []
        for nome_cat, bbox, segmentacao in img["rotulos"]:
            caixa, polis = _caixa_e_poligonos(bbox, segmentacao, sx, sy)
            if caixa is None:
                continue
            caixas.append(caixa)
            rotulos.append(indice[nome_classe(nome_cat)])
            poligonos.append(polis)
        amostra.caixas = np.asarray(caixas, dtype=np.float32).reshape(-1, 4)
        amostra.classes = np.asarray(rotulos, dtype=np.int64)
        amostra.poligonos = poligonos
        amostras.append(amostra)
    if faltando:
        print(f"aviso: {len(faltando)} imagens do COCO não foram encontradas em {pasta_imagens} (ex.: {faltando[:3]})")
    if not amostras:
        raise ValueError("Nenhuma imagem rotulada foi encontrada. Confira a pasta das imagens e o arquivo COCO.")
    return amostras, classes, nomes


def analisar(caminho: Path, pasta_imagens: Path) -> dict:
    """Relatório do conjunto rotulado, para conferir antes de treinar: o que tem e o que falta."""
    categorias, imagens = _conteudo(caminho)
    mapa = _mapa_imagens(pasta_imagens)
    rotuladas = [img for img in imagens if img["rotulos"]]
    encontradas = [img for img in rotuladas if img["nome"] in mapa]
    faltando = [img["nome"] for img in rotuladas if img["nome"] not in mapa]

    por_classe: dict[str, dict] = {}
    tipos = {"caixa": 0, "poligono": 0, "mascara": 0}
    for img in rotuladas:
        vistas = set()
        for n, _, seg in img["rotulos"]:
            c = nome_classe(n)
            item = por_classe.setdefault(c, {"classe": c, "nome": n, "rotulos": 0, "imagens": 0})
            item["rotulos"] += 1
            if c not in vistas:
                item["imagens"] += 1
                vistas.add(c)
            tipos[_tipo(seg)] += 1
    subconjuntos: dict[str, int] = {}
    for img in rotuladas:
        if img["subconjunto"]:
            subconjuntos[img["subconjunto"]] = subconjuntos.get(img["subconjunto"], 0) + 1

    # Orientação e sessões pedem a imagem: a temperatura diz o tamanho da grade; o EXIF, a hora.
    divergentes, amostras = [], []
    for img in encontradas:
        arquivo = mapa[img["nome"]]
        try:
            h_m, w_m = entrada.carregar(arquivo.read_bytes(), ocr=entrada.OCRPreguicoso()).temperatura_c.shape
        except ValueError:
            divergentes.append(img["nome"])
            continue
        if abs(img["largura"] / img["altura"] - w_m / h_m) > 0.05:
            divergentes.append(img["nome"])
        amostras.append(Amostra(arquivo=arquivo, caixas=np.zeros((0, 4)), classes=np.zeros(0), data_hora=_data_hora(arquivo), subconjunto=img["subconjunto"]))
    ses = sessoes(amostras) if amostras else []

    avisos = []
    if faltando:
        avisos.append(f"{len(faltando)} imagens rotuladas não foram achadas na pasta de imagens (por exemplo {', '.join(faltando[:3])}).")
    if divergentes:
        avisos.append(f"{len(divergentes)} imagens têm proporção diferente da matriz de temperatura (girada ou ilegível): ficam de fora.")
    sem_rotulo = len(imagens) - len(rotuladas)
    if sem_rotulo:
        avisos.append(f"{sem_rotulo} imagens do arquivo não têm nenhum rótulo e não entram no treino.")
    poucas = [c["nome"] for c in por_classe.values() if c["rotulos"] < 20]
    if poucas:
        avisos.append(f"Classes com menos de 20 rótulos, que o modelo tende a errar: {', '.join(poucas)}.")
    if amostras and len(set(ses)) == 1:
        avisos.append("Todas as fotos são de uma mesma sessão de captura: a divisão por sessão usa as últimas fotos no tempo como teste.")
    elif subconjuntos.get("treino") and subconjuntos.get("teste") and amostras:
        partes = {}
        for a, s in zip(amostras, ses):
            partes.setdefault(s, set()).add(a.subconjunto)
        mistas = sum(1 for p in partes.values() if "treino" in p and "teste" in p)
        if mistas:
            avisos.append(f"Na divisão do CVAT, {mistas} sessões de fotos aparecem no treino e no teste (fotos quase iguais dos dois lados). "
                          "A divisão por sessão dá uma nota mais honesta.")
    utilizaveis = len(encontradas) - len(divergentes)
    return {
        "arquivo": caminho.name,
        "imagens_no_arquivo": len(imagens),
        "imagens_rotuladas": len(rotuladas),
        "imagens_encontradas": len(encontradas),
        "imagens_utilizaveis": utilizaveis,
        "faltando": faltando[:20],
        "divergentes": divergentes[:20],
        "classes": sorted(por_classe.values(), key=lambda c: -c["rotulos"]),
        "tipos": tipos,
        "rotulos": sum(tipos.values()),
        "subconjuntos": subconjuntos,
        "sessoes": len(set(ses)),
        "avisos": avisos,
        "pronto": utilizaveis >= 8 and bool(por_classe),
    }


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


def dividir(amostras: list[Amostra], frac_teste: float = 0.25, semente: int = 2026, modo: str = "sessao") -> tuple[list[Amostra], list[Amostra], dict]:
    """Treino e teste.

    - ``sessao`` (padrão): separados por sessão de captura; com uma sessão só, o teste são as últimas fotos.
    - ``cvat``: a divisão feita no projeto do CVAT (treino + validação treinam; teste avalia; sem teste, a
      validação avalia). Sem partes no arquivo, volta para a divisão por sessão.
    """
    if modo == "cvat":
        partes = {a.subconjunto for a in amostras}
        avaliacao = "teste" if "teste" in partes else "validacao" if "validacao" in partes else None
        if avaliacao and "treino" in partes:
            treino = [a for a in amostras if a.subconjunto != avaliacao]
            teste = [a for a in amostras if a.subconjunto == avaliacao]
            info = {"sessoes": len(set(sessoes(amostras))), "criterio": f"divisão do CVAT ({avaliacao} avalia)",
                    "treino": [a.nome for a in treino], "teste": [a.nome for a in teste]}
            return treino, teste, info
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
