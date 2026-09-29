# Pesquisa: como a área trabalha, dados e ferramentas

> Versão 0.1, 28/09/2026. Varredura na internet para responder três perguntas:
> como os profissionais fazem manutenção preditiva por termografia, que dados existem para
> treinar e validar os modelos, e que ferramentas usar. O projeto começa do zero; nada do
> trabalho anterior (curto entre espiras) é reaproveitado.

---

## 1. Como os profissionais trabalham

### 1.1 Normas e obrigações

| Referência | O que diz | Consequência para o produto |
|---|---|---|
| **NFPA 70B:2023** (EUA) | Deixou de ser recomendação e virou norma. Exige termografia de **todos** os equipamentos elétricos pelo menos a cada 12 meses; equipamento em condição física 3, a cada 6 meses. A seção 7.4 pede ΔT entre componentes semelhantes sob carga semelhante e ΔT contra o ar ambiente | Mercado garantido de inspeções periódicas; o laudo deve trazer exatamente esses dois ΔT |
| **ASTM E1934** | Guia de inspeção de equipamentos elétricos e mecânicos. Define responsabilidades do usuário final e do termografista. Exceções quentes vêm de aumento de resistência (conexão frouxa ou deteriorada), curto, sobrecarga, desequilíbrio ou componente defeituoso; exceções frias, de componente que falhou. A inspeção vale só para o instante da medição | Classificar achados em "quente" e "frio" desde o início; o produto não pode prometer que o equipamento está bom |
| **ABNT NBR 15572** | Guia brasileiro. Cada anomalia é documentada com termograma e foto lado a lado, temperatura medida, temperatura de referência, ΔT, carga no momento, emissividade, severidade e prazo de correção. A severidade segue o critério do próprio usuário | Esse é o conteúdo mínimo do laudo (REL-01) e o critério tem de ser configurável (ANA-02) |
| **ABNT NBR 15763** | Critérios para definir a periodicidade das inspeções termográficas em sistemas de potência | Recurso novo: sugerir a próxima inspeção de cada ativo pela condição dele |
| **Certificação ABENDI** (SNQC/END, alinhada à ISO 18436-7) | Níveis 1 a 3. O nível 1 coleta dados sob supervisão de nível 2 ou 3; o nível 1 tem 44 h de treinamento | Papéis no sistema: quem coleta, quem analisa, quem assina |

### 1.2 O fluxo de uma inspeção

É esse fluxo que o software precisa acelerar, passo a passo:

1. **Planejar a rota:** lista de ativos e histórico de achados.
2. **Conferir as condições:** carga suficiente, clima, horário (sol e vento atrapalham).
3. **Registrar os dados do equipamento:** fabricante e número de série; classe de resfriamento (ONAN/ONAF1/ONAF2); potência a 65 °C de elevação; posição e contador do comutador; temperaturas de óleo e enrolamento nos indicadores; nível de óleo; carga atual em kVA; temperatura ambiente.
4. **Capturar:** termograma e foto visível.
5. **Medir:** ajustar emissividade, temperatura refletida e distância.
6. **Comparar:** com a fase semelhante, com o ambiente, com o histórico e com a placa.
7. **Classificar:** severidade e prazo.
8. **Recomendar e emitir o laudo** (com ART no Brasil).
9. **Acompanhar:** reinspecionar depois do reparo e seguir a tendência.

Os passos 3, 6, 7 e 8 são os mais demorados e os mais automatizáveis.

### 1.3 O que eles olham no transformador

| Componente | Normal | Anormal e o que indica |
|---|---|---|
| **Radiadores** | Dentro de cerca de 10 °C do tanque principal, com gradiente de cerca de 10 °C de cima para baixo; tubos uniformes e acima do ambiente | Radiador ou tubo frio: válvula fechada, obstrução ou óleo baixo |
| **Comutador sob carga** | Compartimento **não** mais quente que o tanque principal | Mais quente: contatos degradados, óleo carbonizado, borra, umidade |
| **Buchas** | Conexão aparafusada no topo sem ponto quente; nível de óleo visível | Ponto quente na conexão; gradiente anormal de nível |
| **Tanque e fases** | Tanques de fase com carga equilibrada em temperaturas parecidas; temperatura compatível com a carga | Tanque quente para a carga: deficiência de resfriamento |
| **Ventiladores e bombas** | Funcionando no estágio correto | Parados quando deveriam estar ligados |

