# Etapa 3 · Sistema visual e estrutura

Data: 25/10/2026. Código em `app/interface/`, servido em `/nova` (a interface atual continua em `/`).
Catálogo: `/nova/catalogo.html` (`?tema=escuro`, `?toque` simula tela de toque). Capturas:
`docs/interface/capturas/etapa3/`.

**Como abrir no Pyron:** na interface atual, Ctrl+K e "Abrir a interface nova (em construção)".

## 1. Decisões de estrutura

| Decisão | Motivo |
|---|---|
| Pasta e tokens próprios (`app/interface/tokens.css`) | A interface atual precisa ficar intacta até a Etapa 6; trocar a paleta no `tokens.css` antigo mudaria as duas. Na troca, `app/interface` vira a principal e `app/estatico` sai. |
| Módulos ES nativos (`<script type="module">`), sem build | Separa casca, componentes e cada tela em arquivos próprios, com `import` explícito, sem ferramenta nova. O servidor já manda `Cache-Control: no-cache` em tudo que não é `/api`, então a janela do Edge sempre revalida os módulos. |
| Uma tela por módulo em `js/telas/` | A casca carrega a tela sob demanda (`import()`); cada tela exporta `montar(pagina, rota)` e pode devolver a limpeza (intervalos, eventos). |
| Telas ainda não feitas usam `telas/provisoria.js` | Uma só tela provisória para todas as rotas, com link para a mesma tela na interface atual. Cada etapa troca o `modulo` em `js/rotas.js`. |
| Textos do JS em `app/interface/textos.js`; texto fixo da casca no `index.html` | Regra do `CLAUDE.md`. |

```
app/interface/
  index.html        casca (topo, faixa sem conexão, <main>)
  catalogo.html     conferência dos componentes
  tokens.css        fonte única de valores
  base.css          reset, tipografia, foco, movimento, casca
  componentes.css   um bloco por componente
  catalogo.css      só o catálogo
  textos.js         todo texto mostrado pelo JS
  js/base.js        el(), icone(), api(), fmt(), data(), lerNumero(), preferências
  js/icones.js      sprite único de ícones
  js/componentes.js botões, campos, seleção, tabela, estados, aviso, diálogo, menu
  js/rotas.js       mapa de telas, lerRota(), endereco()
  js/casca.js       roteamento, atalhos, busca, soltar arquivo, conexão, sinal, tema
  js/busca.js       busca rápida (Ctrl+K)
  js/importar.js    importação de termogramas de qualquer tela
  js/conferir.js    conferência automática de contraste e alvos
  js/telas/         uma tela por arquivo
```

## 2. Tokens (direção C, cor aço e cobalto)

- **Cor:** `--cobalto-50…900` (ação), neutros ardósia `--n-100…900` + `--branco`, severidade com
  `-fundo` e `-texto`, semânticas derivadas da severidade (sucesso = normal, aviso = atenção,
  erro = urgente), palco grafite, `--borda-campo` (3,0:1), tema escuro completo.
- **Texto:** 6 tamanhos em 1,2 a partir de 14 px: 14 · 17 · 20 · 24 · 29 · 35 (alturas 20 a 44).
  Nada abaixo de 14 px. Família de título `Segoe UI Variable Display`; números com `tabular-nums`.
- **Medidas:** espaço em múltiplos de 4; `--alvo` 44 px (botão, campo, aba, navegação);
  `--alvo-compacto` 36 px (só botão de ícone em tabela e ferramenta), que vira 44 px com
  `pointer: coarse`; `--topo` 56; `--linha` 44; `--detalhe` 400; `--faixa-regioes` 88.
- **Raio:** 4 · 8 · 12 (mais técnico que os 6 · 10 · 16 da interface atual) e pílula só em selo e contador.
- **Movimento:** 150/250/400 ms; `--dur-giro` e `--dur-brilho` para os dois únicos loops (indicador
  de carregamento e brilho do esqueleto); `prefers-reduced-motion` desliga tudo.

## 3. Componentes (`js/componentes.js`)

| Função | Estados e regras |
|---|---|
| `botao({ texto, icone, variante, compacto, soIcone, atalho, contador })` | primário, secundário, fantasma, perigo; ocupado (`ocupado(b, acao)`), desabilitado; só ícone sempre com `aria-label` e dica |
| `campo({ rotulo, tipo, unidade, ajuda, erro, opcoes, area })` | rótulo sempre visível e ligado; ajuda e erro em `aria-describedby`; número aceita vírgula ou ponto (`lerNumero`), porque o campo nativo de número recusa "31,5" |
| `marcar`, `segmentado`, `abas` + `painelAba` | segmentado com contagem no próprio filtro; abas com setas, Home e End (padrão WAI-ARIA) |
| `cabecalho({ titulo, meta, acoes })` | título de página sem subtítulo; um primário por cabeçalho |
| `selo(nivel, { indicativa })`, `.traco`, `.barra`, `indicador(...)` | severidade sempre com o nome do nível; indicador clicável leva à lista filtrada |
| `tabela({ colunas, linhas, severidade, href, ordem })` | cabeçalho fixo, ordenação com `aria-sort`, traço de severidade, linha clicável cujo alvo de teclado é o link da primeira coluna (sem `div` clicável) |
| `esqueleto.linhas/indicadores/tabela/pagina`, `estadoVazio`, `estadoErro` | esqueleto no formato do conteúdo; vazio com frase e ação; erro com a mensagem do servidor e "Tentar de novo" |
| `avisar(texto, { erro, acao })` | para enquanto o mouse ou o foco estão nele; ação "Desfazer"; `atualizar()` para progresso |
| `dialogo(...)`, `confirmar(...)` | `<dialog>` nativo: foco preso, Esc e clique no véu fecham |
| `menu(gatilho, itens)` | `popover` nativo (Esc e clique fora fecham); setas, Home e End; item marcado, perigo, desabilitado, grupo, separador |

