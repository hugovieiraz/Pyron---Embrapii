# Revisão da metodologia de medição (26/10/2026)

Base: o gabarito de `testes/gabarito/` rodado na GTX 1650 (MoGe-2 ViT-L, SAM 2.1 small, objeto marcado por caixa,
sem referência; `saida/medicao/relatorio.json`), os relatórios `relatorio_gabarito.md` e `relatorio_postit.md` e o
código de `nucleo/medicao/`. Os números abaixo foram medidos, exceto onde está escrito "esperado".

## 1. Diagnóstico: o contorno e a forma estão certos; o erro é de escala

**Contorno:** a nota do SAM ficou entre 0,98 e 1,00 nas 6 fotos, e a régua foi conferida na imagem, de 0 a 30 cm.

**Forma:** a razão entre duas medidas da mesma foto não depende da escala, então ela isola o erro de forma.

| Foto | Razão real | Razão medida | Erro de forma | Fator de escala (medido / real) |
|---|---|---|---|---|
| A4 | 1,414 | 1,435 | +1,5 % | 1,09 |
| Cartão | 1,585 | 1,596 | +0,7 % | 1,40 |
| Kindle | 1,392 | 1,347 | −3,2 % | 1,15 a 1,19 |
| Pote (altura / diâmetro) | 0,455 | 0,585 | +28,7 % | 1,42 a 1,83 |

Nos objetos planos, a forma erra de 1 % a 3 %. O que erra é **um único fator de escala por foto**, que varia de 0,91
(pessoa) a 2,88 (régua). O pote é volume a 25 cm da câmera e erra também na forma.

**Origem da escala.** Sem referência, o MoGe-2 adivinha a distância a partir do "jeito" da cena: estimou a régua a
77 cm, o pote a 25 cm e o A4 a 53 cm. Em foto de perto sobre fundo liso, falta contexto e ele erra para longe, por
isso a medida sai sempre maior.

**Lente.** As 6 fotos do gabarito estão comprimidas e sem EXIF, então a lente também é estimada (de 19 a 30 mm
equivalentes). Nas fotos com EXIF do Hugo, usar a lente certa não mudou o erro (29,6 % contra 30,4 %). O problema
é a distância, não a lente.

**Consequência.** Nenhum ajuste do modelo resolve isso de verdade:
- Calibrar um fator por câmera piorou o resultado (deixando uma foto fora a cada vez), porque o fator muda de
  foto para foto.
- Ajustar o MoGe-2 em 6 fotos seria decorar o gabarito.
- Trocar o ViT-L por outro modelo monocular só troca o erro de lugar: medir a distância absoluta a partir de uma
  foto só é ambíguo por natureza.

## 2. Problemas na metodologia atual

1. **A incerteza não é honesta.** O "±" sem referência usa 20 % fixos e cobriu o valor real em só **5 de 10**
   medidas. Para 95 %, teria de cobrir cerca de 9 de 10.
2. **A avaliação é pequena demais para concluir.**
   - Gabarito: 6 fotos e 10 medidas, todas de um celular, sem EXIF e de um objeto cada.
   - Post-it: 36 fotos, com o tamanho do post-it em dúvida (7,6 ou 8,0 cm, um viés de 5 % que entra direto em
     todas as medidas).
   - Em nenhum dos dois há conjunto separado para ajustar e para testar.
3. **O "sem referência" aparece como medida.** Com um fator de 0,9 a 2,9, ele é uma ordem de grandeza, não uma
   medida.
4. **A referência é fraca.** O post-it é achado pela cor e tem cantos arredondados e tamanho incerto. Mesmo assim,
   já levou o erro mediano de 29,6 % para 8,1 %. A referência é o que funciona; dá para melhorá-la.
5. **O objetivo do Pyron é outro caso** (`docs/06_plano_medicao.md`). A térmica da FLIR C5 tem 160 × 120 pixels, e
   1 pixel em cada ponta já dá ±2,6 % no comprimento do para-raio e ±10 % na largura. Em subestação não dá para
   pôr post-it no equipamento energizado.

## 3. Metodologia proposta

Princípio: **a escala vem de algo medido, não do modelo.** O modelo entra só onde ele acerta, que é contorno e forma.

### A. Foto comum com marcador impresso (substitui o post-it)

- **Marcador:** ArUco ou ChArUco, impresso e medido com paquímetro depois da impressão. O OpenCV daqui já tem o
  `cv2.aruco` (5.0.0).
  - Os cantos são achados com precisão de fração de pixel e não dependem de cor nem de luz.
  - O `solvePnP` dá a distância e a inclinação do marcador. Com a lente do EXIF, ou com a calibração da câmera
    feita uma vez com o tabuleiro ChArUco, a escala fica fixa.
- **Objeto no plano do marcador:** a homografia que já existe em `plano_ref.py`. Esperado: menos de 1 %. O
  sintético deu menos de 0,2 %; falta medir em foto real.
- **Objeto fora do plano:** o MoGe-2 dá a forma relativa e o marcador dá a escala. Hoje já é assim com o post-it,
  mas com um fator só para a cena toda. Proposta: fixar a escala pela profundidade do marcador e conferir se a
  forma do próprio marcador sai quadrada. Se não sair, a foto é rejeitada em vez de dar um número errado.
- **Sem marcador:** a tela mostra "estimativa", com o intervalo medido na avaliação, e nunca como medida.

### B. Térmica em subestação (o caso do Pyron)

- **Escala pela física da câmera:**
  - tamanho = pixels × distância × 2·tan(FOV/2) / 160;
  - o FOV da FLIR C5 vem da ficha técnica (54° × 42°) e precisa ser conferido em bancada;
  - a distância é medida com trena a laser e digitada. Hoje o arquivo grava sempre 10 m, o valor padrão.
- **Limite:** o próprio pixel. Para medir melhor, a foto tem de ser de mais perto ou de câmera com mais resolução.
- **Conferência sem tocar no equipamento:**
  - medidas de catálogo do equipamento (para-raio e isolador por classe de tensão) servem de referência;
  - as três fases do mesmo equipamento têm de dar a mesma medida.

### C. Protocolo de avaliação (vale para A e B)

- **Fotos:** pelo menos 40 fotos originais (com EXIF), de 2 celulares, com 5 objetos a 3 distâncias e 2 ângulos,
  medidos com paquímetro ou trena.
- **Separação:** metade para ajustar (tamanho do marcador, limites de rejeição) e metade para teste, sem mexer
  depois de ver o teste.
- **Relatório:** erro mediano e de 95 % por modo, **cobertura do ±** (fração de casos em que o real cai dentro) e
  fotos rejeitadas.
- **Pronto quando**, no conjunto de teste:
  - modo marcador no plano com erro de 95 % abaixo de 2 %;
  - marcador fora do plano abaixo de 5 %;
  - cobertura do ± de pelo menos 90 %.

## 4. O que não fazer

- **Não ajustar o MoGe-2 nem calibrar um fator nas 6 fotos do gabarito.** Seria decorar o teste.
- **Não usar o "calibrado pela câmera".** Ele já piorou o resultado.
- **Não apresentar medida sem referência com ± de 20 %.** A cobertura medida foi de 50 %.
- **Não usar a distância gravada no arquivo térmico.** É sempre 10 m.
