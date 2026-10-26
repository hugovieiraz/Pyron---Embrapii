# Etapa 4 · Análise (tela de referência)

Data: 25/10/2026. Rota `/nova/#inspecoes/<id>`, ligada à API real. Código em `app/interface/js/telas/analise.js`
e `app/interface/js/analise/` (contexto, palco, faixa, painel, cabeçalho); layout em `app/interface/telas.css`.
Capturas: `docs/interface/capturas/etapa4/` (antes e depois, claro e escuro, inspeção inexistente). As imagens
térmicas das capturas são do dataset de estudo ScienceDB 10185 (CC BY-NC-SA), dos dados de demonstração.

## 1. Estrutura em 1536 × 816

| Faixa | Altura | Conteúdo |
|---|---|---|
| Topo | 56 px | navegação (Inspeções ativa) |
| Cabeçalho | 64 px | ‹ equipamento (título) › · severidade · instalação · data · arquivo · câmera · "3 de 3" · pendência em aberto · "Salvo às …" · Detectar de novo · Mais · **Gerar laudo** |
| Barra de ferramentas | 52 px | Selecionar (V) · Região (R) · Ponto (P) · Linha (L) │ Paleta · Escala (com Isoterma) · Camadas (com Foto) │ zoom |
| Palco | o resto | termograma ajustado à área (692 × 519 px nesta inspeção), escala de cores ao lado |
| Faixa de regiões | 88 px | uma ficha por região, da mais grave para a mais fria |
| Painel de detalhe | 400 px de largura | trilho: Resumo ou Região · Condições · Identificação · Pendência |

O termograma inteiro cabe sem rolar (pedido da Etapa 1); na Análise antiga ele começava a 460 px do topo.

## 2. Decisões e motivo

| Decisão | Motivo |
|---|---|
| Painel mostra **Resumo** sem seleção e o **detalhe da região** quando uma é selecionada, na mesma aba | Working Memory: o detalhe aparece onde o olho já está; uma aba a menos (Hick) |
| Seleção ligada nos dois sentidos: clicar na caixa ou na ficha, setas ←/→ percorrem, as outras caixas ficam a 60 % | Uniform Connectedness e Selective Attention (toque 3 do `acabamento.md`) |
| Mira com leitura ao vivo (temperatura do pixel junto ao cursor) e marcador na escala | É o que o termografista faz o tempo todo (toques 1 e 2) |
| Região: desenhar arrastando, mover arrastando, redimensionar pelas alças; volta para Selecionar depois de desenhar | Padrão de editores de imagem (Jakob); uma região por vez evita caixas por engano |
| Apagar região com **Desfazer** no aviso, sem diálogo; apagar a inspeção inteira pede confirmação | Flow: só o irreversível interrompe (toque 8) |
| Edições salvam sozinhas, com "Salvando…" e "Salvo às 21:16" no cabeçalho; o formulário em edição não é reconstruído | Doherty e Flow (toque 9); o foco não sai do campo enquanto salva (conferido) |
| Isoterma dentro de Escala e Foto dentro de Camadas (atalhos I e F) | Hick: a barra ficou com 4 ferramentas e 3 menus de exibição (eram 9 botões) |
| Escala: Automática, Cena inteira ou Manual; os limites da barra são editáveis com clique | Ajuste direto onde o valor aparece (toque 2) |
| Zoom na roda do mouse no ponto do cursor, espaço + arrastar move, 0 encaixa; acima de 300 % o pixel fica nítido | Leitura de pixel em imagem de 160 × 120 (toque 4) |
| Rótulos sobre a imagem só para regiões fora do normal e para a selecionada | Selective Attention: 9 rótulos cobririam o termograma |
| Cabeçalho mostra pendência aberta ou vencida e "temperatura estimada pela cor" quando não é radiométrica | Zeigarnik (o que falta fazer à vista) e confiança na leitura antes do laudo |
| "Detectar de novo" é um menu com os modelos; o que não está instalado aparece indisponível com o motivo | Função que não existe não se esconde quando é escolha de modelo: o técnico precisa saber por que não pode |
| Medição de dimensões (SAM 2) entra como seção "Dimensões estimadas" da região, com "Medir" só se instalado | Decisão da Etapa 1 (dado da região, não três botões de modelo) |
| Laudo: diálogo com responsável do cadastro e ART; sem responsável, explica e leva ao cadastro | O servidor só gera laudo com responsável do cadastro |
| Cortina visível × térmica (toque 5) não entrou: Foto troca a imagem inteira | A foto da FLIR C5 não é alinhada ao termograma; a cortina mostraria peças fora do lugar |

## 3. Conferido no navegador (dados de demonstração)

