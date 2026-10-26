# Etapa 5d · Modelos e Configurações (com Sobre)

Data: 26/10/2026. Rotas `/nova/#modelos` (abas `emuso`, `treino`, `avaliacao`) e `/nova/#configuracoes` (abas
`empresa`, `criterio`, `componentes`, `aparencia`, `dados`, `sobre`), ligadas à API real. Código: `js/telas/modelos.js`
+ `js/modelos/`, `js/telas/configuracoes.js` + `js/configuracoes/`, e a casca de abas que passou a ser compartilhada
com a Captura, `js/telaAbas.js`. A tela provisória saiu: toda rota tem tela própria. Capturas em
`docs/interface/capturas/etapa5d/` (as figuras da avaliação são do caderno do Colab, com imagens do dataset de estudo
ScienceDB 10185, CC BY-NC-SA).

## 1. Estrutura

**Modelos** (decisão da Etapa 1: abas Em uso · Treino · Avaliação; avaliar é parte de escolher o modelo)

| Aba | Primário | Conteúdo |
|---|---|---|
| Em uso | **Usar este modelo** (no painel do escolhido) | tabela dos detectores (modelo, tipo, peças, situação com "Em uso" e "Recomendado"); ao lado, o detalhe: descrição, peças, treino e desempenho, versão rápida (INT8) com "Usar a versão rápida", vantagens e limitações recolhidas; Instalar modelo (.zip) |
| Treino | **Enviar anotações**, depois **Começar treino** | estado do PyTorch e da GPU; ilustração `modelos` e uma linha; com os rótulos: imagens prontas, rótulos, classes, sessões, tabela por classe, avisos, nome, identificador, épocas, separação treino e teste, Baixar pacote para o Colab; treinos com andamento, métricas, previsões e Usar este modelo |
| Avaliação | **Importar resultados** | melhor no teste, peças encontradas, peças que escaparam, fotos; conclusões (empate ou vantagem, ponto fraco comum); comparação no teste com o melhor de cada coluna em negrito; AP50 por componente; "o modelo veio junto" com Usar; figuras do caderno recolhidas |

**Configurações** (Etapa 1: Empresa e responsáveis · Critério · Componentes · Aparência · Dados e backup · Sobre)

| Aba | Salvar | Conteúdo |
|---|---|---|
| Empresa e responsáveis | sozinho ("Salvo às …") | nome, subtítulo, logotipo (enviar, trocar, remover); responsáveis técnicos (nome, função, registro; o marcado à esquerda é o padrão do laudo) |
| Critério | **Salvar critério** | partir de um modelo (Brasil ou NETA); quatro grupos (% da MTA, ΔT entre semelhantes condutores, ΔT de para-raios e isoladores, ΔT sobre o ambiente com "Usar este grupo"), um valor por nível com o selo ao lado; nome, expoente da carga, carga mínima; Restaurar padrão |
| Componentes | **Salvar biblioteca** | tabela: componente, aquecimento, MTA (com o padrão quando mudou), fonte; Restaurar padrão |
| Aparência | na hora | Claro, Escuro, Seguir o Windows |
| Dados e backup | — | pasta, número de inspeções, espaço; Abrir a pasta; **Baixar backup**; Restaurar backup (com confirmação) |
| Sobre | — | logo, versão, detector em uso, pastas de dados e de modelos, créditos e licenças |

## 2. Decisões e motivo

