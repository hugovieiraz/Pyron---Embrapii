# Etapa 5a · Painel e Inspeções (com a importação)

Data: 25/10/2026. Rotas `/nova/#painel` e `/nova/#inspecoes`, ligadas à API real. Código em
`app/interface/js/telas/painel.js`, `js/telas/inspecoes.js` e nos módulos compartilhados novos
`js/situacao.js` (regras de leitura da lista), `js/laudo.js` (diálogo do laudo, usado também pela Análise)
e `js/importar.js` (refeito); layout em `app/interface/telas.css`.
Capturas: `docs/interface/capturas/etapa5a/`. As imagens térmicas são do dataset de estudo ScienceDB 10185
(CC BY-NC-SA), dos dados de demonstração.

## 1. Estrutura em 1536 × 816

**Painel**

| Área | Conteúdo |
|---|---|
| Cabeçalho | Painel · **Importar termogramas** (único primário, Ctrl+O) |
| Coluna principal | "Atenção agora": a última inspeção de cada equipamento fora do normal, da pior para a melhor (equipamento em 20 px, Tmáx em 35 px, selo); abaixo, "Importadas por último" (5, com miniatura) |
| Coluna de 400 px | 4 indicadores clicáveis (críticas, pendências vencidas, inspeções vencidas, alertas) · o que falta para o laudo sair completo · próximas inspeções (5) · situação atual em barra empilhada com legenda |
| Sem nenhuma inspeção | Primeira execução: três passos ligados por uma linha (Importe → Analise → Gere o laudo) com as ilustrações `inspecoes`, `analise` e `laudo`; Importar e "Usar dados de demonstração" |

**Inspeções**

| Área | Conteúdo |
|---|---|
| Cabeçalho | Inspeções, "10 inspeções" · Exportar planilha · **Importar termogramas** |
| Faixa de importação | só durante a importação: "Importando 5 de 5", o arquivo da vez e a barra determinada |
| Filtros | segmentado de severidade com a contagem no próprio botão (Todas, Críticas, Programar, Atenção, Normais e Sem medida quando houver) · chip "Só a última de cada equipamento" quando vem do Painel · busca |
| Tabela | seleção · traço de severidade · miniatura · inspeção (arquivo e data) · equipamento · região crítica (nome e % da MTA ou ΔT) · Tmáx · severidade com "Pendência vencida/aberta"; cabeçalho fixo, a tabela rola por dentro; 100 linhas e "Mostrar mais" |
| Seleção | barra flutuante na borda de baixo: "2 selecionadas" · Gerar laudo · Definir equipamento · Apagar · limpar (Esc) |

Filtros, busca e ordem ficam no endereço (`#inspecoes?sev=criticas&q=tr-01&ordem=tmax-desc`), sem recarregar a
tela (`history.replaceState`): o link do indicador "Críticas" do Painel abre a lista já filtrada.

## 2. Decisões e motivo

| Decisão | Motivo |
|---|---|
| Contagem dentro do filtro de severidade; os cartões de contagem da tela antiga saíram | Faziam a mesma coisa que o filtro (Occam, diagnóstico da Etapa 1) |
| Vista em grade saiu; a miniatura fica na linha da tabela | Repetia a miniatura da tabela (Etapa 1); uma forma de ver a lista |
| Indicadores e "Atenção agora" pela **situação atual** (a última inspeção de cada equipamento); o indicador leva a `?sev=criticas&atual=1` e a lista mostra o chip "Só a última de cada equipamento" | O número do Painel e a lista aberta por ele batem; na tela antiga o indicador contava a situação atual e a lista mostrava todas |
| "Importadas por último" na coluna principal | Com poucos itens de atenção a coluna ficava vazia; é o caminho de volta para o que acabou de entrar (Pareto: o fluxo diário) |
| Ações da seleção numa barra flutuante embaixo, não no lugar dos filtros | Filtros e busca continuam à mão enquanto se seleciona; nada empurra a tabela; padrão de gerenciadores de arquivo (Jakob) |
| Sem botões em cada linha; Abrir, Gerar laudo, Definir equipamento, Ver equipamento e Apagar no **menu de contexto** (botão direito) e na barra de seleção | Hick e densidade: 10 linhas × 2 botões eram 20 alvos repetidos; a linha inteira abre a inspeção |
| Apagar pede confirmação (diálogo com a quantidade); definir equipamento não | Apagar não volta (o servidor apaga os arquivos); definir equipamento se refaz no mesmo diálogo |
| **Laudo pronto** no próprio diálogo: o título vira "Laudo pronto", ilustração `laudo`, quem assina, nome do arquivo, Salvar PDF e **Abrir laudo** | Peak-End (lacuna da Etapa 4); o PDF é pedido com o diálogo aberto e abrir depende de um clique, então o navegador não bloqueia a janela |
| Importação com progresso num lugar fixo no topo de Inspeções; nas outras telas, um aviso que dura até o fim | Toque 7 do `acabamento.md`; Goal-Gradient ("5 de 5" e a barra) |
| A lista enche enquanto importa (recarrega 0,6 s depois de cada termograma pronto) | Doherty: o resultado aparece logo, não só no fim |
| Falhas da importação num aviso só ("3 arquivos não foram importados", com Ver e o motivo de cada um) | Um aviso por arquivo cobria a tela num lote de 40 |
| "Usar dados de demonstração" no vazio de Inspeções e na primeira execução (6 imagens do dataset de estudo, com a licença à vista) | Paradox of the Active User: dá para ver o Pyron funcionando sem ter uma câmera à mão |
| Busca tolerante a acento e maiúscula; `/` foca a busca | Postel ("bodocongo" acha "Bodocongó") |
| Datas relativas no Painel ("vencida há 2 anos", "importada hoje") com a data inteira ao lado ou no `title`; na tabela, a data da captura completa | Na lista, a data da câmera é o que identifica a inspeção |
| Números do Painel sem contagem animada | Decisão da Etapa 1 (sem números animados), que prevalece sobre o toque 15 |
| Barra de status no rodapé (toque 11) não entrou | Custaria 24 px de altura em todas as telas, inclusive na Análise, que precisa caber sem rolar; servidor, câmera e detector já têm lugar (faixa de conexão, Captura, Modelos) |

