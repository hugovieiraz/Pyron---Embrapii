# Relatório do gabarito: medição em foto comum (26/10/2026)

Gerado por `python -m ml.avaliar_medicao --modelos vits vitb vitl` na nuvem (CPU de 4 núcleos, sem placa de vídeo),
com as 6 fotos de `testes/gabarito/` (≈ 900 × 1600, comprimidas, sem EXIF) e o SAM 2.1 small. Abaixo, a saída
completa (`saida/medicao/relatorio.md`). "Calibrado pela câmera" = fator mediano real/estimado das outras fotos.
Nenhuma foto tem duas referências juntas: o modo "com referência" ainda não foi medido em foto real.

Conclusões (detalhe no Registro de `docs/07_roteiro_medicao_geral.md`):
- ViT-L é o melhor: erro mediano 19 % (ViT-B 28 %, ViT-S 47 %); ponto e caixa dão o mesmo (o clique basta);
- com o ambiente em volta (pessoa na sala, A4 na bancada, Kindle na mesa): −9 a +19 %;
- de perto sobre fundo liso (régua no forro, pote contra a parede, cartão pequeno): +40 a +188 %, sempre para
  mais (o modelo acha a cena mais longe);
- calibrar um fator por câmera piorou (o erro não é um fator constante); fixar a lente em 24 ou 26 mm
  equivalentes não mudou nada (18,5 a 19,8 % de erro mediano).

## Resumo por modelo e pista

| Modelo · pista | Modo | n | Erro mediano | Viés mediano | Intervalo de 95 % | Erro máximo |
|---|---|---|---|---|---|---|
| vits · ponto | sem referência | 9 | 46,8 % | 46,8 % | -15,7 a 161,9 % | 170,5 % |
| vits · ponto | calibrado pela câmera | 9 | 35,5 % | -11,7 % | -46,7 a 78,6 % | 84,4 % |
| vits · caixa | sem referência | 9 | 46,9 % | 46,9 % | -15,6 a 162,6 % | 170,7 % |
| vits · caixa | calibrado pela câmera | 9 | 35,4 % | -11,5 % | -46,6 a 79,1 % | 84,6 % |
| vitb · ponto | sem referência | 9 | 27,6 % | 27,6 % | -12,0 a 369,8 % | 425,6 % |
| vitb · ponto | calibrado pela câmera | 9 | 39,8 % | -23,6 % | -45,1 a 277,2 % | 322,0 % |
| vitb · caixa | sem referência | 9 | 27,8 % | 27,8 % | -12,0 a 370,6 % | 426,0 % |
| vitb · caixa | calibrado pela câmera | 9 | 39,8 % | -23,4 % | -45,0 a 277,6 % | 322,0 % |
| vitl · ponto | sem referência | 9 | 19,1 % | 19,1 % | -6,0 a 166,8 % | 188,1 % |
| vitl · ponto | calibrado pela câmera | 9 | 21,9 % | -14,8 % | -28,2 a 127,5 % | 145,7 % |
| vitl · caixa | sem referência | 9 | 19,2 % | 19,2 % | -6,0 a 167,2 % | 188,3 % |
| vitl · caixa | calibrado pela câmera | 9 | 21,7 % | -14,5 % | -28,2 a 127,9 % | 145,8 % |

Tempo mediano por medição (ms): vits · ponto: 11193, vits · caixa: 777, vitb · ponto: 12898, vitb · caixa: 731, vitl · ponto: 17239, vitl · caixa: 956

## Por foto

