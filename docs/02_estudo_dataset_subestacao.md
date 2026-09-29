# Estudo 1: aprender com o dataset público da subestação de 132 kV

> Versão 0.1, 29/09/2026. Uso só para estudo (licença CC BY-NC-SA 4.0). O objetivo é ver se o
> caminho funciona antes de ter imagens próprias. O modelo que for vendido não será treinado
> com estes dados.

**Dataset:** [ScienceDB 10185](https://doi.org/10.57760/sciencedb.10185). 895 imagens RGB de
640×480 na paleta arco-íris, da FLIR C5, com rótulo por pasta: disjuntor 203, trafo de potência 178,
para-raios 181, seccionadora 180, bobina de bloqueio 153. As imagens não são radiométricas; a barra
de cores de cada uma indica a faixa de temperatura.

## Parte A: temperatura a partir da paleta

Não precisa treinar uma rede para isso. É uma inversão direta, mais exata e verificável:

1. **Achar a barra de cores.** A posição é fixa na FLIR C5; mede-se uma vez e confirma-se automaticamente (faixa vertical com cores da paleta).
2. **Ler os limites da escala** (máximo e mínimo, em °C). Como a fonte é sempre a mesma, a leitura pode ser por comparação com modelos de dígitos, e usar OCR só se precisar.
3. **Montar a tabela cor → temperatura** percorrendo a barra de cima a baixo. Supõe-se escala linear, o que precisa ser conferido.
4. **Converter cada pixel:** buscar a cor mais próxima da barra no espaço CIELAB e interpolar a temperatura.
5. **Marcar pixels inválidos:** cor longe de qualquer cor da paleta indica texto, logotipo, contorno da câmera visível (MSX) ou artefato de JPEG. Esses pixels ficam fora das medidas.
6. **Estimar a incerteza** de cada pixel: passo da barra, compressão, distância à paleta.

**Resultado:** uma matriz de temperatura *estimada* por imagem, no mesmo formato que as câmeras
radiométricas vão gerar. Todo o código seguinte serve para os dois casos.

**Validação:**
- **Ida e volta sintética:** pegar imagens radiométricas verdadeiras, pintá-las na paleta arco-íris com barra, comprimir em JPEG, inverter e comparar com a temperatura verdadeira.
- **Termômetro pontual:** se a imagem mostrar a leitura do ponto central (Sp1), comparar com o valor recuperado naquele pixel.
- **Meta:** erro mediano ≤ 1 °C, ou ≤ 2% da faixa, nas regiões válidas.

**Limites:** a temperatura exibida já vem com a emissividade que a câmera usou (desconhecida,
provavelmente 0,95) e com a resolução nativa de 160×120 da C5, ampliada para 640×480.

## Parte B: localizar componentes

1. **Guia de anotação.** Classes: bucha AT, bucha BT, conexão/terminal, tanque, radiador, conservador, comutador, para-raios, ventilador. Diz como desenhar cada uma e o que fazer com partes escondidas.
2. **Anotar com ajuda.** Label Studio + SAM 2: clica-se no objeto e a máscara sai pronta. Prioridade para as 178 imagens de trafo. Nas outras 717, anotar só conexões e isoladores, que aparecem em todos os equipamentos e aumentam a classe mais importante.
3. **Entrada do modelo.** A matriz de temperatura normalizada, e não a imagem colorida. Assim o modelo não depende da paleta e funciona depois com câmeras radiométricas. Comparar com a imagem colorida como experimento.
4. **Modelo.** RF-DETR com segmentação, pré-treinado, com ajuste fino e aumento de dados (espelho, escala, recorte, deslocamento e escala da faixa de temperatura).
5. **Validação honesta.** Separar treino e teste por equipamento físico ou sessão, não por imagem; fotos do mesmo equipamento em horários diferentes são quase duplicadas. Sem identificador, agrupar por semelhança.
6. **Métricas.**
   - mAP50 por classe.
   - A que importa para o produto: a diferença entre a temperatura máxima dentro da máscara prevista e dentro da máscara anotada.

**Expectativa:** tanque e radiadores fáceis, buchas médias, conexões difíceis (poucos pixels na
resolução nativa).

## Parte C: primeira demonstração de ponta a ponta

Imagem → temperatura estimada → componentes → temperatura de cada componente → ΔT entre fases
semelhantes → severidade por regra → laudo curto. É o núcleo do MVP, testado com dados reais.

## Passos

| # | Passo | Quem |
|---|---|---|
| 1 | Baixar (100,9 MB) e inspecionar: posição da barra, textos, MSX, duplicatas, quantos equipamentos distintos | Claude |
| 2 | Repositório, módulo de inversão de paleta e testes de ida e volta | Claude |
| 3 | Validar a inversão (meta ≤ 1 °C) e escrever o relatório | Claude |
| 4 | Guia de anotação, Label Studio + SAM 2 e pré-anotação | Claude |
| 5 | Anotar as 178 imagens de trafo (algumas horas com SAM 2) | Usuário, com revisão |
| 6 | Treinar o RF-DETR com separação por equipamento e medir | Claude |
| 7 | Demonstração de ponta a ponta com laudo | Claude |
| 8 | Câmera do LAT: modelo, se salva imagem radiométrica, fotos de trafos e conexões do laboratório. Serve para validar a inversão de paleta com verdade conhecida e para o primeiro teste com dado radiométrico real | Usuário |
