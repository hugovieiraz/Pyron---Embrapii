# Plano: extração de medidas dos componentes

Data: 26/10/2026. Continua a pesquisa de `docs/05_pesquisa_medicao_dimensional.md`. Só plano, nada implementado.
Todos os números abaixo foram medidos nos dados deste computador.

## 1. O ponto de partida (medido)

**As imagens**

| | Medido |
|---|---|
| Grade térmica | 160 × 120 nas 166 imagens de para-raios e nas do ScienceDB conferidas (FLIR C5) |
| Foto visual dentro do arquivo | nenhuma nas 166 |
| Imagem exibida | 640 × 480: a térmica ampliada 4 vezes, sem informação a mais |
| Distância gravada pela câmera | 10,0 m nas 166 (o valor padrão, nunca ajustado) |
| Tamanho do para-raio na imagem | mediana de 77 px térmicos de comprimento (p10 40, p90 114) e 19 px de largura |
| Terminal superior | mediana de 12 px de comprimento (p10 7) |
| Terminal inferior | mediana de 20 px |
| Aletas | mediana de 55 px |

Limite que nenhum modelo passa: errar 1 pixel em cada ponta dá ±2,6 % no comprimento do para-raio,
±10 % na largura dele e ±16 % no comprimento do terminal superior. Medir melhor exige foto mais de perto ou
câmera de mais resolução; o modelo só consegue chegar perto desse limite.

**O código de medição do Gabriel** (`nucleo/detectores/sam2_dinov2.py`, `nucleo/classificacao/dinov2_engine.py`,
`nucleo/pipeline/pyron_pipeline.py`, `src/geometry/`, commit b41b802)

| # | O que acontece | Onde | Efeito |
|---|---|---|---|
| 1 | O pacote `sam2` não está instalado e os pesos não estão em `modelos/sam2` | registro do servidor de 25/10: `No module named 'sam2'` | "Medir" e o detector SAM 2 + DINOv2 nunca rodaram neste computador |
| 2 | Sem distância, a altura vem da tabela `PADROES_ALTURA` (para-raio 1,20 m, isolador 0,80 m...) ou de 1,0 m | `sam2_dinov2.py:47-55` e `:268-288`; `pyron_pipeline.py:179-186` | a "medida" é o valor da tabela: conferido, máscaras de 40, 160 e 465 px dão 1,0 m |
| 3 | Com distância, usa a gravada no arquivo | `criminisi_metrology.py:126` | 10 m em todas as fotos: erro igual ao erro da distância |
| 4 | O DINOv2 classifica comparando com desenhos sintéticos (retângulos cinza feitos com OpenCV) | `dinov2_engine.py:148-230` e `:299-304` | a classe não tem base em imagem real; o RF-DETR treinado já identifica as peças (AP50 0,73 a 1,0) |
| 5 | SAM 2 em modo automático na imagem inteira (`points_per_side=16`) e um DINOv2 por máscara | `sam2_dinov2.py:137-143`, `:202-217` | lento, e na imagem colorida pela paleta o SAM separa faixas de temperatura, não peças |
| 6 | Altura = `y_max − y_min` da máscara | `criminisi_metrology.py:139-142` | peça inclinada (para-raio fotografado de baixo) sai menor |
| 7 | Mede em pixels da imagem exibida (640 × 480) | `sam2_dinov2.py:175`, `:275-280` | a resolução real é 4 vezes menor; a escala fica certa, mas a precisão aparente é falsa |
| 8 | Ponto de fuga e horizonte estimados na própria imagem térmica | `vanishing_points.py` | em 160 × 120, sem linhas retas nítidas, a estimativa não tem apoio |
| 9 | DINOv2 e SAM 2 rodam pelo PyTorch, baixados do GitHub em tempo de execução | `dinov2_engine.py:287` (`torch.hub.load`) | o Controle Inteligente de Aplicativos barra o PyTorch com CUDA de vez em quando; nada está em ONNX |

O que dá para aproveitar: a ideia de recortar a peça com o SAM 2 a partir de uma caixa
(`nucleo/segmentacao/sam2_engine.py`, `predict_mask_from_bbox`), a temperatura medida só no corpo da peça
(`estatisticas_termicas`) e o perfil de diâmetros ao longo da peça.

## 2. Onde o SAM entra

O SAM segmenta qualquer coisa, mas não diz o que é: ele devolve o contorno de onde você apontar (um ponto, uma
caixa). O SAM 3 (novembro de 2025) aceita texto ("insulator") e acha todas as ocorrências, mas foi treinado em
foto colorida comum; termograma de 160 × 120 em falsa cor está fora do que ele viu.

A divisão que aproveita o que cada um faz bem:

| Pergunta | Quem responde | Precisa treinar? |
|---|---|---|
| O que é e onde está (para-raio, aletas, terminais) | RF-DETR, que já está treinado e roda na placa de vídeo | já treinado; melhora com mais fotos rotuladas |
| Onde a peça termina (contorno) | SAM 2 com a caixa do RF-DETR como pista; ou corte por temperatura dentro da caixa | não (comparar os dois na seção 4) |
| Quanto mede | geometria: eixo da peça, pixels e escala | não |
| Em que escala | referência conhecida, catálogo ou distância medida | não |

Então "talvez nem precise treinar" vale para o contorno e para a medida. Para identificar, o treino já foi
feito; o que falta é dado, não modelo.

## 3. O fluxo proposto

