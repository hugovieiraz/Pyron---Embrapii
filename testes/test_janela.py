"""Janela própria (0.9, F5): adaptador de js/janela.js no Node e o projeto do Pyron desktop (Tauri) em desktop/."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
INTERFACE = RAIZ / "app" / "interface"
DESKTOP = RAIZ / "desktop"


def test_adaptador_nos_tres_hospedeiros() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("sem Node.js neste computador")
    r = subprocess.run([node, "--test", str(RAIZ / "testes" / "js" / "janela.test.mjs")],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_casca_usa_so_o_adaptador() -> None:
    casca = (INTERFACE / "js" / "casca.js").read_text(encoding="utf-8")
    # nenhum acesso direto ao hospedeiro fora de js/janela.js
    assert "chrome.webview" not in casca and "__TAURI__" not in casca
    assert 'from "./janela.js"' in casca


def test_capability_da_abertura_e_minima() -> None:
    """A abertura (conteúdo do próprio executável) só arrasta, minimiza, fecha e pede para reiniciar."""
    cap = json.loads((DESKTOP / "src-tauri" / "capabilities" / "abertura.json").read_text(encoding="utf-8"))
    assert cap["windows"] == ["principal"]
    assert "remote" not in cap
    assert sorted(cap["permissions"]) == sorted([
        "core:window:allow-start-dragging", "core:window:allow-minimize", "core:window:allow-close", "allow-reiniciar",
    ])


def test_servidor_so_recebe_janela_eventos_e_aviso() -> None:
    """A página do servidor (local ou remoto) não ganha shell, fs nem comando do app: só janela, eventos e aviso."""
    fonte = "\n".join(p.read_text(encoding="utf-8") for p in sorted((DESKTOP / "src-tauri" / "src").glob("*.rs")))
    bloco = re.search(r"const PERMISSOES_DO_SERVIDOR: &\[&str\] = &\[(.*?)\];", fonte, flags=re.S).group(1)
    permissoes = re.findall(r'"([^"]+)"', bloco)
    assert permissoes, "lista de permissões não encontrada"
    for p in permissoes:
        assert p.startswith(("core:window:", "core:event:", "notification:")), p
    assert not [p for p in permissoes if p.endswith(":default")], "nada de conjuntos inteiros"
    cargo = (DESKTOP / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    for plugin in ("tauri-plugin-shell", "tauri-plugin-fs", "tauri-plugin-opener", "tauri-plugin-process"):
        assert plugin not in cargo and plugin.replace("-", "_") not in fonte, plugin
    # o servidor sobe com argumentos fixos, nunca vindos da página
    assert '"--sem-navegador", "--auto-encerrar"' in fonte


def test_versao_igual_no_cargo_e_no_tauri() -> None:
    conf = json.loads((DESKTOP / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    cargo = (DESKTOP / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    assert re.search(r'^version = "([^"]+)"', cargo, flags=re.M).group(1) == conf["version"]
    assert conf["app"]["withGlobalTauri"] is True
    assert conf["app"]["windows"] == []  # a janela nasce no main.rs, com os filtros de navegação
