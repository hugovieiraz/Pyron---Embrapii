"""Controle de acesso do modo servidor: quem entra, por quanto tempo e o que cada perfil pode fazer.

No modo local (o de sempre: ``Pyron.exe`` -> 127.0.0.1) nada disto age: não há login e toda rota responde
como antes. No modo servidor (``python -m app.iniciar --modo servidor``), o mesmo ``app/servidor.py``
atende vários engenheiros pela rede, e cada pedido passa por :func:`verificar`, ligada como dependência
global do FastAPI.

- **Senha**: ``hashlib.scrypt`` da biblioteca padrão, com sal próprio por pessoa. A senha nunca é guardada
  nem devolvida; o ``config.json`` só tem o resultado (``senha_hash``).
- **Sessão**: um código aleatório no cookie ``pyron_sessao`` (HttpOnly, SameSite=Strict e Secure no HTTPS);
  o banco guarda só o SHA-256 dele. Vence com 12 h sem uso ou 7 dias depois de entrar.
- **Tentativas**: 5 senhas erradas em 15 min para o mesmo usuário e endereço (ou 20 do mesmo endereço)
  bloqueiam novas tentativas por 15 min.
- **CSRF**: o SameSite=Strict já impede outro site de mandar o cookie; além disso, pedido que grava com
  ``Origin`` de outro endereço, ou marcado pelo navegador como ``cross-site``, é recusado.
- **Proxy**: ``X-Forwarded-For``, ``-Proto`` e ``-Host`` só valem vindos do endereço configurado em
  ``--proxy``. Pedido com esses cabeçalhos vindo de outro endereço não conta como "deste computador".
- **Porta do proxy** (``--porta-proxy``, 0.9 F2): uma segunda porta, só em 127.0.0.1, para o proxy HTTPS (o
  ``tailscale serve``, que não documenta se envia ``X-Forwarded-For``). Tudo que chega por ela é de fora e em
  HTTPS, com ou sem cabeçalhos; a porta principal fica para quem usa o próprio computador.

Cada rota tem um grupo em :data:`CLASSIFICACAO` (público, leitura, envio, revisão, laudo, administração,
só local). Um teste percorre ``app.routes`` e falha se alguma rota nova ficar sem grupo; no modo
servidor, rota sem grupo responde 403.

Perfis (cadastro do time em Configurações › Empresa e time, ``config.json › responsaveis``):

- técnico: leitura, envio de imagens e medidas, comentários e situação de pendência que não seja urgente nem imediata;
- engenheiro: o do técnico e mais revisão (editar regiões, reprocessar, apagar);
- engenheiro que assina (com registro): o do engenheiro e mais o laudo;
- administrador (marca à parte, vale para qualquer perfil): configurações, modelos, treinos e backup.

Criar a primeira conta (o servidor não sobe no modo servidor sem um administrador com senha)::

    python -m app.acesso usuario --usuario ana --nome "Ana Lima" --perfil engenheiro --admin
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from fastapi import HTTPException, WebSocketException
from starlette.requests import HTTPConnection

MODOS = ("local", "servidor")
COOKIE = "pyron_sessao"
INATIVIDADE = timedelta(hours=12)
DURACAO_MAXIMA = timedelta(days=7)
RENOVAR_USO_S = 300  # grava "usada_em" no máximo a cada 5 min (não uma gravação por pedido)
LIMITE_TIME = 20  # pessoas no cadastro do time (decisão de 30/10/2026)
SENHA_MINIMA = 10
SENHA_MAXIMA = 200
RE_USUARIO = re.compile(r"[a-z0-9][a-z0-9._-]{2,31}")

# scrypt: custo de ~50 ms por conferência neste porte de máquina, 16 MB de memória
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_TAMANHO = 2**14, 8, 1, 64

JANELA_TENTATIVAS_S = 15 * 60
TENTATIVAS_POR_USUARIO = 5
TENTATIVAS_POR_ENDERECO = 20

GRUPOS = ("publico", "leitura", "envio", "revisao", "laudo", "administracao", "so_local")
PERMISSOES = ("leitura", "envio", "revisao", "laudo", "administracao")
METODOS_QUE_GRAVAM = ("POST", "PUT", "PATCH", "DELETE")
SEVERIDADES_SO_ENGENHEIRO = ("urgente", "imediato")  # pendência que o técnico não muda de situação

# ---------------------------------------------------------------- estado do processo

def _lista_ambiente(nome: str) -> frozenset:
    return frozenset(p.strip() for p in os.environ.get(nome, "").split(",") if p.strip())


_estado = {"modo": os.environ.get("PYRON_MODO", "local") if os.environ.get("PYRON_MODO") in MODOS else "local",
           "proxies": _lista_ambiente("PYRON_PROXY"),
           "porta_proxy": int(os.environ["PYRON_PORTA_PROXY"]) if os.environ.get("PYRON_PORTA_PROXY", "").isdigit() else None,
           "origens": _lista_ambiente("PYRON_ORIGEM")}
_armazenamento: Callable = lambda: None  # noqa: E731 — ligados por app.servidor (ligar())
_membros: Callable = lambda: []  # noqa: E731


def configurar(modo: str = "local", proxies=(), porta_proxy: int | None = None, origens=()) -> None:
    """Modo do processo, proxies confiáveis, porta reservada ao proxy e endereços públicos aceitos em ``Origin``
    (chamado por app.iniciar e pelos testes)."""
    if modo not in MODOS:
        raise ValueError(f"modo desconhecido: {modo}")
    _estado["modo"] = modo
    _estado["proxies"] = frozenset(str(p).strip() for p in proxies if str(p).strip())
    _estado["porta_proxy"] = int(porta_proxy) if porta_proxy else None
    _estado["origens"] = frozenset(str(o).strip().rstrip("/") for o in origens if str(o).strip())
    _tentativas.clear()


def ligar(armazenamento: Callable, membros: Callable) -> None:
    """De onde vêm as sessões (o armazenamento) e o time (o config.json): o servidor passa funções."""
    global _armazenamento, _membros
    _armazenamento, _membros = armazenamento, membros


def modo() -> str:
    return _estado["modo"]


def modo_servidor() -> bool:
    return _estado["modo"] == "servidor"


# ---------------------------------------------------------------- senha


def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(16)
    resumo = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_TAMANHO)
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(sal)}${b64(resumo)}"


def conferir_senha(senha: str, guardado: str | None) -> bool:
    """Compara em tempo constante. Sem hash guardado, faz a mesma conta à toa (não revela se o usuário existe)."""
    try:
        _, n, r, p, sal, resumo = (guardado or "").split("$")
        n, r, p, sal, resumo = int(n), int(r), int(p), base64.b64decode(sal), base64.b64decode(resumo)
    except ValueError:
        n, r, p, sal, resumo = SCRYPT_N, SCRYPT_R, SCRYPT_P, b"\0" * 16, b"\1" * SCRYPT_TAMANHO
        guardado = None
    calculado = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=n, r=r, p=p, dklen=len(resumo))
    return hmac.compare_digest(calculado, resumo) and guardado is not None


def validar_senha(senha) -> str:
    senha = str(senha or "")
    if len(senha) < SENHA_MINIMA:
        raise ValueError(f"A senha precisa de pelo menos {SENHA_MINIMA} caracteres.")
    if len(senha) > SENHA_MAXIMA:
        raise ValueError(f"A senha passa de {SENHA_MAXIMA} caracteres.")
    return senha


def conta(r: dict, anterior: dict | None, nome: str) -> dict:
    """Campos de acesso de um membro do time vindos da tela: usuário, administrador e senha nova (opcional).

    A senha guardada continua a mesma quando a tela não manda senha nova; sem usuário, ninguém entra.
    """
    usuario = str(r.get("usuario") or "").strip().lower()[:32]
    if usuario and not RE_USUARIO.fullmatch(usuario):
        raise ValueError(f"{nome}: o usuário tem de 3 a 32 letras sem acento, números, ponto, hífen ou sublinhado.")
    senha = r.get("senha")
    guardado = (anterior or {}).get("senha_hash") or ""
    if senha not in (None, ""):
        if not usuario:
            raise ValueError(f"{nome}: defina o nome de usuário antes da senha.")
        try:
            guardado = gerar_hash(validar_senha(senha))
        except ValueError as erro:
            raise ValueError(f"{nome}: {erro}") from erro
    return {"usuario": usuario, "administrador": bool(r.get("administrador", False)), "senha_hash": guardado if usuario else ""}


def pode_entrar(m: dict) -> bool:
    return bool(m.get("usuario") and m.get("senha_hash"))


def falta_para_servidor(membros: list[dict]) -> str | None:
    """Motivo para o modo servidor não subir, ou None. Exige um administrador com usuário e senha."""
    if not any(pode_entrar(m) and m.get("administrador") for m in membros):
        return ("O modo servidor precisa de ao menos um administrador com usuário e senha. Crie com:\n"
                "  python -m app.acesso usuario --usuario <nome> --nome \"<Nome completo>\" --admin")
    return None


# ---------------------------------------------------------------- perfis


def permissoes(m: dict | None) -> set[str]:
    """O que a pessoa pode fazer. Sem pessoa (modo local), tudo."""
    if m is None:
        return set(PERMISSOES)
    p = {"leitura", "envio"}
    if m.get("perfil") == "engenheiro":
        p.add("revisao")
        if m.get("assina") and m.get("registro"):
            p.add("laudo")
    if m.get("administrador"):
        p.add("administracao")
    return p


def descrever(m: dict) -> dict:
    """O que a interface sabe de quem entrou (nunca a senha, o telefone ou o e-mail)."""
    return {"id": m["id"], "nome": m["nome"], "usuario": m.get("usuario", ""), "perfil": m.get("perfil", "tecnico"),
            "funcao": m.get("funcao", ""), "registro": m.get("registro", ""), "assina": bool(m.get("assina")),
            "administrador": bool(m.get("administrador")), "permissoes": sorted(permissoes(m))}


def usuario(conn: HTTPConnection) -> dict | None:
    """Quem fez o pedido (membro do time), ou None no modo local."""
    return getattr(conn.state, "usuario", None)


def pode(conn: HTTPConnection, permissao: str) -> bool:
    return permissao in permissoes(usuario(conn))


# ---------------------------------------------------------------- de onde vem o pedido


@dataclass(frozen=True)
class Origem:
    ip: str
    esquema: str  # http ou https
    host: str
    local: bool  # este computador, sem proxy desconhecido no meio


def _loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def _host_loopback(host: str) -> bool:
    h = host.strip()
    nome = h[1:h.index("]")] if h.startswith("[") and "]" in h else h.split(":")[0]
    return nome in ("127.0.0.1", "localhost", "::1")


def origem(conn: HTTPConnection) -> Origem:
    """Endereço, esquema e host de quem pediu; os cabeçalhos X-Forwarded-* só valem vindos do proxy configurado.

    Pela porta reservada ao proxy, o pedido é sempre de fora e em HTTPS (o proxy faz o HTTPS); o endereço vem do
    ``X-Forwarded-For`` se o proxy mandar e, senão, do login do Tailscale (só para contar tentativas de senha).
    """
    par = conn.scope.get("client") or ("", 0)
    vizinho = str(par[0] or "")
    h = conn.headers
    esquema = {"ws": "http", "wss": "https"}.get(conn.url.scheme, conn.url.scheme)
    host = h.get("host", "")
    porta = (conn.scope.get("server") or (None, None))[1]
    if _estado["porta_proxy"] and porta == _estado["porta_proxy"]:
        cadeia = [p.strip() for p in h.get("x-forwarded-for", "").split(",") if p.strip()]
        ip = cadeia[-1] if cadeia else f"proxy:{h.get('tailscale-user-login', '')}"
        host = h.get("x-forwarded-host", "").split(",")[0].strip() or host
        return Origem(ip=ip, esquema="https", host=host, local=False)
    ip = vizinho
    confiavel = vizinho in _estado["proxies"]
    if confiavel:
        for candidato in reversed([p.strip() for p in h.get("x-forwarded-for", "").split(",") if p.strip()]):
            ip = candidato
            if candidato not in _estado["proxies"]:
                break
        proto = h.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        if proto in ("http", "https"):
            esquema = proto
        host = h.get("x-forwarded-host", "").split(",")[0].strip() or host
    local = _loopback(ip) and (confiavel or "x-forwarded-for" not in h)
    return Origem(ip=ip, esquema=esquema, host=host, local=local)


def _mesma_origem(conn: HTTPConnection, o: Origem) -> bool:
    site = conn.headers.get("sec-fetch-site", "")
    if site == "cross-site":
        return False
    enviada = conn.headers.get("origin")
    if enviada is None:
        return True  # pedido sem Origin (não é de navegador, ou GET); o cookie SameSite=Strict já cobre o resto
    if enviada in _estado["origens"] or enviada == f"{o.esquema}://{o.host}":
        return True
    # proxy que entrega o pedido com o Host dele (127.0.0.1:porta): vale o que o navegador diz do próprio pedido
    return _host_loopback(o.host) and site == "same-origin"


# ---------------------------------------------------------------- tentativas de entrar

_tentativas: dict[str, deque] = {}
_trava_tentativas = threading.Lock()


def _recentes(chave: str, agora: float) -> deque:
    fila = _tentativas.setdefault(chave, deque())
    while fila and agora - fila[0] > JANELA_TENTATIVAS_S:
        fila.popleft()
    return fila


def bloqueado(ip: str, usuario_: str, agora: float | None = None) -> bool:
    agora = time.time() if agora is None else agora
    with _trava_tentativas:
        return (len(_recentes(f"u:{ip}:{usuario_}", agora)) >= TENTATIVAS_POR_USUARIO
                or len(_recentes(f"e:{ip}", agora)) >= TENTATIVAS_POR_ENDERECO)


def _errou(ip: str, usuario_: str, agora: float) -> None:
    with _trava_tentativas:
        _recentes(f"u:{ip}:{usuario_}", agora).append(agora)
        _recentes(f"e:{ip}", agora).append(agora)


def _acertou(ip: str, usuario_: str) -> None:
    with _trava_tentativas:
        _tentativas.pop(f"u:{ip}:{usuario_}", None)


# ---------------------------------------------------------------- sessão


def _resumo(codigo: str) -> str:
    return hashlib.sha256(codigo.encode("ascii", "replace")).hexdigest()


def _membro(membro_id: str) -> dict | None:
    return next((m for m in _membros() if m.get("id") == membro_id and pode_entrar(m)), None)


def sessao_atual(conn: HTTPConnection, agora: datetime | None = None) -> tuple[dict, str] | None:
    """(membro, resumo do código) da sessão válida do cookie, ou None."""
    codigo = conn.cookies.get(COOKIE)
    if not codigo or len(codigo) > 128:
        return None
    arm = _armazenamento()
    resumo = _resumo(codigo)
    s = arm.sessao(resumo)
    if s is None:
        return None
    agora = agora or datetime.now()
    if agora >= datetime.fromisoformat(s["expira_em"]) or agora - datetime.fromisoformat(s["usada_em"]) >= INATIVIDADE:
        arm.encerrar_sessao(resumo)
        return None
    m = _membro(s["membro_id"])
    if m is None:  # saiu do time ou ficou sem senha
        arm.encerrar_sessao(resumo)
        return None
    if (agora - datetime.fromisoformat(s["usada_em"])).total_seconds() > RENOVAR_USO_S:
        arm.usar_sessao(resumo, agora)
    return m, resumo


def entrar(conn: HTTPConnection, usuario_: str, senha: str) -> tuple[dict, str]:
    """Confere usuário e senha e abre a sessão. Devolve (membro, código para o cookie)."""
    o = origem(conn)
    if o.esquema != "https" and not o.local:
        raise HTTPException(400, "No modo servidor, só se entra por HTTPS. Use o endereço com https:// "
                                 "(o proxy precisa estar em --proxy para o Pyron saber que a conexão é segura).")
    usuario_ = str(usuario_ or "").strip().lower()[:32]
    agora = time.time()
    if bloqueado(o.ip, usuario_, agora):
        raise HTTPException(429, "Muitas tentativas erradas. Espere 15 minutos e tente de novo.")
    m = next((x for x in _membros() if usuario_ and x.get("usuario") == usuario_ and pode_entrar(x)), None)
    if not conferir_senha(str(senha or "")[:SENHA_MAXIMA], m.get("senha_hash") if m else None) or m is None:
        _errou(o.ip, usuario_, agora)
        raise HTTPException(401, "Usuário ou senha não conferem.")
    _acertou(o.ip, usuario_)
    codigo = secrets.token_urlsafe(32)
    inicio = datetime.now()
    _armazenamento().criar_sessao(_resumo(codigo), m["id"], inicio, inicio + DURACAO_MAXIMA)
    return m, codigo


def sair(conn: HTTPConnection) -> None:
    codigo = conn.cookies.get(COOKIE)
    if codigo:
        _armazenamento().encerrar_sessao(_resumo(codigo))


def gravar_cookie(resposta, conn: HTTPConnection, codigo: str) -> None:
    resposta.set_cookie(COOKIE, codigo, max_age=int(DURACAO_MAXIMA.total_seconds()), path="/", httponly=True,
                        samesite="strict", secure=origem(conn).esquema == "https")


def apagar_cookie(resposta, conn: HTTPConnection) -> None:
    resposta.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict", secure=origem(conn).esquema == "https")


# ---------------------------------------------------------------- a dependência de toda rota


def _negar(conn: HTTPConnection, status: int, texto: str):
    if conn.scope["type"] == "websocket":
        return WebSocketException(code=1008, reason=texto[:120])
    return HTTPException(status, texto)


def grupo_da_rota(conn: HTTPConnection) -> str | None:
    rota = conn.scope.get("route")
    caminho = getattr(rota, "path", None)
    metodo = "WS" if conn.scope["type"] == "websocket" else conn.scope.get("method", "GET")
    if metodo == "HEAD":
        metodo = "GET"
    return CLASSIFICACAO.get(f"{metodo} {caminho}")


async def verificar(conn: HTTPConnection) -> None:
    """Dependência global do FastAPI. No modo local, não faz nada."""
    conn.state.usuario = None
    if not modo_servidor():
        return
    from starlette.concurrency import run_in_threadpool

    grupo = grupo_da_rota(conn)
    if grupo is None:
        raise _negar(conn, 403, "Rota sem classificação de acesso.")
    o = origem(conn)
    metodo = conn.scope.get("method", "GET")
    if metodo in METODOS_QUE_GRAVAM and not _mesma_origem(conn, o):
        raise _negar(conn, 403, "Pedido de outro endereço recusado.")
    if grupo == "publico":
        return
    if grupo == "so_local" and not o.local:
        raise _negar(conn, 403, "Esta ação só funciona no próprio computador do servidor.")
    atual = await run_in_threadpool(sessao_atual, conn)  # lê o banco: fora do laço de eventos
    if atual is None:
        raise _negar(conn, 401, "Entre com seu usuário e senha.")
    conn.state.usuario = atual[0]
    conn.state.sessao = atual[1]
    precisa = {"so_local": "administracao", "leitura": "leitura"}.get(grupo, grupo)
    if precisa not in permissoes(atual[0]):
        raise _negar(conn, 403, TEXTO_SEM_PERMISSAO[precisa])


TEXTO_SEM_PERMISSAO = {
    "leitura": "Seu perfil não pode ver isto.",
    "envio": "Seu perfil não pode enviar imagens ou medidas.",
    "revisao": "Só engenheiro pode revisar ou apagar inspeções.",
    "laudo": "Só engenheiro que assina (com registro) emite laudo.",
    "administracao": "Só administrador pode mudar isto.",
}

# ---------------------------------------------------------------- classificação das rotas
# Fonte: docs/v09/0-diagnostico.md, seção 2. Rota nova sem grupo aqui: o teste falha e, no modo servidor, 403.

_GRUPOS_DAS_ROTAS = {
    "publico": [
        "GET /api/saude", "GET /api/acesso/eu", "POST /api/acesso/entrar", "POST /api/acesso/sair",
        "GET /nova", "GET /nova/", "GET /antiga",
    ],
    "leitura": [
        "POST /api/acesso/senha",
        "GET /api/analises", "GET /api/analises/{id_}", "GET /api/analises/{id_}/imagem.png",
        "GET /api/analises/{id_}/temperaturas.csv", "GET /api/analises/{id_}/foto.jpg",
        "GET /api/analises/{id_}/original.jpg", "GET /api/analises/{id_}/miniatura.png",
        "GET /api/analises/{id_}/vizinhas", "GET /api/analises/{id_}/comentarios", "GET /api/inspecoes.csv",
        "GET /api/equipamentos", "GET /api/equipamentos/{chave}", "GET /api/pendencias",
        "GET /api/status", "GET /api/alertas", "GET /api/alertas/{id_}/whatsapp", "GET /api/monitoramento",
        "GET /api/monitoramento/previa", "GET /api/criterios", "GET /api/paletas", "GET /api/modelos",
        "GET /api/exemplos", "GET /api/exemplos/{nome}/miniatura.jpg", "GET /api/configuracoes",
        "GET /api/configuracoes/logo.png", "GET /api/laudos/emitidos",
        "GET /api/videos", "GET /api/videos/{id_}", "GET /api/videos/{id_}/quadros/{n}.jpg",
        "GET /api/medicao/estado", "GET /api/medicao/instalar", "GET /api/medicao/acelerador",
        "GET /api/medicao/registro", "GET /api/medicao/registro.csv", "GET /api/medicao/fotos",
        "GET /api/medicao/fotos/{codigo}", "GET /api/medicao/fotos/{codigo}/miniatura",
        "GET /api/medicao/videos/{codigo}", "GET /api/medicao/biblioteca",
        "GET /api/medicao/biblioteca/{id_}/miniatura.jpg", "GET /api/medicao/celular",
        "GET /api/cadastro/medidas", "GET /api/cadastro/equipamentos/{chave}/fases", "GET /api/cadastro/cameras",
        "GET /api/treinos", "GET /api/treinos/ambiente", "GET /api/treinos/{id_}", "GET /api/treinos/{id_}/previsoes.png",
        "GET /api/avaliacoes", "GET /api/avaliacoes/{id_}", "GET /api/avaliacoes/{id_}/arquivos/{nome}",
        "GET /api/celular", "GET /api/celular/qr.png", "WS /api/celular/ws",
    ],
    "envio": [
        "POST /api/analises", "POST /api/exemplos/{nome}/analisar", "POST /api/analises/{id_}/comentarios",
        "PUT /api/analises/{id_}/acompanhamento",  # o técnico só nas que não são urgentes nem imediatas (na rota)
        "POST /api/videos", "POST /api/videos/{id_}/cancelar", "POST /api/videos/{id_}/quadros/{n}/inspecao",
        "POST /api/medicao", "POST /api/medicao/comparar", "POST /api/medicao/previa", "POST /api/medicao/fotos",
        "POST /api/medicao/referencia", "POST /api/medicao/plano", "POST /api/medicao/video/keyframes",
        "POST /api/medicao/video/medir", "POST /api/medicao/video/comparar", "POST /api/medicao/contexto-2d",
        "PUT /api/medicao/registro/{codigo}", "POST /api/cadastro/medidas", "POST /api/cadastro/cameras/{nome}/conferir",
    ],
    "revisao": [
        "PUT /api/analises/{id_}", "POST /api/analises/identificacao", "POST /api/analises/{id_}/detectar",
        "POST /api/analises/{id_}/segmentar", "POST /api/analises/{id_}/classificar",
        "POST /api/analises/{id_}/metodologia_completa", "POST /api/analises/{id_}/parametros",
        "POST /api/analises/{id_}/escala", "POST /api/analises/{id_}/auto_identificar",
        "PUT /api/alertas/{id_}", "DELETE /api/analises/{id_}", "DELETE /api/videos/{id_}", "POST /api/cadastro/escala",
    ],
    "laudo": [
        "GET /api/analises/{id_}/laudo.pdf", "POST /api/laudos",
        "POST /api/cadastro/medidas/{medida_id}/validar", "POST /api/cadastro/medidas/{medida_id}/rejeitar",
    ],
    "administracao": [
        "PUT /api/configuracoes", "POST /api/configuracoes/logo", "DELETE /api/configuracoes/logo", "GET /api/sistema",
        "PUT /api/modelos/ativo", "POST /api/modelos/instalar",
        "POST /api/treinos/rotulos", "POST /api/treinos/pacote", "POST /api/treinos", "POST /api/treinos/{id_}/cancelar",
        "POST /api/avaliacoes", "DELETE /api/avaliacoes/{id_}",
        "POST /api/videos/{id_}/gravar-pesos", "POST /api/videos/{id_}/reconhecer-biblioteca",
        "POST /api/medicao/video/gravar-pesos", "DELETE /api/medicao/biblioteca/{id_}",
        "POST /api/cadastro/cameras/ficha", "POST /api/cadastro/cameras/calibrar", "POST /api/cadastro/cameras/{nome}/posicao",
        "PUT /api/monitoramento", "POST /api/monitoramento/verificar", "POST /api/medicao/acelerador/benchmark",
        "GET /api/backup.zip", "POST /api/celular/ligar", "POST /api/celular/desligar",
    ],
    "so_local": [
        "POST /api/sistema/abrir-pasta", "POST /api/encerrar", "POST /api/sinal", "POST /api/backup/restaurar",
        "POST /api/medicao/instalar",
    ],
}


def _montar_classificacao() -> dict[str, str]:
    saida: dict[str, str] = {}
    for grupo, rotas in _GRUPOS_DAS_ROTAS.items():
        for rota in rotas:
            if rota in saida:
                raise RuntimeError(f"rota classificada duas vezes: {rota}")
            saida[rota] = grupo
    return saida


CLASSIFICACAO = _montar_classificacao()


# ---------------------------------------------------------------- linha de comando (criar a primeira conta)


def _pasta_dados(argumento: str | None) -> Path:
    if argumento:
        return Path(argumento).resolve()
    return Path(os.environ.get("PYRON_DADOS") or Path(__file__).resolve().parent / "dados_app")


def _ler_config(pasta: Path) -> dict:
    arq = pasta / "config.json"
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}


def _time(cfg: dict) -> list[dict]:
    time_ = list(cfg.get("responsaveis") or [])
    antigo = cfg.get("responsavel") or {}
    if not time_ and (antigo.get("nome") or "").strip():  # mesma migração de app.servidor._config
        time_ = [{"id": "r1", "nome": antigo["nome"].strip(), "funcao": "", "registro": (antigo.get("registro") or "").strip()}]
        cfg["responsavel_padrao"] = "r1"
        cfg["responsavel"] = {"nome": "", "registro": ""}
    return time_


def criar_usuario(pasta: Path, usuario_: str, nome: str, senha: str, perfil: str | None = None, admin: bool | None = None,
                  registro: str = "", assina: bool = False) -> dict:
    """Cria ou atualiza uma conta direto no config.json (o servidor relê o arquivo a cada pedido).

    Numa conta que já existe, perfil e administrador só mudam se vierem (None mantém).
    """
    cfg = _ler_config(pasta)
    time_ = _time(cfg)
    usuario_ = usuario_.strip().lower()
    existente = next((m for m in time_ if m.get("usuario") == usuario_), None)
    if existente is None and len(time_) >= LIMITE_TIME:
        raise ValueError(f"O time já tem {LIMITE_TIME} pessoas.")
    perfil = perfil or (existente or {}).get("perfil") or "engenheiro"
    admin = bool((existente or {}).get("administrador")) if admin is None else admin
    if perfil not in ("engenheiro", "tecnico"):
        raise ValueError("Perfil deve ser engenheiro ou tecnico.")
    if assina and not registro.strip():
        raise ValueError("Quem assina laudo precisa do registro profissional (--registro).")
    acesso = conta({"usuario": usuario_, "senha": senha, "administrador": admin}, existente, nome or usuario_)
    if existente is None:
        existente = {"id": secrets.token_hex(4), "nome": (nome or usuario_).strip()[:120], "perfil": perfil, "funcao": "",
                     "registro": registro.strip()[:60], "email": "", "telefone": "", "assina": assina, "alertas": None}
        time_.append(existente)
    else:
        existente.update({k: v for k, v in (("nome", nome.strip()[:120]), ("registro", registro.strip()[:60])) if v})
        existente["perfil"] = perfil
        existente["assina"] = assina or existente.get("assina", False)
    existente.update(acesso)
    cfg["responsaveis"] = time_
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return existente


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.acesso", description="Contas do modo servidor do Pyron.")
    sub = ap.add_subparsers(dest="comando", required=True)
    u = sub.add_parser("usuario", help="cria ou atualiza uma conta (pede a senha; ou PYRON_SENHA)")
    u.add_argument("--usuario", required=True)
    u.add_argument("--nome", default="")
    u.add_argument("--perfil", choices=("engenheiro", "tecnico"), help="padrão: engenheiro (conta nova) ou o atual")
    u.add_argument("--admin", action="store_true", help="marca como administrador")
    u.add_argument("--registro", default="", help="registro profissional (CREA ou CFT)")
    u.add_argument("--assina", action="store_true", help="assina laudo (exige --registro)")
    u.add_argument("--dados", help="pasta de dados (padrão: PYRON_DADOS ou app/dados_app)")
    c = sub.add_parser("conferir", help="diz se o modo servidor pode subir com o cadastro atual")
    c.add_argument("--dados")
    k = sub.add_parser("cabecalhos", help="mostra os cabeçalhos que o proxy entrega (conferência do tailscale serve)")
    k.add_argument("--porta", type=int, default=8767)
    args = ap.parse_args(argv)
    if args.comando == "cabecalhos":
        return mostrar_cabecalhos(args.porta)
    pasta = _pasta_dados(args.dados)
    if args.comando == "conferir":
        falta = falta_para_servidor(_time(_ler_config(pasta)))
        print(falta or f"Pronto para o modo servidor ({pasta}).")
        return 1 if falta else 0
    senha = os.environ.get("PYRON_SENHA")
    if not senha:
        senha = getpass.getpass("Senha: ")
        if getpass.getpass("Repita a senha: ") != senha:
            print("As senhas não conferem.", file=sys.stderr)
            return 2
    try:
        m = criar_usuario(pasta, args.usuario, args.nome, senha, args.perfil, True if args.admin else None, args.registro, args.assina)
    except ValueError as erro:
        print(erro, file=sys.stderr)
        return 2
    print(f"Conta {m['usuario']} ({m['nome']}) gravada em {pasta / 'config.json'}"
          f"{' como administrador' if m.get('administrador') else ''}. Sessões abertas continuam até sair ou vencer.")
    return 0


def mostrar_cabecalhos(porta: int) -> int:
    """Servidor mínimo em 127.0.0.1 que imprime os cabeçalhos de cada pedido e os devolve na página.

    Para conferir, uma vez, o que o proxy entrega:  tailscale serve --bg <porta>  e abrir o endereço no tablet.
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Mostrar(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (nome do http.server)
            texto = f"{self.client_address[0]} {self.command} {self.path}\n" + "".join(f"{k}: {v}\n" for k, v in self.headers.items())
            print(texto, flush=True)
            corpo = texto.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *args):  # o print acima já mostra
            pass

    print(f"Ouvindo em http://127.0.0.1:{porta}. Ctrl+C para parar.")
    try:
        HTTPServer(("127.0.0.1", porta), Mostrar).serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
