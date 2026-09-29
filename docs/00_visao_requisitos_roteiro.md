# Pyron: visão, requisitos e roteiro

> Nome provisório. Versão 0.1, 28/09/2026. Documento-base do projeto: o que entendi da ideia,
> o que é tecnicamente possível, o que proponho e em que ordem fazer.

---

## 1. O que extraí da ideia

**Em uma frase:** um software comercial de manutenção preditiva de equipamentos elétricos
por termografia, começando por transformadores, que antecipa falhas em vez de só apontar
defeitos que já existem.

| Item | Entendimento |
|---|---|
| Núcleo | Modelo de ML treinado com imagens térmicas de transformadores |
| Objetivo do modelo | **Prever** a falha (antecipar), não apenas detectar o defeito atual |
| Escopo | Produto completo: integração com câmeras, processamento, interface, relatórios, software instalável ou em nuvem |
| Extras desejados | Gêmeo digital, LLM, integrações |
| Meta de negócio | Algo pronto para vender |
| Ritmo | Projeto paralelo, incremental, ao longo de alguns meses |

**Requisitos implícitos** (não foram ditos, mas o produto só vende se os tiver):

1. **Confiança de engenheiro.** Quem compra é técnico. Toda saída precisa mostrar de onde veio:
   imagem, região, valores, critério e grau de certeza. Uma caixa-preta não passa.
2. **Valor mensurável.** O comprador precisa enxergar o retorno: horas de laudo economizadas,
   falhas evitadas, compensações de DEC/FEC evitadas.
3. **Diferencial defensável.** Os softwares dos fabricantes de câmera já medem temperatura e
   fazem laudo. O diferencial tem de ser previsão, independência de marca e dados acumulados.
4. **Aceitação por TI/TO de concessionária.** Opção on-premises, segurança cibernética,
   nenhuma porta aberta na subestação.
5. **Responsabilidade técnica.** No Brasil, laudo é assinado por profissional habilitado (ART).
   O software prepara e recomenda; a pessoa decide e assina.

---

## 2. O ponto central: o que "prever" pode significar aqui

### 2.1 A limitação

Para treinar um modelo que prevê falha no sentido estrito, seriam necessárias imagens
térmicas de muitos equipamentos, tiradas ao longo do tempo, com a data em que cada um falhou.
**Esse conjunto não existe publicamente** (seção 4). Os datasets disponíveis servem para
detecção e classificação, não para previsão. Prometer "IA que prevê falhas" sem resolver isso
seria vender algo que não conseguimos validar.

### 2.2 Como contornar: quatro fontes de previsibilidade

Não precisamos de exemplos de falha para prever. Existem quatro caminhos que funcionam com
os dados que conseguimos obter:

| # | Fonte | Ideia | Dado necessário |
|---|---|---|---|
| A | **Tendência por componente** | Acompanhar o ΔT normalizado de cada ponto (ex.: conexão da bucha X1) ao longo do tempo e projetar quando cruza os limiares de severidade | Série temporal do mesmo componente |
| B | **Desvio do comportamento esperado** (gêmeo físico) | O modelo térmico da IEC 60076-7 / IEEE C57.91 diz quanto o trafo *deveria* esquentar com aquela carga e aquele ambiente. Resíduo crescente indica defeito em formação, antes de qualquer limiar | Carga, temperatura ambiente, dados de placa e medições |
| C | **Envelhecimento da isolação** | Com o ponto quente estimado, a perda de vida acumulada do papel isolante é calculada por norma (taxa de envelhecimento de Arrhenius) | Histórico de carga e temperatura |
| D | **Física de falhas progressivas** | Conexão frouxa ou oxidada é o achado mais comum da termografia e se agrava sozinha: resistência maior gera mais calor, mais oxidação e mais resistência. Essa trajetória tem forma conhecida e pode ser modelada | Trajetórias de degradação (bancada e campo) |

O ML entra em todas: segmenta os componentes, aprende o "normal" de cada unidade, calibra o
gêmeo físico, ajusta as trajetórias e quantifica a incerteza. Dados com rótulo de falha, quando
chegarem de clientes, servem para **calibrar** a probabilidade de falha, não para começar.

### 2.3 Formato da saída

Três camadas, sempre com intervalo de confiança:

1. **Estado atual:** severidade pelo critério configurado (NETA, NBR ou do cliente).
2. **Tendência:** "ΔT normalizado da conexão X1 subindo 0,8 °C/mês; deve atingir *reparo
   imediato* em 60 a 110 dias (80% de confiança)."
3. **Risco:** índice de saúde de 0 a 100, vida remanescente da isolação e, quando houver dados
   de frota, probabilidade de falha em 30/90/365 dias.

### 2.4 O que a termografia enxerga, e o que não enxerga

