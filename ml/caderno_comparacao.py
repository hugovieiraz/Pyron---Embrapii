"""Gera o caderno do Colab que compara três detectores: trivial, MobileNet e DINOv2 congelado.

Uso: python -m ml.caderno_comparacao   (grava ml/notebooks/Pyron_comparar_modelos.ipynb)
"""

from __future__ import annotations

import json
from pathlib import Path

DESTINO = Path(__file__).resolve().parent / "notebooks" / "Pyron_comparar_modelos.ipynb"


def md(*linhas: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": _fonte(linhas)}


def code(*linhas: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": _fonte(linhas)}


def _fonte(linhas) -> list[str]:
    texto = "\n".join(linhas).strip("\n")
    partes = texto.split("\n")
    return [p + "\n" for p in partes[:-1]] + [partes[-1]]


CELULAS = [
    md(
        "# Pyron · comparação de detectores de para-raios",
        "",
        "Três modelos treinados e avaliados **com os mesmos dados e as mesmas métricas**:",
        "",
        "| Modelo | O que é | O que aprende |",
        "|---|---|---|",
        "| **1. Trivial** | Põe em toda foto a caixa média de cada classe vista no treino. Não olha a imagem. | Nada: é o piso da comparação. |",
        "| **2. MobileNet** | Detector Faster R-CNN com base MobileNetV3, pré-treinada em fotos comuns (COCO). | A base é ajustada e a cabeça de detecção aprende. |",
        "| **3. DINOv2 (características)** | O mesmo detector Faster R-CNN, mas com o **DINOv2 congelado** como base. | Só a cabeça de detecção aprende; o DINOv2 não muda. |",
        "",
        "**Como rodar:** menu *Ambiente de execução › Alterar o tipo de ambiente de execução › GPU (T4)*. Depois *Ambiente de execução › Executar tudo*. "
        "Na célula de envio, escolha o arquivo `Pyron_pacote_treino_para-raios.zip`. Leva em torno de 15 a 25 minutos.",
    ),
    md(
        "## O que é \"treinar o DINO com as características\"",
        "",
        "Um detector tem duas partes: **os olhos** (a base, que transforma a imagem num mapa de características) e **o cérebro** "
        "(a cabeça, que olha esse mapa e decide onde há um para-raio, um terminal etc.).",
        "",
        "- O **DINOv2** é um modelo da Meta treinado **sem rótulos** em 142 milhões de imagens. Ele aprendeu sozinho a descrever cada pedaço de "
        "14×14 pixels de uma imagem com um vetor de 384 números (as *características*): bordas, formas, texturas, o que é parecido com o quê.",
        "- **Congelado** quer dizer que não mexemos nesses olhos. Passamos a imagem térmica por ele, pegamos o mapa de características "
        "e treinamos só a cabeça de detecção em cima disso.",
        "- No **MobileNet**, os olhos também são ajustados com as nossas imagens.",
        "",
        "Como a cabeça é a mesma nos dois, a comparação responde: **as características prontas do DINOv2 enxergam para-raios térmicos melhor "
        "que uma base menor ajustada?** Com poucos rótulos, costuma ser o caso; com imagens térmicas (diferentes das fotos em que o DINOv2 aprendeu), "
        "só o teste diz.",
    ),
    md(
        "## Como ler as métricas (e por que não é \"acurácia\")",
        "",
        "Em detecção não existe uma resposta por imagem: há vários componentes por foto, e o modelo pode achar alguns, errar a classe, "
        "desenhar a caixa torta ou inventar caixas. Por isso a \"acurácia\" de classificação não serve. Usamos:",
        "",
        "- **Perda (loss):** o número que o treino tenta diminuir (erro de classe + erro de posição das caixas). Serve para ver se o modelo "
        "**está aprendendo** e se está **decorando** (perda do treino caindo e a da validação subindo). Não é nota de qualidade.",
        "- **IoU:** quanto a caixa prevista se sobrepõe à rotulada (0 = nada, 1 = perfeita). É **acerto** quando a classe está certa e o IoU ≥ 0,5.",
        "- **Precisão:** das caixas que o modelo desenhou, quantas estão certas. **Revocação:** dos componentes rotulados, quantos ele achou. "
        "**F1:** o equilíbrio entre as duas.",
        "- **mAP50:** a qualidade média em todos os níveis de confiança, com IoU ≥ 0,5 (0 a 1; é a métrica principal). "
        "**mAP50-95:** a mesma coisa exigindo caixas cada vez mais justas (IoU de 0,5 a 0,95).",
        "- **Erro da Tmáx (°C):** o que importa no Pyron. Diferença entre a temperatura máxima dentro da caixa prevista e dentro da rotulada, "
        "nos componentes que o modelo achou.",
    ),
    code(
        "import torch, sys, time, json",
        "print('PyTorch', torch.__version__)",
        "print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NÃO ENCONTRADA: ative a GPU no menu Ambiente de execução')",
    ),
    md("## 1. Enviar os dados", "", "Escolha o `Pyron_pacote_treino_para-raios.zip` (código do Pyron, rótulos do CVAT e as imagens originais com a temperatura)."),
    code(
        "from google.colab import files",
        "enviado = files.upload()",
        "pacote = next(iter(enviado))",
        "!rm -rf /content/pyron && mkdir -p /content/pyron && unzip -q -o \"$pacote\" -d /content/pyron && echo pacote aberto",
        "%cd /content/pyron",
        "sys.path.insert(0, '/content/pyron')",
    ),
    md("## 2. Configuração", "", "Pode mudar e rodar de novo. `DIVISAO = 'cvat'` usa o teste que você separou no CVAT; a validação (para escolher a melhor época) sai do treino."),
    code(
        "EPOCAS = 40          # passadas pelas imagens de treino",
        "LOTE = 4             # imagens por passo",
        "TAXA = 0.01          # taxa de aprendizado (SGD)",
        "LIMIAR = 0.5         # confiança mínima para contar uma caixa (a mesma do Pyron)",
        "DIVISAO = 'cvat'     # 'cvat' ou 'sessao'",
        "DINO = 'dinov2_vits14'   # 'dinov2_vitb14' é maior e mais lento",
        "PASSO_DINO = 8       # 8 = grade fina (terminais pequenos); 14 = mais rápido",
        "",
        "import glob, numpy as np",
        "torch.manual_seed(2026); np.random.seed(2026)",
        "dispositivo = torch.device('cuda' if torch.cuda.is_available() else 'cpu')",
        "ROTULOS = sorted(glob.glob('rotulos/*.zip') + glob.glob('rotulos/*.json'))[0]",
        "print('rótulos:', ROTULOS)",
    ),
    md("## 3. Conferir os dados", "", "O relatório e alguns exemplos com as caixas rotuladas. As fotos tiradas com a câmera em pé aparecem em pé."),
    code(
        "from pathlib import Path",
        "from ml import dados, comparacao",
        "from ml.treinar import imprimir_analise",
        "imprimir_analise(dados.analisar(Path(ROTULOS), Path('imagens')))",
        "amostras, classes, nomes = dados.ler_coco(Path(ROTULOS), Path('imagens'))",
        "treino, validacao, teste = comparacao.dividir(amostras, DIVISAO)",
        "print(f'\\ntreino {len(treino)} · validação {len(validacao)} · teste {len(teste)} imagens')",
        "print('classes:', [nomes[c] for c in classes])",
        "comparacao.figura_rotulos(treino, classes, nomes, n=8);",
    ),
    md("## 4. Modelo 1: trivial", "", "Caixa média de cada classe, igual em toda foto. Mostra quanto vale \"não olhar a imagem\"."),
    code(
        "trivial = comparacao.ModeloTrivial().ajustar(treino)",
        "t0 = time.time(); prev_trivial = trivial.prever(teste); tempo_trivial = (time.time() - t0) / len(teste)",
        "r_trivial = comparacao.avaliar(teste, prev_trivial, classes, nomes, LIMIAR)",
        "print(json.dumps({k: v for k, v in r_trivial.items() if k != 'por_classe'}, ensure_ascii=False, indent=1))",
    ),
    md("## 5. Modelo 2: MobileNet (base ajustada)", "", "Cada linha é uma época: perda no treino, perda na validação e, a cada 2 épocas, o mAP50 na validação. Fica guardada a melhor época."),
    code(
        "from ml import comparacao_modelos as cm",
        "mobilenet = cm.criar_mobilenet(len(classes))",
        "print('parâmetros:', cm.parametros(mobilenet))",
        "hist_mobilenet = cm.treinar(mobilenet, treino, validacao, classes, EPOCAS, LOTE, TAXA, limiar=LIMIAR, dispositivo=dispositivo, nome='MobileNet')",
        "print('melhor época:', hist_mobilenet['melhor_epoca'], '· mAP50 validação:', round(hist_mobilenet['melhor_map50_validacao'], 3), '·', hist_mobilenet['duracao_min'], 'min')",
    ),
    md(
        "## 6. Modelo 3: DINOv2 congelado (características)",
        "",
        "O DINOv2 é baixado na primeira vez (~85 MB). Repare em `parâmetros`: o total inclui o DINOv2, mas os **treináveis** são só os da cabeça de detecção.",
    ),
    code(
        "dino = cm.criar_dino(len(classes), DINO, PASSO_DINO)",
        "print('parâmetros:', cm.parametros(dino))",
        "hist_dino = cm.treinar(dino, treino, validacao, classes, EPOCAS, LOTE, TAXA, limiar=LIMIAR, dispositivo=dispositivo, nome='DINOv2')",
        "print('melhor época:', hist_dino['melhor_epoca'], '· mAP50 validação:', round(hist_dino['melhor_map50_validacao'], 3), '·', hist_dino['duracao_min'], 'min')",
    ),
    md(
        "## 7. Curvas de treino",
        "",
        "- **Perda caindo nas duas linhas:** está aprendendo.",
        "- **Treino caindo e validação subindo:** está decorando as fotos de treino (sobreajuste); a melhor época (linha pontilhada) fica antes disso.",
        "- **mAP50 da validação subindo e estabilizando:** o ponto em que mais treino já não ajuda.",
    ),
    code(
        "import os; os.makedirs('resultados', exist_ok=True)",
        "comparacao.figura_curvas({'MobileNet': hist_mobilenet, 'DINOv2': hist_dino}, Path('resultados/curvas.png'));",
    ),
    md("## 8. Resultado no teste", "", "Fotos que nenhum modelo viu no treino nem na escolha da melhor época."),
    code(
        "import pandas as pd",
        "def cronometrar(modelo):",
        "    t0 = time.time(); p = cm.prever(modelo, teste, dispositivo); return p, (time.time() - t0) / len(teste)",
        "prev_mobilenet, tempo_mobilenet = cronometrar(mobilenet)",
        "prev_dino, tempo_dino = cronometrar(dino)",
        "resultados = {",
        "    'Trivial': comparacao.avaliar(teste, prev_trivial, classes, nomes, LIMIAR),",
        "    'MobileNet': comparacao.avaliar(teste, prev_mobilenet, classes, nomes, LIMIAR),",
        "    'DINOv2': comparacao.avaliar(teste, prev_dino, classes, nomes, LIMIAR),",
        "}",
        "tempos = {'Trivial': tempo_trivial, 'MobileNet': tempo_mobilenet, 'DINOv2': tempo_dino}",
        "tabela = pd.DataFrame({m: {k: v for k, v in r.items() if k != 'por_classe'} for m, r in resultados.items()}).T",
        "tabela['ms por imagem'] = [round(tempos[m] * 1000, 1) for m in tabela.index]",
        "display(tabela)",
        "por_classe = pd.concat({m: pd.DataFrame(r['por_classe']).T for m, r in resultados.items()}, axis=1)",
        "display(por_classe)",
    ),
    code(
        "import matplotlib.pyplot as plt",
        "metricas = ['mAP50', 'mAP50-95', 'precisao', 'revocacao', 'F1']",
        "fig, ax = plt.subplots(figsize=(10, 4))",
        "largura = 0.26",
        "for i, (m, cor) in enumerate(zip(resultados, ['#9AA2B9', '#3F50D6', '#7D5CF0'])):",
        "    valores = [resultados[m][k] or 0 for k in metricas]",
        "    barras = ax.bar(np.arange(len(metricas)) + (i - 1) * largura, valores, largura, label=m, color=cor)",
        "    ax.bar_label(barras, fmt='%.2f', fontsize=7)",
        "ax.set_xticks(np.arange(len(metricas)), ['mAP50', 'mAP50-95', 'Precisão', 'Revocação', 'F1'])",
        "ax.set_ylim(0, 1.05); ax.set_title('Teste: maior é melhor'); ax.legend(); ax.grid(axis='y', alpha=.3)",
        "fig.tight_layout(); fig.savefig('resultados/metricas.png', dpi=110)",
    ),
    md(
        "## 9. Onde cada modelo acertou e errou",
        "",
        "Cada linha é uma foto de teste; cada coluna, um modelo. **Verde**: acerto. **Vermelho**: caixa falsa (lugar ou classe errada). "
        "**Amarelo tracejado**: componente rotulado que o modelo não achou. O número ao lado da sigla é a confiança.",
    ),
    code(
        "previsoes = {'Trivial': prev_trivial, 'MobileNet': prev_mobilenet, 'DINOv2': prev_dino}",
        "comparacao.figura_comparacao(teste, previsoes, classes, nomes, LIMIAR, Path('resultados/comparacao_teste.png'), n=8);",
    ),
    md("### As fotos mais difíceis", "", "As quatro fotos em que o melhor modelo mais errou (falsos + perdidos). É aqui que dá para ver o que falta: rótulo inconsistente, peça pequena, fundo quente…"),
    code(
        "melhor = max(['MobileNet', 'DINOv2'], key=lambda m: resultados[m]['mAP50'] or 0)",
        "erros = []",
        "for i, a in enumerate(teste):",
        "    pc, pp, pk = previsoes[melhor][i]",
        "    _, falsos, perdidos = comparacao.casar(a.caixas, a.classes, pc, pp, pk, LIMIAR)",
        "    erros.append(len(falsos) + len(perdidos))",
        "piores = list(np.argsort(erros)[::-1][:4])",
        "print('melhor modelo:', melhor, '· fotos:', [teste[i].nome for i in piores])",
        "comparacao.figura_comparacao([teste[i] for i in piores], {m: [p[i] for i in piores] for m, p in previsoes.items()},",
        "                             classes, nomes, LIMIAR, Path('resultados/piores_casos.png'), n=4);",
    ),
    md("## 10. Salvar e baixar", "", "Baixa `resultados_comparacao.zip` com as figuras e os números. Me mande esse arquivo para a gente analisar junto."),
    code(
        "resumo = {",
        "    'configuracao': {'epocas': EPOCAS, 'lote': LOTE, 'taxa': TAXA, 'limiar': LIMIAR, 'divisao': DIVISAO, 'dino': DINO, 'passo_dino': PASSO_DINO},",
        "    'imagens': {'treino': len(treino), 'validacao': len(validacao), 'teste': len(teste)},",
        "    'teste': resultados,",
        "    'ms_por_imagem': {m: round(t * 1000, 1) for m, t in tempos.items()},",
        "    'historico': {'MobileNet': hist_mobilenet, 'DINOv2': hist_dino},",
        "    'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu',",
        "}",
        "Path('resultados/resumo.json').write_text(json.dumps(resumo, ensure_ascii=False, indent=1, default=float), encoding='utf-8')",
        "tabela.to_csv('resultados/metricas_teste.csv'); por_classe.to_csv('resultados/metricas_por_classe.csv')",
        "!cd /content/pyron && zip -q -r /content/resultados_comparacao.zip resultados",
        "files.download('/content/resultados_comparacao.zip')",
    ),
    md(
        "## (Opcional) Guardar os pesos",
        "",
        "Os pesos não vão no zip de resultados (são grandes). Rode esta célula só se quiser guardá-los; o Pyron ainda precisa de uma versão exportada "
        "para usar o vencedor, que a gente faz depois de escolher.",
    ),
    code(
        "torch.save(mobilenet.state_dict(), '/content/pesos_mobilenet.pt')",
        "torch.save({k: v for k, v in dino.state_dict().items() if not k.startswith('backbone.vit.')}, '/content/pesos_dino_cabeca.pt')",
        "files.download('/content/pesos_mobilenet.pt'); files.download('/content/pesos_dino_cabeca.pt')",
    ),
]


def gerar(destino: Path = DESTINO) -> Path:
    caderno = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "T4"}, "kernelspec": {"name": "python3", "display_name": "Python 3"},
                     "language_info": {"name": "python"}},
        "cells": CELULAS,
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(caderno, ensure_ascii=False, indent=1), encoding="utf-8")
    return destino


if __name__ == "__main__":
    print("caderno:", gerar())
