"""Servidor do Pyron: API e interface web, rodando só no computador do usuário.

Iniciar:  Pyron.exe na área de trabalho, ou  python -m app.iniciar --janela
"""

from __future__ import annotations

import base64
import csv
import io
import json
import os
import re
import threading
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from time import perf_counter

import numpy as np
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from app import avaliacoes as avaliacoes_mod
from app import equipamentos
from app import laudo, monitoramento, pendencias
from app import treinos as treinos_mod
from app import videos as videos_mod
from app.armazenamento import Armazenamento, _destaque
from nucleo import analise, detectores, entrada, referencias, render, video

VERSAO = "0.7.0"
RAIZ = Path(__file__).resolve().parents[1]
PASTA_APP = Path(__file__).resolve().parent
# PYRON_DADOS (ou app.iniciar --dados) aponta outra pasta: demonstrações e testes sem tocar nas inspeções reais.
PASTA_DADOS = Path(os.environ.get("PYRON_DADOS") or PASTA_APP / "dados_app")
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

@asynccontextmanager
async def _ciclo_de_vida(_app):
    """Ao subir, retoma o monitoramento que estava ligado; ao descer, para a thread da pasta vigiada."""
    if _config()["monitoramento"].get("ativo"):
        monitor.iniciar()
    yield
    monitor.parar()


app = FastAPI(title="Pyron", version=VERSAO, lifespan=_ciclo_de_vida)
armazenamento = Armazenamento(PASTA_DADOS)
_trava = threading.Lock()


ocr = entrada.OCRPreguicoso()


# ---------------------------------------------------------------- configuração