### 1.4 A correção de carga usada em campo

- **ΔT a plena carga = ΔT medido × (I nominal ÷ I medido)²**. Exemplo das fontes: 28 °C medidos a 60% da carga equivalem a 28 × (1 ÷ 0,6)² ≈ 78 °C a plena carga. Algumas referências usam expoente entre 1,6 e 2 em vez de 2.
- **Tmax corrigido** (derivado de fórmula da IEEE): Tmax,corr = (I medido ÷ I nominal)² × elevação nominal + ambiente. Serve para saber se o componente passa do limite quando a carga subir.
- **Vento e sol:** não encontrei regra de correção consolidada. Fica para a Fase 0, nas normas.

### 1.5 Como eles pensam "previsão": a curva P-F

- **P** é o ponto em que a falha em formação já é detectável; **F** é a falha funcional.
  O **intervalo P-F** é o tempo que sobra para agir.
- Técnica mais sensível move P para mais cedo. Uma das fontes compara uma caixa de engrenagens: a análise de óleo detecta o desgaste de 6 a 12 meses antes, e a câmera térmica só algumas semanas antes. A leitura cruzada de técnicas reduz falso positivo.
- **Consequências para nós:**
  1. A métrica que importa é a **antecedência do alerta dentro do intervalo P-F**, junto com a taxa de falso alarme.
  2. A periodicidade da inspeção precisa ser menor que o intervalo P-F. Por isso, o monitoramento contínuo antecipa mais que a inspeção anual.
  3. Fundir termografia com DGA e carga aumenta a antecedência. A fusão deixa de ser um extra e vira parte da proposta de valor.

### 1.6 Onde os transformadores falham

Levantamento da CIGRE (TB 642, WG A2.37): 964 falhas graves entre 1996 e 2010, em 56
concessionárias de 21 países, com taxa de falha abaixo de 1% ao ano.

| Local da falha | Parcela |
|---|---|
| Enrolamento | 37,7% |
| **Buchas** | **15,9%** (consequências graves: incêndio e explosão) |
| Núcleo e circuito magnético | 14,5% |
| **Comutador sob carga** | **9,4%** |
| Isolação | 9,4% |
| Tanque | 4,3% |

Leitura honesta: a câmera enxerga diretamente as buchas e o comutador, **cerca de um quarto**
das falhas graves, e parte das falhas de resfriamento. As de enrolamento e núcleo precisam de
DGA e de outros ensaios. O produto deve dizer isso claramente em vez de prometer cobrir tudo.

### 1.7 Gestão de ativos: índice de saúde

- **CIGRE TB 761** (avaliação de condição de transformadores): cinco passos para construir
  índices de avaliação. O primeiro é definir para que o índice serve; o uso mais comum é
  ranquear a frota e priorizar substituição. Combina DGA, qualidade do óleo, grau de
  polimerização do papel e umidade, e trata explicitamente a informação faltante.
- Revisão recente comparando índices convencionais e com ML: arXiv 2504.15310.
- **Consequência:** nosso índice de saúde segue essa estrutura, aceita dados faltantes e mostra
  quanto da nota vem de cada fonte.

### 1.8 Como é o monitoramento contínuo hoje

- **Câmeras fixas em subestação:** FLIR (A400/A700, AX8), Optris, Systems With Intelligence
  (TCAM2500), Southern States, MoviTHERM, FOTRIC. Monitoram transformadores, disjuntores,
  buchas, para-raios e seccionadoras; alarmam por limiar; guardam tendência; integram com
  SCADA, OSIsoft PI, GIS e gestão de ativos.
- **Plataformas de IA e laudo:** iFactory e Oxmaint anunciam classificação automática de
  severidade e ordens de serviço; GE Vernova tem inspeção visual automatizada. Os números de
  mercado que essas páginas citam (38% das inspeções com IA em 2025, mercado de US$ 4,8 bi)
  vêm de relatórios comerciais e não foram verificados.
