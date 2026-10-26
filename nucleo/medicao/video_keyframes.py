"""Seleção de keyframes em vídeo e medição 3D multi-frame.

O vídeo (celular ou câmera) captura o objeto sob diferentes ângulos e distâncias.
Em vez de processar cada quadro a 30 FPS (custo computacional proibitivo para MoGe-2 / DA3),
este módulo seleciona os N quadros-chave mais nítidos, representativos e temporalmente
distribuídos (evitando desfoque de movimento / motion blur), propaga as pistas e
agrega as medições em um consenso estatístico com incerteza reduzida.
"""

from __future__ import annotations

import io
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


@dataclass
class Keyframe:
    indice: int
    tempo_s: float
    nitidez: float
    imagem_rgb: np.ndarray = field(repr=False)
    bytes_jpeg: bytes = field(repr=False)
    largura: int = 0
    altura: int = 0

    def para_dict(self, incluir_bytes: bool = False) -> dict[str, Any]:
        d = {
            "indice": self.indice,
            "tempo_s": round(self.tempo_s, 2),
            "nitidez": round(self.nitidez, 1),
            "largura": self.largura,
            "altura": self.altura,
        }
        if incluir_bytes:
            d["bytes_jpeg"] = self.bytes_jpeg
        return d


def calcular_nitidez(imagem: np.ndarray) -> float:
    """Calcula o índice de nitidez usando a variância do Laplaciano.
    
    Imagens com borrão de movimento (motion blur) ou fora de foco têm valores baixos.
    Imagens nítidas e com bordas bem definidas apresentam valores mais altos.
    """
    if cv2 is None:
        return 0.0
    if imagem.ndim == 3:
        cinza = cv2.cvtColor(imagem, cv2.COLOR_RGB2GRAY if imagem.shape[2] == 3 else cv2.COLOR_BGR2GRAY)
    else:
        cinza = imagem
    return float(cv2.Laplacian(cinza, cv2.CV_64F).var())


def diferenca_quadros(q1: np.ndarray, q2: np.ndarray) -> float:
    """Calcula a diferença perceptual média normalizada entre dois quadros."""
    if cv2 is None:
        return 0.0
    # Reduz para resolução baixa para focar em mudanças estruturais de pose/ângulo
    pequeno1 = cv2.resize(q1, (64, 64), interpolation=cv2.INTER_AREA)
    pequeno2 = cv2.resize(q2, (64, 64), interpolation=cv2.INTER_AREA)
    diff = np.mean(np.abs(pequeno1.astype(float) - pequeno2.astype(float)))
    return float(diff / 255.0)


def _quadro_para_jpeg(rgb: np.ndarray, qualidade: int = 92) -> bytes:
    if cv2 is None:
        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format="JPEG", quality=qualidade)
        return buf.getvalue()
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, qualidade])
    if not ok:
        raise ValueError("Falha ao codificar quadro em JPEG")
    return buf.tobytes()


