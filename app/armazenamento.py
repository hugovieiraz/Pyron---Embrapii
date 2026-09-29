"""Inspeções salvas: SQLite para os dados, arquivos para a imagem original e a matriz."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np


class Armazenamento:
    def __init__(self, pasta: Path):
        self.pasta = pasta
        (pasta / "imagens").mkdir(parents=True, exist_ok=True)
        (pasta / "matrizes").mkdir(parents=True, exist_ok=True)
        self.banco = pasta / "inspecoes.sqlite"
        with self._conexao() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS analises ("
                "id TEXT PRIMARY KEY, criado_em TEXT, nome TEXT, severidade TEXT, dados TEXT)"
            )

    def _conexao(self) -> sqlite3.Connection:
        return sqlite3.connect(self.banco)

    def salvar(self, analise: dict, original: bytes | None = None, matriz: np.ndarray | None = None) -> None:
        if original is not None:
            (self.pasta / "imagens" / f"{analise['id']}.jpg").write_bytes(original)
        if matriz is not None:
            np.save(self.pasta / "matrizes" / f"{analise['id']}.npy", matriz.astype(np.float32))
        with self._conexao() as c:
            c.execute(
                "INSERT OR REPLACE INTO analises (id, criado_em, nome, severidade, dados) VALUES (?, ?, ?, ?, ?)",
                (
                    analise["id"],
                    analise["criado_em"],
                    analise["arquivo"],
                    analise["resumo"]["severidade"],
                    json.dumps(analise, ensure_ascii=False),
                ),
            )

    def obter(self, id_: str) -> dict | None:
        with self._conexao() as c:
            linha = c.execute("SELECT dados FROM analises WHERE id = ?", (id_,)).fetchone()
        return json.loads(linha[0]) if linha else None

    def matriz(self, id_: str) -> np.ndarray | None:
        arq = self.pasta / "matrizes" / f"{id_}.npy"
        return np.load(arq) if arq.exists() else None

    def original(self, id_: str) -> bytes | None:
        arq = self.pasta / "imagens" / f"{id_}.jpg"
        return arq.read_bytes() if arq.exists() else None

    def salvar_foto(self, id_: str, foto: bytes) -> None:
        (self.pasta / "imagens" / f"{id_}_foto.jpg").write_bytes(foto)

    def foto(self, id_: str) -> bytes | None:
        arq = self.pasta / "imagens" / f"{id_}_foto.jpg"
        return arq.read_bytes() if arq.exists() else None

    def listar(self) -> list[dict]:
        with self._conexao() as c:
            linhas = c.execute("SELECT dados FROM analises ORDER BY criado_em DESC").fetchall()
        itens = []
        for (dados,) in linhas:
            a = json.loads(dados)
            itens.append(
                {
                    "id": a["id"],
                    "arquivo": a["arquivo"],
                    "criado_em": a["criado_em"],
                    "data_captura": a["metadados"].get("data_hora", ""),
                    "radiometrica": a["radiometrica"],
                    "modelo": a["modelo"]["nome"],
                    "resumo": a["resumo"],
                    "identificacao": a.get("identificacao", {}),
                }
            )
        return itens

    def apagar(self, id_: str) -> bool:
        with self._conexao() as c:
            n = c.execute("DELETE FROM analises WHERE id = ?", (id_,)).rowcount
        for arq in (f"imagens/{id_}.jpg", f"imagens/{id_}_foto.jpg", f"matrizes/{id_}.npy"):
            (self.pasta / arq).unlink(missing_ok=True)
        return n > 0
