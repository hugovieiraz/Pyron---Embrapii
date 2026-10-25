# Etapa 1 · Diagnóstico e nova arquitetura

Data: 25/10/2026. Base: branch `interface-nova` (`914d8c4`), interface atual em `app/estatico`.
Capturas da interface atual em 1536 × 816: `saida/capturas/antes/01-painel.png` … `14-sobre.png`
(dados de demonstração em `saida/dados_demo`: 10 inspeções de exemplo, 3 equipamentos, 5 pendências).

**Escopo decidido pelo usuário (25/10):** a leitura das telas atuais serve só para saber o que
existe; a interface nova é feita do zero com as regras novas. Por isso não há nota 0–60 nem lista de
correções da interface antiga: as Leis de UX entram como **restrição da arquitetura** (seção 3) e as
regras técnicas como **regra de construção** (seção 6). A nota e o checklist passam a valer para as
telas novas (Etapas 4 e 5).

## 1. Inventário do que existe

Frequência é estimada pela tarefa do técnico de manutenção (não há dado de uso).

| Tela atual | Tarefa do usuário | Dados | Ações | Frequência | Excesso |
|---|---|---|---|---|---|
| Painel | Ver o que precisa de atenção | Contagens (inspeções, críticas, pendências vencidas, inspeções vencidas, alertas); "Atenção agora" (pior região por equipamento); distribuição por severidade; próximas inspeções | Abrir inspeção; ir a filtros; configurar laudo | Diária | Subtítulo explicativo; botão "Ver todas as inspeções" duplica a navegação; números animados de 0 até o valor |
| Nova análise | Enviar termogramas | Arquivos; instalação e equipamento opcionais; recentes; exemplos | Escolher/soltar arquivos (Ctrl+O); lote | Diária | Selo e parágrafo de propaganda do SAM 2; lista "1-2-3-4" de como funciona; exemplos sempre visíveis; é item de menu e também botão global |
| Análise (inspeção aberta) | Revisar regiões, ajustar condições, emitir laudo | Termograma, paleta, escala, isoterma; regiões com Tmáx, ΔT, % da MTA, severidade, critério; medição (dimensões, Tmáx da peça, classe); condições (ambiente, carga); parâmetros radiométricos (emissividade, refletida, distância, umidade, ar); identificação (instalação, equipamento, responsável, ART, observações); etapas com tempo em ms | Desenhar, mover, renomear, mudar classe, remover região; ponto e linha de medição; detectar de novo com outro modelo; auto identificar; segmentar, classificar, metodologia completa; camadas; foto visível e original; exportar PNG e CSV; navegar entre inspeções do equipamento; gerar laudo | Diária, a tela mais usada | Termograma começa a 460 px do topo: em 816 px de altura sobra pouco mais de 350 px para a imagem; três grupos de botões de exibição + três de camadas; dois botões de detecção mais um com nome de modelo; avisos longos no painel direito; barra de etapas em ms |
| Inspeções | Encontrar e abrir inspeções; relatório de várias | Tabela (miniatura, arquivo, local, região crítica, máx., severidade); contagens por severidade | Buscar; filtrar; ordenar; tabela/grade; selecionar várias (laudo conjunto, definir equipamento); exportar planilha; apagar | Diária | Cartões de contagem e filtro segmentado fazem a mesma coisa; vista em grade repete a miniatura da tabela |
| Equipamentos | Acompanhar cada equipamento | Por instalação: estado, nº de inspeções, máx., tendência °C/mês, próxima inspeção | Buscar; abrir | Semanal | Subtítulo explicativo; cartões de contagem |
| Equipamento (detalhe) | Ver histórico e tendência | Estado, máx. na última, tendência, próxima inspeção; gráfico da máxima ao longo do tempo; máxima por tipo de peça | Adicionar imagens; relatório do equipamento; abrir inspeção pelo gráfico | Semanal | Legenda explicativa sob o gráfico |
| Pendências | Acompanhar anomalia até a correção verificada | Severidade, equipamento e região, detectada, prazo, situação (aberta, programada, corrigida, verificada, descartada), OS, responsável, histórico | Buscar; filtrar; atualizar situação, OS e responsável; ver a inspeção | Semanal | Subtítulo explicativo; cartões de contagem duplicam o filtro |
| Monitoramento | Vigiar a pasta da câmera e avisar o responsável | Estado, pasta, última verificação, analisadas; fonte; regra de alerta (nível mínimo, não repetir); responsáveis (WhatsApp); prévia da mensagem; alertas | Ligar/desligar; verificar agora; cadastrar responsáveis; abrir WhatsApp com a mensagem; marcar alerta | Configuração rara; alertas quando ligado | Opções "Em breve" (RTSP, Atlas SDK, WhatsApp Business) e cartão "Em desenvolvimento": função que não existe na tela; textos de ajuda em cada cartão |
| Vídeo ao vivo | Simular a câmera analisando um vídeo | Vídeo, ritmo, velocidade, intervalo, detector, escala travada; quadros analisados | Enviar vídeo; ver quadros; salvar quadro como inspeção | Rara (demonstração) | Parágrafo explicando a simulação; explicação do ritmo |
| Câmera do celular | Usar o celular como câmera ao vivo | QR, estado da conexão | Ligar/desligar a conexão | Rara (demonstração) | Lista de 4 passos e dois parágrafos de aviso |
| Modelos | Escolher o detector; instalar e treinar | Cartões de modelo (tipo, versão, classes, treino, métricas, vantagens, limitações); treinos | Usar modelo; instalar pacote; treinar; ver treino | Rara (administração) | Subtítulo longo; instruções de terminal |
| Avaliação | Comparar detectores treinados | Métricas, curvas, erros por foto | Importar resultados do Colab; apagar | Rara (desenvolvimento do modelo) | Instruções do caderno do Colab |
| Configurações | Ajustar laudo, critério e sistema | Empresa, logotipo, responsáveis técnicos; critério de severidade; biblioteca de componentes (MTA); aparência; dados, backup | Salvar; enviar logo; backup e restauração; abrir pasta | Rara | Notas explicativas em cada cartão |
| Sobre | Saber a versão | Versão; texto de apresentação; roteiro do produto; estado da versão | — | Rara | Página de marketing ("Ver o defeito antes da falha", "Para onde vai") |