| Defeito | Visível na imagem? | Evolui de forma previsível? |
|---|---|---|
| Conexão frouxa/oxidada nos terminais das buchas | Sim, muito | **Sim** (semanas a meses, com disparada térmica no fim) |
| Nível de óleo baixo em bucha ou conservador | Sim (gradiente térmico) | Sim, se houver vazamento lento |
| Radiador obstruído ou válvula fechada | Sim (radiador frio) | Parcialmente: é um estado, o risco vem sob carga (gêmeo) |
| Ventilação forçada inoperante | Sim | O risco aparece sob carga (gêmeo) |
| Contatos desgastados no comutador sob carga | Parcialmente (compartimento mais quente que o tanque) | Sim, lentamente |
| Aquecimento do tanque por fluxo disperso | Sim | Geralmente estável |
| Para-raios degradado (equipamento vizinho) | Sim | Sim |
| Envelhecimento da isolação | Indireto (via gêmeo) | Sim (cálculo de perda de vida) |
| Curto entre espiras, descargas parciais em trafo a óleo | **Sinal fraco e indireto** | Melhor por análise de gases dissolvidos (DGA) → fusão de dados |

Consequência prática: o produto começa pelas **conexões, buchas, radiadores e comutador**, que
são visíveis e progressivos. Defeitos internos entram por fusão com DGA no índice de saúde.

### 2.5 Duas linhas de produto

| | **Inspeção** (periódica) | **Monitoramento** (contínuo) |
|---|---|---|
| Captura | Câmera portátil ou drone, a cada 6 a 12 meses | Câmera fixa + caixa de borda, 1 imagem a cada 1 a 5 min |
| Entrega principal | Laudo automático + severidade + histórico | Alerta precoce + tendência + gêmeo em tempo real |
| Força da previsão | Fraca no início (poucos pontos por ano) | **Forte** (série densa, carga conhecida) |
| Cliente típico | Prestadora de termografia, indústria | Transformadores críticos de concessionária e indústria |
| Venda | Rápida, barata, SaaS | Mais cara, hardware + assinatura |

A Inspeção abre a porta e gera dados. O Monitoramento é onde a previsão mostra seu valor.

---

## 3. Ponto de partida: do zero

Decisão de 28/09/2026: o projeto começa do zero, sem reaproveitar código nem modelos do
trabalho anterior sobre curto entre espiras. Continuam valendo apenas os princípios de método:
validação honesta, intervalos de incerteza calibrados, recusa de imagens fora do domínio,
laudo gerado por LLM com verificação dos números e cartão de cada modelo. A pesquisa de
prática, dados e ferramentas está em
[`01_pesquisa_pratica_dados_ferramentas.md`](01_pesquisa_pratica_dados_ferramentas.md).

---

## 4. Dados: o maior risco

### 4.1 O que existe publicamente

| Dataset | Conteúdo | Serve para | Não serve para |
|---|---|---|---|
| Najafi *et al.*, Mendeley (trafo seco monofásico e motor) | Bancada, curtos induzidos, BMP não radiométrico | Baixa prioridade | Campo, temperatura, previsão |
| *Infrared Thermal Image Dataset of High Voltage Electrical Power Equipment* (ScienceDB; também no Kaggle) | FLIR C5, subestação de 132 kV, 5 classes (disjuntor, trafo de potência, para-raios, seccionadora, bobina de bloqueio), horários e cargas diferentes | Detecção de componentes | Previsão (sem série longa nem desfecho) |
| Conjuntos citados em artigos (FLIR T600, robôs de inspeção) | Buchas, TCs, TPs, para-raios, comutador | Detecção e classificação | Disponibilidade incerta; conferir |
| Roboflow Universe | Muitos conjuntos pequenos | Pré-treino de detecção | Qualidade e licença variáveis |

Nenhum tem **séries temporais longas do mesmo equipamento com carga e desfecho**. Também é
preciso conferir, em cada um, se as imagens preservam os dados radiométricos e se a licença
permite uso comercial.

### 4.2 Estratégia de dados, em camadas

1. **Públicos:** treinam a detecção de componentes (onde está cada bucha, radiador etc.).
2. **Bancada própria:** câmera radiométrica barata filmando conexões com resistência de contato
   controlada e corrente conhecida. Gera trajetórias de degradação com verdade conhecida,
   que nenhum dataset público tem. (Se houver acesso a laboratório da UFCG, melhor.)
3. **Sintéticos:** pontos quentes com difusão fisicamente plausível injetados em imagens reais
   de equipamento saudável, e trajetórias simuladas pelo gêmeo térmico. Servem para medir
   sensibilidade (menor ΔT detectável) e testar o motor de previsão.
4. **Histórico de parceiros:** concessionárias e prestadoras guardam anos de laudos em PDF.
   Com o importador (paleta + leitura da escala + extração de texto por LLM), isso vira série
   temporal de milhares de ativos. É a fonte mais valiosa.
5. **Laço de dados:** cada achado que o engenheiro confirma ou corrige na interface vira rótulo.
   Com o tempo, essa base própria é o diferencial mais difícil de copiar.

---

## 5. Requisitos funcionais

Prioridade: **MVP** (primeira versão vendável), **v1** (produto completo), **Futuro**.

### DAD: aquisição e núcleo radiométrico

