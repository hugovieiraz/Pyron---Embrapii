# Medição de dimensões de componentes por imagem: pesquisa

Data: 26/10/2026. Só pesquisa, sem código. Pergunta: com que meios e modelos atuais se mede um componente
(para-raios, isolador, bucha) a partir de imagem de câmera, para integrar em Python, e como validar a medida,
por exemplo com uma referência de tamanho conhecido (comprimento de fio, parafuso padrão).

## 1. O que o Pyron faz hoje (lido no código)

A seção "Dimensões estimadas" da Análise usa `nucleo/pipeline/pyron_pipeline.py` (`analisar_ativo`): o SAM 2
recorta a peça e a altura sai da máscara por um de dois métodos.

**Método 1, distância e lente** (`src/geometry/criminisi_metrology.py`, `compute_dimensions_from_telemetry`):
escala = 2 · d · tan(FOV/2) / largura da imagem em pixels. É o modelo de câmera pinhole, correto em princípio;
o FOV da FLIR C5 está certo na tabela (54°). Dois limites:
- a distância `d` é a que está gravada no arquivo da câmera, que o operador quase nunca ajusta (nos dados de
  demonstração aparece 10,0 m em Condições). O erro da medida é o mesmo erro relativo da distância: 10 m
  gravados para uma peça a 7 m dão 43 % a mais;
- a resolução térmica da C5 é 160 × 120. Pixel na cena:

| Distância | Largura da cena | Térmico (160 px) | Visual (2 592 px, mesmo FOV aproximado) |
|---|---|---|---|
| 3 m | 3,06 m | 19 mm/px | 1,2 mm/px |
| 5 m | 5,10 m | 32 mm/px | 2,0 mm/px |
| 10 m | 10,19 m | 64 mm/px | 3,9 mm/px |

Um para-raios de 1 m a 10 m ocupa ≈ 16 pixels térmicos: errar 1 pixel em cada ponta da máscara já é ±12 %.

**Método 2, Criminisi** (`compute_real_dimensions`): sem distância, a pipeline chama o método com
`h_ref = 1,0 m` por padrão e passa como referência o topo e a base **da própria peça** (`pyron_pipeline.py`,
linha `pts_y = (ys_peca.max(), ys_peca.min())`). Pela fórmula usada, Δproj = Δref e a altura sai sempre igual a
`h_ref`: **1,00 m em qualquer peça**, a menos que o usuário informe a altura (e então devolve o que ele informou).
Conferido chamando a função como a pipeline chama: máscaras de 40, 160 e 465 pixels de altura, com horizontes
diferentes, deram 1,0 m as três.
O número aparece na tela como medida. Além disso, a forma simplificada exige a base da peça no plano do chão e o
ponto de fuga vertical estimado na mesma imagem, o que raramente vale em foto de subestação.

**Medida pela caixa vertical:** a altura é `y_max − y_min` da máscara. Peça inclinada (comum em para-raios
fotografados de baixo) sai menor do que é; o eixo principal da máscara (momentos, `cv2.minAreaRect`) mede melhor.

## 2. A ideia da referência conhecida (fio, parafuso)

É o método clássico de escala por objeto de referência e funciona, com condições que a literatura e as patentes
de medição repetem:
- **mesma profundidade e mesmo plano:** a referência precisa estar à mesma distância da câmera e no plano da
  peça; o erro cresce com a distância entre elas e com a inclinação entre os planos (paralaxe);
- **tamanho da referência na imagem:** referência pequena na imagem gera erro grande quando a peça é muito
  maior (uma patente cita objetos cerca de 10 vezes maiores que a referência como caso problemático);
- **incerteza** (por propagação, sem correlação):
  σL/L = √[(σpx/Lpx)² + (σref,px/Lref,px)² + (σref/Lref)²]. Com 1 pixel de incerteza em cada ponta, o termo
  da referência domina quando ela tem poucos pixels.

Aplicado ao que existe numa subestação:

| Referência | Tamanho | Na imagem térmica a 5 m | Avaliação |
|---|---|---|---|
| Parafuso M16 (cabeça, ISO 4014/4017) | 24 mm entre faces | < 1 px | inviável no térmico; na foto visual, ≈ 12 px a 5 m: só de perto |
| Comprimento de fio ou cabo | variável | bom | o cabo faz catenária e sai do plano da peça; comprimento real raramente é conhecido |
| Diâmetro do condutor | 20 a 30 mm (pela especificação do cabo) | ≈ 1 px | inviável no térmico |
| Disco de isolador de suspensão U70BL (IEC 60305) | ⌀ 255 mm (folha de fabricante) | ≈ 8 px | o melhor candidato "natural": padronizado, repetido na cadeia, perto das peças; o passo de 146 mm precisa ser conferido na tabela da norma |
| Altura ou passo das saias do próprio para-raios (catálogo do fabricante) | 0,5 a 2 m | 16 a 60 px | bom quando o modelo é conhecido; vira validação de si mesmo, não de outra peça |
| Alvo colocado na cena (régua, placa com marcador ArUco ou ChArUco de 30 a 50 cm) | conhecido com precisão | 10 a 15 px | o melhor para a **campanha de validação**; no térmico o alvo precisa de contraste térmico (placa metálica com fita de baixa emissividade) |

