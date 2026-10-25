import json
from pathlib import Path
v = json.load(open("vetor.json"))
C = v["cores"]

def simbolo(mao=None, mono=None):
    cor = lambda n: mono or (mao if (n == "mao" and mao) else C[n])
    partes = [f'<path fill="{cor("laranja")}" d="{v["chama_ext"]}"/>',
              f'<path fill="{cor("amarelo")}" d="{v["chama_meio"]}"/>',
              f'<path fill="{cor("brasa")}" d="{v["chama_nucleo"]}"/>',
              f'<path fill="{cor("mao")}" fill-rule="evenodd" d="{v["mao"]}"/>']
    partes += [f'<rect fill="{cor(p["cor"])}" x="{p["x"]}" y="{p["y"]}" width="{p["lado"]}" height="{p["lado"]}"/>' for p in v["pixels"]]
    return "".join(partes)

if __name__ == "__main__":
    Path("simbolo-teste.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {v["W"]} {v["H"]}">{simbolo()}</svg>')
