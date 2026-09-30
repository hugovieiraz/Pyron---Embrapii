"""Registro de detectores: tudo que acha regiões numa matriz de temperatura.

Todo detector recebe a matriz de temperatura (°C) e devolve caixas com classe e confiança, em
pixels da matriz. Alguns modelos olham a imagem colorida da câmera em vez da temperatura
(``precisa_imagem``); para eles, a análise passa também essa imagem, no mesmo sentido da matriz.
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
    precisa_imagem: bool = False  # True: o modelo olha a imagem colorida da câmera, não a temperatura

    def detectar(self, temperatura: np.ndarray, imagem: np.ndarray | None = None) -> list[Deteccao]:  # pragma: no cover - interface
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


_CARREGADOS: dict[Path, tuple[float, Detector]] = {}  # modelo já aberto (a sessão ONNX demora a carregar)


def _carregar(cartao: Path) -> Detector:
    from nucleo.detectores.onnx_modelo import DetectorONNX

    marca = max([cartao.stat().st_mtime, *(p.stat().st_mtime for p in cartao.parent.glob("*.onnx"))])
    guardado = _CARREGADOS.get(cartao)
    if guardado and guardado[0] == marca:
        return guardado[1]
    detector = DetectorONNX(cartao.parent)
    _CARREGADOS[cartao] = (marca, detector)
    return detector


def listar(pasta_modelos: Path | None = None) -> list[Detector]:
    """Detectores embutidos, os modelos instalados na pasta e, para cada modelo, ele junto com os pontos quentes.

    Assim dá para escolher um, o outro ou os dois: só as peças (modelo), só o calor (regra) ou as peças
    com os pontos quentes ligados a elas (combinado).
    """
    from nucleo.detectores.pontos_quentes import PontosQuentes

    pontos = PontosQuentes()
    detectores: list[Detector] = [pontos]
    aprendidos: list[Detector] = []
    if pasta_modelos and pasta_modelos.exists():
        for cartao in sorted(pasta_modelos.glob("*/cartao.json")):
            try:
                aprendidos.append(_carregar(cartao))
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as erro:
                detectores.append(Indisponivel(cartao.parent.name, str(erro)))
    return detectores + aprendidos + [Combinado(m, pontos) for m in aprendidos]


def obter(id_: str, pasta_modelos: Path | None = None) -> Detector:
    for d in listar(pasta_modelos):
        if d.id == id_:
            return d
    raise KeyError(f"modelo '{id_}' não encontrado")


class Combinado(Detector):
    """Um modelo de componentes e o detector de pontos quentes juntos: o que é cada peça e onde está o calor.

    As duas listas de caixas saem juntas; a análise (``nucleo/analise.py``) liga cada ponto quente à
    peça onde ele está, aponta o ponto mais quente da cena e compara as peças iguais.
    """

    def __init__(self, componentes: Detector, pontos: Detector):
        super().__init__(
            id=f"{componentes.id}+{pontos.id}",
            nome=f"{componentes.nome} + pontos quentes",
            tipo="combinado",
            arquitetura=f"{componentes.arquitetura} + regra de contraste térmico",
            descricao="Identifica as peças com o modelo treinado e acha os pontos quentes pela regra de contraste. "
            "A análise diz em qual peça está cada ponto quente, onde está o ponto mais quente e a diferença "
            "de temperatura entre as peças iguais.",
            classes=list(dict.fromkeys(componentes.classes + pontos.classes)),
            versao=componentes.versao,
            cartao={
                "treino": componentes.cartao.get("treino"),
                "metricas": componentes.cartao.get("metricas"),
                "limitacoes": [*componentes.cartao.get("limitacoes", []),
                               "Reflexo do sol pode aparecer como ponto quente dentro da caixa de uma peça; confira valores muito altos."],
            },
            nomes={**pontos.nomes, **componentes.nomes},
            precisa_imagem=componentes.precisa_imagem or pontos.precisa_imagem,
        )
        self.partes = (componentes, pontos)

    def detectar(self, temperatura: np.ndarray, imagem: np.ndarray | None = None) -> list[Deteccao]:
        return [d for parte in self.partes for d in parte.detectar(temperatura, imagem)]


class Indisponivel(Detector):
    """Modelo instalado com problema (arquivo faltando, cartão inválido): aparece na lista com o erro."""

    def __init__(self, id_: str, erro: str):
        super().__init__(id_, f"{id_} (com erro)", "aprendizado", "-", f"Não foi possível carregar: {erro}", [])

    def detectar(self, temperatura: np.ndarray, imagem: np.ndarray | None = None) -> list[Deteccao]:
        raise ValueError(self.descricao)