Com o mouse, na pré-visualização em 1536 × 816: selecionar pela caixa e pela ficha; mira com leitura
(26,9 °C) e marcador na escala; desenhar região (criada, salva, selecionada, ferramenta volta para
Selecionar); Delete e Desfazer (região volta no lugar); mover a caixa (medida de novo: 42,6 → 36,1 °C);
ponto de medição (P1 67,5 °C); zoom pela roda (144 %, rótulos com tamanho constante); isoterma; paleta
Arco-íris guardada na inspeção e mantida ao recarregar; ambiente digitado com vírgula (31,5) salvo sem
perder o foco; Detectar de novo com outro modelo (região à mão mantida); diálogo do laudo com e sem
responsável (PDF de 228 KB pela rota); aba Pendência aberta pelo link do cabeçalho; inspeção inexistente;
imagem sem radiometria. Os dados de teste foram desfeitos depois.

## 4. Medidas

**Contraste e alvos** (`js/conferir.js` na própria tela): 0 falhas em 70 textos e 44 alvos, claro, escuro e
toque; na imagem sem radiometria, 0 falhas em 56 textos e 38 alvos.

**Proporção de cor** (pixels com saturação > 0,35):

| | Cor fora do termograma | Cobalto | No termograma (dado) |
|---|---|---|---|
| Análise nova (claro / escuro) | 1,4 % / 1,5 % | 0,9 % | 16,8 % |
| Análise antiga | 18,3 % | 9,4 % | 5,3 % |

A regra de cor de estrutura abaixo de 2 % passa; a cor da tela agora é o termograma.

## 5. Checklist de UX (12 itens)

| # | Item | Resultado |
|---|---|---|
| 1 | Ação principal em destaque (Gerar laudo, único primário, canto superior direito) | ✅ |
| 2 | No máximo 7 opções por grupo (ferramentas 4, exibição 3, cabeçalho 3) | ✅ depois de levar Isoterma e Foto para os menus |
| 3 | Elementos relacionados agrupados (barra com divisores, seções do painel, faixa) | ✅ |
| 4 | Resposta em < 400 ms (esqueleto, botão ocupado, "Salvando…", ilustração `analise` procurando ao detectar) | ✅ |
| 5 | Convenções (ferramentas em cima, inspetor à direita, tira de miniaturas embaixo) | ✅ |
| 6 | Hover e foco em todo controle | ✅ |
| 7 | Progresso em fluxo de várias etapas | ✅ (não se aplica) |
| 8 | Alvos ≥ 44 px em toque | ✅ (0 falhas) |
| 9 | Estados vazios (sem regiões, sem pontos, sem pendência, inspeção inexistente) | ✅ |
| 10 | Informação em blocos (seções com faixa de título) | ✅ |
| 11 | Hierarquia (Tmáx em 35 px, título 20 px, corpo 17, dados 14) | ✅ |
| 12 | Complexidade escondida (parâmetros da câmera e referência recolhidos; menus) | ✅ |

**12/12.**

## 6. Nota pelas 30 Leis de UX

2 = cumpre, 1 = parcial, — = não se aplica.

| Lei | Nota | | Lei | Nota |
|---|---|---|---|---|
| Aesthetic-Usability | 2 | | Doherty Threshold | 2 |
| Prägnanz | 2 | | Flow | 2 |
| Von Restorff | 2 | | Goal-Gradient | — |
| Similarity | 2 | | Serial Position | 2 |
| Proximity | 2 | | Peak-End | 1 |
| Common Region | 2 | | Zeigarnik | 2 |
| Uniform Connectedness | 2 | | Working Memory | 2 |
| Cognitive Load | 2 | | Jakob | 2 |
| Hick | 2 | | Postel | 2 |
| Miller | 2 | | Tesler | 2 |
| Chunking | 2 | | Occam | 2 |
| Choice Overload | 1 | | Pareto | 2 |
| Cognitive Bias | — | | Selective Attention | 2 |
| Fitts | 2 | | Mental Model | 2 |
| Paradox of the Active User | 2 | | Parkinson | 2 |

**54 de 56 nas 28 leis que se aplicam (equivale a 58/60).** Os dois pontos que faltam:
- *Choice Overload:* "Detectar de novo" lista 7 modelos com nomes técnicos; a escolha do modelo padrão é
  da tela Modelos (Etapa 5d), que pode recomendar um e deixar os outros em "Mais modelos".
- *Peak-End:* o fim do fluxo (laudo gerado) é só um aviso; dá para fechar com a ilustração `laudo` e
  "Abrir PDF" num retorno próprio quando a tela de Inspeções existir (Etapa 5a).

## 7. Toques do `acabamento.md`, parte 2

Feitos: 1 (mira), 2 (escala ligada ao cursor, limites editáveis com clique), 3 (lista ↔ imagem, 60 %,
alças), 4 (zoom e arrasto), 6 (botão ocupado), 8 (Desfazer), 9 ("Salvo"), 10 (soltar arquivos com a
ilustração `inspecoes`). Não feitos: 5 (cortina, motivo na seção 2) e 7 (progresso de importação num
lugar fixo, que é da tela Inspeções, Etapa 5a).
