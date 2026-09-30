"""Detector de pontos quentes por regra (sem aprendizado).

Um ponto quente é um trecho do equipamento mais quente que o equipamento em volta, como uma
conexão com resistência alta. Por isso a regra usa contraste local, e não a temperatura absoluta:

1. separa o equipamento do fundo frio (céu) pelo limiar de Otsu;
2. calcula, para cada pixel, a média do equipamento numa vizinhança (o céu não entra);
3. marca os pixels de equipamento que excedem essa média em pelo menos ``delta_min`` °C;
4. junta os vizinhos em regiões, descarta as muito pequenas e fica com as mais intensas.

Um equipamento inteiro uniformemente aquecido (tanque ao sol) não vira ponto quente. É a linha
de base do software até o primeiro modelo treinado: não sabe o que é cada componente.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from nucleo.analise import mascara_objetos
from nucleo.detectores import Deteccao, Detector


def media_local(temperatura: np.ndarray, mascara: np.ndarray, janela: int) -> np.ndarray:
    """Média dos pixels da máscara numa janela quadrada (convolução normalizada)."""
    t = np.where(mascara, np.nan_to_num(temperatura), 0.0)
    soma = ndimage.uniform_filter(t, size=janela, mode="nearest")
    peso = ndimage.uniform_filter(mascara.astype(np.float64), size=janela, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(peso > 1e-6, soma / peso, np.nan)


class PontosQuentes(Detector):
    def __init__(self, delta_min: float = 4.0, janela_frac: float = 0.12, maximo: int = 6, area_max_frac: float = 0.012):
        super().__init__(
            id="pontos-quentes",
            nome="Pontos quentes (regra)",
            tipo="regra",
            arquitetura="Contraste térmico local + componentes conectados",
            descricao="Aponta trechos do equipamento mais quentes que o equipamento em volta. Não identifica o "
            "tipo de componente; é a linha de base até o primeiro modelo treinado.",
            classes=["ponto_quente"],
            cartao={
                "treino": "Não é treinado: regra fixa.",
                "parametros": {
                    "delta_min_c": delta_min,
                    "janela_fracao_largura": janela_frac,
                    "area_maxima_fracao": area_max_frac,
                    "maximo_regioes": maximo,
                },
                "limitacoes": [
                    "Não distingue componentes (bucha, conexão, para-raio).",
                    "Reflexo do sol e bordas finas de equipamento podem gerar falsos pontos quentes.",
                    "A severidade usa o entorno como referência, não o componente semelhante de outra fase.",
                ],
            },
        )
        self.delta_min, self.janela_frac, self.maximo = delta_min, janela_frac, maximo
        self.area_max_frac = area_max_frac

    def detectar(self, temperatura: np.ndarray, imagem: np.ndarray | None = None) -> list[Deteccao]:
        objetos = mascara_objetos(temperatura)
        if objetos.sum() < 30:
            return []
        h, w = temperatura.shape
        janela = max(7, int(round(self.janela_frac * w)) | 1)
        local = media_local(temperatura, objetos, janela)
        excesso = np.where(objetos, np.nan_to_num(temperatura) - local, 0.0)
        excesso = np.nan_to_num(excesso)
        mascara = objetos & (excesso >= self.delta_min)
        mascara = ndimage.binary_opening(mascara, structure=np.ones((2, 2)))
        rotulos, n = ndimage.label(mascara)
        if n == 0:
            return []
        area_minima = max(3, int(0.0002 * h * w))
        area_maxima = max(area_minima + 1, int(self.area_max_frac * h * w))
        regioes = []
        for k, fatia in enumerate(ndimage.find_objects(rotulos), start=1):
            if fatia is None:
                continue
            dentro = rotulos[fatia] == k
            # Ponto quente é mancha compacta; faixas longas são peças inteiras (bucha, isolador).
            if not area_minima <= dentro.sum() <= area_maxima:
                continue
            pico = float(excesso[fatia][dentro].max())
            ys, xs = fatia
            folga = 2
            caixa = [
                float(max(0, xs.start - folga)),
                float(max(0, ys.start - folga)),
                float(min(w, xs.stop + folga)),
                float(min(h, ys.stop + folga)),
            ]
            confianca = float(np.clip(0.5 + (pico - self.delta_min) / 20.0, 0.5, 0.99))
            regioes.append((pico, Deteccao("ponto_quente", caixa, round(confianca, 3))))
        regioes.sort(key=lambda r: -r[0])
        return [d for _, d in regioes[: self.maximo]]
