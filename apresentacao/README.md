# Pyron · Apresentação

Aplicativo separado e enxuto, para apresentar a identificação de para-raios por termografia. Só
quatro telas, sem alertas, severidade, laudos ou monitoramento:

- **Análise.** Galeria com as 27 fotos de teste (nunca vistas no treino) e envio de fotos da câmera
  (o JPEG original da FLIR, ou arrastar a foto para a janela). O modelo marca o para-raio, as saias
  e os terminais; em cada para-raio, o **ponto mais quente** aparece marcado na imagem,
  com o valor e a peça onde ele está, e a máxima de cada peça. Passando o mouse sobre a imagem, a
  temperatura daquele ponto. Foto sem dados radiométricos (print, foto de tela): só a identificação.
- **Modelo.** Como funciona em quatro etapas, ilustradas com uma foto de teste de verdade (foto →
  identificação → matriz de temperatura → ponto mais quente), a ficha do RF-DETR Medium e o treino
  (163 fotos, 1.183 peças marcadas, a divisão em treino, validação e teste).
- **Avaliação.** Os três detectores treinados no Colab (Faster R-CNN, YOLO26s, RF-DETR), cada um com
  acerto médio, precisão e revocação em destaque; o modelo deste aplicativo nas 27 fotos de teste
  (159 de 177 peças achadas, uma casinha por peça); o acerto por tipo de peça; as figuras do teste.
  A tabela completa fica em "Ver todos os números".
- **Câmera do celular.** Identificação em tempo real: **Ligar** mostra um QR code; o celular (na
  mesma rede Wi-Fi) abre a câmera apontada para a tela da câmera térmica e marca para-raio, saias e
  terminais com a temperatura máxima estimada pela barra de cores. O computador espelha o vídeo com
  as caixas. Nada é salvo (o botão de capturar não aparece). A temperatura pela barra é estimativa
  (~0,6 °C de erro na mediana); a da foto radiométrica, na aba Análise, é a medida.

A peça que o modelo chama de `aletas_isoladoras` aparece como **Saias** (o nome técnico das abas do
invólucro, IEC 60099-4). As figuras prontas da avaliação (PNG) ainda mostram o nome antigo.

## Abrir

Dois cliques no atalho **Pyron Apresentação** da área de trabalho. Ou, na pasta do projeto:

```bash
.venv/Scripts/python.exe -m apresentacao
```

A janela abre sozinha (Edge em modo aplicativo) e o servidor desliga quando ela fecha. Teclas
**1** a **4** trocam de aba. Para criar o atalho de novo: `.venv/Scripts/python.exe -m apresentacao.atalho`.
Diagnóstico: `-m apresentacao --sem-janela` sobe só o servidor; o endereço e erros vão para
`apresentacao/registro.log`.

## Por dentro

| Arquivo | O que faz |
|---|---|
| `analise.py` | Abre o JPEG da FLIR (imagem colorida + temperatura de cada ponto do sensor), chama o detector e acha o ponto mais quente dentro de cada para-raio |
| `detector.py` | O RF-DETR exportado em ONNX: na placa de vídeo pelo DirectML quando houver (~70 ms por foto), senão no processador (~400 ms) |
| `flir.py` | Leitor dos dados radiométricos da FLIR (cópia do `nucleo/flir.py` do Pyron) |
| `servidor.py` | FastAPI só com as rotas da apresentação, em 127.0.0.1; o modo celular abre um segundo servidor HTTPS na rede local só enquanto está ligado |
| `iniciar.py` | Sobe o servidor e abre a janela |
| `dados/avaliacao/` | Métricas e figuras da avaliação (tiradas de `app/dados_app/avaliacoes`) |

A análise de fotos não depende do resto do Pyron, para a apresentação não mudar quando o Pyron mudar.
A aba Câmera do celular reaproveita do Pyron o servidor do celular (`app/celular.py`, `app/estatico/celular.*`),
o recorte da tela da câmera (`nucleo/enquadrar.py`) e a leitura da barra de cores (`nucleo/barra.py`). O modelo
é lido de `modelos/para-raios-rfdetr-local-20260930-1627` (fora do git, 128 MB) e as fotos de teste,
do acervo em `dados/sciencedb_10185` (também fora do git); `PYRON_APRESENTACAO_MODELO` e
`PYRON_ACERVO` apontam para outras pastas. Tema claro só (projetor).

Fotos: Infrared Power Equipment Dataset (ScienceDB 10185, doi 10.57760/sciencedb.10185), licença
CC BY-NC-SA 4.0, uso não comercial.