Conclusão: o parafuso serve na foto visual e de perto; para a imagem térmica a 5 a 10 m, a referência precisa ter
de 20 cm para cima. Para validar o método, um alvo colocado é melhor que fio ou parafuso, porque o tamanho e a
posição são controlados.

## 3. Outros meios

**Distância medida + câmera calibrada.** Um telêmetro laser (±1 a 3 mm de erro típico em trena laser comum) dá
`d` real; com a matriz da câmera calibrada (`cv2.calibrateCamera` com tabuleiro; no térmico, tabuleiro aquecido ou
de emissividades diferentes), o método 1 passa a ter erro dominado pela máscara, não pela distância. É o caminho
mais barato para tirar o método 1 do "valor padrão da câmera".

**Marcadores fiduciais (ArUco, ChArUco, AprilTag; `cv2.aruco`).** Dão escala e a pose do plano do alvo
(`cv2.solvePnP`); com a peça no mesmo plano, a homografia corrige a perspectiva. Estudos com OpenCV mostram que o
erro sobe com o ângulo e muda com a iluminação; é ferramenta de validação, não de inspeção de rotina.

**Fotogrametria com várias fotos.** Três ou mais fotos em volta da peça e reconstrução 3D: COLMAP (SfM clássico)
ou os modelos de reconstrução direta DUSt3R, MASt3R e VGGT (CVPR 2025). Medem independentemente do ângulo da peça,
mas a escala é desconhecida: precisa de uma referência conhecida ou da distância entre as posições da câmera.
Uma avaliação em blocos aéreos achou o VGGT mais rápido e com poses mais confiáveis, mas com erros de até metros
em cenas grandes; para peça isolada a poucos metros o erro relativo é bem menor, mas não há medição publicada
nesse caso.

**Profundidade métrica com uma foto só** (modelos que estimam a distância de cada pixel):

| Modelo | Ano | O que tem de útil | Cuidado |
|---|---|---|---|
| Depth Pro (Apple) | 2024 | estima também a distância focal; bordas nítidas; ≈ 0,3 s por imagem de 2,25 MP numa V100 | licença própria da Apple, conferir uso comercial |
| Metric3D v2 | 2024 | melhor que o Depth Pro em ETH3D e nuScenes na tabela reproduzida pela revisão de 2025 | precisa da distância focal |
| UniDepth V2 | 2025 | estima a câmera junto; foco em generalizar entre domínios | |
| MoGe-2 (Microsoft) | 2025 | geometria com escala métrica e detalhe fino | |
| Depth Anything V2, versões métricas | 2024 | modelos pequenos (24,8 M parâmetros) | as versões métricas para ambiente externo (Virtual KITTI) são CC BY-NC-SA: não servem para o produto vendido |

Todos foram treinados em imagem colorida, não térmica: usar na foto visual. A própria revisão de 2025 alerta que
as comparações entre artigos usam métricas e dados diferentes; o erro relativo de profundidade em cenas externas
fica tipicamente na casa de alguns por cento a mais de 10 %, e piora em estruturas finas e distantes, que é
exatamente o caso de para-raios e isoladores. Servem como **terceira estimativa independente** da distância
(para conferir o valor gravado na câmera), não como medida principal.

**Segmentação e pontos-chave.**
- SAM 2 (o que já está no projeto) recorta a peça a partir da caixa.
- SAM 3 (Meta, novembro de 2025) acha todas as peças de um conceito por texto ("insulator") ou por exemplo de
  imagem, sob a SAM License; o próprio cartão do modelo diz que domínios específicos se beneficiam de ajuste fino.
- Para medir comprimento, pontos-chave (terminal superior e inferior, primeiro e último disco) são mais estáveis
  que a borda da máscara: um trabalho de 2024 mede o comprimento exposto de parafusos com pontos-chave e um modelo
  monocular (AP 91,6 na detecção dos pontos). Modelos de pose com licença Apache (RTMPose, do MMPose) treinam
  pontos-chave próprios com poucas centenas de imagens anotadas no CVAT, que o projeto já usa.

