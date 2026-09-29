"""Gera o Pyron.exe (lançador) e coloca um na área de trabalho.

O .exe é compilado com o csc.exe do .NET Framework 4, que já vem com o Windows: nada para baixar.
Ele guarda o caminho desta pasta do projeto; se o projeto mudar de lugar, rode de novo.
O ícone vem de marca/gerar_marca.py. A logo da tela de abertura é lida da pasta do projeto: com a
imagem embutida o .exe ficou grande e o Controle Inteligente de Aplicativos do Windows o bloqueou.

Uso (na pasta do projeto):

    python lancador/construir.py                # gera lancador/dist/Pyron.exe e copia para a área de trabalho
    python lancador/construir.py --sem-copiar   # só gera
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PROJETO = AQUI.parent
DIST = AQUI / "dist"

MANIFESTO = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <assemblyIdentity version="0.1.0.0" name="Pyron.Lancador" type="win32"/>
  <description>Pyron</description>
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security><requestedPrivileges><requestedExecutionLevel level="asInvoker" uiAccess="false"/></requestedPrivileges></security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application><supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/></application>
  </compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true</dpiAware>
    </windowsSettings>
  </application>
</assembly>
"""


def compilador() -> Path:
    raiz = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET"
    for pasta in ("Framework64", "Framework"):
        candidatos = sorted((raiz / pasta).glob("v4.*/csc.exe"))
        if candidatos:
            return candidatos[-1]
    sys.exit("csc.exe do .NET Framework 4 não encontrado.")


def area_de_trabalho() -> Path:
    """A área de trabalho de verdade (pode estar no OneDrive e ter nome traduzido)."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as chave:
            valor, _ = winreg.QueryValueEx(chave, "Desktop")
        return Path(os.path.expandvars(valor))
    except OSError:
        return Path.home() / "Desktop"


def construir() -> Path:
    DIST.mkdir(exist_ok=True)
    obj = AQUI / "obj"
    obj.mkdir(exist_ok=True)

    icone = obj / "pyron.ico"
    subprocess.run([sys.executable, str(PROJETO / "marca" / "gerar_marca.py"), str(icone)], check=True)

    local = obj / "Local.cs"
    caminho = str(PROJETO).replace('"', '""')
    local.write_text(
        "namespace Pyron { static class Local { public const string Projeto = @\"" + caminho + "\"; } }\n",
        encoding="utf-8-sig",
    )
    manifesto = obj / "Pyron.manifest"
    manifesto.write_text(MANIFESTO, encoding="utf-8")

    saida = DIST / "Pyron.exe"
    comando = [
        str(compilador()), "/nologo", "/target:winexe", "/optimize+", "/codepage:65001",
        f"/win32icon:{icone}", f"/win32manifest:{manifesto}", f"/out:{saida}",
        "/r:System.dll", "/r:System.Drawing.dll", "/r:System.Windows.Forms.dll",
        str(AQUI / "Pyron.cs"), str(local),
    ]
    r = subprocess.run(comando, capture_output=True, text=True, encoding="oem", errors="replace")
    if r.returncode != 0:
        sys.exit("Falha na compilação:\n" + r.stdout + r.stderr)
    print("gerado:", saida, f"({saida.stat().st_size / 1024:.0f} KB)")
    return saida


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sem-copiar", action="store_true", help="não copiar para a área de trabalho")
    args = ap.parse_args()
    exe = construir()
    if not args.sem_copiar:
        destino = area_de_trabalho() / "Pyron.exe"
        shutil.copy2(exe, destino)
        print("copiado para:", destino)


if __name__ == "__main__":
    main()