CONFIG_PADRAO = {
    "modelo_ativo": "pontos-quentes",
    "empresa": {"nome": "", "subtitulo": ""},
    "responsavel": {"nome": "", "registro": ""},  # formato antigo (um só); migra para "responsaveis"
    "responsaveis": [],  # [{"id", "nome", "funcao", "registro"}]: o laudo só aceita quem está aqui
    "responsavel_padrao": None,
    "tema": "claro",
    "criterios": None,  # None: critério padrão (modelo brasileiro, NBR 15866)
    "componentes": {},  # trocas do usuário na biblioteca de componentes (MTA por classe)
    "monitoramento": dict(monitoramento.PADRAO),
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
    antigo = cfg.get("responsavel") or {}
    if not cfg["responsaveis"] and (antigo.get("nome") or "").strip():  # migração do responsável único
        cfg["responsaveis"] = [{"id": "r1", "nome": antigo["nome"].strip(), "funcao": "", "registro": (antigo.get("registro") or "").strip()}]
        cfg["responsavel_padrao"] = "r1"
    return cfg


def _responsavel(id_: str | None) -> dict | None:
    """Responsável técnico cadastrado (o padrão, se ``id_`` vier vazio)."""
    cfg = _config()
    lista = cfg["responsaveis"]
    escolhido = id_ or cfg.get("responsavel_padrao")
    return next((r for r in lista if r["id"] == escolhido), None)


def _validar_responsaveis(lista) -> list[dict]:
    if not isinstance(lista, list) or len(lista) > 50:
        raise HTTPException(422, "Lista de responsáveis inválida.")
    saida, ids = [], set()
    for i, r in enumerate(lista, start=1):
        nome = str(r.get("nome", "")).strip()[:120]
        registro = str(r.get("registro", "")).strip()[:60]
        if not nome or not registro:
            raise HTTPException(422, f"Responsável {i}: preencha o nome e o registro profissional.")
        id_ = str(r.get("id") or "").strip()[:12]
        if not re.fullmatch(r"[a-z0-9]{1,12}", id_) or id_ in ids:
            id_ = uuid.uuid4().hex[:8]
        ids.add(id_)
        saida.append({"id": id_, "nome": nome, "funcao": str(r.get("funcao", "")).strip()[:80], "registro": registro})
    return saida


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


def _regioes_do_detector(det: detectores.Detector, matriz: np.ndarray, imagem: np.ndarray | None = None) -> list[dict]:
    contagem: dict[str, int] = {}
    regioes = []
    for d in det.detectar(matriz, imagem):
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
    campos_med = ("id", "tipo", "x", "y", "x0", "y0", "x1", "y1")
    a["medicoes"] = analise.medir_medicoes(matriz, [{k: v for k, v in m.items() if k in campos_med} for m in a.get("medicoes", [])])
    return a


PALETAS_EXIBICAO = ("ferro", "arco-iris", "cinza")
PARAMETROS = {  # nome: (mínimo, máximo, rótulo) dos parâmetros de medição que o usuário pode trocar
    "emissividade": (0.05, 1.0, "Emissividade"),
    "temp_refletida_c": (-50.0, 300.0, "Temperatura refletida"),
    "distancia_m": (0.1, 1000.0, "Distância"),
    "umidade_relativa": (0.0, 1.0, "Umidade relativa"),
    "temp_atmosfera_c": (-50.0, 60.0, "Temperatura do ar"),
}


def _validar_medicoes(lista, matriz: np.ndarray) -> list[dict]:
    if not isinstance(lista, list) or len(lista) > 40:
        raise HTTPException(422, "Até 40 pontos e linhas por imagem.")
    h, w = matriz.shape
    saida = []
    for m in lista:
        tipo = m.get("tipo")
        try:
            if tipo == "ponto":
                item = {"tipo": "ponto", "x": float(np.clip(float(m["x"]), 0, w - 0.01)), "y": float(np.clip(float(m["y"]), 0, h - 0.01))}
            elif tipo == "linha":
                item = {"tipo": "linha", **{k: float(np.clip(float(m[k]), 0, (w if k[0] == "x" else h) - 0.01)) for k in ("x0", "y0", "x1", "y1")}}
            else:
                continue
        except (KeyError, TypeError, ValueError) as erro:
            raise HTTPException(422, "Ponto ou linha com coordenadas inválidas.") from erro
        item["id"] = str(m.get("id") or uuid.uuid4().hex[:8])[:12]
        saida.append(item)
    return saida


def _nova_analise(dados: bytes, nome: str, modelo: str | None, fonte: str = "manual", identificacao: dict | None = None,
                  limites: tuple[float, float] | None = None) -> dict:
    t0 = perf_counter()
    try:
        img = entrada.carregar(dados, ocr=ocr, limites=limites)
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro
    t1 = perf_counter()
    det = _detector(modelo)
    try:
        regioes = _regioes_do_detector(det, img.temperatura_c, img.exibida_rgb)
    except ValueError as erro:
        raise HTTPException(422, f"O modelo {det.nome} falhou: {erro}") from erro
    t2 = perf_counter()
    lo, hi = render.faixa_exibicao(img.temperatura_c)
    resp = _responsavel(None)
    a = {
        "id": uuid.uuid4().hex,
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "arquivo": nome,
        "fonte": fonte,
        "radiometrica": img.radiometrica,
        "origem": img.origem,
        "metadados": img.metadados,
        "modelo": _info_modelo(det),
        "condicoes": {"ambiente_c": None, "carga_pct": None},
        "identificacao": {
            **({"responsavel_id": resp["id"]} if resp else {}),
            **(identificacao or {}),
        },
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
    saida["equipamento_chave"] = _chave_de(a)
    if a.get("resumo", {}).get("severidade", "normal") != "normal":
        item = {**a, "destaque": _destaque(a), "data_captura": (a.get("metadados") or {}).get("data_hora", "")}
        saida["pendencia"] = pendencias.montar(item)
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
async def criar(arquivo: UploadFile = File(...), modelo: str | None = Form(None),
                instalacao: str | None = Form(None), equipamento: str | None = Form(None)) -> dict:
    """Analisa uma imagem; com instalação e equipamento, ela já entra no histórico dele."""
    dados = await arquivo.read()
    if not dados:
        raise HTTPException(422, "O arquivo está vazio.")
    ident = {k: v.strip()[:120] for k, v in (("instalacao", instalacao), ("equipamento", equipamento)) if v and v.strip()}
    with _trava:
        return _completa(_nova_analise(dados, arquivo.filename or "imagem.jpg", modelo, identificacao=ident))


def _chave_de(a: dict) -> str:
    ident = a.get("identificacao") or {}
    return equipamentos.chave(ident.get("instalacao"), ident.get("equipamento"))


@app.get("/api/analises")
def listar() -> list[dict]:
    itens = armazenamento.listar()
    for it in itens:
        it["equipamento_chave"] = _chave_de(it)
    return itens


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
    if "medicoes" in corpo:
        a["medicoes"] = _validar_medicoes(corpo["medicoes"], m)
    if "exibicao" in corpo:  # paleta e escala escolhidas na tela: o laudo e a imagem exportada saem iguais
        e = corpo["exibicao"] or {}
        faixa = e.get("faixa")
        if faixa is not None:
            faixa = sorted(float(v) for v in faixa)[:2]
            if len(faixa) != 2 or faixa[1] - faixa[0] < 0.1:
                raise HTTPException(422, "Escala inválida: o máximo precisa ser maior que o mínimo.")
        a["exibicao"] = {"paleta": e.get("paleta") if e.get("paleta") in PALETAS_EXIBICAO else "ferro", "faixa": faixa}
    _calcular(a, m)
    armazenamento.salvar(a)
    return _completa(a)


@app.post("/api/analises/identificacao")
def identificar_varias(corpo: dict = Body(...)) -> dict:
    """Define instalação e equipamento de várias inspeções de uma vez (o resto da identificação fica)."""
    ids = corpo.get("ids") or []
    if not isinstance(ids, list) or not ids or len(ids) > 500:
        raise HTTPException(422, "Selecione de 1 a 500 inspeções.")
    instalacao = str(corpo.get("instalacao") or "").strip()[:120]
    equipamento = str(corpo.get("equipamento") or "").strip()[:120]
    if not equipamento:
        raise HTTPException(422, "Informe o equipamento.")
    with _trava:
        analises = [armazenamento.obter(str(i)) for i in ids]
        if any(a is None for a in analises):
            raise HTTPException(404, "Alguma inspeção selecionada não existe mais.")
        for a in analises:
            a["identificacao"] = {**(a.get("identificacao") or {}), "instalacao": instalacao, "equipamento": equipamento}
            armazenamento.salvar(a)
    return {"atualizadas": len(analises), "chave": equipamentos.chave(instalacao, equipamento)}


@app.post("/api/analises/{id_}/detectar")
def detectar_de_novo(id_: str, corpo: dict = Body(default={})) -> dict:
    a, m = _carregar(id_)
    det = _detector(corpo.get("modelo"))
    manuais = [r for r in a["regioes"] if r.get("origem") == "manual"]
    imagem = None
    if det.precisa_imagem:  # modelo que olha a imagem colorida: reabre o JPEG original guardado
        original = armazenamento.original(id_)
        if original is None:
            raise HTTPException(422, f"O modelo {det.nome} precisa da imagem original, que não está guardada nesta inspeção.")
        imagem = entrada.carregar(original, ocr=ocr).exibida_rgb
    try:
        a["regioes"] = manuais + _regioes_do_detector(det, m, imagem)
    except ValueError as erro:
        raise HTTPException(422, f"O modelo {det.nome} falhou: {erro}") from erro
    a["modelo"] = _info_modelo(det)
    _calcular(a, m)
    armazenamento.salvar(a)
    return _completa(a)


@app.post("/api/analises/{id_}/parametros")
def ajustar_parametros(id_: str, corpo: dict = Body(...)) -> dict:
    """Recalcula a temperatura com outra emissividade, distância, temperaturas ou umidade.

    Parte sempre do JPEG radiométrico original, então dá para voltar aos valores da câmera
    (``{"restaurar": true}``). As regiões ficam onde estão e são medidas de novo.
    """
    a, _ = _carregar(id_)
    if not a.get("radiometrica"):
        raise HTTPException(422, "Só termogramas radiométricos têm emissividade e distância para ajustar.")
    original = armazenamento.original(id_)
    if original is None:
        raise HTTPException(422, "O arquivo original desta inspeção não está guardado.")
    ajustes: dict[str, float] = {}
    if not corpo.get("restaurar"):
        for nome, (lo, hi, rotulo) in PARAMETROS.items():
            v = corpo.get(nome)
            if v in (None, ""):
                continue
            try:
                v = float(v)
            except (TypeError, ValueError) as erro:
                raise HTTPException(422, f"{rotulo}: informe um número.") from erro
            if nome == "umidade_relativa" and v > 1:
                v /= 100  # aceita em %
            if not lo <= v <= hi:
                raise HTTPException(422, f"{rotulo} fora da faixa aceita.")
            ajustes[nome] = v
    try:
        img = entrada.carregar(original, ocr=ocr, ajustes=ajustes)
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro
    a["metadados"] = {**a.get("metadados", {}), **img.metadados}
    if ajustes:
        a["parametros_ajustados"] = sorted(ajustes)
    else:
        a.pop("parametros_ajustados", None)
    lo, hi = render.faixa_exibicao(img.temperatura_c)
    a["matriz_info"] = {**a.get("matriz_info", {}), "faixa_exibicao": [lo, hi]}
    with _trava:
        _calcular(a, img.temperatura_c)
        armazenamento.salvar(a, matriz=img.temperatura_c)
    return _completa(a)


def _nome_exportado(a: dict, sufixo: str) -> str:
    base = re.sub(r"[^\w.-]+", "_", Path(a["arquivo"]).stem, flags=re.UNICODE).strip("_") or "inspecao"
    return f"{base}_{sufixo}"


@app.get("/api/analises/{id_}/imagem.png")
def exportar_imagem(id_: str, largura: int = 1280) -> Response:
    """Termograma com as regiões, pontos e linhas, na paleta e na escala escolhidas na tela."""
    a, m = _carregar(id_)
    _calcular(a, m)
    exib = a.get("exibicao") or {}
    img = render.desenhar(m, a["regioes"], largura=max(320, min(largura, 3840)), nome=exib.get("paleta") or "ferro",
                          medicoes=a.get("medicoes"), faixa=tuple(exib["faixa"]) if exib.get("faixa") else None)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"Content-Disposition": f'attachment; filename="{_nome_exportado(a, "termograma.png")}"'})


