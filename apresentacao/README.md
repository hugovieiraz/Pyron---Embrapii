# Pyron · Apresentação

Aplicativo separado e enxuto, para apresentar a identificação de para-raios por termografia. Só
três telas, sem alertas, severidade, laudos, celular ou monitoramento:

- **Análise.** Galeria com as 27 fotos de teste (nunca vistas no treino) e envio de fotos da câmera
  (o JPEG original da FLIR, ou arrastar a foto para a janela). O modelo marca o para-raio, as aletas
  isoladoras e os terminais; em cada para-raio, o **ponto mais quente** aparece marcado na imagem,
  com o valor e a peça onde ele está, e a máxima de cada peça. Passando o mouse sobre a imagem, a
  temperatura daquele ponto. Foto sem dados radiométricos (print, foto de tela): só a identificação.
- **Modelo.** Como funciona (foto → identificação → temperatura → ponto mais quente), a ficha do
  RF-DETR Medium, os números do treino e as curvas de perda e de acerto na validação.
- **Avaliação.** O modelo usado nas 27 fotos de teste (159 de 177 peças, precisão 88,8%, revocação
  89,8%, erro da temperatura máxima 0,0 °C na mediana), a comparação dos três detectores treinados no
  Colab (Faster R-CNN, YOLO26s, RF-DETR), o acerto por peça e as figuras do teste.

## Abrir

Dois cliques no atalho **Pyron Apresentação** da área de trabalho. Ou, na pasta do projeto:

```bash
.venv/Scripts/python.exe -m apresentacao
```

A janela abre sozinha (Edge em modo aplicativo) e o servidor desliga quando ela fecha. Teclas
**1**, **2** e **3** trocam de aba. Para criar o atalho de novo: `.venv/Scripts/python.exe -m apresentacao.atalho`.
Diagnóstico: `-m apresentacao --sem-janela` sobe só o servidor; o endereço e erros vão para
`apresentacao/registro.log`.

## Por dentro

| Arquivo | O que faz |
|---|---|
| `analise.py` | Abre o JPEG da FLIR (imagem colorida + temperatura de cada ponto do sensor), chama o detector e acha o ponto mais quente dentro de cada para-raio |
| `detector.py` | O RF-DETR exportado em ONNX: na placa de vídeo pelo DirectML quando houver (~70 ms por foto), senão no processador (~400 ms) |
| `flir.py` | Leitor dos dados radiométricos da FLIR (cópia do `nucleo/flir.py` do Pyron) |
| `servidor.py` | FastAPI só com as rotas da apresentação, em 127.0.0.1 |
| `iniciar.py` | Sobe o servidor e abre a janela |
| `dados/avaliacao/` | Métricas e figuras da avaliação (tiradas de `app/dados_app/avaliacoes`) |

O código não depende do resto do Pyron, para a apresentação não mudar quando o Pyron mudar. O modelo
é lido de `modelos/para-raios-rfdetr-local-20260930-1627` (fora do git, 128 MB) e as fotos de teste,
do acervo em `dados/sciencedb_10185` (também fora do git); `PYRON_APRESENTACAO_MODELO` e
`PYRON_ACERVO` apontam para outras pastas. Tema claro só (projetor).

Fotos: Infrared Power Equipment Dataset (ScienceDB 10185, doi 10.57760/sciencedb.10185), licença
CC BY-NC-SA 4.0, uso não comercial.
