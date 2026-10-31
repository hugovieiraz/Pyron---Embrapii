"""Servidor do Pyron: API e interface web, rodando só no computador do usuário.

Iniciar:  Pyron.exe na área de trabalho, ou  python -m app.iniciar --janela
"""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
import json
import mimetypes
import os
import re
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import perf_counter

import numpy as np
from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from app import acesso
from app import avaliacoes as avaliacoes_mod
from app import backup, celular
from app import equipamentos
from app import laudo, monitoramento, pendencias
from app import treinos as treinos_mod
from app import videos as videos_mod
from app.armazenamento import Armazenamento, _destaque
from nucleo import analise, barra, detectores, enquadrar, entrada, referencias, render, video
from nucleo.detectores import placa, provedores

VERSAO = "0.9.0"
# o tipo do manifest do aplicativo instalado (PWA) não depende do registro do Windows nem do Linux
mimetypes.add_type("application/manifest+json", ".webmanifest")
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
    """Ao subir, retoma o monitoramento que estava ligado; ao descer, para a thread da pasta vigiada.

    No modo servidor, não sobe sem um administrador com usuário e senha (ninguém conseguiria entrar).
    """
    if acesso.modo_servidor() and (falta := acesso.falta_para_servidor(_config()["responsaveis"])):
        raise RuntimeError(falta)
    if _config()["monitoramento"].get("ativo"):
        monitor.iniciar()
        _preaquecer()
    elif acesso.modo_servidor():
        _preaquecer()  # no servidor, o modelo já sobe na placa (o TensorRT monta o motor uma vez e guarda no cache)
    yield
    monitor.parar()


# Toda rota passa por acesso.verificar: no modo local não faz nada; no servidor, sessão e perfil (app/acesso.py).
app = FastAPI(title="Pyron", version=VERSAO, lifespan=_ciclo_de_vida, dependencies=[Depends(acesso.verificar)])
armazenamento = Armazenamento(PASTA_DADOS)
_trava = threading.Lock()
acesso.ligar(lambda: armazenamento, lambda: _config()["responsaveis"])


ocr = entrada.OCRPreguicoso()


# ---------------------------------------------------------------- configuração

CONFIG_PADRAO = {
    "modelo_ativo": "pontos-quentes",
    "empresa": {"nome": "", "subtitulo": ""},
    "responsavel": {"nome": "", "registro": ""},  # formato antigo (um só); migra para "responsaveis"
    # time operacional: [{"id", "nome", "perfil", "funcao", "registro", "email", "telefone", "assina", "alertas",
    #                     "usuario", "administrador", "senha_hash"}]; os três últimos são do modo servidor (app/acesso.py);
    # o laudo só aceita quem assina (com registro profissional), a pendência aceita qualquer um e o alerta
    # do monitor vai pelo WhatsApp a quem tem "alertas" (severidade a partir da qual recebe)
    "responsaveis": [],
    "responsavel_padrao": None,
    "tema": "claro",
    "criterios": None,  # None: critério padrão (modelo brasileiro, NBR 15866)
    "componentes": {},  # trocas do usuário na biblioteca de componentes (MTA por classe)
    "monitoramento": dict(monitoramento.PADRAO),
    # motor do laudo em PDF: "typst" (padrão desde a aprovação de 30/10/2026, app/laudo_typst.py) ou "reportlab"
    "laudo": {"motor": "typst"},
}
MOTORES_LAUDO = ("reportlab", "typst")


# o monitor lê o config na thread dele e a leitura pode gravar (migração): sem a trava, uma leitura no meio
# da gravação pega o arquivo pela metade e cai no padrão (monitor desligado)
_TRAVA_CONFIG = threading.RLock()


def _config() -> dict:
    with _TRAVA_CONFIG:
        return _ler_config()


def _ler_config() -> dict:
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
    cfg["responsaveis"] = [_membro(r) for r in cfg["responsaveis"]]
    if _migrar_destinatarios(cfg):
        _salvar_config(cfg)
    return cfg


PERFIS = ("engenheiro", "tecnico")
NIVEIS_ALERTA = ("atencao", "programar", "urgente", "imediato")


def _membro(r: dict) -> dict:
    """Completa um membro do time gravado antes do cadastro operacional (todos assinavam laudo)."""
    return {"perfil": "engenheiro", "email": "", "telefone": "", "assina": True, "alertas": None,
            "usuario": "", "administrador": False, "senha_hash": "", **r}


def _migrar_destinatarios(cfg: dict) -> bool:
    """Quem recebia pela lista própria da Pasta monitorada (formato antigo) passa a ser do time.

    Mesmo telefone: o membro passa a receber a partir do nível do monitor. Sem ninguém igual: entra como
    técnico que não assina laudo, para ninguém deixar de receber alerta. A lista antiga fica vazia.
    """
    mon = cfg.get("monitoramento") or {}
    antigos = mon.get("destinatarios") or []
    if not antigos:
        return False
    minima = mon.get("severidade_minima") or "urgente"
    for d in antigos:
        digitos = monitoramento.telefone_digitos(d.get("telefone"))
        if not digitos:
            continue
        membro = next((r for r in cfg["responsaveis"] if monitoramento.telefone_digitos(r.get("telefone")) == digitos), None)
        if membro is None:
            membro = _membro({"id": f"w{digitos[-11:]}", "nome": (d.get("nome") or "Responsável")[:120], "perfil": "tecnico",
                              "funcao": "", "registro": "", "telefone": d["telefone"], "assina": False})
            cfg["responsaveis"].append(membro)
        membro["alertas"] = membro.get("alertas") or minima
    mon["destinatarios"] = []
    return True


def _destinatarios(cfg: dict | None = None) -> list[dict]:
    """Quem do time recebe o alerta do monitor pelo WhatsApp, com o nível a partir do qual recebe."""
    cfg = cfg or _config()
    return [{"id": r["id"], "nome": r["nome"], "telefone": r["telefone"], "minima": r["alertas"]}
            for r in cfg["responsaveis"] if r.get("alertas") and monitoramento.telefone_digitos(r.get("telefone"))]


def _responsavel(id_: str | None) -> dict | None:
    """Responsável técnico que assina laudo (o padrão, se ``id_`` vier vazio)."""
    cfg = _config()
    lista = [r for r in cfg["responsaveis"] if r["assina"]]
    escolhido = id_ or cfg.get("responsavel_padrao")
    return next((r for r in lista if r["id"] == escolhido), None)


def _validar_responsaveis(lista, anteriores: list[dict] | None = None) -> list[dict]:
    """Confere o time vindo da tela. ``anteriores``: o time gravado, de onde vem a senha de quem não trocou."""
    if not isinstance(lista, list):
        raise HTTPException(422, "Lista do time inválida.")
    if len(lista) > acesso.LIMITE_TIME:
        raise HTTPException(422, f"O time tem no máximo {acesso.LIMITE_TIME} pessoas.")
    guardados = {r["id"]: r for r in anteriores or []}
    saida, ids, usuarios = [], set(), set()
    for i, r in enumerate(lista, start=1):
        nome = str(r.get("nome", "")).strip()[:120]
        registro = str(r.get("registro", "")).strip()[:60]
        assina = bool(r.get("assina", True))
        if not nome:
            raise HTTPException(422, f"Membro {i} do time: preencha o nome.")
        if assina and not registro:
            raise HTTPException(422, f"{nome}: quem assina laudo precisa do registro profissional (CREA ou CFT).")
        perfil = r.get("perfil") if r.get("perfil") in PERFIS else "tecnico"
        email = str(r.get("email", "")).strip()[:120]
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise HTTPException(422, f"{nome}: e-mail inválido.")
        telefone = re.sub(r"[^\d+() -]", "", str(r.get("telefone", "")))[:30].strip()
        alertas = r.get("alertas") or None
        if alertas is not None and alertas not in NIVEIS_ALERTA:
            raise HTTPException(422, f"{nome}: nível de alerta desconhecido.")
        if alertas and not 10 <= len(monitoramento.telefone_digitos(telefone)) <= 15:
            raise HTTPException(422, f"{nome}: para receber alertas pelo WhatsApp, informe o telefone com DDI e DDD, por exemplo +55 83 99999-0000.")
        id_ = str(r.get("id") or "").strip()[:12]
        if not re.fullmatch(r"[a-z0-9]{1,12}", id_) or id_ in ids:
            id_ = uuid.uuid4().hex[:8]
        ids.add(id_)
        try:
            conta = acesso.conta(r, guardados.get(id_), nome)
        except ValueError as erro:
            raise HTTPException(422, str(erro)) from erro
        if conta["usuario"] and conta["usuario"] in usuarios:
            raise HTTPException(422, f"{nome}: o usuário {conta['usuario']} já é de outra pessoa do time.")
        usuarios.add(conta["usuario"])
        saida.append({"id": id_, "nome": nome, "perfil": perfil, "funcao": str(r.get("funcao", "")).strip()[:80], "registro": registro,
                      "email": email, "telefone": telefone, "assina": assina, "alertas": alertas, **conta})
    return saida


def _salvar_config(cfg: dict) -> None:
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    with _TRAVA_CONFIG:
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
            if nivel not in analise.NIVEIS or nivel in analise.SEM_CLASSIFICACAO:
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


def _modelo_termico() -> str:
    """O modelo térmico das análises sem modelo pedido: sempre para-raios + pontos quentes quando há um treinado.

    Vale o combinado do config (inclusive a versão rápida INT8 escolhida), o combinado do treinado do config ou o
    primeiro combinado instalado (o normal antes do INT8). Sem modelo treinado, só os pontos quentes. Desde
    31/10/2026 a tela não oferece mais a regra sozinha, o SAM 2 nem o treinado sem os pontos quentes.
    """
    cfg = _config()["modelo_ativo"]
    lista = detectores.listar(PASTA_MODELOS)
    por_id = {det.id: det for det in lista}
    combinados = [det for det in lista if isinstance(det, detectores.Combinado)]
    if cfg in por_id and isinstance(por_id[cfg], detectores.Combinado):
        return cfg
    combinado_cfg = f"{cfg}+pontos-quentes"
    if combinado_cfg in por_id:
        return combinado_cfg
    if combinados:
        recomendados = [det for det in combinados if not (det.partes[0].cartao.get("otimizacao"))]
        return (recomendados or combinados)[0].id
    return cfg if cfg in por_id else "pontos-quentes"  # o SAM 2 + DINOv2 não fica como padrão: leva minutos por imagem


def _detector(id_: str | None) -> detectores.Detector:
    try:
        return detectores.obter(id_ or _modelo_termico(), PASTA_MODELOS)
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


def _regioes_do_detector(det: detectores.Detector, matriz: np.ndarray, imagem: np.ndarray | None = None, metadados: dict | None = None) -> list[dict]:
    if hasattr(det, "detectar_com_metrologia"):
        regioes = det.detectar_com_metrologia(matriz, imagem, metadados=metadados)
        for r in regioes:
            if not r.get("id"):
                r["id"] = uuid.uuid4().hex[:8]
        return regioes

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
    campos = ("id", "nome", "classe", "caixa", "confianca", "origem", "segmentacao", "classificacao_dinov2")
    base = [{k: v for k, v in r.items() if k in campos} for r in a["regioes"]]
    a["regioes"], a["resumo"] = analise.analisar_regioes(
        matriz, base, cond.get("ambiente_c"), cond.get("carga_pct"), criterios=_criterios(), componentes=_componentes()
    )
    # notas da própria análise (modelo trocado, SAM 2 sob demanda): o resumo é refeito a cada abertura
    a["resumo"]["avisos"].extend(a.get("avisos_analise", []))
    campos_med = ("id", "tipo", "x", "y", "x0", "y0", "x1", "y1")
    a["medicoes"] = analise.medir_medicoes(matriz, [{k: v for k, v in m.items() if k in campos_med} for m in a.get("medicoes", [])])
    return a


def _remover_pontos_quentes_sem_anomalia(a: dict, matriz: np.ndarray) -> None:
    """Tira as caixas de ponto quente que não mostram anomalia; a imagem normal fica só com o ponto mais quente.

    Fica a caixa com severidade acima de normal ou com ΔT do entorno que já seria nível contra o semelhante
    (5 °C no critério da NBR). Abaixo disso é a variação comum da peça. Pedido do Hugo em 31/10/2026.
    """
    regioes = a["regioes"]
    limites = _criterios()["similares"]

    def sem_anomalia(r: dict) -> bool:
        if r.get("classe") != "ponto_quente" or not str(r.get("origem", "")).startswith("modelo:"):
            return False
        if r.get("severidade") not in ("normal", "sem_medida"):
            return False
        dt = r.get("dt_entorno")
        return dt is None or analise.nivel_por_limites(dt, limites) == "normal"

    filtradas = [r for r in regioes if not sem_anomalia(r)]
    if len(filtradas) != len(regioes):
        a["regioes"] = filtradas
        _calcular(a, matriz)


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


# ---------------------------------------------------------------- segmentação SAM 2

_segmentador_sam2 = None
_trava_sam2 = threading.Lock()


def _obter_segmentador_sam2():
    """Instancia o SAM2Segmentor sob demanda (singleton), tratando falhas de checkpoint ou pacote."""
    global _segmentador_sam2
    if _segmentador_sam2 is not None:
        return _segmentador_sam2
    with _trava_sam2:
        if _segmentador_sam2 is not None:
            return _segmentador_sam2
        try:
            from nucleo.segmentacao.sam2_engine import SAM2Segmentor

            _segmentador_sam2 = SAM2Segmentor()
        except FileNotFoundError as erro:
            raise HTTPException(503, f"Modelo SAM 2 não disponível: {erro}") from erro
        except ImportError as erro:
            raise HTTPException(503, f"Dependências do SAM 2 ausentes: {erro}") from erro
        except Exception as erro:
            raise HTTPException(500, f"Falha ao carregar o modelo SAM 2: {erro}") from erro
        return _segmentador_sam2


# ---------------------------------------------------------------- classificação DINOv2

_classificador_dinov2 = None
_trava_dinov2 = threading.Lock()


