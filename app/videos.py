"""Simulação de câmera ao vivo: vídeos enviados e analisados quadro a quadro numa thread.

Cada vídeo fica em ``dados_app/videos/<id>/``:

- ``original.<ext>``: o arquivo enviado;
- ``estado.json``: opções, progresso e resumo (pequeno, para a lista);
- ``quadros.jsonl``: uma linha por quadro analisado (tempo, latência, escala, caixas);
- ``quadros/NNNNN.jpg``: a imagem de cada quadro analisado, para a reprodução com as caixas.

Dois modos:

- ``ao_vivo``: o vídeo corre no relógio, como a câmera. Enquanto o modelo trabalha, os quadros que
  passam se perdem, e o resultado mostra quantos quadros por segundo o computador aguenta.
- ``intervalo``: um quadro a cada N segundos do vídeo, sem perder nenhum (pode levar mais tempo
  que o próprio vídeo).
"""

from __future__ import annotations

import json
import queue
import re
import shutil
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Callable

import numpy as np
from PIL import Image

from nucleo import video

ID_VALIDO = re.compile(r"[0-9a-f]{12}")
LIMITE_BYTES = 2 * 1024**3
MAXIMO_QUADROS = 1800
MODOS = ("ao_vivo", "intervalo")
ATIVOS = ("na_fila", "processando")
ORDEM_SEVERIDADE = ("normal", "atencao", "programar", "urgente", "imediato")


def opcoes_validas(modo: str, intervalo_s, velocidade, modelo: str | None, t_min, t_max) -> dict:
    """Confere as opções do formulário. ValueError com a explicação quando algo não serve."""
    if modo not in MODOS:
        raise ValueError("Modo desconhecido: use ao vivo ou um quadro a cada intervalo.")
    intervalo = float(intervalo_s or 0.5)
    vel = float(velocidade or 1.0)
    if not 0.05 <= intervalo <= 60:
        raise ValueError("Intervalo entre quadros de 0,05 a 60 segundos.")
    if not 0.25 <= vel <= 4:
        raise ValueError("Velocidade de 0,25× a 4×.")
    limites = None
    if t_min not in (None, "") or t_max not in (None, ""):
        try:
            limites = sorted((float(t_min), float(t_max)))
        except (TypeError, ValueError) as erro:
            raise ValueError("Informe o mínimo e o máximo da escala, ou deixe os dois em branco para ler da imagem.") from erro
        if limites[1] - limites[0] < 0.5 or not -40 <= limites[0] <= 2000:
            raise ValueError("A escala informada precisa ter ao menos 0,5 °C entre o mínimo e o máximo.")
    return {"modo": modo, "intervalo_s": intervalo, "velocidade": vel, "modelo": modelo or None, "limites": limites}


def resumir(quadros: list[dict], info: dict) -> dict:
    """Números do vídeo inteiro: ritmo real do modelo, latência e o que ele achou."""
    if not quadros:
        return {"analisados": 0}
    lat = np.array([q["ms"] for q in quadros if not q.get("preparo")] or [quadros[0]["ms"]], dtype=float)
    coberto = max(quadros[-1]["tempo_s"] - quadros[0]["tempo_s"], 1.0 / max(info.get("fps") or 30, 1))
    com_t = [q for q in quadros if q.get("t_max") is not None]
    quente = max(com_t, key=lambda q: q["t_max"]) if com_t else None
    niveis = [q["severidade"] for q in quadros if q.get("severidade") in ORDEM_SEVERIDADE]
    classes: dict[str, int] = {}
    for q in quadros:
        for c in {r["classe"] for r in q["regioes"]}:
            classes[c] = classes.get(c, 0) + 1
    return {
        "analisados": len(quadros),
        "pulados": int(sum(q.get("pulados", 0) for q in quadros)),
        "quadros_por_segundo": round((len(quadros) - 1) / coberto, 2) if len(quadros) > 1 else None,
        "latencia_media_ms": round(float(lat.mean())),
        "latencia_p95_ms": round(float(np.percentile(lat, 95))),
        "preparo_ms": next((q["ms"] for q in quadros if q.get("preparo")), None),
        "t_max": quente["t_max"] if quente else None,
        "t_max_quadro": quente["n"] if quente else None,
        "severidade_max": max(niveis, key=ORDEM_SEVERIDADE.index) if niveis else None,
        "com_anomalia": sum(1 for n in niveis if n != "normal"),
        "sem_escala": sum(1 for q in quadros if q.get("escala") is None),
        "presenca_classes": {c: round(n / len(quadros), 3) for c, n in sorted(classes.items(), key=lambda x: -x[1])},
    }


