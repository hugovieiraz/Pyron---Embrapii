# Plano: nova interface do Pyron

Refazer **do zero** a interface do Pyron completo (`app/estatico`) como um software profissional de
manutenção: enxuto, técnico, usável no dia a dia. Este arquivo é a lista de tarefas: cada etapa é feita
numa conversa nova, marca as caixas ao terminar e preenche o Registro no fim.

## Quem decide

**O Claude decide tudo de produto e de design.** O Hugo não quer opinar em design: ele vê o resultado
ao fim de cada etapa e só intervém se algo não funcionar para ele. Nenhuma etapa espera escolha dele.
Cada decisão é tomada com critério explícito (Leis de UX, tarefa do usuário, padrão de softwares
profissionais do setor) e registrada com o motivo, para poder ser revista.

Autonomia inclui:
- decidir quais telas existem, juntar, dividir, renomear ou tirar telas;
- cortar ou esconder funções da interface que não servem ao trabalho de manutenção;
- tirar textos explicativos: um software de verdade usa rótulos curtos, unidades, estados claros e
  ajuda pontual (dica no campo, link para o manual), não parágrafos na tela;
- definir navegação, layout, hierarquia, tipografia e componentes.

Limites:
- **Nenhuma rota da API nem dado é apagado.** Função cortada sai só da interface e fica anotada na
  seção "Saiu da interface" do Registro, com o motivo, para poder voltar.
- Seguir o `CLAUDE.md` (tokens, tema claro industrial, estados, movimento, acessibilidade).
- Não quebrar o trabalho do Gabriel: a medição de equipamentos entra na interface nova.

## Como usar (Hugo)

1. Abra uma **conversa nova na pasta `C:\Users\hv392\projetos\termovigia`** para cada etapa.
2. Escolha o modelo e o esforço indicados na etapa (seletor do app, ao lado da caixa de mensagem).
3. Cole o pedido abaixo trocando o número da etapa. No fim, olhe as capturas e use o Pyron; não é
   preciso decidir nada de design.

```text
Siga docs/plano-interface.md e faça a Etapa N inteira, parando no critério de pronto dela.
Antes de começar: git fetch; se houver commits novos no main, integre no branch interface-nova e rode os testes.
No fim: marque as tarefas feitas, preencha o Registro e faça commit e push do branch.
```

Por que uma conversa por etapa: o histórico de uma conversa longa é relido a cada mensagem e gasta o
limite do plano à toa. Cada conversa nova começa só com o CLAUDE.md, a memória e este plano.

## Regras fixas (valem em todas as etapas)

- **Do zero de verdade:** nova arquitetura de informação, navegação, layout e hierarquia; não é
  retocar a interface atual.
- **Em paralelo:** a interface nova é construída em `app/interface/` e servida em `/nova`. A atual
  continua em `/` funcionando até a Etapa 6.
- **Branch:** `interface-nova`, criado a partir do `main`. No início de cada etapa, trazer o `main`
  (merge, nunca forçar). Publicar o branch ao fim de cada etapa; o `main` só recebe na Etapa 6.
- **Skills:** `laws-of-ux` (decidir), `laws-of-ux-review` (nota 0–60), `laws-of-ux-checklist`
  (12 itens), `web-design-guidelines` (revisão técnica), `dataviz` (gráficos e indicadores),
  `frontend-design` (direção, subordinada ao `CLAUDE.md`), `gsd-sketch` (esboços internos).
- **Público:** técnicos e engenheiros de manutenção de subestação; notebook 1536 × 816 e projetor.
- **Textos:** rótulos curtos, técnicos e sóbrios; nada de parágrafo explicando a tela; textos do JS em `textos.js`.
- **Conferência:** `.venv/Scripts/python.exe -m pytest testes -q`, `node --check` nos `.js`, capturas
  em 1536 × 816 pela pré-visualização `pyron-demo` (nunca com os dados reais).
- **Economia:** ler arquivos grandes por partes (o `app.js` tem milhares de linhas); não repetir o que
  já está no Registro.
- **Acabamento de software de verdade** (pedido do usuário, 25/10): seguir a seção 6 de
  `docs/interface/2-direcao.md`. Ilustração própria em vetor nos estados vazio e sem conexão,
  tipografia de estrutura (Bahnschrift), barra de ferramentas e painel de detalhe com seções,
  superfícies planas com linha fina e sombra só no que flutua. A referência é o FLIR Thermal Studio:
  é o nível de acabamento, não uma tela a copiar.