| ID | Requisito | Prior. |
|---|---|---|
| DAD-01 | Importar termogramas radiométricos FLIR (R-JPEG), extraindo constantes de Planck e parâmetros de medição (emissividade, temperatura refletida, distância, umidade, temperatura atmosférica) | MVP |
| DAD-02 | Importar R-JPEG de drones DJI (via DJI Thermal SDK) | v1 |
| DAD-03 | Importar matrizes de temperatura (TIFF 16/32 bits, CSV) exportadas por outros softwares | MVP |
| DAD-04 | Recalcular a temperatura com novos parâmetros (emissividade por material, distância), como fazem os softwares dos fabricantes | MVP |
| DAD-05 | Importar a foto visível pareada e alinhá-la ao termograma | v1 |
| DAD-06 | Importar termogramas não radiométricos e laudos antigos (PDF/JPG), estimando a temperatura por paleta + leitura da escala, sempre rotulada como *estimada* e com incerteza | v1 |
| DAD-07 | Capturar continuamente de câmeras fixas (RTSP + SDK/API radiométrica) e USB (Lepton, TC001) | v1 |
| DAD-08 | Registrar as condições de cada medição: carga, ambiente, vento, umidade, radiação solar, distância, operador. Manual no MVP, automático (clima e SCADA) na v1 | MVP / v1 |
| DAD-09 | Verificar a qualidade da imagem (foco, saturação, reflexo solar, faixa de temperatura) e avisar | MVP |

### VIS: visão computacional

| ID | Requisito | Prior. |
|---|---|---|
| VIS-01 | Detectar e segmentar componentes: buchas AT/BT e seus conectores, tanque, radiadores, conservador, comutador, ventiladores, para-raios, TCs. O MVP cobre buchas, conexões, tanque e radiadores | MVP |
| VIS-02 | Identificar fase e posição (H1/H2/H3, X0 a X3) para comparar componentes semelhantes | MVP |
| VIS-03 | Localizar pontos quentes e anomalias frias (radiador obstruído), com máscara e temperaturas máxima, média e percentis | MVP |
| VIS-04 | Associar o componente detectado ao componente cadastrado, para seguir o mesmo ponto entre inspeções (com confirmação do usuário) | MVP |
| VIS-05 | Regiões fixas para câmera fixa, com detecção de deslocamento da câmera | v1 |
| VIS-06 | Detector de fora do domínio: imagem muito diferente do treino recebe aviso em vez de diagnóstico | MVP |
| VIS-07 | Explicabilidade: sobrepor máscaras e os pixels que definiram cada temperatura | MVP |

### ANA: análise do estado atual

| ID | Requisito | Prior. |
|---|---|---|
| ANA-01 | Calcular ΔT entre componentes semelhantes e ΔT sobre o ambiente ou referência | MVP |
| ANA-02 | Classificar severidade por critérios configuráveis (NETA MTS, NBR 15572, critério do cliente), com prazo de ação | MVP |
| ANA-03 | Normalizar para carga de referência, ΔT·(I_ref/I)ⁿ com n entre 1,6 e 2, e avisar quando a carga estiver abaixo do mínimo recomendado para inspeção (tipicamente 40%) | MVP |
| ANA-04 | Corrigir ou sinalizar efeito de vento e radiação solar | v1 |
| ANA-05 | Critérios próprios de transformador: comutador × tanque, perfil topo/base dos radiadores, nível de óleo | v1 |

### PRE: previsão

| ID | Requisito | Prior. |
|---|---|---|
| PRE-01 | Guardar série temporal por componente: ΔT normalizado, temperaturas e condições | MVP |
| PRE-02 | Gêmeo térmico IEC 60076-7 / IEEE C57.91 (topo do óleo e ponto quente), calibrado por unidade a partir de dados de placa e medições | v1 |
| PRE-03 | Resíduo medido − esperado com detecção de mudança (CUSUM/EWMA) para alerta precoce | v1 |
| PRE-04 | Projeção de tendência com intervalo: tempo estimado até cada nível de severidade | v1 |
| PRE-05 | Perda de vida acumulada da isolação e vida remanescente estimada | v1 |
| PRE-06 | Índice de saúde (0 a 100) combinando térmico, idade, carregamento, DGA e manutenção, com metodologia inspirada na CIGRE TB 761 | v1 |
| PRE-07 | Probabilidade de falha em 30/90/365 dias, calibrada com o histórico de falhas da frota do cliente | Futuro |
| PRE-08 | Intervalos calibrados (conformal) e declaração de confiança em toda previsão | v1 |
| PRE-09 | Backtesting reprodutível: antecedência do alerta, falsos alarmes, cobertura dos intervalos | v1 |

### GEM: gêmeo digital

| ID | Requisito | Prior. |
|---|---|---|
| GEM-01 | Registro vivo do ativo: dados de placa, estado atual, histórico, documentos | MVP |
| GEM-02 | Simulação "e se": aumento de carga, onda de calor, falha de ventilação | v1 |
| GEM-03 | Capacidade dinâmica de carregamento: quanto e por quanto tempo sobrecarregar sem exceder os limites de ponto quente | v1 |
| GEM-04 | Visualização 3D com textura térmica e componentes clicáveis | Futuro |
| GEM-05 | Exportação em padrão aberto (CIM, Asset Administration Shell) | Futuro |