Elementos fixos de hoje: barra lateral com 11 itens em 2 grupos + Sobre + cartão "Detector em uso";
topo com trilha, busca (Ctrl+K), chips "Servidor local" e "Monitoramento", sino de alertas e botão
"Nova análise"; faixa "sem conexão".

## 2. Problemas transversais (o que a interface nova não repete)

1. **Texto explicando a tela** em todas as páginas (subtítulo de 2–3 linhas) e em quase todo cartão.
2. **Dois primários por tela**: "Nova análise" fixo no topo + o primário da página.
3. **Excesso de níveis de navegação**: 11 itens no primeiro nível, três deles de demonstração ou de
   desenvolvimento do modelo (Vídeo, Celular, Avaliação).
4. **A tela principal não cabe**: na Análise, cabeçalho + etapas + barras de ferramentas ocupam
   ~460 px antes do termograma.
5. **Função que não existe aparece como opção** ("Em breve", "Backlog").
6. **Nome de algoritmo como rótulo** (SAM 2, DINOv2, "Metodologia Completa", "Pontos quentes (regra)").
7. **Contagem duplicada como cartão e como filtro** (Inspeções, Equipamentos, Pendências).
8. **Números animados** de 0 até o valor: numa captura ou no projetor aparece o número errado.

## 3. Leis de UX que limitam a arquitetura

- **Hick / Miller:** primeiro nível com **no máximo 7 itens**; cada tela com **uma** decisão principal.
- **Pareto:** o fluxo diário (Painel → Inspeções → Análise → Pendência → Laudo) recebe espaço,
  atalhos e o primário; Modelos e Configurações ficam no fim da navegação, sem destaque.
