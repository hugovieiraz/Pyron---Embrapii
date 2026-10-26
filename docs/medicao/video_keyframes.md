# Medição 3D em Vídeo por Seleção de Keyframes e Consenso Multi-Frame

Data: 26/10/2026. Módulo: `nucleo/medicao/video_keyframes.py`.
API: `/api/medicao/video/keyframes` e `/api/medicao/video/medir`.

## 1. Motivação e Diagnóstico

Na medição por foto única monocular:
- Modelos como Depth Anything 3 (DA3) e MoGe-2 estimam a geometria a partir de uma perspectiva estática;
- O erro de uma foto única tem incerteza residual típica de 5% (com referência) a ~20% (sem referência em ambiente aberto);
- Ângulos oblíquos ou oclusões parciais podem degradar a delimitação do contorno (SAM 2.1).

Tentar rodar os modelos densos de profundidade em **todos os frames de vídeo em tempo real (30 FPS)** é inviável em hardware comum:
- MoGe-2 ViT-L ou DA3 levam entre centenas de milissegundos e vários segundos por inferência em placas como a GTX 1650 ou CPU;
- Vídeos gravados em movimento apresentam quadros com *motion blur* (borrão de movimento) e artefatos de compressão.

## 2. Abordagem de Keyframes Nítidos

Em vez de processar 30 quadros por segundo, o algoritmo:
1. **Amostra candidatos uniformemente no tempo** (~4 FPS);
2. **Calcula o índice de nitidez** por variância do Laplaciano:
   $$\text{Score} = \text{Var}(\nabla^2 I_{\text{cinza}})$$
   Quadros borrados por movimento ou fora de foco obtêm scores muito baixos (< 25-50) e são descartados;
3. **Garante diversidade de pose/ângulo:** divide a duração do vídeo em $K$ janelas temporais e seleciona o ápice de nitidez (*peak sharpness*) de cada intervalo;
4. **Propagação de Pista:** se o usuário forneceu a pista (ponto, dois pontos ou caixa) no primeiro keyframe, ela é transportada para os keyframes subsequentes por fluxo óptico piramidal de Lucas-Kanade com filtragem de mediana;
5. **Consenso e Redução de Incerteza:**
   - Para $N$ medições válidas em pontos de vista distintos, o erro padrão da estimativa é reduzido proporcionalmente a:
     $$\sigma_{\text{consenso}} \approx \frac{\sigma_{\text{individual}}}{\sqrt{N}}$$
   - O consenso consolida a mediana (robusta a eventuais *outliers*), desvio padrão e limites [mínimo, máximo].

## 3. Estrutura e Endpoints

- **`nucleo/medicao/video_keyframes.py`:**
  - `calcular_nitidez(imagem)`: variância do operador Laplaciano;
  - `selecionar_keyframes(origem, max_keyframes=5)`: extração e filtragem de quadros;
  - `propagar_pista(pista, img1, img2)`: rastreamento de pontos ou caixas entre quadros;
  - `agregar_medicoes(medidas)`: consolidação estatística com cálculo de redução de incerteza;
  - `medir_video(...)`: execução integrada.

- **Endpoints FastAPI (`app/servidor.py`):**
  - `POST /api/medicao/video/keyframes`: extrai e devolve os keyframes com prévias em JPEG base64 e métricas de nitidez;
  - `POST /api/medicao/video/medir`: executa a medição nos keyframes e devolve o consenso.