- **Marca:** fica a logo original (decisão do usuário, 25/10). Não redesenhar.

## Etapa 0 · Integrar a medição de equipamentos do Gabriel
Modelo: **Sonnet** ou Opus com esforço **médio**.
- [x] `git fetch`; ler os commits novos do `main` (API, banco, telas).
- [x] Criar o branch `interface-nova` a partir do `main` atualizado; rodar os testes.
- [x] Descrever no Registro a funcionalidade de medição: rotas, dados, ações do usuário.
- **Pronto quando:** testes passam e a medição está descrita para entrar no inventário.

## Etapa 1 · Diagnóstico e nova arquitetura (sem mexer em código)
Modelo: **Opus**, esforço **alto**.
- [x] Inventário de todas as telas atuais (Painel, Inspeções, Análise, Equipamentos, Medição,
      Pendências, Monitoramento, Vídeo, Celular, Modelos, Avaliação, Configurações, Sobre): tarefa do
      usuário, dados, ações, frequência de uso e o que é excesso (texto, opção, tela).
- [x] ~~`laws-of-ux-review` em cada tela: nota 0–60~~ Dispensado pelo usuário (25/10): a interface
      atual é só referência do que existe; as leis entram como restrição da arquitetura.
- [x] `web-design-guidelines`: só o que vira regra de construção (seção 6 do diagnóstico).
- [x] Capturas atuais em 1536 × 816 em `saida/capturas/antes/`.
- [x] **Decidir** a nova arquitetura: telas que ficam, juntam, saem; navegação (no máximo 7 itens no
      primeiro nível); fluxo principal (inspecionar → analisar → pendência → laudo); o que vai para
      Configurações ou para o manual.
- **Entregável:** `docs/interface/1-diagnostico.md` com as decisões e o motivo de cada uma.
- **Pronto quando:** arquitetura decidida e registrada, inclusive a lista do que sai da interface.

## Etapa 2 · Direção visual
Modelo: **Opus**, esforço **alto**.
- [x] Brief: assunto, público, tarefa principal, tom (técnico, industrial, sóbrio).
- [x] Explorar três direções diferentes (estrutura, densidade, hierarquia, tipografia) em esboços
      HTML do **Painel** e da **Análise**, com dados de demonstração.
- [x] Cor por teoria das cores, com liberdade dada pelo usuário (25/10): paleta "aço e cobalto".
- [x] **Escolher** uma, pelos critérios: leitura em 1536 × 816 e no projetor, densidade de dados,
      Leis de UX, consistência com o `CLAUDE.md`. Registrar o motivo.
- **Entregável:** `docs/interface/2-direcao.md` (escolha + motivo) e os esboços em `docs/interface/esbocos/`.
- **Pronto quando:** direção escolhida e registrada.

## Etapa 3 · Sistema visual e estrutura
Modelo: **Opus**, esforço **alto**.
- [x] Tokens da direção escolhida (valor novo entra em `tokens.css` primeiro): `app/interface/tokens.css`.
- [x] Componentes base em `app/interface/`: botões, campos, cartões, tabelas, selos de severidade,
      estados (esqueleto, vazio, erro, sem conexão), diálogos, avisos (e menu, abas, segmentado, indicador).
- [x] Página de catálogo dos componentes, para conferência: `/nova/catalogo.html`.
- [x] Casca: navegação nova, cabeçalho, roteamento, atalhos; servir em `/nova`.
- **Pronto quando:** catálogo completo; foco visível, contraste ≥ 4,5:1 e alvos ≥ 44 px conferidos.

## Etapa 3b · Acabamento profissional (antes da tela de referência)
Modelo: **Opus**, esforço **alto**. Base: `docs/interface/2-direcao.md`, seção 6.
- [ ] Tokens novos em `app/interface/tokens.css`: `--fonte-estrutura`, `--ilu-*` (três faces, acento,
      sombra do chão), fundo da área de trabalho; atualizar o `CLAUDE.md` (seções 1 e 2: três famílias,
      ilustrações, sombra só no que flutua).
- [ ] Tipografia de estrutura na casca e nos componentes: navegação, títulos de seção, cabeçalho de
      tabela, barra de ferramentas. Conferir no Edge a largura condensada da Bahnschrift.
- [ ] Componentes novos: barra de ferramentas (ícone + rótulo, divisor, estado indisponível), seção
      recolhível com faixa de título, trilho de ícones do painel de detalhe.
- [ ] Ilustrações: as seis da seção 6.1 em `app/interface/js/ilustracoes.js`; `estadoVazio()` aceita
      ilustração; nos dois temas.
