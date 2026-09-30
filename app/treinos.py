"""Treinos de modelo pedidos pela interface (tela Modelos).

O arquivo do CVAT é guardado em ``dados/rotulos``; o treino roda como processo separado
(``python -m ml.treinar ... --progresso``), então continua mesmo se a janela do Pyron for fechada.
O andamento fica em ``<dados_app>/treinos/<id>/``: ``pedido.json``, ``progresso.json`` e ``registro.txt``.
Um treino por vez: a placa de vídeo é uma só.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ETAPAS_FINAIS = {"pronto", "erro", "cancelado", "interrompido"}
ID_VALIDO = re.compile(r"[a-z0-9][a-z0-9-]{2,48}")
ARQUIVOS_DE_MODELO = {"cartao.json", "modelo.onnx", "relatorio.json", "previsoes_teste.png", "pesos.pt"}

BLOQUEIO_WINDOWS = (
    "O Windows bloqueou o PyTorch: o Controle Inteligente de Aplicativos está ligado e barra as bibliotecas de IA, "
    "que não têm assinatura digital. Para treinar neste computador, desligue-o em Segurança do Windows › Controle de "
    "aplicativos e navegador (decisão sua: é uma proteção do sistema). Sem desligar, use Treinar fora: o Pyron monta "
    "um pacote para o Google Colab ou o supercomputador e depois instala o modelo aqui."
)


def explicar_erro(texto: str) -> str | None:
    """Traduz os erros conhecidos do treino para o que o usuário precisa fazer."""
    if "4551" in texto or "Controle de Aplicativo" in texto or "Application Control" in texto:
        return BLOQUEIO_WINDOWS
    if "No module named 'torch'" in texto:
        return "O PyTorch não está instalado no ambiente do Pyron. Instale a versão com CUDA de pytorch.org, ou use Treinar fora."
    if "CUDA out of memory" in texto:
        return "A placa de vídeo ficou sem memória. Treine de novo com um lote menor (--lote 2) ou use Treinar fora."
    if "Nenhuma imagem rotulada" in texto:
        return "Nenhuma imagem rotulada foi achada. Os JPEG originais precisam estar em alguma pasta dentro de dados/ do projeto."
    return None


def processo_vivo(pid: int | None) -> bool:
    """Sem os.kill(pid, 0): no Windows ele encerra o processo em vez de só consultar."""
    if not pid:
        return False
    if os.name == "nt":
        import ctypes

        kernel = ctypes.windll.kernel32
        h = kernel.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        codigo = ctypes.c_ulong()
        kernel.GetExitCodeProcess(h, ctypes.byref(codigo))
        kernel.CloseHandle(h)
        return codigo.value == 259  # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def slug(texto: str) -> str:
    import unicodedata

    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:40] or "modelo"


class Treinos:
    def __init__(self, raiz_projeto: Path, pasta_dados, pasta_modelos, python: str | None = None):
        self.raiz = raiz_projeto
        self._pasta_dados = pasta_dados  # funções: a pasta pode mudar (testes, --dados)
        self._pasta_modelos = pasta_modelos
        self.python = python or _python_do_projeto(raiz_projeto)
        self._processos: dict[str, subprocess.Popen] = {}
        self._ambiente: tuple[float, dict] | None = None

    # ------------------------------------------------------------ ambiente

    def verificar_ambiente(self, forcar: bool = False) -> dict:
        """PyTorch carrega? Tem GPU? Guardado por 10 minutos (carregar o PyTorch leva alguns segundos)."""
        import time

        if self._ambiente and not forcar and time.time() - self._ambiente[0] < 600:
            return self._ambiente[1]
        codigo = ("import json, torch; print(json.dumps({'torch': torch.__version__, 'cuda': torch.cuda.is_available(), "
                  "'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}))")
        try:
            r = subprocess.run([self.python, "-c", codigo], cwd=self.raiz, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode == 0:
                info = json.loads(r.stdout.strip().splitlines()[-1])
                ambiente = {"ok": True, **info, "mensagem": f"PyTorch {info['torch']} · " + (info["gpu"] or "sem GPU: o treino roda no processador, bem mais devagar")}
            else:
                ambiente = {"ok": False, "mensagem": explicar_erro(r.stderr) or (r.stderr.strip().splitlines() or ["Falha ao carregar o PyTorch."])[-1][:300],
                            "bloqueado_pelo_windows": explicar_erro(r.stderr) == BLOQUEIO_WINDOWS}
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, IndexError) as erro:
            ambiente = {"ok": False, "mensagem": f"Não consegui verificar o PyTorch: {erro}"}
        self._ambiente = (time.time(), ambiente)
        return ambiente

    # ------------------------------------------------------------ modelo treinado fora

    def instalar_modelo(self, dados: bytes) -> str:
        """Instala o .zip de um modelo treinado fora (pasta com cartao.json e modelo.onnx). Devolve o id."""
        import io

        try:
            z = zipfile.ZipFile(io.BytesIO(dados))
        except zipfile.BadZipFile as erro:
            raise ValueError("O arquivo não é um .zip.") from erro
        cartoes = [n for n in z.namelist() if n.endswith("cartao.json")]
        if len(cartoes) != 1:
            raise ValueError("O .zip precisa ter uma pasta de modelo com cartao.json e modelo.onnx (como sai do treino).")
        prefixo = cartoes[0][: -len("cartao.json")]
        cartao = json.loads(z.read(cartoes[0]).decode("utf-8"))
        id_ = str(cartao.get("id", ""))
        if not ID_VALIDO.fullmatch(id_):
            raise ValueError("O cartao.json tem um identificador inválido.")
        if prefixo + "modelo.onnx" not in z.namelist():
            raise ValueError("Falta o modelo.onnx no .zip.")
        destino = self._pasta_modelos() / id_
        if destino.exists():
            raise ValueError(f"Já existe um modelo {id_} instalado.")
        destino.mkdir(parents=True)
        for nome in ARQUIVOS_DE_MODELO:
            if prefixo + nome in z.namelist():
                (destino / nome).write_bytes(z.read(prefixo + nome))
        return id_

    def montar_pacote(self, arquivo: Path, id_: str, nome: str, epocas: int, divisao: str) -> Path:
        from ml import pacote

        return pacote.montar(arquivo, self.pasta_imagens, self.pasta_rotulos / "pacotes", id_, nome, epocas, divisao)

    @property
    def pasta(self) -> Path:
        return self._pasta_dados() / "treinos"

    @property
    def pasta_rotulos(self) -> Path:
        return self.raiz / "dados" / "rotulos"

    @property
    def pasta_imagens(self) -> Path:
        """As imagens rotuladas são procuradas pelo nome em toda a pasta dados/ (dataset e fotos próprias)."""
        return self.raiz / "dados"

    # ------------------------------------------------------------ rótulos

    def guardar_rotulos(self, dados: bytes, nome_original: str) -> Path:
        self.pasta_rotulos.mkdir(parents=True, exist_ok=True)
        base = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(nome_original).stem)[:60] or "rotulos"
        sufixo = Path(nome_original).suffix.lower() if Path(nome_original).suffix.lower() in (".zip", ".json") else ".zip"
        destino = self.pasta_rotulos / f"{datetime.now():%Y%m%d_%H%M%S}_{base}{sufixo}"
        destino.write_bytes(dados)
        return destino

    def arquivo_rotulos(self, nome: str) -> Path:
        caminho = (self.pasta_rotulos / Path(nome).name).resolve()
        if caminho.parent != self.pasta_rotulos.resolve() or not caminho.exists():
            raise FileNotFoundError("Arquivo de rótulos não encontrado. Envie o .zip do CVAT de novo.")
        return caminho

    # ------------------------------------------------------------ treinos

    def em_andamento(self) -> dict | None:
        return next((t for t in self.listar() if t["etapa"] not in ETAPAS_FINAIS), None)

    def iniciar(self, arquivo: Path, id_: str, nome: str, epocas: int, divisao: str) -> dict:
        if not ID_VALIDO.fullmatch(id_):
            raise ValueError("Identificador inválido: use letras minúsculas, números e hífen (3 a 49 caracteres).")
        if not 1 <= epocas <= 500:
            raise ValueError("Número de épocas entre 1 e 500.")
        if divisao not in ("sessao", "cvat"):
            raise ValueError("Divisão deve ser por sessão ou a do CVAT.")
        andando = self.em_andamento()
        if andando:
            raise RuntimeError(f"Já há um treino em andamento ({andando['nome']}). Espere terminar ou cancele.")
        if (self._pasta_modelos() / id_).exists():
            raise ValueError(f"Já existe um modelo com o identificador {id_}. Escolha outro nome.")
        pasta = self.pasta / id_
        pasta.mkdir(parents=True, exist_ok=True)
        progresso = pasta / "progresso.json"
        progresso.unlink(missing_ok=True)
        comando = [
            self.python, "-m", "ml.treinar", "--coco", str(arquivo), "--imagens", str(self.pasta_imagens), "--id", id_, "--nome", nome,
            "--epocas", str(epocas), "--divisao", divisao, "--destino", str(self._pasta_modelos()), "--progresso", str(progresso),
        ]
        registro = open(pasta / "registro.txt", "w", encoding="utf-8")
        ambiente = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        processo = subprocess.Popen(
            comando, cwd=self.raiz, stdout=registro, stderr=subprocess.STDOUT, env=ambiente,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        registro.close()
        self._processos[id_] = processo
        pedido = {"id": id_, "nome": nome, "epocas": epocas, "divisao": divisao, "rotulos": arquivo.name,
                  "criado_em": datetime.now().isoformat(timespec="seconds"), "pid": processo.pid}
        (pasta / "pedido.json").write_text(json.dumps(pedido, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.obter(id_)

    def cancelar(self, id_: str) -> dict:
        t = self.obter(id_)
        if t["etapa"] in ETAPAS_FINAIS:
            return t
        processo = self._processos.get(id_)
        if processo and processo.poll() is None:
            processo.terminate()
        elif processo_vivo(t.get("pid")):
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(t["pid"]), "/T", "/F"], capture_output=True)
            else:
                os.kill(int(t["pid"]), 15)
        (self.pasta / id_ / "cancelado").write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
        return self.obter(id_)

    def obter(self, id_: str) -> dict:
        pasta = self.pasta / id_
        if not (pasta / "pedido.json").exists():
            raise FileNotFoundError("Treino não encontrado.")
        pedido = json.loads((pasta / "pedido.json").read_text(encoding="utf-8"))
        try:
            progresso = json.loads((pasta / "progresso.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            progresso = {"etapa": "iniciando", "mensagem": "Carregando PyTorch e os rótulos"}
        t = {**pedido, **progresso, "id": id_, "nome": pedido["nome"], "pid": pedido["pid"]}
        if t.get("etapa") == "erro":
            t["mensagem"] = explicar_erro(str(t.get("mensagem", ""))) or self._ultima_linha_de_erro(pasta) or t.get("mensagem")
        if t.get("etapa") not in ETAPAS_FINAIS:
            processo = self._processos.get(id_)
            vivo = processo.poll() is None if processo else processo_vivo(pedido["pid"])
            if (pasta / "cancelado").exists():
                t.update(etapa="cancelado", mensagem="Treino cancelado.")
            elif not vivo:
                t.update(etapa="erro" if self._teve_erro(pasta) else "interrompido",
                         mensagem=self._ultima_linha_de_erro(pasta) or "O processo de treino parou antes de terminar.")
        t["percentual"] = self._percentual(t)
        return t

    def listar(self) -> list[dict]:
        if not self.pasta.exists():
            return []
        itens = []
        for p in self.pasta.iterdir():
            if (p / "pedido.json").exists():
                try:
                    itens.append(self.obter(p.name))
                except (OSError, json.JSONDecodeError):
                    continue
        return sorted(itens, key=lambda t: t.get("criado_em", ""), reverse=True)

    def registro(self, id_: str, linhas: int = 40) -> str:
        arquivo = self.pasta / id_ / "registro.txt"
        if not arquivo.exists():
            return ""
        return "\n".join(arquivo.read_text(encoding="utf-8", errors="replace").splitlines()[-linhas:])

    # ------------------------------------------------------------ apoio

    @staticmethod
    def _percentual(t: dict) -> int:
        """Leitura 5%, treino até 90%, avaliação e exportação até 100%."""
        etapa = t.get("etapa")
        if etapa == "pronto":
            return 100
        if etapa in ("iniciando", "lendo"):
            return 3
        if etapa == "treinando" and t.get("epocas"):
            return 5 + int(85 * t.get("epoca", 0) / t["epocas"])
        if etapa == "avaliando":
            return 92
        if etapa == "exportando":
            return 96
        return 0

    def _teve_erro(self, pasta: Path) -> bool:
        texto = (pasta / "registro.txt").read_text(encoding="utf-8", errors="replace") if (pasta / "registro.txt").exists() else ""
        return "Traceback" in texto or "Error" in texto

    def _ultima_linha_de_erro(self, pasta: Path) -> str:
        arquivo = pasta / "registro.txt"
        if not arquivo.exists():
            return ""
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
        explicado = explicar_erro(texto)
        if explicado:
            return explicado
        linhas = [l for l in texto.splitlines() if l.strip()]
        return linhas[-1][:300] if linhas and ("Error" in linhas[-1] or "rror:" in linhas[-1]) else ""


def _python_do_projeto(raiz: Path) -> str:
    """O python.exe do ambiente do projeto (o servidor pode estar rodando no pythonw.exe)."""
    candidato = raiz / ".venv" / "Scripts" / "python.exe"
    if candidato.exists():
        return str(candidato)
    executavel = Path(sys.executable)
    if executavel.name.lower() == "pythonw.exe" and (executavel.parent / "python.exe").exists():
        return str(executavel.parent / "python.exe")
    return sys.executable
