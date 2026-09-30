"""Assistente de treino no terminal: arraste o .zip do CVAT e acompanhe o treino.

Uso: python -m ml.assistente [arquivo_do_cvat.zip]
(O atalho "Pyron - Treinar modelo" da área de trabalho chama este assistente.)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from ml import dados  # noqa: E402

LINHA = "─" * 64


def perguntar(texto: str, padrao: str) -> str:
    resposta = input(f"{texto} [{padrao}]: ").strip()
    return resposta or padrao


def _slug(texto: str) -> str:
    from app.treinos import slug

    return slug(texto)


def _pytorch() -> tuple[bool, str]:
    """Testa o PyTorch num processo à parte: se o Windows bloquear a DLL, o assistente continua vivo."""
    codigo = "import torch; print(torch.__version__, torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'sem GPU')"
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0:
        return True, r.stdout.strip()
    from app.treinos import explicar_erro

    return False, explicar_erro(r.stderr) or r.stderr.strip().splitlines()[-1]


def main() -> None:
    print(LINHA)
    print(" PYRON · treinar um modelo com os rótulos do CVAT")
    print(LINHA)
    if len(sys.argv) > 1:
        arquivo = Path(sys.argv[1].strip('"'))
    else:
        arquivo = Path(input("Arraste aqui a pasta do dataset (com annotations/) ou o .zip/.json do CVAT e aperte Enter:\n> ").strip().strip('"'))
    if not arquivo.exists():
        sys.exit(f"Arquivo não encontrado: {arquivo}")

    # Uma cópia das anotações fica em dados/rotulos, junto com os outros rótulos do projeto.
    destino = RAIZ / "dados" / "rotulos" / f"{datetime.now():%Y%m%d_%H%M%S}_{arquivo.stem if arquivo.is_dir() else arquivo.name}"
    destino.parent.mkdir(parents=True, exist_ok=True)
    if arquivo.is_dir():
        destino = destino.with_suffix(".zip")
        with zipfile.ZipFile(destino, "w") as z:
            for js in sorted(arquivo.rglob("*.json")):
                z.write(js, f"annotations/{js.name}")
        imagens = arquivo  # as imagens estão na própria pasta do dataset
    else:
        shutil.copy2(arquivo, destino)
        imagens = RAIZ / "dados"

    from ml.treinar import imprimir_analise

    print("\nConferindo os rótulos e as imagens…")
    relatorio = dados.analisar(destino, imagens)
    imprimir_analise(relatorio)
    if not relatorio["pronto"]:
        sys.exit("\nPoucas imagens utilizáveis para treinar (mínimo 8). Confira os avisos acima.")

    ok, info = _pytorch()
    print(f"\nPyTorch: {info}")
    if not ok:
        print("\nSem PyTorch aqui, dá para treinar fora. Vou montar o pacote para o Google Colab ou o supercomputador.")
        if perguntar("Montar o pacote agora? (s/n)", "s").lower().startswith("s"):
            from ml import pacote

            id_ = f"para-raios-{datetime.now():%Y%m%d-%H%M}"
            saida = pacote.montar(destino, imagens, Path.home() / "Downloads", id_, "Para-raios")
            print(f"Pacote: {saida}\nAbra o LEIA-ME.txt dentro dele. Depois, no Pyron: Modelos › Instalar modelo treinado.")
            os.startfile(saida.parent)  # noqa: S606 (abre a pasta Downloads)
        return

    nome = perguntar("\nNome do modelo", "Para-raios")
    id_ = perguntar("Identificador (pasta do modelo)", f"{_slug(nome)}-{datetime.now():%Y%m%d-%H%M}")
    epocas = perguntar("Épocas", "60")
    divisao = "sessao"
    if relatorio["subconjuntos"]:
        escolha = perguntar("Separar treino/teste por sessão (1, recomendado) ou usar a divisão do CVAT (2)?", "1")
        divisao = "cvat" if escolha.strip() == "2" else "sessao"

    print(f"\n{LINHA}\n Treinando {nome} ({id_}). Pode demorar alguns minutos.\n{LINHA}")
    from ml import treinar

    relatorio_treino = treinar.main(["--coco", str(destino), "--imagens", str(imagens), "--id", id_, "--nome", nome,
                                     "--epocas", epocas, "--divisao", divisao])
    m = relatorio_treino.get("metricas_teste", {})
    print(f"\n{LINHA}\n Pronto.")
    print(f"  mAP50 (acerto das caixas no teste): {m.get('mAP50')}")
    print(f"  erro da temperatura máxima: mediana {m.get('erro_tmax_mediano_c')} °C, 90% até {m.get('erro_tmax_p90_c')} °C")
    print(f"  O modelo já aparece no Pyron, em Modelos. Clique em \"Usar este modelo\".\n{LINHA}")
    figura = RAIZ / "modelos" / id_ / "previsoes_teste.png"
    if figura.exists():
        os.startfile(figura)  # noqa: S606 (mostra as previsões no teste)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelado.")
    except SystemExit as saida:
        if saida.code and not isinstance(saida.code, int):
            print(f"\n{saida.code}")
    except Exception as erro:  # mensagem legível no console, em vez de só o traceback
        from app.treinos import explicar_erro

        print(f"\nErro: {explicar_erro(str(erro)) or erro}")
    input("\nAperte Enter para fechar.")
