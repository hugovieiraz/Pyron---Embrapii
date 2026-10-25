#!/usr/bin/env python3
"""
validate_cv_dataset.py
Script determinístico para validação e auditoria de datasets de Visão Computacional.
Aplica princípios de Clean Code, validação de integridade de imagens e detecção de anomalias.
"""

import os
import sys
import argparse
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validador determinístico de datasets de Visão Computacional (Clean Code)."
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        required=True,
        help="Diretório raiz do dataset a ser validado."
    )
    parser.add_argument(
        "--format",
        choices=["auto", "yolo", "classification", "generic"],
        default="auto",
        help="Estrutura esperada do dataset (padrão: auto)."
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Caminho para exportar o relatório de auditoria em formato JSON."
    )
    return parser.parse_args()


def verify_image_integrity(image_path: Path) -> Tuple[bool, Optional[str], Optional[Tuple[int, int]]]:
    """
    Verifica integridade física da imagem e retorna resolução (largura, altura).
    """
    if image_path.stat().st_size == 0:
        return False, "Arquivo vazio (0 bytes)", None

    try:
        from PIL import Image, ImageFile
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        with Image.open(image_path) as img:
            img.verify()
        
        # Reabrir para obter dimensões (verify() pode invalidar o objeto)
        with Image.open(image_path) as img:
            return True, None, img.size
    except ImportError:
        # Fallback sem PIL: validação de existência e tamanho básico
        return True, "PIL não instalado (verificação limitada ao tamanho de arquivo)", None
    except Exception as exc:
        return False, str(exc), None


