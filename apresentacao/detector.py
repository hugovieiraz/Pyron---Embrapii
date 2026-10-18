"""O detector de para-raios: RF-DETR Medium treinado com as fotos rotuladas, exportado em ONNX.

Olha a imagem colorida da câmera (como uma pessoa olha o termograma) e devolve uma caixa para cada
peça: o para-raio inteiro, as saias e os terminais superior e inferior. Roda na placa de
vídeo pelo DirectML quando houver (~54 ms por foto na RTX 3050); senão, no processador (~400 ms).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import numpy as np
from PIL import Image

# Nomes exibidos na apresentação. As abas do corpo do para-raio se chamam saias (IEC 60099-4,
# catálogos); o modelo continua com a classe "aletas_isoladoras", só o nome na tela muda.
NOMES = {"aletas_isoladoras": "Saias"}
# Placa de alto desempenho (a RTX), não a Intel integrada, que seria mais lenta que o processador.
OPCOES_DIRECTML = {"performance_preference": "high_performance", "device_filter": "gpu"}


class Detector:
    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)
        cartao = self.pasta / "cartao.json"
        # O modelo fica fora do git: num computador sem ele, o aplicativo abre do mesmo jeito (sem classes)
        # e o erro de carregar() aparece na tela.
        self.cartao = json.loads(cartao.read_text(encoding="utf-8")) if cartao.exists() else {"classes": [], "entrada": {"largura": 640, "altura": 640}}
        relatorio = self.pasta / "relatorio.json"
        self.relatorio = json.loads(relatorio.read_text(encoding="utf-8")) if relatorio.exists() else {}
        self.classes: list[str] = list(self.cartao["classes"])
        self.nomes: dict[str, str] = {**self.cartao.get("nomes", {}), **NOMES}
        self.entrada = self.cartao["entrada"]
        self.saida = self.cartao.get("saida", {})
        self.limiar = float(self.cartao.get("limiar_confianca", 0.5))
        self.motor = ""
        self._sessao = None
        self._trava = threading.Lock()

    def carregar(self) -> None:
        """Abre o modelo na placa de vídeo (DirectML) se der; senão no processador."""
        if not (self.pasta / "cartao.json").exists():
            raise FileNotFoundError(f"Modelo não encontrado em {self.pasta} (fica fora do git; PYRON_APRESENTACAO_MODELO aponta outra pasta).")
        import onnxruntime as ort

        arquivo = str(self.pasta / self.cartao.get("arquivo", "modelo.onnx"))
        if "DmlExecutionProvider" in ort.get_available_providers():
            try:
                opcoes = ort.SessionOptions()
                opcoes.enable_mem_pattern = False
                opcoes.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                sessao = ort.InferenceSession(arquivo, opcoes, providers=[("DmlExecutionProvider", OPCOES_DIRECTML), "CPUExecutionProvider"])
                if sessao.get_providers()[0] == "DmlExecutionProvider":
                    self._sessao, self.motor = sessao, "placa de vídeo (DirectML)"
            except Exception:  # noqa: BLE001 — sem placa compatível: fica o processador
                self._sessao = None
        if self._sessao is None:
            opcoes = ort.SessionOptions()
            opcoes.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
            self._sessao = ort.InferenceSession(arquivo, opcoes, providers=["CPUExecutionProvider"])
            self.motor = "processador"
        self.detectar(np.zeros((480, 640, 3), np.uint8))  # a primeira conta é lenta

    @property
    def pronto(self) -> bool:
        return self._sessao is not None

    def preparar(self, rgb: np.ndarray) -> np.ndarray:
        """Imagem RGB → [1, 3, 640, 640], de 0 a 1 e padronizada como no treino."""
        e = self.entrada
        img = Image.fromarray(np.ascontiguousarray(rgb[..., :3]).astype(np.uint8)).resize(
            (int(e["largura"]), int(e["altura"])), Image.BILINEAR)
        media = np.asarray(e.get("media", (0.485, 0.456, 0.406)), np.float32)
        desvio = np.asarray(e.get("desvio", (0.229, 0.224, 0.225)), np.float32)
        x = np.asarray(img, np.float32)
        x *= 1.0 / (255.0 * desvio)
        x -= media / desvio
        return np.ascontiguousarray(x.transpose(2, 0, 1))[None]

    def detectar(self, rgb: np.ndarray) -> list[dict]:
        """Peças achadas: classe, nome, confiança e caixa (x0, y0, x1, y1 em fração da imagem)."""
        x = self.preparar(rgb)
        with self._trava:
            nomes_saida = [o.name for o in self._sessao.get_outputs()]
            saidas = dict(zip(nomes_saida, self._sessao.run(None, {self._sessao.get_inputs()[0].name: x})))
        n = self.saida.get("nomes", {})
        dets = np.asarray(saidas[n.get("caixas", "dets")], np.float32)[0]
        notas = np.asarray(saidas[n.get("notas", "labels")], np.float32)[0]
        if self.saida.get("fundo_ultima_coluna", True):
            notas = notas[:, :-1]
        prob = 1.0 / (1.0 + np.exp(-np.clip(notas, -88, 88)))
        classes = prob.argmax(axis=1) + int(self.saida.get("deslocamento_classe", 0))
        confianca = prob.max(axis=1)
        pecas = []
        for (cx, cy, w, h), p, c in zip(dets, confianca, classes):
            if p < self.limiar or not 0 <= c < len(self.classes):
                continue
            x0, y0, x1, y1 = (float(v) for v in np.clip([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 0, 1))
            if x1 <= x0 or y1 <= y0:
                continue
            classe = self.classes[int(c)]
            pecas.append({"classe": classe, "nome": self.nomes.get(classe, classe), "confianca": round(float(p), 3),
                          "caixa": [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]})
        return sorted(pecas, key=lambda d: -d["confianca"])
