"""Monta o Pyron Apresentação portátil: uma pasta (e um .zip) que roda em outro Windows sem instalar nada.

Uso, na pasta do projeto: ``.venv\\Scripts\\python.exe -m apresentacao.empacotar [--destino PASTA] [--sem-zip]``

Vai junto: o Python 3.11 desta máquina (python.exe assinado pela Python Software Foundation, sem as bibliotecas
dele), só as bibliotecas que o aplicativo usa (e as dependências declaradas de cada uma), as DLLs do Visual C++
(o ONNX Runtime precisa delas e nem todo Windows tem), o código da apresentação, a pasta de modelos e as 27
imagens de teste do ScienceDB 10185 (CC BY-NC-SA 4.0, com o crédito). O atalho é um .bat que chama o pythonw.exe
do pacote; a janela continua sendo o Edge em modo aplicativo.
"""

from __future__ import annotations

import argparse
import ctypes
import importlib.metadata as md
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement

RAIZ = Path(__file__).resolve().parents[1]
NOME = "Pyron Apresentação"
# o que o aplicativo importa de fora da biblioteca padrão (levantado com ele rodando: análise, avaliação, celular)
IMPORTA = ["fastapi", "uvicorn", "starlette", "pydantic", "anyio", "numpy", "PIL", "cv2", "onnxruntime", "multipart",
           "python_multipart", "httptools", "websockets", "watchfiles", "click", "colorama", "rich", "pygments", "h11",
           "idna", "defusedxml", "typing_extensions", "typing_inspection", "annotated_types", "annotated_doc"]
# o ONNX Runtime declara o sympy (ferramentas de otimização), mas a inferência não usa: ~70 MB a menos
NAO_VAO = {"sympy", "mpmath"}
FORA_DA_LIB = {"site-packages", "test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "__pycache__"}
FORA_DAS_DLLS = {"_tkinter.pyd", "tcl86t.dll", "tk86t.dll"}
VISUAL_C = ["msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll",
            "concrt140.dll"]
FORA_DA_APRESENTACAO = {".janela", ".celular", "__pycache__", "registro.log"}

BAT = r"""@echo off
rem Pyron Apresentacao: abre o aplicativo (nao precisa instalar nada). A janela abre sozinha em alguns segundos.
set "AQUI=%~dp0"
set "PYRON_APRESENTACAO_MODELO=%AQUI%modelos\{modelo}"
set "PYRON_ACERVO=%AQUI%imagens de teste"
cd /d "%AQUI%sistema\pyron"
start "" "%AQUI%sistema\python\pythonw.exe" -E -s -m apresentacao
"""

LEIA_ME = """Pyron Apresentação — identificação de para-raios por termografia
=================================================================

COMO ABRIR
1. Se veio pelo Google Drive em .zip: antes de extrair, clique com o botão direito no .zip ›
   Propriedades › marque "Desbloquear" › OK. (Sem isso o Windows pode barrar os arquivos extraídos.)
2. Extraia o .zip numa pasta qualquer (Documentos, por exemplo).
3. Dois cliques em "Abrir Pyron Apresentação.bat". A janela abre sozinha em alguns segundos
   (o Microsoft Edge em modo aplicativo). Não precisa instalar Python nem nada.
   Se o Windows mostrar "O Windows protegeu o computador", clique em "Mais informações" › "Executar assim mesmo".

O QUE TEM AQUI
- Abrir Pyron Apresentação.bat   o atalho do aplicativo
- modelos\\                       os modelos treinados
    {modelo}\\  RF-DETR Medium (o usado pelo aplicativo):
        modelo.onnx    o modelo exportado em ONNX (roda na placa de vídeo pelo DirectML, ou no processador)
        pesos.pth      os pesos do PyTorch (checkpoint do treino)
        cartao.json    classes, entrada e limiar de confiança
        relatorio.json métricas e histórico do treino
    {modelo}-int8\\  versão quantizada (INT8), mais leve, para processador
- imagens de teste\\              as 27 imagens do conjunto de teste (fora do treino)
- sistema\\                       o Python e o código do aplicativo (não precisa mexer)

ABAS
- Análise: escolha uma imagem de teste ou envie um JPEG radiométrico da FLIR. O modelo detecta o
  para-raio, as saias e os terminais e marca o ponto mais quente de cada para-raio.
- Avaliação do modelo: pipeline, conjunto de dados, os três modelos treinados e o desempenho no teste.
- Câmera do celular: identificação em tempo real pela câmera do celular (mesma rede Wi-Fi).

REQUISITOS
Windows 10 ou 11 (64 bits) com o Microsoft Edge. Com placa de vídeo compatível com DirectX 12, a detecção
leva ~70 ms por imagem; sem ela, roda no processador (~0,4 s).

IMAGENS
Infrared Power Equipment Dataset (ScienceDB 10185, doi 10.57760/sciencedb.10185), licença CC BY-NC-SA 4.0,
uso não comercial.
"""


def area_de_trabalho() -> Path:
    """A Área de Trabalho do usuário (pode estar dentro do OneDrive)."""
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)  # CSIDL_DESKTOPDIRECTORY
    return Path(buf.value)