| Foto | Medida | Real (cm) | Modelo · pista | Forma | Sem ref. (cm) | ± | Erro | Calibrado (cm) | Erro | Com ref. (cm) | Erro |
|---|---|---|---|---|---|---|---|---|---|---|---|
| a4_mesa.jpg | comprimento | 29,70 | vits · ponto | plano | 43,61 | 4,53 | +46,8 % | 26,22 | -11,7 % | — | — |
| a4_mesa.jpg | largura | 21,00 | vits · ponto | plano | 30,76 | 3,24 | +46,5 % | 18,50 | -11,9 % | — | — |
| a4_mesa.jpg | comprimento | 29,70 | vits · caixa | plano | 43,63 | 4,53 | +46,9 % | 26,29 | -11,5 % | — | — |
| a4_mesa.jpg | largura | 21,00 | vits · caixa | plano | 30,74 | 3,24 | +46,4 % | 18,53 | -11,8 % | — | — |
| cartao_mesa.jpg | comprimento | 8,56 | vits · ponto | plano | 14,24 | 1,52 | +66,4 % | 9,72 | +13,6 % | — | — |
| cartao_mesa.jpg | largura | 5,40 | vits · ponto | plano | 8,98 | 0,99 | +66,3 % | 6,13 | +13,5 % | — | — |
| cartao_mesa.jpg | comprimento | 8,56 | vits · caixa | plano | 14,25 | 1,52 | +66,5 % | 9,73 | +13,7 % | — | — |
| cartao_mesa.jpg | largura | 5,40 | vits · caixa | plano | 8,96 | 0,99 | +65,9 % | 6,12 | +13,3 % | — | — |
| regua_30cm.jpg | comprimento | 30,00 | vits · ponto | plano | 81,14 | 8,22 | +170,5 % | 55,33 | +84,4 % | — | — |
| regua_30cm.jpg | comprimento | 30,00 | vits · caixa | plano | 81,20 | 8,23 | +170,7 % | 55,37 | +84,6 % | — | — |
| pessoa_em_pe.jpg | altura | 183,00 | vits · ponto | volume | 146,80 | 15,00 | -19,8 % | 94,13 | -48,6 % | — | — |
| pessoa_em_pe.jpg | altura | 183,00 | vits · caixa | volume | 146,97 | 15,01 | -19,7 % | 94,31 | -48,5 % | — | — |
| pote_fox.jpg | altura | 3,50 | vits · ponto | volume | 7,97 | 0,86 | +127,7 % | 5,43 | +55,1 % | — | — |
| pote_fox.jpg | altura | 3,50 | vits · caixa | volume | 8,06 | 0,87 | +130,3 % | 5,50 | +57,1 % | — | — |
| kindle_capa.jpg | comprimento | 17,40 | vits · ponto | volume | 17,51 | 1,84 | +0,6 % | 10,53 | -39,5 % | — | — |
| kindle_capa.jpg | largura | 12,50 | vits · ponto | volume | 13,40 | 1,43 | +7,2 % | 8,06 | -35,5 % | — | — |
| kindle_capa.jpg | comprimento | 17,40 | vits · caixa | volume | 17,51 | 1,84 | +0,6 % | 10,55 | -39,4 % | — | — |
| kindle_capa.jpg | largura | 12,50 | vits · caixa | volume | 13,41 | 1,43 | +7,3 % | 8,08 | -35,4 % | — | — |
| a4_mesa.jpg | comprimento | 29,70 | vitb · ponto | volume | 27,18 | 2,83 | -8,5 % | 16,27 | -45,2 % | — | — |
| a4_mesa.jpg | largura | 21,00 | vitb · ponto | volume | 19,46 | 2,05 | -7,3 % | 11,65 | -44,5 % | — | — |
| a4_mesa.jpg | comprimento | 29,70 | vitb · caixa | volume | 27,18 | 2,83 | -8,5 % | 16,29 | -45,1 % | — | — |
| a4_mesa.jpg | largura | 21,00 | vitb · caixa | volume | 19,45 | 2,05 | -7,4 % | 11,66 | -44,5 % | — | — |
| cartao_mesa.jpg | comprimento | 8,56 | vitb · ponto | volume | 14,43 | 1,54 | +68,6 % | 11,86 | +38,6 % | — | — |
| cartao_mesa.jpg | largura | 5,40 | vitb · ponto | volume | 9,02 | 1,00 | +67,0 % | 7,41 | +37,2 % | — | — |
| cartao_mesa.jpg | comprimento | 8,56 | vitb · caixa | volume | 14,43 | 1,54 | +68,6 % | 11,87 | +38,7 % | — | — |
| cartao_mesa.jpg | largura | 5,40 | vitb · caixa | volume | 9,01 | 1,00 | +66,8 % | 7,41 | +37,2 % | — | — |
| regua_30cm.jpg | comprimento | 30,00 | vitb · ponto | plano | 157,69 | 15,97 | +425,6 % | 126,59 | +322,0 % | — | — |
| regua_30cm.jpg | comprimento | 30,00 | vitb · caixa | plano | 157,79 | 15,98 | +426,0 % | 126,59 | +322,0 % | — | — |
| pessoa_em_pe.jpg | altura | 183,00 | vitb · ponto | volume | 159,47 | 16,32 | -12,9 % | 110,22 | -39,8 % | — | — |
| pessoa_em_pe.jpg | altura | 183,00 | vitb · caixa | volume | 159,37 | 16,31 | -12,9 % | 110,09 | -39,8 % | — | — |
| pote_fox.jpg | altura | 3,50 | vitb · ponto | volume | 8,63 | 0,93 | +146,6 % | 6,93 | +98,0 % | — | — |
| pote_fox.jpg | altura | 3,50 | vitb · caixa | volume | 8,72 | 0,94 | +149,1 % | 7,00 | +100,0 % | — | — |
| kindle_capa.jpg | comprimento | 17,40 | vitb · ponto | volume | 21,17 | 2,23 | +21,7 % | 12,67 | -27,2 % | — | — |
| kindle_capa.jpg | largura | 12,50 | vitb · ponto | volume | 15,95 | 1,71 | +27,6 % | 9,55 | -23,6 % | — | — |
| kindle_capa.jpg | comprimento | 17,40 | vitb · caixa | volume | 21,16 | 2,23 | +21,6 % | 12,68 | -27,1 % | — | — |
| kindle_capa.jpg | largura | 12,50 | vitb · caixa | volume | 15,98 | 1,71 | +27,8 % | 9,58 | -23,4 % | — | — |
| a4_mesa.jpg | comprimento | 29,70 | vitl · ponto | plano | 32,42 | 3,37 | +9,2 % | 23,19 | -21,9 % | — | — |
| a4_mesa.jpg | largura | 21,00 | vitl · ponto | plano | 22,59 | 2,38 | +7,6 % | 16,16 | -23,1 % | — | — |
| a4_mesa.jpg | comprimento | 29,70 | vitl · caixa | plano | 32,43 | 3,37 | +9,2 % | 23,26 | -21,7 % | — | — |
| a4_mesa.jpg | largura | 21,00 | vitl · caixa | plano | 22,59 | 2,38 | +7,6 % | 16,20 | -22,9 % | — | — |
| cartao_mesa.jpg | comprimento | 8,56 | vitl · ponto | volume | 12,02 | 1,28 | +40,4 % | 10,41 | +21,6 % | — | — |
| cartao_mesa.jpg | largura | 5,40 | vitl · ponto | volume | 7,55 | 0,83 | +39,8 % | 6,54 | +21,1 % | — | — |
| cartao_mesa.jpg | comprimento | 8,56 | vitl · caixa | volume | 12,02 | 1,28 | +40,4 % | 10,42 | +21,7 % | — | — |
| cartao_mesa.jpg | largura | 5,40 | vitl · caixa | volume | 7,53 | 0,83 | +39,4 % | 6,53 | +20,9 % | — | — |
| regua_30cm.jpg | comprimento | 30,00 | vitl · ponto | plano | 86,44 | 8,76 | +188,1 % | 73,70 | +145,7 % | — | — |
| regua_30cm.jpg | comprimento | 30,00 | vitl · caixa | plano | 86,49 | 8,76 | +188,3 % | 73,75 | +145,8 % | — | — |
| pessoa_em_pe.jpg | altura | 183,00 | vitl · ponto | volume | 165,92 | 16,97 | -9,3 % | 128,98 | -29,5 % | — | — |
| pessoa_em_pe.jpg | altura | 183,00 | vitl · caixa | volume | 165,70 | 16,95 | -9,4 % | 128,92 | -29,5 % | — | — |
| pote_fox.jpg | altura | 3,50 | vitl · ponto | volume | 6,35 | 0,68 | +81,4 % | 5,41 | +54,6 % | — | — |
| pote_fox.jpg | altura | 3,50 | vitl · caixa | volume | 6,40 | 0,69 | +82,9 % | 5,46 | +56,0 % | — | — |
| kindle_capa.jpg | comprimento | 17,40 | vitl · ponto | volume | 20,10 | 2,12 | +15,5 % | 14,38 | -17,4 % | — | — |
| kindle_capa.jpg | largura | 12,50 | vitl · ponto | volume | 14,89 | 1,59 | +19,1 % | 10,65 | -14,8 % | — | — |
| kindle_capa.jpg | comprimento | 17,40 | vitl · caixa | volume | 20,08 | 2,11 | +15,4 % | 14,40 | -17,2 % | — | — |
| kindle_capa.jpg | largura | 12,50 | vitl · caixa | volume | 14,90 | 1,59 | +19,2 % | 10,69 | -14,5 % | — | — |