def selecionar_keyframes(
    origem: str | Path | bytes,
    max_keyframes: int = 5,
    min_distancia_s: float = 0.4,
    fps_amostragem: float = 4.0,
    limiar_nitidez: float = 20.0,
) -> list[Keyframe]:
    """Abre um vídeo e seleciona os melhores keyframes nítidos distribuídos no tempo.
    
    Args:
        origem: Caminho do arquivo ou bytes do vídeo em memória.
        max_keyframes: Número máximo de quadros-chave a selecionar (padrão 5).
        min_distancia_s: Intervalo temporal mínimo entre dois keyframes (evita duplicidade).
        fps_amostragem: Taxa de amostragem de candidatos por segundo de vídeo.
        limiar_nitidez: Nitidez mínima para considerar um quadro aproveitável.
        
    Returns:
        Lista ordenada no tempo com os Keyframes selecionados.
    """
    if cv2 is None:
        raise ImportError("OpenCV (cv2) é necessário para processar vídeo.")

    caminho_temporario: str | None = None
    if isinstance(origem, (bytes, bytearray)):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(origem)
            caminho_temporario = tmp.name
        caminho_video = caminho_temporario
    else:
        caminho_video = str(origem)

    try:
        cap = cv2.VideoCapture(caminho_video)
        if not cap.isOpened():
            raise ValueError("Não foi possível abrir o arquivo de vídeo.")

        fps_orig = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        total_quadros = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total_quadros <= 0:
            total_quadros = 1

        duracao_s = total_quadros / max(fps_orig, 1.0)
        passo_quadros = max(1, int(round(fps_orig / max(fps_amostragem, 0.5))))

        candidatos: list[dict] = []
        indice_atual = 0

        while True:
            ret, bgr = cap.read()
            if not ret or bgr is None:
                break

            if indice_atual % passo_quadros == 0:
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                tempo_s = indice_atual / fps_orig
                score_nitidez = calcular_nitidez(rgb)
                candidatos.append({
                    "indice": indice_atual,
                    "tempo_s": tempo_s,
                    "nitidez": score_nitidez,
                    "rgb": rgb,
                })

            indice_atual += 1

        cap.release()

        if not candidatos:
            raise ValueError("O vídeo não contém quadros legíveis para amostragem.")

        # Se houver candidatos acima do limiar, prioriza; caso contrário, usa os melhores disponíveis
        aprovados = [c for c in candidatos if c["nitidez"] >= limiar_nitidez]
        if not aprovados:
            aprovados = candidatos

        # Particiona os candidatos em janelas temporais para garantir cobertura ao longo do vídeo
        n_janelas = min(max_keyframes, len(aprovados))
        t_inicio = candidatos[0]["tempo_s"]
        t_fim = candidatos[-1]["tempo_s"]
        tam_janela = max((t_fim - t_inicio) / max(n_janelas, 1), min_distancia_s)

        selecionados: list[dict] = []
        ultimo_tempo = -min_distancia_s

        for j in range(n_janelas):
            inicio_j = t_inicio + j * tam_janela
            fim_j = inicio_j + tam_janela
            quadros_janela = [
                c for c in aprovados
                if inicio_j <= c["tempo_s"] <= fim_j and (c["tempo_s"] - ultimo_tempo) >= (min_distancia_s * 0.7)
            ]
            if not quadros_janela:
                quadros_janela = [c for c in aprovados if (c["tempo_s"] - ultimo_tempo) >= (min_distancia_s * 0.7)]
            if not quadros_janela:
                continue

            # Escolhe o mais nítido na janela
            melhor = max(quadros_janela, key=lambda c: c["nitidez"])
            selecionados.append(melhor)
            ultimo_tempo = melhor["tempo_s"]

        # Se selecionou menos que o desejado e há opções espaçadas, completa com os de maior nitidez restante
        if len(selecionados) < max_keyframes:
            indices_ja_escolhidos = {s["indice"] for s in selecionados}
            restantes = [
                c for c in aprovados
                if c["indice"] not in indices_ja_escolhidos
                and all(abs(c["tempo_s"] - s["tempo_s"]) >= (min_distancia_s * 0.5) for s in selecionados)
            ]
            restantes.sort(key=lambda c: c["nitidez"], reverse=True)
            for r in restantes[: max_keyframes - len(selecionados)]:
                selecionados.append(r)

        # Ordena cronologicamente
        selecionados.sort(key=lambda c: c["tempo_s"])

        keyframes: list[Keyframe] = []
        for s in selecionados:
            rgb = s["rgb"]
            h, w = rgb.shape[:2]
            jpeg_bytes = _quadro_para_jpeg(rgb)
            keyframes.append(
                Keyframe(
                    indice=s["indice"],
                    tempo_s=s["tempo_s"],
                    nitidez=s["nitidez"],
                    imagem_rgb=rgb,
                    bytes_jpeg=jpeg_bytes,
                    largura=w,
                    altura=h,
                )
            )

        return keyframes

    finally:
        if caminho_temporario and os.path.exists(caminho_temporario):
            try:
                os.remove(caminho_temporario)
            except OSError:
                pass


