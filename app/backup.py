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
# Fora do backup: vídeos e treinos (grandes, refazíveis), backups antigos, o perfil do Edge onde a
# interface roda ("janela": ~500 MB de componentes que o próprio Edge baixa, e arquivos que ele trava
# com a janela aberta) e o certificado do celular ("celular": chave privada, refeita sozinha).
FORA = {"videos", "treinos", "backups", "__pycache__", "janela", "celular"}
RESTAURAVEIS = {"config.json", "logo.png", "monitor_vistos.json", "imagens", "matrizes", "avaliacoes"}


def _arquivos(pasta: Path):
    for p in sorted(pasta.rglob("*")):
        rel = p.relative_to(pasta)
        # o banco vai pela API de backup; os arquivos -wal e -shm do modo WAL são do banco aberto, não se copiam
        if p.is_dir() or rel.parts[0] in FORA or p.name.startswith(BANCO) or p.suffix in (".tmp", ".log"):
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
                    _sem_sessoes(destino)
                origem.close()
                destino.close()
                z.write(copia, BANCO)
        for p, rel in _arquivos(pasta):
            z.write(p, rel.as_posix())
        z.writestr("LEIA-ME.txt", f"Backup do Pyron gerado em {datetime.now():%d/%m/%Y %H:%M}.\n"
                                  "Restaure em Configurações › Dados e sistema › Restaurar backup.\n")
    return buf.getvalue()


def _sem_sessoes(con: sqlite3.Connection) -> None:
    """Sessões de quem entrou (modo servidor) não viajam no backup nem voltam numa restauração."""
    if con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sessoes'").fetchone():
        con.execute("DELETE FROM sessoes")


def contar(pasta: Path) -> dict:
    """Tamanho dos dados e quantas imagens guardadas, para a tela (sem o perfil do navegador nem o certificado)."""
    total = sum(p.stat().st_size for p in pasta.rglob("*")
                if p.is_file() and p.relative_to(pasta).parts[0] not in {"janela", "celular"}) if pasta.exists() else 0
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
            with dst:
                _sem_sessoes(dst)
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


def main(argv=None) -> int:
    """Backup pela linha de comando (agendado no modo servidor; o banco é copiado com o Pyron no ar).

    python -m app.backup --dados <pasta de dados> --saida <pasta>   (grava pyron_backup_<data>.zip; guarda os 30 últimos)
    """
    import argparse
    import os

    ap = argparse.ArgumentParser(prog="python -m app.backup", description="Gera o .zip de backup dos dados do Pyron.")
    ap.add_argument("--dados", help="pasta de dados (padrão: PYRON_DADOS ou app/dados_app)")
    ap.add_argument("--saida", required=True, help="pasta onde gravar o .zip")
    ap.add_argument("--manter", type=int, default=30, help="quantos backups guardar nessa pasta (padrão 30)")
    args = ap.parse_args(argv)
    pasta = Path(args.dados or os.environ.get("PYRON_DADOS") or Path(__file__).resolve().parent / "dados_app")
    if not (pasta / BANCO).exists():
        print(f"Não há banco do Pyron em {pasta}.")
        return 2
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    arquivo = saida / f"pyron_backup_{datetime.now():%Y%m%d_%H%M%S}.zip"
    arquivo.write_bytes(gerar(pasta))
    antigos = sorted(saida.glob("pyron_backup_*.zip"))[:-max(1, args.manter)]
    for velho in antigos:
        velho.unlink()
    print(f"Backup gravado em {arquivo} ({arquivo.stat().st_size // 1024} KB).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
