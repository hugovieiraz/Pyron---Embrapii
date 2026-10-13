"""Cria o atalho "Pyron Apresentação" na área de trabalho.

Chama o ``pythonw.exe`` do ambiente do projeto (assinado pela Python Software Foundation, que o
Controle Inteligente de Aplicativos do Windows deixa rodar) com ``-m apresentacao``.

Uso: ``.venv/Scripts/python.exe -m apresentacao.atalho``
"""

from __future__ import annotations

import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PYTHONW = RAIZ / ".venv" / "Scripts" / "pythonw.exe"
ICONE = RAIZ / "marca" / "pyron.ico"
NOME = "Pyron Apresentação.lnk"


def criar() -> str:
    aspas = lambda texto: str(texto).replace("'", "''")  # noqa: E731
    comando = (
        "$area = [Environment]::GetFolderPath('Desktop'); "
        f"$a = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $area '{NOME}')); "
        f"$a.TargetPath = '{aspas(PYTHONW)}'; $a.Arguments = '-m apresentacao'; "
        f"$a.WorkingDirectory = '{aspas(RAIZ)}'; $a.IconLocation = '{aspas(ICONE)},0'; "
        "$a.Description = 'Pyron: apresentação da identificação de para-raios'; $a.Save(); $a.FullName"
    )
    return subprocess.run(["powershell", "-NoProfile", "-Command", comando], capture_output=True, text=True, check=True).stdout.strip()


if __name__ == "__main__":
    print("atalho:", criar())
