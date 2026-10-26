# Mapa de escala: metodologia (26/10/2026)

Código: `nucleo/medicao/mapa_escala.py`. Testes: `testes/test_medicao_mapa_escala.py`. Os números abaixo vêm de fotos
sintéticas com verdade exata, renderizadas por uma câmera pinhole conhecida e degradadas como foto de celular
(desfoque, ruído e JPEG). **Ainda falta validar em foto real com a folha impressa.**

## 1. Traços ou pontos: medido

**O que se comparou:**
- **Traços:** a régua com traço a cada 1 mm. O período dos traços sai pela FFT, de forma automática, como no teste da
  foto real da régua.
- **Pontos:** os cantos de um xadrez ChArUco. Cada canto tem posição conhecida em mm, e a homografia liga a folha
  à foto.

**Condições do teste:** 2 qualidades de foto; 3 inclinações (0°, 35° e 50° + 25°); 1 cm valendo de 4 a 45 px.

| | Pontos (cantos ChArUco) | Traços (régua de 1 mm, FFT) |
|---|---|---|
| Foto de frente, 1 cm ≥ 20 px | erro < 0,05 % | 0 a 10 %, instável |
| Inclinada 35° a 50° | erro < 0,1 % quando acha | 10 a 40 %, trava no harmônico errado (5 mm ou 1 cm) |
| Foto ruim (desfoque e JPEG 60) | erro < 0,1 % com quadrado ≥ 20 px | falha quase sempre |
| Identifica o que cada marca é | sim (cada marcador tem número) | não (todo traço é igual) |

**Conclusão: medir pontos.**
- Um traço repetido não diz qual traço é qual. Com perspectiva ou desfoque, o período de 1 mm se confunde com os
  de 5 mm e de 1 cm.
- Na foto real da régua deu certo (cerca de 1 %) porque ela estava quase de frente (2°) e com 50 px/cm. Fora dessa
  condição, não se sustenta.
- Os cantos do xadrez são pontos de fração de pixel, e cada um tem número.

## 2. Tamanho viável

**O que decide é o lado do quadrado na foto, em pixels.** Abaixo, todas as poses, qualidades e câmeras juntas
(1200 × 1600, 3000 × 4000 e 640 × 480):

| Quadrado na foto | Folha achada | Erro de 1 cm, mediano (95 %) | Erro de 10 cm, mediano (95 %) |
|---|---|---|---|
| < 20 px | 0 % | — | — |
| 20 a 30 px | 25 % | 0,10 % (0,36 %) | 0,10 % (0,24 %) |
| 30 a 50 px | 62 % | 0,08 % (3,6 %) | 0,05 % (3,1 %) |
| **50 a 80 px** | **100 %** | **0,02 % (0,19 %)** | **0,02 % (0,12 %)** |
| ≥ 80 px | 100 % | 0,01 % (0,04 %) | 0,01 % (0,04 %) |

**Regra:** o quadrado precisa ter **pelo menos 50 px na foto**. Se tiver menos, o programa avisa ("chegue mais
perto"). Para escolher o tamanho da folha:

`lado do quadrado (mm) = 50 × distância (m) × 1000 / focal (px)`

| Câmera | Distância | Quadrado |
|---|---|---|
| 12 MP (focal ≈ 3000 px) | até 1,5 m | 25 mm (folha A4 padrão) |
| 12 MP | 3 m | 50 mm |
| 12 MP | 5 m | 85 mm (placa A3 ou maior) |
| foto de 1200 px de largura | até 0,6 m | 25 mm |

**A folha padrão** é uma A4 com 7 × 10 quadrados de 25 mm: cerca de 175 × 250 mm, que cabe com margem. Ela traz
uma régua de 100 mm para conferir a impressão.
- Depois de imprimir, **medir o quadrado com paquímetro** e informar o valor medido em `--quadrado`. Impressoras
  costumam escalar de 1 % a 3 %, e esse erro entra direto em todas as medidas.
- Para o campo, a folha precisa ser plana e rígida (colada em placa).

**As retas de 1 cm são o resultado do mapa, não a entrada.**
- O programa desenha um traço de 1 cm em cada direção a cada 25 mm da folha (um por canto de quadrado). O valor de
  cada traço sai da homografia, e não de medir o próprio traço.
- Medir um traço de 20 px clicando nas pontas teria cerca de 5 % de erro (1 px em cada ponta). Pela homografia, o
  erro fica abaixo de 0,2 %.

## 3. O que o programa faz sozinho

1. **Lê o tamanho da imagem** da própria foto, já virada pela orientação do EXIF. Testado em 640 × 480,
   1200 × 1600 e 3000 × 4000.
2. **Acha a folha** com o detector ChArUco do OpenCV e calcula a homografia (folha em mm para foto em px). O erro
   de reprojeção ficou entre 0,08 e 0,2 px.
3. **Monta o mapa de escala:** em cada ponto da grade, quantos px valem 1 cm nas duas direções da folha. A escala
   sai da derivada da homografia, e por isso é exata no plano inclinado.
4. **Calcula a distância** de cada ponto à câmera (`solvePnP`). Para isso precisa da lente, que vem de uma destas
   fontes:
   - **EXIF:** o caminho preferido.
   - **Focal informada.**
   - **Estimada pela própria folha:** só funciona com a folha inclinada. Medido: com a folha de frente, erro de
     85 %, e o programa avisa; inclinada 30° ou mais, 0,03 % a 0,08 %.
5. **Desenha** a foto com os traços de 1 cm, a escala e a distância de cada ponto, mais um cabeçalho com o tamanho
   da imagem, os cantos achados, o tamanho do quadrado, a reprojeção, a lente, a faixa de distância, a inclinação e
   os avisos.

## 4. Profundidade geral da cena

- **No plano da folha, o mapa é exato.** Fora dele, a profundidade continua vindo do MoGe-2, que acerta a forma (de
  1 % a 3 % nos objetos planos) e erra a escala.
- **Próximo passo:** usar os pontos da folha (distância conhecida em cada canto) para corrigir a escala do MoGe-2,
  com fator e inclinação ajustados nos cantos, e conferir o erro nos objetos fora do plano.
- Para cenas grandes (subestação, galpão), pôr **várias folhas ou placas** em profundidades diferentes. Cada uma
  dá um trecho de escala e a profundidade entre elas sai do modelo corrigido.

## 5. Para validar em foto real (a fazer)

1. Imprimir `saida/medicao/mapa_escala/folha_charuco_25mm.pdf` em 100 % (sem "ajustar à página"), medir o
   quadrado com paquímetro e colar a folha em papelão.
2. Fotografar, com o celular original e sem WhatsApp, objetos de medida conhecida ao lado da folha e no mesmo
   plano: de frente, inclinado 30° e inclinado 50°, a 0,3, 0,6 e 1 m. São cerca de 20 fotos.
3. Rodar `python -m nucleo.medicao.mapa_escala foto.jpg --quadrado <medido>` e comparar com a trena.
