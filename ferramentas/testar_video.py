"""Script utilitário para testar a extração de keyframes e medição em vídeo manualmente.

Exemplos de uso:
    python ferramentas/testar_video.py --demo
    python ferramentas/testar_video.py caminho/do/video.mp4
    python ferramentas/testar_video.py caminho/do/video.mp4 --ponto 320,240
    python ferramentas/testar_video.py --webcam 4
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

# Adiciona a raiz do projeto ao path
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import cv2
import numpy as np

from nucleo.medicao import video_keyframes as vk


def criar_video_demo(caminho: Path, duracao_s: float = 3.0, fps: int = 20) -> Path:
    """Gera um vídeo de demonstração alternando quadros nítidos e borrados."""
    w, h = 640, 480
    padrao = np.full((h, w, 3), 220, dtype=np.uint8)

    # Cria grades e padrões de alto contraste
    for y in range(0, h, 40):
        for x in range(0, w, 40):
            if (x // 40 + y // 40) % 2 == 0:
                padrao[y : y + 40, x : x + 40] = 40

    cv2.rectangle(padrao, (120, 100), (320, 360), (0, 0, 220), -1)
    cv2.putText(padrao, "GABARITO PYRON", (130, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(caminho), fourcc, float(fps), (w, h))

    total = int(duracao_s * fps)
    for i in range(total):
        fase = (i / fps) % 1.0
        if 0.25 <= fase <= 0.75:
            # Simula movimento suave de câmera
            dx = int(25 * math.sin(i * 0.15))
            dy = int(10 * math.cos(i * 0.15))
            M = np.float32([[1, 0, dx], [0, 1, dy]])
            frame = cv2.warpAffine(padrao, M, (w, h))
        else:
            # Simula borrão por movimento rápido
            frame = cv2.GaussianBlur(padrao, (55, 55), 0)

        out.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

    out.release()
    return caminho


def gravar_webcam(caminho: Path, duracao_s: float) -> Path:
    """Grava N segundos da webcam local para teste."""
    print(f"\nAbrindo webcam... gravando {duracao_s:.1f} segundos.")
    print("DICA: Mova a câmera levemente em torno do objeto para gerar ângulos diferentes.")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Não foi possível acessar a webcam.")

    fps = 20.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(caminho), fourcc, fps, (w, h))

    total = int(duracao_s * fps)
    for _ in range(total):
        ret, frame = cap.read()
        if not ret:
            break
        out.write(frame)

    cap.release()
    out.release()
    print(f"Vídeo gravado com sucesso em: {caminho}")
    return caminho


def main():
    parser = argparse.ArgumentParser(description="Teste manual de medição em vídeo com keyframes")
    parser.add_argument("video", nargs="?", help="Caminho do arquivo de vídeo (.mp4, .mov, .avi)")
    parser.add_argument("--demo", action="store_true", help="Gera um vídeo de demonstração sintético automaticamente")
    parser.add_argument("--webcam", type=float, default=0.0, help="Grava N segundos da webcam para teste")
    parser.add_argument("--keyframes", "-k", type=int, default=4, help="Número de keyframes a extrair (padrão 4)")
    parser.add_argument("--salvar", "-s", type=str, default="saida/keyframes", help="Pasta para salvar os keyframes JPG")
    parser.add_argument("--ponto", type=str, help="Pista: coordenadas x,y no primeiro frame (ex: 320,240)")
    parser.add_argument("--caixa", type=str, help="Pista: caixa x0,y0,x1,y1 (ex: 120,100,320,360)")
    parser.add_argument("--postit", action="store_true", help="Detecta post-it rosa como referência métrica")

    args = parser.parse_args()

    pasta_saida = Path(args.salvar)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    caminho_video: Path | None = None

    if args.demo:
        caminho_video = pasta_saida / "video_demo.mp4"
        print(f"Gerando vídeo de teste sintético em: {caminho_video}")
        criar_video_demo(caminho_video)
    elif args.webcam > 0:
        caminho_video = pasta_saida / "webcam_teste.mp4"
        gravar_webcam(caminho_video, args.webcam)
    elif args.video:
        caminho_video = Path(args.video)
        if not caminho_video.exists():
            print(f"Erro: arquivo não encontrado: {caminho_video}")
            sys.exit(1)
    else:
        parser.print_help()
        print("\nPara testar agora sem vídeo prévio, execute:")
        print("  python ferramentas/testar_video.py --demo")
        sys.exit(0)

    print(f"\n[1/3] Analisando vídeo: {caminho_video}")
    keyframes = vk.selecionar_keyframes(caminho_video, max_keyframes=args.keyframes)

    print(f"\n[2/3] {len(keyframes)} keyframes selecionados (descartando borrões de movimento):\n")
    print(f"{'#':<3} | {'Tempo (s)':<10} | {'Índice':<8} | {'Nitidez':<10} | {'Resolução':<12}")
    print("-" * 55)

    for i, kf in enumerate(keyframes, 1):
        arquivo_kf = pasta_saida / f"keyframe_{i:02d}_t{kf.tempo_s:.1f}s.jpg"
        arquivo_kf.write_bytes(kf.bytes_jpeg)
        print(f"{i:<3} | {kf.tempo_s:<10.2f} | {kf.indice:<8} | {kf.nitidez:<10.1f} | {kf.largura}x{kf.altura:<8}")

    print(f"\n-> Imagens salvas em: {pasta_saida.resolve()}")

    pista = None
    if args.ponto:
        pts = [float(x.strip()) for x in args.ponto.split(",")]
        pista = {"ponto": pts[:2]}
    elif args.caixa:
        pts = [float(x.strip()) for x in args.caixa.split(",")]
        pista = {"caixa": pts[:4]}

    if pista:
        ref = {"auto": "postit_rosa"} if args.postit else None
        print(f"\n[3/3] Executando medição 3D multi-frame com pista: {pista}")
        try:
            res = vk.medir_video(caminho_video, pista, referencia=ref, max_keyframes=args.keyframes)
            consenso = res.get("consenso", {})
            print("\n" + "=" * 55)
            print("CONSENSO DAS MEDIÇÕES MULTI-FRAME:")
            print("=" * 55)
            for k, v in consenso.items():
                if isinstance(v, dict) and "valor" in v:
                    nome = k.replace("_cm", "").capitalize()
                    print(f"- {nome}: {v['valor']} cm (± {v['desvio_padrao']} cm) [min: {v['minimo']}, max: {v['maximo']}]")
                    if v.get("reducao_incerteza_pct"):
                        print(f"  (Incerteza reduzida em ~{v['reducao_incerteza_pct']}% comparado a foto única)")
            print("=" * 55)

            if res.get("quadros"):
                for q_idx, q_info in enumerate(res["quadros"], 1):
                    med = q_info.get("medida", {})
                    cotas_q = med.get("cotas", {})
                    if cotas_q and q_idx <= len(keyframes):
                        caminho_cota = pasta_saida / f"keyframe_{q_idx:02d}_cotas.jpg"
                        img_bgr = cv2.imdecode(np.frombuffer(keyframes[q_idx - 1].bytes_jpeg, np.uint8), cv2.IMREAD_COLOR)
                        if "altura" in cotas_q:
                            p1, p2 = cotas_q["altura"]
                            cv2.line(img_bgr, tuple(p1), tuple(p2), (0, 255, 255), 2)
                            cv2.putText(img_bgr, f"Alt: {med.get('altura_cm', '')}cm", ((p1[0] + p2[0]) // 2 + 10, (p1[1] + p2[1]) // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                        if "comprimento" in cotas_q:
                            p1, p2 = cotas_q["comprimento"]
                            cv2.line(img_bgr, tuple(p1), tuple(p2), (0, 220, 0), 2)
                            cv2.putText(img_bgr, f"Comp: {med.get('comprimento_cm', '')}cm", ((p1[0] + p2[0]) // 2 + 10, (p1[1] + p2[1]) // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 0), 2)
                        if "apoio" in cotas_q:
                            p1, p2 = cotas_q["apoio"]
                            cv2.line(img_bgr, tuple(p1), tuple(p2), (0, 165, 255), 2)
                            cv2.putText(img_bgr, "Apoio", (p1[0], p1[1] + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)
                        cv2.imwrite(str(caminho_cota), img_bgr)
                        print(f"-> Imagem com cotas anotadas salva em: {caminho_cota.name}")
        except Exception as e:
            print(f"\nNota: Inferência completa de medição requer pesos dos modelos instalados ({e}).")


if __name__ == "__main__":
    main()
