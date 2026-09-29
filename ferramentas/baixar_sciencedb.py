"""Baixa um dataset do ScienceDB (scidb.cn) mantendo as pastas e conferindo o MD5 de cada arquivo.

Uso:
    python ferramentas/baixar_sciencedb.py e416c488169f484485ad7575dcfc43ce dados/sciencedb_10185

O padrão é o dataset de imagens térmicas de equipamentos de subestação de 132 kV
(DOI 10.57760/sciencedb.10185, licença CC BY-NC-SA 4.0: só estudo, sem uso comercial).
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API_LISTA = "https://www.scidb.cn/api/gin-sdb-filetree/public/file/childrenFileListByPath"
URL_ARQUIVO = "https://download.scidb.cn/download?fileId={id}&dataSetType=personal&fileName={nome}"


def listar(dataset: str, versao: str, caminho: str, por_pagina: int = 5000) -> list[dict]:
    """Lista os itens de uma pasta.

    A API ignora o cursor de paginação e sempre devolve a primeira página, então pedimos uma
    página grande e avisamos se ela vier cheia (sinal de que pode ter faltado algo).
    """
    corpo = json.dumps(
        {"dataSetId": dataset, "version": versao, "path": caminho, "lastFileId": "*", "pageSize": por_pagina}
    ).encode()
    req = urllib.request.Request(API_LISTA, data=corpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        itens = json.load(r).get("data") or []
    if len(itens) >= por_pagina:
        print(f"aviso: {caminho} tem {por_pagina} itens ou mais; a lista pode estar incompleta")
    return itens


def arvore(dataset: str, versao: str, caminho: str) -> list[dict]:
    """Percorre as pastas e devolve só os arquivos."""
    arquivos: list[dict] = []
    for item in listar(dataset, versao, caminho):
        if item["dir"]:
            arquivos.extend(arvore(dataset, versao, item["path"]))
        else:
            arquivos.append(item)
    return arquivos


def md5(caminho: Path) -> str:
    return hashlib.md5(caminho.read_bytes()).hexdigest()


def _baixar_um(item: dict, alvo: Path) -> bool:
    """Baixa um arquivo, com até 4 tentativas; devolve True se o MD5 conferir."""
    if alvo.exists() and (not item["md5"] or md5(alvo) == item["md5"]):
        return True
    alvo.parent.mkdir(parents=True, exist_ok=True)
    url = URL_ARQUIVO.format(id=item["id"], nome=urllib.parse.quote(item["fileName"]))
    for tentativa in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                alvo.write_bytes(r.read())
            if not item["md5"] or md5(alvo) == item["md5"]:
                return True
        except OSError:
            pass
        time.sleep(2 * (tentativa + 1))
    return False


def baixar(dataset: str, destino: Path, versao: str = "V1", conexoes: int = 2) -> None:
    arquivos = arvore(dataset, versao, f"/{versao}")
    print(f"{len(arquivos)} arquivos, {sum(a['size'] for a in arquivos) / 1e6:.1f} MB", flush=True)
    prefixo = f"/{versao}/"
    falhas: list[str] = []
    with ThreadPoolExecutor(max_workers=conexoes) as pool:
        tarefas = {pool.submit(_baixar_um, it, destino / it["path"][len(prefixo) :]): it for it in arquivos}
        for n, tarefa in enumerate(as_completed(tarefas), 1):
            if not tarefa.result():
                falhas.append(tarefas[tarefa]["path"])
            if n % 100 == 0:
                print(f"  {n}/{len(arquivos)}", flush=True)
    (destino / "lista_arquivos.json").write_text(json.dumps(arquivos, ensure_ascii=False, indent=1), encoding="utf-8")
    for f in falhas:
        print(f"falhou: {f}")
    print("concluído" if not falhas else f"concluído com {len(falhas)} falhas", flush=True)


if __name__ == "__main__":
    dataset = sys.argv[1] if len(sys.argv) > 1 else "e416c488169f484485ad7575dcfc43ce"
    destino = Path(sys.argv[2] if len(sys.argv) > 2 else "dados/sciencedb_10185")
    baixar(dataset, destino)