### REL: relatórios

| ID | Requisito | Prior. |
|---|---|---|
| REL-01 | Laudo por inspeção em PDF e DOCX: identificação, condições de medição, termograma + foto, valores, severidade, recomendação, prazo e campos do responsável técnico (ART) | MVP |
| REL-02 | Modelos por cliente (logo, seções, critérios) | MVP |
| REL-03 | Relatório gerencial da frota: ranking de risco, evolução, pendências | v1 |
| REL-04 | Texto narrativo gerado por LLM a partir do registro estruturado, com verificador que bloqueia números e afirmações ausentes do registro | MVP |
| REL-05 | Fluxo de revisão (rascunho → revisado → emitido), com versões | MVP |

### LLM: assistente

| ID | Requisito | Prior. |
|---|---|---|
| LLM-01 | Perguntas em linguagem natural sobre a frota, respondidas por chamadas à API do sistema (nunca SQL livre) | v1 |
| LLM-02 | Busca nos documentos do cliente (manuais, normas licenciadas por ele, histórico), citando a fonte | v1 |
| LLM-03 | Extração estruturada de laudos antigos em PDF | v1 |
| LLM-04 | Provedor configurável: nuvem (Claude API) ou modelo aberto local para quem não pode enviar dados | v1 |

### ALR: alertas

| ID | Requisito | Prior. |
|---|---|---|
| ALR-01 | Regras por severidade, tendência e resíduo, com histerese para não repetir alarmes | v1 (MVP: e-mail simples) |
| ALR-02 | Canais: e-mail, Telegram, webhook. WhatsApp depois | v1 |
| ALR-03 | Reconhecimento, escalonamento e histórico do alerta | v1 |

### INT: integrações

| ID | Requisito | Prior. |
|---|---|---|
| INT-01 | API REST documentada (OpenAPI) e webhooks | MVP |
| INT-02 | Carga do SCADA ou historiador: CSV, OPC UA, PI Web API; Modbus TCP pela borda | v1 |
| INT-03 | Clima automático por coordenada e hora (Open-Meteo, INMET) | v1 |
| INT-04 | Ordem de serviço no SAP PM ou Maximo (API ou arquivo) | Futuro |
| INT-05 | Exportação para Power BI e Excel | v1 |

### BRD: borda (edge)

| ID | Requisito | Prior. |
|---|---|---|
| BRD-01 | Agente para mini-PC, Jetson ou Raspberry Pi: captura, inferência local (ONNX), armazenamento offline de pelo menos 7 dias | v1 |
| BRD-02 | Comunicação só de saída (MQTT/TLS ou HTTPS), sem porta aberta na subestação | v1 |
| BRD-03 | Atualização remota segura do agente e do modelo, com reversão | v1 |
| BRD-04 | Saúde do agente: batimento, temperatura, disco | v1 |

### UI: interface

| ID | Requisito | Prior. |
|---|---|---|
| UI-01 | Envio em lote de uma inspeção, com progresso | MVP |
| UI-02 | Visualizador radiométrico: temperatura sob o cursor, paletas, isotermas, regiões desenhadas, comparação lado a lado e linha do tempo | MVP |
| UI-03 | Tela de revisão: aceitar, corrigir ou rejeitar achados (vira rótulo para retreino) | MVP |
| UI-04 | Painel da frota: mapa, ranking de risco, pendências | MVP / v1 |
| UI-05 | Página do ativo: histórico, gráficos de tendência, previsão, documentos | MVP / v1 |
| UI-06 | App de campo (PWA) com funcionamento offline | Futuro |
| UI-07 | Português, espanhol e inglês | v1 |

### ADM e MLO: plataforma e ciclo de modelos

| ID | Requisito | Prior. |
|---|---|---|
| ADM-01 | Várias empresas com isolamento de dados | v1 |
| ADM-02 | Papéis: administrador, engenheiro, termografista, leitor | MVP |
| ADM-03 | Login corporativo (OIDC/SAML: Azure AD, Google) | v1 |
| ADM-04 | Auditoria: quem emitiu ou alterou laudo, quem reconheceu alerta | v1 |
| ADM-05 | Implantação em nuvem e on-premises (Docker), inclusive sem internet | v1 |
| MLO-01 | Versionamento de dados e modelos; cada resultado guarda a versão do modelo que o gerou | MVP |
| MLO-02 | Retreino com as correções dos usuários e avaliação antes de promover o modelo | v1 |
| MLO-03 | Monitoramento de deriva (câmera nova, cliente novo) pelo detector de domínio | v1 |
| MLO-04 | Cartão do modelo e cartão dos dados por versão (uso previsto, fora do uso, desempenho medido, limitações) | MVP |

---

## 6. Requisitos não funcionais