## 4. Casca

- **Topo de 56 px:** marca (volta ao Painel), 6 itens de navegação, Buscar (Ctrl K), alertas,
  Configurações. Contador só quando há o que fazer: pendências vencidas na navegação e alertas não
  lidos no sino, com o número no nome acessível ("Pendências, 5 pendências vencidas").
- **Rotas:** `#painel`, `#inspecoes`, `#inspecoes/<id>` (Análise), `#equipamentos`,
  `#equipamentos/<chave>`, `#pendencias`, `#captura/<aba>`, `#modelos/<aba>`, `#configuracoes/<aba>`;
  parâmetros no endereço (`?sev=...`) para filtro e aba.
- **Atalhos:** Ctrl K busca; Ctrl O importar; Alt 1…6 e Alt 0 navegam; `?` lista os atalhos
  (também a tecla do teclado ABNT2); Esc fecha. "Pular para o conteúdo" no primeiro Tab.
- **Arrastar e soltar** termogramas em qualquer tela importa (uma imagem abre a inspeção; várias
  mostram o progresso e "Ver inspeções").
- **Sem conexão:** faixa no topo com "Tentar de novo"; testa o servidor a cada 3 s e some sozinha;
  se o servidor voltou em outra versão, recarrega.
- **Sinal de janela aberta** a cada 20 s (o lançador encerra o servidor quando nenhuma janela avisa).
- **Tema:** lido de Configurações (`/api/configuracoes`), padrão claro.

## 5. Conferência (o critério de pronto)

**Contraste e alvos** (`js/conferir.js`, catálogo inteiro, Edge com área útil 1536 × 816):

| Combinação | Textos conferidos | Abaixo de 4,5:1 (3:1 se grande) | Alvos conferidos | Abaixo do mínimo |
|---|---|---|---|---|
| Claro, mouse | 359 | 0 | 70 | 0 |
| Escuro, mouse | 359 | 0 | 70 | 0 |
| Claro, toque (tudo ≥ 44 px) | 359 | 0 | 70 | 0 |
| Escuro, toque | 359 | 0 | 70 | 0 |

A primeira passada achou 5 alvos de 40 px (link da linha da tabela); corrigido fazendo o link
cobrir a célula. Mínimo com mouse: 44 px, exceto os compactos (36 px).

**Foco visível:** anel cobalto de 2 px com 2 px de folga (`:focus-visible`) em todo controle;
conferido com Tab real no navegador (navegação, botões, busca). O teste
`testes/test_interface_nova.py` falha se alguma regra tirar o contorno sem pôr outro sinal no
lugar; ele achou o campo da busca rápida sem sinal de foco, que ganhou um sublinhado na cor de foco.

**Teclado e fluxo**, conferidos no navegador com os dados de demonstração: Ctrl+K com busca sem
acento ("campina" acha os equipamentos de Campina Grande); Enter abre; Alt+3 vai a Equipamentos;
`?` abre os atalhos centralizados; importar uma imagem criou a inspeção e abriu
`#inspecoes/<id>`; servidor desligado mostrou a faixa, religado a faixa sumiu em até 3 s.

**Projetor** (simulação: tela reduzida para 1280 px e contraste 40 % menor, como sob luz
ambiente; `capturas/etapa3/projetor-tabela.png`): textos de 14 px (11,7 px efetivos) e números
continuam legíveis. As linhas finas da tabela e o fundo claro dos indicadores somem; a leitura se
mantém pelo espaçamento, pelo alinhamento e pelos traços de severidade. Regra para as telas: a
estrutura nunca depende só de linha fina ou de fundo claro.

**Checklist de UX aplicado à casca** (as telas fazem o seu nas Etapas 4 e 5): sem primário global
(um por tela); 6 itens + Configurações na navegação; resposta visual imediata (esqueleto ao trocar
de tela, botão ocupado); convenções (marca leva ao início, busca e alertas à direita); foco e
hover em todo controle; progresso na importação; alvos ≥ 44 px; vazio e erro com ação; atalhos
escondidos atrás de `?` e da busca, não na tela.

**Testes:** 10 novos em `testes/test_interface_nova.py` (entrega em `/nova`, todo módulo importado
existe, toda rota tem tela, regra dura do CSS sem cor, tamanho ou duração fora dos tokens, foco,
tema escuro e escala mínima de 14 px, textos sem emoji). Suíte completa: 242 passam, 8 pulados.

## 6. Pendências

- Todas as telas estão provisórias; a Análise entra na Etapa 4.
- Tema escuro conferido só no catálogo e na casca; a revisão completa fica para a Etapa 6.
- Séries de gráfico (`--serie-*`) definidas, mas sem gráfico ainda; conferir na Etapa 5.
- A importação em lote mostra progresso num aviso; a tela de Inspeções (5a) pode dar um lugar fixo a ele.
