"""Avaliações de modelos trazidas do Colab: a comparação dos detectores e, se vier junto, o modelo.

O caderno do Colab baixa ``resultados_comparacao.zip`` (``resumo.json``, figuras .png e tabelas .csv)
e, no passo de exportação, um pacote com o modelo pronto para o Pyron (``<id>/cartao.json`` +
``<id>/modelo.onnx``) e uma cópia dos resultados. Os dois entram pelo mesmo botão: a comparação
vai para ``dados_app/avaliacoes/<id>/`` e o modelo, se houver, é instalado em ``modelos/``.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

ID_VALIDO = re.compile(r"[0-9]{8}-[0-9]{6}(-[0-9]+)?")
NOME_VALIDO = re.compile(r"[\w .()-]+\.(png|csv)", re.UNICODE)
EXTENSOES = (".png", ".csv")
LIMITE_ARQUIVO = 25 * 1024 * 1024  # figura ou tabela; o modelo .onnx segue pela instalação


class Avaliacoes:
    def __init__(self, pasta_dados: Callable[[], Path], instalar_modelo: Callable[[bytes], str]):
        self._pasta_dados = pasta_dados
        self._instalar_modelo = instalar_modelo

    @property
    def pasta(self) -> Path:
        return self._pasta_dados() / "avaliacoes"

    # ---------------------------------------------------------------- importação

    def importar(self, dados: bytes, nome_arquivo: str = "resultados.zip") -> dict:
        """Guarda a comparação e instala o modelo que vier no .zip. Devolve o que entrou."""
        try:
            z = zipfile.ZipFile(io.BytesIO(dados))
        except zipfile.BadZipFile as erro:
            raise ValueError("O arquivo não é um .zip.") from erro
        nomes = [n for n in z.namelist() if "__MACOSX" not in n]
        resumos = sorted((n for n in nomes if n.split("/")[-1] == "resumo.json"), key=lambda n: n.count("/"))
        cartoes = [n for n in nomes if n.split("/")[-1] == "cartao.json"]
        if not resumos and not cartoes:
            raise ValueError("O .zip não tem os resultados do Colab (resumo.json) nem um modelo (cartao.json).")

        resultado: dict = {"avaliacao": None, "modelo": None, "avisos": []}
        if cartoes:
            try:
                resultado["modelo"] = self._instalar_modelo(dados)
            except ValueError as erro:
                resultado["avisos"].append(str(erro))
        if resumos:
            resultado["avaliacao"] = self._guardar(z, resumos[0], nome_arquivo, resultado["modelo"])
        return resultado

    def _guardar(self, z: zipfile.ZipFile, caminho_resumo: str, nome_arquivo: str, modelo: str | None) -> str:
        try:
            resumo = json.loads(z.read(caminho_resumo).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as erro:
            raise ValueError("O resumo.json está corrompido.") from erro
        teste = resumo.get("teste")
        if not isinstance(teste, dict) or not teste:
            raise ValueError("O resumo.json não tem o resultado dos modelos no teste.")

        id_ = self._novo_id()
        destino = self.pasta / id_
        destino.mkdir(parents=True)
        (destino / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False), encoding="utf-8")
        prefixo = caminho_resumo[: -len("resumo.json")]
        figuras, tabelas = [], []
        for info in z.infolist():
            nome = info.filename
            if not nome.startswith(prefixo) or "/" in nome[len(prefixo):] or info.file_size > LIMITE_ARQUIVO:
                continue  # só o que está ao lado do resumo.json (as subpastas, como recuperar/, ficam de fora)
            base = nome[len(prefixo):]
            if not NOME_VALIDO.fullmatch(base):
                continue
            (destino / base).write_bytes(z.read(nome))
            (figuras if base.endswith(".png") else tabelas).append(base)

        melhor = max(teste, key=lambda m: teste[m].get("mAP50") or 0)
        fotos = resumo.get("fotos", {})
        meta = {
            "id": id_,
            "importado_em": datetime.now().isoformat(timespec="seconds"),
            "arquivo": nome_arquivo,
            "modelos": list(teste),
            "melhor": melhor,
            "mAP50_melhor": teste[melhor].get("mAP50"),
            "fotos": {k: len(v) if isinstance(v, list) else v for k, v in fotos.items()},
            "gpu": resumo.get("gpu"),
            "figuras": sorted(figuras),
            "tabelas": sorted(tabelas),
            "modelo_instalado": modelo,
        }
        (destino / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        return id_

    def _novo_id(self) -> str:
        base = datetime.now().strftime("%Y%m%d-%H%M%S")
        id_, n = base, 1
        while (self.pasta / id_).exists():
            n += 1
            id_ = f"{base}-{n}"
        return id_

    # ---------------------------------------------------------------- leitura

    def listar(self) -> list[dict]:
        if not self.pasta.exists():
            return []
        metas = []
        for arq in self.pasta.glob("*/meta.json"):
            try:
                metas.append(json.loads(arq.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return sorted(metas, key=lambda m: m.get("importado_em", ""), reverse=True)

    def _pasta_de(self, id_: str) -> Path:
        if not ID_VALIDO.fullmatch(id_ or ""):
            raise KeyError(id_)
        pasta = self.pasta / id_
        if not (pasta / "meta.json").exists():
            raise KeyError(id_)
        return pasta

    def obter(self, id_: str) -> dict:
        pasta = self._pasta_de(id_)
        meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
        resumo = json.loads((pasta / "resumo.json").read_text(encoding="utf-8"))
        tabelas = {}
        for nome in meta.get("tabelas", []):
            try:
                tabelas[nome] = ler_csv(pasta / nome)
            except (OSError, UnicodeDecodeError, csv.Error):
                continue
        return {"meta": meta, "resumo": resumo, "tabelas": tabelas}

    def arquivo(self, id_: str, nome: str) -> Path:
        pasta = self._pasta_de(id_)
        if not NOME_VALIDO.fullmatch(nome or "") or not (pasta / nome).is_file():
            raise KeyError(nome)
        return pasta / nome

    def apagar(self, id_: str) -> None:
        shutil.rmtree(self._pasta_de(id_))


def ler_csv(caminho: Path) -> dict:
    """Tabela do pandas gravada em .csv: {"colunas": [...], "linhas": [[...], ...]}, números como número."""
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.reader(f))
    if not linhas:
        return {"colunas": [], "linhas": []}

    def valor(v: str):
        try:
            n = float(v)
        except ValueError:
            return v
        return int(n) if n.is_integer() and "." not in v else n

    return {"colunas": linhas[0], "linhas": [[valor(v) for v in l] for l in linhas[1:]]}