| ID | Requisito |
|---|---|
| RNF-01 | **Exatidão.** Com os mesmos parâmetros, a temperatura exibida difere no máximo 0,5 °C da calculada pelo software do fabricante. Temperatura de imagem não radiométrica sempre aparece como *estimada*, com intervalo |
| RNF-02 | **Honestidade.** Nenhuma previsão sem intervalo e sem a base que a gerou (dados, modelo, versão) |
| RNF-03 | **Pessoa no circuito.** O sistema recomenda; emissão de laudo e decisão de desligar são sempre de uma pessoa habilitada |
| RNF-04 | **Desempenho.** Até 5 s por imagem em CPU comum; inspeção de 300 imagens em até 20 min; borda em até 1 s por quadro |
| RNF-05 | **Disponibilidade.** Nuvem com 99,5%; a borda continua funcionando sem internet |
| RNF-06 | **Segurança.** TLS, criptografia em repouso, controle de acesso por papel, MFA, trilha de auditoria; aderência gradual à IEC 62443 e à REN ANEEL 964/2021; borda sem portas de entrada |
| RNF-07 | **Privacidade.** LGPD para dados de usuários; opção de desfocar pessoas nas fotos |
| RNF-08 | **Licenças.** Só dependências compatíveis com venda de software fechado (sem AGPL: a Ultralytics YOLO, por exemplo, exige licença comercial) e só datasets cuja licença permita uso comercial |
| RNF-09 | **Reprodutibilidade.** Sementes fixas, versões travadas, testes na CI, resultados regeneráveis |
| RNF-10 | **Portabilidade.** Desenvolvimento no Windows, servidor Linux, borda ARM |
| RNF-11 | **Custo baixo no começo.** Inferência sem GPU num servidor de ~4 vCPU e 8 GB |
| RNF-12 | **Localização.** Português por padrão, unidades SI, datas no formato brasileiro |

---

## 7. Requisitos técnicos e arquitetura

### 7.1 Visão geral

```
 CAPTURA                                   FONTES EXTERNAS
 câmera portátil (R-JPEG) ──┐              SCADA / historiador (carga) ──┐
 drone (R-JPEG) ────────────┤              clima (Open-Meteo / INMET) ───┤
 laudos antigos (PDF/JPG) ──┤                                            │
 câmera fixa ─► AGENTE DE BORDA ── MQTT/HTTPS, só saída ──┐              │
                                                          ▼              ▼
 ┌──────────────────────────────── PLATAFORMA ─────────────────────────────────┐
 │ ingestão → núcleo radiométrico → visão (componentes, pontos quentes)        │
 │   → séries por componente (PostgreSQL + TimescaleDB)                        │
 │   → motor de previsão (normalização, gêmeo térmico, tendência, saúde)       │
 │   → alertas │ laudos PDF/DOCX │ assistente LLM                              │
 │ API REST ── interface web (React) ── integrações (SAP PM, Power BI, webhook)│
 └─────────────────────────────────────────────────────────────────────────────┘
```

Princípio: todo o conhecimento técnico mora numa biblioteca Python independente (`nucleo`),
testável sem web, e usada igualmente pela API, pela borda e pelos experimentos de ML.

### 7.2 Pilha proposta

| Camada | Escolha | Motivo |
|---|---|---|
| ML | PyTorch; detecção e segmentação com RF-DETR (Apache-2.0, tamanhos Nano a Large); anomalia com anomalib (Apache-2.0) | Licenças compatíveis com venda; aprende o normal sem exemplos de defeito |
| Gêmeo térmico | transformer-thermal-model da Alliander (IEC 60076-7, MPL-2.0) | Implementação aberta e mantida da norma |
| Anotação | Label Studio + SAM 2 como assistente | Livres; aceleram a anotação de máscaras |
| Experimentos e dados | MLflow, DVC | Rastreabilidade de modelo e dataset |
| Previsão | NumPy/SciPy, statsmodels, conformal próprio; lifelines no futuro | Modelos simples e explicáveis primeiro |
| Backend | FastAPI, Pydantic, SQLAlchemy; fila com Redis + Dramatiq ou Celery | Mesma linguagem do ML |
| Banco | PostgreSQL 16 + TimescaleDB; imagens em MinIO/S3 | Séries temporais no mesmo banco; roda on-premises |
| Frontend | React + TypeScript + Vite (você já usa); visualizador em canvas/WebGL; MapLibre; three.js no futuro | Familiaridade; desempenho com matrizes de temperatura |
| Relatórios | Jinja2 → PDF (WeasyPrint); DOCX (docxtpl) | Concessionárias pedem Word |
| LLM | Camada de provedor: Claude API ou modelo aberto via Ollama/vLLM; verificador de números | Nuvem ou local, sem prender a um fornecedor |
| Borda | Python + ONNX Runtime (TensorRT no Jetson), MQTT | Mesmo modelo em qualquer hardware |
| Implantação | Docker Compose (MVP e on-premises); Kubernetes só se precisar | Simples de instalar no cliente |
| Qualidade | pytest, ruff, mypy, Vitest, Playwright, GitHub Actions | Testes automáticos a cada envio |