- [ ] Verificar se a janela do Edge em modo aplicativo aceita barra de título própria (Window Controls
      Overlay) sem mudar o `Pyron.exe`; registrar se dá ou não, sem implementar se exigir mudança no lançador.
- [ ] Catálogo atualizado; contraste e alvos conferidos de novo nos dois temas.
- **Pronto quando:** o catálogo mostra tudo nos dois temas, contraste e alvos com 0 falhas, e a
  captura do estado "Captura sem câmera" ao lado da referência da FLIR mostra o mesmo nível de acabamento.

## Etapa 4 · Tela de referência
Modelo: **Opus**, esforço **alto**.
- [ ] Construir a **Análise** completa na interface nova, ligada à API real, já com o acabamento da Etapa 3b.
- [ ] Capturas antes/depois; `laws-of-ux-checklist` 12/12; nota ≥ 50/60.
- **Pronto quando:** os critérios acima passam. Esta tela vira o padrão das outras.

## Etapa 5 · Demais telas (uma conversa por grupo)
Modelo: **Sonnet** ou Opus com esforço **médio** (o padrão já está decidido).
- Os grupos seguem a arquitetura decidida na Etapa 1 (o agrupamento abaixo é o ponto de partida):
- [ ] 5a · Painel e Inspeções (com a importação)
- [ ] 5b · Equipamentos e Pendências (a medição já entra na Análise, Etapa 4)
- [ ] 5c · Captura (pasta monitorada, vídeo, celular, alertas)
- [ ] 5d · Modelos (em uso, treino, avaliação) e Configurações (com Sobre)
- Em cada grupo: mesmo padrão da Etapa 4, checklist 12/12, capturas antes/depois, testes; estados
  vazio e sem conexão com a ilustração da tela.

## Etapa 6 · Troca e acabamento
Modelo: Opus com esforço **médio**.
- [ ] A interface nova passa a ser a principal (`/`); a antiga sai (ou fica em `/antiga` por uma versão).
- [ ] Tema escuro; revisão final com `web-design-guidelines`; acessibilidade com axe e Lighthouse
      (rodar por `npx`, pedir antes de baixar).
- [ ] Testes, manual e capturas atualizados; merge no `main`; avisar o Gabriel.
- **Pronto quando:** todas as telas com nota ≥ 50/60 e checklist 12/12, testes passando.

## Registro

