"""Instala os modelos da medição neste computador: os pacotes que faltam (pelo pip do próprio Python do Pyron) e
os pesos (``modelos.baixar``). Usado pelo botão "Instalar" de Modelos › Medição e pelo terminal::

    python -m nucleo.medicao.instalar            # DA3, MoGe-2 e SAM
    python -m nucleo.medicao.instalar da3 sam

O código do DA3, do MoGe e do utils3d vem do GitHub oficial como .zip, preso ao mesmo commit testado (não precisa
do git instalado) e sem dependências: o DA3 inteiro puxaria o ``evo`` (GPL), o open3d e o xformers, e o MoGe o
FlexGEMM e o Gradio do MoGe-3; a rede de cada um usa só o que está em ``PACOTES``. Só instala o que falta: o
``torch`` que já existe (com CUDA, no computador com placa) nunca é trocado.
"""

from __future__ import annotations

import importlib
import subprocess
import sys

from nucleo.medicao import modelos

# repositório e commit testado; instala pelo .zip e, se falhar, pelo git (quando houver)
SEM_DEPENDENCIAS = {
    "depth_anything_3": ("ByteDance-Seed/Depth-Anything-3", "3d835ec1a5802d64a8b8b15f817a1ab54809bfe4"),
    "utils3d_moge": ("EasternJournalist/utils3d-moge", "62f09d58509485564e24d5d9f6aac9ee9ebc0c37"),
    "moge": ("microsoft/MoGe", "74fbce054ebed49800de42d0ad0e83495065719a"),
}


def fontes(mod: str) -> list[str]:
    repo, commit = SEM_DEPENDENCIAS[mod]
    return [f"https://github.com/{repo}/archive/{commit}.zip", f"git+https://github.com/{repo}.git@{commit}"]


COMUNS = [("torch", "torch"), ("torchvision", "torchvision"), ("transformers", "transformers>=4.56"),
          ("huggingface_hub", "huggingface_hub"), ("safetensors", "safetensors"), ("cv2", "opencv-python-headless"),
          ("pillow_heif", "pillow-heif")]
# (módulo importado, o que pedir ao pip) de cada modelo, na ordem de instalar
PACOTES = {
    "da3": COMUNS + [("einops", "einops"), ("omegaconf", "omegaconf"), ("addict", "addict"), ("depth_anything_3", None)],
    "moge": COMUNS + [("scipy", "scipy"), ("tqdm", "tqdm"), ("utils3d_moge", None), ("moge", None)],
    "sam": COMUNS,
}


def faltando(modelo: str) -> list[str]:
    importlib.invalidate_caches()
    return [mod for mod, _ in PACOTES[modelo] if not modelos.pacote(mod)]


def _pip(argumentos: list[str], aviso) -> None:
    comando = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", *argumentos]
    aviso("pip install " + " ".join(argumentos))
    r = subprocess.run(comando, capture_output=True, text=True)
    if r.returncode != 0:
        fim = (r.stderr or r.stdout).strip().splitlines()[-8:]
        raise RuntimeError("O pip não conseguiu instalar:\n" + "\n".join(fim))


def instalar(modelo: str, aviso=print) -> None:
    """Pacotes que faltam e depois os pesos de ``modelo`` (``da3``, ``moge`` ou ``sam``)."""
    if modelo not in PACOTES:
        raise ValueError(f"modelo desconhecido: {modelo} (use {', '.join(PACOTES)})")
    falta = faltando(modelo)
    comuns = [pip for mod, pip in PACOTES[modelo] if mod in falta and pip]
    if comuns:
        aviso("instalando os pacotes")
        _pip(comuns, aviso)
    for mod in [m for m in falta if m in SEM_DEPENDENCIAS]:
        aviso(f"instalando {mod}")
        for i, fonte in enumerate(fontes(mod)):
            try:
                _pip(["--no-deps", "--ignore-requires-python", fonte], aviso)
                break
            except RuntimeError:
                if i == len(fontes(mod)) - 1:
                    raise
    resta = faltando(modelo)
    if resta:
        raise RuntimeError(f"Ainda faltam os pacotes: {', '.join(resta)}")
    if not next(c for c in modelos.catalogo() if c["id"] == modelo)["pesos"]:
        aviso("baixando os pesos")
        modelos.baixar([modelos.VARIANTE_DO_MODELO[modelo]])
    aviso("pronto")


def main() -> None:
    pedidos = sys.argv[1:] or list(PACOTES)
    for m in pedidos:
        print(f"== {m}")
        instalar(m)
    print("Tudo instalado. Abra o Pyron em Modelos › Medição.")


if __name__ == "__main__":
    main()
