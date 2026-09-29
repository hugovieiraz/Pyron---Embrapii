"""Como a matriz de temperatura vira a entrada de uma rede.

Treino (``ml/``) e uso (``DetectorONNX``) chamam as mesmas funções: se os dois preparassem a
imagem de jeitos diferentes, o modelo funcionaria no treino e erraria no aplicativo.

Normalizações:

- ``por_imagem``: de 0 a 1 entre o 1º percentil do equipamento e o máximo da cena (a mesma faixa
  que o aplicativo usa para exibir). Realça a forma dos componentes em qualquer clima;
- ``fixa``: de 0 a 1 entre ``t_min`` e ``t_max`` fixos. Preserva o valor absoluto.
"""

from __future__ import annotations

import numpy as np
from PIL import Image


def faixa(temperatura: np.ndarray, modo: str = "por_imagem", t_min: float = -20.0, t_max: float = 80.0) -> tuple[float, float]:
    if modo == "fixa":
        return float(t_min), float(t_max)
    from nucleo.render import faixa_exibicao

    return faixa_exibicao(temperatura)


def para_rede(
    temperatura: np.ndarray,
    largura: int,
    altura: int,
    modo: str = "por_imagem",
    t_min: float = -20.0,
    t_max: float = 80.0,
    ajuste_faixa: tuple[float, float] = (0.0, 0.0),
) -> np.ndarray:
    """Matriz float32 [altura, largura] de 0 a 1.

    ``ajuste_faixa`` desloca o limite inferior e superior (em fração da faixa); só o treino usa,
    como aumento de dados.
    """
    lo, hi = faixa(temperatura, modo, t_min, t_max)
    amplitude = max(hi - lo, 1e-6)
    lo, hi = lo + ajuste_faixa[0] * amplitude, hi + ajuste_faixa[1] * amplitude
    t = np.nan_to_num(temperatura.astype(np.float32), nan=lo)
    norm = np.clip((t - lo) / max(hi - lo, 1e-6), 0.0, 1.0).astype(np.float32)
    if norm.shape != (altura, largura):
        norm = np.asarray(Image.fromarray(norm, mode="F").resize((largura, altura), Image.BILINEAR), dtype=np.float32)
    return norm


def tensor_entrada(norm: np.ndarray, media=(0.0, 0.0, 0.0), desvio=(1.0, 1.0, 1.0)) -> np.ndarray:
    """[1, 3, altura, largura]: o canal único repetido três vezes e padronizado."""
    canais = np.stack([norm] * 3, axis=0)
    m = np.asarray(media, dtype=np.float32)[:, None, None]
    d = np.asarray(desvio, dtype=np.float32)[:, None, None]
    return ((canais - m) / d)[None].astype(np.float32)
