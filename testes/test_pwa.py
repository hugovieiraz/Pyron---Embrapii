"""Tablet (0.9, F2): aplicativo instalável (manifest, ícones, service worker) e a porta reservada ao proxy HTTPS."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from PIL import Image

from app import acesso

RAIZ = Path(__file__).resolve().parents[1]
INTERFACE = RAIZ / "app" / "interface"
MARCA = RAIZ / "app" / "estatico" / "marca"
SENHA = "senha-de-teste-1"


def _token(nome: str) -> str:
    """Valor de um token do tema claro (o primeiro :root de tokens.css), seguindo var(--outro)."""
    tokens = (INTERFACE / "tokens.css").read_text(encoding="utf-8")
    claro = tokens[: tokens.index(':root[data-tema="escuro"]')]
    valor = re.search(rf"--{nome}:\s*([^;]+);", claro).group(1).strip()
    referencia = re.fullmatch(r"var\(--([a-z0-9-]+)\)", valor)
    return _token(referencia.group(1)) if referencia else valor


def _manifest() -> dict:
    return json.loads((INTERFACE / "manifest.webmanifest").read_text(encoding="utf-8"))


def test_manifest_com_cores_dos_tokens_e_icones_gerados() -> None:
    m = _manifest()
    assert m["name"] == m["short_name"] == "Pyron"
    assert m["display"] == "standalone" and m["start_url"] == "/#painel" and m["scope"] == "/"
    assert m["theme_color"].upper() == _token("superficie").upper()  # o topo
    assert m["background_color"].upper() == _token("fundo-trabalho").upper()  # a área de trabalho
    propositos = {i["purpose"] for i in m["icons"]}
    assert propositos == {"any", "maskable"}
    for icone in m["icons"]:
        arquivo = MARCA / Path(icone["src"]).name
        lado = int(icone["sizes"].split("x")[0])
        with Image.open(arquivo) as im:
            assert im.size == (lado, lado), arquivo.name
    tamanhos = {i["sizes"] for i in m["icons"] if i["purpose"] == "any"}
    assert {"192x192", "512x512"} <= tamanhos
    with Image.open(MARCA / "icone-app-180.png") as im:  # iPad: apple-touch-icon sem transparência
        assert im.size == (180, 180) and im.mode == "RGB"


def test_icones_do_aplicativo_saem_do_gerador_da_marca() -> None:
    gerador = (RAIZ / "marca" / "gerar_marca.py").read_text(encoding="utf-8")
    for trecho in ('f"icone-app-{lado}.png"', '"icone-app-mascara-512.png"', '"icone-app-180.png"', "def gerar_pwa"):
        assert trecho in gerador, trecho


def _casca_do_sw() -> list[str]:
    sw = (INTERFACE / "sw.js").read_text(encoding="utf-8")
    bloco = re.search(r"const CASCA = \[(.*?)\];", sw, flags=re.S).group(1)
    return re.findall(r'"([^"]+)"', bloco)


def test_service_worker_nunca_guarda_api_nem_pdf() -> None:
    sw = (INTERFACE / "sw.js").read_text(encoding="utf-8")
    casca = _casca_do_sw()
    assert not [u for u in casca if u.startswith("/api") or u.lower().endswith(".pdf")]
    regra = re.search(r"function nuncaGuardar\(url\) \{(.*?)\n\}", sw, flags=re.S).group(1)
    for trecho in ('"/api/"', '".pdf"', '"/antiga"'):
        assert trecho in regra, trecho
    # o fetch confere a regra antes de qualquer resposta guardada e só responde para a casca ou navegação
    fetch = sw[sw.index('addEventListener("fetch"'):]
    assert fetch.index("nuncaGuardar(url)") < fetch.index("respondWith")
    assert 'pedido.method !== "GET"' in fetch
    assert "VERSAO" in sw and "PREFIXO" in sw  # cache com a versão no nome


def test_service_worker_tem_toda_a_casca() -> None:
    """Módulo novo da interface fora da lista: sem rede, a tela não abriria. Este teste lembra de pôr."""
    casca = set(_casca_do_sw())
    modulos = {"/" + p.relative_to(INTERFACE).as_posix() for p in (INTERFACE / "js").rglob("*.js") if p.name != "catalogo.js"}
    estilos = {f"/{p.name}" for p in INTERFACE.glob("*.css") if p.name != "catalogo.css"}
    faltam = (modulos | estilos | {"/textos.js", "/", "/manifest.webmanifest"}) - casca
    assert not faltam, f"faltam na casca do sw.js: {sorted(faltam)}"
    for u in casca:
        if u.startswith("/marca/"):
            assert (MARCA / Path(u).name).exists(), u
        elif u not in ("/",):
            assert (INTERFACE / u.lstrip("/")).exists(), u


def test_modo_local_nao_registra_aplicativo() -> None:
    """O manifest e o service worker só entram no modo servidor (o Pyron.exe segue como antes)."""
    index = (INTERFACE / "index.html").read_text(encoding="utf-8")
    assert "manifest" not in index and "serviceWorker" not in index
    casca = (INTERFACE / "js" / "casca.js").read_text(encoding="utf-8")
    assert re.search(r"if \(modoServidor\(\)\) import\(\"\./aplicativo\.js\"\)", casca)


@pytest.fixture()
def cliente_servidor(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    pasta = tmp_path / "dados_app"
    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(pasta))
    monkeypatch.setattr(servidor, "PASTA_DADOS", pasta)
    acesso.criar_usuario(pasta, "ana", "Ana Lima", SENHA, "engenheiro", True, "CREA-PB 1", True)
    yield servidor
    acesso.configurar("local")


def test_casca_e_manifest_publicos_no_modo_servidor(cliente_servidor) -> None:
    from fastapi.testclient import TestClient

    acesso.configurar("servidor")
    c = TestClient(cliente_servidor.app, base_url="https://pyron.teste", client=("10.0.0.7", 5000))
    r = c.get("/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
    r = c.get(f"/sw.js?v={cliente_servidor.VERSAO}")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert r.headers["cache-control"] == "no-cache"  # versão nova do sw.js entra sem esperar cache
    assert c.get("/marca/icone-app-mascara-512.png").status_code == 200
    assert c.get("/api/analises").status_code == 401


# ---------------------------------------------------------------- porta reservada ao proxy (tailscale serve)

def _pela_porta_do_proxy(servidor, **kw):
    """Como o tailscale serve entrega: de 127.0.0.1, com Host 127.0.0.1:<porta>, sem X-Forwarded-*."""
    from fastapi.testclient import TestClient

    return TestClient(servidor.app, base_url="http://127.0.0.1:8798", client=("127.0.0.1", 50000), **kw)


def test_porta_do_proxy_e_sempre_de_fora_e_https(cliente_servidor) -> None:
    acesso.configurar("servidor", porta_proxy=8798)
    c = _pela_porta_do_proxy(cliente_servidor)
    r = c.post("/api/acesso/entrar", json={"usuario": "ana", "senha": SENHA},
               headers={"Tailscale-User-Login": "ana@exemplo.com", "Origin": "https://pyron.tail1234.ts.net",
                        "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200 and "secure" in r.headers["set-cookie"].lower()  # o tablet fala HTTPS com o proxy
    cookie = {"Cookie": f"{acesso.COOKIE}={r.cookies[acesso.COOKIE]}"}
    # mesmo vindo de 127.0.0.1 e sem X-Forwarded-For, não é "este computador"
    assert c.post("/api/encerrar", headers={**cookie, "Origin": "https://pyron.tail1234.ts.net", "Sec-Fetch-Site": "same-origin"}).status_code == 403
    assert c.get("/api/analises", headers=cookie).status_code == 200
    # outro site, pela mesma porta: recusado
    assert c.post("/api/acesso/sair", headers={**cookie, "Origin": "https://malicioso.exemplo", "Sec-Fetch-Site": "cross-site"}).status_code == 403
    # Origin de outro endereço sem Sec-Fetch-Site (navegador antigo ou script): recusado
    assert c.post("/api/acesso/sair", headers={**cookie, "Origin": "https://malicioso.exemplo"}).status_code == 403


def test_porta_principal_continua_local(cliente_servidor) -> None:
    from fastapi.testclient import TestClient

    acesso.configurar("servidor", porta_proxy=8798)
    c = TestClient(cliente_servidor.app, base_url="http://127.0.0.1:8795", client=("127.0.0.1", 50000))
    assert c.post("/api/acesso/entrar", json={"usuario": "ana", "senha": SENHA}).status_code == 200
    assert c.post("/api/encerrar").status_code == 200
    cliente_servidor.sinais["encerrar"] = False


def test_origem_publica_configurada_e_tentativas_por_login_do_tailscale(cliente_servidor) -> None:
    acesso.configurar("servidor", porta_proxy=8798, origens=["https://pyron.tail1234.ts.net"])
    c = _pela_porta_do_proxy(cliente_servidor)
    r = c.post("/api/acesso/entrar", json={"usuario": "ana", "senha": SENHA}, headers={"Origin": "https://pyron.tail1234.ts.net"})
    assert r.status_code == 200
    # sem X-Forwarded-For, as tentativas contam por login do Tailscale: um tablet não bloqueia os outros
    for _ in range(acesso.TENTATIVAS_POR_USUARIO):
        c.post("/api/acesso/entrar", json={"usuario": "ana", "senha": "errada-123456"}, headers={"Tailscale-User-Login": "a@x.com"})
    assert c.post("/api/acesso/entrar", json={"usuario": "ana", "senha": SENHA}, headers={"Tailscale-User-Login": "a@x.com"}).status_code == 429
    assert c.post("/api/acesso/entrar", json={"usuario": "ana", "senha": SENHA}, headers={"Tailscale-User-Login": "b@x.com"}).status_code == 200


def test_iniciar_recusa_porta_do_proxy_no_modo_local() -> None:
    from argparse import Namespace

    from app.iniciar import conferir_argumentos

    base = dict(modo="local", host="127.0.0.1", proxy=[], auto_encerrar=False, janela=False, sem_navegador=False, porta_proxy=8798, origem=[])
    with pytest.raises(ValueError, match="porta-proxy"):
        conferir_argumentos(Namespace(**base))