def _obter_classificador_dinov2():
    """Instancia o DINOv2Classifier sob demanda (singleton), tratando falhas de modelo ou pacote."""
    global _classificador_dinov2
    if _classificador_dinov2 is not None:
        return _classificador_dinov2
    with _trava_dinov2:
        if _classificador_dinov2 is not None:
            return _classificador_dinov2
        try:
            from nucleo.classificacao.dinov2_engine import DINOv2Classifier

            _classificador_dinov2 = DINOv2Classifier.obter_instancia()
        except ImportError as erro:
            raise HTTPException(503, f"Dependências do DINOv2 ausentes: {erro}") from erro
        except Exception as erro:
            raise HTTPException(500, f"Falha ao carregar o modelo DINOv2: {erro}") from erro
        return _classificador_dinov2


def _imagem_rgb_para_analise(matriz: np.ndarray, exibida_rgb: np.ndarray | None = None) -> np.ndarray:
    """Garante que a imagem RGB esteja nas mesmas dimensões da matriz térmica."""
    if exibida_rgb is not None:
        rgb = exibida_rgb
        if rgb.shape[:2] != matriz.shape[:2]:
            import cv2

            rgb = cv2.resize(rgb, (matriz.shape[1], matriz.shape[0]), interpolation=cv2.INTER_LINEAR)
        return rgb

    if hasattr(nucleo, "paleta") and hasattr(nucleo.paleta, "termograma"):
        try:
            return nucleo.paleta.termograma(matriz, "ferro")
        except Exception:
            pass
    return render.colorir(matriz, nome="ferro")


def _obter_imagem_rgb(id_: str, matriz: np.ndarray) -> np.ndarray:
    """Tenta obter a imagem original exibida ou sintetiza RGB a partir da matriz térmica."""
    try:
        original = armazenamento.original(id_)
        if original:
            img = entrada.carregar(original, ocr=ocr)
            return _imagem_rgb_para_analise(matriz, img.exibida_rgb)
    except Exception:
        pass
    return _imagem_rgb_para_analise(matriz, None)


def _simplificar_contorno(mascara: np.ndarray, epsilon: float = 1.0) -> list[list[float]]:
    """Gera um polígono simplificado [[x, y], ...] a partir da máscara binária."""
    import cv2

    binaria = (np.asarray(mascara) > 0).astype(np.uint8)
    contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contornos:
        return []
    maior = max(contornos, key=cv2.contourArea)
    aproximado = cv2.approxPolyDP(maior, epsilon=epsilon, closed=True)
    return [[float(p[0][0]), float(p[0][1])] for p in aproximado]


# Fontes em que a imagem chega sozinha e a resposta tem de ser rápida: a análise fica com a detecção e a
# severidade. A segmentação SAM 2 (1 a 8 s por imagem na CPU) fica para quando alguém abre a peça na Análise
# (botão Medir, /api/analises/{id}/segmentar), e o SAM 2 + DINOv2 (até minutos por imagem) dá lugar aos pontos quentes.
FONTES_AUTOMATICAS = ("monitoramento", "celular", "video")
DETECTORES_LENTOS = ("sam2-dinov2",)


def _na_placa(det: detectores.Detector) -> detectores.Detector:
    """O mesmo modelo escolhido, rodando na placa de vídeo (DirectML) se ela já estiver pronta; senão ele mesmo.

    Nunca troca pela versão INT8: a inspeção registra o modelo escolhido, e o DirectML dá as mesmas notas
    da CPU (diferença de 0,0002, ``nucleo/detectores/placa.py``). A primeira chamada começa a carregar a
    placa em outro fio; enquanto isso a inspeção segue na CPU.
    """
    combinado = isinstance(det, detectores.Combinado)
    na_placa = placa.variante(det.partes[0] if combinado else det)
    if na_placa is None:
        return det
    return detectores.Combinado(na_placa, det.partes[1]) if combinado else na_placa


def _preaquecer() -> None:
    """Deixa pronto o que a primeira imagem do monitor usaria (modelo na placa e OCR), sem segurar a subida."""
    def trabalho() -> None:
        try:
            _na_placa(_detector(None))
            ocr(np.zeros((32, 96, 3), np.uint8))
        except Exception:  # noqa: BLE001 — pré-aquecer é só ganho de tempo; a análise carrega de novo se precisar
            pass
    threading.Thread(target=trabalho, name="pyron-preaquecer", daemon=True).start()


def _nova_analise(dados: bytes, nome: str, modelo: str | None, fonte: str = "manual", identificacao: dict | None = None,
                  limites: tuple[float, float] | None = None, somente_imagem: bool = False) -> dict:
    t0 = perf_counter()
    automatica = fonte in FONTES_AUTOMATICAS
    try:
        img = entrada.carregar(dados, ocr=ocr, limites=limites, somente_imagem=somente_imagem)
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro
    t1 = perf_counter()
    det = _detector(modelo)
    aviso_rapido = None
    if automatica and det.id in DETECTORES_LENTOS:
        aviso_rapido = (f"Imagem que chega sozinha usa os pontos quentes: o {det.nome} leva até minutos por imagem. "
                        "Para usá-lo, analise de novo esta imagem com ele.")
        det = detectores.obter("pontos-quentes", PASTA_MODELOS)
    try:
        if img.tem_temperatura or getattr(det, "precisa_imagem", False):
            regioes = _regioes_do_detector(_na_placa(det), img.temperatura_c, img.exibida_rgb, metadados=img.metadados)
        else:
            regioes = []  # o modelo lê temperatura, que esta imagem não tem
    except ValueError as erro:
        raise HTTPException(422, f"O modelo {det.nome} falhou: {erro}") from erro
    except (ImportError, FileNotFoundError) as erro:
        raise HTTPException(503, f"O modelo {det.nome} não está instalado neste computador: {erro}") from erro
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
        **({} if img.tem_temperatura else {"sem_temperatura": True}),
        "tem_foto": img.foto_visivel is not None,
        "matriz_info": {
            "largura": int(img.temperatura_c.shape[1]),
            "altura": int(img.temperatura_c.shape[0]),
            "faixa_exibicao": [lo, hi],
        },
    }

    # Segmentação automática com SAM 2 se o modelo ativo for pontos-quentes-sam2 ou contiver "sam2"
    modelo_sam2 = det.id == "pontos-quentes-sam2" or "sam2" in (det.id or "").lower()
    t_seg_ms = 0
    aviso_sam2 = None
    segmentador = None
    if modelo_sam2 and automatica:
        aviso_sam2 = "Segmentação SAM 2 sob demanda: abra a peça na Análise e use Medir."
    elif modelo_sam2 and img.tem_temperatura and any(not r.get("segmentacao") for r in a["regioes"]):
        # Sem o SAM 2 instalado a análise segue sem segmentação, com aviso, em vez de falhar.
        try:
            segmentador = _obter_segmentador_sam2()
        except HTTPException as erro:
            aviso_sam2 = f"Segmentação SAM 2 não executada: {erro.detail}"
    if segmentador is not None:
        t_seg_ini = perf_counter()
        imagem_rgb = _imagem_rgb_para_analise(img.temperatura_c, img.exibida_rgb)
        from nucleo.pipeline.pyron_pipeline import analisar_ativo

        primeiro = True
        for r in a["regioes"]:
            if r.get("segmentacao"):
                continue
            caixa = r.get("caixa")
            if not caixa or len(caixa) != 4:
                continue
            classe_r = (r.get("classe") or "componente").lower()
            padroes_h = {"isolador": 0.80, "bucha": 1.25, "para_raio": 1.20, "terminal_superior": 0.65, "transformador": 1.60}
            h_ref_r = padroes_h.get(classe_r, 0.80)
            try:
                res = analisar_ativo(
                    segmentador=segmentador,
                    imagem_rgb=imagem_rgb,
                    matriz_termica=img.temperatura_c,
                    bbox_xyxy=caixa,
                    ref_height_meters=h_ref_r,
                    metadados_camera=a.get("metadados"),
                    reutilizar_quadro=not primeiro,
                )
                primeiro = False
                contorno_pontos = _simplificar_contorno(res.mascara, epsilon=1.0)
                r["segmentacao"] = {
                    "score": float(res.score),
                    "geometria": res.geometria,
                    "termica_isolada": asdict(res.termica) if res.termica else None,
                    "contorno": contorno_pontos,
                }
            except Exception:
                pass
        t_seg_ms = round((perf_counter() - t_seg_ini) * 1000)

    t_calc_ini = perf_counter()
    notas = []
    if not img.tem_temperatura and not getattr(det, "precisa_imagem", False):
        notas.append(f"O modelo {det.nome} procura pelo calor; sem temperatura, ele não identifica componentes. "
                     "Escolha um modelo que olha a imagem colorida.")
    notas += [n for n in (aviso_sam2, aviso_rapido) if n]
    if notas:
        a["avisos_analise"] = notas
    _calcular(a, img.temperatura_c)
    _remover_pontos_quentes_sem_anomalia(a, img.temperatura_c)
    t3 = perf_counter()
    etapas = [
        {"nome": "Leitura da temperatura", "ms": round((t1 - t0) * 1000), **({} if img.tem_temperatura else {"sem_dado": True})},
        {"nome": "Detecção", "ms": round((t2 - t1) * 1000)},
        {"nome": "Medição e severidade", "ms": round((t3 - t_calc_ini) * 1000), **({} if img.tem_temperatura else {"sem_dado": True})},
    ]
    if t_seg_ms > 0:
        etapas.insert(2, {"nome": "Segmentação SAM 2", "ms": t_seg_ms})
    a["etapas"] = etapas
    armazenamento.salvar(a, original=dados, matriz=img.temperatura_c)
    if img.foto_visivel:
        armazenamento.salvar_foto(a["id"], img.foto_visivel)
    return a


def _completa(a: dict) -> dict:
    matriz = armazenamento.matriz(a["id"])
    saida = dict(a)
    saida["equipamento_chave"] = _chave_de(a)
    if a.get("resumo", {}).get("severidade", "normal") not in analise.SEM_CLASSIFICACAO:
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
    """Analisa uma imagem com auto-segmentação SAM 2, classificação DINOv2 e metrologia monocular imediata."""
    dados = await arquivo.read()
    if not dados:
        raise HTTPException(422, "O arquivo está vazio.")
    ident = {k: v.strip()[:120] for k, v in (("instalacao", instalacao), ("equipamento", equipamento)) if v and v.strip()}
    # Sem modelo explícito, _detector resolve o modelo térmico ativo.
    modelo_analise = modelo if (modelo and modelo.strip()) else None

    def analisar() -> dict:
        with _trava:
            return _completa(_nova_analise(dados, arquivo.filename or "imagem.jpg", modelo_analise, identificacao=ident))

    # A análise leva segundos: num fio à parte, para o servidor seguir atendendo os outros pedidos (e outros usuários).
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(analisar)


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
    """Grava a edição da tela. Com ``revisao`` no corpo, recusa (409) se outra pessoa gravou antes."""
    with _trava:
        a, m = _carregar(id_)
        if "revisao" in corpo and corpo["revisao"] != a.get("revisao", 0):
            raise HTTPException(409, "Outra pessoa alterou esta inspeção enquanto você editava. Abra de novo para ver a versão nova.")
        _aplicar_edicao(a, m, corpo)
        a["revisao"] = a.get("revisao", 0) + 1
        _calcular(a, m)
        armazenamento.salvar(a)
    return _completa(a)


def _aplicar_edicao(a: dict, m: np.ndarray, corpo: dict) -> None:
    if "regioes" in corpo:
        novas = []
        for r in corpo["regioes"]:
            caixa = [float(v) for v in r["caixa"]]
            if caixa[2] - caixa[0] < 1 or caixa[3] - caixa[1] < 1:
                continue
            item = {
                "id": r.get("id") or uuid.uuid4().hex[:8],
                "nome": str(r.get("nome") or "Região")[:60],
                "classe": str(r.get("classe") or "componente")[:40],
                "caixa": caixa,
                "confianca": r.get("confianca"),
                "origem": r.get("origem") or "manual",
            }
            if "segmentacao" in r:
                item["segmentacao"] = r["segmentacao"]
            if "classificacao_dinov2" in r:
                item["classificacao_dinov2"] = r["classificacao_dinov2"]
            novas.append(item)
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
    _remover_pontos_quentes_sem_anomalia(a, m)
    armazenamento.salvar(a)
    return _completa(a)


# ---------------------------------------------------------------- rotas: segmentação SAM 2


def _normalizar_caixa_se_rgb(id_: str, m: np.ndarray, caixa: list[float]) -> list[float]:
    """Se a caixa foi informada nas coordenadas de imagem óptica de alta resolução, ajusta para a matriz."""
    try:
        original = armazenamento.original(id_)
        if original:
            raw_rgb = entrada.exibida(original)
            if raw_rgb is not None and (raw_rgb.shape[1] > m.shape[1] or raw_rgb.shape[0] > m.shape[0]):
                if caixa[2] > m.shape[1] or caixa[3] > m.shape[0]:
                    sx = m.shape[1] / raw_rgb.shape[1]
                    sy = m.shape[0] / raw_rgb.shape[0]
                    return [caixa[0] * sx, caixa[1] * sy, caixa[2] * sx, caixa[3] * sy]
    except Exception:
        pass
    return caixa


