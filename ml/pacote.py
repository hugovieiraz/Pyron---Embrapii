"""Pacote para treinar fora deste computador (Google Colab, supercomputador, outro PC com GPU).

Junta num .zip o código de treino, os rótulos do CVAT, as imagens rotuladas (os JPEG originais, com a
temperatura), um caderno pronto para o Colab e as instruções. O resultado do treino é uma pasta
``modelos/<id>`` que volta para o Pyron pela tela Modelos › Instalar modelo.

Uso: python -m ml.pacote --coco dados/rotulos/export.zip [--saida pasta]
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from ml import dados  # noqa: E402

REQUISITOS = """numpy
pillow
scipy
matplotlib
onnx
onnxruntime
# PyTorch e torchvision já vêm no Colab. Em outra máquina, instale a versão com CUDA de pytorch.org.
# Só para imagens sem dados radiométricos (temperatura estimada pelas cores):
# rapidocr-onnxruntime
"""

LEIA_ME = """PYRON · pacote de treino
========================

Conteúdo
  ml/, nucleo/        código de treino do Pyron (o mesmo do aplicativo)
  rotulos/            arquivo exportado do CVAT (COCO 1.0)
  imagens/            os JPEG originais rotulados, com a temperatura da câmera
  treinar_no_colab.ipynb   caderno pronto para o Google Colab (treina o modelo do Pyron)
  Pyron_comparar_modelos.ipynb   compara trivial × MobileNet × DINOv2 com métricas e figuras
  requirements-treino.txt

No Google Colab (GPU grátis)
  1. Abra https://colab.research.google.com e envie o caderno treinar_no_colab.ipynb (Arquivo > Enviar notebook).
  2. Menu Ambiente de execução > Alterar o tipo > GPU (T4).
  3. Rode as células na ordem. Uma delas pede este .zip: envie o arquivo inteiro.
  4. No fim, o navegador baixa modelo_<id>.zip.
  5. No Pyron: Modelos > Instalar modelo treinado > escolha esse .zip.

Em outro computador ou supercomputador
  pip install -r requirements-treino.txt   (e o PyTorch com CUDA)
  python -m ml.treinar --coco rotulos/{rotulos} --imagens imagens --id {id} --nome "{nome}" --epocas {epocas}
  Compacte a pasta modelos/{id} e instale no Pyron (Modelos > Instalar modelo treinado).

  Exemplo de job SLURM:
    #!/bin/bash
    #SBATCH --job-name=pyron
    #SBATCH --gres=gpu:1
    #SBATCH --time=02:00:00
    python -m ml.treinar --coco rotulos/{rotulos} --imagens imagens --id {id} --nome "{nome}" --epocas {epocas}

Licença: as imagens do dataset ScienceDB 10185 são só para estudo (CC BY-NC-SA 4.0).
"""


def _caderno(rotulos: str, id_: str, nome: str, epocas: int, divisao: str) -> dict:
    def celula(tipo, *linhas):
        c = {"cell_type": tipo, "metadata": {}, "source": [l + "\n" for l in linhas]}
        if tipo == "code":
            c.update(execution_count=None, outputs=[])
        return c

    return {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {"accelerator": "GPU", "colab": {"provenance": []}, "kernelspec": {"name": "python3", "display_name": "Python 3"}},
        "cells": [
            celula("markdown", "# Pyron · treinar o detector", "", "Ambiente de execução > Alterar o tipo > **GPU**. Depois rode as células na ordem."),
            celula("code", "import torch", "print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NÃO: ative a GPU no menu')"),
            celula("markdown", "## 1. Envie o pacote gerado pelo Pyron (o .zip inteiro)"),
            celula("code", "from google.colab import files", "enviado = files.upload()", "pacote = next(iter(enviado))",
                   "!unzip -q -o \"$pacote\" -d pyron && echo pronto"),
            celula("code", "%cd pyron", "!pip -q install -r requirements-treino.txt"),
            celula("markdown", "## 2. Confira os rótulos"),
            celula("code", f"!python -m ml.treinar --coco rotulos/{rotulos} --imagens imagens --so-analisar"),
            celula("markdown", "## 3. Treine", "Mude `EPOCAS` se quiser. Com GPU T4, 60 épocas em ~180 imagens levam poucos minutos."),
            celula("code", f"EPOCAS = {epocas}",
                   f"!python -m ml.treinar --coco rotulos/{rotulos} --imagens imagens --id {id_} --nome \"{nome}\" --epocas $EPOCAS --divisao {divisao}"),
            celula("markdown", "## 4. Veja as previsões no teste e baixe o modelo"),
            celula("code", "from IPython.display import Image, display", f"display(Image('modelos/{id_}/previsoes_teste.png'))"),
            celula("code", f"!cd modelos && zip -q -r ../modelo_{id_}.zip {id_}", f"files.download('modelo_{id_}.zip')"),
            celula("markdown", "No Pyron: **Modelos › Instalar modelo treinado** e escolha o `.zip` baixado."),
        ],
    }


def montar(coco: Path, pasta_imagens: Path, destino: Path, id_: str, nome: str, epocas: int = 60, divisao: str = "sessao") -> Path:
    """Cria o .zip do pacote e devolve o caminho."""
    _, imagens = dados._conteudo(coco)
    mapa = dados._mapa_imagens(pasta_imagens)
    rotuladas = [mapa[i["nome"]] for i in imagens if i["rotulos"] and i["nome"] in mapa]
    if not rotuladas:
        raise ValueError("Nenhuma imagem rotulada foi achada para colocar no pacote.")
    destino.mkdir(parents=True, exist_ok=True)
    saida = destino / f"Pyron_pacote_treino_{id_}.zip"
    with zipfile.ZipFile(saida, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for pasta in ("ml", "nucleo"):
            for arq in (RAIZ / pasta).rglob("*.py"):
                z.write(arq, arq.relative_to(RAIZ).as_posix())
        z.write(coco, f"rotulos/{coco.name}")
        for arq in rotuladas:
            z.write(arq, f"imagens/{arq.name}")
        z.writestr("requirements-treino.txt", REQUISITOS)
        z.writestr("LEIA-ME.txt", LEIA_ME.format(rotulos=coco.name, id=id_, nome=nome, epocas=epocas))
        z.writestr("treinar_no_colab.ipynb", json.dumps(_caderno(coco.name, id_, nome, epocas, divisao), ensure_ascii=False, indent=1))
        comparar = RAIZ / "ml" / "notebooks" / "Pyron_comparar_modelos.ipynb"
        if comparar.exists():
            z.write(comparar, comparar.name)
    return saida


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--coco", required=True, type=Path)
    ap.add_argument("--imagens", type=Path, default=RAIZ / "dados")
    ap.add_argument("--id", default=f"para-raios-{datetime.now():%Y%m%d-%H%M}")
    ap.add_argument("--nome", default="Para-raios")
    ap.add_argument("--epocas", type=int, default=60)
    ap.add_argument("--saida", type=Path, default=Path.home() / "Downloads")
    args = ap.parse_args(argv)
    saida = montar(args.coco, args.imagens, args.saida, args.id, args.nome, args.epocas)
    print(f"Pacote de treino: {saida} ({saida.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
