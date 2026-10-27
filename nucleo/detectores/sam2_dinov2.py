"""Detector automático de ativos elétricos com modelos fundacionais (SAM 2 + DINOv2 + Criminisi).

Pipeline:
1. SAM 2 (AutomaticMaskGenerator): descobre propostas de regiões e máscaras de ativos na cena.
2. DINOv2 (ViT): classifica cada ativo (bucha, isolador, para-raio, transformador, conexão).
3. Geometria Projetiva (Criminisi): calcula altura métrica H, largura média, diâmetro máx e área.
4. Termografia Isolada: extrai Tmáx, Tmed e anomalias térmicas estritamente no corpo da peça.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np
import torch

from nucleo.detectores import Deteccao, Detector
from nucleo.detectores.pontos_quentes import PontosQuentes

log = logging.getLogger(__name__)

CLASSES_ATIVOS = [
    "bucha",
    "isolador",
    "para_raio",
    "transformador",
    "conexao",
    "radiador",
    "cabo",
]

NOMES_ATIVOS = {
    "bucha": "Bucha",
    "isolador": "Isolador",
    "para_raio": "Para-raio",
    "transformador": "Transformador",
    "conexao": "Conexão",
    "radiador": "Radiador",
    "cabo": "Condutor/Cabo",
    "ponto_quente": "Ponto quente",
}

PADROES_ALTURA = {
    "isolador": 0.80,
    "bucha": 1.25,
    "para_raio": 1.20,
    "transformador": 1.60,
    "conexao": 0.50,
    "radiador": 1.20,
    "cabo": 1.00,
}


def calcular_iou_boxes(box_a: Sequence[float], box_b: Sequence[float]) -> float:
    """Calcula sobreposição máxima (IoU ou contenção) entre duas caixas [x0, y0, x1, y1]."""
    x_esq = max(box_a[0], box_b[0])
    y_topo = max(box_a[1], box_b[1])
    x_dir = min(box_a[2], box_b[2])
    y_fundo = min(box_a[3], box_b[3])

    if x_dir <= x_esq or y_fundo <= y_topo:
        return 0.0

    intersecao = (x_dir - x_esq) * (y_fundo - y_topo)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    uniao = area_a + area_b - intersecao
    iou = intersecao / max(uniao, 1e-6)
    contencao = intersecao / max(min(area_a, area_b), 1e-6)
    return max(iou, contencao)


def simplificar_contorno_binario(mascara: np.ndarray, epsilon: float = 1.0) -> list[list[float]]:
    """Extrai contorno vetorial simplificado para renderização SVG com fechamento morfológico anti-ruído."""
    binaria = (np.asarray(mascara) > 0).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, kernel)
    contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contornos:
        return []
    maior = max(contornos, key=cv2.contourArea)
    aproximado = cv2.approxPolyDP(maior, epsilon=epsilon, closed=True)
    return [[float(p[0][0]), float(p[0][1])] for p in aproximado]


class SAM2DINOv2Detector(Detector):
    """Detector fundacional automático: segmenta com SAM 2, classifica com DINOv2 e mede dimensões."""

    def __init__(
        self,
        caminho_pesos_sam2: Path | str | None = None,
        conf_minima: float = 0.40,
        iou_nms: float = 0.45,
    ) -> None:
        self.id = "sam2-dinov2"
        self.nome = "SAM 2 + DINOv2 (Identificação e Metrologia Automática)"
        self.tipo = "aprendizado"
        self.arquitetura = "Meta SAM 2 (Hiera) + DINOv2 (ViT) + Criminisi Single View Metrology"
        self.descricao = (
            "Descobre e segmenta os ativos elétricos da subestação automaticamente com SAM 2, "
            "classifica com DINOv2 e calcula dimensões físicas reais e pureza térmica."
        )
        self.classes = CLASSES_ATIVOS + ["ponto_quente"]
        self.nomes = NOMES_ATIVOS
        self.precisa_imagem = True
        self.conf_minima = conf_minima
        self.iou_nms = iou_nms
        self._caminho_pesos = Path(caminho_pesos_sam2) if caminho_pesos_sam2 else Path("modelos/sam2/sam2.1_hiera_small.pt")
        self._mask_generator = None
        self.cartao = {
            "treino": "SAM 2 (Meta AI) + DINOv2 ViT (Meta AI) pré-treinados em escala fundacional",
            "parametros": {"conf_minima": conf_minima, "iou_nms": iou_nms},
            "vantagens": [
                "Identificação e segmentação de ativos inteiros sem depender de caixa manual.",
                "Classificação zero-shot/few-shot com representações fundacionais DINOv2.",
                "Cálculo automático de altura, largura média, diâmetro máximo e área projetada.",
            ],
            "limitacoes": [
                "Demanda GPU CUDA para inferência ágil (segundos por imagem).",
            ],
        }

    def _obter_generator(self):
        if self._mask_generator is not None:
            return self._mask_generator

        from sam2.build_sam import build_sam2
        from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator

        dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
        cfg = "configs/sam2.1/sam2.1_hiera_s.yaml"
        sam2 = build_sam2(cfg, str(self._caminho_pesos), device=dispositivo)
        self._mask_generator = SAM2AutomaticMaskGenerator(
            sam2,
            points_per_side=16,
            pred_iou_thresh=0.75,
            stability_score_thresh=0.85,
            min_mask_region_area=3500,
        )
        return self._mask_generator

    def detectar(
        self,
        temperatura: np.ndarray,
        imagem: np.ndarray | None = None,
        metadados: dict | None = None,
    ) -> list[Deteccao]:
        """Detecta ativos elétricos na imagem e retorna caixas com classes e metadados completos."""
        regioes = self.detectar_com_metrologia(temperatura, imagem, metadados=metadados)
        return [Deteccao(classe=r["classe"], caixa=r["caixa"], confianca=r["confianca"]) for r in regioes]

    def detectar_com_metrologia(
        self,
        temperatura: np.ndarray,
        imagem: np.ndarray | None = None,
        metadados: dict | None = None,
    ) -> list[dict]:
        """Executa a detecção completa com máscaras SAM 2, classificações DINOv2 e metrologia projetiva."""
        from nucleo.classificacao.dinov2_engine import DINOv2Classifier
        from nucleo.metrologia.vanishing_points import VanishingGeometryEstimator
        from nucleo.metrologia.criminisi_metrology import ProjectiveMetrologyEngine
        from nucleo.pipeline.pyron_pipeline import estatisticas_termicas

        if imagem is None:
            from nucleo import render

            imagem = render.colorir(temperatura, nome="ferro")

        rgb = np.asarray(imagem)
        matriz = np.asarray(temperatura)
        h_rgb, w_rgb = rgb.shape[:2]
        h_mat, w_mat = matriz.shape[:2]
        area_total = h_rgb * w_rgb

        # 1. Geração automática de propostas de máscaras com SAM 2
        generator = self._obter_generator()
        try:
            raw_masks = generator.generate(rgb)
        except Exception as e:
            log.warning("Falha no SAM2AutomaticMaskGenerator: %s. Utilizando fallback.", e)
            raw_masks = []

        clf = DINOv2Classifier.obter_instancia()
        p_engine = ProjectiveMetrologyEngine(default_unit="m")

        # Geometria projetiva da cena (pontos de fuga e horizonte)
        try:
            vp_est = VanishingGeometryEstimator()
            geom_res = vp_est.estimate(rgb)
            hz_y = geom_res["horizon_y_center"]
            vz = geom_res["vanishing_point_z"]
        except Exception:
            hz_y = float(h_rgb * 2.0)
            vz = (float(w_rgb / 2.0), -10000.0)

        # 2. Filtragem, classificação DINOv2 e medição dos ativos candidatos
        candidatos = []
        for m_item in raw_masks:
            mask = m_item["segmentation"].astype(np.uint8)
            area = int(m_item["area"])
            bbox_xywh = [int(v) for v in m_item["bbox"]]
            x0, y0, w, h = bbox_xywh
            x1, y1 = x0 + w, y0 + h
            caixa_rgb = [float(x0), float(y0), float(x1), float(y1)]

            # Descarta máscaras que cobrem quase toda a imagem ou ruídos desproporcionais (sensibilidade adaptativa)
            area_min = max(80, int(area_total * 0.002))
            area_max = int(area_total * 0.88)
            if area > area_max or area < area_min:
                continue

            # Classificação DINOv2 com máscara
            res_dino = clf.classificar(rgb, bbox=caixa_rgb, mascara=mask)
            classe = res_dino["classe"]
            conf = float(res_dino["confianca"])

            # Descarta ruídos de baixa confiança ou falsos pontos quentes
            if conf < self.conf_minima or classe in ("ponto_quente", "fundo"):
                continue

            candidatos.append({
                "mask_rgb": mask,
                "caixa_rgb": caixa_rgb,
                "area_px": area,
                "classe": classe,
                "nome_classe": res_dino["nome"],
                "confianca": conf,
                "scores": res_dino.get("scores", {}),
                "score_sam2": float(m_item.get("predicted_iou", 0.95)),
            })

        # 3. Non-Maximum Suppression (NMS) baseado em IoU e confiança
        candidatos.sort(key=lambda x: (x["confianca"] * ((x["caixa_rgb"][3] - x["caixa_rgb"][1]) / max(x["caixa_rgb"][2] - x["caixa_rgb"][0], 1))), reverse=True)
        selecionados = []
        for cand in candidatos:
            sobreposto = False
            for sel in selecionados:
                iou = calcular_iou_boxes(cand["caixa_rgb"], sel["caixa_rgb"])
                if iou > self.iou_nms:
                    sobreposto = True
                    break
            if not sobreposto:
                selecionados.append(cand)

        # 4. Enriquecimento de cada ativo com contorno SVG, metrologia e termometria
        sx = w_mat / w_rgb
        sy = h_mat / h_rgb
        regioes_finais = []
        contagem: dict[str, int] = {}

        dist_m = None
        if metadados:
            try:
                d = metadados.get("distancia_m")
                if d is not None and float(d) > 0:
                    dist_m = float(d)
            except (ValueError, TypeError):
                dist_m = None

        for sel in selecionados:
            classe = sel["classe"]
            contagem[classe] = contagem.get(classe, 0) + 1
            mask_rgb = sel["mask_rgb"]
            h_ref = PADROES_ALTURA.get(classe, 1.0)

            ys, _ = np.nonzero(mask_rgb)
            pts_y = (float(ys.max()), float(ys.min())) if len(ys) else (sel["caixa_rgb"][3], sel["caixa_rgb"][1])

            # Metrologia Inteligente (Método 1: Telemetria Óptica prioritária; Método 2: Geometria Projetiva)
            if dist_m:
                dim_res = p_engine.compute_dimensions_from_telemetry(
                    mask=mask_rgb,
                    distance_m=dist_m,
                    camera_model=metadados.get("camera"),
                    image_width=w_rgb,
                )
            else:
                dim_res = p_engine.compute_real_dimensions(
                    mask=mask_rgb,
                    horizon_y=hz_y,
                    vz=vz,
                    ref_height_meters=h_ref,
                    ref_points_y=pts_y,
                )

            # Redimensiona máscara e caixa para coordenadas da matriz térmica
            if (w_mat, h_mat) != (w_rgb, h_rgb):
                mask_mat = cv2.resize(mask_rgb, (w_mat, h_mat), interpolation=cv2.INTER_NEAREST)
                caixa_mat = [
                    round(sel["caixa_rgb"][0] * sx, 2),
                    round(sel["caixa_rgb"][1] * sy, 2),
                    round(sel["caixa_rgb"][2] * sx, 2),
                    round(sel["caixa_rgb"][3] * sy, 2),
                ]
            else:
                mask_mat = mask_rgb
                caixa_mat = [round(v, 2) for v in sel["caixa_rgb"]]

            # Contorno SVG no espaço da matriz
            contorno = simplificar_contorno_binario(mask_mat, epsilon=1.0)

            # Pureza térmica dentro do ativo
            stat_termica = estatisticas_termicas(matriz, mask_mat)

            geometria = {
                "unit": "m",
                "metodo_metrologia": dim_res.get("metodo_metrologia", "telemetria_optica" if dist_m else "geometria_projetiva_criminisi"),
                "detalhes_metrologia": dim_res.get("detalhes_metrologia", f"Referência projetiva: {h_ref:.2f}m"),
                "height_meters": dim_res["height_meters"],
                "mean_width_meters": dim_res["mean_width_meters"],
                "max_diameter_meters": dim_res["max_diameter_meters"],
                "min_diameter_meters": dim_res["min_diameter_meters"],
                "projected_area_m2": dim_res["projected_area_m2"],
                "aspect_ratio": dim_res["aspect_ratio"],
                "scale_y_m_per_px": dim_res["scale_y_m_per_px"],
                "ref_height_meters": h_ref,
                "distancia_m": dist_m,
                "length_metric": dim_res["height_meters"],
                "width_metric": dim_res["max_diameter_meters"],
                "mean_width_metric": dim_res["mean_width_meters"],
                "area_metric": dim_res["projected_area_m2"],
                "metric_ratio": dim_res["scale_y_m_per_px"],
                "diameter_profile": dim_res.get("diameter_profile"),
                "area_px": float(mask_mat.sum()),
                "length_px": float(ys.max() - ys.min() + 1) * sy if len(ys) else 0.0,
            }

            regioes_finais.append({
                "id": None,
                "nome": f"{sel['nome_classe']} {contagem[classe]}",
                "classe": classe,
                "caixa": caixa_mat,
                "confianca": round(sel["confianca"], 4),
                "origem": "detector:sam2_dinov2",
                "segmentacao": {
                    "score": round(sel["score_sam2"], 4),
                    "geometria": geometria,
                    "termica_isolada": asdict(stat_termica) if stat_termica else None,
                    "contorno": contorno,
                },
                "classificacao_dinov2": {
                    "classe": classe,
                    "confianca": round(sel["confianca"], 4),
                    "nome": sel["nome_classe"],
                    "scores": sel["scores"],
                },
            })

        # 5. Adiciona pontos quentes pontuais encontrados pela regra térmica (se não contidos em ativo)
        det_termico = PontosQuentes()
        pontos_quentes = det_termico.detectar(matriz, imagem)
        for pq in pontos_quentes:
            cx = (pq.caixa[0] + pq.caixa[2]) / 2.0
            cy = (pq.caixa[1] + pq.caixa[3]) / 2.0
            
            # Verifica se já está coberto por algum ativo detectado
            contido = False
            for reg in regioes_finais:
                bx = reg["caixa"]
                if bx[0] <= cx <= bx[2] and bx[1] <= cy <= bx[3]:
                    contido = True
                    break
            
            if not contido:
                regioes_finais.append({
                    "id": None,
                    "nome": f"Ponto quente {len(regioes_finais) + 1}",
                    "classe": "ponto_quente",
                    "caixa": [round(v, 2) for v in pq.caixa],
                    "confianca": round(pq.confianca, 2),
                    "origem": "modelo:pontos-quentes",
                })

        return regioes_finais