Por que PostgreSQL puro e não Supabase, como no site: o cliente de concessionária vai pedir
instalação local, e o Supabase auto-hospedado é pesado para isso.

### 7.3 Estrutura do repositório

```
pyron/
  docs/          visão, requisitos, decisões (ADRs), cartões de modelo e de dados
  nucleo/        biblioteca: radiometria, visão, análise, previsão, gêmeo (sem web)
  ml/            treino, avaliação, experimentos
  api/           FastAPI
  web/           React + TypeScript
  borda/         agente de captura e inferência
  bancada/       aquisição da bancada experimental
  implantacao/   docker-compose e scripts
```

### 7.4 Ambiente de desenvolvimento

- Python 3.12, Node 20+, Docker Desktop (WSL2), exiftool.
- GPU não é necessária no começo. Para treinar detectores: Colab ou Kaggle (GPU T4) ou uma
  GPU local com 8 GB ou mais.

### 7.5 Câmeras (ordem de grandeza de preço; conferir antes de comprar)

| Uso | Opções | Observação |
|---|---|---|
| Protótipo e bancada | FLIR Lepton 3.5 + PureThermal (160×120, ~US$ 300); InfiRay P2 Pro ou TOPDON TC001 (256×192, ~US$ 250 a 400) | Exatidão absoluta ruim, mas ΔT útil. Para tendência, o ΔT importa mais que o valor absoluto |
| Inspeção portátil | FLIR, HIKMICRO, Testo, Fluke | Suportamos o formato do arquivo, não o aparelho |
| Drone | DJI M30T, Mavic 3T, Matrice 4T | R-JPEG via DJI Thermal SDK |
| Monitoramento fixo | FLIR série A, câmeras termográficas Hikvision e Dahua, Optris | ~US$ 3 mil a 15 mil por ponto; borda com Jetson Orin Nano ou mini-PC industrial |

---

## 8. Propostas e ideias novas

| # | Proposta | Por quê |
|---|---|---|
| 1 | **Duas linhas: Inspeção e Monitoramento** (seção 2.5) | A Inspeção vende logo; o Monitoramento entrega a previsão de verdade |
| 2 | **Previsão física + dados** (gêmeo IEC 60076-7) em vez de ML puro | Contorna a falta de dados de falha, é explicável e rende artigo (CIGRE A2) |
| 3 | **Entrar pelo laudo automático** | Dor imediata (laudo leva horas); vende antes de a previsão amadurecer e gera dados |
| 4 | **Importador de laudos antigos** (recuperação da paleta + leitura da escala + LLM) | Transforma arquivos em PDF em histórico: tendência desde o primeiro dia |
| 5 | **Bancada de degradação própria** | Única forma barata de ter trajetórias com verdade conhecida |
| 6 | **Dados sintéticos com física** | Medem sensibilidade e testam o motor de previsão sem esperar meses |
| 7 | **Laço de dados** (correções viram rótulos; contrato permite uso anonimizado) | A base própria vira o diferencial mais difícil de copiar |
| 8 | **Clima e carga automáticos** | Menos digitação e correção de vento/carga melhor |
| 9 | **Fusão com DGA e histórico** no índice de saúde | Cobre defeitos internos que a câmera não vê |
| 10 | **Priorização com orçamento** ("com R$ X, quais ativos atacar primeiro") | Fala a língua de quem aprova a compra |
| 11 | **Calculadora de retorno** com custo de falha e compensações de DEC/FEC | Argumento de venda com os números do próprio cliente |
| 12 | **Capacidade dinâmica de carregamento** | Uso diário pela operação, não só pela manutenção |
| 13 | **Triagem de voo de drone inteiro** | Centenas de imagens de um voo reduzidas às dez que importam |
| 14 | **Expansão por vertical**: disjuntores, seccionadoras, painéis, cabos; usinas solares (há dados públicos abundantes); motores | Mesmo núcleo, mercado maior |
| 15 | **P&D ANEEL + publicações** (ERIAC 2027, SNPTEE) | Financiamento e credibilidade junto às concessionárias |
| 16 | **Propriedade intelectual desde o início**: registro de software e marca no INPI | Barato e necessário para vender e licenciar |

---

## 9. Negócio e entrada no mercado

**Segmentos, do mais fácil ao mais difícil de vender:**

1. **Prestadoras de termografia e manutenção preditiva.** Dor: produzir laudos. Ciclo de venda
   curto, SaaS. Melhor primeiro cliente e melhor fonte de dados.
2. **Indústrias com subestação própria** (mineração, siderurgia, papel e celulose, alimentos,
   data centers, hospitais). Dor: parada de produção.
3. **Concessionárias de distribuição e transmissão.** Maior valor e ciclo longo. Entrada
   natural por projeto de P&D ANEEL.
4. **Usinas solares e eólicas.** Trafos elevadores, inversores, módulos.
5. **Seguradoras.** Avaliação de risco de ativos segurados.

**Modelos de cobrança possíveis:** por ativo por mês; por laudo; licença anual on-premises;
kit (câmera + borda) + assinatura. Preços são definidos na fase de entrada no mercado, com o
piloto como referência.