1. **Achar as peças:** RF-DETR (ONNX, DirectML, como hoje).
2. **Contorno:** dentro de cada caixa, duas opções medidas lado a lado:
   - SAM 2.1 tiny ou small exportado para ONNX e rodando no `onnxruntime-directml` (sem PyTorch em tempo de execução);
   - corte por temperatura na grade radiométrica (limiar a meia altura entre a peça e o fundo), que é exato no
     pixel térmico e não precisa de modelo.
3. **Geometria na grade térmica de 160 × 120**, não na imagem ampliada:
   - eixo principal da máscara (momentos), comprimento ao longo dele;
   - largura perpendicular em cada ponto (perfil);
   - borda com fração de pixel pela temperatura (onde o perfil cruza a meia altura), o que pode descer o erro
     de ±1 px para perto de ±0,3 px.
4. **Escala, nesta ordem de confiança:**
   1. referência marcada pelo usuário: uma linha sobre algo de tamanho conhecido e o tamanho dele;
   2. catálogo: altura do para-raio do fabricante, disco de isolador U70BL de 255 mm;
   3. distância medida (trena laser) mais o campo de visão da câmera (54° na C5);
   4. sem nenhuma: não mostrar centímetros. Mostrar só **proporções**, que não dependem de escala (largura
      sobre altura, terminal sobre corpo, simetria entre fases). Elas já servem para comparar as três fases.
5. **Incerteza ao lado de cada número** (± cm), somando o pixel, a referência e a distância.
6. **Na tela:** "Dimensões" na região, com o método escrito ("pela referência de 255 mm", "pela distância de 4,2 m").

## 4. Como provar que a medida bate (validação cruzada)

- **Conjunto de validação:** 20 a 30 fotos novas, com duas referências de tamanho conhecido no mesmo plano. Por
  exemplo, uma placa de 50 cm com fita de baixa emissividade (aparece no térmico) e a altura de catálogo do
  para-raio. Tirar em 3, 5 e 10 m, de frente e a 20° e 40°, com a distância medida por trena laser.
- **Comparação:** escala por uma referência e medida da outra, para cada método de escala da seção 3.
- **Contorno:** 30 máscaras feitas à mão no CVAT, para comparar o SAM 2 com o corte por temperatura (IoU e erro
  de comprimento em pixels).
- **Resultado:** erro mediano e intervalo de 95 % por método, por distância e por ângulo.
- **Meta de partida** (rever depois dos primeiros números): até 5 % no comprimento do para-raio a 5 m com
  referência no mesmo plano.

Parafuso e fio: o parafuso M16 (24 mm) fica com menos de 1 pixel térmico a 5 m, então só serve em foto visual
tirada de perto. O fio faz curva e sai do plano. Para a validação, a placa colocada é melhor que os dois.

## 5. As 10 horas de treino no seu computador

O último treino (RF-DETR Medium, 100 épocas, paciência 20) parou sozinho em 18 minutos: com 111 fotos de treino,
o modelo já tinha aprendido o que elas ensinam. Dez horas com os mesmos dados não melhoram o resultado. O que
limita é **dado rotulado**, não tempo de placa de vídeo. Tem 895 fotos de outros equipamentos no ScienceDB
(disjuntores 203, seccionadoras 180, transformadores 178, para-raios 181, bobinas de bloqueio 153), todas sem
rótulo.

O que vale uma noite de treino, depois de juntar dados:

| Bloco | Tempo estimado na RTX 3050 | Para quê |
|---|---|---|
| Pré-rotular com o RF-DETR e o SAM 2 as fotos novas, e revisar no CVAT | minutos de máquina, horas de revisão humana | multiplica os dados sem rotular do zero |
| Validação cruzada em 5 partes do RF-DETR Medium | cerca de 2 h (5 × 20 min) | acerto real com margem, não de uma divisão só |
| Treino mais forte: multiescala ligada, resolução maior, mais aumentos de dados | 2 a 4 h | os terminais (AP50 0,73 no inferior e caixas imprecisas no superior), que são as pontas da medida |
| RF-DETR com máscara (segmentação), usando como rótulo as máscaras do SAM 2 revisadas | 3 a 4 h | contorno direto no detector, sem o SAM em tempo de execução |

Ajustar o próprio SAM 2 aos termogramas não cabe nos 4 GB da placa com folga; e o SAM não é o gargalo enquanto
os rótulos forem poucos.

Risco: o PyTorch com CUDA é barrado pelo Controle Inteligente de Aplicativos de vez em quando. O treino de 30/09
rodou aqui, mas se for barrado, o Colab faz o mesmo treino.

## 6. Ordem de trabalho

1. **Correção imediata:**
   - tirar a medida feita pela tabela de alturas e pela distância de 10 m da tela e do laudo;
   - medir pelo eixo da peça e na grade térmica;
   - sem referência, mostrar só proporções.
2. **Ferramenta de referência** na Análise (linha e tamanho, mais o catálogo de componentes), com a incerteza.
3. **Contorno:** instalar o SAM 2 (pedir antes de baixar), comparar com o corte por temperatura em 30 máscaras à
   mão e ficar com o melhor; exportar para ONNX se for o SAM.
4. **Campanha de validação** (seção 4), com fotos tiradas por você.
5. **Dados e a noite de treino** (seção 5), quando houver fotos rotuladas de outros equipamentos.
6. **Classificação do DINOv2:** sair dos desenhos sintéticos. Ou usar protótipos tirados das peças rotuladas,
   ou deixar a identificação só com o RF-DETR.