def propagar_pista(pista: dict, img_origem: np.ndarray, img_destino: np.ndarray) -> dict:
    """Propaga a localização da pista (ponto ou caixa) de um keyframe para outro.
    
    Usa rastreamento por fluxo óptico ou translação robusta de centroides.
    Se a propagação falhar ou for incerta, mantém a pista original como fallback.
    """
    if cv2 is None:
        return dict(pista)

    cinza1 = cv2.cvtColor(img_origem, cv2.COLOR_RGB2GRAY) if img_origem.ndim == 3 else img_origem
    cinza2 = cv2.cvtColor(img_destino, cv2.COLOR_RGB2GRAY) if img_destino.ndim == 3 else img_destino

    nova_pista = dict(pista)

    if "ponto" in pista:
        pt = np.array([[pista["ponto"]]], dtype=np.float32)
        pt_novo, status, _ = cv2.calcOpticalFlowPyrLK(cinza1, cinza2, pt, None, winSize=(31, 31), maxLevel=3)
        if status is not None and status[0][0] == 1:
            nova_pista["ponto"] = [float(pt_novo[0][0][0]), float(pt_novo[0][0][1])]
        return nova_pista

    if "pontos" in pista:
        pts = np.array([pista["pontos"]], dtype=np.float32)
        pts_novos, status, _ = cv2.calcOpticalFlowPyrLK(cinza1, cinza2, pts, None, winSize=(31, 31), maxLevel=3)
        if status is not None and np.all(status == 1):
            nova_pista["pontos"] = [
                [float(pts_novos[0][0][0]), float(pts_novos[0][0][1])],
                [float(pts_novos[0][1][0]), float(pts_novos[0][1][1])],
            ]
        return nova_pista

    if "caixa" in pista:
        x0, y0, x1, y1 = pista["caixa"]
        w = max(x1 - x0, 1.0)
        h = max(y1 - y0, 1.0)
        # Amostra grade de pontos dentro da caixa
        xs = np.linspace(x0 + w * 0.2, x1 - w * 0.2, 5)
        ys = np.linspace(y0 + h * 0.2, y1 - h * 0.2, 5)
        grade = np.array([[[x, y]] for y in ys for x in xs], dtype=np.float32)

        pts_novos, status, _ = cv2.calcOpticalFlowPyrLK(cinza1, cinza2, grade, None, winSize=(31, 31), maxLevel=3)
        if status is not None:
            validos = status.ravel() == 1
            if validos.sum() >= 5:
                deslocamento = pts_novos.reshape(-1, 2)[validos] - grade.reshape(-1, 2)[validos]
                dx, dy = np.median(deslocamento, axis=0)
                nova_pista["caixa"] = [float(x0 + dx), float(y0 + dy), float(x1 + dx), float(y1 + dy)]
        return nova_pista

    return nova_pista


def agregar_medicoes(medidas: list[Any]) -> dict[str, Any]:
    """Consolida as medições individuais de múltiplos keyframes em um consenso estatístico.
    
    A combinação de múltiplos pontos de vista reduz a incerteza estatística (erro cai com ~1/sqrt(N)).
    """
    if not medidas:
        return {}

    campos = ["comprimento_cm", "largura_cm", "altura_cm", "espessura_cm", "distancia_cm"]
    consenso: dict[str, Any] = {}

    for c in campos:
        valores = [getattr(m, c) for m in medidas if getattr(m, c, None) is not None]
        if not valores:
            continue

        arr = np.array(valores, dtype=float)
        mediana = float(np.median(arr))
        desvio = float(np.std(arr)) if len(arr) > 1 else 0.0
        n_amostras = len(arr)

        # Ganho teórico na redução de incerteza por amostragem multi-frame
        fator_reducao = round((1.0 - (1.0 / math.sqrt(n_amostras))) * 100.0, 1) if n_amostras > 1 else 0.0

        consenso[c] = {
            "valor": round(mediana, 2),
            "desvio_padrao": round(desvio, 2),
            "minimo": round(float(np.min(arr)), 2),
            "maximo": round(float(np.max(arr)), 2),
            "n_quadros": n_amostras,
            "reducao_incerteza_pct": fator_reducao,
        }

    metodos = [getattr(m, "metodo", "") for m in medidas]
    consenso["metodo"] = metodos[0] if len(set(metodos)) == 1 else "misto"
    consenso["total_quadros"] = len(medidas)
    return consenso