@app.post("/api/analises/{id_}/segmentar")
def segmentar(id_: str, corpo: dict = Body(default={})) -> dict:
    """Segmenta o ativo dentro da região com SAM 2, calculando metrologia e térmica isolada."""
    a, m = _carregar(id_)
    regiao_id = corpo.get("regiao_id")
    caixa = corpo.get("caixa")
    metric_ratio = corpo.get("metric_ratio")

    if metric_ratio is not None:
        try:
            metric_ratio = float(metric_ratio)
            if metric_ratio <= 0:
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(422, "O parâmetro 'metric_ratio' deve ser um número positivo.")

    a_regiao = None
    if regiao_id:
        for r in a.get("regioes", []):
            if r.get("id") == regiao_id:
                a_regiao = r
                break
        if a_regiao is None:
            raise HTTPException(404, f"Região '{regiao_id}' não encontrada na análise.")
        if caixa is None:
            caixa = a_regiao.get("caixa")

    if not caixa or len(caixa) != 4:
        raise HTTPException(422, "Coordenadas da caixa [x0, y0, x1, y1] não fornecidas ou inválidas.")

    try:
        caixa = [float(v) for v in caixa]
    except (ValueError, TypeError) as erro:
        raise HTTPException(422, f"Coordenadas da caixa inválidas: {erro}") from erro

    if caixa[2] <= caixa[0] or caixa[3] <= caixa[1]:
        raise HTTPException(422, "Caixa inválida: x1 deve ser maior que x0 e y1 maior que y0.")

    caixa = _normalizar_caixa_se_rgb(id_, m, caixa)
    imagem_rgb = _obter_imagem_rgb(id_, m)
    segmentador = _obter_segmentador_sam2()

    h_ref = corpo.get("altura_referencia") or corpo.get("ref_height_meters")
    if h_ref is not None:
        try:
            h_ref = float(h_ref)
        except (ValueError, TypeError):
            h_ref = None
    if h_ref is None and metric_ratio is None:
        classe_atual = (a_regiao.get("classe") if a_regiao else "componente") or "componente"
        padroes_h = {"isolador": 0.80, "bucha": 1.25, "para_raio": 1.20, "terminal_superior": 0.65, "transformador": 1.60, "conexao": 0.50}
        h_ref = padroes_h.get(str(classe_atual).lower(), 0.80)

    try:
        from nucleo.pipeline.pyron_pipeline import analisar_ativo
        from nucleo.metrologia.dimension_estimator import MascaraVaziaError

        res = analisar_ativo(
            segmentador=segmentador,
            imagem_rgb=imagem_rgb,
            matriz_termica=m,
            bbox_xyxy=caixa,
            metric_ratio=metric_ratio,
            ref_height_meters=h_ref,
            metadados_camera=a.get("metadados"),
        )
    except MascaraVaziaError as erro:
        raise HTTPException(422, f"Não foi possível segmentar o ativo na caixa informada: {erro}") from erro
    except Exception as erro:
        raise HTTPException(500, f"Falha na segmentação do ativo: {erro}") from erro

    contorno_pontos = _simplificar_contorno(res.mascara, epsilon=1.0)

    dados_segmentacao = {
        "score": float(res.score),
        "geometria": res.geometria,
        "termica_isolada": asdict(res.termica) if res.termica else None,
        "contorno": contorno_pontos,
    }

    if a_regiao is None:
        a_regiao = {
            "id": uuid.uuid4().hex[:8],
            "nome": "Segmentação",
            "classe": "componente",
            "caixa": caixa,
            "origem": "segmentacao:sam2",
            "segmentacao": dados_segmentacao,
        }
        a.setdefault("regioes", []).append(a_regiao)
    else:
        a_regiao["segmentacao"] = dados_segmentacao
        if "caixa" in corpo:
            a_regiao["caixa"] = caixa

    with _trava:
        _calcular(a, m)
        armazenamento.salvar(a)

    regiao_atualizada = next((r for r in a["regioes"] if r["id"] == a_regiao["id"]), a_regiao)

    return {
        "ok": True,
        "segmentacao": regiao_atualizada.get("segmentacao", dados_segmentacao),
        "analise": _completa(a),
    }


# ---------------------------------------------------------------- classificação DINOv2 e metodologia completa


@app.post("/api/analises/{id_}/classificar")
def classificar(id_: str, corpo: dict = Body(default={})) -> dict:
    """Classifica o ativo dentro da região com DINOv2 via embeddings fundacionais e galeria de protótipos."""
    a, m = _carregar(id_)
    regiao_id = corpo.get("regiao_id")
    caixa = corpo.get("caixa")

    a_regiao = None
    if regiao_id:
        for r in a.get("regioes", []):
            if r.get("id") == regiao_id:
                a_regiao = r
                break
        if a_regiao is None:
            raise HTTPException(404, f"Região '{regiao_id}' não encontrada na análise.")
        if caixa is None:
            caixa = a_regiao.get("caixa")

    if not caixa or len(caixa) != 4:
        raise HTTPException(422, "Coordenadas da caixa [x0, y0, x1, y1] não fornecidas ou inválidas.")

    try:
        caixa = [float(v) for v in caixa]
    except (ValueError, TypeError) as erro:
        raise HTTPException(422, f"Coordenadas da caixa inválidas: {erro}") from erro

    if caixa[2] <= caixa[0] or caixa[3] <= caixa[1]:
        raise HTTPException(422, "Caixa inválida: x1 deve ser maior que x0 e y1 maior que y0.")

    caixa = _normalizar_caixa_se_rgb(id_, m, caixa)
    imagem_rgb = _obter_imagem_rgb(id_, m)
    classificador = _obter_classificador_dinov2()

    try:
        resultado = classificador.classificar(imagem_rgb, bbox=caixa)
    except Exception as erro:
        raise HTTPException(500, f"Falha na classificação com DINOv2: {erro}") from erro

    dados_classificacao = {
        "classe": resultado["classe"],
        "confianca": float(resultado["confianca"]),
        "nome": resultado["nome"],
        "scores": resultado.get("scores", {}),
    }

    if a_regiao is None:
        a_regiao = {
            "id": uuid.uuid4().hex[:8],
            "nome": f"Classificação ({resultado['nome']})",
            "classe": resultado["classe"],
            "caixa": caixa,
            "origem": "classificacao:dinov2",
            "classificacao_dinov2": dados_classificacao,
        }
        a.setdefault("regioes", []).append(a_regiao)
    else:
        a_regiao["classificacao_dinov2"] = dados_classificacao
        if "caixa" in corpo:
            a_regiao["caixa"] = caixa
        if resultado["confianca"] > 0.60:
            a_regiao["classe"] = resultado["classe"]

    with _trava:
        _calcular(a, m)
        armazenamento.salvar(a)

    regiao_atualizada = next((r for r in a["regioes"] if r["id"] == a_regiao["id"]), a_regiao)

    return {
        "ok": True,
        "classificacao": regiao_atualizada.get("classificacao_dinov2", dados_classificacao),
        "analise": _completa(a),
    }


@app.post("/api/analises/{id_}/metodologia_completa")
def metodologia_completa(id_: str, corpo: dict = Body(default={})) -> dict:
    """Executa a tríade completa na região: Segmentação SAM 2 + Metrologia/Termometria + Classificação DINOv2."""
    a, m = _carregar(id_)
    regiao_id = corpo.get("regiao_id")
    caixa = corpo.get("caixa")
    metric_ratio = corpo.get("metric_ratio")

    if metric_ratio is not None:
        try:
            metric_ratio = float(metric_ratio)
            if metric_ratio <= 0:
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(422, "O parâmetro 'metric_ratio' deve ser um número positivo.")

    a_regiao = None
    if regiao_id:
        for r in a.get("regioes", []):
            if r.get("id") == regiao_id:
                a_regiao = r
                break
        if a_regiao is None:
            raise HTTPException(404, f"Região '{regiao_id}' não encontrada na análise.")
        if caixa is None:
            caixa = a_regiao.get("caixa")

    if not caixa or len(caixa) != 4:
        raise HTTPException(422, "Coordenadas da caixa [x0, y0, x1, y1] não fornecidas ou inválidas.")

    try:
        caixa = [float(v) for v in caixa]
    except (ValueError, TypeError) as erro:
        raise HTTPException(422, f"Coordenadas da caixa inválidas: {erro}") from erro

    if caixa[2] <= caixa[0] or caixa[3] <= caixa[1]:
        raise HTTPException(422, "Caixa inválida: x1 deve ser maior que x0 e y1 maior que y0.")

    caixa = _normalizar_caixa_se_rgb(id_, m, caixa)
    imagem_rgb = _obter_imagem_rgb(id_, m)
    segmentador = _obter_segmentador_sam2()
    classificador = _obter_classificador_dinov2()

    # 1. Segmentação SAM 2 + Metrologia dimensional + Pureza térmica
    h_ref = corpo.get("altura_referencia") or corpo.get("ref_height_meters")
    if h_ref is not None:
        try:
            h_ref = float(h_ref)
        except (ValueError, TypeError):
            h_ref = None
    if h_ref is None and metric_ratio is None:
        classe_atual = (a_regiao.get("classe") if a_regiao else "componente") or "componente"
        padroes_h = {"isolador": 0.80, "bucha": 1.25, "para_raio": 1.20, "terminal_superior": 0.65, "transformador": 1.60, "conexao": 0.50}
        h_ref = padroes_h.get(str(classe_atual).lower(), 0.80)

    try:
        from nucleo.pipeline.pyron_pipeline import analisar_ativo
        from nucleo.metrologia.dimension_estimator import MascaraVaziaError

        res = analisar_ativo(
            segmentador=segmentador,
            imagem_rgb=imagem_rgb,
            matriz_termica=m,
            bbox_xyxy=caixa,
            metric_ratio=metric_ratio,
            ref_height_meters=h_ref,
            metadados_camera=a.get("metadados"),
        )
    except MascaraVaziaError as erro:
        raise HTTPException(422, f"Não foi possível segmentar o ativo na caixa informada: {erro}") from erro
    except Exception as erro:
        raise HTTPException(500, f"Falha na segmentação do ativo: {erro}") from erro

    contorno_pontos = _simplificar_contorno(res.mascara, epsilon=1.0)

    dados_segmentacao = {
        "score": float(res.score),
        "geometria": res.geometria,
        "termica_isolada": asdict(res.termica) if res.termica else None,
        "contorno": contorno_pontos,
    }

    # 2. Classificação DINOv2 focada no corpo da peça com máscara SAM 2
    try:
        res_dino = classificador.classificar(imagem_rgb, bbox=caixa, mascara=res.mascara)
    except Exception as erro:
        raise HTTPException(500, f"Falha na classificação com DINOv2: {erro}") from erro

    dados_classificacao = {
        "classe": res_dino["classe"],
        "confianca": float(res_dino["confianca"]),
        "nome": res_dino["nome"],
        "scores": res_dino.get("scores", {}),
    }

    # 3. Consolidação na região
    if a_regiao is None:
        a_regiao = {
            "id": uuid.uuid4().hex[:8],
            "nome": f"Ativo ({res_dino['nome']})",
            "classe": res_dino["classe"],
            "caixa": caixa,
            "origem": "metodologia_completa",
            "segmentacao": dados_segmentacao,
            "classificacao_dinov2": dados_classificacao,
        }
        a.setdefault("regioes", []).append(a_regiao)
    else:
        a_regiao["segmentacao"] = dados_segmentacao
        a_regiao["classificacao_dinov2"] = dados_classificacao
        if "caixa" in corpo:
            a_regiao["caixa"] = caixa
        if res_dino["confianca"] > 0.60:
            a_regiao["classe"] = res_dino["classe"]

    with _trava:
        _calcular(a, m)
        armazenamento.salvar(a)

    regiao_atualizada = next((r for r in a["regioes"] if r["id"] == a_regiao["id"]), a_regiao)

    return {
        "ok": True,
        "classificacao": regiao_atualizada.get("classificacao_dinov2", dados_classificacao),
        "segmentacao": regiao_atualizada.get("segmentacao", dados_segmentacao),
        "analise": _completa(a),
    }


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


@app.post("/api/analises/{id_}/escala")
def informar_escala(id_: str, corpo: dict = Body(...)) -> dict:
    """Mínimo e máximo da barra de cores, quando a leitura automática falhou ou leu errado.

    Vale para imagens sem dados radiométricos que têm a barra: as cores viram temperatura com
    essa escala. As regiões ficam onde estão e são medidas de novo.
    """
    a, _ = _carregar(id_)
    if a.get("radiometrica"):
        raise HTTPException(422, "Este termograma é radiométrico: a temperatura vem da câmera, não de uma escala.")
    try:
        t_min, t_max = float(corpo.get("t_min")), float(corpo.get("t_max"))
    except (TypeError, ValueError) as erro:
        raise HTTPException(422, "Informe o mínimo e o máximo da escala em °C.") from erro
    if not (-60 <= t_min < t_max <= 2000):
        raise HTTPException(422, "Escala inválida: o máximo precisa ser maior que o mínimo (de −60 a 2000 °C).")
    original = armazenamento.original(id_)
    if original is None:
        raise HTTPException(422, "O arquivo original desta inspeção não está guardado.")
    try:
        img = entrada.carregar(original, ocr=None, limites=(t_min, t_max))
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro
    a["metadados"] = {k: v for k, v in {**a.get("metadados", {}), **img.metadados}.items()
                      if k not in ("sem_temperatura", "barra_encontrada")}
    a["origem"] = img.origem
    a.pop("sem_temperatura", None)
    a["etapas"] = [{k: v for k, v in e.items() if k != "sem_dado"} for e in a.get("etapas", [])]
    lo, hi = render.faixa_exibicao(img.temperatura_c)
    a["matriz_info"] = {**a.get("matriz_info", {}), "faixa_exibicao": [lo, hi]}
    a.pop("exibicao", None)  # a faixa manual antiga não vale para a escala nova
    with _trava:
        _calcular(a, img.temperatura_c)
        armazenamento.salvar(a, matriz=img.temperatura_c)
    return _completa(a)


def _fundo(id_: str, a: dict) -> np.ndarray | None:
    """Sem temperatura, o fundo das imagens exportadas é a própria imagem enviada."""
    if not a.get("sem_temperatura"):
        return None
    original = armazenamento.original(id_)
    return entrada.exibida(original) if original else None


def _sem_temperatura(itens: list[dict]) -> None:
    """Laudo termográfico sem temperatura não diz nada: barra antes de gerar."""
    faltam = [a["arquivo"] for a in itens if a.get("sem_temperatura")]
    if faltam:
        raise HTTPException(422, f"{', '.join(faltam[:3])}{'…' if len(faltam) > 3 else ''}: sem temperatura medida. "
                                 "Informe a escala na inspeção ou use o JPEG radiométrico antes do laudo.")


def _nome_exportado(a: dict, sufixo: str) -> str:
    base = re.sub(r"[^\w.-]+", "_", Path(a["arquivo"]).stem, flags=re.UNICODE).strip("_") or "inspecao"
    return f"{base}_{sufixo}"


