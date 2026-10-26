"""Onde ficam os pesos da medição, o que está instalado e em que dispositivo roda.

Pesos em ``modelos/medicao/`` (fora do git, como os outros modelos), um diretório por modelo com o nome
do repositório do Hugging Face. ``PYRON_MODELOS_MEDICAO`` troca a pasta.

Baixar (licenças MIT e Apache 2.0, conferidas nos cartões oficiais)::

    python -m nucleo.medicao.modelos --baixar da3 vitl small

Profundidade padrão: o Depth Anything 3 Metric Large quando instalado (nas fotos do Hugo com post-it: erro mediano
5,1 % contra 8,1 % do MoGe-2 ViT-L, e 2 s por foto na CPU contra 20 s); senão o MoGe-2 ViT-L.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

MOGE = {
    "vits": "Ruicheng/moge-2-vits-normal",
    "vitb": "Ruicheng/moge-2-vitb-normal",
    "vitl": "Ruicheng/moge-2-vitl-normal",
}
SAM = {
    "small": "facebook/sam2.1-hiera-small",
    "base-plus": "facebook/sam2.1-hiera-base-plus",
}
MOGE_PADRAO = "vitl"  # no gabarito: erro mediano 19 % (ViT-L), 28 % (ViT-B), 47 % (ViT-S)
SAM_PADRAO = "small"
DA3 = "depth-anything/DA3METRIC-LARGE"


def pasta() -> Path:
    return Path(os.environ.get("PYRON_MODELOS_MEDICAO", RAIZ / "modelos" / "medicao"))


def caminho_moge(variante: str = MOGE_PADRAO) -> Path:
    return pasta() / MOGE[variante].split("/")[1] / "model.pt"


def caminho_sam(variante: str = SAM_PADRAO) -> Path:
    return pasta() / SAM[variante].split("/")[1]


def caminho_da3() -> Path:
    return pasta() / "DA3METRIC-LARGE" / "model.safetensors"


def da3_instalado() -> bool:
    return caminho_da3().exists() and pacote("depth_anything_3") and pacote("safetensors")


def profundidade_padrao():
    """O estimador de profundidade que o Pyron usa: DA3 Metric se instalado, senão o MoGe-2 (``MOGE_PADRAO``)."""
    from nucleo.medicao.profundidade import Profundidade, ProfundidadeDA3

    return ProfundidadeDA3() if da3_instalado() else Profundidade()


MODELOS_PROFUNDIDADE = {
    "da3": "Depth Anything 3 Metric (melhor com referência e em foto de perto; 2 s na CPU)",
    "moge": "MoGe-2 ViT-L (estima a lente; bom em cena ampla sem referência; 20 s na CPU)",
}


def profundidade_por_id(modelo: str):
    """``da3`` ou ``moge``: o estimador de profundidade escolhido na tela."""
    from nucleo.medicao.profundidade import Profundidade, ProfundidadeDA3

    if modelo == "da3":
        return ProfundidadeDA3()
    if modelo == "moge":
        return Profundidade(MOGE_PADRAO)
    raise ValueError(f"modelo de profundidade desconhecido: {modelo} (use da3 ou moge)")


def disponiveis() -> list[dict]:
    instalado = {"da3": da3_instalado(), "moge": pacote("moge") and caminho_moge(MOGE_PADRAO).exists()}
    return [{"id": k, "nome": v, "instalado": instalado[k]} for k, v in MODELOS_PROFUNDIDADE.items()]


def sam_instalado(variante: str = SAM_PADRAO) -> bool:
    p = caminho_sam(variante)
    return (p / "config.json").exists() and any(p.glob("*.safetensors"))


def pacote(nome: str) -> bool:
    return importlib.util.find_spec(nome) is not None


def dispositivo() -> str:
    """``cuda`` se houver placa de vídeo com o PyTorch que a enxerga; senão ``cpu``."""
    if not pacote("torch"):
        return "cpu"
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def estado() -> dict:
    """O que está instalado, para a API e para a tela."""
    pacotes = {nome: pacote(nome) for nome in ("torch", "transformers", "moge")}
    return {
        "pacotes": pacotes,
        "dispositivo": dispositivo() if pacotes["torch"] else None,
        "profundidade": {**{v: caminho_moge(v).exists() for v in MOGE}, "da3": da3_instalado()},
        "contorno": {v: sam_instalado(v) for v in SAM},
        "modelos": disponiveis(),
        "modelo_padrao": "da3" if da3_instalado() else "moge",
        "pasta": str(pasta()),
        "pronto": pacotes["torch"]
        and pacotes["transformers"]
        and (da3_instalado() or (pacotes["moge"] and any(caminho_moge(v).exists() for v in MOGE)))
        and any(sam_instalado(v) for v in SAM),
    }


def baixar(variantes: list[str]) -> list[Path]:
    """Baixa do Hugging Face as variantes pedidas (``vits``, ``vitb``, ``vitl``, ``small``, ``base-plus``)."""
    from huggingface_hub import hf_hub_download, snapshot_download

    feitos = []
    for v in variantes:
        if v == "da3":
            destino = caminho_da3().parent
            snapshot_download(DA3, local_dir=destino, allow_patterns=["*.json", "*.safetensors"])
            feitos.append(destino)
        elif v in MOGE:
            destino = caminho_moge(v).parent
            hf_hub_download(MOGE[v], "model.pt", local_dir=destino)
            feitos.append(destino)
        elif v in SAM:
            destino = caminho_sam(v)
            snapshot_download(SAM[v], local_dir=destino, allow_patterns=["*.json", "*.safetensors", "*.txt"])
            feitos.append(destino)
        else:
            raise ValueError(f"variante desconhecida: {v} (use da3, {', '.join([*MOGE, *SAM])})")
    return feitos


def main() -> None:
    ap = argparse.ArgumentParser(description="Pesos da medição em foto comum")
    ap.add_argument("--baixar", nargs="+", metavar="VARIANTE", help="da3 vits vitb vitl small base-plus")
    args = ap.parse_args()
    if args.baixar:
        for p in baixar(args.baixar):
            print("ok", p)
    import json

    print(json.dumps(estado(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
