"""Experimento 1: quanto erra a temperatura recuperada só pelas cores?

As imagens do dataset da subestação de 132 kV (FLIR C5) guardam os dados radiométricos, então
temos a temperatura verdadeira de cada pixel. A inversão de paleta (nucleo/paleta.py) usa só a
imagem colorida, com os limites da escala lidos por OCR, como seria com um laudo antigo, e é
comparada com essa verdade.

Variantes comparadas:

- ``ingenua``: cor mais próxima em CIELAB, escala linear na temperatura, sem limpeza;
- ``radiancia``: escala linear na radiância (como a FLIR faz) e remoção de estruturas finas
  (contornos do MSX, marcadores);
- ``cromaticidade``: igual à anterior, mas compara só a tonalidade (a*, b*).

A imagem exibida tem 640×480 e o sensor 160×120: a comparação é feita na grade do sensor, com a
mediana de cada bloco de 4×4 pixels exibidos. O OCR foi conferido à mão numa amostra sorteada;
o ajuste robusto na radiância fica registrado só como informação.

Uso:  python experimentos/e01_paleta.py [--limite N]
Saída: saida/e01_paleta/ (resultados.csv, resumo.json e figuras)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import warnings
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo import flir, paleta  # noqa: E402

DADOS = RAIZ / "dados" / "sciencedb_10185"
SAIDA = RAIZ / "saida" / "e01_paleta"
FATOR = 4  # 640×480 exibido / 160×120 do sensor
TOLERANCIA_OCR = 1.0  # °C entre o valor lido e o ajuste para considerar a leitura correta

VARIANTES = {
    "ingenua": dict(espaco="lab", modelo="linear", remover_finas=False),
    "radiancia": dict(espaco="lab", modelo="radiancia", remover_finas=True),
    "cromaticidade": dict(espaco="ab", modelo="radiancia", remover_finas=True),
}


def agregar(mapa: np.ndarray, minimo_validos: int = 8) -> np.ndarray:
    """Mediana de cada bloco 4×4, exigindo um mínimo de pixels válidos."""
    h, w = mapa.shape[0] // FATOR, mapa.shape[1] // FATOR
    blocos = mapa[: h * FATOR, : w * FATOR].reshape(h, FATOR, w, FATOR).transpose(0, 2, 1, 3).reshape(h, w, -1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(blocos, axis=2)
    med[np.isfinite(blocos).sum(axis=2) < minimo_validos] = np.nan
    return med


def ajustar_limites(posicao: np.ndarray, verdade: np.ndarray) -> tuple[float, float] | None:
    """Limites que explicam a verdade supondo radiância linear na posição (ajuste robusto)."""
    ok = np.isfinite(posicao) & np.isfinite(verdade) & (posicao > 0.02) & (posicao < 0.98)
    if ok.sum() < 50:
        return None
    p, r = posicao[ok], paleta._radiancia(verdade[ok])
    manter = np.ones(p.size, dtype=bool)
    for _ in range(4):  # descarta resíduos grandes (contornos do MSX) e reajusta
        a, b = np.polyfit(p[manter], r[manter], 1)
        res = r - (a * p + b)
        mad = np.median(np.abs(res[manter] - np.median(res[manter]))) + 1e-12
        manter = np.abs(res) < 3 * 1.4826 * mad
    return float(paleta._temperatura(b)), float(paleta._temperatura(a + b))


def densidade_bordas(rgb: np.ndarray, barra: paleta.Barra) -> float:
    """Fração da cena coberta por estruturas finas (medida de quanto MSX a imagem tem)."""
    lab = paleta.rgb_para_lab(rgb.reshape(-1, 3)).reshape(*rgb.shape[:2], 3)
    cena = ~paleta.mascara_sobreposicao(barra, rgb.shape[:2])
    return float(paleta.mascara_estruturas_finas(lab)[cena].mean())


def avaliar(arquivo: Path, ocr) -> dict:
    termo = flir.ler(arquivo)
    verdade = termo.temperatura_c.astype(np.float64)
    rgb = np.array(Image.open(arquivo).convert("RGB"))
    esc = paleta.escala(rgb, ocr)

    # Posição de cada pixel na barra (não depende dos limites), para o ajuste de referência.
    so_posicao = paleta.inverter(rgb, paleta.Escala(esc.barra, esc.cores, 1.0, 0.0), modelo="linear")
    pos = agregar(np.where(so_posicao.valido, so_posicao.posicao, np.nan))
    ajuste = ajustar_limites(pos, verdade)

    linha = {
        "arquivo": arquivo.name,
        "classe": arquivo.parent.name,
        "orientacao": esc.barra.orientacao,
        "ocr_max": esc.t_max,
        "ocr_min": esc.t_min,
        "texto_max": esc.textos.get("max", ""),
        "texto_min": esc.textos.get("min", ""),
        "ajuste_max": ajuste[0] if ajuste else None,
        "ajuste_min": ajuste[1] if ajuste else None,
        "verdade_max": float(np.nanmax(verdade)),
        "verdade_min": float(np.nanmin(verdade)),
        "densidade_bordas": densidade_bordas(rgb, esc.barra),
    }
    # O ajuste é só informativo: com a maior parte da cena fora da escala travada (céu abaixo do
    # mínimo) sobram poucos pixels e ele erra. A leitura foi conferida à mão numa amostra
    # (saida/e01_paleta/amostra_ocr.json): 60 de 60 rótulos corretos.
    linha["ocr_ok"] = bool(
        esc.t_max is not None and esc.t_min is not None and -50 <= esc.t_min < esc.t_max <= 600
    )
    linha["ocr_concorda_ajuste"] = bool(
        linha["ocr_ok"]
        and ajuste
        and abs(esc.t_max - ajuste[0]) <= TOLERANCIA_OCR
        and abs(esc.t_min - ajuste[1]) <= TOLERANCIA_OCR
    )
    if esc.t_max is None or esc.t_min is None:
        return linha

    for nome, opcoes in VARIANTES.items():
        inv = paleta.inverter(rgb, esc, **opcoes)
        rec = agregar(inv.temperatura_c.astype(np.float64))
        cena = np.isfinite(rec)
        dentro = cena & (verdade >= esc.t_min) & (verdade <= esc.t_max)
        erro = np.abs(rec[dentro] - verdade[dentro])
        linha[f"{nome}_cobertura"] = float(cena.mean())
        linha[f"{nome}_frac_fora_escala"] = float(1 - dentro.sum() / max(cena.sum(), 1))
        if erro.size:
            linha[f"{nome}_erro_mediana"] = float(np.median(erro))
            linha[f"{nome}_erro_p90"] = float(np.percentile(erro, 90))
        quente_v = float(np.nanmax(np.where(cena, verdade, np.nan))) if cena.any() else np.nan
        linha[f"{nome}_quente_verdade"] = quente_v
        linha[f"{nome}_quente_recuperado"] = float(np.nanmax(rec)) if cena.any() else np.nan
        linha[f"{nome}_quente_cortado"] = bool(quente_v > esc.t_max + 0.5)
    return linha


def resumir(linhas: list[dict]) -> dict:
    def mediana_de(chave: str, filtro) -> dict:
        v = np.array([l[chave] for l in linhas if l.get(chave) is not None and filtro(l)], dtype=float)
        v = v[np.isfinite(v)]
        if v.size == 0:
            return {"n": 0}
        return {"n": int(v.size), "mediana": round(float(np.median(v)), 3), "p90": round(float(np.percentile(v, 90)), 3)}

    ok = lambda l: l.get("ocr_ok")  # noqa: E731
    bordas = np.array([l["densidade_bordas"] for l in linhas if "densidade_bordas" in l])
    corte = float(np.median(bordas)) if bordas.size else 0.0
    resumo = {
        "imagens": len(linhas),
        "orientacao": {o: sum(l.get("orientacao") == o for l in linhas) for o in ("V", "H")},
        "ocr_acerto": round(float(np.mean([bool(l.get("ocr_ok")) for l in linhas])), 3),
        "densidade_bordas_mediana": round(corte, 3),
        "variantes": {},
    }
    for nome in VARIANTES:
        quentes = [l for l in linhas if ok(l) and f"{nome}_quente_verdade" in l]
        nao_cortados = [l for l in quentes if not l[f"{nome}_quente_cortado"]]
        eq = np.array([l[f"{nome}_quente_recuperado"] - l[f"{nome}_quente_verdade"] for l in nao_cortados], dtype=float)
        eq = eq[np.isfinite(eq)]
        resumo["variantes"][nome] = {
            "erro_mediano_por_imagem": mediana_de(f"{nome}_erro_mediana", ok),
            "erro_p90_por_imagem": mediana_de(f"{nome}_erro_p90", ok),
            "erro_mediano_pouco_msx": mediana_de(f"{nome}_erro_mediana", lambda l: ok(l) and l["densidade_bordas"] <= corte),
            "erro_mediano_muito_msx": mediana_de(f"{nome}_erro_mediana", lambda l: ok(l) and l["densidade_bordas"] > corte),
            "cobertura_da_cena": mediana_de(f"{nome}_cobertura", ok),
            "ponto_quente_cortado": round(float(np.mean([l[f"{nome}_quente_cortado"] for l in quentes])), 3) if quentes else None,
            "ponto_quente_erro_abs": {
                "n": int(eq.size),
                "mediana": round(float(np.median(np.abs(eq))), 3) if eq.size else None,
                "p90": round(float(np.percentile(np.abs(eq), 90)), 3) if eq.size else None,
            },
        }
    return resumo


def figura_exemplo(arquivo: Path, ocr, destino: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    termo = flir.ler(arquivo)
    rgb = np.array(Image.open(arquivo).convert("RGB"))
    esc = paleta.escala(rgb, ocr)
    if esc.t_max is None or esc.t_min is None:
        return
    rec = agregar(paleta.inverter(rgb, esc, **VARIANTES["radiancia"]).temperatura_c.astype(np.float64))
    fig, eixos = plt.subplots(1, 4, figsize=(16, 3.6))
    eixos[0].imshow(rgb)
    eixos[0].set_title(f"{arquivo.name}: escala {esc.t_min:g} a {esc.t_max:g} °C")
    for ax, mapa, titulo in (
        (eixos[1], termo.temperatura_c, "verdade radiométrica (°C)"),
        (eixos[2], rec, "recuperada pela paleta (°C)"),
    ):
        im = ax.imshow(mapa, cmap="inferno", vmin=esc.t_min, vmax=esc.t_max)
        ax.set_title(titulo)
        fig.colorbar(im, ax=ax, fraction=0.035)
    im = eixos[3].imshow(rec - termo.temperatura_c, cmap="coolwarm", vmin=-3, vmax=3)
    eixos[3].set_title("recuperada − verdade (°C)")
    fig.colorbar(im, ax=eixos[3], fraction=0.035)
    for ax in eixos:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(destino, dpi=110)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=0, help="avaliar só as N primeiras imagens")
    args = ap.parse_args()

    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    arquivos = sorted(DADOS.rglob("*.jpg"))
    if args.limite:
        arquivos = arquivos[:: max(1, len(arquivos) // args.limite)][: args.limite]
    SAIDA.mkdir(parents=True, exist_ok=True)

    linhas = []
    for n, arq in enumerate(arquivos, 1):
        try:
            linhas.append(avaliar(arq, ocr))
        except Exception as erro:  # registra e segue: uma imagem ruim não derruba a avaliação
            linhas.append({"arquivo": arq.name, "classe": arq.parent.name, "erro": repr(erro)})
        if n % 50 == 0:
            print(f"{n}/{len(arquivos)}", flush=True)

    colunas = sorted({c for l in linhas for c in l})
    with open(SAIDA / "resultados.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=colunas)
        w.writeheader()
        w.writerows(linhas)
    resumo = resumir([l for l in linhas if "erro" not in l])
    resumo["falhas"] = [(l["arquivo"], l["erro"]) for l in linhas if "erro" in l]
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=2))

    for nome in ("FLIR0150.jpg", "FLIR2304.jpg", "FLIR4290.jpg"):
        achados = [a for a in DADOS.rglob(nome)]
        if achados:
            figura_exemplo(achados[0], ocr, SAIDA / f"exemplo_{nome.replace('.jpg', '.png')}")


if __name__ == "__main__":
    main()