def medir_video(
    video_origem: str | Path | bytes,
    pista_inicial: dict,
    referencia: dict | None = None,
    max_keyframes: int = 4,
    medidor=None,
) -> dict[str, Any]:
    """Pipeline completa: extrai keyframes nítidos, propaga a pista, mede e gera consenso."""
    from nucleo import medicao as medicao_mod

    keyframes = selecionar_keyframes(video_origem, max_keyframes=max_keyframes)
    if not keyframes:
        raise ValueError("Nenhum keyframe válido pôde ser extraído do vídeo.")

    medidas = []
    detalhes_quadros = []
    pista_corrente = pista_inicial
    img_anterior = keyframes[0].imagem_rgb

    for i, kf in enumerate(keyframes):
        if i > 0:  # de quadro em quadro: a pista do anterior segue para este (a do 1º só vale no 1º)
            pista_corrente = propagar_pista(pista_corrente, img_anterior, kf.imagem_rgb)

        if medidor is not None:
            m = medidor.medir(kf.bytes_jpeg, pista_corrente, referencia)
        else:
            m = medicao_mod.medir(kf.bytes_jpeg, pista_corrente, referencia)

        medidas.append(m)
        detalhes_quadros.append({
            "keyframe": kf.para_dict(),
            "pista": pista_corrente,
            "medida": m.para_dict(),
        })
        img_anterior = kf.imagem_rgb

    consenso = agregar_medicoes(medidas)

    return {
        "consenso": consenso,
        "quadros": detalhes_quadros,
        "n_keyframes": len(keyframes),
    }


def comparar_video(
    video_origem: str | Path | bytes,
    pista_inicial: dict,
    referencia: dict | None = None,
    max_keyframes: int = 4,
    comparar=None,
) -> dict[str, Any]:
    """Como ``medir_video``, mas cada quadro passa por ``medicao.comparar`` (DA3 e MoGe-2, sem e com a referência)
    e o consenso sai por modelo e modo: ``{"consenso": {modelo: {modo: {campo: {...}}}}, "quadros": [...]}``.
    A pista vale no 1º quadro e segue o objeto de quadro em quadro; quadro onde o objeto se perde fica de fora."""
    from types import SimpleNamespace

    if comparar is None:
        from nucleo import medicao as medicao_mod

        comparar = medicao_mod.comparar
    keyframes = selecionar_keyframes(video_origem, max_keyframes=max_keyframes)
    if not keyframes:
        raise ValueError("Nenhum quadro nítido no vídeo: grave mais devagar, com o objeto parado e bem iluminado.")

    quadros: list[dict] = []
    pista, anterior = pista_inicial, keyframes[0].imagem_rgb
    for i, kf in enumerate(keyframes):
        if i > 0:
            pista = propagar_pista(pista, anterior, kf.imagem_rgb)
        anterior = kf.imagem_rgb
        try:
            r = comparar(kf.bytes_jpeg, pista, referencia)
        except ValueError as e:
            quadros.append({"keyframe": kf.para_dict(), "pista": pista, "erro": str(e)})
            continue
        quadros.append({"keyframe": kf.para_dict(), "pista": pista, "resultados": r["resultados"], "contorno": r.get("contorno", [])})

    validos = [q for q in quadros if "resultados" in q]
    if not validos:
        raise ValueError(quadros[0]["erro"])
    consenso: dict = {}
    for modelo in validos[0]["resultados"]:
        for modo in ("sem_referencia", "com_referencia"):
            medidas = [SimpleNamespace(**q["resultados"][modelo][modo]) for q in validos if (q["resultados"].get(modelo) or {}).get(modo)]
            if medidas:
                consenso.setdefault(modelo, {})[modo] = agregar_medicoes(medidas)
    return {"consenso": consenso, "quadros": quadros, "n_keyframes": len(keyframes), "jpeg_primeiro": keyframes[0].bytes_jpeg}
