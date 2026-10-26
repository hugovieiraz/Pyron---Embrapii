# Relatório: fotos do Hugo com post-it (26/10/2026)

Fotos do Galaxy S23 (HEIC, 1848 × 4000, com EXIF), 31 fotos de objeto (A4, cartão, pote Fox, Kindle, Hugo) e 5 só de post-it.
Post-it rosa achado sozinho pela cor (`nucleo/medicao/referencia_auto.py`), tamanho informado 8,0 cm. MoGe-2 ViT-L + SAM 2.1
small na CPU da nuvem; pista marcada à mão (ponto ou caixa) e conferida no contorno. As fotos ficaram fora do repositório
(têm GPS). Tipo da foto pelo nome: "ideal" (post-it perto e grande), "difícil" (ângulo e perspectiva) e "normal" (numeradas).

## Erro mediano (valor absoluto) por tipo de foto

| Fotos | Sem referência | Post-it + profundidade | Só o plano do post-it (homografia) |
|---|---|---|---|
| todas | 29,6 % (95 %: -13 a +128 %; n = 55) | 8,1 % (95 %: -49 a +19 %; n = 55) | 15,4 % (95 %: +2 a +858 %; n = 50) |
| normal | 19,5 % (95 %: -15 a +86 %; n = 34) | 8,1 % (95 %: -69 a +13 %; n = 34) | 12,5 % (95 %: +2 a +62 %; n = 31) |
| difícil | 69,9 % (95 %: -7 a +132 %; n = 14) | 7,8 % (95 %: -11 a +22 %; n = 14) | 122,2 % (95 %: +21 a +1567 %; n = 12) |
| ideal | 38,3 % (95 %: +2 a +129 %; n = 7) | 13,7 % (95 %: -15 a +5 %; n = 7) | 8,2 % (95 %: +5 a +16 %; n = 7) |

Lente: com a focal do EXIF ou com a estimada pelo modelo, o resultado é o mesmo (sem referência 29,6 % × 30,4 %;
com post-it 8,1 % × 8,2 %).

## Por objeto (lente do EXIF)

| Objeto | Sem referência | Post-it + profundidade | Plano do post-it |
|---|---|---|---|
| a4 | 4,7 % (95 %: -16 a +14 %; n = 14) | 4,0 % (95 %: -4 a +8 %; n = 14) | 13,3 % (95 %: +6 a +1526 %; n = 14) |
| cartao | 71,1 % (95 %: +27 a +128 %; n = 14) | 11,7 % (95 %: -14 a +20 %; n = 14) | 15,0 % (95 %: +5 a +410 %; n = 14) |
| fox | 61,4 % (95 %: -2 a +135 %; n = 8) | 11,2 % (95 %: -17 a +15 %; n = 8) | 19,5 % (95 %: +3 a +72 %; n = 6) |
| kindle | 35,2 % (95 %: +7 a +89 %; n = 16) | 7,7 % (95 %: -15 a +8 %; n = 16) | 15,2 % (95 %: +2 a +136 %; n = 16) |
| hugo | 3,1 % (95 %: -4 a -2 %; n = 3) | 66,3 % (95 %: -79 a +17 %; n = 3) | — |

## Depth Anything 3 Metric Large × MoGe-2 ViT-L (erro mediano)

DA3 Metric Large (Apache 2.0) instalado com a autorização do Hugo; só a rede, sem a API do pacote (que puxa o `evo`, GPL).
Profundidade em 2 s por foto na CPU (MoGe-2 ViT-L: 20 s).

| Fotos | Sem ref. MoGe-2 | Sem ref. DA3 | Post-it + MoGe-2 | Post-it + DA3 | Post-it + DA3 sem EXIF |
|---|---|---|---|---|---|
| Todas | 29,6 % | 19,8 % | 8,1 % | 5,1 % | 5,9 % |
| Normais | 19,5 % | 16,6 % | 8,1 % | 5,1 % | 4,7 % |
| Difíceis | 69,9 % | 38,0 % | 7,8 % | 5,9 % | 6,8 % |
| Ideais | 38,3 % | 56,8 % | 13,7 % | 4,8 % | 4,9 % |
| a4 | 4,7 % | 9,6 % | 4,0 % | 5,6 % | 5,1 % |
| cartao | 71,1 % | 62,7 % | 11,7 % | 3,7 % | 4,2 % |
| fox | 61,4 % | 60,4 % | 11,2 % | 24,4 % | 16,4 % |
| kindle | 35,2 % | 28,5 % | 7,7 % | 3,8 % | 4,3 % |
| hugo | 3,1 % | 7,2 % | 66,3 % | 76,8 % | 78,4 % |

A média geométrica dos dois modelos com post-it deu 6,1 % (não supera o DA3 sozinho). Sem EXIF (lente padrão de 65°)
o DA3 fica em 5,9 % com post-it e 22,4 % sem referência. Padrão do Pyron a partir daqui: DA3 quando instalado.