def validate_yolo_labels(label_path: Path) -> Tuple[bool, List[str], int]:
    """
    Valida formato de anotação YOLO (class_id x_center y_center width height normalizados em [0, 1]).
    """
    errors: List[str] = []
    box_count = 0

    if not label_path.exists():
        return False, ["Arquivo de anotação correspondente ausente"], 0

    try:
        with open(label_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        for line_idx, line in enumerate(lines, start=1):
            parts = line.split()
            if len(parts) < 5:
                errors.append(f"Linha {line_idx}: formato inválido (menos de 5 campos). Conteúdo: '{line}'")
                continue

            try:
                class_id = int(parts[0])
                coords = [float(p) for p in parts[1:5]]
            except ValueError:
                errors.append(f"Linha {line_idx}: coordenadas ou classe não numéricas: '{line}'")
                continue

            # Checar coordenadas normalizadas [0, 1]
            for coord_val in coords:
                if coord_val < 0.0 or coord_val > 1.0:
                    errors.append(f"Linha {line_idx}: coordenada fora do intervalo normalizado [0, 1]: {coord_val}")

            box_count += 1

        return len(errors) == 0, errors, box_count
    except Exception as exc:
        return False, [f"Falha ao ler arquivo de anotação: {str(exc)}"], 0


def detect_dataset_format(data_dir: Path) -> str:
    """Detecta automaticamente o formato do dataset com base na estrutura de pastas."""
    subdirs = [p.name.lower() for p in data_dir.iterdir() if p.is_dir()]
    if "images" in subdirs or "labels" in subdirs:
        return "yolo"
    if any(p in subdirs for p in ["train", "val", "test"]):
        # Checar se dentro de train há images/labels
        train_dir = data_dir / "train"
        if train_dir.is_dir() and any(p in [s.name.lower() for s in train_dir.iterdir() if s.is_dir()] for p in ["images", "labels"]):
            return "yolo"
        return "classification"
    return "generic"


def run_audit(data_dir_path: Path, expected_format: str) -> Dict[str, Any]:
    resolved_format = expected_format if expected_format != "auto" else detect_dataset_format(data_dir_path)

    images_found: List[Path] = []
    for ext in VALID_IMAGE_EXTENSIONS:
        images_found.extend(data_dir_path.rglob(f"*{ext}"))
        images_found.extend(data_dir_path.rglob(f"*{ext.upper()}"))

    # Remover duplicatas (Windows case-insensitive)
    images_found = sorted(list({p.resolve(): p for p in images_found}.values()))

    total_images = len(images_found)
    corrupted_images: List[Dict[str, str]] = []
    valid_images_count = 0
    yolo_annotation_errors: List[Dict[str, Any]] = []
    total_bounding_boxes = 0
    resolutions: List[Tuple[int, int]] = []

    for img_path in images_found:
        is_valid, error_msg, size = verify_image_integrity(img_path)
        if not is_valid:
            corrupted_images.append({
                "path": str(img_path),
                "error": error_msg or "Erro desconhecido"
            })
            continue

        valid_images_count += 1
        if size:
            resolutions.append(size)

        if resolved_format == "yolo":
            # Tenta encontrar labels/ correspondente a images/
            str_path = str(img_path)
            if "images" in str_path:
                label_str = str_path.replace("images", "labels")
                label_path = Path(label_str).with_suffix(".txt")
            else:
                label_path = img_path.with_suffix(".txt")

            has_valid_label, label_errs, box_count = validate_yolo_labels(label_path)
            total_bounding_boxes += box_count
            if not has_valid_label:
                yolo_annotation_errors.append({
                    "image": str(img_path),
                    "label": str(label_path),
                    "errors": label_errs
                })

    report: Dict[str, Any] = {
        "dataset_root": str(data_dir_path),
        "detected_format": resolved_format,
        "total_images": total_images,
        "valid_images": valid_images_count,
        "corrupted_images_count": len(corrupted_images),
        "corrupted_images": corrupted_images[:50],  # Limitar saída
        "has_integrity_errors": len(corrupted_images) > 0,
    }

    if resolved_format == "yolo":
        report["yolo_stats"] = {
            "total_bounding_boxes": total_bounding_boxes,
            "label_errors_count": len(yolo_annotation_errors),
            "label_errors": yolo_annotation_errors[:50]
        }

    if resolutions:
        widths = [w for w, _ in resolutions]
        heights = [h for _, h in resolutions]
        report["resolution_stats"] = {
            "min_resolution": f"{min(widths)}x{min(heights)}",
            "max_resolution": f"{max(widths)}x{max(heights)}",
            "average_resolution": f"{int(sum(widths)/len(widths))}x{int(sum(heights)/len(heights))}"
        }

    return report


def main() -> None:
    args = parse_arguments()
    data_dir = Path(args.data_dir).resolve()

    if not data_dir.exists() or not data_dir.is_dir():
        print(f"[-] Erro: O diretório '{data_dir}' não existe ou não é válido.", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Iniciando auditoria do dataset em: {data_dir}")
    report = run_audit(data_dir, args.format)

    print("\n" + "=" * 60)
    print(" Relatório de Auditoria do Dataset de Visão Computacional")
    print("=" * 60)
    print(f" Formato detectado: {report['detected_format']}")
    print(f" Total de imagens:  {report['total_images']}")
    print(f" Imagens válidas:   {report['valid_images']}")
    print(f" Imagens corrompidas: {report['corrupted_images_count']}")

    if "resolution_stats" in report:
        res = report["resolution_stats"]
        print(f" Resoluções (mín/méd/máx): {res['min_resolution']} / {res['average_resolution']} / {res['max_resolution']}")

    if "yolo_stats" in report:
        ystats = report["yolo_stats"]
        print(f" Total de Bounding Boxes: {ystats['total_bounding_boxes']}")
        print(f" Erros em Anotações YOLO: {ystats['label_errors_count']}")

    print("=" * 60)

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"[+] Relatório completo salvo em: {out_path}")

    if report["has_integrity_errors"]:
        print("\n[!] Atenção: Foram encontradas imagens corrompidas ou inválidas!", file=sys.stderr)
        sys.exit(1)

    print("\n[✓] Dataset validado com sucesso! Nenhuma anomalia crítica encontrada.")
    sys.exit(0)


if __name__ == "__main__":
    main()
