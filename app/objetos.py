"""Arquivos das inspeções (imagem original, foto visível, matriz de temperatura) por chave.

O banco guarda os dados; os arquivos pesados ficam num "armazém de objetos" endereçado por chave
(``imagens/<id>.jpg``, ``matrizes/<id>.npy``). Trocar o armazém não muda o resto do programa:

- ``ArmazemLocal`` (padrão): a pasta de dados, com as mesmas subpastas de sempre. O backup, as
  inspeções já salvas e o uso offline continuam iguais;
- ``ArmazemS3``: um bucket S3 (ou compatível: MinIO, R2, GCS em modo S3). Liga com
  ``PYRON_OBJETOS=s3://bucket/prefixo`` e o pacote opcional ``boto3`` (``pip install .[nuvem]``).
  Com ele, o backup .zip leva só o banco e as configurações: os arquivos ficam no bucket.

Toda gravação devolve o tamanho e o SHA-256 do conteúdo, que o banco registra para conferir a
integridade do arquivo depois (``Armazenamento`` guarda na tabela ``arquivos``).
"""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from typing import Protocol

import numpy as np


class Armazem(Protocol):
    def gravar(self, chave: str, dados: bytes) -> dict: ...
    def ler(self, chave: str) -> bytes | None: ...
    def apagar(self, chave: str) -> None: ...
    def descricao(self) -> str: ...


def _validar(chave: str) -> str:
    partes = chave.split("/")
    if not chave or chave.startswith("/") or "\\" in chave or any(p in ("", ".", "..") for p in partes):
        raise ValueError(f"Chave de arquivo inválida: {chave!r}")
    return chave


def _ficha(chave: str, dados: bytes) -> dict:
    return {"chave": chave, "bytes": len(dados), "sha256": hashlib.sha256(dados).hexdigest()}


class ArmazemLocal:
    """Arquivos numa pasta do computador; a chave é o caminho relativo dentro dela."""

    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)

    def _caminho(self, chave: str) -> Path:
        return self.pasta / _validar(chave)

    def gravar(self, chave: str, dados: bytes) -> dict:
        destino = self._caminho(chave)
        destino.parent.mkdir(parents=True, exist_ok=True)
        # grava ao lado e troca: um arquivo pela metade (queda de energia) nunca substitui o bom
        temporario = destino.with_name(destino.name + ".tmp")
        temporario.write_bytes(dados)
        os.replace(temporario, destino)
        return _ficha(chave, dados)

    def ler(self, chave: str) -> bytes | None:
        arq = self._caminho(chave)
        return arq.read_bytes() if arq.exists() else None

    def apagar(self, chave: str) -> None:
        self._caminho(chave).unlink(missing_ok=True)

    def descricao(self) -> str:
        return str(self.pasta)


class ArmazemS3:
    """Arquivos num bucket S3 (ou compatível). ``cliente`` é um cliente boto3 (os testes passam um falso)."""

    def __init__(self, bucket: str, prefixo: str = "", cliente=None):
        if cliente is None:
            try:
                import boto3  # opcional: só quem usa nuvem instala
            except ImportError as erro:
                raise RuntimeError("PYRON_OBJETOS aponta para S3, mas o pacote boto3 não está instalado "
                                   "(pip install .[nuvem]).") from erro
            # endpoint próprio (MinIO, R2…) e credenciais vêm das variáveis padrão da AWS
            cliente = boto3.client("s3", endpoint_url=os.environ.get("PYRON_S3_ENDPOINT") or None)
        self.bucket = bucket
        self.prefixo = prefixo.strip("/")
        self.cliente = cliente

    def _nome(self, chave: str) -> str:
        _validar(chave)
        return f"{self.prefixo}/{chave}" if self.prefixo else chave

    def gravar(self, chave: str, dados: bytes) -> dict:
        ficha = _ficha(chave, dados)
        self.cliente.put_object(Bucket=self.bucket, Key=self._nome(chave), Body=dados, Metadata={"sha256": ficha["sha256"]})
        return ficha

    def ler(self, chave: str) -> bytes | None:
        try:
            resposta = self.cliente.get_object(Bucket=self.bucket, Key=self._nome(chave))
        except Exception as erro:  # botocore.ClientError sem importar o botocore
            codigo = str(getattr(erro, "response", {}).get("Error", {}).get("Code", ""))
            if codigo in ("NoSuchKey", "404", "NotFound"):
                return None
            raise
        return resposta["Body"].read()

    def apagar(self, chave: str) -> None:
        self.cliente.delete_object(Bucket=self.bucket, Key=self._nome(chave))

    def descricao(self) -> str:
        return f"s3://{self.bucket}/{self.prefixo}".rstrip("/")


def do_ambiente(pasta_dados: Path) -> Armazem:
    """Armazém escolhido por ``PYRON_OBJETOS``: vazio ou ``local`` usa a pasta de dados; ``s3://bucket/prefixo`` usa o S3."""
    destino = (os.environ.get("PYRON_OBJETOS") or "").strip()
    if not destino or destino == "local":
        return ArmazemLocal(pasta_dados)
    if destino.startswith("s3://"):
        bucket, _, prefixo = destino[5:].partition("/")
        if not bucket:
            raise ValueError("PYRON_OBJETOS=s3://… precisa do nome do bucket.")
        return ArmazemS3(bucket, prefixo)
    raise ValueError(f"PYRON_OBJETOS desconhecido: {destino!r} (use 'local' ou 's3://bucket/prefixo').")


# ---------------------------------------------------------------- matriz de temperatura <-> bytes


def matriz_para_bytes(matriz: np.ndarray) -> bytes:
    """Mesmo formato .npy de sempre (float32), agora em memória para ir a qualquer armazém."""
    buf = io.BytesIO()
    np.save(buf, np.asarray(matriz, dtype=np.float32), allow_pickle=False)
    return buf.getvalue()


def bytes_para_matriz(dados: bytes) -> np.ndarray:
    return np.load(io.BytesIO(dados), allow_pickle=False)

