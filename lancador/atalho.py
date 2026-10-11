"""Cria o atalho "Abrir Pyron" na área de trabalho, que abre o Pyron sem o Pyron.exe.

O Controle Inteligente de Aplicativos do Windows decide pela reputação na nuvem e às vezes passa a
barrar o Pyron.exe, que não tem assinatura digital (aconteceu em 11/10/2026 com o mesmo arquivo de
28/09). O atalho chama direto o ``pythonw.exe`` do ambiente do projeto, assinado pela Python Software
Foundation, com ``-m app.iniciar --janela --auto-encerrar``: sobe o servidor sem console, abre a
janela própria e desliga quando ela fecha. Só não tem a tela de abertura do .exe.

Uso: ``.venv/Scripts/python.exe lancador/atalho.py``
"""

from __future__ import annotations

import subprocess
from pathlib import Path

PROJETO = Path(__file__).resolve().parents[1]
PYTHONW = PROJETO / ".venv" / "Scripts" / "pythonw.exe"
ICONE = PROJETO / "marca" / "pyron.ico"
NOME = "Abrir Pyron.lnk"


def criar() -> Path:
    if not PYTHONW.exists():
        raise SystemExit(f"Não achei {PYTHONW}: crie o ambiente do projeto antes.")
    aspas = lambda texto: str(texto).replace("'", "''")  # noqa: E731  (texto entre aspas simples no PowerShell)
    comando = (
        "$area = [Environment]::GetFolderPath('Desktop'); "
        f"$a = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $area '{NOME}')); "
        f"$a.TargetPath = '{aspas(PYTHONW)}'; "
        "$a.Arguments = '-m app.iniciar --janela --auto-encerrar'; "
        f"$a.WorkingDirectory = '{aspas(PROJETO)}'; "
        f"$a.IconLocation = '{aspas(ICONE)},0'; "
        "$a.Description = 'Pyron: manutenção preditiva por termografia'; "
        "$a.Save(); $a.FullName"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", comando], capture_output=True, text=True, check=True)
    return Path(r.stdout.strip())


if __name__ == "__main__":
    print("atalho:", criar())