class Videos:
    def __init__(self, pasta_dados: Callable[[], Path], preparar: Callable[[dict], tuple[Callable[[np.ndarray, float], dict], dict]]):
        """``preparar(opcoes)`` devolve (função que analisa um quadro RGB, informações do modelo)."""
        self._pasta_dados = pasta_dados
        self._preparar = preparar
        self._trava = threading.Lock()
        self._vivos: dict[str, dict] = {}  # estado em memória de quem está na fila ou em processamento
        self._quadros: dict[str, list[dict]] = {}
        self._cancelar: dict[str, threading.Event] = {}
        self._fila: queue.Queue[str] = queue.Queue()
        self._trabalhador: threading.Thread | None = None

    @property
    def pasta(self) -> Path:
        return self._pasta_dados() / "videos"

    def _pasta_de(self, id_: str) -> Path:
        if not ID_VALIDO.fullmatch(id_ or ""):
            raise KeyError(id_)
        p = self.pasta / id_
        if not (p / "estado.json").exists():
            raise KeyError(id_)
        return p

    # ---------------------------------------------------------------- entrada

    def criar(self, origem, nome: str, opcoes: dict) -> dict:
        """Copia o vídeo (``origem`` é um arquivo aberto), confere se abre e põe na fila."""
        ext = Path(nome or "").suffix.lower()
        if ext not in video.EXTENSOES:
            raise ValueError("Formato de vídeo não aceito. Envie MP4, AVI, MOV, MKV, M4V, WMV ou WEBM.")
        id_ = uuid.uuid4().hex[:12]
        pasta = self.pasta / id_
        (pasta / "quadros").mkdir(parents=True)
        destino = pasta / f"original{ext}"
        total = 0
        try:
            with open(destino, "wb") as saida:
                while bloco := origem.read(4 * 1024 * 1024):
                    total += len(bloco)
                    if total > LIMITE_BYTES:
                        raise ValueError("Vídeo maior que 2 GB. Corte o trecho que interessa e envie de novo.")
                    saida.write(bloco)
            leitor = video.Leitor(destino)
            info = leitor.info
            leitor.fechar()
        except Exception:
            shutil.rmtree(pasta, ignore_errors=True)
            raise
        e = {
            "id": id_,
            "arquivo": Path(nome).name,
            "criado_em": datetime.now().isoformat(timespec="seconds"),
            "tamanho_bytes": total,
            "info": info.__dict__,
            "opcoes": opcoes,
            "modelo": None,
            "status": "na_fila",
            "erro": None,
            "progresso": 0.0,
            "matriz": None,
            "resumo": {"analisados": 0},
        }
        self._gravar(e)
        with self._trava:
            self._vivos[id_] = e
            self._quadros[id_] = []
            self._cancelar[id_] = threading.Event()
        self._fila.put(id_)
        if self._trabalhador is None or not self._trabalhador.is_alive():
            self._trabalhador = threading.Thread(target=self._trabalhar, name="pyron-videos", daemon=True)
            self._trabalhador.start()
        return self._publico(e)

    # ---------------------------------------------------------------- processamento

    def _trabalhar(self) -> None:
        while True:
            id_ = self._fila.get()
            try:
                self._processar(id_)
            except Exception as erro:  # noqa: BLE001 - o erro vai para o estado, a thread continua
                with self._trava:
                    e = self._vivos.get(id_)
                    if e is not None:
                        e.update(status="erro", erro=str(erro) or erro.__class__.__name__)
                if e is not None:
                    self._encerrar(id_)

    def _processar(self, id_: str) -> None:
        with self._trava:
            e = self._vivos.get(id_)
            cancelar = self._cancelar.get(id_)
        if e is None or cancelar is None:  # apagado enquanto esperava na fila
            return
        if cancelar.is_set():
            e["status"] = "cancelado"
            return self._encerrar(id_)
        pasta = self.pasta / id_
        opc = e["opcoes"]
        analisar, modelo = self._preparar(opc)
        leitor = video.Leitor(next(pasta.glob("original.*")))
        fps = leitor.info.fps
        duracao = max(leitor.info.duracao_s, 1e-6)
        with self._trava:
            e.update(status="processando", modelo=modelo, iniciado_em=datetime.now().isoformat(timespec="seconds"))
        self._gravar(e)
        linhas = open(pasta / "quadros.jsonl", "a", encoding="utf-8")
        inicio = None  # o relógio do "ao vivo" só começa depois do primeiro quadro (carregar OCR e modelo)
        gravado = perf_counter()
        alvo, anterior, falhas = 0.0, -1, 0
        try:
            while len(self._quadros[id_]) < MAXIMO_QUADROS and not cancelar.is_set():
                if opc["modo"] == "ao_vivo" and inicio is not None:
                    alvo = max(alvo, (perf_counter() - inicio) * opc["velocidade"])
                q = leitor.em(alvo)
                if q is None:
                    break
                indice, tempo, rgb = q
                if opc["modo"] == "ao_vivo" and inicio is not None:
                    # Modelo mais rápido que o vídeo: espera o quadro "chegar", como numa câmera.
                    espera = tempo / opc["velocidade"] - (perf_counter() - inicio)
                    if espera > 0 and cancelar.wait(espera):
                        break
                t0 = perf_counter()
                try:
                    r = analisar(rgb, tempo)
                    falhas = 0
                except Exception as erro:  # noqa: BLE001 - um quadro ruim não derruba o vídeo inteiro
                    falhas += 1
                    with open(pasta / "erros.log", "a", encoding="utf-8") as log:
                        log.write(f"quadro {indice} ({tempo:.2f} s)\n{traceback.format_exc()}\n")
                    if falhas >= 5:
                        raise RuntimeError(f"A análise falhou em 5 quadros seguidos: {erro}") from erro
                    r = {"regioes": [], "escala": None, "t_max": None, "severidade": None, "erro": str(erro)}
                ms = (perf_counter() - t0) * 1000
                n = len(self._quadros[id_])
                Image.fromarray(rgb).save(pasta / "quadros" / f"{n:05d}.jpg", quality=90)
                quadro = {"n": n, "indice": indice, "tempo_s": round(tempo, 3), "ms": round(ms), "pulados": indice - anterior - 1, **r}
                if inicio is None:
                    quadro["preparo"] = True  # carregou OCR e modelo: fica fora da latência
                    inicio = perf_counter() - tempo / opc["velocidade"]
                anterior = indice
                linhas.write(json.dumps(quadro, ensure_ascii=False) + "\n")
                with self._trava:
                    if e["matriz"] is None:
                        e["matriz"] = r.get("matriz")
                    self._quadros[id_].append(quadro)
                    e["progresso"] = round(min(1.0, (tempo + 1 / fps) / duracao), 4)
                alvo = tempo + (1 / fps if opc["modo"] == "ao_vivo" else opc["intervalo_s"])
                if perf_counter() - gravado > 2:
                    linhas.flush()
                    with self._trava:
                        e["resumo"] = resumir(self._quadros[id_], e["info"])
                    self._gravar(e)
                    gravado = perf_counter()
        finally:
            linhas.close()
            leitor.fechar()
        with self._trava:
            e["status"] = "cancelado" if cancelar.is_set() else "concluido"
            if e["status"] == "concluido":
                e["progresso"] = 1.0
            if len(self._quadros[id_]) >= MAXIMO_QUADROS:
                e["aviso"] = f"Parei em {MAXIMO_QUADROS} quadros analisados. Use um intervalo maior para cobrir o vídeo inteiro."
        self._encerrar(id_)

    def _encerrar(self, id_: str) -> None:
        with self._trava:
            e = self._vivos.pop(id_, None)
            quadros = self._quadros.pop(id_, [])
            self._cancelar.pop(id_, None)
            if e is None:
                return
            e["resumo"] = resumir(quadros, e["info"])
            e["terminado_em"] = datetime.now().isoformat(timespec="seconds")
        self._gravar(e)

    # ---------------------------------------------------------------- consulta

    def _gravar(self, e: dict) -> None:
        arq = self.pasta / e["id"] / "estado.json"
        if not arq.parent.exists():
            return
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
        tmp.replace(arq)

    def _ler(self, id_: str) -> dict:
        with self._trava:
            if id_ in self._vivos:
                return dict(self._vivos[id_])
        e = json.loads((self._pasta_de(id_) / "estado.json").read_text(encoding="utf-8"))
        if e["status"] in ATIVOS:  # o Pyron fechou no meio: o que foi analisado continua valendo
            e["status"] = "interrompido"
            e["resumo"] = resumir(self._ler_quadros(id_), e["info"])
            self._gravar(e)
        return e

    def _ler_quadros(self, id_: str) -> list[dict]:
        with self._trava:
            if id_ in self._quadros:
                return list(self._quadros[id_])
        arq = self._pasta_de(id_) / "quadros.jsonl"
        if not arq.exists():
            return []
        saida = []
        for linha in arq.read_text(encoding="utf-8").splitlines():
            try:
                saida.append(json.loads(linha))
            except json.JSONDecodeError:
                break  # última linha cortada no meio por um fechamento abrupto
        return saida

    def _publico(self, e: dict) -> dict:
        n = e.get("resumo", {}).get("analisados", 0)
        return {**e, "miniatura": f"/api/videos/{e['id']}/quadros/0.jpg" if n or e["status"] == "processando" else None}

    def listar(self) -> list[dict]:
        if not self.pasta.exists():
            return []
        saida = []
        for p in self.pasta.iterdir():
            if not ID_VALIDO.fullmatch(p.name) or not (p / "estado.json").exists():
                continue
            try:
                saida.append(self._publico(self._ler(p.name)))
            except (json.JSONDecodeError, KeyError, OSError):
                continue
        return sorted(saida, key=lambda e: e["criado_em"], reverse=True)

    def obter(self, id_: str, desde: int = 0) -> dict:
        e = self._ler(id_)
        quadros = self._ler_quadros(id_)
        if e["status"] in ATIVOS:
            e["resumo"] = resumir(quadros, e["info"])
        return {**self._publico(e), "total_quadros": len(quadros), "desde": desde, "quadros": quadros[max(0, desde):]}

    def quadro(self, id_: str, n: int) -> tuple[Path, dict | None]:
        arq = self._pasta_de(id_) / "quadros" / f"{int(n):05d}.jpg"
        if not arq.exists():
            raise KeyError(n)
        info = next((q for q in self._ler_quadros(id_) if q["n"] == int(n)), None)
        return arq, info

    def cancelar(self, id_: str) -> dict:
        self._pasta_de(id_)
        with self._trava:
            ev = self._cancelar.get(id_)
        if ev is not None:
            ev.set()
        return self._publico(self._ler(id_))

    def apagar(self, id_: str) -> None:
        pasta = self._pasta_de(id_)
        with self._trava:
            ev = self._cancelar.get(id_)
            if id_ in self._vivos and self._vivos[id_]["status"] == "na_fila":  # ainda nem começou: sai da fila
                for d in (self._vivos, self._quadros, self._cancelar):
                    d.pop(id_, None)
                ev = None
        if ev is not None:
            ev.set()
            limite = perf_counter() + 10
            while perf_counter() < limite:  # espera a thread soltar o arquivo do vídeo (Windows trava arquivo aberto)
                with self._trava:
                    if id_ not in self._vivos:
                        break
                threading.Event().wait(0.05)
        shutil.rmtree(pasta)