## Achados

- **Detecção do post-it sem treino:** 36 de 36 fotos, inclusive as difíceis e as de longe (50 a 70 px de lado); o cartão roxo
  (H ≈ 126 no HSV) não confunde com o post-it (H ≈ 155) nem o lençol azul (H ≈ 106). Não precisa treinar detector.
- **Sem referência, a escala depende do contexto:** o Hugo na sala sai com −2 a −4 %; objetos na cama lisa, de +25 a +137 %;
  o próprio post-it sozinho em close-up sai com 14 a 20 cm (real 8).
- **O post-it + profundidade é o modo robusto:** 8 % de erro mediano, inclusive nas fotos difíceis (7,8 %).
- **O plano do post-it só serve com o objeto no mesmo plano e a referência grande:** ótimo nas "ideais" (8,2 %), péssimo nas
  difíceis (122 %, com casos de +1789 %: post-it pequeno e muito inclinado não segura a perspectiva).
- **Post-it na mão, longe do objeto, não serve** (Hugo: −79 % e −66 %); na frente do corpo, +21 %.
- **Suspeita de tamanho do post-it:** pelo plano, quase tudo sai maior (+12,5 % na mediana das normais). Se o post-it tiver
  7,6 cm (o tamanho comercial de 3 polegadas) em vez de 8,0, esse viés cai para cerca de +7 %. Medir de novo.
- **Nas "ideais", a profundidade + post-it saiu 13 a 15 % para menos no cartão e no Kindle:** de muito perto, o MoGe-2 deforma o
  post-it em relação ao objeto. Ali o plano do post-it é melhor.

## Só o post-it, sem referência (o modelo medindo o post-it)

| Foto | Lado em px | Modelo, sem referência | Distância estimada |
|---|---|---|---|
| postit/20261026_114718 | 951 a 978 | 20,3 × 20,1 cm | 0,51 m |
| postit/20261026_114721 | 410 a 599 | 14,3 × 14,1 cm | 0,65 m |
| postit/20261026_114725 | 354 a 648 | 14,4 × 14,3 cm | 0,64 m |
| postit/20261026_114728 | 478 a 781 | 19,8 × 18,8 cm | 0,72 m |
| postit/20261026_114731 | 685 a 981 | 19,4 × 17,9 cm | 0,57 m |

Real: 8 × 8 cm. Em close-up da cama lisa, o MoGe-2 erra a escala 1,8 a 2,5 vezes; a detecção acerta o quadrado nas 5.

## Por foto (lente do EXIF)

