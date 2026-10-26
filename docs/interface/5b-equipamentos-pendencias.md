# Etapa 5b · Equipamentos e Pendências

Data: 25/10/2026. Rotas `/nova/#equipamentos`, `/nova/#equipamentos/<chave>` e `/nova/#pendencias`, ligadas à API
real. Código em `app/interface/js/telas/equipamentos.js`, `equipamento.js` e `pendencias.js`, e nos módulos
compartilhados novos `js/grafico.js` (gráfico de uma série, tendência e linha pequena) e `js/pendencia.js`
(formulário de acompanhamento, usado também pela Análise); layout em `app/interface/telas.css`.
Capturas: `docs/interface/capturas/etapa5b/`. As imagens térmicas são do dataset de estudo ScienceDB 10185
(CC BY-NC-SA), dos dados de demonstração. A medição de dimensões já está na Análise (Etapa 4).

## 1. Estrutura em 1536 × 816

**Equipamentos**

| Área | Conteúdo |
|---|---|
| Cabeçalho | Equipamentos, "3 equipamentos em 2 instalações" (sem primário: a tela é de consulta, decisão da Etapa 1) |
| Filtros | Todos · Com anomalia · Inspeção vencida · Esquentando (> 0,5 °C/mês), com a contagem no botão · busca |
| Tabela | agrupada por instalação (linha de título fixa ao rolar): traço de severidade · última imagem · equipamento ("3 inspeções, desde …") · estado · última inspeção (data e "há 3 anos") · Tmáx na última · tendência (linha pequena e "+1,9 °C/mês" com seta) · próxima inspeção (data e "vencida há 2 anos") |
| Rodapé | "3 inspeções sem equipamento não entram no histórico. Definir em Inspeções" (abre Inspeções já filtrada) |

**Equipamento (detalhe)**

| Área | Conteúdo |
|---|---|
| Cabeçalho | migalhas Equipamentos › instalação › equipamento · nome · selo e "3 inspeções, desde …" · Adicionar imagens · **Relatório do equipamento** |
| Indicadores | estado atual · máxima na última (e a região) · tendência (com a data estimada em que chega à MTA) · próxima inspeção |
| Gráfico | temperatura máxima por inspeção (ou elevação a plena carga, quando há ambiente e carga), 320 px de altura |
| Peças | máxima, tendência e estado de cada tipo de peça (quando há mais de um tipo) |
| Coluna de 400 px | as inspeções do equipamento: miniatura, data, região crítica, Tmáx e selo |

**Pendências**

| Área | Conteúdo |
|---|---|
| Cabeçalho | Pendências, "5 pendências" (sem primário na tela; o primário fica no painel: Salvar) |
| Filtros | Em andamento · Vencidas · Aguardando reinspeção · Concluídas · Todas, com contagem · busca |
| Tabela | traço · severidade · equipamento e região (instalação, região, Tmáx) · detectada · prazo (data e "vencida há 3 anos") · situação (e "reinspeção normal em …") · OS · responsável |
| Painel de 400 px | miniatura, equipamento, região, data da detecção, Abrir a inspeção; acompanhamento (situação e prazo, OS e responsável lado a lado, nota) com **Salvar** fixo embaixo; histórico recolhido |

Filtros, busca e a pendência aberta ficam no endereço (`#pendencias?situacao=vencidas&id=<inspeção>`,
`#equipamentos?filtro=vencidas&q=bay`). Os indicadores do Painel (Etapa 5a) já apontavam para esses endereços.

## 2. Decisões e motivo

