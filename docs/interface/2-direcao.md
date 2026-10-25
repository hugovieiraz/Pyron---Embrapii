# Etapa 2 · Direção visual

Data: 25/10/2026. Esboços em `docs/interface/esbocos/` (abrir no navegador; `#painel` ou `#analise`
no fim do endereço). Capturas em 1536 × 816: `docs/interface/esbocos/capturas/`. Os esboços usam
dados fictícios e um termograma sintético (`comum/termograma.js`); nenhuma imagem do dataset de estudo.

## 1. Brief

- **Assunto:** manutenção preditiva por termografia em subestação; o termograma e a severidade são o
  conteúdo, o resto é instrumento.
- **Público:** técnicos e engenheiros de manutenção; notebook 1536 × 816 no escritório e projetor
  na reunião de programação da manutenção.
- **Tarefa principal:** abrir uma inspeção, conferir onde está o calor, quanto passou do limite e o
  que fazer; emitir o laudo.
- **Tom:** técnico, industrial, sóbrio. Nada que pareça propaganda.
- **Arquitetura** (Etapa 1): Painel, Inspeções, Equipamentos, Pendências, Captura, Modelos +
  Configurações; um primário por tela; a Análise cabe sem rolar.

## 2. Cor (decidida com liberdade dada pelo usuário em 25/10)

Antes: azul-índigo de ação, violeta em subtom, barra lateral azul com degradê para violeta, palco do
termograma índigo profundo. Novo: **"aço e cobalto"** (`esbocos/comum/cores.css`).

**Raciocínio (teoria das cores aplicada ao dado):**
1. O dado já ocupa quase todo o círculo cromático: a paleta ferro vai de preto a violeta, magenta,
   laranja, amarelo e branco; a severidade vai de verde a amarelo, laranja, vermelho e carmim.
2. A interface usa o que sobra: **azul-cobalto (~214°)** para ação e seleção e **neutros ardósia**
   (mesmo matiz, croma baixo) para o resto. Análogos entre si, harmonia sem disputar com o dado.
3. **Violeta e índigo saem.** No termograma eles significam frio; um realce violeta na tela passa a
   ler como "região fria" ao lado da imagem.