**No ambiente deste computador:** SAM 2, SAM 3, Depth Pro e afins dependem de PyTorch, que o Controle Inteligente
de Aplicativos barra de forma intermitente. O caminho que já funciona é exportar para ONNX em outro computador (ou
no Colab) e rodar com `onnxruntime-directml`.

## 4. Proposta, em ordem

1. **Corrigir o que já está na tela.** Não mostrar "Dimensões estimadas" pelo método 2 quando a referência é a
   própria peça (hoje sai sempre 1,00 m); medir pelo eixo principal da máscara; mostrar a incerteza (± em cm) que
   vem do pixel e da distância.
2. **Ferramenta de referência na Análise.** Traçar uma linha sobre um elemento de tamanho conhecido e informar o
   tamanho (ou escolher num catálogo: disco U70BL, altura do para-raios do fabricante etc.); a escala vale para
   linhas traçadas no mesmo plano, com o resultado em "comprimento ± incerteza". É a ideia do fio e do parafuso,
   com as condições do item 2.
3. **Campanha de validação cruzada** (antes de confiar em qualquer número): fotos com **duas** referências
   conhecidas (por exemplo, alvo de 50 cm e a altura de catálogo do para-raios), em 3, 5 e 10 m e em 0°, 20° e
   40°, com a distância medida por trena laser. Para cada foto: escala pela referência A, medida de B e comparação
   com o tamanho real de B; o mesmo pelo método 1 com a distância medida e com a distância gravada na câmera; e
   pela profundidade do Depth Pro ou MoGe-2. Resultado: erro mediano e intervalo de 95 % por método, distância e
   ângulo (gráfico de Bland-Altman).
4. Só depois, se a medida de uma foto só não bastar: várias fotos (VGGT ou COLMAP) com uma referência para a escala.

Bibliotecas, todas em Python: OpenCV (`calibrateCamera`, `aruco`, `solvePnP`, `minAreaRect`), NumPy,
scikit-image (`regionprops`: eixo maior e orientação), onnxruntime-directml para os modelos.

## Fontes

- Revisão de profundidade métrica monocular (2025): https://arxiv.org/pdf/2501.11841
- MoGe-2: https://arxiv.org/pdf/2507.02546 · MoGe: https://arxiv.org/pdf/2410.19115
- Depth Pro: https://arxiv.org/pdf/2410.02073v2 · UniDepth V2: https://papers.cool/arxiv/2502.20110
- Depth Anything V2 métrico externo (cartão do modelo): https://huggingface.co/depth-anything/Depth-Anything-V2-Metric-Outdoor-Small-hf/blame/main/README.md
  · licenças das variantes: https://docs.lightly.ai/train/0.16.1/depth_estimation.html
- SAM 3: https://arxiv.org/pdf/2511.16719 · https://github.com/facebookresearch/sam3
- Avaliação de DUSt3R, MASt3R e VGGT em fotogrametria: https://arxiv.org/pdf/2507.14798
- Escala métrica para o VGGT com altura conhecida (UrbanVGGT): https://arxiv.org/pdf/2603.22531 · AMB3R: https://arxiv.org/pdf/2511.20343
- Medição fotogramétrica de equipamento elétrico com objeto de referência (patente US 9570892): https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9570892
- Erros de escala com objeto de referência (patentes US 10201273 e US 8428392): https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10201273 · https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8428392
- Cadeia de isoladores como sequência de elipses (J. Electronic Imaging): https://astronomicaltelescopes.spiedigitallibrary.org/journals/journal-of-electronic-imaging/volume-26/issue-06/063014/Automatic-identification-and-location-technology-of-glass-insulator-self-shattering/10.1117/1.JEI.26.6.063014.full
- Pontos-chave e modelo monocular para parafusos (2024): https://airlab.hku.hk/PaperPublications/56.pdf
- Medição monocular em linha isolada a gás (Energies, 2025): https://doaj.org/article/686a67ff49df4aa497449bb85eb4c092
- U70BL, ⌀ 255 mm (folha de fabricante): https://www.ahlsell.se/en/products/electric/mains-power-supply-equipment-06-09/06-mains-power-supply-equipment/insulators/0624851 · IEC 60305: https://standards.globalspec.com/std/14356064/iec-60305
- FLIR C5 (160 × 120, 54° × 42°, visual 5 MP): https://www.edmundoptics.com/p/flir-c5-compact-thermal-imaging-camera/56466/ · https://digitalcameraworld.com/reviews/flir-c5-review
- Erro de distância com ArUco (ângulo e iluminação): https://www.iris.unisa.it/handle/11386/4916436 · https://doi.org/10.3390/s21051829