| Etapa | Data | Feito | Decisões | Pendências |
|---|---|---|---|---|
| plano | 25/10/2026 | Plano criado | Claude decide produto e design; construir em `/nova`, branch `interface-nova` | Etapa 0 quando o push do Gabriel chegar |
| 0 | 25/10/2026 | Branch `interface-nova` a partir do `main` em `b41b802` (commit do Gabriel); 3 correções de integração; 232 testes passam, 8 pulados | Medição não é tela própria: entra na Análise, como dado da região | Avisar o Gabriel das 3 correções; observações para a Etapa 1 abaixo |
| 1 | 25/10/2026 | Inventário de 14 telas, capturas em `saida/capturas/antes/`, arquitetura em `docs/interface/1-diagnostico.md` | Navegação: Painel, Inspeções, Equipamentos, Pendências, Captura, Modelos + Configurações; Nova análise vira ação de Inspeções; Análise é detalhe da inspeção e cabe sem rolar; Monitoramento + Vídeo + Celular = Captura; Modelos + Avaliação; Sobre em Configurações; um primário por tela, sem primário global | Etapa 2: esboços do Painel e da Análise |
| 2 | 25/10/2026 | Brief, paleta nova, três esboços (A mesa, B cartões, C leitura ampla) com capturas e medidas em 1536 × 816; `docs/interface/2-direcao.md` | Direção C: navegação no topo, corpo 17 px, nada abaixo de 14 px, termograma com 33 % da tela; cor "aço e cobalto" (cobalto para ação, ardósia, palco grafite; violeta e índigo saem porque significam frio no termograma) | Etapa 3: tokens novos em `tokens.css`, `CLAUDE.md` seção 1 atualizada, componentes e casca em `/nova` |
| 3 | 25/10/2026 | Tokens, base, 13 componentes, casca (rotas, atalhos, busca Ctrl+K, soltar arquivo, sem conexão, sinal de janela, tema), catálogo, conferência automática, 10 testes; `docs/interface/3-sistema.md` | Pasta e tokens próprios para não mexer na interface atual; módulos ES sem build; número aceita vírgula; contraste 0 falhas em 359 textos e alvos 0 falhas em 70, nos dois temas e em toque | Etapa 4: Análise completa na interface nova |
| plano | 25/10/2026 | Referência de acabamento do usuário (FLIR Thermal Studio) traduzida em regras: `2-direcao.md` seção 6; Etapa 3b criada | Ilustração vetorial própria nos estados; Bahnschrift como fonte de estrutura (já vem no Windows); barra de ferramentas e seções recolhíveis; sombra só no que flutua; logo original mantida, redesenho descartado | Etapa 3b antes da Etapa 4 |
| 3b (em andamento) | 25/10/2026 | Tokens (estrutura, ilustração, ferro, fundo de trabalho); Bahnschrift semicondensada na navegação, abas, cabeçalho de tabela e ferramentas (medido: 15 % mais estreita); barra de ferramentas, seção recolhível, painel com trilho; 6 ilustrações isométricas em `js/ilustracoes.js`; `/nova#captura` mostra o estado sem fonte com dados reais; catálogo: 0 falhas em 395 textos e 83 alvos (claro, escuro, toque); Captura: 0 falhas | Barra de título própria (WCO) não dá: na janela `--app` a API existe mas fica desligada (`visible: false`); só funciona instalando como PWA, o que muda o lançador | Falta: revisar a olho as 5 outras ilustrações nos dois temas, CLAUDE.md seções 1 e 2, comparação lado a lado com a FLIR (`saida/`), marcar as caixas |
| 3b (nuvem) | 25/10/2026 | Ilustrações v2: moldura 4:3 comum, gradiente nas faces, filete de luz, sombra difusa; 6 corrigidas e 4 novas (`analise`, `laudo`, `busca`, `celular`); entrada peça a peça e varredura no `procurando`; 4 tokens `--ilu-*`; capturas em `docs/interface/capturas/etapa3b/`; lista de toques finais em `docs/interface/acabamento.md` | Cada ilustração em até 6 peças (chão, peças, acento por último); loop só em `procurando`; logo original mantida (redesenho fica para designer ou ferramenta de vetor) | Usar as ilustrações nos estados da tabela de `acabamento.md`; CLAUDE.md seções 1 e 2; comparação com a FLIR; decidir a Etapa 3c (`acabamento.md`, parte 5) |

### Medição de equipamentos (Etapa 0)

Chegou no commit `b41b802` (GS87, 25/10): segmentação SAM 2, classificação DINOv2 e medição de
dimensões por imagem única. Não há tela nova: tudo está na **Análise**, sobre cada região.

**Como mede.** Para cada região, o SAM 2 recorta o contorno da peça dentro da caixa; desse contorno
saem as dimensões e a temperatura só da peça (fundo descartado). Escala em metros por dois métodos:
1. *Telemetria óptica* (preferido): distância gravada pela câmera FLIR + campo de visão da lente
   (tabela de lentes T400, Ex, A300, FLIR ONE).
2. *Geometria projetiva* (Criminisi): altura de referência da classe e pontos de fuga da cena.
   Alturas padrão: isolador 0,80 m; bucha 1,25; para-raio 1,20; terminal superior 0,65;
   transformador 1,60; conexão 0,50. O usuário pode trocar.

**Rotas** (todas em `app/servidor.py`; corpo JSON com `regiao_id` ou `caixa` `[x0,y0,x1,y1]`;
sem `regiao_id`, cria região nova):

| Rota | Faz | Resposta |
|---|---|---|
| `POST /api/analises` | Com modelo `sam2-dinov2` ou `pontos-quentes-sam2`, já segmenta e mede cada região; etapa "Segmentação SAM 2" em `etapas` | análise |
| `POST /api/analises/{id}/segmentar` | SAM 2 + medição + térmica da peça; aceita `altura_referencia` (m) ou `metric_ratio` (unidade/px) | `{ok, segmentacao, analise}` |
| `POST /api/analises/{id}/classificar` | DINOv2; troca a classe da região se confiança > 0,60 | `{ok, classificacao, analise}` |
| `POST /api/analises/{id}/metodologia_completa` | As duas acima juntas (DINOv2 usa a máscara do SAM 2) | `{ok, segmentacao, classificacao, analise}` |
| `POST /api/analises/{id}/auto_identificar` | Descobre os ativos na imagem inteira; mantém as regiões manuais e troca as automáticas | análise |
| `GET /api/modelos` | Lista também `sam2-dinov2`, com `disponivel` (acrescentado nesta etapa) | — |
| `PUT /api/analises/{id}` | Preserva `segmentacao` e `classificacao_dinov2` ao editar regiões | análise |