4. **Palco do termograma em grafite neutro (#121418), sem matiz.** Um entorno índigo tinge, por
   contraste simultâneo, as áreas frias da imagem e muda a leitura da temperatura pela cor.
5. **60-30-10:** branco e ardósia clara na maior área, ardósia média em texto e bordas, cobalto só em
   ação e seleção. A barra de navegação deixa de ser um bloco grande de cor saturada (o que pedia a
   barra lateral azul): a cor forte da tela é sempre do dado.
6. **Severidade:** mantida a ordem de semáforo (convenção do setor, Jakob). Amarelo de atenção
   escurecido para #B58900, porque o anterior (#D9A40B) não passava de 3:1 como marca sobre branco.
   Toda marca de severidade vem com o nome do nível ao lado: a cor nunca é o único sinal.

**Contraste medido (WCAG):**

| Par | Razão | Mínimo |
|---|---|---|
| Texto #161B22 sobre branco | 17,3:1 | 4,5 |
| Texto secundário #424B59 / terciário #5A6474 sobre branco | 8,8:1 / 6,0:1 | 4,5 |
| Botão: branco sobre cobalto #1F5BC4 | 6,3:1 | 4,5 |
| Item ativo da navegação #194BA3 sobre #EEF4FF | 7,1:1 | 4,5 |
| Texto dos selos de severidade sobre o fundo do selo | 6,2 a 8,3:1 | 4,5 |
| Marcas de severidade sobre branco (normal, atenção, programar, urgente, imediato) | 3,4 / 3,2 / 3,2 / 4,7 / 7,8:1 | 3,0 |
| Contorno de campo #8B95A5 sobre branco | 3,0:1 | 3,0 |
| Anel de foco #3570DB sobre branco | 4,7:1 | 3,0 |
| Texto sobre o palco #C8CDD6 / #8D94A1 sobre #121418 | 11,6:1 / 6,0:1 | 4,5 |

## 3. As três direções

A paleta é a mesma nas três, para comparar só estrutura, densidade e hierarquia.

| | A · Mesa de operação | B · Cartões de trabalho | C · Leitura ampla |
|---|---|---|---|
| Ideia | Painéis de altura total separados por linhas finas, sem cartões; tabela como forma principal; lista, imagem e detalhe lado a lado | Blocos brancos sobre fundo frio; números grandes; a região selecionada abre no lugar, dentro da lista | Navegação no topo (toda a largura para o conteúdo); uma escala de texto acima; poucos itens por tela, leitura de pé |
| Navegação | Barra lateral 216 px | Barra lateral 248 px | Barra no topo, 56 px |
| Corpo do texto | 14 px | 14 px | 17 px |
| Análise | Regiões 300 px · imagem · detalhe 344 px | Imagem · inspetor 432 px (lista + detalhe) | Imagem com ferramentas flutuantes · detalhe 400 px · regiões em faixa abaixo |

**Medido em 1536 × 816** (`esbocos/comum/medir.js`, Edge sem janela com área útil 1536 × 816):

| Medida | A | B | C |
|---|---|---|---|
| Termograma na Análise | 580 × 435 px | 694 × 521 px | **745 × 559 px** |
| Fração da tela ocupada pelo termograma | 20 % | 29 % | **33 %** |
| Regiões visíveis sem rolar | 7 de 7 (com % da MTA) | 6 de 7 | 7 de 7 (Tmáx) |
| Itens de "Atenção agora" visíveis | 6 de 6, 7 colunas | 6 de 6 | 6 de 6 |
| Menor texto | 12 px | 12 px | **14 px** |
| Textos em 12 px ou menos | 30–35 % | 36–37 % | **0 %** |
| Controles visíveis na Análise | 32 | 31 | **23** |

## 4. Escolha: C · Leitura ampla

**Motivos, pelos critérios do plano:**
1. **Leitura em 1536 × 816 e no projetor.** O termograma fica 65 % maior em área que em A e 15 %
   maior que em B. Nenhum texto abaixo de 14 px; temperaturas de destaque em 30 px. Numa sala com
   projetor, 12 px some; em A e B um terço dos textos tem 12 px.
2. **Densidade de dados suficiente.** A Análise mostra todas as regiões com a temperatura e o detalhe
   completo da selecionada; o Painel mostra os 6 itens de atenção. A densidade de A só se paga nas
   telas de lista, e ela entra lá (ajuste 2).
3. **Leis de UX.** Hick: 23 controles na Análise contra 31–32. Fitts: botões de 44 px no
   cabeçalho e ferramentas de 40 px junto da imagem. Von Restorff: a temperatura da região é o maior
   elemento da tela depois da imagem. Jakob: navegação superior com 6 itens é padrão comum em
   software de gestão; a busca, os alertas e as configurações ficam à direita, onde se espera.
4. **`CLAUDE.md`.** Tema claro, tokens, severidade só em selo/faixa/barra, um primário por tela,
   palco escuro para o termograma: tudo mantido. Muda o que a seção 2 explica (cor) e a barra
   lateral, que sai.

**Por que não A:** melhor densidade, mas termograma pequeno (20 % da tela) e um terço do texto em
12 px; serve à mesa, não ao projetor. **Por que não B:** meio-termo sem vantagem própria; o
inspetor de 432 px tira largura da imagem e esconde a 7.ª região.

**Ajustes na direção escolhida (entram na Etapa 3):**
1. Painel com todos os itens de atenção (já aplicado no esboço), rolando dentro da coluna se passar de 6.
2. Telas de lista (Inspeções, Equipamentos, Pendências) em tabela, como em A, com corpo de 14 px e
   linha de 44 px (alvo de toque), cabeçalho da tabela fixo.
3. A faixa de regiões abaixo da imagem mostra Tmáx e um traço de severidade; o % da MTA e o ΔT ficam
   no detalhe. Teclas ← → percorrem as regiões.
4. Paleta, escala e foto entram como um controle compacto no canto superior direito do palco (o
   esboço só tem as ferramentas de desenho e camadas).
5. Etiquetas sobre a imagem só para regiões fora do normal (como no esboço), em 14 px.

## 5. O que muda no sistema (Etapa 3)

- **Cores:** `tokens.css` passa a ter `--cobalto-*` no lugar de `--azul-*` e `--violeta-*`; neutros
  ardósia em 9 tons; `--borda-campo`; palco grafite; `--atencao` #B58900. O `CLAUDE.md` seção 1 e a
  memória de preferências de design são atualizados junto.
- **Tipografia:** corpo em 17 px (`--t-3`) nas telas de leitura e 14 px (`--t-2`) em tabela e
  controle; 12 px (`--t-1`) sai das telas (fica só no laudo em PDF, se precisar). Mesma proporção 1,2.
- **Layout:** `--topo` 56 px com a navegação; `--lateral` sai; painel de detalhe 400 px;
  faixa de regiões 88 px.
- **Família:** Segoe UI Variable continua (é a do sistema, nítida em 125 %); Cascadia Mono só para
  caminho, comando e leitura bruta.

## 6. Acabamento: parecer software de verdade (25/10, pedido do usuário)

Referência trazida pelo usuário: o FLIR Thermal Studio (software da câmera), aba Live Stream sem
câmera conectada. Não é para copiar a tela; é o **nível de acabamento**: os elementos parecem parte do
programa, não imagens coladas. O que produz essa impressão, decomposto em regras para o Pyron:

| Na referência | Por que parece software de verdade | Regra no Pyron |
|---|---|---|
| Ilustração vetorial (câmera, notebook, caminho pontilhado) no estado vazio | Desenhada no estilo e nas cores do próprio programa; mostra a tarefa sem texto longo | Ilustrações próprias em SVG, feitas com os tokens, nos estados vazio, sem conexão e primeira execução (6.1) |
| Abas e títulos de seção em maiúsculas, fonte condensada, letras espaçadas | Separa a estrutura do programa do conteúdo; lembra painel de instrumento | Segunda voz tipográfica, só na estrutura (6.2) |
| Barra de ferramentas fina: ícone + rótulo, divisores verticais, ação indisponível em cinza | Ações sempre no mesmo lugar; o estado de cada uma é visível | Componente barra de ferramentas, uma por tela |
| Painel à direita com trilho de ícones e seções recolhíveis com faixa cinza no título | Inspetor de propriedades, padrão de software técnico (Jakob) | Painel de detalhe com seções recolhíveis e título em faixa |
| Superfícies planas separadas por linha de 1 px; quase nenhuma sombra | Calmo e plano; a profundidade fica para o que flutua | Sombra só em menu, diálogo, aviso e ilustração (6.3) |
| Preto, cinzas e um acento | A cor vai para o dado e para o ponto de interesse do desenho | Já é a regra 60-30-10 da seção 2 |
| Marca, abas, menu do usuário e botões da janela numa barra só | Programa, não página web aberta no navegador | Verificar se a janela do Edge em modo aplicativo aceita barra de título própria (Window Controls Overlay); se não aceitar, a barra superior fica como está |

### 6.1 Ilustrações

- SVG inline desenhado no projeto, num arquivo só (`js/ilustracoes.js`, como `icones.js`). Nada de
  banco de imagens, captura de tela ou PNG.
- Projeção isométrica (30°), luz de cima à esquerda: face de cima clara, lateral esquerda média,
  lateral direita escura. Três tons tirados dos neutros (tokens `--ilu-*`), que trocam no tema escuro.
- **Um acento por ilustração**, no ponto de interesse: o visor do termovisor com a paleta ferro ou um
  ponto quente na peça. Cobalto não entra (é cor de ação, não de desenho).
- Sombra no chão em elipse suave, de opacidade baixa (token). Ligações em linha pontilhada.
- 240 a 320 px, centrada, acima de no máximo 3 linhas de instrução e de uma ação. Uma por tela.
- Movimento: entrada de 400 ms (opacidade e deslocamento). Só o estado "procurando câmera" pode ter o
  pontilhado correndo, porque é indicador de carregamento. `prefers-reduced-motion` desliga tudo.
- Primeiras seis: Captura sem câmera (termovisor apontado para uma peça de subestação); Inspeções sem
  imagem (pasta com termogramas); Pendências zeradas (prancheta com verificação); Equipamentos vazio
  (transformador com etiqueta); sem conexão com o servidor (notebook com o cabo solto); Modelos sem
  detector (placa de processamento).

### 6.2 Tipografia de estrutura

- **Bahnschrift**, a DIN que vem no Windows 10 e 11 (`C:\Windows\Fonts\bahnschrift.ttf`, conferido
  neste computador): nada a baixar, sem licença à parte. Fonte variável com largura condensada.
- Só na estrutura: itens da navegação, títulos de seção dentro de painéis, cabeçalho de tabela,
  rótulos da barra de ferramentas. Maiúsculas com espaçamento de letra nos três primeiros; botões em
  caixa normal. Mínimo de 14 px, como o resto.
- Conteúdo, campos e textos continuam em Segoe UI Variable; leituras e caminhos em Cascadia Mono.
  Ficam três famílias com papéis separados (o `CLAUDE.md` passa de duas para três na Etapa 3b).
- Fora do Windows (página do celular), cai para a fonte do sistema: token `--fonte-estrutura` com
  alternativas.

### 6.3 Superfície e sombra

- Área de trabalho em cinza muito claro; barras, painéis e tabelas em branco, separados por linha de
  1 px. Hierarquia por plano e linha, não por sombra.
- Sombra só no que flutua (menu, diálogo, aviso) e no chão das ilustrações. Cartão não tem sombra.

### 6.4 Marca

Atualizado em 25/10, depois: a **logo nova** foi aprovada pelo usuário (`marca/vetor/`, ver o
`LEIA-ME.md` de lá): o símbolo da referência dele vetorizado sem redesenho, com a palavra em Chakra Petch
Bold. Ela substitui a logo raster. O esboço anterior (`esbocos/marca.html`) continua descartado.
Na interface nova a barra do topo usa a logo horizontal (`logo-cor.svg` no claro, `logo-escuro.svg` no
escuro, 32 px de altura); como há versão para fundo escuro, acabou a regra do ladrilho branco.