**Diferencial frente aos concorrentes:** softwares dos fabricantes de câmera medem e fazem
laudo, mas não preveem nem funcionam com outras marcas. Sistemas de monitoramento online
(fabricantes de trafo e de sensores) exigem sensores instalados. O nosso: sem contato,
instala em equipamento existente sem desligamento, aceita qualquer câmera, e junta laudo,
tendência e gêmeo no mesmo lugar.

---

## 10. Roteiro: marcos, fases e metas

Premissa de ritmo: projeto paralelo, cerca de 8 a 10 h/semana suas, mais o meu trabalho
entre as sessões. Os meses são aproximados e servem para ordenar, não para cobrar. Cada fase
termina com algo utilizável e verificável.

### Marco 1: Fundação (meses 1 e 2)
*"De uma imagem radiométrica real, o sistema sabe onde está cada componente e quanto ele esquenta."*

| Fase | Entregas | Meta de sucesso |
|---|---|---|
| **F0. Descoberta e base** | Repositório, estrutura e CI; levantamento de critérios (NETA MTS, NBR 15572, IEEE C57.91, IEC 60076-7, CIGRE TB 761); taxonomia de componentes e defeitos; inventário de datasets com licença e formato; escolha e compra da câmera do protótipo | Documento de critérios revisado; datasets baixados e catalogados; CI passando |
| **F1. Núcleo radiométrico** | Leitores FLIR R-JPEG, TIFF/CSV e Lepton; correções de emissividade, refletida e distância; estrutura `Termograma` (matriz °C + metadados); verificação de qualidade | Erro ≤ 0,5 °C frente ao software do fabricante num conjunto de referência; testes cobrindo cada formato |
| **F2. Visão** | Anotação (Label Studio + SAM 2) de 300 a 500 imagens; detector/segmentador de componentes; pontos quentes; comparação entre fases; severidade por regra; detector de domínio | mAP50 ≥ 0,75 nos componentes do MVP; concordância de severidade com especialista ≥ 85% |

### Marco 2: MVP de Inspeção vendável (meses 3 e 4)
*"O termografista envia as imagens de uma inspeção e recebe o laudo pronto para revisar e assinar."*

| Fase | Entregas | Meta de sucesso |
|---|---|---|
| **F3. Backend e dados** | Cadastro de ativos (empresa → instalação → equipamento → componente); inspeções; envio em lote; processamento assíncrono; API | Inspeção de 300 imagens processada em até 20 min |
| **F4. Interface web** | Envio, visualizador radiométrico, tela de revisão, painel da frota, página do ativo | Um usuário novo faz uma inspeção completa sem ajuda |
| **F5. Laudo automático + LLM** | PDF/DOCX no modelo da NBR 15572; modelo por cliente; narrativa por LLM com verificador; fluxo de revisão | Laudo de 20 pontos em menos de 10 min (medido com termografista real), contra horas no processo manual |
| **F6. Piloto de campo 1** | Parceiro real (prestadora ou indústria) usando em inspeções; importação de laudos antigos | 1 parceiro, 100 ativos cadastrados, retorno documentado, histórico importado |

### Marco 3: Previsão (meses 4 a 6)
*"O sistema diz o que vai piorar e quando, com margem de erro."*

| Fase | Entregas | Meta de sucesso |
|---|---|---|
| **F7. Bancada e dados de degradação** (pode correr em paralelo com F3 a F6) | Câmera barata + conexão com resistência de contato controlada + sensores de corrente e ambiente; gerador de dados sintéticos | 10 trajetórias de degradação registradas com verdade conhecida |
| **F8. Motor de previsão v1** | Normalização de carga, vento e ambiente; gêmeo térmico calibrado por unidade; resíduo com detecção de mudança; tendência com intervalo; perda de vida; índice de saúde; backtesting | Em backtest: alerta com antecedência mediana definida na F0 antes de cruzar o limiar crítico; taxa de falso alarme por ativo-ano abaixo do alvo; intervalos de 80% cobrindo entre 75% e 85% |

### Marco 4: Monitoramento contínuo (meses 6 a 8)
*"Câmera fixa e caixa de borda enviando alertas sozinhas."*

| Fase | Entregas | Meta de sucesso |
|---|---|---|
| **F9. Agente de borda + câmera fixa** | Captura (RTSP/SDK/Lepton); regiões fixas; inferência local; armazenamento offline; comunicação só de saída; atualização remota | 30 dias contínuos na bancada sem intervenção |
| **F10. Alertas e integrações** | Regras com histerese; e-mail, Telegram, webhook; carga via CSV/OPC UA/PI; clima automático; exportação para Power BI | Alerta chega em até 5 min; carga e clima entram sem digitação |

### Marco 5: Gêmeo digital e assistente (meses 8 a 10)

| Fase | Entregas | Meta de sucesso |
|---|---|---|
| **F11. Gêmeo digital** | Simulação "e se"; capacidade dinâmica de carregamento (visualização 3D fica para depois: GEM-04, Futuro) | O gêmeo reproduz a temperatura de topo do óleo medida dentro de uma margem definida na F8 |
| **F12. Assistente LLM** | Perguntas sobre a frota por ferramentas; busca em documentos do cliente com citação; extração de laudos; modo local | Respostas conferidas em um conjunto de perguntas de teste, sem número inventado |

