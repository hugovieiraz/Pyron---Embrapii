"""Servidor do Pyron: API e interface web, rodando só no computador do usuário.

Iniciar:  Pyron.exe na área de trabalho, ou  python -m app.iniciar --janela
"""

from __future__ import annotations

import base64
import csv
import io
import json
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from time import perf_counter

import numpy as np
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from app import laudo
from app.armazenamento import Armazenamento
from nucleo import analise, detectores, entrada, referencias, render

VERSAO = "0.1.0"
RAIZ = Path(__file__).resolve().parents[1]
PASTA_APP = Path(__file__).resolve().parent
PASTA_DADOS = PASTA_APP / "dados_app"
PASTA_MODELOS = RAIZ / "modelos"
PASTA_EXEMPLOS = RAIZ / "dados" / "sciencedb_10185"
INVENTARIO = RAIZ / "saida" / "e00_inventario" / "inventario.csv"

NOMES_CLASSES = {
    "ponto_quente": "Ponto quente",
    "componente": "Componente",
    "para_raio": "Para-raio",
    "terminal_superior": "Terminal superior",
    "isolador": "Isolador",
    "terminal_inferior": "Terminal inferior",
    "bucha": "Bucha",
    "conexao": "Conexão",
    "radiador": "Radiador",
    "tanque": "Tanque",
}
NOMES_EXEMPLOS = {
    "Power Transformers": "Transformador de potência",
    "Surge Arresters": "Para-raios",
    "Circuit Breakers": "Disjuntor",
    "Disconnectors": "Seccionadora",
    "Wave Traps": "Bobina de bloqueio",
}

app = FastAPI(title="Pyron", version=VERSAO)
armazenamento = Armazenamento(PASTA_DADOS)
_trava = threading.Lock()


ocr = entrada.OCRPreguicoso()


# ---------------------------------------------------------------- configuração

CONFIG_PADRAO = {
    "modelo_ativo": "pontos-quentes",
    "empresa": {"nome": "", "subtitulo": ""},
    "responsavel": {"nome": "", "registro": ""},
    "tema": "sistema",
    "criterios": None,  # None: critério padrão (modelo brasileiro, NBR 15866)
    "componentes": {},  # trocas do usuário na biblioteca de componentes (MTA por classe)
}


