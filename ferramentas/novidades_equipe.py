"""Mostra, no começo de cada sessão do Claude Code, o que a outra pessoa da equipe enviou ao GitHub.

Roda pelo gancho SessionStart de `.claude/settings.json`; o que este script imprime entra no contexto do
Claude. Busca o `origin` e lista o que chegou ao `origin/main` desde a última sessão neste computador:
os commits de outros autores (autor diferente do `git config user.email` daqui) e as entradas novas do
diário da equipe (`docs/equipe/diario.md`). A última sessão vista fica em `.git/pyron-ultima-visita`,
que é deste clone e não vai para o repositório. Só biblioteca padrão; nunca falha a sessão.

Uso à mão: python ferramentas/novidades_equipe.py [--tudo]   (--tudo: ignora a marca e mostra 7 dias)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIARIO = "docs/equipe/diario.md"
MARCA = RAIZ / ".git" / "pyron-ultima-visita"
MAX_COMMITS = 25
MAX_LINHAS_DIARIO = 80
VAZIO = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # árvore vazia do git: compara com "nada"


def git(*args: str, tempo: int = 20) -> str:
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=tempo)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"git {args[0]} falhou")
    return r.stdout.strip()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # o console do Windows não é UTF-8; o Claude lê a saída como UTF-8
    tudo = "--tudo" in sys.argv
    avisos = []
    try:
        git("fetch", "--quiet", "origin", tempo=30)
    except Exception as erro:  # noqa: BLE001 — sem rede, mostra o que já tinha sido buscado
        avisos.append(f"Não consegui buscar o GitHub agora ({erro}); mostrando o último estado buscado.")

    remoto = git("rev-parse", "origin/main")
    eu = git("config", "user.email").lower()
    marca = "" if tudo or not MARCA.exists() else MARCA.read_text(encoding="utf-8").strip()
    if marca and subprocess.run(["git", "cat-file", "-e", marca], cwd=RAIZ, capture_output=True).returncode != 0:
        marca = ""
    intervalo = [f"{marca}..origin/main"] if marca else ["--since=7.days", "origin/main"]

    linhas = git("log", *intervalo, f"--max-count={MAX_COMMITS * 4}", "--no-merges",
                 "--format=%h%x09%ad%x09%an%x09%ae%x09%s", "--date=format:%d/%m %H:%M")
    outros = [l.split("\t") for l in linhas.splitlines() if l and l.split("\t")[3].lower() != eu][:MAX_COMMITS]

    # base do diário: a última visita; sem ela, o main de 7 dias atrás (ou o arquivo inteiro, se for mais novo)
    base = marca or git("rev-list", "-1", "--before=7.days", "origin/main") or VAZIO
    diario = git("diff", "--unified=0", base, "origin/main", "--", DIARIO)
    novas = [l[1:] for l in diario.splitlines() if l.startswith("+") and not l.startswith("+++")][:MAX_LINHAS_DIARIO]

    atras = int(git("rev-list", "--count", "HEAD..origin/main") or 0)
    saida = ["# Novidades da equipe no GitHub (gancho de início de sessão)"]
    saida += avisos
    if not outros and not novas:
        saida.append("Nada novo dos outros desde a última sessão neste computador.")
    else:
        if outros:
            saida.append(f"\nCommits de outras pessoas em origin/main ({len(outros)}):")
            saida += [f"- {h} {d} {n}: {s}" for h, d, n, _e, s in outros]
        if novas:
            saida.append(f"\nEntradas novas em {DIARIO}:")
            saida += novas
        saida.append("\nPara o Claude: leia isto antes de começar, para não refazer o que já foi feito. "
                     "Ao resumir para o usuário, diga em poucas linhas o que a outra pessoa fez.")
    if atras:
        saida.append(f"Este computador está {atras} commit(s) atrás do origin/main: integre (git merge origin/main, "
                     "sem forçar) antes de mexer nos mesmos arquivos.")
    print("\n".join(saida))
    MARCA.write_text(remoto, encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:  # noqa: BLE001 — o gancho nunca pode impedir a sessão de abrir
        print(f"(novidades da equipe indisponíveis: {erro})")
