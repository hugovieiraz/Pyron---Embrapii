"""Monta um vídeo de demonstração a partir de termogramas, imitando a tela da câmera ao vivo.

Cada foto vira alguns segundos de vídeo com um movimento lento de câmera (aproximação e
deslocamento) só na cena; a barra de escala, os números e o logotipo ficam parados, como na tela
da FLIR. As fotos entram em cortes secos (a câmera apontando para o próximo equipamento): uma fusão
misturaria duas escalas diferentes e cores que não existem na paleta.

Só entram fotos com a câmera deitada (barra vertical à esquerda), o sentido em que a imagem gravada
já é o sentido de exibição.

    .venv\\Scripts\\python.exe -m ml.video_demo --fotos dados/para_raios_dataset_v2/test --saida dados/video_demo.mp4
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from nucleo import paleta


def _cena_em_movimento(rgb: np.ndarray, mascara: np.ndarray, t: float, sentido: int):
    import cv2

    h, w = rgb.shape[:2]
    zoom = 1.0 + 0.07 * t
    dx, dy = sentido * 14 * (t - 0.5), 6 * np.sin(np.pi * t)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), 0, zoom)
    m[:, 2] += (dx, dy)
    movida = cv2.warpAffine(rgb, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return np.where(mascara[..., None], rgb, movida)


def montar(fotos: list[Path], saida: Path, fps: int = 10, segundos: float = 2.5, maximo: int = 24) -> int:
    import cv2

    usadas = 0
    escritor = None
    for foto in fotos:
        rgb = np.array(Image.open(foto).convert("RGB"))
        if rgb.shape[:2] != (480, 640):
            continue
        try:
            barra = paleta.localizar_barra(rgb)
        except ValueError:
            continue
        if barra.orientacao != "V":
            continue
        if escritor is None:
            saida.parent.mkdir(parents=True, exist_ok=True)
            escritor = cv2.VideoWriter(str(saida), cv2.VideoWriter_fourcc(*"mp4v"), fps, (640, 480))
        mascara = paleta.mascara_sobreposicao(barra, rgb.shape[:2])
        n = max(2, round(fps * segundos))
        for i in range(n):
            quadro = _cena_em_movimento(rgb, mascara, i / (n - 1), 1 if usadas % 2 else -1)
            escritor.write(cv2.cvtColor(quadro, cv2.COLOR_RGB2BGR))
        usadas += 1
        if usadas >= maximo:
            break
    if escritor is not None:
        escritor.release()
    return usadas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fotos", nargs="+", required=True, help="pastas com os termogramas (JPEG)")
    ap.add_argument("--saida", default="dados/video_demo.mp4")
    ap.add_argument("--fps", type=int, default=10)
    ap.add_argument("--segundos", type=float, default=2.5, help="tempo de cada foto no vídeo")
    ap.add_argument("--maximo", type=int, default=24, help="número máximo de fotos")
    a = ap.parse_args()
    fotos = sorted(p for pasta in a.fotos for p in Path(pasta).glob("*.jpg"))
    n = montar(fotos, Path(a.saida), a.fps, a.segundos, a.maximo)
    if not n:
        raise SystemExit("Nenhuma foto com a barra de escala vertical (câmera deitada) nas pastas indicadas.")
    print(f"{a.saida}: {n} fotos, {n * a.segundos:.0f} s a {a.fps} quadros por segundo.")


if __name__ == "__main__":
    main()
