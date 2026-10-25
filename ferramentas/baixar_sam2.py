"""Baixa e confere o checkpoint do SAM 2 (codificador Hiera) usado em ``nucleo/segmentacao``.

Uso:
    python ferramentas/baixar_sam2.py                          # sam2.1_hiera_small (padrão)
    python ferramentas/baixar_sam2.py --variante sam2.1_hiera_base_plus
    python ferramentas/baixar_sam2.py --so-validar             # confere o que já está baixado

Os pesos vão para ``modelos/sam2/`` (fora do git, como os outros modelos). A Meta não publica hash
dos checkpoints, então a conferência é em camadas:

1. tamanho mínimo (pega download truncado);
2. ``torch.load(weights_only=True)``: abre sem executar código e precisa ter a chave ``model``
   com os pesos do codificador Hiera;
3. ``build_sam2`` com carga estrita do state_dict (nenhuma chave faltando ou sobrando) e uma
   inferência de fumaça numa imagem sintética;
4. grava o SHA-256 ao lado (``.sha256``) para detectar troca ou corrupção depois.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.segmentacao.sam2_engine import PASTA_PESOS, VARIANTE_PADRAO, VARIANTES, VarianteSAM2  # noqa: E402

MB = 2**20
BLOCO = 1 << 20
TENTATIVAS = 4
CHAVE_HIERA = "image_encoder.trunk.patch_embed.proj.weight"


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(BLOCO), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar(variante: VarianteSAM2, destino: Path) -> Path:
    """Baixa para um ``.parcial`` e só renomeia no fim: nunca deixa um checkpoint pela metade."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            with urllib.request.urlopen(variante.url, timeout=60) as r, parcial.open("wb") as f:
                total = int(r.headers.get("Content-Length", 0))
                feito, ultimo = 0, 0.0
                while bloco := r.read(BLOCO):
                    f.write(bloco)
                    feito += len(bloco)
                    if time.monotonic() - ultimo > 2:
                        ultimo = time.monotonic()
                        pct = f" ({100 * feito / total:.0f}%)" if total else ""
                        print(f"  {feito / MB:.0f} MB{pct}", flush=True)
            if total and parcial.stat().st_size != total:
                raise OSError(f"tamanho {parcial.stat().st_size} diferente do anunciado {total}")
            parcial.replace(destino)
            return destino
        except OSError as erro:
            print(f"tentativa {tentativa}/{TENTATIVAS} falhou: {erro}")
            time.sleep(2 * tentativa)
    raise SystemExit(f"não foi possível baixar {variante.url}")


def validar(variante: VarianteSAM2, caminho: Path, inferir: bool = True) -> None:
    import numpy as np
    import torch

    tamanho_mb = caminho.stat().st_size / MB
    if tamanho_mb < variante.tamanho_min_mb:
        raise SystemExit(f"{caminho.name}: {tamanho_mb:.0f} MB, abaixo de {variante.tamanho_min_mb} MB (truncado?)")
    pesos = torch.load(caminho, map_location="cpu", weights_only=True)
    if "model" not in pesos or CHAVE_HIERA not in pesos["model"]:
        raise SystemExit(f"{caminho.name}: não parece um checkpoint SAM 2 (falta '{CHAVE_HIERA}')")
    parametros = sum(t.numel() for t in pesos["model"].values())
    print(f"ok: {tamanho_mb:.0f} MB, {len(pesos['model'])} tensores, {parametros / 1e6:.1f} M parâmetros")
    del pesos
    if not inferir:
        return

    from nucleo.segmentacao.sam2_engine import SAM2Segmentor

    segmentador = SAM2Segmentor(checkpoint=caminho, variante=variante.nome)
    imagem = np.zeros((256, 256, 3), dtype=np.uint8)
    imagem[80:176, 64:192] = 220
    segmentador.set_frame(imagem)
    mascara = segmentador.predict_mask_from_bbox([56, 72, 200, 184])
    verdade = imagem[..., 0] > 0
    iou = (mascara.astype(bool) & verdade).sum() / max(1, (mascara.astype(bool) | verdade).sum())
    print(f"ok: build_sam2 estrito e inferência de fumaça em {segmentador.dispositivo} (IoU {iou:.3f})")
    if iou < 0.8:
        raise SystemExit("inferência de fumaça com IoU baixo: checkpoint e configuração não combinam?")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--variante", default=VARIANTE_PADRAO, choices=sorted(VARIANTES))
    p.add_argument("--pasta", type=Path, default=PASTA_PESOS)
    p.add_argument("--so-validar", action="store_true", help="não baixa; só confere o arquivo existente")
    p.add_argument("--sem-inferencia", action="store_true", help="pula build_sam2 e a inferência de fumaça")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    variante = VARIANTES[a.variante]
    destino = a.pasta / variante.arquivo
    if not destino.exists():
        if a.so_validar:
            raise SystemExit(f"{destino} não existe")
        print(f"baixando {variante.url}")
        baixar(variante, destino)
    validar(variante, destino, inferir=not a.sem_inferencia)
    hash_ = sha256(destino)
    arquivo_hash = destino.with_suffix(".sha256")
    if arquivo_hash.exists() and arquivo_hash.read_text().split()[0] != hash_:
        raise SystemExit(f"SHA-256 mudou desde a última validação: {destino}")
    arquivo_hash.write_text(f"{hash_}  {destino.name}\n")
    print(f"sha256 {hash_}\npronto: {destino}")


if __name__ == "__main__":
    main()
