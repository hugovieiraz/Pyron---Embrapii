# Modelos instalados

Cada subpasta desta pasta é um modelo treinado que o Pyron reconhece. Ao abrir a aba
**Modelos**, eles aparecem ao lado do detector de pontos quentes (a regra embutida); o botão
"Usar este modelo" define qual é aplicado às próximas análises.

## Estrutura de uma pasta de modelo

```
modelos/
  para-raios-rfdetr-v1/
    cartao.json     identidade, classes, entrada, métricas e limitações
    modelo.onnx     a rede já exportada, com o pós-processamento embutido
```

## `cartao.json`

```json
{
  "id": "para-raios-rfdetr-v1",
  "nome": "Para-raios (RF-DETR Nano)",
  "arquitetura": "RF-DETR Nano, backbone DINOv2",
  "versao": "1.0",
  "descricao": "Encontra para-raios e suas partes em termogramas de subestação.",
  "classes": ["para_raio", "terminal_superior", "isolador", "terminal_inferior"],
  "arquivo": "modelo.onnx",
  "entrada": {
    "largura": 384, "altura": 384,
    "t_min": -20.0, "t_max": 80.0,
    "media": [0.485, 0.456, 0.406], "desvio": [0.229, 0.224, 0.225]
  },
  "limiar_confianca": 0.4,
  "treino": {"imagens": 145, "dados": "ScienceDB 10185, rótulos próprios (CVAT)", "data": "2026-10-xx"},
  "metricas": {"mAP50 (teste)": 0.0, "erro Tmáx terminal (°C)": 0.0},
  "limitacoes": ["Treinado com uma única subestação e uma única câmera (FLIR C5)."]
}
```

## Contrato do `modelo.onnx`

Igual para qualquer arquitetura (RF-DETR, SSD MobileNet, YOLOX...):

- **Entrada `imagem`**: float32 `[1, 3, altura, largura]`. A temperatura (°C) é normalizada
  para 0..1 entre `t_min` e `t_max`, redimensionada, repetida nos 3 canais e padronizada com
  `media` e `desvio`.
- **Saídas**:
  - `caixas` `[1, N, 4]`: x0, y0, x1, y1 normalizados de 0 a 1;
  - `pontuacoes` `[1, N]`: confiança;
  - `classes` `[1, N]`: índice na lista `classes` do cartão.

O script de treino (a escrever quando os rótulos do CVAT chegarem) exporta o modelo já neste
formato. O teste `testes/test_detectores.py` monta um modelo mínimo que segue o contrato e
confere que o Pyron o reconhece e usa.

## Como um modelo nasce

1. **Rótulos**: caixas no CVAT, exportadas em COCO 1.0 (sem as imagens).
2. **Preparação**: cada rótulo é ligado à matriz de temperatura verdadeira da imagem
   (o dataset é radiométrico). O modelo aprende com a temperatura, não com a paleta de cores.
3. **Separação honesta**: treino e teste separados por sessão de captura, para que fotos
   quase iguais do mesmo equipamento não fiquem dos dois lados.
4. **Treino**: ajuste fino de um detector pré-treinado (RF-DETR com DINOv2, ou SSD com
   MobileNet para rodar leve em tempo real).
5. **Avaliação**: mAP no teste e, principalmente, o erro da temperatura máxima medida em cada
   componente em comparação com os rótulos.
6. **Exportação e instalação**: `modelo.onnx` + `cartao.json` numa pasta aqui.
