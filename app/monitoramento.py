"""Monitoramento: vigia a pasta onde a câmera grava, analisa cada imagem nova e gera alertas.

Fontes de imagem
    - Pasta monitorada (disponível): a câmera, o cartão SD sincronizado, o FTP da câmera fixa ou o
      FLIR Thermal Studio gravam os JPEG numa pasta; o Pyron analisa cada arquivo novo.
    - Câmera de rede RTSP/ONVIF e câmera FLIR fixa (Atlas SDK): no backlog.

Alertas
    Quando a severidade da imagem atinge o mínimo configurado, nasce um alerta com a mensagem pronta
    para o WhatsApp de cada responsável. Nesta versão o envio é manual (link wa.me que abre o WhatsApp
    com o texto preenchido); o envio automático pela API oficial do WhatsApp Business está no backlog.

O monitoramento roda enquanto o Pyron estiver aberto (o servidor desliga junto com a janela).
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import quote

ORDEM = {"sem_medida": -2, "nao_avaliado": -1, "normal": 0, "atencao": 1, "programar": 2, "urgente": 3, "imediato": 4}
EXTENSOES = {".jpg", ".jpeg", ".png"}
SEGUNDOS_ESTAVEL = 2.0  # arquivo mais novo que isso pode ainda estar sendo gravado pela câmera

PADRAO = {
    "ativo": False,
    "fonte": "pasta",
    "pasta": "",
    "intervalo_s": 10,
    "instalacao": "",
    "equipamento": "",
    "subpastas": False,  # cada subpasta é um equipamento (uma câmera fixa por pasta, por exemplo)
    "severidade_minima": "urgente",
    "repetir_min": 60,
    "destinatarios": [],
    "envio": "manual",
}

DISPONIVEL = {
    "fontes": {"pasta": True, "rtsp": False, "flir_sdk": False},
    "envio": {"manual": True, "automatico": False},
}


# ---------------------------------------------------------------- configuração


class ConfiguracaoInvalida(ValueError):
    pass


def telefone_digitos(telefone: str) -> str:
    return re.sub(r"\D", "", telefone or "")


def validar(cfg: dict) -> dict:
    """Confere a configuração vinda da interface e devolve só os campos conhecidos."""
    saida = dict(PADRAO)
    saida["ativo"] = bool(cfg.get("ativo", False))
    fonte = cfg.get("fonte", "pasta")
    if fonte not in DISPONIVEL["fontes"]:
        raise ConfiguracaoInvalida("Fonte de imagens desconhecida.")
    if not DISPONIVEL["fontes"][fonte]:
        raise ConfiguracaoInvalida("Essa fonte de imagens ainda está em desenvolvimento. Use a pasta monitorada.")
    saida["fonte"] = fonte
    saida["pasta"] = str(cfg.get("pasta") or "").strip()[:400]
    if saida["ativo"] and not saida["pasta"]:
        raise ConfiguracaoInvalida("Escolha a pasta onde a câmera grava as imagens.")
    if saida["ativo"] and not Path(saida["pasta"]).is_dir():
        raise ConfiguracaoInvalida(f"A pasta {saida['pasta']} não existe ou não está acessível.")
    intervalo = int(cfg.get("intervalo_s", PADRAO["intervalo_s"]))
    if not 2 <= intervalo <= 3600:
        raise ConfiguracaoInvalida("O intervalo de verificação vai de 2 s a 1 hora.")
    saida["intervalo_s"] = intervalo
    saida["instalacao"] = str(cfg.get("instalacao") or "")[:120]
    saida["equipamento"] = str(cfg.get("equipamento") or "")[:120]
    saida["subpastas"] = bool(cfg.get("subpastas", False))
    minima = cfg.get("severidade_minima", "urgente")
    if minima not in ORDEM or minima == "normal":
        raise ConfiguracaoInvalida("Severidade mínima deve ser atenção, programar, urgente ou imediato.")
    saida["severidade_minima"] = minima
    repetir = int(cfg.get("repetir_min", PADRAO["repetir_min"]))
    if not 0 <= repetir <= 24 * 60:
        raise ConfiguracaoInvalida("O intervalo para repetir o alerta vai de 0 a 24 horas.")
    saida["repetir_min"] = repetir
    destinatarios = []
    for d in cfg.get("destinatarios") or []:
        nome = str(d.get("nome") or "").strip()[:80]
        telefone = str(d.get("telefone") or "").strip()[:30]
        if not nome and not telefone:
            continue
        if not 10 <= len(telefone_digitos(telefone)) <= 15:
            raise ConfiguracaoInvalida(f"O WhatsApp de {nome or 'um responsável'} precisa ter DDI e DDD, por exemplo +55 83 99999-0000.")
        destinatarios.append({"nome": nome or "Responsável", "telefone": telefone})
    saida["destinatarios"] = destinatarios[:10]
    envio = cfg.get("envio", "manual")
    if envio not in DISPONIVEL["envio"]:
        raise ConfiguracaoInvalida("Forma de envio desconhecida.")
    if not DISPONIVEL["envio"][envio]:
        raise ConfiguracaoInvalida("O envio automático pelo WhatsApp Business ainda está em desenvolvimento.")
    saida["envio"] = envio
    return saida


# ---------------------------------------------------------------- mensagem


def _numero(v: float | None, casas: int = 1) -> str:
    return "–" if v is None else f"{v:.{casas}f}".replace(".", ",")


def mensagem(analise: dict, cfg: dict) -> str:
    """Texto do alerta, curto e sem emoji: lido na tela do celular."""
    r = analise["resumo"]
    ident = analise.get("identificacao") or {}
    local = " · ".join(v for v in (ident.get("instalacao") or cfg.get("instalacao"), ident.get("equipamento") or cfg.get("equipamento")) if v)
    linhas = [f"[Pyron] {r['severidade_rotulo'].upper()}" + (f": {local}" if local else "")]
    criticas = [g for g in analise["regioes"] if g.get("severidade") == r["severidade"]]
    if criticas:
        pior = max(criticas, key=lambda g: (g.get("pct_mta") or 0, (g.get("medida") or {}).get("t_max") or 0))
        partes = [f"{_numero((pior.get('medida') or {}).get('t_max'))} °C medidos"]
        if pior.get("t_projetada") is not None and pior.get("avaliacao_absoluta") == "completa":
            partes.append(f"{_numero(pior['t_projetada'])} °C a plena carga")
        if pior.get("pct_mta") is not None:
            partes.append(f"{_numero(pior['pct_mta'], 0)}% da MTA")
        linhas.append(f"{pior.get('nome') or 'Região'}: " + ", ".join(partes) + ".")
    linhas.append(r["mensagem"])
    quando = analise.get("metadados", {}).get("data_hora") or analise.get("criado_em", "").replace("T", " ")
    linhas.append(f"Imagem {analise['arquivo']}" + (f", {quando[:16]}" if quando else "") + ".")
    return "\n".join(linhas)


def links_whatsapp(texto: str, destinatarios: list[dict]) -> list[dict]:
    """Links wa.me: abrem o WhatsApp (celular ou computador) com a mensagem pronta para o responsável enviar."""
    return [
        {"nome": d["nome"], "telefone": d["telefone"], "url": f"https://wa.me/{telefone_digitos(d['telefone'])}?text={quote(texto)}"}
        for d in destinatarios
        if telefone_digitos(d.get("telefone", ""))
    ]


# ---------------------------------------------------------------- vigia da pasta


class Monitor:
    """Uma thread que confere a pasta a cada intervalo. `verificar()` faz uma passada e pode ser chamada direto."""

    def __init__(
        self,
        analisar: Callable[[bytes, str, dict], dict],
        configuracao: Callable[[], dict],
        salvar_alerta: Callable[[dict], None],
        alertas_recentes: Callable[[], list[dict]],
        pasta_estado: Callable[[], Path],
    ):
        self._analisar = analisar
        self._configuracao = configuracao
        self._salvar_alerta = salvar_alerta
        self._alertas_recentes = alertas_recentes
        self._pasta_estado = pasta_estado
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self._trava = threading.Lock()
        self.estado = {"vigiando": False, "ultima_verificacao": None, "ultima_imagem": None, "analisadas": 0, "alertas": 0, "erro": None}

    # -------- arquivos já vistos (sobrevive a reinícios do programa)

    @property
    def _arquivo_vistos(self) -> Path:
        return self._pasta_estado() / "monitor_vistos.json"

    def _vistos(self) -> dict:
        try:
            return json.loads(self._arquivo_vistos.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _guardar_vistos(self, vistos: dict) -> None:
        self._arquivo_vistos.parent.mkdir(parents=True, exist_ok=True)
        self._arquivo_vistos.write_text(json.dumps(vistos), encoding="utf-8")

    @staticmethod
    def _chave(p: Path) -> str:
        st = p.stat()
        return f"{p.name}|{st.st_size}|{st.st_mtime_ns}"

    def _imagens(self, pasta: Path, subpastas: bool = False) -> list[Path]:
        candidatos = pasta.rglob("*") if subpastas else pasta.iterdir()
        return sorted((p for p in candidatos if p.is_file() and p.suffix.lower() in EXTENSOES), key=lambda p: p.stat().st_mtime)

    @staticmethod
    def identificacao(p: Path, pasta: Path, cfg: dict) -> dict:
        """Instalação e equipamento da imagem: os da configuração ou, com subpastas, o nome da subpasta."""
        ident = {k: cfg[k] for k in ("instalacao", "equipamento") if cfg.get(k)}
        if cfg.get("subpastas") and p.parent != pasta:
            ident["equipamento"] = p.parent.name
        return ident

    def linha_de_base(self, pasta: str, subpastas: bool = False) -> int:
        """Ao ligar numa pasta, o que já estava lá não é analisado: só o que chegar depois."""
        caminho = Path(pasta)
        vistos = self._vistos()
        marcadas = 0
        if caminho.is_dir():
            for p in self._imagens(caminho, subpastas):
                vistos[str(p.resolve()).lower() + "|" + self._chave(p)] = True
                marcadas += 1
        self._guardar_vistos(vistos)
        return marcadas

    # -------- uma passada

    def verificar(self) -> list[dict]:
        """Analisa as imagens novas e estáveis da pasta. Devolve as análises criadas."""
        with self._trava:
            cfg = self._configuracao()
            self.estado["ultima_verificacao"] = datetime.now().isoformat(timespec="seconds")
            pasta = Path(cfg.get("pasta") or "")
            if not cfg.get("pasta") or not pasta.is_dir():
                self.estado["erro"] = "A pasta monitorada não existe ou não está acessível."
                return []
            self.estado["erro"] = None
            vistos = self._vistos()
            novas = []
            for p in self._imagens(pasta, cfg.get("subpastas", False)):
                try:
                    chave = str(p.resolve()).lower() + "|" + self._chave(p)
                    if chave in vistos or time.time() - p.stat().st_mtime < SEGUNDOS_ESTAVEL:
                        continue
                    dados = p.read_bytes()
                except OSError:
                    continue  # arquivo sumiu ou está preso pela câmera: tenta na próxima passada
                vistos[chave] = True
                ident = self.identificacao(p, pasta, cfg)
                try:
                    a = self._analisar(dados, p.name, ident)
                except Exception as erro:  # imagem ilegível não pode parar o monitoramento
                    self.estado["erro"] = f"{p.name}: {getattr(erro, 'detail', erro)}"
                    continue
                novas.append(a)
                self.estado["analisadas"] += 1
                self.estado["ultima_imagem"] = {"arquivo": p.name, "analise_id": a["id"], "severidade": a["resumo"]["severidade"], "em": a["criado_em"]}
                alerta = self._talvez_alertar(a, cfg)
                if alerta:
                    self._salvar_alerta(alerta)
                    self.estado["alertas"] += 1
            self._guardar_vistos(vistos)
            return novas

    def _talvez_alertar(self, a: dict, cfg: dict) -> dict | None:
        sev = a["resumo"]["severidade"]
        if ORDEM[sev] < ORDEM[cfg.get("severidade_minima", "urgente")]:
            return None
        # Não repete o mesmo nível dentro da janela configurada; se piorar, avisa na hora.
        janela = cfg.get("repetir_min", 60) * 60
        agora = datetime.now()
        for anterior in self._alertas_recentes():
            idade = (agora - datetime.fromisoformat(anterior["criado_em"])).total_seconds()
            if idade < janela and ORDEM[anterior["severidade"]] >= ORDEM[sev]:
                return None
        texto = mensagem(a, cfg)
        return {
            "id": uuid.uuid4().hex[:12],
            "criado_em": agora.isoformat(timespec="seconds"),
            "analise_id": a["id"],
            "arquivo": a["arquivo"],
            "severidade": sev,
            "severidade_rotulo": a["resumo"]["severidade_rotulo"],
            "resumo": a["resumo"]["mensagem"],
            "mensagem": texto,
            "instalacao": cfg.get("instalacao", ""),
            "equipamento": cfg.get("equipamento", ""),
            "destinatarios": [d["nome"] for d in cfg.get("destinatarios", [])],
            "status": "pendente",
        }

    # -------- thread

    def _laco(self) -> None:
        while not self._parar.is_set():
            cfg = self._configuracao()
            if not cfg.get("ativo"):
                break
            try:
                self.verificar()
            except Exception as erro:  # nunca derrubar a thread
                self.estado["erro"] = str(erro)
            self._parar.wait(max(2, int(cfg.get("intervalo_s", 10))))
        self.estado["vigiando"] = False

    def iniciar(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._parar.clear()
        self.estado["vigiando"] = True
        self._thread = threading.Thread(target=self._laco, name="monitoramento", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        self.estado["vigiando"] = False