| Decisão | Motivo |
|---|---|
| Em uso como lista com painel ao lado (como Pendências), não cartões; o escolhido abre no em uso | Comparar tipo, peças e situação na mesma coluna; o detalhe longo (vantagens, limitações) fica recolhido |
| **Recomendado** marcado na lista: a IA treinada junto com a regra dos pontos quentes | Lacuna *Choice Overload* da Etapa 4: sete modelos com nomes técnicos e nenhum caminho indicado |
| Versão rápida (INT8) sem linha própria: opção no detalhe do original | Dois itens quase iguais na lista confundiam (como na tela antiga) |
| Modelo que não está instalado aparece com o motivo, sem botão | Escolha de modelo: a pessoa precisa saber por que não pode (mesma regra da Análise) |
| Treino: instruções de terminal e do Colab saem da tela; ficam uma linha e o LEIA-ME do pacote | Etapa 1 (texto de desenvolvedor vai para o manual) |
| Avaliação em números e tabelas, sem gráfico de barras | Três modelos e cinco métricas: o valor exato decide (a diferença é de 0,01); o caderno do Colab já traz as curvas como figuras |
| Melhor de cada coluna em negrito, não em cor | Severidade e ação são as únicas cores; o negrito não depende de ver cor |
| Empresa e responsáveis salvam sozinhos; responsável só vai ao servidor com nome e registro | Padrão da Análise e da Pasta monitorada; o servidor recusa o cadastro incompleto enquanto a pessoa digita |
| Critério e componentes com **Salvar** explícito | Cada gravação recalcula todas as inspeções: salvar a cada letra recalcularia o acervo inteiro dezenas de vezes |
| No critério, o selo do nível é o rótulo visível do campo (o rótulo completo "Atenção a partir de" fica para o leitor de tela) | A primeira versão repetia o rótulo em cima de cada campo ao lado do selo: o grupo ficava duas vezes mais alto |
| Barras de rótulos por classe em cinza | Contagem é dado neutro; o cobalto fica para ação e seleção (achado na revisão) |
| Restaurar backup pede confirmação; remover o logotipo também | Os dois não voltam com Desfazer |
| Sobre sem texto de apresentação ("Ver o defeito antes da falha") | Etapa 1: marketing vai para o README; aqui ficam versão, pastas e créditos |
| A casca de abas virou `telaComAbas()` | Captura, Modelos e Configurações: componente que aparece 2+ vezes vira um só |
| Links que ainda iam para a interface antiga (cadastrar responsável, configurar o laudo) apontam para `#configuracoes` | Não há mais tela que dependa da interface antiga |

## 3. Conferido no navegador

Roteiros no Edge sem janela, 1536 × 816, nos dados de demonstração e na pasta de rascunho (`pyron-vazio`, apagada
depois pela Lixeira). Os arquivos foram postos nos campos de arquivo pelo protocolo de depuração (o mesmo caminho do
botão):
- Em uso: escolher o recomendado, Usar este modelo (aviso e "Em uso" na linha), Usar a versão rápida.
- Treino: `dados/rotulos/PR.zip` → 141 imagens prontas, 1 047 caixas, 4 classes, avisos ("30 imagens sem rótulo",
  "uma só sessão"). O treino em si não foi rodado (leva minutos na GPU); Começar treino ficou habilitado com o
  PyTorch e a RTX 3050 detectados.
- Avaliação: um .zip montado com os resultados de 30/09 (cópia, a pasta real só foi lida) → 3 modelos, RF-DETR
  Medium melhor (mAP50 0,91), empate com o YOLO26S por 2 peças, ponto fraco Terminal Inferior.
- Empresa e responsáveis: nome da empresa e um responsável novo salvos sozinhos (só depois do registro preenchido);
  responsável padrão trocado pelo marcador.
- Critério: Atenção em 55 % salvo (Personalizado); Programar em 50 % recusado pelo servidor com a mensagem no
  formulário ("Os limites precisam subir junto com a gravidade dos níveis").
- Componentes: MTA da conexão em 85 °C salva, linha marcada como alterada com o padrão ao lado.
- Aparência: Escuro aplicado na hora e guardado; de volta ao Claro.
- Backup: 5,3 MB baixado; empresa mudada pela API; restaurado pelo botão com confirmação → nome de volta e página
  recarregada.
- Abrir a pasta não foi clicado (abre o Explorador no computador).

## 4. Medidas