@app.post("/api/analises/{id_}/auto_identificar")
def auto_identificar_ativos(id_: str) -> dict:
    """Descobre e segmenta os ativos elétricos automaticamente na cena com SAM 2 + DINOv2 + Criminisi."""
    a, m = _carregar(id_)
    imagem_rgb = _obter_imagem_rgb(id_, m)
    from nucleo.detectores.sam2_dinov2 import SAM2DINOv2Detector

    det = SAM2DINOv2Detector()
    manuais = [r for r in a["regioes"] if r.get("origem") == "manual"]
    novas = det.detectar_com_metrologia(m, imagem_rgb, metadados=a.get("metadados"))
    for r in novas:
        if not r.get("id"):
            r["id"] = uuid.uuid4().hex[:8]

    a["regioes"] = manuais + novas
    a["modelo"] = _info_modelo(det)
    with _trava:
        _calcular(a, m)
        armazenamento.salvar(a)
    return _completa(a)


@app.get("/api/analises/{id_}/imagem.png")
def exportar_imagem(id_: str, largura: int = 1280) -> Response:
    """Termograma com as regiões, pontos e linhas, na paleta e na escala escolhidas na tela."""
    a, m = _carregar(id_)
    _calcular(a, m)
    exib = a.get("exibicao") or {}
    img = render.desenhar(m, a["regioes"], largura=max(320, min(largura, 3840)), nome=exib.get("paleta") or "ferro",
                          medicoes=a.get("medicoes"), faixa=tuple(exib["faixa"]) if exib.get("faixa") else None,
                          fundo=_fundo(id_, a))
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


def _tipo_imagem(dados: bytes) -> str:
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    if dados[:2] == b"BM":
        return "image/bmp"
    return "image/jpeg"


@app.get("/api/analises/{id_}/original.jpg")
def original(id_: str) -> Response:
    dados = armazenamento.original(id_)
    if not dados:
        raise HTTPException(404, "Imagem original não encontrada.")
    return Response(dados, media_type=_tipo_imagem(dados))


@app.get("/api/analises/{id_}/miniatura.png")
def miniatura(id_: str) -> Response:
    a, m = _carregar(id_)
    buf = io.BytesIO()
    render.desenhar(m, a["regioes"], largura=320, fundo=_fundo(id_, a)).save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png")


def _escolher_responsavel(id_: str | None, a: dict | None = None) -> dict:
    """Só sai laudo com responsável do cadastro: nome e registro nunca são digitados na hora."""
    escolhido = id_ or ((a or {}).get("identificacao") or {}).get("responsavel_id")
    resp = _responsavel(escolhido)
    if resp is None:
        raise HTTPException(422, "Escolha o responsável técnico. Se ainda não houver, cadastre em Configurações › Empresa e time.")
    return resp


def _motor_laudo(pedido: str | None = None):
    """O gerador do laudo: o da configuração (laudo.motor), ou o pedido por quem administra (?motor=, para comparar).

    Typst escolhido mas indisponível (pacote ausente, DLL barrada pelo Windows): o laudo sai pelo reportlab.
    """
    motor = pedido if pedido in MOTORES_LAUDO else (_config().get("laudo") or {}).get("motor", "typst")
    if motor == "typst":
        from app import laudo_typst

        if laudo_typst.disponivel() is None:
            return laudo_typst
    return laudo


def _quem_assina(request: Request, escolhido: str | None, a: dict | None = None) -> dict:
    """No modo local, o responsável escolhido na tela; no servidor, sempre quem entrou (nome e registro dele)."""
    quem = acesso.usuario(request)
    return quem if quem is not None else _escolher_responsavel(escolhido, a)


def _registrar_laudo(request: Request, ids: list[str], resp: dict, pdf: bytes) -> None:
    """Trilha de auditoria: quem emitiu, quem assina, quando, quais inspeções e o SHA-256 do PDF."""
    quem = acesso.usuario(request)
    armazenamento.registrar_laudo({
        "id": uuid.uuid4().hex[:12], "emitido_em": datetime.now().isoformat(timespec="seconds"),
        "emitido_por_id": quem["id"] if quem else None, "emitido_por_nome": quem["nome"] if quem else None,
        "responsavel_nome": resp["nome"], "responsavel_registro": resp.get("registro") or None,
        "analises": ids, "sha256": hashlib.sha256(pdf).hexdigest(), "bytes": len(pdf),
    })


@app.get("/api/analises/{id_}/laudo.pdf")
def laudo_pdf(request: Request, id_: str, responsavel: str | None = None, art: str | None = None, motor: str | None = None) -> Response:
    a, m = _carregar(id_)
    _sem_temperatura([a])
    resp = _quem_assina(request, responsavel, a)
    art = (art if art is not None else (a.get("identificacao") or {}).get("art")) or ""
    gerador = _motor_laudo(motor if acesso.pode(request, "administracao") else None)
    pdf = gerador.gerar(a, m, armazenamento.foto(id_), VERSAO, empresa=_config()["empresa"], responsavel=resp, art=art[:60],
                        criterios=_criterios(), logo=_logo())
    _registrar_laudo(request, [a["id"]], resp, pdf)
    nome = f"relatorio_{re.sub(r'[^A-Za-z0-9_-]', '_', Path(a['arquivo']).stem)}_{a['id'][:6]}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nome}"'})


@app.post("/api/laudos")
def laudo_varias(request: Request, corpo: dict = Body(...)) -> Response:
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
    _sem_temperatura([a for a, _, _ in itens])
    resp = _quem_assina(request, corpo.get("responsavel"))
    gerador = _motor_laudo(corpo.get("motor") if acesso.pode(request, "administracao") else None)
    pdf = gerador.gerar_relatorio(itens, VERSAO, empresa=_config()["empresa"], responsavel=resp,
                                  art=str(corpo.get("art") or "")[:60], criterios=_criterios(), logo=_logo())
    _registrar_laudo(request, [a["id"] for a, _, _ in itens], resp, pdf)
    nome = f"relatorio_termografico_{datetime.now():%Y%m%d_%H%M}_{len(itens)}_imagens.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{nome}"'})


@app.get("/api/laudos/emitidos")
def laudos_emitidos(limite: int = 200) -> list[dict]:
    """Os laudos emitidos, do mais novo para o mais antigo: quem pediu, quem assina, inspeções e SHA-256 do PDF."""
    return armazenamento.laudos_emitidos(max(1, min(limite, 1000)))


# ---------------------------------------------------------------- rotas: comentários

LIMITE_COMENTARIO = 2000


def _autor(request: Request) -> tuple[str | None, str]:
    """(id, nome) de quem escreve: quem entrou (servidor) ou o responsável padrão deste computador (local)."""
    quem = acesso.usuario(request)
    if quem is not None:
        return quem["id"], quem["nome"]
    cfg = _config()
    padrao = next((r for r in cfg["responsaveis"] if r["id"] == cfg.get("responsavel_padrao")), None)
    return (padrao["id"], padrao["nome"]) if padrao else (None, "Este computador")


@app.get("/api/analises/{id_}/comentarios")
def comentarios(id_: str) -> list[dict]:
    if armazenamento.obter(id_) is None:
        raise HTTPException(404, "Inspeção não encontrada.")
    return armazenamento.comentarios(id_)


@app.post("/api/analises/{id_}/comentarios")
def comentar(request: Request, id_: str, corpo: dict = Body(...)) -> list[dict]:
    """Acrescenta um comentário com autor e data (região opcional). Devolve a lista toda."""
    a = armazenamento.obter(id_)
    if a is None:
        raise HTTPException(404, "Inspeção não encontrada.")
    texto = str(corpo.get("texto") or "").strip()
    if not texto:
        raise HTTPException(422, "Escreva o comentário.")
    if len(texto) > LIMITE_COMENTARIO:
        raise HTTPException(422, f"O comentário passa de {LIMITE_COMENTARIO} caracteres.")
    regiao = corpo.get("regiao_id") or None
    if regiao is not None and not any(r.get("id") == regiao for r in a.get("regioes") or []):
        raise HTTPException(422, "Essa região não existe mais nesta inspeção.")
    autor_id, autor_nome = _autor(request)
    armazenamento.comentar(id_, texto, autor_nome, autor_id, regiao)
    return armazenamento.comentarios(id_)


# ---------------------------------------------------------------- rotas: acesso (modo servidor)


@app.get("/api/acesso/eu")
def acesso_eu(request: Request) -> dict:
    """Modo do servidor e quem está usando. No modo local não há login: usuário vazio e todas as permissões."""
    if not acesso.modo_servidor():
        return {"modo": "local", "usuario": None, "permissoes": sorted(acesso.PERMISSOES)}
    atual = acesso.sessao_atual(request)
    return {"modo": "servidor", "usuario": acesso.descrever(atual[0]) if atual else None,
            "permissoes": sorted(acesso.permissoes(atual[0])) if atual else []}


@app.post("/api/acesso/entrar")
def acesso_entrar(request: Request, corpo: dict = Body(...)) -> JSONResponse:
    if not acesso.modo_servidor():
        raise HTTPException(409, "No modo local não há login.")
    m, codigo = acesso.entrar(request, corpo.get("usuario"), corpo.get("senha"))
    resposta = JSONResponse({"modo": "servidor", "usuario": acesso.descrever(m), "permissoes": sorted(acesso.permissoes(m))})
    acesso.gravar_cookie(resposta, request, codigo)
    return resposta


@app.post("/api/acesso/sair")
def acesso_sair(request: Request) -> JSONResponse:
    if acesso.modo_servidor():
        acesso.sair(request)
    resposta = JSONResponse({"ok": True})
    acesso.apagar_cookie(resposta, request)
    return resposta


@app.post("/api/acesso/senha")
def acesso_trocar_senha(request: Request, corpo: dict = Body(...)) -> dict:
    """A própria pessoa troca a senha (pede a atual). As outras sessões dela são encerradas."""
    quem = acesso.usuario(request)
    if quem is None:
        raise HTTPException(409, "No modo local não há senha.")
    if not acesso.conferir_senha(str(corpo.get("atual") or ""), quem.get("senha_hash")):
        raise HTTPException(422, "A senha atual não confere.")
    try:
        nova = acesso.validar_senha(corpo.get("nova"))
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro
    with _trava:
        cfg = _config()
        for r in cfg["responsaveis"]:
            if r["id"] == quem["id"]:
                r["senha_hash"] = acesso.gerar_hash(nova)
        _salvar_config(cfg)
    armazenamento.encerrar_sessoes_de(quem["id"], menos=getattr(request.state, "sessao", None))
    return {"ok": True}


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
    lista = [d.descrever() for d in detectores.listar(PASTA_MODELOS)]
    if not any(m["id"] == "sam2-dinov2" for m in lista):
        # O módulo importa o torch, que o Controle Inteligente de Aplicativos pode barrar: sem ele, a lista segue.
        try:
            from nucleo.detectores.sam2_dinov2 import SAM2DINOv2Detector

            sam2 = SAM2DINOv2Detector()
        except (ImportError, OSError):
            sam2 = None
        if sam2 is not None:
            disponivel = importlib.util.find_spec("sam2") is not None and sam2._caminho_pesos.exists()
            lista.insert(1, {**sam2.descrever(), "disponivel": disponivel})
    combinados = [d for d in detectores.listar(PASTA_MODELOS) if isinstance(d, detectores.Combinado)]
    # o que a tela mostra: os combinados normais; só com o INT8 instalado, ele; sem treinado, os pontos quentes
    principais = [d.id for d in combinados if not d.partes[0].cartao.get("otimizacao")] or [d.id for d in combinados]
    if principais:
        principais_set = set(principais)
    else:
        principais_set = {"pontos-quentes"}
    for item in lista:
        if item["id"] in principais_set:
            item["principal"] = True
    # onde o modelo ativo roda (placa, "carregando" = preparando a placa, ou processador) e o acelerador do servidor
    return {"ativo": _modelo_termico(), "modelos": lista, "placa": _onde_modelo_ativo(), "acelerador": provedores.situacao()}


def _onde_modelo_ativo() -> dict | None:
    try:
        det = _detector(None)
    except HTTPException:
        return None
    return placa.situacao(_original(det.partes[0] if isinstance(det, detectores.Combinado) else det))


@app.put("/api/modelos/ativo")
def definir_ativo(corpo: dict = Body(...)) -> dict:
    det = _detector(corpo.get("id"))
    if det.id != corpo.get("id"):
        raise HTTPException(404, "Modelo não encontrado.")
    cfg = _config()
    if det.tipo == "aprendizado":
        combinado = f"{det.id}+pontos-quentes"
        instalados = {d.id for d in detectores.listar(PASTA_MODELOS)}
        cfg["modelo_ativo"] = combinado if combinado in instalados else det.id
    else:
        cfg["modelo_ativo"] = det.id
    _salvar_config(cfg)
    return modelos()


@app.get("/api/criterios")
def criterios() -> dict:
    return {"criterio": _criterios(), "padrao": analise.CRITERIOS_PADRAO, "niveis": analise.NIVEIS}


def _time_para_tela(request: Request | None, responsaveis: list[dict]) -> list[dict]:
    """O time como a tela vê: nunca a senha (só se tem); telefone, e-mail e alertas só para quem administra."""
    completo = request is None or acesso.pode(request, "administracao")
    privados = {"senha_hash"} | (set() if completo else {"email", "telefone", "alertas"})
    return [{**{k: v for k, v in r.items() if k not in privados}, "tem_senha": bool(r.get("senha_hash"))} for r in responsaveis]


