"""Backup e restauração dos dados do Pyron (inspeções, imagens, matrizes, configurações e logotipo).

O backup é um .zip com a mesma estrutura de ``dados_app``. O banco SQLite é copiado pela API de
backup do próprio SQLite, que gera uma cópia consistente mesmo com o programa aberto.

Ficam de fora o que é grande e se refaz: vídeos enviados (``videos/``), treinos (``treinos/``),
backups anteriores e arquivos temporários.

A restauração troca os dados atuais pelos do backup. Antes, o estado atual vai para
``dados_app/backups/antes_de_restaurar_<data>.zip``: um engano tem volta.
"""

from __future__ import annotations

import io
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

BANCO = "inspecoes.sqlite"
FORA = {"videos", "treinos", "backups", "__pycache__"}
RESTAURAVEIS = {"config.json", "logo.png", "monitor_vistos.json", "imagens", "matrizes", "avaliacoes"}


def _arquivos(pasta: Path):
    for p in sorted(pasta.rglob("*")):
        rel = p.relative_to(pasta)
        if p.is_dir() or rel.parts[0] in FORA or p.name == BANCO or p.suffix in (".tmp", ".log"):
            continue
        yield p, rel


def gerar(pasta: Path) -> bytes:
    """Zip com os dados de ``pasta`` (o banco copiado de forma consistente)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        banco = pasta / BANCO
        if banco.exists():
            with tempfile.TemporaryDirectory() as tmp:
                copia = Path(tmp) / BANCO
                origem, destino = sqlite3.connect(banco), sqlite3.connect(copia)
                with destino:
                    origem.backup(destino)
                origem.close()
                destino.close()
                z.write(copia, BANCO)
        for p, rel in _arquivos(pasta):
            z.write(p, rel.as_posix())
        z.writestr("LEIA-ME.txt", f"Backup do Pyron gerado em {datetime.now():%d/%m/%Y %H:%M}.\n"
                                  "Restaure em Configurações › Dados e sistema › Restaurar backup.\n")
    return buf.getvalue()


def contar(pasta: Path) -> dict:
    """Tamanho dos dados e quantas imagens guardadas, para a tela."""
    total = sum(p.stat().st_size for p in pasta.rglob("*") if p.is_file()) if pasta.exists() else 0
    videos = sum(p.stat().st_size for p in (pasta / "videos").rglob("*") if p.is_file()) if (pasta / "videos").exists() else 0
    imagens = len(list((pasta / "imagens").glob("*.jpg"))) if (pasta / "imagens").exists() else 0
    return {"bytes": total, "bytes_videos": videos, "arquivos_imagem": imagens}


def restaurar(pasta: Path, dados: bytes) -> dict:
    """Troca os dados de ``pasta`` pelos do backup; guarda antes uma cópia do estado atual."""
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
    except zipfile.BadZipFile as erro:
        raise ValueError("O arquivo não é um .zip de backup do Pyron.") from erro
    nomes = z.namelist()
    if BANCO not in nomes:
        raise ValueError("Este .zip não é um backup do Pyron: falta o banco de inspeções.")
    if any(n.startswith("/") or ".." in Path(n).parts for n in nomes):
        raise ValueError("Backup com caminhos inválidos.")
    pasta.mkdir(parents=True, exist_ok=True)
    seguranca = pasta / "backups" / f"antes_de_restaurar_{datetime.now():%Y%m%d_%H%M%S}.zip"
    seguranca.parent.mkdir(parents=True, exist_ok=True)
    seguranca.write_bytes(gerar(pasta))
    with tempfile.TemporaryDirectory() as tmp:
        z.extractall(tmp)
        origem = Path(tmp)
        # confere que o banco do backup abre antes de trocar qualquer coisa
        con = sqlite3.connect(origem / BANCO)
        try:
            con.execute("SELECT count(*) FROM analises").fetchone()
        except sqlite3.DatabaseError as erro:
            raise ValueError("O banco de inspeções do backup está danificado.") from erro
        finally:
            con.close()
        # O banco é trocado por dentro (API de backup do SQLite), sem apagar o arquivo que o programa usa.
        src, dst = sqlite3.connect(origem / BANCO), sqlite3.connect(pasta / BANCO)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        for nome in RESTAURAVEIS:
            alvo = pasta / nome
            if alvo.is_dir():
                shutil.rmtree(alvo)
            elif alvo.exists():
                alvo.unlink()
            fonte = origem / nome
            if fonte.is_dir():
                shutil.copytree(fonte, alvo)
            elif fonte.exists():
                shutil.copy2(fonte, alvo)
        (pasta / "imagens").mkdir(exist_ok=True)
        (pasta / "matrizes").mkdir(exist_ok=True)
    con = sqlite3.connect(pasta / BANCO)
    try:
        n = con.execute("SELECT count(*) FROM analises").fetchone()[0]
    finally:
        con.close()
    return {"inspecoes": n, "copia_anterior": str(seguranca)}
