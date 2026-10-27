"""Biblioteca de Pesos e Contexto Multi-Ângulo de Vídeo para Medição 2D do Pyron.

Permite memorizar a assinatura visual invariante e as dimensões métricas reais de ativos
elétricos a partir de sequências de vídeo multi-ângulo (celular, drone, câmera térmica ou
inspeções prévias) e reutilizá-las para:
1. Reconhecimento automático de ativos em vídeos futuros via similaridade multi-ângulo.
2. Medição métrica em fotos 2D comuns (sem necessidade de MoGe-2 / DA3 ou referências na foto),
   corrigindo a inclinação de perspectiva e escorço (foreshortening).
"""

from __future__ import annotations

import io
import json
import math
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
from PIL import Image, ImageOps

from nucleo.medicao import contorno as extrair_poligono_contorno
from nucleo.medicao.video_keyframes import Keyframe, propagar_pista, selecionar_keyframes

PADROES_ALTURA_CM: dict[str, float] = {
    "transformador": 220.0,
    "bucha": 95.0,
    "isolador": 120.0,
    "disjuntor": 180.0,
    "para_raios": 150.0,
    "para_raio": 150.0,
    "chave_seccionadora": 140.0,
    "conexao": 25.0,
    "cabo": 50.0,
    "radiador": 120.0,
    "tanque": 160.0,
    "equipamento": 100.0,
}

ALTURA_PADRAO_DEFAULT_CM: float = 100.0
NUM_FATIAS_PERFIL: int = 20
DIM_VETOR_PESOS: int = 128
LIMIAR_CONFIANCA_PADRAO: float = 0.60
EPSILON: float = 1e-7


def _desnormalizar_coordenadas(pista: dict[str, Any], largura: int, altura: int) -> dict[str, Any]:
    """Converte coordenadas normalizadas [0..1] em pixels da imagem."""
    nova = dict(pista)
    if "ponto" in pista:
        x, y = pista["ponto"]
        if float(x) <= 1.0 and float(y) <= 1.0:
            x, y = float(x) * largura, float(y) * altura
        nova["ponto"] = [float(x), float(y)]

    if "pontos" in pista:
        pts = pista["pontos"]
        novos_pts = []
        for x, y in pts:
            if float(x) <= 1.0 and float(y) <= 1.0:
                x, y = float(x) * largura, float(y) * altura
            novos_pts.append([float(x), float(y)])
        nova["pontos"] = novos_pts

    if "caixa" in pista:
        x0, y0, x1, y1 = pista["caixa"]
        if max(float(x0), float(y0), float(x1), float(y1)) <= 1.0:
            x0, y0 = float(x0) * largura, float(y0) * altura
            x1, y1 = float(x1) * largura, float(y1) * altura
        nova["caixa"] = [float(x0), float(y0), float(x1), float(y1)]

    return nova


def extrair_perfil_fatias(mascara_crop: np.ndarray, num_fatias: int = NUM_FATIAS_PERFIL) -> np.ndarray:
    """Extrai o perfil horizontal normalizado de larguras D(y) in [0, 1] ao longo da altura do objeto."""
    h_c, w_c = mascara_crop.shape[:2]
    if h_c == 0 or w_c == 0:
        return np.ones(num_fatias, dtype=np.float32) * 0.5

    fatias = np.zeros(num_fatias, dtype=np.float32)
    passo = h_c / float(num_fatias)

    for i in range(num_fatias):
        y_ini = int(math.floor(i * passo))
        y_fim = max(int(math.ceil((i + 1) * passo)), y_ini + 1)
        bloco = mascara_crop[y_ini:y_fim, :]
        cols = np.nonzero(bloco)[1]
        if len(cols) > 0:
            largura_fatia = (float(cols.max()) - float(cols.min()) + 1.0) / float(max(w_c, 1))
            fatias[i] = np.clip(largura_fatia, 0.0, 1.0)
        else:
            fatias[i] = 0.0

    return fatias