def distribuicoes() -> list[md.Distribution]:
    """As distribuições que fornecem os módulos de IMPORTA, mais as dependências declaradas (recursivo)."""
    por_modulo = md.packages_distributions()
    ambiente = default_environment()
    fila = [d for m in IMPORTA for d in por_modulo.get(m, [])]
    vistas: dict[str, md.Distribution] = {}
    while fila:
        nome = fila.pop()
        chave = re.sub(r"[-_.]+", "-", nome).lower()
        if chave in vistas or chave in NAO_VAO:
            continue
        try:
            dist = md.distribution(nome)
        except md.PackageNotFoundError:
            continue
        vistas[chave] = dist
        for req in dist.requires or []:
            r = Requirement(req)
            if r.marker is None or r.marker.evaluate({**ambiente, "extra": ""}):
                fila.append(r.name)
    return list(vistas.values())


def copiar_python(destino: Path) -> None:
    base = Path(sys.base_prefix)
    destino.mkdir(parents=True)
    for nome in ["python.exe", "pythonw.exe", "python3.dll", "python311.dll", "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"]:
        shutil.copy2(base / nome, destino / nome)
    shutil.copytree(base / "DLLs", destino / "DLLs", ignore=lambda _d, nomes: [n for n in nomes if n in FORA_DAS_DLLS])
    shutil.copytree(base / "Lib", destino / "Lib", ignore=lambda _d, nomes: [n for n in nomes if n in FORA_DA_LIB])
    sistema = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    for nome in VISUAL_C:  # redistribuíveis da Microsoft, junto do python.exe (o Windows procura ali primeiro)
        if (sistema / nome).exists():
            shutil.copy2(sistema / nome, destino / nome)


def copiar_bibliotecas(destino: Path) -> list[str]:
    destino.mkdir(parents=True, exist_ok=True)
    nomes = []
    for dist in distribuicoes():
        nomes.append(f"{dist.metadata['Name']} {dist.version}")
        for arquivo in dist.files or []:
            partes = Path(arquivo).parts
            if partes[0] == ".." or "__pycache__" in partes:
                continue  # executáveis da pasta Scripts e cache: não vão
            origem = Path(dist.locate_file(arquivo))
            if origem.is_file():
                alvo = destino / arquivo
                alvo.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(origem, alvo)
    return sorted(nomes, key=str.lower)


def copiar_codigo(destino: Path) -> None:
    ignorar = lambda _d, nomes: [n for n in nomes if n in FORA_DA_APRESENTACAO or n.endswith(".pyc")]  # noqa: E731
    shutil.copytree(RAIZ / "apresentacao", destino / "apresentacao", ignore=ignorar)
    (destino / "app").mkdir(parents=True)
    for nome in ["__init__.py", "celular.py"]:
        shutil.copy2(RAIZ / "app" / nome, destino / "app" / nome)
    shutil.copytree(RAIZ / "app" / "estatico", destino / "app" / "estatico", ignore=ignorar)
    (destino / "nucleo").mkdir()
    for nome in ["__init__.py", "enquadrar.py"]:
        shutil.copy2(RAIZ / "nucleo" / nome, destino / "nucleo" / nome)


def montar(destino: Path, com_zip: bool) -> Path:
    from app import celular
    from apresentacao import servidor

    if destino.exists():
        raise SystemExit(f"A pasta {destino} já existe: apague ou escolha outro --destino.")
    modelo = servidor.MODELO.name
    print("Python…")
    copiar_python(destino / "sistema" / "python")
    print("Bibliotecas…")
    nomes = copiar_bibliotecas(destino / "sistema" / "python" / "Lib" / "site-packages")
    print("  ", ", ".join(nomes))
    print("Código…")
    pyron = destino / "sistema" / "pyron"
    copiar_codigo(pyron)
    # certificado do modo celular já pronto: sem o Git (OpenSSL) no outro computador, ele é reaproveitado
    celular.certificado(pyron / "apresentacao" / ".celular", "0.0.0.0")
    print("Modelos…")
    shutil.copytree(RAIZ / "modelos", destino / "modelos", ignore=lambda _d, nomes: [n for n in nomes if n == "__pycache__"])
    print("Imagens de teste…")
    imagens = destino / "imagens de teste"
    imagens.mkdir()
    fotos = json.loads((RAIZ / "apresentacao" / "dados" / "avaliacao" / "avaliacao.json").read_text(encoding="utf-8"))["fotos_teste"]
    for nome in fotos:
        shutil.copy2(servidor.ACERVO / nome, imagens / nome)
    (imagens / "CRÉDITO.txt").write_text(
        "Infrared Power Equipment Dataset (ScienceDB 10185, doi 10.57760/sciencedb.10185).\n"
        "Licença CC BY-NC-SA 4.0: uso não comercial, com crédito, compartilhamento pela mesma licença.\n", encoding="utf-8")
    (destino / f"Abrir {NOME}.bat").write_text(BAT.format(modelo=modelo).replace("\n", "\r\n"), encoding="ascii")
    (destino / "LEIA-ME.txt").write_text(LEIA_ME.format(modelo=modelo), encoding="utf-8-sig")
    if not com_zip:
        return destino
    arquivo = destino.with_suffix(".zip")
    print(f"Compactando em {arquivo.name}…")
    with zipfile.ZipFile(arquivo, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(destino.rglob("*")):
            if f.is_file():
                z.write(f, Path(destino.name) / f.relative_to(destino))
    return arquivo


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--destino", type=Path, default=area_de_trabalho() / NOME)
    ap.add_argument("--sem-zip", action="store_true")
    args = ap.parse_args()
    feito = montar(args.destino, not args.sem_zip)
    print("Pronto:", feito)


if __name__ == "__main__":
    main()