| Foto | Tipo | Medida | Real (cm) | Sem ref. | Post-it + prof. | Plano do post-it |
|---|---|---|---|---|---|---|
| A4/20261026_114024.heic | normal | comprimento | 29,7 | +4,8 % | +2,3 % | +10,1 % |
| A4/20261026_114024.heic | normal | largura | 21,0 | -1,6 % | -4,0 % | +12,1 % |
| A4/20261026_114030.heic | normal | comprimento | 29,7 | -16,4 % | +5,6 % | +6,6 % |
| A4/20261026_114030.heic | normal | largura | 21,0 | -14,1 % | +8,5 % | +11,6 % |
| A4/20261026_114033.heic | normal | comprimento | 29,7 | -4,9 % | +1,2 % | +7,8 % |
| A4/20261026_114033.heic | normal | largura | 21,0 | +0,5 % | +7,0 % | +14,5 % |
| A4/20261026_114038.heic | normal | comprimento | 29,7 | +4,3 % | -1,5 % | +50,4 % |
| A4/20261026_114038.heic | normal | largura | 21,0 | +6,0 % | +0,1 % | +95,5 % |
| A4/dificil (2).heic | difícil | comprimento | 29,7 | +4,7 % | -4,0 % | +1788,5 % |
| A4/dificil (2).heic | difícil | largura | 21,0 | +17,1 % | +7,3 % | +981,8 % |
| A4/dificil.heic | difícil | comprimento | 29,7 | +0,1 % | +8,1 % | +76,9 % |
| A4/dificil.heic | difícil | largura | 21,0 | -11,1 % | -4,0 % | +118,1 % |
| A4/ideal.heic | ideal | comprimento | 29,7 | +1,5 % | +3,5 % | +5,9 % |
| A4/ideal.heic | ideal | largura | 21,0 | +3,2 % | +5,3 % | +6,4 % |
| CARTAO/20261026_114108.heic | normal | comprimento | 8,56 | +89,2 % | +8,2 % | +9,8 % |
| CARTAO/20261026_114108.heic | normal | largura | 5,4 | +84,8 % | +5,6 % | +5,4 % |
| CARTAO/20261026_114111.heic | normal | comprimento | 8,56 | +70,9 % | -13,1 % | +12,5 % |
| CARTAO/20261026_114111.heic | normal | largura | 5,4 | +73,5 % | -11,8 % | +17,4 % |
| CARTAO/20261026_114116.heic | normal | comprimento | 8,56 | +68,3 % | -13,8 % | +8,5 % |
| CARTAO/20261026_114116.heic | normal | largura | 5,4 | +70,4 % | -12,8 % | +12,4 % |
| CARTAO/20261026_114124.heic | normal | comprimento | 8,56 | +44,9 % | +10,4 % | +20,1 % |
| CARTAO/20261026_114124.heic | normal | largura | 5,4 | +46,3 % | +11,5 % | +23,5 % |
| CARTAO/dificil (2).heic | difícil | comprimento | 8,56 | +25,8 % | +1,9 % | +79,9 % |
| CARTAO/dificil (2).heic | difícil | largura | 5,4 | +29,6 % | +5,0 % | +68,2 % |
| CARTAO/dificil.heic | difícil | comprimento | 8,56 | +71,3 % | +7,6 % | +429,9 % |
| CARTAO/dificil.heic | difícil | largura | 5,4 | +98,0 % | +24,4 % | +367,4 % |
| CARTAO/ideal.heic | ideal | comprimento | 8,56 | +126,5 % | -14,7 % | +5,0 % |
| CARTAO/ideal.heic | ideal | largura | 5,4 | +128,9 % | -13,7 % | +10,7 % |
| FOX/20261026_113919.heic | normal | comprimento | 7,7 | +26,5 % | -17,7 % | +19,5 % |
| FOX/20261026_113922.heic | normal | comprimento | 7,7 | +11,0 % | +10,8 % | +19,6 % |
| FOX/20261026_113924.heic | normal | comprimento | 7,7 | -4,4 % | +8,4 % | +28,6 % |
| FOX/dificil (2).heic | difícil | comprimento | 7,7 | +68,6 % | -11,7 % | +78,4 % |
| FOX/dificil (2).heic | difícil | altura | 3,5 | +120,9 % | +15,7 % | — |
| FOX/dificil.heic | difícil | comprimento | 7,7 | +137,5 % | +14,0 % | +2,6 % |
| FOX/dificil.heic | difícil | altura | 3,5 | +88,3 % | -9,7 % | — |
| FOX/ideal.heic | ideal | comprimento | 7,7 | +54,3 % | -0,8 % | +8,2 % |
| HUGo/20261026_114515.heic | normal | altura | 183,0 | -3,1 % | -79,3 % | — |
| HUGo/20261026_114524.heic | normal | altura | 183,0 | -4,0 % | -66,3 % | — |
| HUGo/20261026_114533.heic | normal | altura | 183,0 | -1,6 % | +21,2 % | — |
| KINDLE/20261026_114207.heic | normal | comprimento | 17,4 | +39,6 % | +8,0 % | +14,0 % |
| KINDLE/20261026_114207.heic | normal | largura | 12,5 | +38,0 % | +6,7 % | +18,3 % |
| KINDLE/20261026_114210.heic | normal | comprimento | 17,4 | +22,5 % | +1,0 % | +2,2 % |
| KINDLE/20261026_114210.heic | normal | largura | 12,5 | +27,0 % | +4,7 % | +17,9 % |
| KINDLE/20261026_114212.heic | normal | comprimento | 17,4 | +30,3 % | +5,6 % | +5,0 % |
| KINDLE/20261026_114212.heic | normal | largura | 12,5 | +33,1 % | +7,9 % | +23,8 % |
| KINDLE/20261026_114215.heic | normal | comprimento | 17,4 | +15,0 % | -11,6 % | +5,3 % |
| KINDLE/20261026_114215.heic | normal | largura | 12,5 | +16,6 % | -10,3 % | +9,9 % |
| KINDLE/20261026_114217.heic | normal | comprimento | 17,4 | +6,3 % | +6,0 % | +1,5 % |
| KINDLE/20261026_114217.heic | normal | largura | 12,5 | +7,8 % | +7,5 % | +3,4 % |
| KINDLE/20261026_114226.heic | normal | comprimento | 17,4 | +84,4 % | -4,6 % | +24,7 % |
| KINDLE/20261026_114226.heic | normal | largura | 12,5 | +76,6 % | -8,6 % | +29,6 % |
| KINDLE/dificil.heic | difícil | comprimento | 17,4 | +77,5 % | +0,6 % | +126,3 % |
| KINDLE/dificil.heic | difícil | largura | 12,5 | +91,3 % | +8,5 % | +142,5 % |
| KINDLE/ideal.heic | ideal | comprimento | 17,4 | +37,4 % | -15,3 % | +14,1 % |
| KINDLE/ideal.heic | ideal | largura | 12,5 | +38,3 % | -14,7 % | +16,3 % |