@app.get("/api/configuracoes")
def configuracoes(request: Request = None) -> dict:
    cfg = _config()
    pastas = request is None or acesso.pode(request, "administracao")
    return {
        "empresa": cfg["empresa"],
        "responsaveis": _time_para_tela(request, cfg["responsaveis"]),
        "responsavel_padrao": cfg.get("responsavel_padrao"),
        "tema": cfg["tema"],
        "criterio": cfg.get("criterios") or analise.CRITERIOS_PADRAO,
        "criterio_padrao": analise.CRITERIOS_PADRAO,
        "modelos_criterio": {"brasil": analise.CRITERIOS_PADRAO, "neta": analise.CRITERIOS_NETA},
        "criterio_personalizado": bool(cfg.get("criterios")),
        "niveis": analise.NIVEIS,
        "componentes": _componentes(),
        "componentes_padrao": referencias.COMPONENTES_PADRAO,
        "pasta_dados": str(PASTA_DADOS) if pastas else "",
        "pasta_modelos": str(PASTA_MODELOS) if pastas else "",
        "versao": VERSAO,
        "tem_logo": (PASTA_DADOS / "logo.png").exists(),
        "modo": acesso.modo(),
        "limite_time": acesso.LIMITE_TIME,
        "laudo": cfg.get("laudo") or {"motor": "typst"},
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


@app.get("/api/sistema")
def sistema() -> dict:
    """Onde estão os dados, quanto ocupam e quantas inspeções há."""
    return {"pasta_dados": str(PASTA_DADOS), "pasta_modelos": str(PASTA_MODELOS), "versao": VERSAO,
            "inspecoes": len(armazenamento.listar()), **backup.contar(PASTA_DADOS),
            "acelerador": provedores.situacao(), "placa": _onde_modelo_ativo()}


@app.get("/api/backup.zip")
def baixar_backup() -> Response:
    with _trava:
        dados = backup.gerar(PASTA_DADOS)
    nome = f"pyron_backup_{datetime.now():%Y%m%d_%H%M}.zip"
    return Response(dados, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@app.post("/api/backup/restaurar")
async def restaurar_backup(arquivo: UploadFile = File(...)) -> dict:
    """Troca os dados atuais pelos do backup (o estado atual vai antes para dados_app/backups)."""
    dados = await arquivo.read()
    try:
        with _trava:
            return backup.restaurar(PASTA_DADOS, dados)
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro


@app.post("/api/sistema/abrir-pasta")
def abrir_pasta(corpo: dict = Body(...)) -> dict:
    """Abre a pasta de dados ou de modelos no Explorador de Arquivos (o Pyron roda neste computador)."""
    pasta = {"dados": PASTA_DADOS, "modelos": PASTA_MODELOS}.get(corpo.get("qual"))
    if pasta is None or not hasattr(os, "startfile"):
        raise HTTPException(422, "Não dá para abrir essa pasta daqui.")
    pasta.mkdir(parents=True, exist_ok=True)
    os.startfile(pasta)  # noqa: S606 - pasta fixa do próprio programa, aberta a pedido do usuário
    return {"ok": True}


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
def salvar_configuracoes(request: Request, corpo: dict = Body(...)) -> dict:
    cfg = _config()
    if "empresa" in corpo:
        cfg["empresa"] = {k: str(corpo["empresa"].get(k, ""))[:120] for k in ("nome", "subtitulo")}
    if "responsaveis" in corpo:
        antes = {r["id"]: r.get("senha_hash") for r in cfg["responsaveis"]}
        cfg["responsaveis"] = _validar_responsaveis(corpo["responsaveis"], cfg["responsaveis"])
        if acesso.modo_servidor() and acesso.falta_para_servidor(cfg["responsaveis"]):
            raise HTTPException(422, "O time precisa continuar com ao menos um administrador com usuário e senha.")
        trocaram = [r["id"] for r in cfg["responsaveis"] if r["id"] in antes and r.get("senha_hash") != antes[r["id"]]]
        cfg["responsavel"] = {"nome": "", "registro": ""}  # o formato antigo não volta a migrar
        ids = [r["id"] for r in cfg["responsaveis"] if r["assina"]]
        if cfg.get("responsavel_padrao") not in ids:
            cfg["responsavel_padrao"] = ids[0] if ids else None
    if "responsavel_padrao" in corpo:
        ids = [r["id"] for r in cfg["responsaveis"] if r["assina"]]
        if corpo["responsavel_padrao"] not in ids:
            raise HTTPException(422, "Responsável padrão não está no cadastro de quem assina laudo.")
        cfg["responsavel_padrao"] = corpo["responsavel_padrao"]
    if "laudo" in corpo:
        motor = (corpo["laudo"] or {}).get("motor")
        if motor not in MOTORES_LAUDO:
            raise HTTPException(422, "Motor do laudo deve ser reportlab ou typst.")
        if motor == "typst":
            from app import laudo_typst

            if (falta := laudo_typst.disponivel()) is not None:
                raise HTTPException(422, f"O Typst não carrega neste computador: {falta}")
        cfg["laudo"] = {"motor": motor}
    if "tema" in corpo:
        if corpo["tema"] not in ("sistema", "claro", "escuro"):
            raise HTTPException(422, "Tema deve ser sistema, claro ou escuro.")
        cfg["tema"] = corpo["tema"]
    if "criterio" in corpo:
        cfg["criterios"] = None if corpo["criterio"] is None else _validar_criterios(corpo["criterio"])
    if "componentes" in corpo:
        cfg["componentes"] = {} if corpo["componentes"] is None else _validar_componentes(corpo["componentes"])
    _salvar_config(cfg)
    if "responsaveis" in corpo:  # quem saiu do time, ficou sem senha ou trocou de senha sai das sessões abertas
        armazenamento.encerrar_sessoes_fora({r["id"] for r in cfg["responsaveis"] if acesso.pode_entrar(r)})
        for id_ in trocaram:
            armazenamento.encerrar_sessoes_de(id_, menos=getattr(request.state, "sessao", None))
    if "criterio" in corpo or "componentes" in corpo:
        _recalcular_todas()
    return configuracoes(request)


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
    configuracao=lambda: _config_monitor(),
    salvar_alerta=lambda alerta: armazenamento.salvar_alerta(alerta),
    alertas_recentes=lambda: armazenamento.alertas(50),
    pasta_estado=lambda: PASTA_DADOS,
)


def _config_monitor() -> dict:
    """Configuração do monitor com quem recebe vindo do time (Configurações › Empresa e time)."""
    cfg = _config()
    return {**cfg["monitoramento"], "destinatarios": _destinatarios(cfg)}


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
    return {"config": _config_monitor(), "estado": _estado_monitor(), "disponivel": monitoramento.DISPONIVEL}


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
        if ligando:
            _preaquecer()
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
    pior = max(itens, key=lambda it: (analise.NIVEIS.get(it["resumo"]["severidade"], {"ordem": -1})["ordem"], it["criado_em"]))
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
    d["modelo_ativo"] = _modelo_termico()
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


def _mudancas_pendencia(a: dict, corpo: dict) -> list[str]:
    """Campos que o pedido muda de fato (a tela manda todos, inclusive os que ficaram iguais)."""
    atual = pendencias.montar({**a, "destaque": _destaque(a), "data_captura": (a.get("metadados") or {}).get("data_hora", "")})
    mudou = []
    if "status" in corpo and corpo["status"] != atual["status"]:
        mudou.append("status")
    if "prazo" in corpo and str(corpo["prazo"] or "")[:10] not in ((atual["prazo"], "") if atual["prazo_padrao"] else (atual["prazo"],)):
        mudou.append("prazo")
    for campo in ("ordem_servico", "responsavel"):
        if campo in corpo and str(corpo[campo] or "").strip() != (atual[campo] or ""):
            mudou.append(campo)
    return mudou


@app.put("/api/analises/{id_}/acompanhamento")
def acompanhar(request: Request, id_: str, corpo: dict = Body(...)) -> dict:
    """Situação da anomalia: aberta, programada (com OS), corrigida, verificada ou descartada.

    O técnico acompanha as pendências de atenção e de programar; nas urgentes e imediatas só deixa nota.
    """
    with _trava:
        a = armazenamento.obter(id_)
        if a is None:
            raise HTTPException(404, "Inspeção não encontrada.")
        if a["resumo"]["severidade"] == "normal":
            raise HTTPException(422, "Esta inspeção está normal: não há anomalia para acompanhar.")
        if (not acesso.pode(request, "revisao") and a["resumo"]["severidade"] in acesso.SEVERIDADES_SO_ENGENHEIRO
                and _mudancas_pendencia(a, corpo)):
            raise HTTPException(403, "Pendência urgente ou imediata: só engenheiro muda situação, prazo, OS ou responsável. "
                                     "Você pode deixar uma nota.")
        quem = acesso.usuario(request)
        try:
            pendencias.atualizar(a, corpo, autor=quem["nome"] if quem else None)
        except ValueError as erro:
            raise HTTPException(422, str(erro)) from erro
        armazenamento.salvar(a)
    return next(p for p in pendencias.listar(armazenamento.listar()) if p["id"] == id_)


# ---------------------------------------------------------------- rotas: equipamentos (histórico e tendência)


@app.get("/api/analises/{id_}/vizinhas")
def vizinhas(id_: str) -> dict:
    """A inspeção anterior e a seguinte do mesmo equipamento, pela data da captura."""
    itens = armazenamento.listar()
    atual = next((it for it in itens if it["id"] == id_), None)
    if atual is None:
        raise HTTPException(404, "Inspeção não encontrada.")
    chave = _chave_de(atual)
    if chave == equipamentos.SEM_EQUIPAMENTO:
        return {"anterior": None, "seguinte": None, "posicao": None, "total": 0}
    mesmas = sorted((it for it in itens if _chave_de(it) == chave), key=lambda it: equipamentos.ponto(it)["data"])
    i = next(k for k, it in enumerate(mesmas) if it["id"] == id_)
    resumo = lambda it: it and {**equipamentos.ponto(it), "arquivo": it["arquivo"]}  # noqa: E731
    return {"anterior": resumo(mesmas[i - 1]) if i > 0 else None, "seguinte": resumo(mesmas[i + 1]) if i + 1 < len(mesmas) else None,
            "posicao": i + 1, "total": len(mesmas), "atual": resumo(atual)}


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
    """Detector, critério e termômetro de um vídeo; devolve a função que analisa cada quadro.

    Ao vivo a velocidade manda: usa a versão rápida (INT8) do modelo escolhido, se houver.
    """
    det = _ao_vivo(_detector(opcoes.get("modelo")))
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


@app.post("/api/videos/{id_}/gravar-pesos")
def gravar_pesos_video(id_: str, corpo: dict = Body(...)) -> dict:
    """Memoriza pesos multi-ângulo de um equipamento a partir de um vídeo processado."""
    try:
        info_vid = _video(videos.obter, id_, 0)
    except KeyError as e:
        raise HTTPException(404, "Vídeo não encontrado.") from e
    pasta_vid = PASTA_DADOS / "videos" / id_
    arq_video = next(pasta_vid.glob("original.*"), None)
    bib = _biblioteca_contexto()
    try:
        return bib.gravar_de_video(
            caminho_video=arq_video or pasta_vid,
            nome=corpo.get("nome") or f"Ativo de {id_}",
            classe=corpo.get("classe", "equipamento"),
            caixa_inicial=corpo.get("caixa"),
            quadro_n=corpo.get("quadro_n"),
            altura_cm=corpo.get("altura_cm"),
            largura_cm=corpo.get("largura_cm"),
            comprimento_cm=corpo.get("comprimento_cm"),
            quadros_analisados=info_vid.get("quadros"),
            id_video=id_,
        )
    except ValueError as erro:
        raise HTTPException(422, str(erro)) from erro


@app.post("/api/videos/{id_}/reconhecer-biblioteca")
def reconhecer_biblioteca_video(id_: str, corpo: dict = Body(default={})) -> dict:
    """Reconhece ativos da biblioteca no vídeo informado."""
    try:
        info_vid = _video(videos.obter, id_, 0)
    except KeyError as e:
        raise HTTPException(404, "Vídeo não encontrado.") from e
    pasta_vid = PASTA_DADOS / "videos" / id_
    arq_video = next(pasta_vid.glob("original.*"), None)
    bib = _biblioteca_contexto()
    reconhecidos = bib.reconhecer_em_video(
        caminho_video_ou_quadros=arq_video or pasta_vid,
        quadros_analisados=info_vid.get("quadros"),
        pasta_quadros=pasta_vid / "quadros",
    )
    return {"video_id": id_, "reconhecidos": reconhecidos}



@app.get("/api/alertas/{id_}/whatsapp")
def whatsapp_alerta(id_: str) -> dict:
    alerta = armazenamento.alerta(id_)
    if alerta is None:
        raise HTTPException(404, "Alerta não encontrado.")
    destinatarios = monitoramento.para_severidade(_destinatarios(), alerta["severidade"])
    return {"mensagem": alerta["mensagem"], "links": monitoramento.links_whatsapp(alerta["mensagem"], destinatarios)}


# ---------------------------------------------------------------- medição em foto comum (nucleo/medicao)

_trava_medicao = threading.Lock()
LIMITE_FOTO_MEDICAO = 40 * 1024 * 1024
LIMITE_VIDEO_MEDICAO = 100 * 1024 * 1024  # vídeo curto do celular para medir (alguns segundos)


def _json_form(texto: str | None, nome: str) -> dict | None:
    if texto is None or not texto.strip():
        return None
    try:
        valor = json.loads(texto)
    except json.JSONDecodeError:
        raise HTTPException(422, f"O campo {nome} não é um JSON válido.")
    if not isinstance(valor, dict):
        raise HTTPException(422, f"O campo {nome} precisa ser um objeto.")
    return valor


def _validar_pista_medicao(p: dict | None, nome: str, exige_tamanho: bool = False) -> dict:
    if not p:
        raise HTTPException(422, f"Informe {nome}: um ponto, uma caixa ou dois pontos.")

    def numeros(v, n):
        if not isinstance(v, (list, tuple)) or len(v) != n or not all(isinstance(x, (int, float)) for x in v):
            raise HTTPException(422, f"{nome}: esperava {n} números.")
        return [float(x) for x in v]

    saida: dict = {}
    if exige_tamanho and "auto" in p:  # referência achada sozinha pela cor (post-it); tamanho padrão do tipo
        from nucleo.medicao.referencia_auto import REFERENCIAS_AUTO

        if p["auto"] not in REFERENCIAS_AUTO:
            raise HTTPException(422, f"Referência automática desconhecida: {p['auto']}.")
        saida["auto"] = p["auto"]
        p = {"tamanho_cm": REFERENCIAS_AUTO[p["auto"]]["lado_cm"], "medida": "lado", **p}
    elif exige_tamanho and "cantos" in p:
        cantos = p["cantos"]
        if not isinstance(cantos, list) or len(cantos) != 4:
            raise HTTPException(422, f"{nome}: são 4 cantos.")
        saida["cantos"] = [numeros(c, 2) for c in cantos]
        p = {"medida": "lado", **p}
    elif "pontos" in p:
        par = p["pontos"]
        if not isinstance(par, (list, tuple)) or len(par) != 2:
            raise HTTPException(422, f"{nome}: \"pontos\" precisa de dois pontos.")
        saida["pontos"] = [numeros(par[0], 2), numeros(par[1], 2)]
    elif "caixa" in p:
        x0, y0, x1, y1 = numeros(p["caixa"], 4)
        if x1 <= x0 or y1 <= y0:
            raise HTTPException(422, f"{nome}: caixa vazia.")
        saida["caixa"] = [x0, y0, x1, y1]
    elif "ponto" in p:
        saida["ponto"] = numeros(p["ponto"], 2)
    else:
        raise HTTPException(422, f"Informe {nome}: um ponto, uma caixa ou dois pontos.")
    if exige_tamanho:
        tam = p.get("tamanho_cm")
        if not isinstance(tam, (int, float)) or not (0 < tam < 100000):
            raise HTTPException(422, "Informe o tamanho real da referência, em cm.")
        saida["tamanho_cm"] = float(tam)
        medida = p.get("medida", "comprimento")
        if medida not in ("comprimento", "largura", "altura", "lado"):
            raise HTTPException(422, "A medida da referência é comprimento, largura, altura ou lado.")
        saida["medida"] = medida
        saida["nome"] = str(p.get("nome") or "")[:60]
        outro = p.get("outro_lado_cm")
        if isinstance(outro, (int, float)) and 0 < outro < 100000:
            saida["outro_lado_cm"] = float(outro)
    return saida


def _biblioteca_contexto():
    from nucleo.medicao.biblioteca_contexto import BibliotecaContexto

    return BibliotecaContexto(PASTA_DADOS / "medicao")


@app.get("/api/medicao/acelerador")
def medicao_acelerador_estado() -> dict:
    """Diagnóstico do motor híbrido de aceleração (Mojo SIMD / C-LAPACK Batch)."""
    from nucleo.aceleradores import estado_acelerador

    return estado_acelerador()


@app.post("/api/medicao/acelerador/benchmark")
def medicao_acelerador_benchmark() -> dict:
    """Executa benchmark em tempo real comparando motor legado vs aceleradores híbridos."""
    from nucleo.aceleradores import benchmark_hibrido

    return benchmark_hibrido()


@app.get("/api/medicao/estado")
def medicao_estado() -> dict:
    """Modelos da medição instalados e dispositivo (placa de vídeo ou processador)."""
    from nucleo.aceleradores import estado_acelerador
    from nucleo.medicao import REFERENCIAS_PRONTAS, modelos as modelos_medicao
    from nucleo.medicao.referencia_auto import REFERENCIAS_AUTO

    return {
        **modelos_medicao.estado(),
        "referencias": REFERENCIAS_PRONTAS,
        "referencias_auto": {k: {"nome": v["nome"], "lado_cm": v["lado_cm"]} for k, v in REFERENCIAS_AUTO.items()},
        "biblioteca_total": len(_biblioteca_contexto().listar()),
        "acelerador": estado_acelerador(),
    }


# instalação dos modelos da medição pela tela (pip + pesos): uma por vez, numa linha de execução à parte
_instalacao_medicao: dict = {"modelo": None, "etapa": None, "erro": None, "ativa": False}


@app.get("/api/medicao/instalar")
def medicao_instalacao() -> dict:
    """Como vai a instalação pedida em Modelos › Medição."""
    return dict(_instalacao_medicao)


@app.post("/api/medicao/instalar")
def medicao_instalar(corpo: dict = Body(...)) -> dict:
    """Instala os pacotes que faltam e baixa os pesos de ``da3``, ``moge`` ou ``sam`` (só os da lista, todos MIT
    ou Apache 2.0). Leva minutos: volta na hora e a tela acompanha por ``GET /api/medicao/instalar``."""
    from nucleo.medicao import instalar

    modelo = str(corpo.get("modelo"))
    if modelo not in instalar.PACOTES:
        raise HTTPException(400, "Modelo desconhecido (use da3, moge ou sam).")
    if _instalacao_medicao["ativa"]:
        raise HTTPException(409, "Já há uma instalação em andamento.")
    _instalacao_medicao.update(modelo=modelo, etapa="começando", erro=None, ativa=True)

    def rodar():
        import nucleo.medicao

        try:
            instalar.instalar(modelo, aviso=lambda etapa: _instalacao_medicao.update(etapa=etapa))
            nucleo.medicao.esquecer()  # o padrão pode ter mudado para o DA3
        except Exception as e:  # pip, rede, disco
            _instalacao_medicao["erro"] = str(e)
        finally:
            _instalacao_medicao["ativa"] = False

    threading.Thread(target=rodar, daemon=True, name="instalar-medicao").start()
    return dict(_instalacao_medicao)


@app.post("/api/medicao")
async def medicao(arquivo: UploadFile = File(...), pista: str = Form(...), referencia: str | None = Form(None)) -> dict:
    """Mede um objeto numa foto comum: pista (ponto, caixa ou dois pontos) e referência opcional
    (outra pista mais o tamanho real). Devolve as medidas em cm, a incerteza, o método e os tempos."""
    dados = await arquivo.read()
    if not dados:
        raise HTTPException(422, "O arquivo está vazio.")
    if len(dados) > LIMITE_FOTO_MEDICAO:
        raise HTTPException(413, "A foto passa de 40 MB.")
    p = _validar_pista_medicao(_json_form(pista, "pista"), "a pista")
    ref_bruta = _json_form(referencia, "referencia")
    ref = _validar_pista_medicao(ref_bruta, "a referência", exige_tamanho=True) if ref_bruta else None
    try:
        Image.open(io.BytesIO(dados)).verify()
    except Exception:
        raise HTTPException(422, "Não consegui abrir a foto.")
    from nucleo import medicao as medicao_mod

    def medir() -> dict:
        with _trava_medicao:
            return medicao_mod.medir(dados, p, ref).para_dict()

    try:
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(medir)
    except (ImportError, OSError) as e:
        raise HTTPException(503, f"Os modelos da medição não estão instalados ({type(e).__name__}: {e}).")
    except ValueError as e:
        raise HTTPException(422, str(e))


def _registro_medicao():
    from nucleo.medicao.registro import Registro

    global _registro_med
    if _registro_med is None or _registro_med.pasta != PASTA_DADOS / "medicao":
        _registro_med = Registro(PASTA_DADOS / "medicao")
    return _registro_med


_registro_med = None


def _modelo_medicao(modelo: str | None) -> list[str] | None:
    """O modelo de profundidade pedido na medida (``da3`` ou ``moge``), como lista para ``comparar``; sem pedido, todos."""
    if not modelo:
        return None
    from nucleo.medicao.modelos import MODELOS_PROFUNDIDADE

    if modelo not in MODELOS_PROFUNDIDADE:
        raise HTTPException(422, f"Modelo de profundidade desconhecido: {modelo}.")
    return [modelo]


def comparar_e_registrar(dados: bytes, pista: dict, referencia: dict | None, origem: str = "tela", como: str = "ambos",
                         registrar: bool = True, modelos: list[str] | None = None) -> dict:
    """Mede com os modelos de profundidade (sem e com referência). Só com ``registrar`` guarda a foto como chegou e a medida."""
    from nucleo import medicao as medicao_mod

    with _trava_medicao:
        r = medicao_mod.comparar(dados, pista, referencia, modelos=modelos)
    if not registrar:
        return r
    reg = _registro_medicao()
    foto = reg.guardar_foto(dados)
    entrada = reg.adicionar(foto, pista, referencia, r["resultados"], origem=origem, como=como)
    return {**r, "id": entrada["id"], "foto": foto, "erros": entrada["erros"]}


@app.post("/api/medicao/comparar")
async def medicao_comparar(arquivo: UploadFile = File(...), pista: str = Form(...), referencia: str | None = Form(None),
                           como: str = Form("ambos"), modelo: str | None = Form(None), registrar: bool = Form(False)) -> dict:
    """A mesma pista nos modelos de profundidade (DA3 e MoGe-2; ``modelo`` limita a um), sem e com referência.
    Não guarda nada: só com ``registrar=true`` a foto e a medida entram no registro (avaliação dos modelos)."""
    dados = await arquivo.read()
    if not dados:
        raise HTTPException(422, "O arquivo está vazio.")
    if len(dados) > LIMITE_FOTO_MEDICAO:
        raise HTTPException(413, "A foto passa de 40 MB.")
    p = _validar_pista_medicao(_json_form(pista, "pista"), "a pista")
    ref_bruta = _json_form(referencia, "referencia")
    ref = _validar_pista_medicao(ref_bruta, "a referência", exige_tamanho=True) if ref_bruta else None
    from nucleo.medicao.profundidade import abrir

    try:
        abrir(dados)
    except Exception:
        raise HTTPException(422, "Não consegui abrir a foto.")
    modelos = _modelo_medicao(modelo)
    from starlette.concurrency import run_in_threadpool

    try:
        return await run_in_threadpool(comparar_e_registrar, dados, p, ref, "tela", como if como in ("ambos", "com", "sem") else "ambos",
                                       registrar, modelos)
    except (ImportError, OSError) as e:
        raise HTTPException(503, f"Os modelos da medição não estão instalados ({type(e).__name__}: {e}).")
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/medicao/registro")
def medicao_registro(limite: int = 50) -> dict:
    """As últimas medições (da tela e do celular) e o erro mediano de cada modelo onde há valor real."""
    reg = _registro_medicao()
    return {"versao": reg.versao, "entradas": reg.entradas(max(1, min(limite, 500))), "resumo": reg.resumo()}


@app.put("/api/medicao/registro/{codigo}")
def medicao_real(codigo: str, corpo: dict = Body(...)) -> dict:
    """Informa a medida real (cm) e/ou o nome do objeto de uma medição: o registro calcula o erro de cada modelo."""
    real, nome = corpo.get("real"), corpo.get("nome")
    if real is not None and not isinstance(real, dict) or real is None and not isinstance(nome, str):
        raise HTTPException(422, "Informe as medidas reais, em cm, ou o nome do objeto.")
    try:
        return _registro_medicao().atualizar(codigo, real=real, nome=nome)
    except KeyError:
        raise HTTPException(404, "Medição não encontrada.")
    except (TypeError, ValueError):
        raise HTTPException(422, "Medida real inválida.")


@app.post("/api/medicao/previa")
async def medicao_previa(arquivo: UploadFile = File(...)) -> Response:
    """JPEG do mesmo tamanho (orientação do EXIF aplicada) para a tela mostrar foto que o navegador não abre (HEIC).
    Só para ver: a medida usa sempre o arquivo original."""
    from nucleo.medicao.profundidade import abrir

    dados = await arquivo.read()
    try:
        img = abrir(dados)
    except Exception:
        raise HTTPException(422, "Não consegui abrir a foto.")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return Response(buf.getvalue(), media_type="image/jpeg")


@app.get("/api/medicao/registro.csv")
def medicao_registro_csv() -> Response:
    """Todas as medições guardadas, para analisar numa planilha (separador ;, vírgula decimal)."""
    return Response("\ufeff" + _registro_medicao().csv(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="medicoes_pyron.csv"'})


@app.get("/api/medicao/fotos")
def medicao_fotos(limite: int = 200) -> dict:
    """As fotos guardadas para medir (da tela e do celular), da mais nova para a mais antiga."""
    return {"fotos": _registro_medicao().fotos(max(1, min(limite, 1000)))}


@app.post("/api/medicao/fotos")
async def medicao_guardar_foto(arquivo: UploadFile = File(...)) -> dict:
    """Guarda a foto aberta na tela como chegou (bytes originais), para ela ficar na faixa de fotos."""
    dados = await arquivo.read()
    if not dados or len(dados) > LIMITE_FOTO_MEDICAO:
        raise HTTPException(422, "Foto vazia ou maior que 40 MB.")
    return {"codigo": _registro_medicao().guardar_foto(dados)}


@app.get("/api/medicao/fotos/{codigo}/miniatura")
def medicao_miniatura(codigo: str) -> Response:
    """JPEG pequeno da foto guardada (também de HEIC), para a lista de medições."""
    from nucleo.medicao.profundidade import abrir

    caminho = _registro_medicao().caminho_foto(codigo)
    if caminho is None:
        raise HTTPException(404, "Foto não encontrada.")
    img = abrir(caminho)
    img.thumbnail((240, 240))
    saida = io.BytesIO()
    img.save(saida, "JPEG", quality=82)
    return Response(saida.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@app.get("/api/medicao/fotos/{codigo}")
def medicao_foto(codigo: str) -> Response:
    """A foto original, como chegou (para a tela abrir as fotos que vieram do celular)."""
    from fastapi.responses import FileResponse

    caminho = _registro_medicao().caminho_foto(codigo)
    if caminho is None:
        raise HTTPException(404, "Foto não encontrada.")
    return FileResponse(caminho)


@app.post("/api/medicao/referencia")
async def medicao_referencia(arquivo: UploadFile = File(...), tipo: str = Form("postit_rosa")) -> dict:
    """Acha sozinho, pela cor, a referência quadrada (post-it) na foto e devolve os 4 cantos. Sem modelo."""
    from nucleo.medicao import referencia_auto
    from nucleo.medicao.profundidade import abrir

    if tipo not in referencia_auto.REFERENCIAS_AUTO:
        raise HTTPException(422, f"Referência automática desconhecida: {tipo}.")
    dados = await arquivo.read()
    try:
        img = abrir(dados)
    except Exception:
        raise HTTPException(422, "Não consegui abrir a foto.")
    pronta = referencia_auto.REFERENCIAS_AUTO[tipo]
    achado = referencia_auto.achar(img, pronta["cor"])
    if achado is None:
        raise HTTPException(422, f"Não achei o {pronta['nome']} na foto.")
    return {"cantos": [[round(float(x), 2), round(float(y), 2)] for x, y in achado.cantos],
            "lado_cm": pronta["lado_cm"], "nome": pronta["nome"], "retangularidade": achado.retangularidade}


@app.post("/api/medicao/plano")
def medicao_plano(corpo: dict = Body(...)) -> dict:
    """Medir sem modelo: 4 cantos de um retângulo de tamanho conhecido (A4, cartão) e 2 pontos no mesmo plano.
    Só geometria (homografia); não precisa da foto nem dos pesos."""
    from nucleo.medicao import plano_ref

    cantos, tamanho, pontos = corpo.get("cantos"), corpo.get("tamanho_cm"), corpo.get("pontos")

    def pares(v, n):
        return (isinstance(v, list) and len(v) == n
                and all(isinstance(p, list) and len(p) == 2 and all(isinstance(x, (int, float)) for x in p) for p in v))

    if not pares(cantos, 4):
        raise HTTPException(422, "Marque os 4 cantos da referência.")
    if not pares(pontos, 2):
        raise HTTPException(422, "Marque os 2 pontos a medir.")
    if not (isinstance(tamanho, list) and len(tamanho) == 2 and all(isinstance(x, (int, float)) and 0 < x < 100000 for x in tamanho)):
        raise HTTPException(422, "Informe os dois lados da referência, em cm.")
    try:
        return plano_ref.medir(cantos, tamanho, pontos)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/medicao/video/keyframes")
async def medicao_video_keyframes(arquivo: UploadFile = File(...), max_keyframes: int = Form(5)) -> dict:
    """Extrai os quadros-chave mais nítidos e espaçados no tempo de um vídeo gravado."""
    dados = await arquivo.read()
    if not dados:
        raise HTTPException(422, "O arquivo de vídeo está vazio.")
    if len(dados) > 100 * 1024 * 1024:
        raise HTTPException(413, "O vídeo passa de 100 MB.")
    from nucleo.medicao import video_keyframes as vk

    try:
        keyframes = vk.selecionar_keyframes(dados, max_keyframes=max_keyframes)
    except Exception as e:
        raise HTTPException(422, f"Erro ao processar vídeo: {e}")

    import base64
    quadros = []
    for kf in keyframes:
        b64 = base64.b64encode(kf.bytes_jpeg).decode("ascii")
        quadros.append({
            **kf.para_dict(),
            "imagem_base64": f"data:image/jpeg;base64,{b64}",
        })
    return {"total": len(quadros), "keyframes": quadros}


@app.post("/api/medicao/video/medir")
async def medicao_video_medir(
    arquivo: UploadFile = File(...),
    pista: str = Form(...),
    referencia: str | None = Form(None),
    max_keyframes: int = Form(4),
) -> dict:
    """Mede objeto ao longo do vídeo com propagação de pista nos keyframes e consenso estatístico."""
    dados = await arquivo.read()
    if not dados:
        raise HTTPException(422, "O arquivo de vídeo está vazio.")
    if len(dados) > 100 * 1024 * 1024:
        raise HTTPException(413, "O vídeo passa de 100 MB.")
    p = _validar_pista_medicao(_json_form(pista, "pista"), "a pista")
    ref_bruta = _json_form(referencia, "referencia")
    ref = _validar_pista_medicao(ref_bruta, "a referência", exige_tamanho=True) if ref_bruta else None

    from nucleo.medicao import video_keyframes as vk

    def rodar():
        with _trava_medicao:
            return vk.medir_video(dados, p, ref, max_keyframes=max_keyframes)

    from starlette.concurrency import run_in_threadpool
    try:
        return await run_in_threadpool(rodar)
    except (ImportError, OSError) as e:
        raise HTTPException(503, f"Os modelos de medição não estão instalados ({type(e).__name__}: {e}).")
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/medicao/video/comparar")
async def medicao_video_comparar(
    arquivo: UploadFile = File(...),
    pista: str = Form(...),
    referencia: str | None = Form(None),
    como: str = Form("ambos"),
    max_keyframes: int = Form(4),
    modelo: str | None = Form(None),
    registrar: bool = Form(False),
) -> dict:
    """O vídeo nos modelos de profundidade (``modelo`` limita a um), sem e com referência: a pista vale no 1º quadro nítido
    e segue o objeto nos outros; o resultado de cada modelo e modo é a mediana dos quadros. Não guarda nada: só com
    ``registrar=true`` guarda o vídeo e registra a medida (foto: o 1º quadro)."""
    dados = await arquivo.read()
    if not dados:
        raise HTTPException(422, "O arquivo de vídeo está vazio.")
    if len(dados) > LIMITE_VIDEO_MEDICAO:
        raise HTTPException(413, "O vídeo passa de 100 MB.")
    p = _validar_pista_medicao(_json_form(pista, "pista"), "a pista")
    ref_bruta = _json_form(referencia, "referencia")
    ref = _validar_pista_medicao(ref_bruta, "a referência", exige_tamanho=True) if ref_bruta else None
    como = como if como in ("ambos", "com", "sem") else "ambos"
    extensao = Path(arquivo.filename or "").suffix.lower() or ".mp4"
    modelos = _modelo_medicao(modelo)

    def rodar():
        from nucleo import medicao as medicao_mod
        from nucleo.medicao import video_keyframes as vk

        comparar = medicao_mod.comparar if modelos is None else (lambda jpeg, pista, referencia: medicao_mod.comparar(jpeg, pista, referencia, modelos=modelos))
        with _trava_medicao:
            r = vk.comparar_video(dados, p, ref, max_keyframes=max(1, min(max_keyframes, 8)), comparar=comparar)
        if not registrar:
            r.pop("jpeg_primeiro")
            return r
        reg = _registro_medicao()
        codigo_video = reg.guardar_video(dados, extensao)
        foto = reg.guardar_foto(r.pop("jpeg_primeiro"))
        resultados = {modelo: {modo: {campo: v["valor"] for campo, v in c.items() if isinstance(v, dict)}
                               | {"desvio_cm": {campo[:-3]: v["desvio_padrao"] for campo, v in c.items() if isinstance(v, dict)},
                                  "n_quadros": c.get("total_quadros")}
                               for modo, c in modos.items()} for modelo, modos in r["consenso"].items()}
        entrada = reg.adicionar(foto, p, ref, resultados, origem="video", como=como,
                                video={"codigo": codigo_video, "quadros": r["n_keyframes"]})
        return {**r, "id": entrada["id"], "foto": foto, "video": codigo_video, "erros": entrada["erros"]}

    from starlette.concurrency import run_in_threadpool

    try:
        return await run_in_threadpool(rodar)
    except (ImportError, OSError) as e:
        raise HTTPException(503, f"Os modelos de medição não estão instalados ({type(e).__name__}: {e}).")
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/medicao/videos/{codigo}")
def medicao_video(codigo: str) -> Response:
    """O vídeo guardado, como chegou (para a tela abrir o que veio do celular)."""
    from fastapi.responses import FileResponse

    caminho = _registro_medicao().caminho_video(codigo)
    if caminho is None:
        raise HTTPException(404, "Vídeo não encontrado.")
    return FileResponse(caminho)


# ---------------------------------------------------------------- biblioteca de contexto e medição 2D (nucleo/medicao/biblioteca_contexto.py)


@app.get("/api/medicao/biblioteca")
def listar_biblioteca_medicao() -> dict:
    """Lista todos os equipamentos e padrões salvos na biblioteca de contexto."""
    return {"itens": _biblioteca_contexto().listar()}


@app.get("/api/medicao/biblioteca/{id_}/miniatura.jpg")
def miniatura_biblioteca_medicao(id_: str) -> Response:
    """Retorna a miniatura em JPEG do ativo registrado na biblioteca."""
    bib = _biblioteca_contexto()
    caminho = bib.caminho_miniatura(id_)
    if not caminho.exists():
        raise HTTPException(404, "Miniatura não encontrada.")
    return Response(caminho.read_bytes(), media_type="image/jpeg")


@app.delete("/api/medicao/biblioteca/{id_}")
def remover_item_biblioteca_medicao(id_: str) -> dict:
    """Remove um item da biblioteca de contexto."""
    bib = _biblioteca_contexto()
    if not bib.remover(id_):
        raise HTTPException(404, "Item não encontrado na biblioteca.")
    return {"ok": True, "id": id_}


@app.post("/api/medicao/video/gravar-pesos")
async def gravar_pesos_video_upload(
    arquivo: UploadFile = File(...),
    nome: str = Form(...),
    classe: str = Form("equipamento"),
    pista: str | None = Form(None),
    altura_cm: float | None = Form(None),
    largura_cm: float | None = Form(None),
    comprimento_cm: float | None = Form(None),
) -> dict:
    """Recebe vídeo por upload e grava a assinatura multi-ângulo do ativo na biblioteca."""
    dados = await arquivo.read()
    if not dados:
        raise HTTPException(422, "O arquivo de vídeo está vazio.")
    pista_dict = _json_form(pista, "pista") if pista else None
    caixa = pista_dict.get("caixa") if isinstance(pista_dict, dict) else None
    bib = _biblioteca_contexto()
    try:
        return bib.gravar_de_video(
            bytes_video=dados,
            nome=nome,
            classe=classe,
            caixa_inicial=caixa,
            altura_cm=altura_cm,
            largura_cm=largura_cm,
            comprimento_cm=comprimento_cm,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/medicao/contexto-2d")
async def medicao_contexto_2d(
    arquivo: UploadFile = File(...),
    pista: str | None = Form(None),
    id_contexto: str | None = Form(None),
) -> dict:
    """Mede objeto em imagem 2D única por ancoragem nos pesos e contexto multi-ângulo memorizados."""
    dados = await arquivo.read()
    if not dados:
        raise HTTPException(422, "A imagem enviada está vazia.")
    pista_dict = _json_form(pista, "pista") if pista else None
    bib = _biblioteca_contexto()
    try:
        return bib.medir_imagem_2d(
            imagem_bytes_ou_rgb=dados,
            pista=pista_dict,
            id_contexto=id_contexto,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e



# ---------------------------------------------------------------- cadastro de medidas e câmeras (app/cadastro_medidas.py)


def _cadastro():
    from app.cadastro_medidas import Cadastro

    return Cadastro(PASTA_DADOS)


def _erro_cadastro(func):
    from app.cadastro_medidas import ErroCadastro

    try:
        return func()
    except ErroCadastro as e:
        raise HTTPException(422, str(e))


@app.get("/api/cadastro/medidas")
def cadastro_medidas(equipamento: str | None = None, status: str | None = None) -> list:
    return _cadastro().medidas(equipamento, status)


@app.post("/api/cadastro/medidas")
def cadastro_propor(corpo: dict = Body(...)) -> dict:
    """Registra uma medida como proposta (do programa ou de uma pessoa). Só vale depois de validada."""
    campos = ("equipamento_chave", "componente", "medida", "valor_cm", "metodo", "criado_por", "incerteza_cm",
              "classe", "fase", "origem", "substitui_id", "nota")
    return _erro_cadastro(lambda: _cadastro().propor(**{k: corpo.get(k) for k in campos if k in corpo}))


@app.post("/api/cadastro/medidas/{medida_id}/validar")
def cadastro_validar(medida_id: int, corpo: dict = Body(...)) -> dict:
    return _erro_cadastro(lambda: _cadastro().validar(medida_id, corpo.get("engenheiro"), corpo.get("registro"), corpo.get("nota")))


@app.post("/api/cadastro/medidas/{medida_id}/rejeitar")
def cadastro_rejeitar(medida_id: int, corpo: dict = Body(...)) -> dict:
    return _erro_cadastro(lambda: _cadastro().rejeitar(medida_id, corpo.get("engenheiro"), corpo.get("registro"), corpo.get("motivo")))


@app.get("/api/cadastro/equipamentos/{chave}/fases")
def cadastro_fases(chave: str) -> list:
    """Mesma classe e medida nas fases A, B e C: a diferença que o engenheiro vê antes de validar."""
    return _cadastro().conferir_fases(chave)


@app.get("/api/cadastro/cameras")
def cadastro_cameras() -> list:
    return _cadastro().cameras()


@app.post("/api/cadastro/cameras/ficha")
def cadastro_camera_ficha(corpo: dict = Body(...)) -> dict:
    """Câmera pela ficha técnica (térmica): resolução e campo de visão horizontal."""
    from nucleo.medicao.camera import perfil_da_ficha

    try:
        p = perfil_da_ficha(str(corpo["nome"]), int(corpo["largura"]), int(corpo["altura"]),
                            float(corpo["fov_horizontal_graus"]), corpo.get("tipo", "termica"), corpo.get("modelo", ""))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "Informe nome, largura, altura e fov_horizontal_graus.")
    return _cadastro().salvar_camera(p)


@app.post("/api/cadastro/cameras/calibrar")
async def cadastro_camera_calibrar(nome: str = Form(...), modelo: str = Form(""), quadrado_mm: float = Form(25.0),
                                   fotos: list[UploadFile] = File(...)) -> dict:
    """Calibra a lente com a folha ChArUco em várias fotos (5 a 20) e guarda o perfil da câmera."""
    from nucleo.medicao import camera as camera_mod

    dados = [await f.read() for f in fotos]
    try:
        p = camera_mod.calibrar(nome, dados, modelo=modelo, quadrado_mm=quadrado_mm,
                                marcador_mm=quadrado_mm * 18 / 25)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return _cadastro().salvar_camera(p)


@app.post("/api/cadastro/cameras/{nome}/posicao")
async def cadastro_camera_posicao(nome: str, arquivo: UploadFile = File(...), quadrado_mm: float = Form(25.0),
                                  equipamento_chave: str | None = Form(None)) -> dict:
    """Câmera fixa: a foto de instalação com a folha. Guarda o plano de referência e a cena para conferir."""
    from nucleo.medicao import camera as camera_mod

    cad = _cadastro()
    perfil = _erro_cadastro(lambda: cad.camera(nome))
    try:
        pos = camera_mod.registrar_posicao(perfil, await arquivo.read(), quadrado_mm=quadrado_mm,
                                           marcador_mm=quadrado_mm * 18 / 25)
    except ValueError as e:
        raise HTTPException(422, str(e))
    cad.salvar_posicao(pos, equipamento_chave)
    return pos.para_dict()


@app.post("/api/cadastro/cameras/{nome}/conferir")
async def cadastro_camera_conferir(nome: str, arquivo: UploadFile = File(...)) -> dict:
    """A câmera fixa continua na posição calibrada?"""
    from nucleo.medicao import camera as camera_mod

    pos = _cadastro().posicao(nome)
    if pos is None:
        raise HTTPException(404, "Esta câmera não tem posição fixa registrada.")
    return camera_mod.conferir_posicao(pos, await arquivo.read())


@app.post("/api/cadastro/escala")
def cadastro_escala(corpo: dict = Body(...)) -> dict:
    """Escala de uma foto por um componente cadastrado e validado: câmera, medida e tamanho dele em pixels."""
    from nucleo.medicao.camera import escala_por_referencia

    cad = _cadastro()
    m = _erro_cadastro(lambda: cad.medida(int(corpo.get("medida_id", 0))))
    if m["status"] != "validada":
        raise HTTPException(422, f"A medida {m['id']} está {m['status']}: só medida validada por engenheiro dá escala.")
    perfil = _erro_cadastro(lambda: cad.camera(str(corpo.get("camera"))))
    try:
        largura, altura = int(corpo["largura"]), int(corpo["altura"])
        r = escala_por_referencia(perfil.para_resolucao(largura, altura), float(corpo["comprimento_px"]),
                                  m["valor_cm"], m["incerteza_cm"] or 0.0)
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(422, f"Informe largura, altura e comprimento_px da foto ({e}).")
    return r | {"referencia": {k: m[k] for k in ("id", "equipamento_chave", "componente", "medida", "valor_cm", "validado_por")}}


# ---------------------------------------------------------------- câmera do celular


def _detector_imagem() -> detectores.Detector:
    """O modelo que olha a imagem colorida: o ativo, se for um; senão o primeiro instalado.

    A foto do celular não tem temperatura, então a regra de pontos quentes não acha nada nela.
    Ao vivo, cada milissegundo conta: vai o mesmo modelo na placa de vídeo, se houver (``_ao_vivo``).
    """
    ativo = _detector(None)
    if isinstance(ativo, detectores.Combinado):
        ativo = ativo.partes[0]
    candidatos = [d for d in detectores.listar(PASTA_MODELOS) if d.precisa_imagem and d.tipo == "aprendizado"]
    base = ativo if ativo.precisa_imagem and ativo.tipo == "aprendizado" else next(iter(candidatos), None)
    if base is None:
        raise ValueError("Nenhum modelo que olha a imagem colorida está instalado. Instale um em Modelos "
                         "(o de para-raios, por exemplo).")
    return _ao_vivo(base)


def _original(det: detectores.Detector) -> detectores.Detector:
    """O modelo de onde a versão rápida (INT8) saiu; o próprio, se não for uma."""
    origem = (det.cartao.get("otimizacao") or {}).get("origem")
    return next((d for d in detectores.listar(PASTA_MODELOS) if d.id == origem), det) if origem else det


def _ao_vivo(det: detectores.Detector) -> detectores.Detector:
    """O detector para o ao vivo (celular e vídeo): o mesmo modelo na placa de vídeo, se houver.

    A placa carrega em outro fio na primeira vez (``nucleo/detectores/placa.py``); até lá, ou se ela
    não estiver disponível, vai a versão rápida (INT8) na CPU. Vale também para o combinado com os
    pontos quentes.
    """
    combinado = isinstance(det, detectores.Combinado)
    na_placa = placa.variante(_original(det.partes[0] if combinado else det))
    if na_placa is None:
        return _versao_rapida(det)
    return detectores.Combinado(na_placa, det.partes[1]) if combinado else na_placa


def _versao_rapida(det: detectores.Detector) -> detectores.Detector:
    """A versão rápida (INT8, ``ml/otimizar.py``) do mesmo modelo, se houver; senão o próprio.

    Vale também para o modelo combinado com os pontos quentes. Usada onde a velocidade manda (celular e
    vídeo); as análises de foto ficam com o modelo escolhido, que é o que o laudo registra.
    """
    combinado = isinstance(det, detectores.Combinado)
    base = det.partes[0] if combinado else det
    if base.cartao.get("otimizacao"):
        return det
    todos = detectores.listar(PASTA_MODELOS)
    rapida = next((d for d in todos if d.tipo == "aprendizado" and (d.cartao.get("otimizacao") or {}).get("origem") == base.id), None)
    if rapida is None:
        return det
    if combinado:
        return next((d for d in todos if d.id == f"{rapida.id}+{det.partes[1].id}"), det)
    return rapida


def _celular_modelo() -> dict:
    det = _detector_imagem()
    return {"id": det.id, "nome": det.nome, "classes": det.classes,
            "onde": placa.situacao(_original(det.partes[0] if isinstance(det, detectores.Combinado) else det))}


CONFIANCA_CELULAR = 0.5  # foto de tela tem reflexo e moiré: só caixas com boa confiança
# Barra de cores no quadro do celular: lida em paralelo com o detector (outro fio), com os números
# guardados entre quadros (o OCR só roda quando eles parecem ter mudado).
leitor_escala_celular = barra.LeitorAoVivo()
_fio_escala = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pyron-escala")


def _celular_detectar(rgb: np.ndarray) -> tuple[list[dict], dict]:
    """Peças achadas no quadro, só dentro da área que parece um termograma.

    O modelo foi treinado só com termogramas: no quadro inteiro (a sala, a mesa) ele vê para-raios em
    qualquer coisa. No recorte, ele também vê o termograma maior e na proporção em que aprendeu.
    """
    det = _detector_imagem()
    area = enquadrar.achar_termograma(rgb)
    if area is None:
        return [], {"area": None}
    recorte = np.ascontiguousarray(rgb[area.y0:area.y1, area.x0:area.x1])
    h, w = recorte.shape[:2]
    img_lab = barra.lab(recorte)
    leitura = _fio_escala.submit(leitor_escala_celular.ler, recorte, img_lab)
    saida = []
    for d in det.detectar(np.zeros((h, w), dtype=np.float32), recorte):
        if d.confianca < CONFIANCA_CELULAR:
            continue
        nome = det.nomes.get(d.classe) or NOMES_CLASSES.get(d.classe, d.classe)
        saida.append({"classe": d.classe, "nome": nome, "confianca": round(float(d.confianca), 3), "caixa": [float(v) for v in d.caixa]})
    escala, achada, estado = leitura.result()
    for s in saida:
        if escala is not None:
            t, acima = barra.maxima(img_lab, escala, s["caixa"])
            if t is not None:
                s["tmax"], s["tmax_acima"] = round(t, 1), acima
        x0, y0, x1, y1 = s["caixa"]
        s["caixa"] = [x0 + area.x0, y0 + area.y0, x1 + area.x0, y1 + area.y0]
    return saida, {"area": area.caixa(), "escala": _escala_celular(escala, achada, estado, area)}


def _escala_celular(escala, achada, estado: str, area) -> dict | None:
    """O que o celular e o computador mostram da barra: onde está, se os números já foram lidos e os limites."""
    if achada is None:
        return None
    x0, y0, x1, y1 = achada.caixa()
    info = {"estado": estado, "barra": [x0 + area.x0, y0 + area.y0, x1 + area.x0, y1 + area.y0]}
    if escala is not None:
        info.update(min=round(escala.t_min, 1), max=round(escala.t_max, 1))
    return info


def _celular_capturar(dados: bytes, nome: str) -> dict:
    """Salva só a área do termograma: é ela que vira a imagem da inspeção."""
    det = _detector_imagem()
    rgb = celular.ler_imagem(dados)
    area = enquadrar.achar_termograma(rgb)
    if area is None:
        raise ValueError("Nenhuma imagem térmica no quadro. Aponte para o termograma e tente de novo.")
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(rgb[area.y0:area.y1, area.x0:area.x1])).save(buf, format="JPEG", quality=92)
    with _trava:
        a = _nova_analise(buf.getvalue(), nome, det.id, fonte="celular", somente_imagem=True)
    return {"id": a["id"], "arquivo": a["arquivo"], "regioes": len(a["regioes"]), "nomes": [r["nome"] for r in a["regioes"]]}


def _celular_guardar_foto(dados: bytes) -> str:
    """Foto que o celular mandou para medir: confere que abre e guarda os bytes como chegaram."""
    from nucleo.medicao.profundidade import abrir

    try:
        abrir(dados)
    except Exception as erro:
        raise ValueError("Não consegui abrir a foto.") from erro
    return _registro_medicao().guardar_foto(dados)


def _celular_previa(codigo: str) -> bytes:
    """JPEG do mesmo tamanho da foto (para o navegador do celular mostrar HEIC); os toques valem no original."""
    from nucleo.medicao.profundidade import abrir

    caminho = _registro_medicao().caminho_foto(codigo)
    buf = io.BytesIO()
    abrir(caminho.read_bytes()).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


celular_modo = celular.ModoCelular(PASTA_DADOS / "celular", _celular_detectar, _celular_capturar, _celular_modelo,
                                   guardar_foto=_celular_guardar_foto, previa=_celular_previa,
                                   guardar_video=lambda dados, ext: _registro_medicao().guardar_video(dados, ext))
INTERVALO_ESPELHO_S = 1 / 30  # o espelho confere se chegou quadro novo até 30 vezes por segundo


@app.get("/api/celular")
def celular_estado() -> dict:
    return celular_modo.estado()


@app.post("/api/celular/ligar")
def celular_ligar(para: str = "camera") -> dict:
    """Abre o servidor do celular na rede local (HTTPS, só as rotas do celular, com código no link).
    ``para=medicao``: só para medir objetos em foto, sem exigir o detector térmico."""
    if acesso.modo_servidor():
        raise HTTPException(409, "O modo celular só liga no modo local (o servidor do celular abre outra porta na rede).")
    try:
        if para != "medicao":
            _detector_imagem()
        leitor_escala_celular.reiniciar()
        celular_modo.ligar()
    except ValueError as erro:
        raise HTTPException(409, str(erro)) from erro
    except (RuntimeError, OSError) as erro:
        raise HTTPException(503, str(erro)) from erro
    return celular_modo.estado()


@app.post("/api/celular/desligar")
def celular_desligar() -> dict:
    celular_modo.desligar()
    return celular_modo.estado()


@app.get("/api/celular/qr.png")
def celular_qr(medir: bool = False) -> Response:
    """QR do link do celular; ``medir=1``: o link da página de medir objetos em foto."""
    if not celular_modo.url:
        raise HTTPException(404, "O modo celular está desligado.")
    url = celular_modo.url_medir if medir else celular_modo.url
    return Response(celular.qr_png(url), media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/medicao/celular")
def medicao_celular() -> dict:
    """A conexão com o celular para medir: ligada, o link e as fotos que chegaram (a mais nova primeiro)."""
    return celular_modo.estado_medicao()


@app.websocket("/api/celular/ws")
async def celular_ao_vivo(ws: WebSocket) -> None:
    """Vídeo ao vivo do celular no computador: cada quadro novo e cada resultado novo.

    Quadro: mensagem binária com o cabeçalho do celular (número e posição da câmera) e o JPEG.
    Resultado: JSON com as peças e o número e a posição do quadro analisado, para o computador levar
    as caixas junto com a câmera nos quadros seguintes. Só o próprio computador alcança este servidor;
    o celular fala com o servidor à parte (outro laço de eventos), por isso aqui se confere o estado.
    """
    import anyio

    await ws.accept()
    # Grupo de tarefas do anyio (o que o Starlette usa): quando uma das duas acaba, a outra é cancelada.
    # Com tarefas soltas do asyncio, o cancelamento de quem fecha a conexão chegava no meio da limpeza.
    async with anyio.create_task_group() as grupo:

        async def mandar() -> None:
            visto_quadro = visto_resultado = -1
            try:
                while True:
                    vivo, ultimo = celular_modo.vivo, celular_modo.ultimo
                    if vivo.seq != visto_quadro and vivo.jpeg:
                        visto_quadro = vivo.seq
                        await ws.send_bytes(celular.cabecalho(vivo.quadro, vivo.posicao) + vivo.jpeg)
                    if ultimo.seq != visto_resultado and ultimo.quando:
                        visto_resultado = ultimo.seq
                        await ws.send_json({"deteccoes": ultimo.deteccoes, "area": ultimo.area, "escala": ultimo.escala,
                                            "seq": ultimo.seq, "ms": ultimo.ms, "quadro": ultimo.quadro, "posicao": ultimo.posicao})
                    await anyio.sleep(INTERVALO_ESPELHO_S)
            except (WebSocketDisconnect, RuntimeError):
                pass
            finally:
                grupo.cancel_scope.cancel()

        async def ouvir() -> None:  # só para saber quando a tela fecha: o computador não manda nada
            try:
                while (await ws.receive())["type"] != "websocket.disconnect":
                    pass
            finally:
                grupo.cancel_scope.cancel()

        grupo.start_soon(mandar)
        grupo.start_soon(ouvir)


# ---------------------------------------------------------------- ciclo de vida (janela do aplicativo)

sinais: dict = {"clientes": {}, "algum": False, "encerrar": False}


@app.post("/api/sinal")
def sinal(cliente: str = "lancador", saindo: bool = False) -> dict:
    """Cada janela avisa que está aberta (a cada 20 s) ou que está sendo fechada. Não existe no modo servidor."""
    if acesso.modo_servidor():
        raise HTTPException(404, "No modo servidor o Pyron não se desliga sozinho.")
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
    """A interface é local: sempre servir a versão mais nova dos arquivos (atualizações entram sem limpar cache).

    No modo servidor, a interface anterior (/antiga) não existe: ela não conhece o login.
    """
    if acesso.modo_servidor() and request.url.path.startswith("/antiga"):
        return RedirectResponse("/")
    resposta = await chamar_proximo(request)
    if not request.url.path.startswith("/api/"):
        resposta.headers["Cache-Control"] = "no-cache"
    return resposta


@app.get("/nova", include_in_schema=False)
@app.get("/nova/", include_in_schema=False)
def interface_nova() -> RedirectResponse:
    """Endereço da interface nova enquanto ela era construída: agora ela é a principal."""
    return RedirectResponse("/")


@app.get("/antiga", include_in_schema=False)
def interface_antiga() -> RedirectResponse:
    return RedirectResponse("/antiga/")


# Interface principal em "/" (app/interface); a antiga (app/estatico) fica em "/antiga" por uma versão.
# A marca é servida das duas: a nova usa /marca/…, a antiga caminhos relativos.
app.mount("/antiga", StaticFiles(directory=PASTA_APP / "estatico", html=True), name="estatico")
app.mount("/marca", StaticFiles(directory=PASTA_APP / "estatico" / "marca"), name="marca")
app.mount("/", StaticFiles(directory=PASTA_APP / "interface", html=True), name="interface")