**Contraste e alvos** (`js/conferir.js`, com as seções recolhidas abertas), claro, escuro e toque: 0 falhas em todas
as abas e estados (vazio e com dados: 9 a 113 textos, 11 a 41 alvos por aba). Achado e corrigido: links das figuras
da avaliação com 2 px de altura antes de a imagem carregar.

**Proporção de cor** (saturação > 0,35 e brilho > 0,3; estrutura = azul, violeta e cobalto):

| | Estrutura | Total |
|---|---|---|
| Modelos / Avaliação / Configurações / Sobre antigas | 16,0 % / 16,6 % / 15,9 % / 17,3 % | 16,1 % / 16,9 % / 16,2 % / 18,3 % |
| Em uso (claro / escuro) | 0,2 % / 0,2 % | 0,3 % / 0,4 % |
| Treino / Avaliação com dados | 0,7 % / 0,8 % | 0,9 % / 0,9 % |
| Configurações (as seis abas) | 0,1 % a 0,6 % | 0,2 % a 0,7 % |

## 5. Checklist de UX (12 itens)

| # | Item | Modelos | Configurações |
|---|---|---|---|
| 1 | Ação principal em destaque | um primário por aba (Usar, Enviar ou Começar, Importar) | Salvar critério, Salvar biblioteca, Baixar backup; empresa salva sozinha |
| 2 | No máximo 7 opções | 3 abas, 5 modelos na lista | 6 abas, 4 níveis por grupo |
| 3 | Agrupamento | lista e painel; seções | grupos do critério em caixas |
| 4 | Resposta em < 400 ms | esqueleto, botões ocupados, "Lendo os rótulos…" | "Salvando…", botões ocupados |
| 5 | Convenções | mestre e detalhe, tabela | abas de configuração, Restaurar padrão |
| 6 | Hover e foco | sim | sim |
| 7 | Progresso | andamento do treino (barra e etapa) | não se aplica |
| 8 | Alvos ≥ 44 px em toque | 0 falhas | 0 falhas |
| 9 | Estados vazios | `modelos` em Treino e Avaliação | "Sem logotipo", "Ninguém cadastrado" |
| 10 | Blocos | seções recolhíveis | seções com título |
| 11 | Hierarquia | números 29, títulos 17, tabela 14 | idem |
| 12 | Complexidade escondida | vantagens, limitações, figuras recolhidas | "Partir de um modelo", padrão restaurável |

**12/12 nas duas telas.**

## 6. Nota pelas 30 Leis de UX

| Lei | Nota | | Lei | Nota |
|---|---|---|---|---|
| Aesthetic-Usability | 2 | | Doherty Threshold | 2 |
| Prägnanz | 2 | | Flow | 2 |
| Von Restorff | 2 | | Goal-Gradient | 2 |
| Similarity | 2 | | Serial Position | 2 |
| Proximity | 2 | | Peak-End | 1 |
| Common Region | 2 | | Zeigarnik | 2 |
| Uniform Connectedness | 2 | | Working Memory | 2 |
| Cognitive Load | 2 | | Jakob | 2 |
| Hick | 2 | | Postel | 2 |
| Miller | 2 | | Tesler | 2 |
| Chunking | 2 | | Occam | 2 |
| Choice Overload | 2 | | Pareto | 2 |
| Cognitive Bias | 2 | | Selective Attention | 2 |
| Fitts | 2 | | Mental Model | 2 |
| Paradox of the Active User | 2 | | Parkinson | 2 |

**59 de 60.** O ponto que falta:
- *Peak-End:* o fim de um treino é só a etapa "Pronto" no cartão, com as métricas; não há um retorno próprio
  (como o "Laudo pronto") nem aviso se a pessoa estiver em outra tela quando o treino acabar. Fica para a revisão
  da Etapa 6 ou para quando o treino pela interface for usado de verdade (hoje o caminho principal é o Colab).

A lacuna *Choice Overload* da Etapa 4 (escolha de modelo) foi resolvida aqui com o recomendado.
