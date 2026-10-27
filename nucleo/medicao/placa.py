"""A placa de vídeo na medição: diagnóstico e troca segura do PyTorch para a versão com CUDA.

Com o Pyron fechado (o Windows não deixa trocar arquivos em uso)::

    python -m nucleo.medicao.placa              # diz se a placa é usada e, se não, por quê
    python -m nucleo.medicao.placa --instalar   # PyTorch com CUDA, testado antes de trocar

A troca é em dois passos: o PyTorch com CUDA vai primeiro para uma pasta de teste e um Python à parte confere se a
placa responde (uma conta nela). Só se der certo o do Pyron é trocado, pela mesma versão (o download fica no cache
do pip). Se o Windows barrar a DLL (Controle Inteligente de Aplicativos) ou o driver não servir, nada muda e a
medição segue no processador.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

from nucleo.medicao import modelos

INDICE_CUDA = "https://download.pytorch.org/whl/cu126"  # CUDA 12.6: drivers NVIDIA 528 em diante, RTX 20xx a 50xx
MOTIVOS = {
    "ok": "A placa de vídeo é usada na medição.",
    "sem_torch": "O PyTorch não está instalado.",
    "torch_cpu": "O PyTorch instalado é a versão só para processador. Rode: python -m nucleo.medicao.placa --instalar",
    "driver": "O PyTorch tem CUDA, mas não achou a placa: atualize o driver da NVIDIA (GeForce Experience ou nvidia.com).",
    "bloqueado": "O Windows (Controle Inteligente de Aplicativos) barrou uma DLL do PyTorch com CUDA.",
    "falhou": "A placa foi achada, mas não respondeu a uma conta de teste.",
}
TESTE = ("import json, torch\n"
         "r = {'torch': torch.__version__, 'cuda': torch.version.cuda, 'ok': False}\n"
         "try:\n"
         "    r['ok'] = torch.cuda.is_available() and (torch.ones(8, device='cuda') * 2).sum().item() == 16\n"
         "    r['nome'] = torch.cuda.get_device_name(0) if r['ok'] else None\n"
         "except Exception as e:\n"
         "    r['erro'] = str(e)[:300]\n"
         "print(json.dumps(r))\n")


def driver_nvidia() -> str | None:
    """Placa e driver pelo ``nvidia-smi`` (vem com o driver), sem depender do PyTorch."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _pip(*argumentos: str) -> None:
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *argumentos])
    if r.returncode != 0:
        raise RuntimeError("o pip não conseguiu instalar (veja as linhas acima)")


def _testar(pasta: Path | None = None) -> dict:
    """Roda o teste num Python à parte (com ``pasta`` na frente do caminho de importação, se houver)."""
    env = None
    if pasta is not None:
        import os

        env = {**os.environ, "PYTHONPATH": str(pasta)}
    r = subprocess.run([sys.executable, "-c", TESTE], capture_output=True, text=True, env=env, timeout=600)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"ok": False, "erro": (r.stderr or r.stdout).strip()[-400:]}


def instalar_cuda() -> bool:
    """PyTorch com CUDA, testado numa pasta à parte antes de trocar o do Pyron. Devolve se a placa ficou em uso."""
    try:
        versao = importlib.metadata.version("torch").split("+")[0]
    except importlib.metadata.PackageNotFoundError:
        versao = None
    pedido = [f"torch=={versao}" if versao else "torch", "torchvision"]
    teste = modelos.pasta() / "torch_cuda_teste"
    shutil.rmtree(teste, ignore_errors=True)
    print(f"1/3 baixando o PyTorch com CUDA para uma pasta de teste ({teste}); uns 2,5 GB…")
    try:
        _pip("--no-deps", "--target", str(teste), "--index-url", INDICE_CUDA, *pedido)
    except RuntimeError:
        if not versao:
            raise
        print(f"   a versão {versao} não existe com CUDA; tentando a mais nova")
        pedido = ["torch", "torchvision"]
        _pip("--no-deps", "--target", str(teste), "--index-url", INDICE_CUDA, *pedido)
    print("2/3 testando a placa com essa versão…")
    r = _testar(teste)
    if not r.get("ok"):
        shutil.rmtree(teste, ignore_errors=True)
        print("A placa não respondeu; o PyTorch do Pyron não foi trocado (a medição segue no processador).")
        print("   motivo:", r.get("erro") or "o PyTorch não achou a placa (driver da NVIDIA?)")
        if "4551" in str(r.get("erro")) or "Application Control" in str(r.get("erro")):
            print("   o Windows (Controle Inteligente de Aplicativos) barrou a DLL do CUDA.")
        return False
    instalados = [p.name.split("-")[:2] for p in teste.glob("*.dist-info")]
    fixos = [f"{nome}=={ver}" for nome, ver in instalados if nome in ("torch", "torchvision")]
    shutil.rmtree(teste, ignore_errors=True)
    print(f"   placa ok: {r.get('nome')}. 3/3 trocando o PyTorch do Pyron ({', '.join(fixos)}), do cache do pip…")
    _pip("--force-reinstall", "--no-deps", "--index-url", INDICE_CUDA, *fixos)
    final = _testar()
    print("Pronto: a medição vai usar", final.get("nome") if final.get("ok") else "o processador (algo mudou; rode de novo)")
    return bool(final.get("ok"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Placa de vídeo na medição em foto")
    ap.add_argument("--instalar", action="store_true", help="troca o PyTorch pela versão com CUDA, testada antes")
    args = ap.parse_args()
    if args.instalar:
        instalar_cuda()
        return
    info = _testar()
    info["motivo"] = "ok" if info.get("ok") else ("torch_cpu" if info.get("torch") and not info.get("cuda") else
                                                  "bloqueado" if "erro" in info else "driver")
    print(json.dumps(info, ensure_ascii=False))
    print("driver NVIDIA:", driver_nvidia() or "nvidia-smi não encontrado")
    print(MOTIVOS[info["motivo"]])


if __name__ == "__main__":
    main()
