"""Registro das medições para comparar os modelos: cada medida roda no DA3 e no MoGe-2, com e sem referência; quem
mede informa o valor real quando souber, e o resumo mostra o erro de cada modelo e modo ao longo do tempo.

Fotos guardadas sem nenhuma alteração (os bytes que chegaram, com EXIF, lente e tudo) em ``<pasta>/fotos/``, com o
nome pelo hash do conteúdo; o registro é um JSON Lines em ``<pasta>/registro.jsonl`` (uma linha por medição; a
linha mais nova de um mesmo ``id`` vale).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import numpy as np

EXTENSOES = {b"\xff\xd8\xff": ".jpg", b"\x89PNG": ".png", b"RIFF": ".webp"}
MODOS = ("sem_referencia", "com_referencia")
MEDIDAS = ("comprimento", "largura", "altura", "espessura", "distancia")


def _extensao(dados: bytes) -> str:
    for inicio, ext in EXTENSOES.items():
        if dados.startswith(inicio):
            return ext
    if dados[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return ".heic"
    return ".jpg"


class Registro:
    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)
        self._trava = threading.Lock()
        self.versao = 0

    @property
    def arquivo(self) -> Path:
        return self.pasta / "registro.jsonl"

    # ------------------------------------------------------------ fotos
    def guardar_foto(self, dados: bytes) -> str:
        """Guarda os bytes como chegaram (qualidade e metadados intactos). Devolve o código da foto."""
        codigo = hashlib.sha1(dados).hexdigest()[:16]
        pasta = self.pasta / "fotos"
        pasta.mkdir(parents=True, exist_ok=True)
        if not any(pasta.glob(f"{codigo}.*")):
            (pasta / f"{codigo}{_extensao(dados)}").write_bytes(dados)
        return codigo

    def caminho_foto(self, codigo: str) -> Path | None:
        if not codigo.isalnum():
            return None
        achados = list((self.pasta / "fotos").glob(f"{codigo}.*"))
        return achados[0] if achados else None

    # ------------------------------------------------------------ medições
    def _todas(self) -> dict[str, dict]:
        if not self.arquivo.exists():
            return {}
        saida = {}
        for linha in self.arquivo.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                e = json.loads(linha)
                saida[e["id"]] = e
        return saida

    def _gravar(self, entrada: dict) -> dict:
        self.pasta.mkdir(parents=True, exist_ok=True)
        with self._trava, open(self.arquivo, "a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
            self.versao += 1
        return entrada

    def adicionar(self, foto: str, pista: dict, referencia: dict | None, resultados: dict, origem: str = "tela") -> dict:
        entrada = {"id": f"{int(time.time() * 1000):x}", "quando": time.time(), "origem": origem, "foto": foto,
                   "pista": pista, "referencia": referencia, "resultados": resultados, "real": {}}
        return self._gravar(com_erros(entrada))

    def informar_real(self, codigo: str, real: dict) -> dict:
        e = self._todas().get(codigo)
        if e is None:
            raise KeyError(codigo)
        e["real"] = {k: float(v) for k, v in real.items() if k in MEDIDAS and v is not None and float(v) > 0}
        return self._gravar(com_erros(e))

    def entradas(self, limite: int = 200) -> list[dict]:
        return sorted(self._todas().values(), key=lambda e: e["quando"], reverse=True)[:limite]

    def resumo(self) -> dict:
        """Erro mediano (valor absoluto, %) por modelo e modo, nas medições com valor real informado."""
        erros: dict = {}
        for e in self._todas().values():
            for modelo, modos in e.get("erros", {}).items():
                for modo, por_medida in modos.items():
                    erros.setdefault(modelo, {}).setdefault(modo, []).extend(abs(v) for v in por_medida.values())
        return {
            modelo: {modo: {"n": len(v), "erro_mediano_pct": round(float(np.median(v)) * 100, 1),
                            "erro_maximo_pct": round(float(np.max(v)) * 100, 1)} for modo, v in modos.items() if v}
            for modelo, modos in erros.items()
        }


def com_erros(entrada: dict) -> dict:
    """Erro relativo de cada modelo e modo em cada medida que tem valor real."""
    erros: dict = {}
    for modelo, modos in entrada.get("resultados", {}).items():
        for modo in MODOS:
            m = modos.get(modo)
            if not isinstance(m, dict):
                continue
            for medida, real in entrada.get("real", {}).items():
                previsto = m.get(f"{medida}_cm")
                if previsto is not None and real:
                    erros.setdefault(modelo, {}).setdefault(modo, {})[medida] = round((previsto - real) / real, 4)
    return {**entrada, "erros": erros}
