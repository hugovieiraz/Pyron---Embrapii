"""Inventário do dataset da subestação de 132 kV: o que cada imagem traz.

Para cada JPEG: classe, data e hora da captura, se tem dados radiométricos, parâmetros de
medição gravados pela câmera, faixa de temperatura da cena e orientação da barra.

Uso:  python experimentos/e00_inventario.py
Saída: saida/e00_inventario/ (inventario.csv e resumo.json)
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo import flir, paleta  # noqa: E402

DADOS = RAIZ / "dados" / "sciencedb_10185"
SAIDA = RAIZ / "saida" / "e00_inventario"


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = []
    for arq in sorted(DADOS.rglob("*.jpg")):
        img = Image.open(arq)
        exif = img.getexif()
        linha = {
            "arquivo": arq.name,
            "classe": arq.parent.name,
            "data_hora": str(exif.get(306, "")),  # DateTime
            "modelo": str(exif.get(272, "")),
            "largura": img.width,
            "altura": img.height,
        }
        try:
            t = flir.ler(arq)
            p = t.parametros
            linha.update(
                radiometrica=True,
                emissividade=round(p.emissividade, 3),
                distancia_m=round(p.distancia_m, 2),
                temp_refletida_c=round(p.temp_refletida_c, 1),
                umidade=round(p.umidade_relativa, 2),
                sensor=f"{t.bruto.shape[1]}x{t.bruto.shape[0]}",
                t_min=round(float(np.nanmin(t.temperatura_c)), 2),
                t_p50=round(float(np.nanmedian(t.temperatura_c)), 2),
                t_max=round(float(np.nanmax(t.temperatura_c)), 2),
            )
        except ValueError as erro:
            linha.update(radiometrica=False, erro=str(erro))
        try:
            linha["orientacao"] = paleta.localizar_barra(np.array(img.convert("RGB"))).orientacao
            linha["jpeg_ok"] = True
        except ValueError:
            linha["orientacao"], linha["jpeg_ok"] = "?", True
        except OSError:  # JPEG corrompido já na origem (o MD5 confere com o servidor)
            linha["orientacao"], linha["jpeg_ok"] = "?", False
        linhas.append(linha)

    colunas = sorted({c for l in linhas for c in l})
    with open(SAIDA / "inventario.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=colunas)
        w.writeheader()
        w.writerows(linhas)

    datas = sorted(l["data_hora"] for l in linhas if l["data_hora"])
    dias = Counter(d[:10] for d in datas)
    resumo = {
        "imagens": len(linhas),
        "por_classe": dict(Counter(l["classe"] for l in linhas)),
        "radiometricas": sum(bool(l.get("radiometrica")) for l in linhas),
        "jpeg_corrompido": [l["arquivo"] for l in linhas if not l["jpeg_ok"]],
        "modelos": dict(Counter(l["modelo"] for l in linhas)),
        "sensor": dict(Counter(l.get("sensor") for l in linhas)),
        "orientacao": dict(Counter(l["orientacao"] for l in linhas)),
        "emissividade": dict(Counter(l.get("emissividade") for l in linhas)),
        "distancia_m": dict(Counter(l.get("distancia_m") for l in linhas)),
        "primeira": datas[0] if datas else None,
        "ultima": datas[-1] if datas else None,
        "dias_de_captura": dict(sorted(dias.items())),
        "trafos_por_dia": dict(sorted(Counter(l["data_hora"][:10] for l in linhas if l["classe"] == "Power Transformers").items())),
    }
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