- **Von Restorff:** **um** botão primário por tela, nenhum global no topo.
- **Jakob:** padrão de software de manutenção (lista de ativos, ordens de serviço, inspeções com
  detalhe): barra lateral à esquerda, trilha no topo, busca no topo, tabela com filtro acima,
  detalhe abrindo do item. Nada de padrão novo sem ganho declarado.
- **Fitts:** ações frequentes da Análise junto da imagem; alvos ≥ 32 px no mouse e ≥ 44 px em toque
  (regra do `CLAUDE.md`); ação de apagar longe das frequentes.
- **Working Memory:** na Análise, imagem, regiões e severidade visíveis juntas, sem rolar; o
  contexto (equipamento, data) fica no cabeçalho em todas as abas.
- **Selective Attention / Occam:** cor forte só para severidade e termograma; nada de selo
  promocional, opção "em breve" ou texto de ajuda permanente.
- **Doherty:** resposta visual em < 400 ms em toda ação; detecção e laudo com progresso.

## 4. Nova arquitetura

### 4.1 Navegação (primeiro nível: 6 itens + Configurações)

| # | Item | Conteúdo | Vem de |
|---|---|---|---|
| 1 | **Painel** | O que precisa de atenção hoje | Painel |
| 2 | **Inspeções** | Lista + importação + Análise como detalhe da inspeção | Inspeções, Nova análise, Análise |
| 3 | **Equipamentos** | Ativos por instalação, histórico, tendência, relatório | Equipamentos |
| 4 | **Pendências** | Anomalias até a correção verificada | Pendências |
| 5 | **Captura** | Pasta monitorada, vídeo, celular e alertas | Monitoramento, Vídeo ao vivo, Câmera do celular |
| 6 | **Modelos** | Detectores, treino e avaliação | Modelos, Avaliação |
| — | **Configurações** (no rodapé da barra) | Empresa e responsáveis, critério, componentes, aparência, dados e backup, sobre | Configurações, Sobre |

Ordem pelo fluxo de trabalho (Serial Position: o mais usado primeiro, a administração no fim).

**Motivos das junções:**
- *Nova análise → Inspeções.* Importar é ação sobre a lista de inspeções, não um lugar. Fica como
  primário de Inspeções ("Importar termogramas"), por arrastar e soltar em qualquer tela e por Ctrl+O.
  A Análise é o detalhe de uma inspeção (`Inspeções › FLIR1552.jpg`), como em todo software de
  registros; deixa de ser item de menu.
- *Monitoramento + Vídeo + Celular → Captura.* As três são **fontes de imagem que chegam sozinhas**
  (pasta vigiada, vídeo quadro a quadro, câmera do celular); os alertas são o resultado delas. Uma
  tela com abas `Pasta monitorada · Vídeo · Celular · Alertas` em vez de três itens de menu, dois
  deles de uso raro.
- *Modelos + Avaliação → Modelos* com abas `Em uso · Treino · Avaliação`. Avaliar é parte do ciclo
  de vida do modelo; ninguém avalia sem estar decidindo qual modelo usar.
- *Sobre → Configurações › Sobre:* versão, pasta de dados, licenças e crédito do dataset. O texto de
  apresentação e o roteiro do produto saem da interface (vão para o README).

### 4.2 Elementos fixos

- **Barra lateral** (largura de layout por token): logo, 6 itens, Configurações no rodapé. Recolhe
  para ícones (Ctrl+B, lembrado por visitante) para dar largura ao termograma. Contadores só quando
  há algo a fazer (pendências vencidas, alertas não lidos); sem contador de total.
- **Topo** de uma linha: trilha à esquerda, busca (Ctrl+K) no centro, sino de alertas à direita.
  Sem botão primário global, sem chip "Servidor local" (a faixa "sem conexão" já cobre a falha).
- **Faixa sem conexão** no topo com "Tentar de novo" (regra do `CLAUDE.md`).

### 4.3 Fluxo principal

