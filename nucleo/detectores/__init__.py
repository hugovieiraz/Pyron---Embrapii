"""Registro de detectores: tudo que acha regiões numa matriz de temperatura.

Todo detector recebe a matriz de temperatura (°C) e devolve caixas com classe e confiança.
Há dois tipos:

- **regra**: sem aprendizado, embutido no código (ex.: pontos quentes por limiar adaptativo);
- **aprendizado**: um modelo treinado, instalado como uma pasta em ``modelos/`` com
  ``cartao.json`` (identidade, classes, métricas) e ``modelo.onnx``. Ver ``modelos/LEIA-ME.md``.

O software lista os dois tipos do mesmo jeito; trocar de modelo é escolher outro na lista.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Deteccao:
    classe: str
    caixa: list[float]  # x0, y0, x1, y1 em pixels da matriz
    confianca: float


@dataclass
class Detector:
    id: str
    nome: str
    tipo: str  # "regra" ou "aprendizado"
    arquitetura: str
    descricao: str
    classes: list[str]
    versao: str = "1.0"
    cartao: dict = field(default_factory=dict)
    nomes: dict = field(default_factory=dict)  # classe -> nome para exibir (ex.: "parte_isoladora" -> "Parte isoladora")

    def detectar(self, temperatura: np.ndarray) -> list[Deteccao]:  # pragma: no cover - interface
        raise NotImplementedError

    def descrever(self) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "tipo": self.tipo,
            "arquitetura": self.arquitetura,
            "descricao": self.descricao,
            "classes": self.classes,
            "versao": self.versao,
            "cartao": self.cartao,
            "nomes": self.nomes,
        }


def listar(pasta_modelos: Path | None = None) -> list[Detector]:
    """Detectores embutidos mais os modelos instalados na pasta."""
    from nucleo.detectores.onnx_modelo import DetectorONNX
    from nucleo.detectores.pontos_quentes import PontosQuentes

    detectores: list[Detector] = [PontosQuentes()]
    if pasta_modelos and pasta_modelos.exists():
        for cartao in sorted(pasta_modelos.glob("*/cartao.json")):
            try:
                detectores.append(DetectorONNX(cartao.parent))
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as erro:
                detectores.append(Indisponivel(cartao.parent.name, str(erro)))
    return detectores


def obter(id_: str, pasta_modelos: Path | None = None) -> Detector:
    for d in listar(pasta_modelos):
        if d.id == id_:
            return d
    raise KeyError(f"modelo '{id_}' não encontrado")


class Indisponivel(Detector):
    """Modelo instalado com problema (arquivo faltando, cartão inválido): aparece na lista com o erro."""

    def __init__(self, id_: str, erro: str):
        super().__init__(id_, f"{id_} (com erro)", "aprendizado", "-", f"Não foi possível carregar: {erro}", [])

    def detectar(self, temperatura: np.ndarray) -> list[Deteccao]:
        raise ValueError(self.descricao)
