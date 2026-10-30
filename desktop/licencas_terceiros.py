"""Gera desktop/LICENCAS-TERCEIROS.txt: o aviso de licenças que acompanha o pyron-desktop.exe ao distribuir.

Lê `cargo metadata` (só o que entra no executável do Windows) e junta, para cada crate, nome, versão, licença,
repositório e os arquivos de licença que ela traz (LICENSE*, COPYING*, NOTICE*). Crate sem arquivo de licença fica
com o link do texto padrão no SPDX. Licenças aprovadas pelo usuário em 30/10/2026 (docs/v09/5-tauri.md).

Uso: python desktop/licencas_terceiros.py   (precisa do cargo no PATH ou em %USERPROFILE%\\.cargo\\bin)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PROJETO_TAURI = AQUI / "src-tauri"
SAIDA = AQUI / "LICENCAS-TERCEIROS.txt"
ARQUIVOS_DE_LICENCA = re.compile(r"^(licen[cs]e|copying|notice)", re.I)
# o que pode aparecer sem perguntar de novo: MIT/Apache e as aprovadas em 30/10/2026
APROVADAS = {"MIT", "Apache-2.0", "MPL-2.0", "Unicode-3.0", "BSD-3-Clause", "Zlib",
             "Unlicense", "0BSD", "CC0-1.0", "MIT-0", "BSD-2-Clause", "ISC"}


def _cargo() -> str:
    return shutil.which("cargo") or str(Path(os.environ["USERPROFILE"]) / ".cargo" / "bin" / "cargo.exe")


def _ids(licenca: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9.\-]+", licenca.replace("/", " OR "))) - {"OR", "AND", "WITH"}


def main() -> None:
    meta = json.loads(subprocess.run(
        [_cargo(), "metadata", "--format-version", "1", "--filter-platform", "x86_64-pc-windows-msvc"],
        cwd=PROJETO_TAURI, capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    usados = {n["id"] for n in meta["resolve"]["nodes"]}
    pacotes = sorted((p for p in meta["packages"] if p["id"] in usados and p["source"]),
                     key=lambda p: (p["name"], p["version"]))
    fora = [f"{p['name']} {p['version']}: {p.get('license')}" for p in pacotes
            if not p.get("license") or not _ids(p["license"]) & APROVADAS]
    if fora:
        raise SystemExit("licença ainda não aprovada (perguntar ao usuário):\n" + "\n".join(fora))

    partes = [
        "Pyron desktop: componentes de terceiros",
        "",
        f"O pyron-desktop.exe inclui {len(pacotes)} bibliotecas de código aberto (crates do Rust), cada uma sob a",
        "licença indicada. Nenhuma foi modificada. Texto de cada licença abaixo, como a biblioteca o distribui.",
        "",
    ]
    for p in pacotes:
        pasta = Path(p["manifest_path"]).parent
        textos = sorted(f for f in pasta.iterdir() if f.is_file() and ARQUIVOS_DE_LICENCA.match(f.name))
        partes += ["=" * 100, f"{p['name']} {p['version']}", f"Licença: {p.get('license')}"]
        if p.get("repository"):
            partes.append(f"Fonte: {p['repository']}")
        partes.append("")
        for f in textos:
            partes += [f"--- {f.name}", f.read_text(encoding="utf-8", errors="replace").strip(), ""]
        if not textos:
            partes += [f"Texto padrão: https://spdx.org/licenses/{i}.html" for i in sorted(_ids(p["license"]))] + [""]
    SAIDA.write_text("\n".join(partes) + "\n", encoding="utf-8")
    print(f"{SAIDA} ({len(pacotes)} bibliotecas)")


if __name__ == "__main__":
    main()