`Painel` (o que está vencido ou grave) → `Inspeções › Importar` (uma imagem abre direto na Análise;
várias entram na lista com progresso) → `Análise` (revisar regiões, condições, identificação) →
**pendência criada pelo sistema** quando a severidade pede (a Análise mostra "Pendência aberta ·
prazo dd/mm" com link) → `Gerar laudo` (primário da Análise) → `Pendências` (OS, responsável,
situação até verificada; a reinspeção normal sugere "verificada").

### 4.4 Telas e o primário de cada uma

| Tela | Primário | Estrutura |
|---|---|---|
| Painel | Importar termogramas | Linha de 4 indicadores clicáveis (críticas, pendências vencidas, inspeções vencidas, alertas); "Atenção agora" ocupa a maior área; próximas inspeções e distribuição por severidade ao lado. Sem números animados. |
| Inspeções | Importar termogramas | Filtro de severidade com contagem no próprio filtro (sem cartões), busca, ordenação, tabela com miniatura; seleção múltipla abre barra de ações (laudo conjunto, definir equipamento, exportar, apagar). |
| Análise | Gerar laudo | Cabeçalho de uma linha (arquivo, equipamento, data, severidade, anterior/próxima). Abaixo, a altura toda: termograma à esquerda (~62 % da largura) com uma barra de ferramentas única (selecionar, região, ponto, linha · paleta · escala · camadas · foto); painel à direita com abas `Regiões · Condições · Identificação`. A lista de regiões mostra Tmáx, ΔT/% MTA e severidade; a região selecionada abre o detalhe (critério, ação recomendada, **dimensões estimadas** com método e escala, pendência). "Detectar de novo" vira menu com o modelo; exportar vai para menu "Mais". O termograma inteiro cabe em 1536 × 816 sem rolar. |
| Equipamentos | — | Agrupados por instalação, tabela compacta (estado, última, máx., tendência, próxima inspeção) com filtro "vencidas / com anomalia / esquentando". |
| Equipamento | Relatório do equipamento | Indicadores (estado, máx. na última, tendência, próxima inspeção), gráfico da máxima com pontos na cor da severidade, inspeções do equipamento em tabela. |
| Pendências | — | Filtro por situação com contagem, tabela (severidade, equipamento e região, prazo, situação, OS, responsável); atualizar em painel lateral, não em diálogo. |
| Captura | Ligar (na aba ativa) | Abas Pasta monitorada · Vídeo · Celular · Alertas. Só fontes que funcionam. |
| Modelos | Usar este modelo (no cartão escolhido) | Abas Em uso · Treino · Avaliação. |
| Configurações | Salvar (por seção) | Abas Empresa e responsáveis · Critério · Componentes · Aparência · Dados e backup · Sobre. |

### 4.5 Medição de equipamentos (trabalho do Gabriel)

Entra como **dado da região**, não como tela nem como três botões de modelo:
- no detalhe da região: "Dimensões (estimadas)": altura × largura média, diâmetro máx., área
  projetada, com o **método** ("pela distância da câmera" ou "pela altura de referência") e o valor
  de referência editável; Tmáx da peça (sem fundo) ao lado da Tmáx da caixa;
- ação "Medir" no detalhe da região quando o modelo de segmentação está instalado; sem ele, a ação
  some e Modelos indica o que falta;
- "Identificar componentes" no menu "Detectar de novo" (o `auto_identificar`);
- contornos e classe como opções do menu Camadas (Regiões, Contornos, Classe, Rótulos).
Todas as rotas continuam (`segmentar`, `classificar`, `metodologia_completa`, `auto_identificar`).

### 4.6 Textos

- Título da tela sem subtítulo. Rótulo curto + unidade (`Tmáx °C`, `Carga %`, `Emissividade`).
- Ajuda só no ponto de uso: dica no campo (`title`/texto de apoio de uma linha) e link "Manual".
- Nome de algoritmo só em Modelos. Na operação, o que a coisa faz: "Detectar", "Medir", "Identificar".
- Estado vazio: uma frase + a ação (ex.: "Nenhuma inspeção. Importar termogramas").

## 5. O que sai da interface (as rotas e os dados continuam)