- **Brasil:**
  - P&D ANEEL 021 (2001) obteve boa previsão da condição de para-raios por termografia.
  - P&D ANEEL 169 (2006) gerou software livre de processamento de termogramas de subestação.
  - Na PCH da Ceran, montaram uma câmera térmica em base giratória com 6 posições (seccionadoras,
    isoladores, para-raios, saída do trafo elevador, conectores). Dados de corrente, tensão e
    potência vêm via OPC. Uma rede neural pequena (5-5-1) estima a temperatura **esperada**. O
    alarme dispara quando o desvio passa de 15% em três inspeções seguidas ou quando a
    temperatura passa do limite do material; também comparam as fases (10%). **É a mesma ideia
    da nossa fonte B (esperado × medido)**, numa versão simples e sem incerteza.
- **Europa: RESISTO** (Espanha, Doñana; e-distribución/Endesa, Universidade de Granada, ATIS).
  É o sistema publicado mais parecido com o nosso e funciona **só com câmera**, sem dado de carga:
  - 20 câmeras térmicas fixas em 20 trafos de distribuição: Hikvision DS-2TD2137T-4/P (384×288, ±2 °C), Hikvision bi-espectral DS-2TD2628T-3/QA (256×192 térmico + 2688×1520 visível) e Sunell SN-TPC6401KT-F II (640×512). PCs industriais no local.
  - Uma imagem por minuto por cabo, ou a cada 5 min por 4G com VPN.
  - Nove regiões desenhadas à mão por câmera: 3 terminais e buchas de AT, 4 de BT, corpo do trafo e fundo (parede, usada como referência de ambiente). A temperatura de cada região é a média dos 5% de pixels mais quentes.
  - Segmentação automática (Otsu + MSER) mede o tamanho das regiões para detectar vegetação, intrusos e fogo.
  - Previsão: modelo autorregressivo por câmera, treinado nas últimas 24 h e retreinado a cada 12 h. O ciclo diário de temperatura ("curva de pato") faz o papel da carga. Alarme quando medido − previsto passa de 15 °C.
  - Resultado: erro de previsão de cerca de 0,6 a 0,8 °C em dados reais; um ano sintético com anomalias injetadas por balanço térmico teve quase todas detectadas e poucos falsos positivos.
  - **Limite:** retreinar sobre as últimas 24 h faz o modelo absorver uma degradação lenta. Ele pega o que muda em horas, não a conexão que piora ao longo de semanas. É esse o espaço do nosso produto.

---

## 2. Datasets

### 2.1 Imagens térmicas