### Marco 6: Produto comercial v1.0 (meses 10 a 12)

| Fase | Entregas | Meta de sucesso |
|---|---|---|
| **F13. Endurecimento** | Várias empresas; login corporativo; papéis; auditoria; backups; observabilidade; checklist de segurança (IEC 62443, REN 964); instaladores nuvem e on-premises | Instalação on-premises do zero em menos de 1 hora; teste de invasão básico sem achado crítico |
| **F14. Entrada no mercado** | Marca e software no INPI; site e demonstração com dados sintéticos; calculadora de retorno; material comercial; preços; caso do piloto; artigo técnico; proposta de P&D ANEEL | Primeira proposta comercial enviada |

As metas numéricas marcadas como "definida na F0/F8" dependem dos dados que conseguirmos;
fixá-las antes seria chute.

---

## 11. Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Não haver dados de falha real para validar a previsão | Alto | Camadas físicas (seção 2.2), bancada, histórico de parceiros; comunicar a incerteza |
| Imagens de campo muito variadas (câmera, ângulo, clima) | Alto | Normalização, detector de domínio, dados de várias fontes, revisão humana |
| Não conseguir parceiro para o piloto | Alto | Começar por prestadoras e indústria (ciclo curto); contatos UFCG e CIGRE; demonstração com dados sintéticos |
| Ciclo de venda longo nas concessionárias | Médio | Indústria primeiro; P&D ANEEL como porta |
| Responsabilidade por um laudo errado | Alto | Pessoa no circuito, ART, termos de uso com limitação de responsabilidade |
| Licenças incompatíveis (AGPL, datasets, textos de norma) | Médio | Checklist de licenças na CI; normas só as que o cliente licencia |
| Escopo grande para um projeto paralelo | Alto | Marcos pequenos e vendáveis; cortar o que é "Futuro" sem dó |
| Exigências de segurança de TI/TO | Médio | Borda só de saída, opção on-premises, documentação de segurança |
| Concorrência (fabricantes de câmera, monitoramento por sensores) | Médio | Previsão, independência de marca, laudo + tendência + gêmeo juntos |

---

## 12. Decisões pendentes

1. Nome definitivo e repositório (GitHub privado?).
2. Primeiro segmento-alvo: prestadora de termografia, indústria ou concessionária.
3. Acesso a laboratório (UFCG?) e a alguém com termogramas históricos.
4. Orçamento e escolha da câmera do protótipo.
5. Termografista certificado para validar critérios e laudos.
6. Horas por semana disponíveis (ajusta o cronograma).

---

## Fontes consultadas

- Najafi, Baleghi e Mirimani, Mendeley Data: [trafo seco monofásico](https://data.mendeley.com/datasets/8mg8mkc7k5/3), [motor de indução](https://data.mendeley.com/datasets/m4sbt8hbvk/3), [repositório](https://github.com/mohnaj-nit/thermal-images-equip)
- [Infrared Thermal Image Dataset of High Voltage Electrical Power Equipment under Different Operating Conditions (ScienceDB)](https://www.scidb.cn/en/detail?dataSetId=e416c488169f484485ad7575dcfc43ce) e [versão no Kaggle](https://www.kaggle.com/datasets/s3programmerlead/infrared-thermal-image-dataset/data)
- [Deep learning model for detection of hotspots using infrared thermographic images of electrical installations (JESIT, 2024)](https://jesit.springeropen.com/articles/10.1186/s43067-024-00148-y)
- [Infrared image identification method of substation equipment fault under weak supervision (arXiv 2311.11214)](https://arxiv.org/pdf/2311.11214)
- [Infrared Image Detection and Recognition of Substation Electrical Equipment Based on Improved YOLOv8 (MDPI, 2025)](https://www.mdpi.com/2076-3417/15/1/328)
- [Roboflow Universe: conjuntos térmicos](https://universe.roboflow.com/search?q=class:thermal+camera)
- [IEC 60076-7 loading guide thermal model constants estimation (SINTEF)](https://www.sintef.no/en/publications/publication/912067/)
- [Data-Driven vs Traditional Approaches to Power Transformer's Top-Oil Temperature Estimation (arXiv 2501.16831)](https://arxiv.org/html/2501.16831)
- [AI-driven predictive maintenance for enhanced reliability of power transformers: systematic review (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S2949821X26003121)
- [Research on Digital Analysis Method of Transformer Hot Spot Temperature Based on BP Neural Network (IET, 2025)](https://ietresearch.onlinelibrary.wiley.com/doi/full/10.1049/elp2.70018)

Normas citadas (NETA MTS, ABNT NBR 15572, IEEE C57.91, IEC 60076-7, IEC 60599, CIGRE TB 761,
IEC 62443, REN ANEEL 964/2021): valores e tabelas serão conferidos nas edições vigentes na F0.