| Função ou texto | Para onde foi | Motivo |
|---|---|---|
| Item de menu "Nova análise" e botão global "Nova análise" | Primário de Inspeções e Painel; Ctrl+O; soltar arquivo em qualquer tela | Importar é ação, não lugar; um primário por tela |
| Subtítulos explicativos de todas as telas e notas dos cartões | Manual | Rótulo curto + ajuda pontual |
| Lista "1-2-3-4" de como a análise funciona | Manual | Explicação, não tarefa |
| Selo e parágrafo "Auto-Segmentação SAM 2 & Metrologia" | Fora | Propaganda; o resultado aparece na região |
| Botões "Segmentar (SAM 2)", "Classificar (DINOv2)", "Metodologia Completa", "Auto Identificar (SAM 2 + DINOv2)" | "Medir" no detalhe da região; "Identificar componentes" no menu Detectar | Nome de modelo não é ação do técnico; 4 botões viram 2 |
| Botões de camada "Térmica / SAM 2 / DINOv2" e grupo "Tudo / Peças / Pontos" | Um menu "Camadas" | 6 controles sempre visíveis para algo de uso raro |
| Barra de etapas com tempo em ms | Configurações › Sobre (diagnóstico) | Informação de desenvolvimento |
| Exemplos para testar (sempre visíveis) | Só no estado vazio de Inspeções | Conteúdo de demonstração |
| Cartões de contagem em Inspeções, Equipamentos e Pendências | Contagem dentro do filtro | Mesma função duas vezes |
| Vista em grade de Inspeções | Fora (miniatura fica na tabela) | Duplica a tabela |
| Cartão "Detector em uso" na barra lateral | Modelos › Em uso; metadado da inspeção | Não é navegação |
| Chip "Servidor local" | Fora (faixa "sem conexão" quando cai) | Estado normal não precisa de aviso |
| Opções "Em breve" (RTSP/ONVIF, Atlas SDK, WhatsApp Business) e cartão "Em desenvolvimento" | README (roteiro) | Função que não existe não aparece |
| Página Sobre de apresentação ("Ver o defeito antes da falha", "Para onde vai", "Estado desta versão") | README; versão e licenças em Configurações › Sobre | Marketing fora do software |
| Instruções do Colab e do terminal (Avaliação, Treino) | Manual | Texto longo de desenvolvedor |
| Passo a passo de 4 itens do celular | Uma linha + QR; detalhe no manual | Ajuda no ponto de uso |
| Números animados de 0 até o valor | Fora | Mostra valor errado durante a animação |

## 6. Regras de construção (revisão técnica, para as Etapas 3–5)

Da lista Web Interface Guidelines (Vercel), o que a interface atual já mostrou que precisa de regra:
- Nada de `transition: all` (há em `app/estatico/tokens.css:551` e `:732`): transição só de
  `transform` e `opacity`, como o `CLAUDE.md` pede.
- Não tirar o contorno de foco sem anel no lugar (`estilo.css:169`, `:833`, `:876` dependem de sombra):
  usar `:focus-visible` com o anel do token.
- Clique só em `button`/`a` (há `div` com `onclick` em `app.js:3635`).
- Reticências com o caractere `…` em textos de espera (19 ocorrências de `...`).
- Números com `font-variant-numeric: tabular-nums` em tabela e indicador; datas e números por `Intl`.
- Estado da tela no endereço (`#inspecoes?sev=critico`, aba ativa da Análise), para voltar e compartilhar.
- Apagar com desfazer (aviso com "Desfazer") em vez de diálogo de confirmação, onde a API permitir.
- Sem regra de componente no `tokens.css`: só tokens.
- Regras em inglês que não valem aqui: "Title Case" (português usa só a inicial maiúscula).

## 7. Para a Etapa 2

Esboçar o **Painel** e a **Análise** nesta arquitetura. Pontos a resolver na direção visual: densidade
da tabela de regiões ao lado do termograma em 1536 × 816; leitura no projetor (tamanho mínimo dos
números); como mostrar "estimado" nas dimensões sem texto longo.