| Dataset | O que tem | Uso no projeto | Licença |
|---|---|---|---|
| [Infrared Thermal Image Dataset of HV Electrical Power Equipment (ScienceDB)](https://www.scidb.cn/en/detail?dataSetId=e416c488169f484485ad7575dcfc43ce), espelhado no [Kaggle](https://www.kaggle.com/datasets/s3programmerlead/infrared-thermal-image-dataset/data) | FLIR C5, subestação de 132 kV (Nigéria), horários e cargas diferentes. 895 imagens (100,9 MB): disjuntor 203, **trafo de potência 178**, para-raios 181, seccionadora 180, bobina de bloqueio 153. **Imagens RGB de 640×480 na paleta arco-íris, não radiométricas**; rótulo só por pasta, sem caixas | Estudo e teste de código; **não pode treinar o modelo vendido** | **CC BY-NC-SA 4.0: proíbe uso comercial** |
| [Substation Equipment, 15 classes (Zenodo 7884270)](https://zenodo.org/records/7884270) e [Dataset Ninja](https://datasetninja.com/substation-equipment) | 1.660 imagens, 50.705 objetos anotados, 15 classes incluindo trafos e seccionadoras (provavelmente imagens visíveis; conferir) | Detector na foto visível pareada; pré-treino de componentes | Conferir |
| [InfraredSolarModules (Raptor Maps)](https://github.com/RaptorMaps/InfraredSolarModules) | 20.000 imagens de 24×40 px de módulos solares, 12 classes (11 anomalias + normal), captadas por avião e drone | Pré-treino de classificação de anomalia térmica; vertical solar no futuro | Conferir |
| [Roboflow Universe, conjuntos térmicos](https://universe.roboflow.com/search?q=class:thermal+camera) | Muitos conjuntos pequenos | Pré-treino | Varia |
| [Najafi *et al.*, trafo seco e motor (Mendeley)](https://data.mendeley.com/datasets/8mg8mkc7k5/3) | Bancada, 255 BMP não radiométricos + 45 máscaras de segmentação | Baixa prioridade: não é campo nem radiométrico | CC BY (conferir) |
| Conjuntos de artigos (500 imagens de robô de inspeção; FLIR T600 em várias subestações) | Buchas, TCs, TPs, para-raios, comutador | Seriam ótimos, mas não estão públicos | Pedir aos autores |

### 2.2 Séries temporais e operação

| Dataset | O que tem | Uso no projeto | Licença |
|---|---|---|---|
| [ETDataset (ETT)](https://github.com/zhouhaoyi/ETDataset) | Temperatura do óleo + 6 variáveis de carga de transformadores na China, a cada 15 min e a cada hora, por 2 anos (70.080 pontos por série). ETT-small: 2 trafos; o README cita um ETT-large com 39 trafos (conferir se está publicado) | Calibrar e testar o gêmeo térmico e a previsão de temperatura **antes** de ter dados próprios | Conferir no repositório |
| [Temperaturas de trafo na subestação grega do projeto R2D2 (Zenodo 17085011)](https://zenodo.org/records/17085011) | Só uma tabela, sem imagens: `time;max;min;mean;difference`. Parte lida: de 31/01/2025 a 18/06/2025, em sessões curtas com uma linha a cada 16 a 17 s. Câmera, regiões e amostragem não são documentadas. O mínimo chega a −57 °C (céu no quadro), então as estatísticas são do quadro inteiro, não de um componente. A coluna `difference` não bate com a descrição | **Fraco.** No máximo, serve para ver o ruído de uma câmera fixa ao longo de minutos | CC BY 4.0 |
| [DGA dataset (IEEE DataPort)](https://ieee-dataport.org/documents/dga-dataset) | Treino balanceado, teste com dados reais e o benchmark IEC TC 10; gases H2, CH4, C2H6, C2H4, C2H2 com classe de falha | Módulo de DGA no índice de saúde | Conferir |
| [Power transformer data for fault diagnosis (Mendeley)](https://data.mendeley.com/datasets/98f4z3f8tx/2) | Dados para diagnóstico de falha de trafo | Conferir conteúdo | Conferir |
| [Distribution transformers, Cauca, Colômbia (Mendeley)](https://data.mendeley.com/datasets/yzyj46xpmy/4) ([artigo](https://ncbi.nlm.nih.gov/pmc/articles/PMC8521452)) | 16.000 trafos de distribuição, 2019 e 2020, taxa de queima, potência, usuários, energia não suprida, variáveis de instalação | Modelo de risco de frota e priorização (sem imagem) | Conferir |
| [Data-driven predictive maintenance of distribution transformers (IEEE DataPort)](https://ieee-dataport.org/documents/data-driven-predictive-maintenance-distribution-transformers) | Manutenção preditiva de trafos de distribuição | Conferir conteúdo | Conferir |

### 2.3 O que continua faltando

Nenhum conjunto público junta **imagens do mesmo equipamento ao longo do tempo, com carga e
desfecho**. A pesquisa confirma o plano: bancada própria, histórico de parceiros e dados sintéticos.
O ETT permite começar a estudar a dinâmica térmica antes da bancada ficar pronta. O método de
dados sintéticos do RESISTO (curvas diárias reais escaladas pelo clima + anomalias por balanço
térmico) é um bom ponto de partida para o nosso gerador.

---

## 3. Ferramentas

### 3.1 Ler temperatura das imagens

| Ferramenta | Faz | Observação |
|---|---|---|
| **exiftool** | Extrai o bruto do sensor e as constantes de Planck embutidas no R-JPEG da FLIR | Base de quase todas as bibliotecas abaixo |
| [flirpy](https://github.com/kengregson/flirpy) | Formatos FLIR (seq, fff, tmc), captura de câmeras FLIR (Lepton, Boson), conversão de bruto em temperatura | Conferir licença |
| [FlirImageExtractor](https://github.com/ITVRoC/FlirImageExtractor) / [read_thermal.py](https://github.com/Nervengift/read_thermal.py) | Temperatura por pixel e foto visível de R-JPEG FLIR, via exiftool | Conversão portada do pacote R Thermimage |
| [Thermimage (R)](https://rdrr.io/github/gtatters/Thermimage/man/readflirJPG.html) | Referência das fórmulas de conversão | Útil para validar nossa implementação |
| [thermal_parser](https://github.com/SanNianYiSi/thermal_parser) | R-JPEG DJI (H20T, XT2, M2EA, M3T, M30T, M4T) para matriz NumPy | Principal candidato para drones |
| [DJI Thermal SDK (pacote Python)](https://pypi.org/project/dji-thermal-sdk/) | Processa R-JPEG com o SDK oficial | O próprio pacote avisa que falha no Linux |
| [Drone-Thermal](https://github.com/torkian/Drone-Thermal) | R-JPEG de DJI, FLIR, Skydio, Autel etc. para CSV por pixel | Boa referência de formatos |

### 3.2 Capturar de câmeras

| Câmera | Integração | Ferramenta |
|---|---|---|
| **FLIR A400/A500/A700** (fixa) | REST API com imagem radiométrica; RTSP; GigE Vision; Modbus TCP; MQTT; EtherNet/IP; ONVIF opcional | [Spinnaker SDK](https://www.flir.com/instruments/a-series-integrator-page/) (gratuito, Python) e [guia da REST API](https://flir.custhelp.com/app/answers/detail/a_id/3602/~/getting-started-using-rest-api-with-automation-cameras) |
| **Hikvision** termográfica (fixa, mais barata) | ISAPI via HTTP: `/ISAPI/Thermal/channels/<id>/thermometry/jpegPicWithAppendData` devolve imagem térmica, visível e **matriz de temperatura em °C** | [hiktemp](https://github.com/xynogen/hiktemp), [hikvision-thermal-parser](https://github.com/MaomaoMAo-17/hikvision-thermal-parser) (só requests + numpy, sem SDK) |
| **TOPDON TC001 / InfiRay P2 Pro** (USB, protótipo) | Quadros brutos por UVC, formato obtido por engenharia reversa | [PyThermalCamera](https://github.com/leswright1977/PyThermalCamera), [versão Windows](https://github.com/m-riley04/PyThermalCamera-Windows), [P2Pro-Viewer](https://github.com/LeoDJ/P2Pro-Viewer) |
| **FLIR Lepton** (módulo, bancada) | Radiométrico via PureThermal | flirpy |

Achado útil: câmeras Hikvision entregam a matriz de temperatura por HTTP simples. Isso barateia
muito o kit de monitoramento contínuo em relação às FLIR da série A.

### 3.3 Visão computacional

| Ferramenta | Papel | Licença |
|---|---|---|
| [RF-DETR (Roboflow)](https://github.com/roboflow/rf-detr) | Detecção e segmentação de instâncias em tempo real, backbone DINOv2, feito para ajuste fino. Primeiro modelo em tempo real acima de 60 AP no COCO | **Apache 2.0** nos tamanhos Nano a Large; XL e 2XL em PML 1.0. **Candidato principal** |
| RT-DETR, D-FINE, YOLOX | Alternativas | Apache 2.0 |
| Ultralytics YOLO | Evitar | AGPL-3.0: exige licença paga em produto fechado |
| [anomalib (Intel)](https://github.com/open-edge-platform/anomalib) | Detecção de anomalia treinada **só com imagens normais** (PatchCore e outros) | Apache 2.0. **Resolve a falta de exemplos de defeito:** aprende o normal de cada componente |
| Label Studio, CVAT + SAM 2 | Anotação com máscara assistida | Apache 2.0 / MIT / Apache 2.0 |

### 3.4 Física do transformador e previsão

| Ferramenta | Papel | Licença |
|---|---|---|
| [transformer-thermal-model (Alliander)](https://github.com/alliander-opensource/transformer-thermal-model) | Implementação da IEC 60076-7: temperatura de topo do óleo e ponto quente a partir de dados de placa (perdas em carga e em vazio, potência nominal), perfil de carga e perfil de ambiente. Trafos de potência, de distribuição e de três enrolamentos; ONAN e ONAF; envelhecimento. `pip install transformer-thermal-model` | **MPL 2.0**: pode ser usado em produto fechado; mudanças nos arquivos da própria biblioteca precisam ser publicadas. **É a base do nosso gêmeo térmico** |
| ruptures | Detecção de ponto de mudança no resíduo medido − esperado | BSD |
| statsforecast / darts | Previsão de séries | Apache 2.0 |
| PyOD | Detecção de anomalia em séries e tabelas | BSD |
| lifelines | Sobrevivência (probabilidade de falha na frota) | MIT |
| scikit-survival | Evitar em produto fechado | GPL-3.0 |

### 3.5 Modelo de degradação de conexões

O [artigo da MDPI Sensors (2021)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8198314/) estima a
vida remanescente de conectores de potência online:

- **Modelo de resistência por oxidação:** R(t) = R₀ (1 − t/tₘ)³ (1 + 2t/tₘ) / (1 + t/tₘ), onde R₀ é a resistência inicial e tₘ a vida máxima. Os parâmetros são ajustados por Nelder-Mead.
- **Critério de fim de vida:** o ponto de inflexão da curva, em t = 0,0482 tₘ, onde R = 1,395 R₀. A partir de +39,5% de resistência, a degradação acelera.
- **Ensaio:** 7 conectores Al-Cu de 120 mm², 140 ciclos térmicos pela IEC 61238-1-3 (120 °C, 330 a 380 A), amostragem a cada 6 s, cerca de 92 h.
- **Resultado:** erro total de previsão de 49,9 h, contra mais de 89 h do ARIMA, em 5 ms por cálculo.

**Como usar:** com corrente constante, a potência dissipada na conexão é I²R, e a elevação de
temperatura acompanha R de forma aproximada. Assim, o modelo pode ser reescrito em termos de
ΔT normalizado, que é o que a câmera mede. O critério de +39,5% vira um limiar físico de
"degradação acelerando", mais defensável que um limiar arbitrário. A bancada da F7 pode repetir
esse ensaio, filmando com a câmera.

### 3.6 Dados sintéticos

- Levantamento geral: [A Comprehensive Survey on Synthetic Infrared Image Synthesis (arXiv 2408.06868)](https://arxiv.org/html/2408.06868v2).
- Difusão condicionada para imagem térmica ([arXiv 2408.03748](https://arxiv.org/pdf/2408.03748), [ThermalDiff](https://www.sciencedirect.com/science/article/abs/pii/S1047320325001385)) e balanceamento de falhas em PV por difusão ([ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2590123026010492)).
- Modelos com física explícita (emissão própria, reflexão do entorno, transmissão atmosférica), como a V2IR-GAN.
- **Recomendação:** começar com injeção física simples de pontos quentes em imagens radiométricas reais (difusão térmica 2D), que é controlável e tem verdade conhecida. Difusão generativa fica para depois, se faltar variedade.

### 3.7 Clima e DGA

- **Open-Meteo:** clima histórico e previsão por coordenada. O plano gratuito é para uso não comercial; conferir os termos antes de vender.
- **INMET:** dados oficiais brasileiros, gratuitos.
- **DGA:** há implementações abertas dos métodos IEEE/IEC (Duval, razões), por exemplo [transformer-health-dga](https://github.com/AR0714/transformer-health-dga); conferir a licença antes de usar.

---

## 4. O que muda no plano

1. **Métrica central:** antecedência do alerta dentro do intervalo P-F, sempre junto com o falso alarme por ativo-ano.
2. **Motor de previsão:** a ideia "esperado × medido" já foi usada na Ceran. Nós a fazemos com o gêmeo IEC 60076-7 da Alliander no lugar de uma rede neural pequena, com incerteza calibrada e detecção de ponto de mudança.
3. **Conexões:** o modelo de degradação por oxidação, com o critério de +39,5% traduzido para ΔT, vira o primeiro modelo de tendência.
4. **Visão:** RF-DETR para achar componentes e anomalib para aprender o normal. Assim o modelo não depende de muitos exemplos de defeito.
5. **Dados para começar já:** ETT e R2D2 para o motor de previsão; ScienceDB para componentes; DGA do DataPort para fusão; Cauca para risco de frota.
6. **Formulário de campo:** o checklist do termografista (placa, classe de resfriamento, carga, comutador, nível de óleo, ambiente) vira o formulário do DAD-08.
7. **Periodicidade como recurso:** sugerir a próxima inspeção por condição (NBR 15763, NFPA 70B).
8. **Licenças a vigiar:** Open-Meteo (uso comercial), Alliander (MPL 2.0), scikit-survival (GPL), RF-DETR XL/2XL (PML).
9. **Posicionamento honesto:** a câmera cobre diretamente cerca de um quarto das falhas graves (buchas e comutador). O resto vem da fusão com DGA e carga.
10. **Visualização 3D do gêmeo:** fica para depois (Futuro), por decisão de 28/09/2026.
11. **Câmera como único sensor instalado** (decisão de 28/09/2026). A carga e a temperatura do óleo passam a ser dados opcionais: se o cliente já os tiver, melhoram o resultado. No modo só câmera:
    - a temperatura do topo do tanque e da entrada dos radiadores, medida pela câmera, faz o papel da temperatura do óleo;
    - fases semelhantes são comparadas entre si, sob a mesma carga;
    - a razão entre a elevação da conexão e a do condutor vizinho, que esquentam ambos com I², cancela aproximadamente a carga;
    - o ciclo diário serve de carga implícita, como no RESISTO;
    - o ambiente vem de uma região de fundo na imagem e de serviço de clima.

    O ETT continua útil para aprender a dinâmica da temperatura do óleo. Ele não tem coluna de temperatura ambiente.

---

## 5. Lacunas e próximos passos

- Ler NBR 15572, NBR 15763 e a tabela de ações da NETA MTS. As normas são pagas; ver acesso por biblioteca universitária.
- Baixar e abrir cada dataset da seção 2: tamanho real, formato (radiométrico ou não), anotações e licença.
- Encontrar regras de correção de vento e radiação solar.
- **Primeira prova técnica:** rodar o modelo da Alliander nos dados do ETT e medir o erro de previsão da temperatura do óleo. Não depende de câmera e pode ser feita já. O ETT não tem ambiente, então é preciso buscar a temperatura histórica da região ou assumir um perfil.
- Pedir aos autores os conjuntos de imagens de subestação que não estão públicos.

---

## Fontes

**Prática e normas**
- [Fluke: NFPA 70B e termografia](https://www.fluke.com/en-us/learn/blog/thermal-imaging/nfpa-70b-how-thermal-imaging-supports-electrical-equipment-maintenance)
- [TÜV SÜD: NFPA 70B 2023](https://www.tuvsud.com/en-us/resource-centre/blogs/risk-engineering/nfpa-70b-2023-new-standard-for-electrical-equipment-and-infrared-testing)
- [infraredtraining.com: NFPA 70B 2023](https://www.infraredtraining.com/en-US/home/resources/blog/nfpa-70b-2023-new-guidelines-for-electric-inspections/)
- [IRISS: NFPA 70B 2023](https://iriss.com/discover/blog/mandatory-inspections-navigating-the-shift-of-nfpa-70b-2023/)
- [FLIR: NFPA 70B 2023](https://www.flir.com/discover/industrial/nfpa-70b-2023-new-guidelines-for-electric-inspections/)
- [Assured NDT: inspeção anual obrigatória](https://www.assuredndt.com/post/nfpa-70b-2023-update-annual-infrared-thermography-inspections-now-required)
- [SDMyers: termografia vira padrão](https://www.sdmyers.com/about/news-events/infrared-thermography-becomes-standard-for-electrical-maintenance/)
- [ASTM E1934](https://www.astm.org/Standards/E1934.htm)
- [ABNT NBR 15572 (Target)](https://www.target.com.br/produtos/normas-tecnicas/40644/nbr15572-ensaios-nao-destrutivos-termografia-guia-para-inspecao-de-equipamentos-eletricos-e-mecanicos)
- [Token Engenharia: o que um laudo termográfico inclui](https://tokenengenharia.com.br/quanto-custa-laudo-termografico-eletrico-preco-e-o-que-inclui/)
- [ABENDI: certificação em termografia](https://www1.abendi.org.br/certficacao/termografia-tm/)
- [irinfo: inspeção termográfica de trafos de subestação](https://irinfo.org/articles/05-01-2018-conte)
- [irinfo: inspeção de trafos a óleo](https://irinfo.org/tip-of-week-alphabeta/ir-inspection-of-liquid-filled-transformers)
- [irinfo: fórmula Tmax corrigido](https://irinfo.org/tip-of-week-alphabeta/using-tmax-corrected-formula-to-prioritize-electrical-exceptions)
- [The Drone Life: termografia sob carga](https://thedronelifenj.com/under-load-thermography-inspection/)
- [EEP: guia de manutenção de trafos](https://electrical-engineering-portal.com/download-center/books-and-guides/power-substations/transformer-maintenance)
- [Fluke: curva P-F](https://www.fluke.com/en-us/learn/blog/predictive-maintenance/p-f-curve-stay-ahead-of-equipment-failure)
- [Reliability Magazine: curva P-F](https://reliamag.com/articles/what-is-a-p-f-curve/)
- [eMaint: curva P-F](https://www.emaint.com/resources/blog/p-f-curve-explained-definition-and-explanation)

**Falhas, condição e monitoramento**
- [CIGRE TB 642: Transformer reliability survey](https://www.e-cigre.org/publications/detail/642-transformer-reliability-survey.html)
- [Standardized survey of transformer reliability (WG A2.37)](https://www.researchgate.net/publication/321660440_Standardized_survey_of_transformer_reliability_On_behalf_of_CIGRE_WG_A237)
- [CIGRE Canadá: metodologia de avaliação de condição](https://cigre.ca/papers/2019/CIGRE-134.pdf)
- [TJ/H2b: aplicação de metodologias de avaliação de condição](https://tjh2b.com/white-papers/application-of-condition-assessment-methodologies-for-transformers/)
- [Revisão de índice de saúde e vida útil (arXiv 2504.15310)](https://arxiv.org/pdf/2504.15310)
- [RESISTO: anomalias térmicas em trafos (arXiv 2410.19800)](https://arxiv.org/abs/2410.19800)
- [R2D2 (CORDIS)](https://cordis.europa.eu/project/id/101075714/reporting), [R2D2 (Smart Energy)](https://www.smart-energy.com/industry-sectors/energy-grid-management/r2d2-project-to-improve-the-reliability-resilience-and-defence-of-europes-grid/), [site do projeto](https://r2d2project.eu/)
- [FLIR: câmeras fixas em subestação](https://www.flir.com/discover/instruments/electrical-mechanical/the-advantages-of-fixed-mount-thermal-imaging-cameras-for-power-substation-monitoring/)
- [Systems With Intelligence: TCAM2500](https://systemswithintelligence.com/tcam2500)
- [Southern States: monitoramento de ativos](https://www.southernstatesllc.com/products/grid-security-products/asset-monitoring)
- [MoviTHERM: monitoramento de subestação](https://movitherm.com/feeds/category/thermal-substation-monitoring)
- [Optris: subestação](https://optris.com/application/condition-monitoring/electrical-substation-monitoring-with-an-infrared-camera/)
- [FOTRIC: subestação](https://www.fotric.com/post/infrared-cameras-in-substation-monitoring)
- [iFactory: IA térmica em infraestrutura elétrica](https://ifactoryapp.com/industries/infrastructure-management/thermal-imaging-ai-electrical-infrastructure-inspection)
- [Oxmaint: inspeção termográfica](https://oxmaint.ai/article/thermographic-inspection-electrical)
- [GE Vernova: inspeção visual automatizada](https://www.gevernova.com/software/products/automated-visual-inspection)
- [O Setor Elétrico: inspeção termográfica inteligente (Ceran)](https://www.osetoreletrico.com.br/manutencao-preditiva-com-inspecao-termografica-inteligente-sistema-de-monitoramento-permite-a-realizacao-de-inspecoes-remotas-e-personalizadas-no-campo-de-visao-das-cameras-termograficas/)
- [Revista P&D ANEEL, 4ª edição](https://knbs.com.br/wp-content/uploads/2022/07/Revista-PeD-ANEEL-4-2011.pdf)
- [Vida remanescente de conectores de potência (MDPI Sensors 2021)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8198314/)

**Dados e ferramentas:** links nas tabelas das seções 2 e 3, mais [RF-DETR é livre para uso comercial](https://blog.roboflow.com/rf-detr-is-free-to-use-commercially/), [anomalib: PatchCore](https://anomalib.readthedocs.io/en/latest/markdown/guides/reference/models/image/patchcore.html) e [Alliander: Transformer Thermal Model](https://alliander-opensource.github.io/transformer-thermal-model/).