| Decisão | Motivo |
|---|---|
| Cartões de contagem saem nas duas telas; a contagem fica no filtro | Faziam a mesma coisa duas vezes (diagnóstico da Etapa 1, item 7) |
| Equipamentos em **tabela agrupada por instalação**, não em cartões | Etapa 1 (tabela compacta); compara estado, tendência e prazo na mesma coluna; instalação com o pior equipamento primeiro |
| Tendência mostrada como linha pequena + número com seta, com R² e número de inspeções no `title`; sem pontos suficientes, "sem tendência ainda" com o motivo | O número sozinho engana com 3 pontos; a linha mostra a forma (Prägnanz) |
| Detalhe com migalhas (toque 14) e indicadores no topo; gráfico grande | Working Memory: de onde vim e o estado atual à vista antes do histórico |
| Gráfico: uma série, um eixo; linha neutra de 2 px; pontos de 10 px **na cor da severidade** com anel da superfície; reta de tendência tracejada; rótulo só no último ponto; dica ao passar o mouse ou focar; o ponto é link para a inspeção | Regras da orientação de visualização de dados: a cor é dado (severidade), não identidade de série; o valor que importa é o último |
| Datas do eixo: as das inspeções, uma por dia, sem ficar a menos de 96 px uma da outra | Duas inspeções no mesmo dia sobrepunham a data (achado na captura) |
| Relatório do equipamento usa o mesmo diálogo do laudo (`js/laudo.js`), da inspeção mais antiga para a mais nova | Componente que aparece duas vezes vira um só; o fim "Laudo pronto" vale aqui também |
| "Adicionar imagens" no detalhe: a escolha de arquivos leva instalação e equipamento (`escolherArquivos(destino)`) | As imagens entram já no histórico, sem o passo de definir equipamento |
| Pendências: lista com painel ao lado, **sem diálogo** (Etapa 1); clicar na linha escolhe, ↑ ↓ percorrem | O técnico atualiza várias em sequência sem abrir e fechar janela (Flow) |
| Um formulário de pendência para a Análise e para Pendências (`js/pendencia.js`); situação e prazo, OS e responsável em pares; a linha repetida de selo e prazo saiu | Componente compartilhado; com os pares, Salvar cabe em 816 px; selo e prazo já estão na linha da tabela e no cabeçalho da Análise |
| Salvar fixo no pé do painel e o aviso "Pendência atualizada" à esquerda do painel | Na primeira captura o aviso cobria o próprio botão Salvar |
| Dica de reinspeção ("A inspeção de … saiu normal. Se foi depois do reparo, marque como verificada.") com link | Tesler: o sistema acha a reinspeção, a pessoa só confirma |
| Busca das listas virou componente (`campoBusca()`), usado em Inspeções, Equipamentos e Pendências | Aparecia três vezes |
| Inspeções aceita `?equipamento=sem` (chip "Só as sem equipamento") | Destino do rodapé e do vazio de Equipamentos: a pessoa chega direto nas imagens a definir |

## 3. Conferido no navegador

Roteiros no Edge sem janela (protocolo de depuração), 1536 × 816, nos dados de demonstração (`pyron-demo`) e
numa pasta vazia de rascunho (`pyron-vazio`, apagada depois pela Lixeira):
- Equipamentos: 2 grupos e 3 linhas; filtro Esquentando (1, endereço `?filtro=esquentando`); busca sem resultado
  com Limpar filtros; rodapé das inspeções sem equipamento (3) com o link para Inspeções filtrada (6 → chip);
- detalhe do TR-01: migalhas, 4 pontos, dica "46,8 °C | 29/02/2024 | Normal, Ponto quente 4", datas sem repetir;
- Adicionar imagens com destino: a imagem nova entrou como "SE Teste / TR-99" e abriu a Análise;
  Relatório do equipamento sem responsável cadastrado mostra o aviso e o caminho para cadastrar;
- Pendências: clique escolhe (endereço com `id`), ↓ passa para a seguinte, filtro Aguardando reinspeção (2),
  busca "bay" (1); salvar situação Programada com OS e nota: aviso, linha atualizada ("Programada", "OS 2026-0001");
- Análise: a aba Pendência abre pelo link do cabeçalho com o mesmo formulário (9 textos, 11 alvos, 0 falhas).

## 4. Medidas

**Contraste e alvos** (`js/conferir.js`), claro, escuro e toque: 0 falhas em todos os estados.

| Estado | Textos | Alvos |
|---|---|---|
| Equipamentos com dados | 55 | 19 |
| Equipamento (detalhe) | 76 | 23 |
| Pendências com uma escolhida | 60 | 27 |
| Equipamentos vazio / Pendências vazio | 13 / 13 | 12 / 12 |

Falhas achadas e corrigidas: links das migalhas com 36 px e área dos pontos do gráfico com 28 px (passaram a 44 px).

**Proporção de cor** (saturação > 0,35 e brilho > 0,3; estrutura = azul, violeta e cobalto):

| | Estrutura (claro / escuro) | Total com dados |
|---|---|---|
| Equipamentos antiga | 15,8 % | 16,3 % |
| Equipamento antiga | 16,4 % | 16,7 % |
| Pendências antiga | 15,5 % | 15,6 % |
| Equipamentos nova | 0,3 % / 0,3 % | 0,8 % |
| Equipamento nova | 1,0 % / 1,0 % | 1,4 % |
| Pendências nova | 0,6 % / 0,6 % | 1,1 % |