Erros: 503 quando o SAM 2 ou o DINOv2 não estão instalados; 422 caixa inválida ou máscara vazia; 404 região.

**Dados** (gravados na região, dentro da análise):
- `segmentacao.score` (0–1); `segmentacao.contorno` `[[x, y], …]` em coordenadas da matriz térmica.
- `segmentacao.geometria`: `metodo_metrologia` (`telemetria_optica` | `geometria_projetiva_criminisi`),
  `detalhes_metrologia` (câmera, distância, campo de visão), `height_meters`, `mean_width_meters`,
  `max_diameter_meters`, `min_diameter_meters`, `projected_area_m2`, `aspect_ratio`,
  `ref_height_meters`, `distancia_m`, `scale_y_m_per_px`; sem escala, só `length_px`, `width_px`,
  `area_px`, `rotation_deg`.
- `segmentacao.termica_isolada`: `t_max`, `t_min`, `t_media`, `t_mediana`, `desvio_padrao`,
  `delta_t_ativo`, `area_pixels`.
- `classificacao_dinov2`: `classe`, `nome`, `confianca`, `scores` por classe.

**Ações do usuário na interface atual** (Análise):
- Seletor "Detector": `sam2-dinov2` passa a ser o preferido quando instalado; botão "Anexar nova imagem".
- Botão "Auto Identificar (SAM 2 + DINOv2)" na barra de ações.
- Em cada região (ao passar o mouse ou selecionar): Segmentar, Classificar, Metodologia completa.
- Bloco de medição na região: método, altura, largura média, diâmetro máx., área projetada, razão H/W,
  Tmáx da peça, score do SAM 2, classe DINOv2 com barra de confiança.
- Calibração: campo "Altura ref" (m) + Recalcular, e atalhos Isolador 0,80 · Bucha 1,25 · Trafo 1,60.
- Camadas do termograma: Térmica, SAM 2 (contornos e cota "H=…m"), DINOv2 (classe e %); ficam
  guardadas nas preferências.
- Modelos: o cartão ganhou "Vantagens".

**Dependências.** Extra `segmentacao` no `pyproject.toml` (torch, torchvision, `sam2` do GitHub,
opencv-headless, scipy); pesos `modelos/sam2/sam2.1_hiera_small.pt` por `ferramentas/baixar_sam2.py`.
O DINOv2 vem do `torch.hub` (código do GitHub + ~88 MB de pesos na primeira execução). Neste
notebook: torch presente, `sam2` e pesos ausentes, então segmentação e medição ficam indisponíveis;
a classificação DINOv2 carrega.

**Correções feitas na integração** (sem tirar rota):
1. `POST /api/analises` com `sam2-dinov2` sem o SAM 2 instalado dava erro 500; agora 503 com o motivo.
2. Com `pontos-quentes-sam2` sem SAM 2, a análise inteira falhava (503); agora segue sem segmentação
   e com aviso. Era a causa da falha de `test_upload_com_sam2_calculo_instantaneo` neste computador.
3. A interface trocava o detector padrão por `sam2-dinov2` mesmo sem ele instalado (todo envio
   falhava aqui); agora só troca se `disponivel`. `GET /api/modelos` também não quebra mais se o
   torch for barrado pelo Controle Inteligente de Aplicativos.

**Observações para a Etapa 1** (inventário e excesso):
- Textos com emoji (três, no `app.js` e no `index.html`), nomes de modelo na tela ("SAM 2", "DINOv2", "Metodologia Completa"),
  parágrafo de propaganda na área de soltar arquivo; rótulos fixos no `app.js` fora do `textos.js`.
- Para o técnico, a medição é **dado da região** (dimensões estimadas, com o método e a escala),
  não três botões de modelo. A medição é estimativa: mostrar como tal.
- 525 linhas de regras de componente foram coladas no `tokens.css` (duplicam o `estilo.css`).
- Três funções `fetch` quase iguais em vez de `api()`; tabela de alturas padrão repetida em 4 lugares.
- Pastas `src/` e `tests/` paralelas a `nucleo/` e `testes/` (o `pytest -q` roda as duas).

### Saiu da interface (com motivo, para poder voltar)

| Função ou tela | Para onde foi | Motivo |
|---|---|---|
| (lista completa com 17 itens) | `docs/interface/1-diagnostico.md`, seção 5 | Decidido na Etapa 1; cada item sai quando a tela nova correspondente for feita |