def _csv_excel(linhas: list[list], nome: str) -> Response:
    """CSV como o Excel em português abre direto: ponto e vírgula, vírgula decimal e BOM."""
    buf = io.StringIO()
    escritor = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    for linha in linhas:
        escritor.writerow(["" if v is None else (f"{v:.2f}".replace(".", ",") if isinstance(v, float) else v) for v in linha])
    return Response(("\ufeff" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@app.get("/api/analises/{id_}/temperaturas.csv")
def exportar_temperaturas(id_: str) -> Response:
    """A matriz de temperatura inteira (°C), uma linha por linha da imagem."""
    a, m = _carregar(id_)
    linhas = [["y / x", *range(m.shape[1])]]
    linhas += [[y, *(float(v) if np.isfinite(v) else None for v in m[y])] for y in range(m.shape[0])]
    return _csv_excel(linhas, _nome_exportado(a, "temperaturas.csv"))


@app.get("/api/inspecoes.csv")
def exportar_inspecoes() -> Response:
    """Lista de inspeções para planilha: equipamento, data, severidade e a região que decide."""
    linhas = [["Data da captura", "Arquivo", "Instalação", "Equipamento", "Severidade", "Região crítica", "Tmáx (°C)",
               "% da MTA", "ΔT (°C)", "Temperatura", "Detector"]]
    for it in armazenamento.listar():
        d, ident, r = it.get("destaque") or {}, it.get("identificacao") or {}, it["resumo"]
        linhas.append([it.get("data_captura") or it["criado_em"].replace("T", " "), it["arquivo"], ident.get("instalacao", ""),
                       ident.get("equipamento", ""), r.get("severidade_rotulo", r["severidade"]), d.get("nome", ""),
                       d.get("t_max"), d.get("pct_mta"), d.get("dt"), "medida" if it["radiometrica"] else "estimada", it["modelo"]])
    return _csv_excel(linhas, f"inspecoes_{datetime.now():%Y%m%d}.csv")


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


def _escolher_responsavel(id_: str | None, a: dict | None = None) -> dict:
    """Só sai laudo com responsável do cadastro: nome e registro nunca são digitados na hora."""
    escolhido = id_ or ((a or {}).get("identificacao") or {}).get("responsavel_id")
    resp = _responsavel(escolhido)
    if resp is None:
        raise HTTPException(422, "Escolha o responsável técnico. Se ainda não houver, cadastre em Configurações › Empresa e responsáveis.")
    return resp


@app.get("/api/analises/{id_}/laudo.pdf")
def laudo_pdf(id_: str, responsavel: str | None = None, art: str | None = None) -> Response:
    a, m = _carregar(id_)
    resp = _escolher_responsavel(responsavel, a)
    art = (art if art is not None else (a.get("identificacao") or {}).get("art")) or ""
    pdf = laudo.gerar(a, m, armazenamento.foto(id_), VERSAO, empresa=_config()["empresa"], responsavel=resp, art=art[:60],
                      criterios=_criterios(), logo=_logo())
    nome = f"relatorio_{re.sub(r'[^A-Za-z0-9_-]', '_', Path(a['arquivo']).stem)}_{a['id'][:6]}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nome}"'})


@app.post("/api/laudos")
def laudo_varias(corpo: dict = Body(...)) -> Response:
    """Um relatório com várias inspeções, na ordem escolhida."""
    ids = corpo.get("ids")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(422, "Selecione ao menos uma inspeção.")
    if len(ids) > 60:
        raise HTTPException(422, "Selecione no máximo 60 inspeções por relatório.")
    itens = []
    for id_ in dict.fromkeys(str(i) for i in ids):
        a, m = _carregar(id_)
        itens.append((a, m, armazenamento.foto(id_)))
    resp = _escolher_responsavel(corpo.get("responsavel"))
    pdf = laudo.gerar_relatorio(itens, VERSAO, empresa=_config()["empresa"], responsavel=resp,
                                art=str(corpo.get("art") or "")[:60], criterios=_criterios(), logo=_logo())
    nome = f"relatorio_termografico_{datetime.now():%Y%m%d_%H%M}_{len(itens)}_imagens.pdf"
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
        "responsaveis": cfg["responsaveis"],
        "responsavel_padrao": cfg.get("responsavel_padrao"),
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
        "tem_logo": (PASTA_DADOS / "logo.png").exists(),
    }


def _logo() -> bytes | None:
    arq = PASTA_DADOS / "logo.png"
    return arq.read_bytes() if arq.exists() else None


@app.post("/api/configuracoes/logo")
async def enviar_logo(arquivo: UploadFile = File(...)) -> dict:
    """Logotipo da empresa para o cabeçalho do laudo (guardado em PNG, até 800 px de largura)."""
    dados = await arquivo.read()
    if len(dados) > 5 * 1024 * 1024:
        raise HTTPException(422, "Logotipo maior que 5 MB.")
    try:
        img = Image.open(io.BytesIO(dados))
        img.load()
    except OSError as erro:
        raise HTTPException(422, "Não consegui abrir o arquivo como imagem. Envie PNG ou JPEG.") from erro
    img = img.convert("RGBA")
    if img.width > 800:
        img = img.resize((800, round(img.height * 800 / img.width)), Image.LANCZOS)
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    img.save(PASTA_DADOS / "logo.png", format="PNG")
    return {"ok": True, "largura": img.width, "altura": img.height}


@app.get("/api/configuracoes/logo.png")
def ver_logo() -> Response:
    dados = _logo()
    if dados is None:
        raise HTTPException(404, "Nenhum logotipo enviado.")
    return Response(dados, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.delete("/api/configuracoes/logo")
def apagar_logo() -> dict:
    (PASTA_DADOS / "logo.png").unlink(missing_ok=True)
    return {"ok": True}


@app.put("/api/configuracoes")
def salvar_configuracoes(corpo: dict = Body(...)) -> dict:
    cfg = _config()
    if "empresa" in corpo:
        cfg["empresa"] = {k: str(corpo["empresa"].get(k, ""))[:120] for k in ("nome", "subtitulo")}
    if "responsaveis" in corpo:
        cfg["responsaveis"] = _validar_responsaveis(corpo["responsaveis"])
        cfg["responsavel"] = {"nome": "", "registro": ""}  # o formato antigo não volta a migrar
        ids = [r["id"] for r in cfg["responsaveis"]]
        if cfg.get("responsavel_padrao") not in ids:
            cfg["responsavel_padrao"] = ids[0] if ids else None
    if "responsavel_padrao" in corpo:
        ids = [r["id"] for r in cfg["responsaveis"]]
        if corpo["responsavel_padrao"] not in ids:
            raise HTTPException(422, "Responsável padrão não está no cadastro.")
        cfg["responsavel_padrao"] = corpo["responsavel_padrao"]
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


# ---------------------------------------------------------------- rotas: monitoramento e alertas


def _analisar_do_monitor(dados: bytes, nome: str, identificacao: dict) -> dict:
    with _trava:
        return _nova_analise(dados, nome, None, fonte="monitoramento", identificacao=identificacao)


monitor = monitoramento.Monitor(
    analisar=_analisar_do_monitor,
    configuracao=lambda: _config()["monitoramento"],
    salvar_alerta=lambda alerta: armazenamento.salvar_alerta(alerta),
    alertas_recentes=lambda: armazenamento.alertas(50),
    pasta_estado=lambda: PASTA_DADOS,
)


def _estado_monitor() -> dict:
    cfg = _config()["monitoramento"]
    return {**monitor.estado, "ativo": bool(cfg.get("ativo")), "pasta": cfg.get("pasta", "")}


@app.get("/api/status")
def status() -> dict:
    """Barra superior: servidor, monitoramento e alertas pendentes, num pedido só."""
    pendentes = sum(1 for a in armazenamento.alertas() if a["status"] == "pendente")
    andando = treinos.em_andamento()
    treino = {k: andando.get(k) for k in ("id", "nome", "etapa", "percentual", "mensagem")} if andando else None
    return {"versao": VERSAO, "monitoramento": _estado_monitor(), "alertas_pendentes": pendentes, "treino": treino}


@app.get("/api/monitoramento")
def obter_monitoramento() -> dict:
    return {"config": _config()["monitoramento"], "estado": _estado_monitor(), "disponivel": monitoramento.DISPONIVEL}


@app.put("/api/monitoramento")
def salvar_monitoramento(corpo: dict = Body(...)) -> dict:
    cfg = _config()
    anterior = cfg["monitoramento"]
    try:
        novo = monitoramento.validar({**anterior, **corpo})
    except monitoramento.ConfiguracaoInvalida as erro:
        raise HTTPException(422, str(erro)) from erro
    ligando = novo["ativo"] and (not anterior.get("ativo") or novo["pasta"] != anterior.get("pasta"))
    cfg["monitoramento"] = novo
    _salvar_config(cfg)
    if ligando:
        monitor.linha_de_base(novo["pasta"], novo.get("subpastas", False))  # só o que chegar a partir de agora
    if novo["ativo"]:
        monitor.iniciar()
    else:
        monitor.parar()
    return obter_monitoramento()


@app.post("/api/monitoramento/verificar")
def verificar_agora() -> dict:
    if not _config()["monitoramento"].get("pasta"):
        raise HTTPException(422, "Configure a pasta monitorada primeiro.")
    novas = monitor.verificar()
    return {"novas": len(novas), "estado": _estado_monitor()}


@app.get("/api/monitoramento/previa")
def previa_mensagem() -> dict:
    """Como a mensagem vai chegar no WhatsApp, usando a inspeção mais grave salva."""
    cfg = _config()["monitoramento"]
    itens = armazenamento.listar()
    if not itens:
        return {"mensagem": None}
    ordem = list(analise.NIVEIS)
    pior = max(itens, key=lambda it: (ordem.index(it["resumo"]["severidade"]), it["criado_em"]))
    a = armazenamento.obter(pior["id"])
    return {"mensagem": monitoramento.mensagem(a, cfg), "arquivo": a["arquivo"]}


@app.get("/api/alertas")
def listar_alertas() -> dict:
    itens = armazenamento.alertas()
    return {"alertas": itens, "pendentes": sum(1 for a in itens if a["status"] == "pendente")}


@app.put("/api/alertas/{id_}")
def atualizar_alerta(id_: str, corpo: dict = Body(...)) -> dict:
    alerta = armazenamento.alerta(id_)
    if alerta is None:
        raise HTTPException(404, "Alerta não encontrado.")
    if corpo.get("status") not in ("pendente", "enviado", "resolvido"):
        raise HTTPException(422, "Status deve ser pendente, enviado ou resolvido.")
    alerta["status"] = corpo["status"]
    alerta["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
    armazenamento.salvar_alerta(alerta)
    return alerta


# ---------------------------------------------------------------- rotas: treino de modelos

treinos = treinos_mod.Treinos(RAIZ, pasta_dados=lambda: PASTA_DADOS, pasta_modelos=lambda: PASTA_MODELOS)


def _sugestao(relatorio: dict) -> dict:
    classes = [c["classe"] for c in relatorio["classes"]]
    nome = "Para-raios" if any("para" in c and "raio" in c for c in classes) else (relatorio["classes"][0]["nome"] if classes else "Modelo")
    return {"nome": nome, "id": f"{treinos_mod.slug(nome)}-{datetime.now():%Y%m%d-%H%M}", "epocas": 60,
            "divisao": "sessao"}


@app.post("/api/treinos/rotulos")
def enviar_rotulos(arquivos: list[UploadFile] = File(...)) -> dict:
    """Recebe o .zip do CVAT ou os .json de anotação (um por parte), guarda em dados/rotulos e devolve o relatório."""
    from ml import dados as ml_dados  # só numpy/PIL: não carrega o PyTorch

    if len(arquivos) == 1:
        conteudo, nome = arquivos[0].file.read(), arquivos[0].filename or "rotulos.zip"
    else:  # vários .json (treino, validação, teste): viram um .zip igual ao que o CVAT exporta
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for a in arquivos:
                if not (a.filename or "").lower().endswith(".json"):
                    raise HTTPException(422, "Envie um .zip ou os arquivos .json de anotação do CVAT.")
                z.writestr(f"annotations/{Path(a.filename).name}", a.file.read())
        conteudo, nome = buf.getvalue(), "anotacoes_cvat.zip"
    if not conteudo:
        raise HTTPException(422, "O arquivo está vazio.")
    caminho = treinos.guardar_rotulos(conteudo, nome)
    try:
        relatorio = ml_dados.analisar(caminho, treinos.pasta_imagens)
    except (ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as erro:
        caminho.unlink(missing_ok=True)
        raise HTTPException(422, f"Não consegui ler os rótulos: {erro}. Exporte do CVAT em COCO 1.0.") from erro
    return {"arquivo": caminho.name, "relatorio": relatorio, "sugestao": _sugestao(relatorio)}


@app.get("/api/treinos")
def listar_treinos() -> dict:
    return {"treinos": treinos.listar()}


@app.get("/api/treinos/ambiente")
def ambiente_de_treino(forcar: bool = False) -> dict:
    """O PyTorch carrega neste computador? (O Controle Inteligente de Aplicativos do Windows pode bloquear.)"""
    return treinos.verificar_ambiente(forcar)


@app.post("/api/treinos/pacote")
def pacote_de_treino(corpo: dict = Body(...)) -> Response:
    """Pacote para treinar fora (Colab, supercomputador): código, rótulos, imagens e caderno."""
    try:
        arquivo = treinos.arquivo_rotulos(str(corpo.get("arquivo", "")))
        id_ = str(corpo.get("id", "")).strip()
        if not treinos_mod.ID_VALIDO.fullmatch(id_):
            raise ValueError("Identificador inválido: use letras minúsculas, números e hífen.")
        caminho = treinos.montar_pacote(arquivo, id_, str(corpo.get("nome") or "Modelo")[:80], int(corpo.get("epocas", 60)), str(corpo.get("divisao", "sessao")))
    except FileNotFoundError as erro:
        raise HTTPException(404, str(erro)) from erro
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro
    return Response(caminho.read_bytes(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{caminho.name}"'})


@app.post("/api/modelos/instalar")
def instalar_modelo(arquivo: UploadFile = File(...)) -> dict:
    """Instala um modelo treinado fora (o .zip da pasta modelos/<id>)."""
    try:
        id_ = treinos.instalar_modelo(arquivo.file.read())
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro
    return {"id": id_, **modelos()}


@app.post("/api/treinos")
def iniciar_treino(corpo: dict = Body(...)) -> dict:
    try:
        arquivo = treinos.arquivo_rotulos(str(corpo.get("arquivo", "")))
        return treinos.iniciar(arquivo, str(corpo.get("id", "")).strip(), str(corpo.get("nome", "")).strip()[:80] or "Modelo",
                               int(corpo.get("epocas", 60)), str(corpo.get("divisao", "sessao")))
    except FileNotFoundError as erro:
        raise HTTPException(404, str(erro)) from erro
    except (ValueError, RuntimeError) as erro:
        raise HTTPException(422, str(erro)) from erro


@app.get("/api/treinos/{id_}")
def obter_treino(id_: str) -> dict:
    try:
        return {**treinos.obter(id_), "registro": treinos.registro(id_)}
    except FileNotFoundError as erro:
        raise HTTPException(404, str(erro)) from erro


@app.post("/api/treinos/{id_}/cancelar")
def cancelar_treino(id_: str) -> dict:
    try:
        return treinos.cancelar(id_)
    except FileNotFoundError as erro:
        raise HTTPException(404, str(erro)) from erro


@app.get("/api/treinos/{id_}/previsoes.png")
def previsoes_treino(id_: str) -> Response:
    if not treinos_mod.ID_VALIDO.fullmatch(id_):
        raise HTTPException(400, "Identificador inválido.")
    arquivo = PASTA_MODELOS / id_ / "previsoes_teste.png"
    if not arquivo.exists():
        raise HTTPException(404, "Ainda não há imagem de previsões para este modelo.")
    return Response(arquivo.read_bytes(), media_type="image/png")


# ---------------------------------------------------------------- rotas: avaliação de modelos (resultados do Colab)

avaliacoes = avaliacoes_mod.Avaliacoes(lambda: PASTA_DADOS, treinos.instalar_modelo)


@app.get("/api/avaliacoes")
def listar_avaliacoes() -> list[dict]:
    return avaliacoes.listar()


@app.post("/api/avaliacoes")
async def importar_avaliacao(arquivo: UploadFile = File(...)) -> dict:
    """Recebe o resultados_comparacao.zip ou o pacote do modelo exportado pelo caderno do Colab."""
    dados = await arquivo.read()
    if not dados:
        raise HTTPException(422, "O arquivo está vazio.")
    try:
        return avaliacoes.importar(dados, arquivo.filename or "resultados.zip")
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro


@app.get("/api/avaliacoes/{id_}")
def obter_avaliacao(id_: str) -> dict:
    try:
        d = avaliacoes.obter(id_)
    except KeyError as erro:
        raise HTTPException(404, "Avaliação não encontrada.") from erro
    instalados = {m.id for m in detectores.listar(PASTA_MODELOS)}
    d["modelo_disponivel"] = d["meta"].get("modelo_instalado") in instalados
    d["modelo_ativo"] = _config()["modelo_ativo"]
    return d


@app.get("/api/avaliacoes/{id_}/arquivos/{nome}")
def arquivo_avaliacao(id_: str, nome: str) -> Response:
    try:
        caminho = avaliacoes.arquivo(id_, nome)
    except KeyError as erro:
        raise HTTPException(404, "Arquivo não encontrado.") from erro
    tipo = "image/png" if nome.endswith(".png") else "text/csv; charset=utf-8"
    return Response(caminho.read_bytes(), media_type=tipo)


@app.delete("/api/avaliacoes/{id_}")
def apagar_avaliacao(id_: str) -> dict:
    try:
        avaliacoes.apagar(id_)
    except KeyError as erro:
        raise HTTPException(404, "Avaliação não encontrada.") from erro
    return {"ok": True}


# ---------------------------------------------------------------- rotas: pendências (acompanhamento das anomalias)


@app.get("/api/pendencias")
def listar_pendencias() -> list[dict]:
    return pendencias.listar(armazenamento.listar())


@app.put("/api/analises/{id_}/acompanhamento")
def acompanhar(id_: str, corpo: dict = Body(...)) -> dict:
    """Situação da anomalia: aberta, programada (com OS), corrigida, verificada ou descartada."""
    with _trava:
        a = armazenamento.obter(id_)
        if a is None:
            raise HTTPException(404, "Inspeção não encontrada.")
        if a["resumo"]["severidade"] == "normal":
            raise HTTPException(422, "Esta inspeção está normal: não há anomalia para acompanhar.")
        try:
            pendencias.atualizar(a, corpo)
        except ValueError as erro:
            raise HTTPException(422, str(erro)) from erro
        armazenamento.salvar(a)
    return next(p for p in pendencias.listar(armazenamento.listar()) if p["id"] == id_)


# ---------------------------------------------------------------- rotas: equipamentos (histórico e tendência)


@app.get("/api/equipamentos")
def listar_equipamentos() -> list[dict]:
    return equipamentos.listar(armazenamento.listar())


@app.get("/api/equipamentos/{chave}")
def obter_equipamento(chave: str) -> dict:
    itens = [it for it in armazenamento.listar() if _chave_de(it) == chave]
    if not itens:
        raise HTTPException(404, "Equipamento não encontrado.")
    resumo = next(e for e in equipamentos.listar(itens))
    completas = [a for a in (armazenamento.obter(it["id"]) for it in itens) if a]
    return {**resumo, "componentes": equipamentos.componentes(completas),
            "lista": sorted(itens, key=lambda it: equipamentos.ponto(it)["data"], reverse=True),
            "prazos_dias": equipamentos.PRAZO_DIAS}


# ---------------------------------------------------------------- rotas: vídeo (simulação de câmera ao vivo)


def _regiao_do_quadro(r: dict) -> dict:
    m = r.get("medida") or {}
    item = {k: r.get(k) for k in ("nome", "classe", "caixa", "confianca", "severidade")}
    item.update(t_max=m.get("t_max"), x_max=m.get("x_max"), y_max=m.get("y_max"))
    if r.get("componente"):
        item["componente"] = r["componente"].get("nome")
    return item


def _preparar_video(opcoes: dict):
    """Detector, critério e termômetro de um vídeo; devolve a função que analisa cada quadro."""
    det = _detector(opcoes.get("modelo"))
    termometro = video.Termometro(entrada.OCRPreguicoso(), opcoes.get("limites"))  # OCR próprio: roda em outra thread
    criterios, componentes = _criterios(), _componentes()

    def analisar(rgb: np.ndarray, tempo_s: float) -> dict:
        t0 = perf_counter()
        m = termometro.medir(rgb, tempo_s)
        t1 = perf_counter()
        medida = m.temperatura_c is not None
        matriz = m.temperatura_c if medida else np.full((rgb.shape[0] // 2, rgb.shape[1] // 2), np.nan, np.float32)
        regioes = []
        if medida or det.precisa_imagem:
            try:
                regioes = _regioes_do_detector(det, matriz, rgb)
            except ValueError:
                regioes = []
        t2 = perf_counter()
        resumo = None
        if medida and regioes:
            regioes, resumo = analise.analisar_regioes(matriz, regioes, criterios=criterios, componentes=componentes)
        t3 = perf_counter()
        pq = (resumo or {}).get("ponto_mais_quente")
        finito = medida and bool(np.isfinite(matriz).any())
        return {
            "matriz": [int(matriz.shape[1]), int(matriz.shape[0])],
            "escala": list(m.escala) if m.escala else None,
            "fonte_escala": m.fonte,
            "saturado": m.saturado,
            "t_max": round(float(np.nanmax(matriz)), 1) if finito else None,
            "severidade": resumo["severidade"] if resumo else ("normal" if medida else None),
            "ponto_mais_quente": {"t_max": pq["t_max"], "x": pq["x"], "y": pq["y"], "componente": (pq.get("componente") or {}).get("nome")} if pq else None,
            "regioes": [_regiao_do_quadro(r) for r in regioes],
            "etapas_ms": {"temperatura": round((t1 - t0) * 1000), "deteccao": round((t2 - t1) * 1000), "medicao": round((t3 - t2) * 1000)},
        }

    return analisar, _info_modelo(det)


videos = videos_mod.Videos(lambda: PASTA_DADOS, _preparar_video)


@app.get("/api/videos")
def listar_videos() -> list[dict]:
    return videos.listar()


@app.post("/api/videos")
def enviar_video(
    arquivo: UploadFile = File(...),
    modo: str = Form("ao_vivo"),
    intervalo_s: float = Form(0.5),
    velocidade: float = Form(1.0),
    modelo: str = Form(""),
    t_min: str = Form(""),
    t_max: str = Form(""),
) -> dict:
    try:
        opcoes = videos_mod.opcoes_validas(modo, intervalo_s, velocidade, modelo or None, t_min, t_max)
        return videos.criar(arquivo.file, arquivo.filename or "video.mp4", opcoes)
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro


def _video(funcao, *args):
    try:
        return funcao(*args)
    except KeyError as erro:
        raise HTTPException(404, "Vídeo não encontrado.") from erro


@app.get("/api/videos/{id_}")
def obter_video(id_: str, desde: int = 0) -> dict:
    return _video(videos.obter, id_, desde)


@app.get("/api/videos/{id_}/quadros/{n}.jpg")
def imagem_quadro(id_: str, n: int) -> Response:
    caminho, _ = _video(videos.quadro, id_, n)
    return Response(caminho.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@app.post("/api/videos/{id_}/cancelar")
def cancelar_video(id_: str) -> dict:
    return _video(videos.cancelar, id_)


@app.delete("/api/videos/{id_}")
def apagar_video(id_: str) -> dict:
    _video(videos.apagar, id_)
    return {"ok": True}


@app.post("/api/videos/{id_}/quadros/{n}/inspecao")
def quadro_para_inspecao(id_: str, n: int) -> dict:
    """Guarda um quadro como inspeção comum, com a mesma escala que valeu no vídeo."""
    caminho, info = _video(videos.quadro, id_, n)
    e = _video(videos.obter, id_, 10**9)
    tempo = (info or {}).get("tempo_s") or 0.0
    nome = f"{Path(e['arquivo']).stem} {int(tempo // 60):02d}m{tempo % 60:04.1f}s.jpg"
    limites = tuple(info["escala"]) if info and info.get("escala") else None
    modelo = (e.get("modelo") or {}).get("id")
    with _trava:
        return _completa(_nova_analise(caminho.read_bytes(), nome, modelo, fonte="video", limites=limites))


@app.get("/api/alertas/{id_}/whatsapp")
def whatsapp_alerta(id_: str) -> dict:
    alerta = armazenamento.alerta(id_)
    if alerta is None:
        raise HTTPException(404, "Alerta não encontrado.")
    destinatarios = _config()["monitoramento"].get("destinatarios", [])
    return {"mensagem": alerta["mensagem"], "links": monitoramento.links_whatsapp(alerta["mensagem"], destinatarios)}


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