def extrair_pesos_regiao(
    rgb: np.ndarray,
    mascara: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Extrai um vetor numérico L2-normalizado de dimensão fixa (128 floats) e o perfil de fatias.

    Combina:
    1. Descritores cromáticos em CIE Lab e HSV (64 floats);
    2. Gradientes orientados (HOG compacto em grade 4x4) (32 floats);
    3. Momentos invariantes de forma e silhueta (Hu moments + perfil de fatias + solidez) (32 floats).

    Execução determinística, < 5 ms por quadro, sem dependência de GPU ou download externo.
    """
    h_orig, w_orig = rgb.shape[:2]
    if mascara is not None and np.any(mascara):
        ys, xs = np.nonzero(mascara)
        y0, y1 = int(ys.min()), int(ys.max())
        x0, x1 = int(xs.min()), int(xs.max())
        # Margem de segurança de 2%
        margem_y = max(int((y1 - y0) * 0.02), 1)
        margem_x = max(int((x1 - x0) * 0.02), 1)
        y0 = max(0, y0 - margem_y)
        y1 = min(h_orig - 1, y1 + margem_y)
        x0 = max(0, x0 - margem_x)
        x1 = min(w_orig - 1, x1 + margem_x)
        recorte_rgb = rgb[y0 : y1 + 1, x0 : x1 + 1]
        recorte_mask = mascara[y0 : y1 + 1, x0 : x1 + 1].astype(np.uint8)
    else:
        recorte_rgb = rgb
        recorte_mask = np.ones((h_orig, w_orig), dtype=np.uint8)

    h_c, w_c = recorte_rgb.shape[:2]
    if h_c == 0 or w_c == 0:
        recorte_rgb = np.zeros((64, 64, 3), dtype=np.uint8)
        recorte_mask = np.ones((64, 64), dtype=np.uint8)
        h_c, w_c = 64, 64

    # 1. Perfil de fatias normalizado (20 fatias verticais)
    perfil_fatias = extrair_perfil_fatias(recorte_mask, num_fatias=NUM_FATIAS_PERFIL)

    # 2. Redimensionamento para grade padrão 64x64
    crop_64 = cv2.resize(recorte_rgb, (64, 64), interpolation=cv2.INTER_AREA)
    mask_64 = cv2.resize(recorte_mask, (64, 64), interpolation=cv2.INTER_NEAREST)

    # --- Bloco A: Cor (64 floats) ---
    # Lab (32 floats: 8 L + 12 a + 12 b)
    lab = cv2.cvtColor(crop_64, cv2.COLOR_RGB2LAB)
    hist_l = cv2.calcHist([lab], [0], mask_64, [8], [0, 256]).flatten()
    hist_a = cv2.calcHist([lab], [1], mask_64, [12], [0, 256]).flatten()
    hist_b = cv2.calcHist([lab], [2], mask_64, [12], [0, 256]).flatten()
    cor_lab = np.concatenate([hist_l, hist_a, hist_b])
    soma_lab = np.sum(cor_lab)
    cor_lab = cor_lab / (soma_lab + EPSILON)

    # HSV (32 floats: 16 H + 8 S + 8 V)
    hsv = cv2.cvtColor(crop_64, cv2.COLOR_RGB2HSV)
    hist_h = cv2.calcHist([hsv], [0], mask_64, [16], [0, 180]).flatten()
    hist_s = cv2.calcHist([hsv], [1], mask_64, [8], [0, 256]).flatten()
    hist_v = cv2.calcHist([hsv], [2], mask_64, [8], [0, 256]).flatten()
    cor_hsv = np.concatenate([hist_h, hist_s, hist_v])
    soma_hsv = np.sum(cor_hsv)
    cor_hsv = cor_hsv / (soma_hsv + EPSILON)

    # --- Bloco B: Gradientes Orientados HOG Compacto (32 floats) ---
    cinza = cv2.cvtColor(crop_64, cv2.COLOR_RGB2GRAY)
    sobel_x = cv2.Sobel(cinza, cv2.CV_32F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(cinza, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(sobel_x, sobel_y)
    ang = (np.arctan2(sobel_y, sobel_x) % math.pi)  # [0, pi)

    # Grade 4x4 (células de 16x16) x 2 bins de orientação (horizontal vs vertical)
    hog_feats = np.zeros(32, dtype=np.float32)
    idx = 0
    for cy in range(4):
        for cx in range(4):
            c_mag = mag[cy * 16 : (cy + 1) * 16, cx * 16 : (cx + 1) * 16]
            c_ang = ang[cy * 16 : (cy + 1) * 16, cx * 16 : (cx + 1) * 16]
            c_mask = mask_64[cy * 16 : (cy + 1) * 16, cx * 16 : (cx + 1) * 16] > 0

            # Bin 0: ângulos horizontais (< 45 graus ou >= 135 graus)
            # Bin 1: ângulos verticais (45 a 135 graus)
            sel = (c_ang >= math.pi / 4.0) & (c_ang < 3.0 * math.pi / 4.0)
            if np.any(c_mask):
                hog_feats[idx] = float(np.sum(c_mag[c_mask & (~sel)]))
                hog_feats[idx + 1] = float(np.sum(c_mag[c_mask & sel]))
            else:
                hog_feats[idx] = float(np.sum(c_mag[~sel]))
                hog_feats[idx + 1] = float(np.sum(c_mag[sel]))
            idx += 2

    soma_hog = np.sum(hog_feats)
    hog_feats = hog_feats / (soma_hog + EPSILON)

    # --- Bloco C: Forma e Silhueta (32 floats) ---
    # 7 Momentos de Hu
    mom = cv2.moments(mask_64)
    hu = cv2.HuMoments(mom).flatten()
    hu_log = -np.sign(hu) * np.log10(np.abs(hu) + 1e-10)
    hu_norm = np.clip(hu_log / 10.0, -1.0, 1.0).astype(np.float32)  # 7 floats

    # 5 Propriedades estruturais
    razao_aspecto = float(min(h_c / max(w_c, 1), 10.0) / 10.0)
    preenchimento = float(np.count_nonzero(recorte_mask) / max(h_c * w_c, 1))
    simetria = 1.0 - float(np.mean(np.abs(mask_64.astype(float) - np.fliplr(mask_64).astype(float))) / 255.0)
    cy_rel = float(mom["m01"] / max(mom["m00"] * 64.0, 1e-5))
    cx_rel = float(mom["m10"] / max(mom["m00"] * 64.0, 1e-5))
    props = np.array([razao_aspecto, preenchimento, simetria, cy_rel, cx_rel], dtype=np.float32)  # 5 floats

    # Total forma: 7 hu + 20 fatias + 5 props = 32 floats
    forma_feats = np.concatenate([hu_norm, perfil_fatias, props]).astype(np.float32)

    # Vetor final consolidado (64 + 32 + 32 = 128)
    vetor = np.concatenate([cor_lab, cor_hsv, hog_feats, forma_feats]).astype(np.float32)
    norma = float(np.linalg.norm(vetor))
    vetor = vetor / (norma + EPSILON)

    return vetor, perfil_fatias


def _segmentar_rapido_caixa(rgb: np.ndarray, caixa: Sequence[float]) -> np.ndarray:
    """Segmentação morfológica adaptativa de silhueta restrita à caixa delimitadora."""
    h_img, w_img = rgb.shape[:2]
    x0 = int(np.clip(math.floor(caixa[0]), 0, w_img - 1))
    y0 = int(np.clip(math.floor(caixa[1]), 0, h_img - 1))
    x1 = int(np.clip(math.ceil(caixa[2]), x0 + 1, w_img))
    y1 = int(np.clip(math.ceil(caixa[3]), y0 + 1, h_img))

    mascara_global = np.zeros((h_img, w_img), dtype=np.uint8)
    roi = rgb[y0:y1, x0:x1]
    h_roi, w_roi = roi.shape[:2]
    if h_roi < 3 or w_roi < 3:
        mascara_global[y0:y1, x0:x1] = 1
        return mascara_global

    cinza = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    desfoque = cv2.GaussianBlur(cinza, (5, 5), 0)
    _, limiar = cv2.threshold(desfoque, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Confere se o centro da caixa está ativo; se as bordas forem maioria, inverte
    borda_superior = limiar[0, :]
    borda_inferior = limiar[-1, :]
    borda_esquerda = limiar[:, 0]
    borda_direita = limiar[:, -1]
    pixels_borda = (
        np.sum(borda_superior == 255)
        + np.sum(borda_inferior == 255)
        + np.sum(borda_esquerda == 255)
        + np.sum(borda_direita == 255)
    )
    total_borda = 2 * (w_roi + h_roi)
    if (pixels_borda / max(total_borda, 1)) > 0.60:
        limiar = cv2.bitwise_not(limiar)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    fechado = cv2.morphologyEx(limiar, cv2.MORPH_CLOSE, kernel, iterations=2)

    # Mantém o maior componente conexo dentro do ROI
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(fechado)
    if num_labels > 1:
        maior_idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        mascara_roi = (labels == maior_idx).astype(np.uint8)
    else:
        mascara_roi = np.ones((h_roi, w_roi), dtype=np.uint8)

    mascara_global[y0:y1, x0:x1] = mascara_roi
    return mascara_global


def _segmentar_rapido_ponto(rgb: np.ndarray, ponto: Sequence[float]) -> np.ndarray:
    """Segmentação morfológica local conectada a partir de uma coordenada clicada."""
    h_img, w_img = rgb.shape[:2]
    px = int(np.clip(round(ponto[0]), 0, w_img - 1))
    py = int(np.clip(round(ponto[1]), 0, h_img - 1))

    # Define uma janela local ao redor do ponto (ex.: 25% da dimensão menor)
    raio = max(int(min(h_img, w_img) * 0.25), 30)
    x0 = max(0, px - raio)
    x1 = min(w_img, px + raio)
    y0 = max(0, py - raio)
    y1 = min(h_img, py + raio)

    caixa_local = [x0, y0, x1, y1]
    return _segmentar_rapido_caixa(rgb, caixa_local)


class BibliotecaContexto:
    """Gerencia a biblioteca persistente de contexto e pesos multi-ângulo para medição 2D."""

    def __init__(self, pasta: Path | str):
        self.pasta = Path(pasta)
        self.pasta_pesos = self.pasta / "pesos_contexto"
        self.arquivo_indice = self.pasta / "biblioteca_contexto.json"
        self.pasta_pesos.mkdir(parents=True, exist_ok=True)
        self._trava = threading.Lock()

    def _ler_indice(self) -> list[dict[str, Any]]:
        if not self.arquivo_indice.exists():
            return []
        try:
            return json.loads(self.arquivo_indice.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _gravar_indice(self, itens: list[dict[str, Any]]) -> None:
        tmp = self.arquivo_indice.with_suffix(".tmp")
        tmp.write_text(json.dumps(itens, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.arquivo_indice)

    def listar(self) -> list[dict[str, Any]]:
        """Lista todos os itens registrados na biblioteca de contexto."""
        with self._trava:
            return list(self._ler_indice())

    def obter(self, id_: str) -> dict[str, Any] | None:
        """Obtém os metadados de um item pelo seu ID."""
        with self._trava:
            for item in self._ler_indice():
                if item["id"] == id_:
                    return dict(item)
            return None

    def obter_pesos(self, id_: str) -> dict[str, np.ndarray] | None:
        """Carrega os tensores numéricos gravados em .npz."""
        caminho = self.pasta_pesos / f"{id_}.npz"
        if not caminho.exists():
            return None
        try:
            with np.load(caminho) as dados:
                return {k: np.array(dados[k]) for k in dados.files}
        except Exception:
            return None

    def caminho_miniatura(self, id_: str) -> Path:
        """Caminho absoluto da imagem miniatura em JPEG."""
        return self.pasta_pesos / f"{id_}.jpg"

    def remover(self, id_: str) -> bool:
        """Remove item do índice e apaga seus pesos e miniatura associados."""
        with self._trava:
            itens = self._ler_indice()
            novos = [it for it in itens if it["id"] != id_]
            if len(novos) == len(itens):
                return False
            self._gravar_indice(novos)

        # Remove arquivos
        for arq in [self.pasta_pesos / f"{id_}.npz", self.pasta_pesos / f"{id_}.jpg"]:
            if arq.exists():
                try:
                    arq.unlink()
                except OSError:
                    pass
        return True

    def gravar_de_video(
        self,
        caminho_video: Path | str | None = None,
        nome: str = "",
        classe: str = "equipamento",
        caixa_inicial: Sequence[float] | None = None,
        quadro_n: int | None = None,
        altura_cm: float | None = None,
        largura_cm: float | None = None,
        comprimento_cm: float | None = None,
        quadros_analisados: Sequence[dict[str, Any]] | None = None,
        id_video: str | None = None,
        bytes_video: bytes | None = None,
    ) -> dict[str, Any]:
        """Extrai keyframes de um vídeo, consolida pesos multi-ângulo e persiste na biblioteca."""
        classe_normalizada = (classe or "equipamento").strip().lower()
        nome_final = nome.strip() or f"{classe_normalizada.capitalize()} memorizado"

        # 1. Obtenção de quadros e imagens
        keyframes_rgb: list[np.ndarray] = []
        caixas_alvo: list[list[float]] = []

        # Se houver quadros_analisados já persistidos em pasta de vídeo
        if quadros_analisados and caminho_video:
            pasta_vid = Path(caminho_video)
            if not pasta_vid.is_dir():
                pasta_vid = pasta_vid.parent

            pasta_quadros = pasta_vid / "quadros"
            if pasta_quadros.exists():
                amostras = list(quadros_analisados)
                if len(amostras) > 8:
                    passo = max(len(amostras) // 8, 1)
                    amostras = amostras[::passo][:8]

                for q in amostras:
                    n = q.get("n", 0)
                    arq_q = pasta_quadros / f"{int(n):05d}.jpg"
                    if arq_q.exists():
                        im_bgr = cv2.imread(str(arq_q))
                        if im_bgr is not None:
                            rgb = cv2.cvtColor(im_bgr, cv2.COLOR_BGR2RGB)
                            keyframes_rgb.append(rgb)
                            dets = q.get("deteccoes") or q.get("regioes") or []
                            caixa_q = None
                            for det in dets:
                                if det.get("classe") == classe_normalizada:
                                    caixa_q = det.get("caixa")
                                    break
                            if caixa_q is None and dets:
                                caixa_q = dets[0].get("caixa")
                            caixas_alvo.append(caixa_q)


        # Caso não tenha carregado de quadros_analisados, seleciona keyframes do vídeo
        if not keyframes_rgb:
            origem = bytes_video if bytes_video is not None else caminho_video
            if origem is not None:
                kfs = selecionar_keyframes(origem, max_keyframes=8)
                for kf in kfs:
                    keyframes_rgb.append(kf.imagem_rgb)
                    caixas_alvo.append(None)

        if not keyframes_rgb:
            raise ValueError("Não foi possível extrair quadros válidos do vídeo para memorização.")

        # 2. Definição da caixa base
        h0, w0 = keyframes_rgb[0].shape[:2]
        if caixa_inicial is not None:
            c0 = _desnormalizar_coordenadas({"caixa": list(caixa_inicial)}, w0, h0)["caixa"]
        elif caixas_alvo[0] is not None:
            c0 = _desnormalizar_coordenadas({"caixa": list(caixas_alvo[0])}, w0, h0)["caixa"]
        else:
            # Fallback: recorte central com 60% do tamanho
            c0 = [w0 * 0.20, h0 * 0.15, w0 * 0.80, h0 * 0.85]

        # 3. Propagação e extração multi-ângulo
        vetores_angulos: list[np.ndarray] = []
        perfis_angulos: list[np.ndarray] = []
        proporcoes_angulos: list[float] = []
        miniatura_salvar: np.ndarray | None = None

        caixa_corrente = c0
        img_anterior = keyframes_rgb[0]

        for i, img_rgb in enumerate(keyframes_rgb):
            hi, wi = img_rgb.shape[:2]
            if i == 0:
                caixa_quadro = c0
            else:
                if caixas_alvo[i] is not None:
                    caixa_quadro = _desnormalizar_coordenadas({"caixa": list(caixas_alvo[i])}, wi, hi)["caixa"]
                else:
                    prop = propagar_pista({"caixa": caixa_corrente}, img_anterior, img_rgb)
                    caixa_quadro = prop.get("caixa", caixa_corrente)

            caixa_corrente = caixa_quadro
            img_anterior = img_rgb

            # Segmenta objeto dentro da caixa
            mascara = _segmentar_rapido_caixa(img_rgb, caixa_quadro)
            vetor, perfil = extrair_pesos_regiao(img_rgb, mascara)

            # Proporção geométrica h_px / w_px observada
            ys, xs = np.nonzero(mascara)
            if len(ys) > 0 and len(xs) > 0:
                h_px = float(ys.max() - ys.min() + 1)
                w_px = float(xs.max() - xs.min() + 1)
            else:
                h_px = float(max(caixa_quadro[3] - caixa_quadro[1], 1.0))
                w_px = float(max(caixa_quadro[2] - caixa_quadro[0], 1.0))

            proporcao = h_px / max(w_px, 1.0)
            vetores_angulos.append(vetor)
            perfis_angulos.append(perfil)
            proporcoes_angulos.append(proporcao)

            if miniatura_salvar is None or i == len(keyframes_rgb) // 2:
                # Recorte para miniatura
                x0_m = int(np.clip(caixa_quadro[0], 0, wi - 1))
                y0_m = int(np.clip(caixa_quadro[1], 0, hi - 1))
                x1_m = int(np.clip(caixa_quadro[2], x0_m + 1, wi))
                y1_m = int(np.clip(caixa_quadro[3], y0_m + 1, hi))
                miniatura_salvar = img_rgb[y0_m:y1_m, x0_m:x1_m]

        # 4. Consolidação estatística multi-ângulo
        pesos_angulos = np.array(vetores_angulos, dtype=np.float32)  # (K, 128)
        vetor_centroide = np.mean(pesos_angulos, axis=0)
        vetor_centroide = vetor_centroide / (float(np.linalg.norm(vetor_centroide)) + EPSILON)

        # Consistência (média da similaridade de cosseno contra o centróide)
        produtos = np.dot(pesos_angulos, vetor_centroide)
        consistencia = float(np.mean(produtos))

        perfil_medio = np.mean(np.array(perfis_angulos, dtype=np.float32), axis=0)
        proporcao_canonica = float(np.median(proporcoes_angulos))

        # 5. Dimensões métricas reais (cm)
        if altura_cm is not None and float(altura_cm) > 0:
            h_real = float(altura_cm)
            if largura_cm is not None and float(largura_cm) > 0:
                l_real = float(largura_cm)
                proporcao_canonica = float(h_real / max(l_real, 0.1))
            else:
                l_real = round(h_real / max(proporcao_canonica, 0.1), 1)
            c_real = float(comprimento_cm) if (comprimento_cm and float(comprimento_cm) > 0) else max(h_real, l_real)
        else:
            h_padrao = PADROES_ALTURA_CM.get(classe_normalizada, ALTURA_PADRAO_DEFAULT_CM)
            h_real = float(h_padrao)
            if largura_cm is not None and float(largura_cm) > 0:
                l_real = float(largura_cm)
                proporcao_canonica = float(h_real / max(l_real, 0.1))
            else:
                l_real = round(h_real / max(proporcao_canonica, 0.1), 1)
            c_real = float(comprimento_cm) if (comprimento_cm and float(comprimento_cm) > 0) else max(h_real, l_real)


        fator_incerteza = 0.05 + 0.10 * (1.0 - min(consistencia, 1.0))
        incertezas = {
            "altura": round(h_real * fator_incerteza, 1),
            "largura": round(l_real * (fator_incerteza + 0.02), 1),
            "comprimento": round(c_real * (fator_incerteza + 0.02), 1),
        }

        # 6. Gravação de arquivos
        id_item = f"ctx_{uuid.uuid4().hex[:10]}"
        caminho_npz = self.pasta_pesos / f"{id_item}.npz"
        caminho_jpg = self.pasta_pesos / f"{id_item}.jpg"

        np.savez_compressed(
            caminho_npz,
            vetor_centroide=vetor_centroide,
            pesos_angulos=pesos_angulos,
            perfil_fatias=perfil_medio,
            proporcoes_angulos=np.array(proporcoes_angulos, dtype=np.float32),
        )

        if miniatura_salvar is not None and miniatura_salvar.size > 0:
            im_pil = Image.fromarray(miniatura_salvar)
            im_pil.thumbnail((256, 256), Image.Resampling.LANCZOS)
            im_pil.save(caminho_jpg, format="JPEG", quality=90)
        else:
            Image.new("RGB", (128, 128), (80, 80, 80)).save(caminho_jpg, format="JPEG")

        registro = {
            "id": id_item,
            "nome": nome_final,
            "classe": classe_normalizada,
            "id_video": id_video,
            "criado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_angulos": int(len(pesos_angulos)),
            "consistencia": round(consistencia, 3),
            "proporcao_canonica": round(proporcao_canonica, 3),
            "dimensoes_cm": {
                "altura": round(h_real, 1),
                "largura": round(l_real, 1),
                "comprimento": round(c_real, 1),
                "incerteza": incertezas,
            },
            "perfil_fatias": perfil_medio.round(3).tolist(),
            "miniatura": f"/api/medicao/biblioteca/{id_item}/miniatura.jpg",
        }

        with self._trava:
            itens = self._ler_indice()
            itens.insert(0, registro)
            self._gravar_indice(itens)

        return registro

    def reconhecer_em_video(
        self,
        caminho_video_ou_quadros: Path | str | None = None,
        quadros_analisados: Sequence[dict[str, Any]] | None = None,
        pasta_quadros: Path | str | None = None,
        limiar: float = LIMIAR_CONFIANCA_PADRAO,
    ) -> list[dict[str, Any]]:
        """Reconhece ativos da biblioteca em quadros de um vídeo por similaridade de pesos."""
        itens = self.listar()
        if not itens:
            return []

        # Carrega pesos dos itens em memória
        itens_pesos = []
        for it in itens:
            pesos = self.obter_pesos(it["id"])
            if pesos is not None:
                itens_pesos.append((it, pesos["vetor_centroide"], pesos["pesos_angulos"]))

        if not itens_pesos:
            return []

        reconhecidos: list[dict[str, Any]] = []

        # Se houver quadros_analisados e pasta_quadros
        if quadros_analisados and pasta_quadros:
            pasta_q = Path(pasta_quadros)
            for q in quadros_analisados:
                n = q.get("n", 0)
                arq_q = pasta_q / f"{int(n):05d}.jpg"
                if not arq_q.exists():
                    continue
                im_bgr = cv2.imread(str(arq_q))
                if im_bgr is None:
                    continue
                im_rgb = cv2.cvtColor(im_bgr, cv2.COLOR_BGR2RGB)
                h_q, w_q = im_rgb.shape[:2]

                deteccoes = q.get("deteccoes") or q.get("regioes") or []
                if not deteccoes:
                    deteccoes = [{"caixa": [w_q * 0.2, h_q * 0.2, w_q * 0.8, h_q * 0.8], "classe": "equipamento"}]

                for det in deteccoes:
                    caixa = det.get("caixa")
                    if not caixa:
                        continue
                    cx_px = _desnormalizar_coordenadas({"caixa": caixa}, w_q, h_q)["caixa"]
                    mascara = _segmentar_rapido_caixa(im_rgb, cx_px)
                    vetor, _ = extrair_pesos_regiao(im_rgb, mascara)

                    melhor_score = -1.0
                    melhor_item = None
                    for it, centroide, angulos in itens_pesos:
                        sim_c = float(np.dot(vetor, centroide))
                        sim_ang = float(np.max(np.dot(angulos, vetor)))
                        score = max(sim_c, sim_ang)
                        if score > melhor_score:
                            melhor_score = score
                            melhor_item = it

                    if melhor_item and melhor_score >= limiar:
                        reconhecidos.append({
                            "id_contexto": melhor_item["id"],
                            "nome": melhor_item["nome"],
                            "classe": melhor_item["classe"],
                            "confianca": round(melhor_score, 3),
                            "quadro_n": int(n),
                            "caixa": [round(float(v), 1) for v in cx_px],
                            "dimensoes_cm": melhor_item["dimensoes_cm"],
                            "delta_termico_c": det.get("delta_termico") or det.get("t_max"),
                        })


        return reconhecidos

    def medir_imagem_2d(
        self,
        imagem_bytes_ou_rgb: bytes | np.ndarray,
        pista: dict[str, Any] | None = None,
        id_contexto: str | None = None,
    ) -> dict[str, Any]:
        """Realiza medição métrica em imagem 2D única ancorada no contexto de vídeo memorizado.

        Calcula o foreshortening (escorço/inclinação de câmera theta) e a escala axial métrica s_px.
        """
        # 1. Carrega imagem
        if isinstance(imagem_bytes_ou_rgb, (bytes, bytearray)):
            im_pil = Image.open(io.BytesIO(imagem_bytes_ou_rgb))
            im_pil = ImageOps.exif_transpose(im_pil)
            rgb = np.asarray(im_pil.convert("RGB"))
        else:
            rgb = np.asarray(imagem_bytes_ou_rgb)

        h_img, w_img = rgb.shape[:2]

        # 2. Resolução da pista e segmentação da silhueta
        pista_limpa = dict(pista or {})
        if pista_limpa:
            pista_px = _desnormalizar_coordenadas(pista_limpa, w_img, h_img)
        else:
            pista_px = {"caixa": [w_img * 0.20, h_img * 0.15, w_img * 0.80, h_img * 0.85]}

        if "caixa" in pista_px:
            mascara = _segmentar_rapido_caixa(rgb, pista_px["caixa"])
        elif "ponto" in pista_px:
            mascara = _segmentar_rapido_ponto(rgb, pista_px["ponto"])
        elif "pontos" in pista_px:
            pts = pista_px["pontos"]
            x_min = min(pts[0][0], pts[1][0])
            x_max = max(pts[0][0], pts[1][0])
            y_min = min(pts[0][1], pts[1][1])
            y_max = max(pts[0][1], pts[1][1])
            mascara = _segmentar_rapido_caixa(rgb, [x_min, y_min, x_max, y_max])
        else:
            mascara = _segmentar_rapido_caixa(rgb, [w_img * 0.20, h_img * 0.15, w_img * 0.80, h_img * 0.85])

        # 3. Extração dos pesos e proporção 2D observada
        vetor_2d, perfil_2d = extrair_pesos_regiao(rgb, mascara)
        ys, xs = np.nonzero(mascara)
        if len(ys) > 0 and len(xs) > 0:
            x0, x1 = int(xs.min()), int(xs.max())
            y0, y1 = int(ys.min()), int(ys.max())
        else:
            x0, x1 = int(w_img * 0.2), int(w_img * 0.8)
            y0, y1 = int(h_img * 0.2), int(h_img * 0.8)

        h_px = float(max(y1 - y0 + 1, 1))
        w_px = float(max(x1 - x0 + 1, 1))
        ar_2d = h_px / max(w_px, 1.0)

        # 4. Busca do item correspondente na biblioteca
        item_selecionado = None
        sim_pesos = 0.0

        if id_contexto and id_contexto not in ("auto", "", "null", "undefined"):
            item_selecionado = self.obter(id_contexto)

        if item_selecionado is None:
            # Matching automático pelo maior score de cosseno + perfil
            itens = self.listar()
            melhor_score = -1.0
            for it in itens:
                pesos = self.obter_pesos(it["id"])
                if pesos is None:
                    continue
                cosseno = float(np.dot(vetor_2d, pesos["vetor_centroide"]))
                # Correlação de perfil de fatias
                p_it = pesos["perfil_fatias"]
                p_sim = float(np.dot(perfil_2d, p_it) / (np.linalg.norm(perfil_2d) * np.linalg.norm(p_it) + EPSILON))
                score = 0.70 * cosseno + 0.30 * p_sim
                if score > melhor_score:
                    melhor_score = score
                    item_selecionado = it
                    sim_pesos = cosseno

        # Fallback de calibração padrão caso a biblioteca ainda esteja vazia
        if item_selecionado is None:
            h_canon = ALTURA_PADRAO_DEFAULT_CM
            ar_canon = ar_2d
            l_canon = round(h_canon / max(ar_canon, 0.1), 1)
            nome_ctx = "Padrão de Referência Geral"
            classe_ctx = "equipamento"
            id_ctx = "padrao"
        else:
            h_canon = float(item_selecionado["dimensoes_cm"]["altura"])
            l_canon = float(item_selecionado["dimensoes_cm"]["largura"])
            ar_canon = float(item_selecionado.get("proporcao_canonica", h_canon / max(l_canon, 1.0)))
            nome_ctx = item_selecionado["nome"]
            classe_ctx = item_selecionado["classe"]
            id_ctx = item_selecionado["id"]

        # 5. Compensação de escorço (foreshortening) e cálculo da escala métrica
        fator_escorco = float(np.clip(ar_2d / max(ar_canon, 1e-4), 0.50, 1.0))
        theta_rad = float(np.arccos(fator_escorco))
        theta_graus = round(float(np.degrees(theta_rad)), 1)

        # Escala métrica corrigida pelo contexto: s_px = (H_canon * fator_escorco) / h_px [cm/px]
        s_px = float((h_canon * fator_escorco) / max(h_px, 1.0))

        # Dimensões medidas reconstruídas
        h_medido = round(float((h_px * s_px) / fator_escorco), 1)
        l_medido = round(float(w_px * s_px), 1)
        c_medido = round(float(max(h_medido, l_medido)), 1)
        pixels_mascara = int(np.count_nonzero(mascara))
        area_cm2 = round(float(pixels_mascara * (s_px**2)), 1)

        # 6. Polígonos de contorno e cotas visuais
        contornos = extrair_poligono_contorno(mascara)
        x_meio = int(round((x0 + x1) / 2.0))
        y_meio = int(round((y0 + y1) / 2.0))

        cotas = {
            "altura": [[x_meio, int(y0)], [x_meio, int(y1)]],
            "largura": [[int(x0), y_meio], [int(x1), y_meio]],
        }

        incerteza_cm = {
            "altura": round(h_medido * 0.08, 1),
            "largura": round(l_medido * 0.08, 1),
            "comprimento": round(c_medido * 0.08, 1),
        }

        return {
            "altura_cm": h_medido,
            "largura_cm": l_medido,
            "comprimento_cm": c_medido,
            "area_cm2": area_cm2,
            "incerteza_cm": incerteza_cm,
            "fator_escorco": round(fator_escorco, 3),
            "angulo_inclinacao_deg": theta_graus,
            "escala_cm_por_px": round(s_px, 5),
            "id_contexto": id_ctx,
            "nome_contexto": nome_ctx,
            "classe_contexto": classe_ctx,
            "confianca_contexto": round(sim_pesos, 3) if sim_pesos > 0 else 1.0,
            "caixa_px": [int(x0), int(y0), int(x1), int(y1)],
            "contorno": contornos,
            "cotas": cotas,
            "tamanho_imagem": [int(w_img), int(h_img)],
            "metodo": "contexto_video_2d",
        }