## 5. Checklist de UX (12 itens)

| # | Item | Equipamentos | Equipamento | Pendências |
|---|---|---|---|---|
| 1 | Ação principal em destaque | consulta, sem primário (Etapa 1) | Relatório do equipamento | Salvar, no painel |
| 2 | No máximo 7 opções por grupo | 4 filtros | 2 ações, 4 indicadores | 5 filtros, 5 campos |
| 3 | Agrupamento | por instalação | indicadores, gráfico, peças, inspeções | lista e painel |
| 4 | Resposta em < 400 ms | esqueleto de lista | esqueleto, dica no ponto | Salvar ocupado, aviso |
| 5 | Convenções | tabela agrupada | migalhas, gráfico com eixo | lista e detalhe (mestre e detalhe) |
| 6 | Hover e foco | linhas | pontos com anel de foco | linhas, ↑ ↓ |
| 7 | Progresso em várias etapas | não se aplica | não se aplica | situação aberta → programada → corrigida → verificada no campo |
| 8 | Alvos ≥ 44 px em toque | 0 falhas | 0 falhas | 0 falhas |
| 9 | Estados vazios | `equipamentos` com Definir em Inspeções; busca sem resultado | equipamento inexistente com `busca` | `pendencias` (estado bom); busca sem resultado |
| 10 | Informação em blocos | grupos | blocos com título | seções recolhíveis |
| 11 | Hierarquia | título 24, tabela 14 | indicadores 29, gráfico | título 24, painel 17 |
| 12 | Complexidade escondida | R² no `title` | série a plena carga só quando existe | histórico recolhido |

**12/12 nas três telas.**

## 6. Nota pelas 30 Leis de UX (as três telas juntas)

| Lei | Nota | | Lei | Nota |
|---|---|---|---|---|
| Aesthetic-Usability | 2 | | Doherty Threshold | 2 |
| Prägnanz | 2 | | Flow | 2 |
| Von Restorff | 2 | | Goal-Gradient | — |
| Similarity | 2 | | Serial Position | 2 |
| Proximity | 2 | | Peak-End | 2 |
| Common Region | 2 | | Zeigarnik | 2 |
| Uniform Connectedness | 2 | | Working Memory | 2 |
| Cognitive Load | 2 | | Jakob | 2 |
| Hick | 2 | | Postel | 2 |
| Miller | 2 | | Tesler | 2 |
| Chunking | 2 | | Occam | 2 |
| Choice Overload | — | | Pareto | 2 |
| Cognitive Bias | 1 | | Selective Attention | 2 |
| Fitts | 2 | | Mental Model | 2 |
| Paradox of the Active User | 2 | | Parkinson | 2 |

**53 de 54 nas 27 leis que se aplicam (equivale a 59/60).** O ponto que falta:
- *Cognitive Bias:* a projeção "chega à MTA por volta de 20/05/2024" é uma extrapolação linear de 3 pontos e
  aparece como número de destaque no indicador de tendência; o texto marca "(estimativa fraca)", mas a data
  ainda ancora a leitura. Melhorar exige regra de produto (mostrar só com 4 pontos ou mais e R² ≥ 0,5, o que o
  servidor já chama de `confiavel`); fica registrado para a revisão da Etapa 6.

## 7. Toques do `acabamento.md`

Feito: 14 (migalhas, no detalhe do equipamento). Na Análise as migalhas não entraram: o cabeçalho de uma linha
precisa caber com o termograma inteiro em 816 px, e as setas anterior e próxima já dão o caminho dentro do equipamento.

## 8. Componentes que mudaram

- `tabela()`: `grupo(linha)` (linha de título por grupo, fixa ao rolar) e `aoEscolher(linha)` (a linha
  seleciona em vez de navegar; o alvo de teclado vira botão).
- `campoBusca({ rotulo, valor, aoMudar })`.
- `js/grafico.js`: `graficoSerie()`, `seloTendencia()`, `miniSerie()`.
- `js/pendencia.js`: `formularioPendencia(p, { primario, aoSalvar })`.
- `importar.js`: `escolherArquivos(destino)` e `arquivosEscolhidos()`.
- `situacao.js`: `ESQUENTANDO`, `nomeClasse()`.
- Tabela: data em cima e atraso embaixo (`.tabela td > .vencida` em bloco).