## 3. Conferido no navegador

Dados de demonstração (`pyron-demo`, porta 8790) e uma pasta vazia de rascunho (`pyron-vazio`, porta 8791,
apagada depois pela Lixeira). Roteiros no Edge sem janela, comandado pelo protocolo de depuração, em 1536 × 816:
- filtro Atenção (4 linhas), busca "bodocongo" (2 linhas, com o acento), busca sem resultado ("Nada para "xyz"
  em Atenção." e Limpar filtros), ordenar por Tmáx (67,5 → 59,7 → 58,6 °C, foco mantido no cabeçalho);
  endereço acompanhando (`?sev=atencao&q=bodocongo`);
- seleção: 2 linhas (cabeçalho em estado misto), marcar todas (10), Esc limpa; menu de contexto no ponteiro
  com 5 itens e foco no primeiro, removido ao fechar;
- laudo de 2 e de 3 inspeções pela seleção (PDF em 0,2 s) e de 1 pela Análise (o mesmo diálogo);
- definir equipamento sem nome (erro "Informe o equipamento." com foco no campo) e com nome (2 inspeções
  ligadas, aviso acima da barra de seleção); apagar 2 com confirmação (15 → 13);
- "Usar dados de demonstração" na lista vazia: 6 imagens em cerca de 0,6 s; com a rede atrasada em 900 ms,
  a faixa mostra "Importando 5 de 5" com a barra em 80 % e a lista enchendo;
- sem conexão (toda chamada `/api/` falhando): faixa do topo e a ilustração `sem-conexao` com Tentar de novo.
- Painel com só imagens normais e sem equipamento: "Nada fora do normal" com a ilustração `pendencias`; o
  teste mostrou que o grupo "sem equipamento" entrava na contagem de equipamentos ("de 1 equipamento",
  "2 equipamentos"), corrigido para "2 inspeções sem equipamento".

## 4. Medidas

**Contraste e alvos** (`js/conferir.js` na própria tela), claro, escuro e toque: 0 falhas em todos os estados.

| Estado | Textos | Alvos |
|---|---|---|
| Painel com dados | 73 | 28 |
| Painel, primeira execução | 23 | 13 |
| Painel, nada fora do normal | 45 | 21 |
| Inspeções com dados | 114 | 44 |
| Inspeções vazia | 14 | 13 |
| Busca sem resultado | 26 | 20 |
| Seleção com a barra | 118 | 48 |
| Diálogo do laudo / laudo pronto | 6 / 5 | 5 / 3 |
| Diálogo Definir equipamento | 6 | 5 |
| Menu de contexto | 5 | 5 |

Falhas achadas e corrigidas no caminho: botão "Tmáx" do cabeçalho com 33 px (ganhou largura mínima),
links "Ver equipamentos" e "Ver as 10 inspeções" com 20 px de altura (alvo de 44 px sem mudar a faixa).

**Proporção de cor** (pixels com saturação > 0,35 e brilho > 0,3; estrutura = azul, violeta e cobalto):

| | Cor de estrutura | Cor total (com miniaturas e severidade) |
|---|---|---|
| Painel antigo | 15,3 % | 16,1 % |
| Inspeções antiga | 16,2 % | 16,9 % |
| Painel novo (claro / escuro) | 0,9 % / 0,8 % | 1,5 % / 1,7 % |
| Inspeções nova (claro / escuro) | 1,1 % / 1,0 % | 2,1 % / 2,7 % |
| Primeira execução | 0,8 % | 1,6 % |

A regra de cor de estrutura abaixo de 2 % passa nas duas telas e nos dois temas.

## 5. Checklist de UX (12 itens)

| # | Item | Painel | Inspeções |
|---|---|---|---|
| 1 | Ação principal em destaque | Importar, único primário | Importar, único primário; ações da seleção em secundário |
| 2 | No máximo 7 opções por grupo | 4 indicadores, 5 próximas | 5 filtros, 4 ações na seleção, 5 no menu |
| 3 | Agrupamento | duas colunas com títulos e linhas | filtros, tabela, barra de seleção |
| 4 | Resposta em < 400 ms | esqueleto da página | esqueleto de lista, botão ocupado, faixa de importação |
| 5 | Convenções | indicadores clicáveis, listas | tabela com seleção, menu de contexto, Esc, `/` |
| 6 | Hover e foco | linhas e links com fundo no hover; anel de foco | idem |
| 7 | Progresso em várias etapas | três passos numerados na primeira execução | "Importando i de n" com barra |
| 8 | Alvos ≥ 44 px em toque | 0 falhas | 0 falhas |
| 9 | Estados vazios | primeira execução; "Nada fora do normal" com `pendencias` | vazio com `inspecoes`; busca sem resultado com `busca`; sem conexão |
| 10 | Informação em blocos | sim | 100 linhas por vez |
| 11 | Hierarquia | Tmáx 35 px, equipamento 20 px, corpo 17, dados 14 | título 24, tabela 14 |
| 12 | Complexidade escondida | aviso de configuração só quando falta algo | ações no menu e na seleção; chip "atual" só vindo do Painel |

**12/12 nas duas telas.**

## 6. Nota pelas 30 Leis de UX (Painel e Inspeções juntos)

| Lei | Nota | | Lei | Nota |
|---|---|---|---|---|
| Aesthetic-Usability | 2 | | Doherty Threshold | 2 |
| Prägnanz | 2 | | Flow | 1 |
| Von Restorff | 2 | | Goal-Gradient | 2 |
| Similarity | 2 | | Serial Position | 2 |
| Proximity | 2 | | Peak-End | 2 |
| Common Region | 2 | | Zeigarnik | 2 |
| Uniform Connectedness | 2 | | Working Memory | 2 |
| Cognitive Load | 2 | | Jakob | 2 |
| Hick | 2 | | Postel | 2 |
| Miller | 2 | | Tesler | 2 |
| Chunking | 2 | | Occam | 2 |
| Choice Overload | 2 | | Pareto | 2 |
| Cognitive Bias | — | | Selective Attention | 2 |
| Fitts | 2 | | Mental Model | 2 |
| Paradox of the Active User | 2 | | Parkinson | 2 |

**57 de 58 nas 29 leis que se aplicam (equivale a 59/60).** O ponto que falta:
- *Flow:* a faixa de importação aparece no topo de Inspeções e empurra a tabela 62 px para baixo enquanto
  importa. Foi mantida no topo porque é o "lugar fixo" pedido e some no fim; a alternativa (sobrepor a
  faixa à tabela) esconderia as primeiras linhas, que são justamente as que acabaram de entrar.

A lacuna *Peak-End* da Análise (fim do laudo) foi resolvida aqui: o diálogo compartilhado vale nas duas telas.

## 7. Toques do `acabamento.md`

Feitos: 7 (progresso fixo), 12 (atalho na dica dos botões Importar: "Ctrl O"), 13 (menu de contexto nas
linhas), 16 (datas relativas no Painel, tabular-nums nas temperaturas), 17 (texto cortado com reticências
e o inteiro no `title`), 19 (primeira execução). Não feitos: 11 (barra de status, motivo na seção 2), 14
(migalhas, fica para quando houver o detalhe do equipamento, Etapa 5b), 15 (decisão da Etapa 1), 18 (tela de
abertura, do lançador, Etapa 6) e 20 (Sobre, Etapa 5d).

## 8. Componentes que mudaram

- `tabela()`: coluna com `link: true` recebe o link da linha; `marcar` põe a caixa de seleção (alvo de 44 px)
  e o "marcar todas" com estado misto; `aoMenu` liga o menu de contexto.
- `menu(gatilho, itens, { em, descartar })`: abre no ponteiro e sai do documento ao fechar.
- `esqueleto.lista()`; a casca usa o esqueleto declarado na rota (`esqueleto: "lista"`).
- `el()` aceita variáveis CSS no `style` (`{ "--sev": … }`); `relativa()` em `base.js`.
- `importar.js`: fila única (o que chega durante uma importação entra no fim), evento `progresso`,
  `mostrarProgressoNaTela()`, `importarDemonstracao()`, falhas resumidas.
- `laudo.js`: `abrirLaudo({ ids, config, responsavel, art })` para uma ou várias inspeções.
- Seta da ordenação: para baixo em ordem decrescente (estava invertida); botões do cabeçalho da tabela com
  a mesma voz de estrutura do resto do cabeçalho.
