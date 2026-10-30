"""Modo servidor e controle de acesso (0.9, F1): classificação das rotas, login, perfis, proxy e auditoria.

O modo local continua sem login: os testes antigos do servidor rodam sem nenhuma mudança e provam isso.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.websockets import WebSocketDisconnect

from app import acesso

SENHA = "senha-de-teste-1"
REMOTO = ("10.0.0.7", 50000)
LOCAL = ("127.0.0.1", 50000)


# ---------------------------------------------------------------- classificação


def _rotas(app) -> list[str]:
    saida = []
    for r in app.routes:
        if isinstance(r, APIWebSocketRoute):
            saida.append(f"WS {r.path}")
        elif isinstance(r, APIRoute):
            saida.extend(f"{m} {r.path}" for m in sorted(r.methods - {"HEAD"}))
    return saida


def test_toda_rota_tem_classificacao_de_acesso() -> None:
    """Rota nova sem grupo em app/acesso.py faz este teste falhar (e no modo servidor responderia 403)."""
    from app import servidor

    rotas = _rotas(servidor.app)
    sem_grupo = [r for r in rotas if r not in acesso.CLASSIFICACAO]
    assert not sem_grupo, f"rotas sem classificação de acesso em app/acesso.py: {sem_grupo}"
    sobrando = [r for r in acesso.CLASSIFICACAO if r not in rotas]
    assert not sobrando, f"classificação de rotas que não existem mais: {sobrando}"
    assert set(acesso.CLASSIFICACAO.values()) <= set(acesso.GRUPOS)


# ---------------------------------------------------------------- senha e perfis


def test_senha_scrypt_com_sal_e_sem_texto_guardado() -> None:
    a, b = acesso.gerar_hash(SENHA), acesso.gerar_hash(SENHA)
    assert a != b and SENHA not in a and a.startswith("scrypt$")
    assert acesso.conferir_senha(SENHA, a) and not acesso.conferir_senha("outra-senha-1", a)
    assert not acesso.conferir_senha(SENHA, None) and not acesso.conferir_senha(SENHA, "lixo")


def test_permissoes_por_perfil() -> None:
    tecnico = {"perfil": "tecnico", "assina": False}
    eng = {"perfil": "engenheiro", "assina": False}
    assina = {"perfil": "engenheiro", "assina": True, "registro": "CREA-PB 1"}
    assert acesso.permissoes(tecnico) == {"leitura", "envio"}
    assert acesso.permissoes(eng) == {"leitura", "envio", "revisao"}
    assert acesso.permissoes(assina) == {"leitura", "envio", "revisao", "laudo"}
    assert "laudo" not in acesso.permissoes({**assina, "registro": ""})  # sem registro não assina
    assert "administracao" in acesso.permissoes({**tecnico, "administrador": True})
    assert acesso.permissoes(None) == set(acesso.PERMISSOES)  # modo local


def test_conta_mantem_senha_quando_a_tela_nao_manda_outra() -> None:
    primeira = acesso.conta({"usuario": "Ana", "senha": SENHA}, None, "Ana")
    assert primeira["usuario"] == "ana" and acesso.conferir_senha(SENHA, primeira["senha_hash"])
    assert acesso.conta({"usuario": "ana"}, primeira, "Ana")["senha_hash"] == primeira["senha_hash"]
    assert acesso.conta({"usuario": ""}, primeira, "Ana")["senha_hash"] == ""  # sem usuário ninguém entra
    with pytest.raises(ValueError, match="pelo menos"):
        acesso.conta({"usuario": "ana", "senha": "curta"}, None, "Ana")
    with pytest.raises(ValueError, match="usuário"):
        acesso.conta({"usuario": "a b", "senha": SENHA}, None, "Ana")
    with pytest.raises(ValueError, match="antes da senha"):
        acesso.conta({"senha": SENHA}, None, "Ana")


# ---------------------------------------------------------------- servidor no modo servidor


@pytest.fixture()
def servidor_rede(tmp_path, monkeypatch):
    """O app no modo servidor, com um time de quatro: administrador que assina, engenheiro, técnico e um sem senha."""
    from app import servidor
    from app.armazenamento import Armazenamento

    pasta = tmp_path / "dados_app"
    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(pasta))
    monkeypatch.setattr(servidor, "PASTA_DADOS", pasta)
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    acesso.criar_usuario(pasta, "ana", "Ana Lima", SENHA, "engenheiro", True, "CREA-PB 111", True)
    acesso.criar_usuario(pasta, "bruno", "Bruno Reis", SENHA, "engenheiro")
    acesso.criar_usuario(pasta, "caio", "Caio Dias", SENHA, "tecnico")
    cfg = json.loads((pasta / "config.json").read_text(encoding="utf-8"))
    cfg["responsaveis"].append({"id": "semsenha", "nome": "Dora", "perfil": "tecnico", "registro": "", "assina": False,
                                "telefone": "+55 83 99999-0000", "email": "dora@exemplo.com", "alertas": None})
    for r in cfg["responsaveis"]:
        r["telefone"], r["email"] = r.get("telefone") or "+55 83 98888-0000", r.get("email") or f"{r['nome'][:3].lower()}@exemplo.com"
    (pasta / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    acesso.configurar("servidor")
    yield servidor, pasta
    acesso.configurar("local")


def _cliente(servidor, quem: str | None = None, endereco=REMOTO, https=True):
    from fastapi.testclient import TestClient

    c = TestClient(servidor.app, base_url="https://pyron.teste" if https else "http://pyron.teste", client=endereco)
    if quem:
        r = c.post("/api/acesso/entrar", json={"usuario": quem, "senha": SENHA})
        assert r.status_code == 200, r.text
    return c


def _caminho(rota: str) -> str:
    return re.sub(r"\{[^}]+\}", "x1", rota)


def test_sem_sessao_toda_api_responde_401_menos_entrar_e_saude(servidor_rede) -> None:
    servidor, _ = servidor_rede
    c = _cliente(servidor)
    for rota, grupo in acesso.CLASSIFICACAO.items():
        metodo, caminho = rota.split(" ", 1)
        if metodo == "WS" or not caminho.startswith("/api/"):
            continue
        r = c.request(metodo, _caminho(caminho))
        if grupo == "publico":
            assert r.status_code not in (401, 403), rota
        elif grupo == "so_local":
            assert r.status_code == 403, rota  # de fora, nem chega a pedir login
        else:
            assert r.status_code == 401, f"{rota}: {r.status_code}"
    assert c.get("/api/saude").json()["ok"] is True
    eu = c.get("/api/acesso/eu").json()
    assert eu["modo"] == "servidor" and eu["usuario"] is None


def test_websocket_sem_sessao_e_recusado(servidor_rede) -> None:
    servidor, _ = servidor_rede
    with pytest.raises(WebSocketDisconnect):
        with _cliente(servidor).websocket_connect("/api/celular/ws") as ws:
            ws.receive_bytes()


def test_entrar_cookie_seguro_e_sair(servidor_rede) -> None:
    servidor, _ = servidor_rede
    c = _cliente(servidor)
    assert c.post("/api/acesso/entrar", json={"usuario": "ana", "senha": "errada-123456"}).status_code == 401
    r = c.post("/api/acesso/entrar", json={"usuario": "ANA", "senha": SENHA})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "secure" in cookie
    assert r.json()["usuario"]["nome"] == "Ana Lima" and "senha_hash" not in r.json()["usuario"]
    assert c.get("/api/analises").status_code == 200
    assert c.post("/api/acesso/sair").status_code == 200
    assert c.get("/api/analises").status_code == 401


def test_quem_nao_tem_senha_nao_entra_e_http_de_fora_e_recusado(servidor_rede) -> None:
    servidor, _ = servidor_rede
    c = _cliente(servidor)
    assert c.post("/api/acesso/entrar", json={"usuario": "", "senha": SENHA}).status_code == 401
    http_de_fora = _cliente(servidor, https=False)
    r = http_de_fora.post("/api/acesso/entrar", json={"usuario": "ana", "senha": SENHA})
    assert r.status_code == 400 and "HTTPS" in r.json()["erro"]
    local = _cliente(servidor, endereco=LOCAL, https=False)  # no próprio computador, HTTP serve (cookie sem Secure)
    r = local.post("/api/acesso/entrar", json={"usuario": "ana", "senha": SENHA})
    assert r.status_code == 200 and "secure" not in r.headers["set-cookie"].lower()


def test_tentativas_erradas_bloqueiam(servidor_rede) -> None:
    servidor, _ = servidor_rede
    c = _cliente(servidor)
    for _ in range(acesso.TENTATIVAS_POR_USUARIO):
        assert c.post("/api/acesso/entrar", json={"usuario": "ana", "senha": "errada-123456"}).status_code == 401
    r = c.post("/api/acesso/entrar", json={"usuario": "ana", "senha": SENHA})
    assert r.status_code == 429  # nem a senha certa passa durante o bloqueio
    outro = _cliente(servidor, endereco=("10.0.0.8", 50000))
    assert outro.post("/api/acesso/entrar", json={"usuario": "ana", "senha": SENHA}).status_code == 200


def test_pedido_de_outro_site_e_recusado(servidor_rede) -> None:
    servidor, _ = servidor_rede
    c = _cliente(servidor, "ana")
    assert c.post("/api/analises/x1/comentarios", json={"texto": "oi"}, headers={"Origin": "https://malicioso.exemplo"}).status_code == 403
    assert c.post("/api/acesso/sair", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert c.post("/api/analises/x1/comentarios", json={"texto": "oi"}, headers={"Origin": "https://pyron.teste"}).status_code == 404


def test_tecnico_nao_emite_laudo_nem_revisa_nem_administra(servidor_rede) -> None:
    servidor, _ = servidor_rede
    c = _cliente(servidor, "caio")
    for metodo, caminho in (("POST", "/api/laudos"), ("GET", "/api/analises/x1/laudo.pdf"), ("DELETE", "/api/analises/x1"),
                            ("PUT", "/api/analises/x1"), ("PUT", "/api/configuracoes"), ("GET", "/api/backup.zip")):
        r = c.request(metodo, caminho, json={} if metodo in ("POST", "PUT") else None)
        assert r.status_code == 403, f"{metodo} {caminho}: {r.status_code}"
    assert c.get("/api/analises").status_code == 200
    bruno = _cliente(servidor, "bruno")  # engenheiro sem assinatura: revisa, mas não emite laudo
    assert bruno.post("/api/laudos", json={"ids": ["x1"]}).status_code == 403
    assert bruno.delete("/api/analises/x1").status_code == 404  # passou do acesso; a inspeção é que não existe


def test_rota_so_local_responde_403_de_fora_mesmo_para_administrador(servidor_rede) -> None:
    servidor, _ = servidor_rede
    de_fora = _cliente(servidor, "ana")
    assert de_fora.post("/api/encerrar").status_code == 403
    assert de_fora.post("/api/backup/restaurar").status_code == 403
    aqui = _cliente(servidor, "ana", endereco=LOCAL)
    assert aqui.post("/api/encerrar").status_code == 200
    servidor.sinais["encerrar"] = False
    assert aqui.post("/api/sinal").status_code == 404  # o modo servidor não se desliga sozinho
    tecnico_aqui = _cliente(servidor, "caio", endereco=LOCAL)
    assert tecnico_aqui.post("/api/encerrar").status_code == 403


def test_cabecalhos_de_proxy_so_valem_do_proxy_configurado(servidor_rede) -> None:
    servidor, _ = servidor_rede
    # Caddy no mesmo computador, mas sem --proxy: o pedido tem X-Forwarded-For e não conta como local
    c = _cliente(servidor, endereco=LOCAL, https=False)
    r = c.post("/api/acesso/entrar", json={"usuario": "ana", "senha": SENHA},
               headers={"X-Forwarded-For": "10.0.0.9", "X-Forwarded-Proto": "https"})
    assert r.status_code == 400  # não acredita no "https" de quem não é o proxy
    acesso.configurar("servidor", ["127.0.0.1"])
    r = c.post("/api/acesso/entrar", json={"usuario": "ana", "senha": SENHA},
               headers={"X-Forwarded-For": "10.0.0.9", "X-Forwarded-Proto": "https", "X-Forwarded-Host": "pyron.empresa"})
    assert r.status_code == 200 and "secure" in r.headers["set-cookie"].lower()
    # o navegador guarda o cookie Secure (ele fala HTTPS com o Caddy); entre o Caddy e o Pyron é HTTP
    cookie = {"Cookie": f"{acesso.COOKIE}={r.cookies[acesso.COOKIE]}"}
    pelo_proxy = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "pyron.empresa", "Origin": "https://pyron.empresa", **cookie}
    # pelo proxy, de fora: rota só local continua fechada; o próprio computador pelo proxy passa
    assert c.post("/api/encerrar", headers={"X-Forwarded-For": "10.0.0.9", **pelo_proxy}).status_code == 403
    assert c.post("/api/encerrar", headers={"X-Forwarded-For": "127.0.0.1", **pelo_proxy}).status_code == 200
    servidor.sinais["encerrar"] = False


def test_sessao_vence_sem_uso(servidor_rede) -> None:
    servidor, _ = servidor_rede
    c = _cliente(servidor, "ana")
    with servidor.armazenamento._conexao() as con:
        velho = (datetime.now() - acesso.INATIVIDADE - timedelta(minutes=1)).isoformat(timespec="seconds")
        con.execute("UPDATE sessoes SET usada_em = ?", (velho,))
    assert c.get("/api/analises").status_code == 401


def test_configuracoes_sem_senha_e_sem_contato_para_quem_nao_administra(servidor_rede) -> None:
    servidor, _ = servidor_rede
    tecnico = _cliente(servidor, "caio").get("/api/configuracoes").json()
    assert all("senha_hash" not in r and "telefone" not in r and "email" not in r for r in tecnico["responsaveis"])
    assert tecnico["pasta_dados"] == "" and tecnico["modo"] == "servidor"
    admin = _cliente(servidor, "ana").get("/api/configuracoes").json()
    assert all("senha_hash" not in r for r in admin["responsaveis"])
    assert all(r["telefone"] for r in admin["responsaveis"]) and admin["pasta_dados"]
    assert {r["nome"]: r["tem_senha"] for r in admin["responsaveis"]}["Dora"] is False


def test_time_salvo_pela_tela_mantem_senhas_e_exige_administrador(servidor_rede) -> None:
    servidor, _ = servidor_rede
    ana = _cliente(servidor, "ana")
    caio = _cliente(servidor, "caio")
    time_ = ana.get("/api/configuracoes").json()["responsaveis"]
    r = ana.put("/api/configuracoes", json={"responsaveis": time_})
    assert r.status_code == 200, r.text
    assert caio.get("/api/analises").status_code == 200  # salvar sem trocar senha não derruba ninguém
    sem_admin = [{**m, "administrador": False} for m in time_]
    assert ana.put("/api/configuracoes", json={"responsaveis": sem_admin}).status_code == 422
    nova = [{**m, "senha": "senha-nova-do-caio"} if m["usuario"] == "caio" else m for m in time_]
    assert ana.put("/api/configuracoes", json={"responsaveis": nova}).status_code == 200
    assert caio.get("/api/analises").status_code == 401  # senha trocada: a sessão antiga cai
    assert ana.get("/api/analises").status_code == 200
    sem_caio = [m for m in time_ if m["usuario"] != "caio"]
    caio2 = _cliente(servidor)
    assert caio2.post("/api/acesso/entrar", json={"usuario": "caio", "senha": "senha-nova-do-caio"}).status_code == 200
    assert ana.put("/api/configuracoes", json={"responsaveis": sem_caio}).status_code == 200
    assert caio2.get("/api/analises").status_code == 401  # saiu do time: sessão encerrada
    grande = time_ + [{"nome": f"P{i}", "perfil": "tecnico", "assina": False} for i in range(acesso.LIMITE_TIME)]
    assert ana.put("/api/configuracoes", json={"responsaveis": grande}).status_code == 422


def test_trocar_a_propria_senha(servidor_rede) -> None:
    servidor, _ = servidor_rede
    a1, a2 = _cliente(servidor, "bruno"), _cliente(servidor, "bruno")
    assert a1.post("/api/acesso/senha", json={"atual": "errada-123456", "nova": "outra-senha-boa"}).status_code == 422
    assert a1.post("/api/acesso/senha", json={"atual": SENHA, "nova": "curta"}).status_code == 422
    assert a1.post("/api/acesso/senha", json={"atual": SENHA, "nova": "outra-senha-boa"}).status_code == 200
    assert a1.get("/api/analises").status_code == 200  # esta sessão continua
    assert a2.get("/api/analises").status_code == 401  # as outras caem


def test_interface_antiga_e_celular_fora_do_modo_servidor(servidor_rede) -> None:
    servidor, _ = servidor_rede
    c = _cliente(servidor, "ana")
    r = c.get("/antiga/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/"
    assert c.post("/api/celular/ligar").status_code == 409


def test_servidor_nao_sobe_sem_administrador_com_senha(servidor_rede) -> None:
    from fastapi.testclient import TestClient

    servidor, pasta = servidor_rede
    cfg = json.loads((pasta / "config.json").read_text(encoding="utf-8"))
    for r in cfg["responsaveis"]:
        r["administrador"] = False
    (pasta / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    with pytest.raises(RuntimeError, match="administrador"):
        with TestClient(servidor.app):
            pass


# ---------------------------------------------------------------- comportamento com inspeção de verdade


def _nova_inspecao(c) -> dict:
    from testes.test_servidor import _termograma_flir

    r = c.post("/api/analises", files={"arquivo": ("teste.jpg", _termograma_flir(), "image/jpeg")},
               headers={"Origin": "https://pyron.teste"})
    assert r.status_code == 200, r.text
    return r.json()


def test_laudo_assinado_por_quem_entrou_com_auditoria(servidor_rede) -> None:
    servidor, _ = servidor_rede
    ana = _cliente(servidor, "ana")
    a = _nova_inspecao(_cliente(servidor, "caio"))  # o técnico envia a imagem
    outro = next(r["id"] for r in ana.get("/api/configuracoes").json()["responsaveis"] if r["nome"] == "Bruno Reis")
    pdf = ana.get(f"/api/analises/{a['id']}/laudo.pdf?responsavel={outro}")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    emitidos = ana.get("/api/laudos/emitidos").json()
    assert len(emitidos) == 1
    e = emitidos[0]
    assert e["emitido_por_nome"] == "Ana Lima" and e["responsavel_nome"] == "Ana Lima"  # nunca o escolhido na tela
    assert e["responsavel_registro"] == "CREA-PB 111" and e["analises"] == [a["id"]]
    import hashlib
    assert e["sha256"] == hashlib.sha256(pdf.content).hexdigest()


def test_comentarios_com_autor_e_data(servidor_rede) -> None:
    servidor, _ = servidor_rede
    caio = _cliente(servidor, "caio")
    a = _nova_inspecao(caio)
    texto = "Conexão com aperto suspeito; conferir na próxima parada. <b>#$@\\"
    r = caio.post(f"/api/analises/{a['id']}/comentarios", json={"texto": texto, "regiao_id": a["regioes"][0]["id"]})
    assert r.status_code == 200, r.text
    lista = _cliente(servidor, "ana").get(f"/api/analises/{a['id']}/comentarios").json()
    assert len(lista) == 1 and lista[0]["autor_nome"] == "Caio Dias" and lista[0]["texto"] == texto
    assert datetime.fromisoformat(lista[0]["criado_em"])
    assert caio.post(f"/api/analises/{a['id']}/comentarios", json={"texto": "  "}).status_code == 422
    assert caio.post(f"/api/analises/{a['id']}/comentarios", json={"texto": "x", "regiao_id": "nao-existe"}).status_code == 422


def test_edicao_concorrente_recusada_com_409(servidor_rede) -> None:
    servidor, _ = servidor_rede
    ana, bruno = _cliente(servidor, "ana"), _cliente(servidor, "bruno")
    a = _nova_inspecao(ana)
    rev = a.get("revisao", 0)
    r = ana.put(f"/api/analises/{a['id']}", json={"revisao": rev, "condicoes": {"ambiente_c": "25", "carga_pct": ""}})
    assert r.status_code == 200 and r.json()["revisao"] == rev + 1
    r = bruno.put(f"/api/analises/{a['id']}", json={"revisao": rev, "condicoes": {"ambiente_c": "30", "carga_pct": ""}})
    assert r.status_code == 409
    assert ana.get(f"/api/analises/{a['id']}").json()["condicoes"]["ambiente_c"] == 25.0


def test_tecnico_muda_pendencia_menos_urgente_e_imediata(servidor_rede) -> None:
    servidor, _ = servidor_rede
    caio = _cliente(servidor, "caio")
    a = _nova_inspecao(caio)
    for severidade, pode_mudar in (("programar", True), ("urgente", False), ("imediato", False)):
        guardada = servidor.armazenamento.obter(a["id"])
        guardada["resumo"]["severidade"] = severidade
        guardada.pop("acompanhamento", None)
        servidor.armazenamento.salvar(guardada)
        r = caio.put(f"/api/analises/{a['id']}/acompanhamento", json={"status": "programada", "ordem_servico": "OS-1", "nota": ""})
        assert (r.status_code == 200) is pode_mudar, f"{severidade}: {r.status_code}"
        so_nota = caio.put(f"/api/analises/{a['id']}/acompanhamento", json={"status": "programada" if pode_mudar else "aberta",
                                                                              "ordem_servico": "OS-1" if pode_mudar else "",
                                                                              "nota": "Equipe avisada."})
        assert so_nota.status_code == 200, so_nota.text
        assert so_nota.json()["historico"][-1]["autor"] == "Caio Dias"
    bruno = _cliente(servidor, "bruno")
    assert bruno.put(f"/api/analises/{a['id']}/acompanhamento", json={"status": "programada"}).status_code == 200
    with servidor.armazenamento._conexao() as con:
        autores = {linha[0] for linha in con.execute("SELECT autor FROM historico_pendencias")}
    assert {"Caio Dias", "Bruno Reis"} <= autores


# ---------------------------------------------------------------- modo local continua igual


def test_modo_local_sem_login(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "d"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "d")
    acesso.configurar("local")
    c = TestClient(servidor.app)
    assert c.get("/api/acesso/eu").json() == {"modo": "local", "usuario": None, "permissoes": sorted(acesso.PERMISSOES)}
    assert c.get("/api/analises").status_code == 200
    assert c.post("/api/sinal?cliente=t").status_code == 200
    assert c.post("/api/acesso/entrar", json={"usuario": "x", "senha": "y"}).status_code == 409
    assert c.get("/api/configuracoes").json()["modo"] == "local"


# ---------------------------------------------------------------- linha de comando e argumentos


def test_linha_de_comando_cria_conta_e_confere(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("PYRON_SENHA", SENHA)
    assert acesso.main(["conferir", "--dados", str(tmp_path)]) == 1
    assert acesso.main(["usuario", "--usuario", "ana", "--nome", "Ana", "--admin", "--dados", str(tmp_path)]) == 0
    assert acesso.main(["conferir", "--dados", str(tmp_path)]) == 0
    assert acesso.main(["usuario", "--usuario", "ana", "--dados", str(tmp_path)]) == 0  # troca a senha sem tirar o administrador
    cfg = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert cfg["responsaveis"][0]["administrador"] is True and SENHA not in json.dumps(cfg)
    assert acesso.main(["usuario", "--usuario", "x y", "--dados", str(tmp_path)]) == 2


def test_argumentos_do_iniciar() -> None:
    from argparse import Namespace

    from app.iniciar import conferir_argumentos

    base = dict(modo="local", host="127.0.0.1", proxy=[], auto_encerrar=False, janela=False, sem_navegador=False)
    assert conferir_argumentos(Namespace(**base)) == []
    with pytest.raises(ValueError, match="modo servidor"):
        conferir_argumentos(Namespace(**{**base, "host": "0.0.0.0"}))
    with pytest.raises(ValueError, match="proxy"):
        conferir_argumentos(Namespace(**{**base, "proxy": ["127.0.0.1"]}))
    args = Namespace(**{**base, "modo": "servidor", "host": "0.0.0.0", "auto_encerrar": True})
    avisos = conferir_argumentos(args)
    assert avisos and args.auto_encerrar is False and args.sem_navegador is True


def test_backup_pela_linha_de_comando_sem_sessoes(tmp_path) -> None:
    """O backup agendado do servidor não depende de login e não leva as sessões abertas."""
    import sqlite3
    import zipfile
    from datetime import datetime as dt

    from app import backup
    from app.armazenamento import Armazenamento

    arm = Armazenamento(tmp_path / "dados")
    arm.criar_sessao("abc", "m1", dt.now(), dt.now() + timedelta(days=1))
    assert backup.main(["--dados", str(tmp_path / "dados"), "--saida", str(tmp_path / "copias"), "--manter", "1"]) == 0
    assert backup.main(["--dados", str(tmp_path / "dados"), "--saida", str(tmp_path / "copias"), "--manter", "1"]) == 0
    zips = list((tmp_path / "copias").glob("pyron_backup_*.zip"))
    assert len(zips) == 1  # guarda só os N últimos
    with zipfile.ZipFile(zips[0]) as z:
        assert not any(n.endswith(("-wal", "-shm")) for n in z.namelist())
        z.extract("inspecoes.sqlite", tmp_path / "aberto")
    con = sqlite3.connect(tmp_path / "aberto" / "inspecoes.sqlite")
    assert con.execute("SELECT count(*) FROM sessoes").fetchone()[0] == 0
    con.close()
    assert arm.sessao("abc") is not None  # o banco em uso continua com a sessão