## Tempos por etapa (ms)

| Foto | Modelo · pista | Etapas |
|---|---|---|
| a4_mesa.jpg | vits · ponto | profundidade 8058, contorno 4976, geometria 1354, total 14399 |
| a4_mesa.jpg | vits · caixa | profundidade 0, contorno 142, geometria 1318, total 1468 |
| cartao_mesa.jpg | vits · ponto | profundidade 8614, contorno 1950, geometria 611, total 11193 |
| cartao_mesa.jpg | vits · caixa | profundidade 0, contorno 56, geometria 633, total 698 |
| regua_30cm.jpg | vits · ponto | profundidade 7804, contorno 1412, geometria 1828, total 11060 |
| regua_30cm.jpg | vits · caixa | profundidade 0, contorno 185, geometria 1745, total 1941 |
| pessoa_em_pe.jpg | vits · ponto | profundidade 8676, contorno 1752, geometria 856, total 11294 |
| pessoa_em_pe.jpg | vits · caixa | profundidade 0, contorno 55, geometria 757, total 820 |
| pote_fox.jpg | vits · ponto | profundidade 7093, contorno 1462, geometria 720, total 9284 |
| pote_fox.jpg | vits · caixa | profundidade 0, contorno 54, geometria 607, total 668 |
| kindle_capa.jpg | vits · ponto | profundidade 7959, contorno 1638, geometria 900, total 10506 |
| kindle_capa.jpg | vits · caixa | profundidade 0, contorno 56, geometria 713, total 777 |
| a4_mesa.jpg | vitb · ponto | profundidade 10338, contorno 2037, geometria 1503, total 13887 |
| a4_mesa.jpg | vitb · caixa | profundidade 0, contorno 161, geometria 1492, total 1663 |
| cartao_mesa.jpg | vitb · ponto | profundidade 11573, contorno 1603, geometria 383, total 13570 |
| cartao_mesa.jpg | vitb · caixa | profundidade 0, contorno 59, geometria 418, total 485 |
| regua_30cm.jpg | vitb · ponto | profundidade 9174, contorno 1411, geometria 1542, total 12138 |
| regua_30cm.jpg | vitb · caixa | profundidade 0, contorno 102, geometria 1546, total 1658 |
| pessoa_em_pe.jpg | vitb · ponto | profundidade 9712, contorno 1642, geometria 869, total 12232 |
| pessoa_em_pe.jpg | vitb · caixa | profundidade 0, contorno 61, geometria 821, total 891 |
| pote_fox.jpg | vitb · ponto | profundidade 10508, contorno 1526, geometria 852, total 12898 |
| pote_fox.jpg | vitb · caixa | profundidade 0, contorno 65, geometria 657, total 731 |
| kindle_capa.jpg | vitb · ponto | profundidade 10057, contorno 1440, geometria 694, total 12200 |
| kindle_capa.jpg | vitb · caixa | profundidade 0, contorno 58, geometria 627, total 693 |
| a4_mesa.jpg | vitl · ponto | profundidade 14471, contorno 1463, geometria 1294, total 17239 |
| a4_mesa.jpg | vitl · caixa | profundidade 0, contorno 188, geometria 1371, total 1568 |
| cartao_mesa.jpg | vitl · ponto | profundidade 14032, contorno 1593, geometria 420, total 16053 |
| cartao_mesa.jpg | vitl · caixa | profundidade 0, contorno 62, geometria 407, total 478 |
| regua_30cm.jpg | vitl · ponto | profundidade 14985, contorno 1361, geometria 1682, total 18040 |
| regua_30cm.jpg | vitl · caixa | profundidade 0, contorno 142, geometria 1536, total 1691 |
| pessoa_em_pe.jpg | vitl · ponto | profundidade 13672, contorno 1659, geometria 839, total 16184 |
| pessoa_em_pe.jpg | vitl · caixa | profundidade 0, contorno 50, geometria 952, total 1010 |
| pote_fox.jpg | vitl · ponto | profundidade 15595, contorno 1601, geometria 695, total 17902 |
| pote_fox.jpg | vitl · caixa | profundidade 0, contorno 55, geometria 846, total 909 |
| kindle_capa.jpg | vitl · ponto | profundidade 15069, contorno 1585, geometria 873, total 17539 |
| kindle_capa.jpg | vitl · caixa | profundidade 0, contorno 63, geometria 883, total 956 |

Carregar os modelos (ms): carregar_vits_ms 2853, carregar_vitb_ms 1367, carregar_vitl_ms 10383
