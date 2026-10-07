<p align="center"><img src="app/estatico/marca/logo.png" alt="Pyron: Manutenção Preditiva, Termografia Digital" width="260"></p>

# Pyron

Manutenção preditiva por termografia para ativos elétricos, começando por transformadores e
equipamentos de subestação. Lê a temperatura de cada pixel, encontra componentes e pontos quentes,
compara cada um com o limite do componente e com as outras fases, classifica a severidade e gera o
laudo.

**Estado:** versão 0.7 (aplicativo local com painel, análise com ferramentas de medição, relatório
com várias imagens, histórico e tendência por equipamento, pendências até a correção verificada,
monitoramento de pasta com alertas, detector de para-raios RF-DETR combinado com a regra de pontos
quentes e simulação de câmera ao vivo a partir de vídeo).

Todas as funcionalidades, tela por tela: [`docs/Pyron_Funcionalidades.pdf`](docs/Pyron_Funcionalidades.pdf)
(gerado por `docs/manual/gerar_manual.py`).

> Os termogramas das capturas do manual (`docs/manual/imagens/`) vêm do *Infrared Thermal Image
> Dataset of High Voltage Electrical Power Equipment under Different Operating Conditions*
> ([ScienceDB 10185](https://doi.org/10.57760/sciencedb.10185)), licença
> [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/): uso não comercial, para estudo.

## Abrir o aplicativo

Dois cliques em **`Pyron.exe`** na área de trabalho. Aparece a tela de abertura, o motor carrega
em poucos segundos e a interface abre numa janela própria (Edge em modo aplicativo, sem barra de
endereço). Tudo roda só neste computador, em `http://127.0.0.1:8765`. Não há console nem nada para
encerrar: o servidor se desliga sozinho quando a última janela é fechada.

O `.exe` é um lançador pequeno (C#, compilado pelo `csc.exe` que vem com o Windows) que guarda o
caminho desta pasta. Para gerar de novo, por exemplo depois de mover o projeto:

```bash
.venv/Scripts/python.exe lancador/construir.py
```

Sem o `.exe`, pela pasta do projeto:

```bash
.venv/Scripts/python.exe -m app.iniciar --janela
```

Depois de uma atualização, se um servidor de versão antiga ainda estiver na memória, o `Pyron.exe`
percebe (compara `/api/saude` com `VERSAO` de `app/servidor.py`), desliga o antigo e sobe o novo; as
janelas abertas recarregam sozinhas quando o servidor volta.

Diagnóstico: `Pyron.exe --verificar` sobe o servidor escondido, confere se respondeu e desliga; o
resultado fica em `app/dados_app/verificacao.txt`. Erros do servidor ficam em
`app/dados_app/servidor.log`.

> O lançador não é assinado digitalmente. Com o Controle Inteligente de Aplicativos do Windows
> ligado, uma versão com a logo embutida (390 KB) foi bloqueada; a versão atual (≈100 KB, logo lida
> da pasta do projeto) passa. Para distribuir a clientes, o caminho é assinar o executável.

## Como a severidade é decidida

Temperatura sozinha não diz nada; o Pyron compara cada região com duas referências da NBR 15866 e
fica com a pior:

1. **Máxima temperatura admissível (MTA) do componente**, com a temperatura projetada para plena
   carga: `T_proj = T_amb + (T − T_amb) · (100 / carga)²`. Faixas: > 60% da MTA atenção, > 70%
   programar, > 80% urgente, > 100% imediato. A biblioteca de componentes (Configurações) traz as
   MTAs de partida com a fonte de cada uma e pode ser editada.
2. **ΔT entre componentes semelhantes** (as três fases): 5–10 °C atenção, > 10–20 programar,
   > 20–40 urgente, > 40 imediato. Para-raios e isoladores aquecem por fuga, não por carga: faixas
   próprias (2 / 5 / 10 °C) e sem correção de carga.

Também mostra até que carga o componente chega à MTA. Os detalhes e as fontes estão em
[`docs/04_referencias_de_temperatura.md`](docs/04_referencias_de_temperatura.md).

## Equipamentos: histórico, tendência e próxima inspeção

Cada imagem pode pertencer a uma instalação e a um equipamento (no envio, na aba Laudo da análise
ou em Inspeções › marcar várias › **Definir equipamento**). A tela **Equipamentos** mostra, para
cada um:

- a máxima de cada inspeção pela data da captura, com a **tendência em °C por mês** (mínimos
  quadrados, a partir de 3 inspeções espalhadas por pelo menos um mês) e a reta no gráfico;
- quando o % da MTA sobe, **em quanto tempo chegaria à MTA** se a tendência continuar (estimativa,
  até 5 anos);
- a **próxima inspeção** pela severidade atual: anual quando normal (a NFPA 70B pede ao menos uma
  vez por ano), 90 dias em atenção, 30 em programar, 7 em urgente e 1 em imediato;
- a máxima de cada tipo de peça ao longo do tempo e o histórico de inspeções.

## Pendências: da anomalia à correção verificada

Toda inspeção fora do normal vira uma pendência com prazo pela severidade e a situação **aberta →
programada (com nº da ordem de serviço) → corrigida → verificada** (ou descartada), com responsável,
notas e histórico. Uma inspeção normal posterior do mesmo equipamento é sugerida como a reinspeção
que verifica a correção. O Painel mostra as pendências vencidas e as próximas inspeções.

## Ferramentas de análise

- **Ponto (P)** e **Linha (L)** sobre o termograma, com o perfil de temperatura ao longo da linha;
  ficam guardados e vão para o laudo.
- **Escala manual** (nível e amplitude) e paleta: o laudo e a imagem exportada saem como a tela.
- **Parâmetros de medição** dos termogramas radiométricos: emissividade (com tabela de materiais),
  temperatura refletida, distância, umidade e temperatura do ar, recalculados a partir do arquivo
  original, com volta aos valores da câmera.
- **Exportar**: PNG com regiões, pontos e linhas; matriz de temperaturas e planilha de inspeções em
  CSV que abre direto no Excel em português.
- **Busca rápida (Ctrl+K)** por inspeção, equipamento, tela ou ação, e **?** para os atalhos.

## Imagens sem temperatura

Nem toda imagem térmica traz temperatura. De onde ela sai, em ordem de confiança:

1. **JPEG radiométrico da câmera** (FLIR, bloco FFF): temperatura **medida**, com emissividade e
   demais parâmetros ajustáveis.
2. **Imagem colorida com a barra de cores e os números da escala** (print, foto exportada, quadro de
   vídeo): temperatura **estimada** pelas cores. A escala lida aparece na aba Resultado e pode ser
   corrigida.
3. **Sem dados radiométricos e sem escala legível** (imagem da internet, gerada por IA, captura
   cortada): a análise **não trava**. Os componentes são identificados pela imagem colorida (com um
   modelo que olha a imagem, como o RF-DETR), as etapas de temperatura ficam marcadas como "sem
   dado" e a inspeção entra como **Sem medida**: não conta como normal, não vira pendência e não
   gera laudo. Se a imagem tem a barra de cores, basta informar o mínimo e o máximo dela para
   estimar a temperatura.

Aceita JPEG, PNG, WebP e BMP.

## Relatório de inspeção

O relatório segue a estrutura de um documento técnico: identificação, normas citadas (ABNT NBR
15572:2013, NBR 15866:2010 e NBR 15424), critério e recomendação por nível, resumo dos resultados,
um registro por imagem (termograma numerado, foto visível, condições de medição, tabela de pontos,
comparação entre peças semelhantes), conclusão, referências de temperatura e o bloco do responsável
técnico com ART. Número do relatório (`RT-AAAAMMDD-XXXX`) e "Página x de y" no rodapé.

- **Várias imagens num relatório:** marque as inspeções em Inspeções e use *Gerar relatório*.
- **Responsável só do cadastro:** o responsável técnico (nome, função, registro) é escolhido de uma
  lista cadastrada em Configurações; o laudo não sai sem ele, para o nome e o registro nunca saírem
  digitados errado. A ART é informada na hora de gerar.
- **Logotipo da empresa** (Configurações › Empresa) no cabeçalho de cada laudo.

## Vídeo ao vivo (simulação de câmera)

A tela **Vídeo ao vivo** recebe a gravação da tela da câmera (MP4, AVI, MOV, MKV) e analisa quadro a
quadro com o mesmo caminho de uma foto sem dados radiométricos: barra de cores → temperatura
estimada → detector → medição e severidade.

- **Ao vivo:** o vídeo corre no relógio, como a câmera; enquanto o detector trabalha, os quadros
  que passam se perdem. Mostra o ritmo real (quadros por segundo) e o tempo por quadro deste
  computador. **Um quadro a cada intervalo:** analisa sem perder nenhum.
- A imagem aparece com as caixas enquanto a análise roda; depois dá para reproduzir no ritmo em
  que os quadros foram analisados, pular pelo gráfico da máxima ao longo do tempo ou pelos momentos
  com anomalia, e **salvar um quadro como inspeção** (vira uma análise comum, com laudo).
- Os números da escala só passam pelo OCR quando mudam (e a cada 10 s de vídeo, por segurança); o
  reconhecimento direto leva ~100 ms e, na dúvida, cai no OCR completo. A cor vira temperatura por
  uma tabela montada uma vez por paleta. Com a escala travada na câmera, informe os limites.
- Neste notebook, com o RF-DETR (ONNX no processador) + pontos quentes: ~0,6 s por quadro (≈1,6 quadro/s).

Vídeo de teste montado a partir das fotos do conjunto (a cena se move, a barra fica parada):

```bash
.venv/Scripts/python.exe -m ml.video_demo --fotos dados/para_raios_dataset_v2/test dados/para_raios_dataset_v2/val --saida dados/video_demo.mp4
```

## Monitoramento e alertas

O Pyron vigia a pasta onde a câmera grava (cartão sincronizado, FTP da câmera fixa, FLIR Thermal
Studio), analisa cada imagem nova e, quando a severidade atinge o mínimo configurado, cria um alerta
com a mensagem pronta para o WhatsApp de cada responsável (link `wa.me`, envio manual). Funciona
enquanto o Pyron está aberto. No backlog: conexão direta RTSP/ONVIF e FLIR Atlas, envio automático
pelo WhatsApp Business, aviso no celular, serviço do Windows e escalonamento.

## Treinar um modelo com os rótulos do CVAT

1. No CVAT: projeto (ou tarefa) › ⋮ › **Exportar conjunto de dados** › formato **COCO 1.0**, com
   **Salvar imagens desmarcado** (a temperatura vem dos JPEG originais, achados pelo nome em `dados/`).
   Projeto com treino/validação/teste exporta um `.json` por parte; o Pyron junta todos. Caixas,
   polígonos e máscaras são aceitos.
2. **No Pyron:** Modelos › Treinar um modelo › solte o `.zip`. Aparece o relatório (imagens achadas,
   rótulos por classe, sessões, avisos); escolha nome, épocas e a separação treino/teste (por sessão,
   recomendado, ou a do CVAT) e acompanhe época por época. O treino roda em processo separado e
   continua mesmo se a janela for fechada.
3. **No terminal:** arraste o `.zip` sobre `treinar_modelo.bat` (ou o atalho "Pyron - Treinar modelo"
   da área de trabalho), ou `python -m ml.assistente arquivo.zip`.
4. **Fora deste computador** (Google Colab, supercomputador): "Baixar pacote para treinar fora" gera
   um `.zip` com código, rótulos, imagens, caderno do Colab e exemplo de job SLURM
   (`python -m ml.pacote --coco arquivo.zip`). O resultado volta por Modelos › Instalar modelo treinado.

> Com o Controle Inteligente de Aplicativos do Windows ligado, as DLLs do PyTorch são bloqueadas
> (WinError 4551) e o treino local não roda; o Pyron detecta e explica. Usar modelos já treinados
> continua funcionando (o ONNX Runtime é assinado).

## Comparar detectores no Colab e trazer o vencedor (aba Avaliação)

O caderno `Treino_para_raios_Colab.ipynb` (gerado à parte, roda inteiro no Google Colab) treina e
compara três detectores com a mesma divisão de fotos: **Faster R-CNN** (clássico), **YOLO26**
(o mais usado; licença AGPL, só para comparar) e **RF-DETR** (topo de linha, base DINOv2, licença
Apache). Ele baixa `resultados_comparacao.zip` (passo 16) e, no passo 17, exporta o RF-DETR em ONNX,
confere o ONNX contra o PyTorch e baixa `pyron_para-raios-rfdetr-….zip` (modelo + resultados).

No Pyron, **Avaliação › Importar do Colab** aceita os dois arquivos:

- a comparação vai para `dados_app/avaliacoes/<data>/` e aparece com gráficos (métricas no teste,
  AP50 por componente, curvas de perda e mAP50 por época), a leitura automática (empate técnico,
  ponto fraco comum), peças perdidas por classe e tamanho, efeito do limiar e as fotos de teste marcadas;
- o modelo, se vier junto, é instalado em `modelos/` e pode ser ativado ali mesmo.

Esses modelos olham a **imagem colorida** da câmera (`entrada.fonte = "imagem_exibida"`), não a
matriz de temperatura; as caixas voltam para a matriz, onde a temperatura é medida. Contrato em
[`modelos/LEIA-ME.md`](modelos/LEIA-ME.md).

### Peças, calor ou os dois (tela Modelos)

Cada modelo instalado aparece três vezes na escolha do detector: **só os pontos quentes** (regra),
**só as peças** (o modelo treinado) e **o modelo + pontos quentes**. Com os dois juntos, a análise
(`nucleo/analise.relacionar_componentes`) liga cada ponto quente à peça mais específica onde ele está
(o terminal, e não o para-raio inteiro), aponta o **ponto mais quente nas peças** (com um alvo no
termograma), avisa se há um ponto ≥ 1 °C mais quente fora das peças ou acima de 150 °C (sol ou
reflexo), e monta a **comparação entre componentes** iguais: Tmáx de cada fase, diferença para a
referência do critério e entre a mais quente e a mais fria. Tudo isso vai também para o laudo.

### Treinar o RF-DETR aqui no computador (GPU)

Com o PyTorch carregando (o Controle Inteligente de Aplicativos liberou as DLLs dele) e
`pip install "rfdetr[train]==1.11.0" "numpy==2.4.6"` (o numpy fixo evita trocar o do Pyron):

```bash
.venv/Scripts/python.exe -m ml.rfdetr_local --dados dados/para_raios_dataset_v2
```

Lê a pasta do dataset (fotos + `annotations/` do CVAT), treina com a divisão do CVAT (lote 2 × 2,
640 px, cabe numa GPU de 4 GB; ~18 min numa RTX 3050 Laptop), exporta o ONNX, confere pelo próprio
detector do Pyron, escolhe o limiar na validação, mede o **erro da Tmáx** (caixa do modelo × caixa
rotulada, na matriz radiométrica), instala em `modelos/` e grava a avaliação na aba Avaliação.
O cálculo de mAP usa o `faster_coco_eval`: o `vernier` (padrão do RF-DETR) e o `hotcoco` são
bloqueados pelo Windows.

## Interface

Tema claro industrial: fundo branco, azul-índigo nas ações, subtons de violeta, barra lateral azul.
No termograma, as etiquetas das caixas nunca se sobrepõem (cada uma procura um lugar livre; sem
lugar, mostra só a temperatura ou some, e o nome continua na lista). Com peças e pontos quentes na
mesma imagem, o seletor **Tudo / Peças / Pontos quentes** separa as camadas, e **Rótulos** (tecla R)
liga e desliga as etiquetas.
Todos os valores visuais vêm de [`app/estatico/tokens.css`](app/estatico/tokens.css) e os textos
montados pelo JavaScript de [`app/estatico/textos.js`](app/estatico/textos.js). As regras de design,
estados e movimento estão em [`CLAUDE.md`](CLAUDE.md).

Demonstração sem tocar nas inspeções reais:

```bash
.venv/Scripts/python.exe app/iniciar.py --janela --dados C:\temp\pyron_demo
```

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `nucleo/` | Motor sem interface: leitura radiométrica FLIR (`flir.py`), inversão de paleta (`paleta.py`), entrada única (`entrada.py`), referências de temperatura (`referencias.py`), medição e severidade (`analise.py`), desenho (`render.py`), detectores (`detectores/`) |
| `app/` | Servidor local (FastAPI), laudo em PDF, inspeções e alertas salvos, equipamentos e tendência (`equipamentos.py`), pendências (`pendencias.py`), vídeo (`videos.py`), monitoramento de pasta (`monitoramento.py`) e interface web (`estatico/`) |
| `lancador/` | `Pyron.exe`: fonte C# e script de construção |
| `marca/` | Logo original e o script que gera símbolo, ícones e favicon (`gerar_marca.py`) |
| `ml/` | Treino de detectores a partir de rótulos do CVAT, avaliação e exportação ONNX |
| `modelos/` | Modelos treinados instalados (ver `modelos/LEIA-ME.md`) |
| `experimentos/` | Inventário do dataset (`e00`) e avaliação da inversão de paleta (`e01`) |
| `ferramentas/` | Download do dataset de estudo |
| `testes/` | `pytest -q` |
| `docs/` | Visão e roteiro, pesquisa, estudos, manual de funcionalidades (`manual/`) |

## Documentos

| Documento | Conteúdo |
|---|---|
| [`docs/00_visao_requisitos_roteiro.md`](docs/00_visao_requisitos_roteiro.md) | Visão, requisitos, arquitetura, propostas e roteiro de fases |
| [`docs/01_pesquisa_pratica_dados_ferramentas.md`](docs/01_pesquisa_pratica_dados_ferramentas.md) | Como os profissionais trabalham, datasets e ferramentas |
| [`docs/02_estudo_dataset_subestacao.md`](docs/02_estudo_dataset_subestacao.md) | Plano do estudo com o dataset público |
| [`docs/04_referencias_de_temperatura.md`](docs/04_referencias_de_temperatura.md) | Normas, MTAs, projeção para plena carga e tabelas de prioridade |
| [`modelos/LEIA-ME.md`](modelos/LEIA-ME.md) | Como um modelo treinado entra no software |

## Instalação do zero

```bash
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install numpy pillow scipy matplotlib pytest rapidocr-onnxruntime onnx onnxruntime fastapi "uvicorn[standard]" python-multipart reportlab httpx
.venv/Scripts/python.exe ferramentas/baixar_sciencedb.py   # dataset de estudo (CC BY-NC-SA 4.0, só estudo)
.venv/Scripts/python.exe experimentos/e00_inventario.py
.venv/Scripts/python.exe lancador/construir.py              # gera o Pyron.exe na área de trabalho
```

Para treinar detectores (`ml/`), instale também PyTorch com CUDA (`torch` e `torchvision`, índice
cu126 do pytorch.org).

Os dados (`dados/`), resultados (`saida/`), inspeções salvas (`app/dados_app/`) e os modelos
treinados não vão para o repositório.
