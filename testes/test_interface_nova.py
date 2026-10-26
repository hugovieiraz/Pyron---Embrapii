"""Interface nova (app/interface, servida em /nova): entrega dos arquivos e as regras do sistema de design."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import servidor

PASTA = Path(servidor.PASTA_APP) / "interface"


@pytest.fixture(scope="module")
def cliente():
    return TestClient(servidor.app)


def test_nova_redireciona_e_entrega_a_casca(cliente):
    r = cliente.get("/nova", follow_redirects=False)
    assert r.status_code in (301, 302, 307, 308) and r.headers["location"].endswith("/nova/")
    r = cliente.get("/nova/")
    assert r.status_code == 200
    assert '<script type="module" src="js/casca.js">' in r.text
    assert cliente.get("/").status_code == 200  # a interface atual continua em /


def _importados(arquivo: Path) -> set[Path]:
    """Módulos que um .js importa (estáticos e dinâmicos de caminho fixo), recursivamente."""
    vistos: set[Path] = set()
    fila = [arquivo]
    while fila:
        atual = fila.pop()
        if atual in vistos:
            continue
        vistos.add(atual)
        texto = atual.read_text(encoding="utf-8")
        for rel in re.findall(r'(?:from|import)\s*\(?\s*"(\.{1,2}/[^"]+\.js)"', texto):
            fila.append((atual.parent / rel).resolve())
    return vistos


def test_todo_modulo_importado_existe_e_e_servido(cliente):
    raizes = [PASTA / "js" / "casca.js", PASTA / "js" / "catalogo.js", *(PASTA / "js" / "telas").glob("*.js")]  # telas: carregadas sob demanda
    modulos = set().union(*(_importados(r.resolve()) for r in raizes))
    for m in modulos:
        assert m.exists(), m
        caminho = "/nova/" + m.relative_to(PASTA.resolve()).as_posix()
        r = cliente.get(caminho)
        assert r.status_code == 200 and "javascript" in r.headers["content-type"], caminho


def test_toda_tela_das_rotas_tem_modulo():
    rotas = (PASTA / "js" / "rotas.js").read_text(encoding="utf-8")
    nomes = set(re.findall(r'(?:modulo|detalhe): "([a-z_]+)"', rotas))
    assert nomes
    for n in nomes:
        assert (PASTA / "js" / "telas" / f"{n}.js").exists(), n


def _sem_comentarios(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


@pytest.mark.parametrize("nome", ["base.css", "componentes.css", "catalogo.css", "telas.css"])
def test_regra_dura_css_so_usa_tokens(nome):
    """Fora do tokens.css: nenhuma cor literal, nenhum tamanho além da linha fina de 1 px, nenhuma duração."""
    css = _sem_comentarios((PASTA / nome).read_text(encoding="utf-8"))
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", css), "cor em hexadecimal"
    assert not re.findall(r"\brgba?\(|\bhsla?\(", css), "cor em rgb/hsl"
    px = [v for v in re.findall(r"-?\d*\.?\d+px", css) if v not in ("1px", "-1px")]
    assert not px, f"tamanho fora dos tokens: {sorted(set(px))}"
    reduzido = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{.*?\}\s*\}", css, flags=re.S)
    sem_reduzido = css.replace(reduzido.group(0), "") if reduzido else css
    assert not re.findall(r"\b\d+m?s\b", sem_reduzido), "duração fora dos tokens"


def test_js_nao_tem_cor_literal():
    for js in PASTA.rglob("*.js"):
        assert not re.findall(r"['\"`]#[0-9a-fA-F]{3,8}['\"`]", js.read_text(encoding="utf-8")), js.name


def test_foco_visivel_sempre_definido():
    base = (PASTA / "base.css").read_text(encoding="utf-8")
    assert re.search(r":focus-visible\s*\{\s*outline:\s*var\(--borda-sel\) solid var\(--foco\)", base)
    for nome in ("componentes.css", "catalogo.css", "telas.css"):
        for regra in re.findall(r"([^{}]+)\{([^}]*outline:\s*none[^}]*)\}", (PASTA / nome).read_text(encoding="utf-8")):
            seletor, corpo = regra
            # tirar o contorno só vale se a regra põe outro sinal de foco no lugar
            assert "box-shadow" in corpo or "background" in corpo, seletor.strip()


def test_tokens_tem_tema_escuro_e_reducao_de_movimento():
    tokens = (PASTA / "tokens.css").read_text(encoding="utf-8")
    assert ':root[data-tema="escuro"]' in tokens
    assert "prefers-reduced-motion" in (PASTA / "base.css").read_text(encoding="utf-8")
    # nada abaixo de 14 px na escala de texto (direção da Etapa 2)
    tamanhos = [int(v) for v in re.findall(r"--t-\d:\s*(\d+)px", tokens)]
    assert tamanhos and min(tamanhos) >= 14


def test_textos_sem_emoji():
    emoji = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2728]")
    for arq in [PASTA / "textos.js", PASTA / "index.html", PASTA / "catalogo.html"]:
        assert not emoji.findall(arq.read_text(encoding="utf-8")), arq.name


def test_painel_e_inspecoes_tem_tela_propria_e_laudo_compartilhado():
    """Etapa 5a: Painel e Inspeções saíram da tela provisória; o diálogo do laudo é um só (Análise e Inspeções)."""
    rotas = (PASTA / "js" / "rotas.js").read_text(encoding="utf-8")
    for tela in ("painel", "inspecoes"):
        assert re.search(rf'{tela}: \{{[^}}]*modulo: "{tela}"', rotas), tela
    for usuario in ("js/analise/cabecalho.js", "js/telas/inspecoes.js"):
        assert 'from "../laudo.js"' in (PASTA / usuario).read_text(encoding="utf-8"), usuario
    assert "laudo.pdf" not in (PASTA / "js" / "analise" / "cabecalho.js").read_text(encoding="utf-8")



def test_equipamentos_e_pendencias_tem_tela_propria_e_formulario_compartilhado():
    """Etapa 5b: Equipamentos (lista e detalhe) e Pendências saíram da tela provisória; o formulário da
    pendência é um só (Análise e Pendências) e a busca das listas é o mesmo componente."""
    rotas = (PASTA / "js" / "rotas.js").read_text(encoding="utf-8")
    assert re.search(r'equipamentos: \{[^}]*modulo: "equipamentos"[^}]*detalhe: "equipamento"', rotas)
    assert re.search(r'pendencias: \{[^}]*modulo: "pendencias"', rotas)
    for usuario in ("js/analise/painel.js", "js/telas/pendencias.js"):
        assert 'from "../pendencia.js"' in (PASTA / usuario).read_text(encoding="utf-8"), usuario
    assert "/acompanhamento" not in (PASTA / "js" / "analise" / "painel.js").read_text(encoding="utf-8")
    for tela in ("inspecoes", "equipamentos", "pendencias"):
        assert "campoBusca(" in (PASTA / "js" / "telas" / f"{tela}.js").read_text(encoding="utf-8"), tela