def _config() -> dict:
    cfg = json.loads(json.dumps(CONFIG_PADRAO))
    arq = PASTA_DADOS / "config.json"
    if arq.exists():
        try:
            salvo = json.loads(arq.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            salvo = {}
        for chave, valor in salvo.items():
            if isinstance(cfg.get(chave), dict) and isinstance(valor, dict):
                cfg[chave].update(valor)
            else:
                cfg[chave] = valor
    return cfg


def _salvar_config(cfg: dict) -> None:
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    (PASTA_DADOS / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _criterios() -> dict:
    return _config().get("criterios") or analise.CRITERIOS_PADRAO


def _componentes() -> dict:
    return referencias.componentes(_config().get("componentes"))


def _validar_criterios(c: dict) -> dict:
    """Confere e normaliza um critério editado pelo usuário."""
    saida = {"nome": str(c.get("nome") or "Critério do usuário")[:120]}
    for grupo in ("similares", "dieletrico", "mta_faixas", "ambiente"):
        linhas = []
        for limite, nivel in c.get(grupo, analise.CRITERIOS_PADRAO[grupo]):
            if nivel not in analise.NIVEIS or nivel == "normal":
                raise HTTPException(422, f"Nível desconhecido no critério: {nivel}.")
            linhas.append([round(float(limite), 2), nivel])
        linhas.sort(key=lambda linha: linha[0])
        ordens = [analise.NIVEIS[n]["ordem"] for _, n in linhas]
        if ordens != sorted(ordens):
            raise HTTPException(422, "Os limites precisam subir junto com a gravidade dos níveis.")
        saida[grupo] = linhas
    saida["usar_ambiente"] = bool(c.get("usar_ambiente", False))
    expoente = float(c.get("expoente_carga", 2.0))
    carga_min = float(c.get("carga_minima_pct", 40.0))
    if not 1.0 <= expoente <= 3.0 or not 0 <= carga_min <= 100:
        raise HTTPException(422, "Expoente de carga entre 1 e 3 e carga mínima entre 0 e 100%.")
    saida["expoente_carga"], saida["carga_minima_pct"] = expoente, carga_min
    return saida


def _validar_componentes(c: dict) -> dict:
    saida = {}
    for classe, v in c.items():
        classe = str(classe)[:40]
        mta = v.get("mta_c")
        if mta not in (None, ""):
            mta = float(mta)
            if not 20 <= mta <= 400:
                raise HTTPException(422, f"MTA de {classe} fora da faixa de 20 a 400 °C.")
        else:
            mta = None
        item = {"mta_c": mta}
        if v.get("fonte"):
            item["fonte"] = str(v["fonte"])[:200]
        saida[classe] = item
    return saida


def _detector(id_: str | None) -> detectores.Detector:
    try:
        return detectores.obter(id_ or _config()["modelo_ativo"], PASTA_MODELOS)
    except KeyError:
        return detectores.obter("pontos-quentes", PASTA_MODELOS)


def _info_modelo(det: detectores.Detector) -> dict:
    return {
        "id": det.id,
        "nome": det.nome,
        "tipo": det.tipo,
        "arquitetura": det.arquitetura,
        "classes": det.classes,
        "nomes": det.nomes,
    }


# ---------------------------------------------------------------- análise


def _regioes_do_detector(det: detectores.Detector, matriz: np.ndarray) -> list[dict]:
    contagem: dict[str, int] = {}
    regioes = []
    for d in det.detectar(matriz):
        contagem[d.classe] = contagem.get(d.classe, 0) + 1
        regioes.append(
            {
                "id": uuid.uuid4().hex[:8],
                "nome": f"{det.nomes.get(d.classe) or NOMES_CLASSES.get(d.classe, d.classe)} {contagem[d.classe]}",
                "classe": d.classe,
                "caixa": [round(v, 2) for v in d.caixa],
                "confianca": d.confianca,
                "origem": f"modelo:{det.id}",
            }
        )
    return regioes


def _calcular(a: dict, matriz: np.ndarray) -> dict:
    cond = a.get("condicoes", {})
    campos = ("id", "nome", "classe", "caixa", "confianca", "origem")
    base = [{k: v for k, v in r.items() if k in campos} for r in a["regioes"]]
    a["regioes"], a["resumo"] = analise.analisar_regioes(
        matriz, base, cond.get("ambiente_c"), cond.get("carga_pct"), criterios=_criterios(), componentes=_componentes()
    )
    return a


def _nova_analise(dados: bytes, nome: str, modelo: str | None) -> dict:
    t0 = perf_counter()
    try:
        img = entrada.carregar(dados, ocr=ocr)
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro
    t1 = perf_counter()
    det = _detector(modelo)
    try:
        regioes = _regioes_do_detector(det, img.temperatura_c)
    except ValueError as erro:
        raise HTTPException(422, f"O modelo {det.nome} falhou: {erro}") from erro
    t2 = perf_counter()
    lo, hi = render.faixa_exibicao(img.temperatura_c)
    resp = _config()["responsavel"]
    a = {
        "id": uuid.uuid4().hex,
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "arquivo": nome,
        "radiometrica": img.radiometrica,
        "origem": img.origem,
        "metadados": img.metadados,
        "modelo": _info_modelo(det),
        "condicoes": {"ambiente_c": None, "carga_pct": None},
        "identificacao": {k: v for k, v in (("responsavel", resp.get("nome")), ("art", resp.get("registro"))) if v},
        "regioes": regioes,
        "tem_foto": img.foto_visivel is not None,
        "matriz_info": {
            "largura": int(img.temperatura_c.shape[1]),
            "altura": int(img.temperatura_c.shape[0]),
            "faixa_exibicao": [lo, hi],
        },
    }
    _calcular(a, img.temperatura_c)
    t3 = perf_counter()
    a["etapas"] = [
        {"nome": "Leitura da temperatura", "ms": round((t1 - t0) * 1000)},
        {"nome": "Detecção", "ms": round((t2 - t1) * 1000)},
        {"nome": "Medição e severidade", "ms": round((t3 - t2) * 1000)},
    ]
    armazenamento.salvar(a, original=dados, matriz=img.temperatura_c)
    if img.foto_visivel:
        armazenamento.salvar_foto(a["id"], img.foto_visivel)
    return a


def _completa(a: dict) -> dict:
    matriz = armazenamento.matriz(a["id"])
    saida = dict(a)
    if matriz is not None:
        saida["matriz"] = {
            "largura": int(matriz.shape[1]),
            "altura": int(matriz.shape[0]),
            "dados": base64.b64encode(np.ascontiguousarray(matriz, dtype="<f4").tobytes()).decode(),
        }
    return saida


def _carregar(id_: str) -> tuple[dict, np.ndarray]:
    a = armazenamento.obter(id_)
    m = armazenamento.matriz(id_)
    if a is None or m is None:
        raise HTTPException(404, "Inspeção não encontrada.")
    return a, m


# ---------------------------------------------------------------- rotas: análise


@app.get("/api/saude")
def saude() -> dict:
    return {"ok": True, "app": "Pyron", "versao": VERSAO}  # o lançador (.exe) confere o "app"


@app.post("/api/analises")
async def criar(arquivo: UploadFile = File(...), modelo: str | None = Form(None)) -> dict:
    dados = await arquivo.read()
    if not dados:
        raise HTTPException(422, "O arquivo está vazio.")
    with _trava:
        return _completa(_nova_analise(dados, arquivo.filename or "imagem.jpg", modelo))


@app.get("/api/analises")
def listar() -> list[dict]:
    return armazenamento.listar()


@app.get("/api/analises/{id_}")
def obter(id_: str) -> dict:
    a, m = _carregar(id_)
    _calcular(a, m)  # sempre com o critério em vigor
    return _completa(a)


@app.put("/api/analises/{id_}")
def atualizar(id_: str, corpo: dict = Body(...)) -> dict:
    a, m = _carregar(id_)
    if "regioes" in corpo:
        novas = []
        for r in corpo["regioes"]:
            caixa = [float(v) for v in r["caixa"]]
            if caixa[2] - caixa[0] < 1 or caixa[3] - caixa[1] < 1:
                continue
            novas.append(
                {
                    "id": r.get("id") or uuid.uuid4().hex[:8],
                    "nome": str(r.get("nome") or "Região")[:60],
                    "classe": str(r.get("classe") or "componente")[:40],
                    "caixa": caixa,
                    "confianca": r.get("confianca"),
                    "origem": r.get("origem") or "manual",
                }
            )
        a["regioes"] = novas
    if "condicoes" in corpo:
        c = corpo["condicoes"]
        a["condicoes"] = {
            "ambiente_c": float(c["ambiente_c"]) if c.get("ambiente_c") not in (None, "") else None,
            "carga_pct": float(c["carga_pct"]) if c.get("carga_pct") not in (None, "") else None,
        }
    if "identificacao" in corpo:
        a["identificacao"] = {k: str(v)[:300] for k, v in corpo["identificacao"].items()}
    _calcular(a, m)
    armazenamento.salvar(a)
    return _completa(a)


@app.post("/api/analises/{id_}/detectar")
def detectar_de_novo(id_: str, corpo: dict = Body(default={})) -> dict:
    a, m = _carregar(id_)
    det = _detector(corpo.get("modelo"))
    manuais = [r for r in a["regioes"] if r.get("origem") == "manual"]
    try:
        a["regioes"] = manuais + _regioes_do_detector(det, m)
    except ValueError as erro:
        raise HTTPException(422, f"O modelo {det.nome} falhou: {erro}") from erro
    a["modelo"] = _info_modelo(det)
    _calcular(a, m)
    armazenamento.salvar(a)
    return _completa(a)


@app.delete("/api/analises/{id_}")
def apagar(id_: str) -> dict:
    if not armazenamento.apagar(id_):
        raise HTTPException(404, "Inspeção não encontrada.")
    return {"ok": True}


@app.get("/api/analises/{id_}/foto.jpg")
def foto(id_: str) -> Response:
    dados = armazenamento.foto(id_)
    if not dados:
        raise HTTPException(404, "Esta imagem não tem foto visível.")
    return Response(dados, media_type="image/jpeg")


@app.get("/api/analises/{id_}/original.jpg")
def original(id_: str) -> Response:
    dados = armazenamento.original(id_)
    if not dados:
        raise HTTPException(404, "Imagem original não encontrada.")
    return Response(dados, media_type="image/jpeg")


@app.get("/api/analises/{id_}/miniatura.png")
def miniatura(id_: str) -> Response:
    a, m = _carregar(id_)
    buf = io.BytesIO()
    render.desenhar(m, a["regioes"], largura=320).save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png")


@app.get("/api/analises/{id_}/laudo.pdf")
def laudo_pdf(id_: str) -> Response:
    a, m = _carregar(id_)
    pdf = laudo.gerar(a, m, armazenamento.foto(id_), VERSAO, empresa=_config()["empresa"])
    nome = f"laudo_{re.sub(r'[^A-Za-z0-9_-]', '_', Path(a['arquivo']).stem)}_{a['id'][:6]}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nome}"'})


# ---------------------------------------------------------------- rotas: exemplos


def _mapa_exemplos() -> dict[str, Path]:
    if not PASTA_EXEMPLOS.exists():
        return {}
    return {p.name: p for p in PASTA_EXEMPLOS.rglob("*.jpg")}


def _curadoria() -> list[dict]:
    """Algumas imagens de cada tipo de equipamento, das mais quentes para as mais frias."""
    mapa = _mapa_exemplos()
    if not mapa:
        return []
    por_classe: dict[str, list[tuple[float, str]]] = {}
    if INVENTARIO.exists():
        with open(INVENTARIO, encoding="utf-8") as f:
            for linha in csv.DictReader(f):
                if linha.get("jpeg_ok") == "True" and linha.get("t_max") and "Copy" not in linha["arquivo"]:
                    por_classe.setdefault(linha["classe"], []).append((float(linha["t_max"]), linha["arquivo"]))
    else:
        for nome, p in mapa.items():
            por_classe.setdefault(p.parent.name, []).append((0.0, nome))
    cotas = {"Power Transformers": 4, "Surge Arresters": 3, "Circuit Breakers": 2, "Disconnectors": 2, "Wave Traps": 1}
    itens = []
    for classe, cota in cotas.items():
        # Evita o sol no quadro (leituras acima de 150 °C) na vitrine.
        candidatos = [c for c in sorted(por_classe.get(classe, []), reverse=True) if c[0] < 150]
        for _t, nome in candidatos[:cota]:
            if nome in mapa:
                itens.append({"nome": nome, "classe": NOMES_EXEMPLOS.get(classe, classe)})
    return itens


@app.get("/api/exemplos")
def exemplos() -> dict:
    return {
        "fonte": "Dataset de estudo ScienceDB 10185 (FLIR C5, subestação de 132 kV). Licença CC BY-NC-SA 4.0: só estudo.",
        "itens": _curadoria(),
    }


def _exemplo(nome: str) -> Path:
    if not re.fullmatch(r"FLIR\d+\.jpg", nome):
        raise HTTPException(400, "Nome de exemplo inválido.")
    caminho = _mapa_exemplos().get(nome)
    if caminho is None:
        raise HTTPException(404, "Exemplo não encontrado.")
    return caminho


@app.get("/api/exemplos/{nome}/miniatura.jpg")
def miniatura_exemplo(nome: str) -> Response:
    img = Image.open(_exemplo(nome)).convert("RGB")
    img.thumbnail((320, 240))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return Response(buf.getvalue(), media_type="image/jpeg")


@app.post("/api/exemplos/{nome}/analisar")
def analisar_exemplo(nome: str, corpo: dict = Body(default={})) -> dict:
    caminho = _exemplo(nome)
    with _trava:
        return _completa(_nova_analise(caminho.read_bytes(), nome, corpo.get("modelo")))


# ---------------------------------------------------------------- rotas: modelos e critérios


@app.get("/api/modelos")
def modelos() -> dict:
    return {"ativo": _config()["modelo_ativo"], "modelos": [d.descrever() for d in detectores.listar(PASTA_MODELOS)]}


@app.put("/api/modelos/ativo")
def definir_ativo(corpo: dict = Body(...)) -> dict:
    det = _detector(corpo.get("id"))
    if det.id != corpo.get("id"):
        raise HTTPException(404, "Modelo não encontrado.")
    cfg = _config()
    cfg["modelo_ativo"] = det.id
    _salvar_config(cfg)
    return modelos()


@app.get("/api/criterios")
def criterios() -> dict:
    return {"criterio": _criterios(), "padrao": analise.CRITERIOS_PADRAO, "niveis": analise.NIVEIS}


@app.get("/api/configuracoes")
def configuracoes() -> dict:
    cfg = _config()
    return {
        "empresa": cfg["empresa"],
        "responsavel": cfg["responsavel"],
        "tema": cfg["tema"],
        "criterio": cfg.get("criterios") or analise.CRITERIOS_PADRAO,
        "criterio_padrao": analise.CRITERIOS_PADRAO,
        "modelos_criterio": {"brasil": analise.CRITERIOS_PADRAO, "neta": analise.CRITERIOS_NETA},
        "criterio_personalizado": bool(cfg.get("criterios")),
        "niveis": analise.NIVEIS,
        "componentes": _componentes(),
        "componentes_padrao": referencias.COMPONENTES_PADRAO,
        "pasta_dados": str(PASTA_DADOS),
        "pasta_modelos": str(PASTA_MODELOS),
        "versao": VERSAO,
    }


@app.put("/api/configuracoes")
def salvar_configuracoes(corpo: dict = Body(...)) -> dict:
    cfg = _config()
    if "empresa" in corpo:
        cfg["empresa"] = {k: str(corpo["empresa"].get(k, ""))[:120] for k in ("nome", "subtitulo")}
    if "responsavel" in corpo:
        cfg["responsavel"] = {k: str(corpo["responsavel"].get(k, ""))[:120] for k in ("nome", "registro")}
    if "tema" in corpo:
        if corpo["tema"] not in ("sistema", "claro", "escuro"):
            raise HTTPException(422, "Tema deve ser sistema, claro ou escuro.")
        cfg["tema"] = corpo["tema"]
    if "criterio" in corpo:
        cfg["criterios"] = None if corpo["criterio"] is None else _validar_criterios(corpo["criterio"])
    if "componentes" in corpo:
        cfg["componentes"] = {} if corpo["componentes"] is None else _validar_componentes(corpo["componentes"])
    _salvar_config(cfg)
    if "criterio" in corpo or "componentes" in corpo:
        _recalcular_todas()
    return configuracoes()


def _recalcular_todas() -> None:
    """Critério novo: a severidade guardada de cada inspeção é refeita."""
    with _trava:
        for item in armazenamento.listar():
            a, m = armazenamento.obter(item["id"]), armazenamento.matriz(item["id"])
            if a is not None and m is not None:
                armazenamento.salvar(_calcular(a, m))


# ---------------------------------------------------------------- ciclo de vida (janela do aplicativo)

sinais: dict = {"clientes": {}, "algum": False, "encerrar": False}


@app.post("/api/sinal")
def sinal(cliente: str = "lancador", saindo: bool = False) -> dict:
    """Cada janela avisa que está aberta (a cada 20 s) ou que está sendo fechada."""
    clientes = sinais["clientes"]
    if saindo:
        clientes.pop(cliente[:32], None)
    else:
        clientes[cliente[:32]] = time.time()
        sinais["algum"] = True
    return {"ok": True, "janelas": len(clientes)}


@app.post("/api/encerrar")
def encerrar() -> dict:
    sinais["encerrar"] = True
    return {"ok": True}


@app.get("/api/paletas")
def paletas() -> dict:
    return {nome: render.tabela(nome).tolist() for nome in render.PALETAS}


@app.exception_handler(HTTPException)
async def erro_http(_req, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"erro": exc.detail}, status_code=exc.status_code)


@app.middleware("http")
async def sem_cache_da_interface(request, chamar_proximo):
    """A interface é local: sempre servir a versão mais nova dos arquivos (atualizações entram sem limpar cache)."""
    resposta = await chamar_proximo(request)
    if not request.url.path.startswith("/api/"):
        resposta.headers["Cache-Control"] = "no-cache"
    return resposta


app.mount("/", StaticFiles(directory=PASTA_APP / "estatico", html=True), name="estatico")
