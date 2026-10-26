# Pyron: regras do projeto

Software de manutenção preditiva por termografia (FastAPI local + interface web em `app/estatico/`,
núcleo em `nucleo/`, treino em `ml/`, lançador `Pyron.exe` em `lancador/`). Textos em português do Brasil.

## 0. Interface principal (`app/interface`, em `/`; histórico em `docs/plano-interface.md`)

- Código em `app/interface/`, servido em `/` desde a 0.8.0 (`/nova` redireciona para `/`). A interface
  anterior (seções 1 a 3) fica em `/antiga` por esta versão, com link em Configurações › Sobre; sai na próxima.
- **Fonte única: `app/interface/tokens.css`** (direção em `docs/interface/2-direcao.md`, sistema
  em `docs/interface/3-sistema.md`): cobalto só em ação e seleção, neutros ardósia, palco grafite,
  sem violeta nem índigo (no termograma significam frio), navegação no topo, nada abaixo de 14 px,
  alvo 44 px (compacto 36 px só com mouse).
- **Três famílias** com papéis separados: Segoe UI Variable (conteúdo), **Bahnschrift semicondensada**
  (`--fonte-estrutura`: navegação, abas, títulos de seção, cabeçalho de tabela e barra de ferramentas;
  maiúsculas espaçadas, menos nos rótulos de ferramenta) e Cascadia Mono (caminhos e leituras).
- **Proporção de cor:** cor de estrutura (cobalto) abaixo de 2 % da tela, medida nas capturas em toda
  etapa; o cobalto marca só a ação principal, a aba atual e a seleção. O resto da cor é dado
  (termograma, severidade) ou o acento das ilustrações. A FLIR é referência de sobriedade, não estilo a copiar.
- **Superfície:** área de trabalho em `--fundo-trabalho`; barras, painéis e tabelas brancos com linha
  de 1 px. **Sombra só no que flutua** (menu, diálogo, aviso) e no chão das ilustrações; cartão sem sombra.
- **Estrutura de tela de trabalho:** `barraFerramentas()` (uma por tela) + área + `painelDetalhe()`
  (trilho de ícones e `secao()` recolhível com faixa de título).
- **Ilustrações** (`js/ilustracoes.js`, `estadoVazio({ ilustracao })`): isométricas, feitas só com
  tokens `--ilu-*` e `--ferro-*`, um acento térmico por desenho, nunca cobalto; onde cada uma entra está
  em `docs/interface/acabamento.md`. Movimento contínuo só no estado `procurando`.
- Módulos ES sem build: `js/base.js`, `js/componentes.js`, `js/casca.js`, uma tela por arquivo em
  `js/telas/` (mapa em `js/rotas.js`). Textos do JS em `app/interface/textos.js`. Layout das telas em
  `telas.css`. **Tela de referência: a Análise** (`js/telas/analise.js` + `js/analise/`, `docs/interface/4-analise.md`):
  contexto com `ouvir()/mudou()`, salvamento automático com "Salvo", Desfazer em vez de confirmar; as
  outras telas seguem esse padrão. Testes visuais: `?conferir`, `?tema=escuro`, `?toque` no endereço.
- **Telas de lista** (padrão de Inspeções, `docs/interface/5a-painel-inspecoes.md`): filtro segmentado com a
  contagem dentro, busca sem acento, filtros e ordem no endereço (`history.replaceState`), `tabela()` com
  `marcar` e `aoMenu`, barra de seleção flutuante embaixo (anexada ao `body`), a tabela rola por dentro.
  Regras de leitura da lista (situação atual, severidade) em `js/situacao.js`; laudo só por `js/laudo.js`;
  importação só por `js/importar.js`; busca das listas por `campoBusca()`; acompanhamento de pendência só
  por `js/pendencia.js`; gráfico no tempo por `js/grafico.js` (uma série, pontos na cor da severidade).
  Lista com painel ao lado (Pendências): `tabela({ aoEscolher })`; lista agrupada: `tabela({ grupo })`.
- **Tela com abas** (Captura, Modelos, Configurações): `telaComAbas()` em `js/telaAbas.js` e um módulo por aba
  em `js/captura/`, `js/modelos/` ou `js/configuracoes/` com `montar(no, ctx)` devolvendo a limpeza; trocar de aba
  não recarrega (endereço por `history.replaceState`). Critério e componentes salvam com botão (recalculam tudo). Só aparece fonte que funciona. Teste com o vídeo `dados/video_demo.mp4` em `pyron-vazio`. Estado vazio sem dados: pré-visualização `pyron-vazio` (porta 8791,
  `saida/dados_vazio`, apagar pela Lixeira depois).
- Conferir: `testes/test_interface_nova.py` (regra dura do CSS, foco, módulos), axe (WCAG 2.2 AA, Etapa 6) e o catálogo
  `/catalogo.html` com "Conferir acessibilidade" (claro, `?tema=escuro`, `?toque`).

## 1. Sistema de design da interface anterior (`/antiga`; fonte única: `app/estatico/tokens.css`)

- **Direção estética:** software industrial claro. Fundo branco e neutros frios levemente azulados;
  azul-índigo como cor de ação; violeta só em subtom (barra lateral, realces). A cor forte fica
  para os dados: termograma e severidade. Sem emoji, sem sombra pesada, sem gradiente fora da
  barra lateral. Tema padrão: claro. Escuro é opcional (Configurações › Aparência).
- **Cores:** primária `--azul-*` (ação `--azul-600`), destaque `--violeta-*`, neutros `--n-100…900`,
  semânticas `--sucesso/--aviso/--erro/--info` com `-fundo` e `-texto`, cada uma com versão escura.
  Severidade (`--normal … --imediato`) é dado: selos, faixas e barras, **nunca botão**.
- **Tipografia:** 6 tamanhos em proporção 1,2 (`--t-1` 12 → `--t-6` 30, alturas `--a-*`), 3 pesos
  (400/600/700), 2 famílias (Segoe UI Variable; Cascadia Mono só para caminhos, comandos e leituras).
- **Espaçamento:** múltiplos de 4 px (`--e-1 … --e-16`). **Raio:** `--r-p`, `--r-m`, `--r-g`.
  **Sombras:** `--sombra-1/2/3`. **Tamanhos de layout:** `--col-*`, `--alvo*`, `--medida` etc.
- **Regra dura:** nenhuma tela usa cor, espaçamento, tamanho, raio, sombra ou duração fora dos
  tokens. Precisou de valor novo? Entra em `tokens.css` primeiro. Cores no canvas vêm dos tokens
  (`corNivel()` em `app.js`).
- **Marca** (logo nova de 25/10, vetores em `marca/vetor/`; a raster antiga, `marca/pyron_logo.png`, fica só como registro): mão e texto
  `#0A0A0A`, chama `#EF5F0C` / `#FEC31F` / `#A70F3C`; em fundo escuro, mão e texto `#E6EAF0`
  (`*-escuro.svg`). Palavra em Chakra Petch Bold (SIL OFL) convertida em contornos. Os PNG, os SVG da
  barra e o `pyron.ico` saem de `python marca/gerar_marca.py` (rasteriza no Edge sem janela); não editar
  os arquivos gerados à mão. O ícone dentro do `Pyron.exe` só muda ao recompilar (`lancador/construir.py`).
  O palco do termograma é índigo profundo (`--palco`), inclusive no tema claro.

## 2. Hierarquia e estados

- Um botão primário (azul cheio) por área; secundário com contorno; fantasma só texto.
- Toda tela tem: carregamento com **esqueleto** (não spinner no meio da tela), **vazio** com texto
  útil e ação, **erro** com o que aconteceu e "Tentar de novo", e a faixa **sem conexão** no topo.
  Componentes: `esqueleto.*`, `estadoVazio()`, `estadoErro()` em `app.js`.
- Acessibilidade: foco visível (anel azul), contraste ≥ 4,5:1 (texto secundário mínimo `--n-600`),
  rótulo em todo campo, alvos ≥ 44 px em telas de toque (`@media (pointer: coarse)`).

## 3. Movimento

- Toque/hover 150 ms (`--dur-rapida`); troca de página e de aba 250 ms (`--dur-media`);
  conteúdo grande 400 ms (`--dur-lenta`).
- Listas: entrada escalonada de 30 ms, no máximo 6 itens (`animarEntrada()`).
- Só `transform` e `opacity`. Saída mais rápida que a entrada (`--ease-saida`).
- `prefers-reduced-motion` desliga tudo. Loop infinito só em indicador de carregamento.

## 4. Regras permanentes

- A solução mais simples que resolve; nada de biblioteca sem justificar (a interface é JS puro, sem build).
- Componente que aparece 2+ vezes vira função compartilhada.
- Texto que o JavaScript mostra fica em `app/estatico/textos.js` (`TEXTOS`); o texto fixo das telas
  fica no `index.html`. Nada de texto solto espalhado no código.
- Nomes de variáveis e funções: o projeto nasceu em português e mantém o português, por coerência
  (o template geral pede inglês; migrar tudo seria uma mudança à parte, só se o usuário pedir).
- Depois de mexer na interface: `pytest -q`, `node --check app/estatico/app.js` e conferir as telas
  no navegador (tema claro e escuro). Para demonstração sem tocar nos dados reais:
  `python app/iniciar.py --porta 8790 --sem-navegador --dados <pasta>`.
- Ao terminar cada etapa, resumir em 3 linhas o que foi feito e o que ficou pendente.
- Commit e push: autorizados desde a 0.7 para as mudanças feitas (ver a seção 5). O repositório é
  https://github.com/hugovieiraz/Pyron---Embrapii.
- O dataset ScienceDB 10185 é só para estudo (CC BY-NC-SA): as imagens em si não vão para o
  repositório. Capturas de tela que mostram essas imagens (manual) podem ir, com o crédito e a
  licença no README (decisão do usuário: o projeto é compartilhado para estudo).
- O `Pyron.exe` precisa continuar pequeno (≈100 KB, sem recursos embutidos): o Controle Inteligente
  de Aplicativos do Windows bloqueou uma versão de 390 KB. Nunca mexer nessa proteção.

## 5. Estrutura, comandos e fluxo de trabalho

**Dois aplicativos no mesmo repositório:**
- `app/` + `nucleo/` + `ml/`: o Pyron completo (inspeções, equipamentos, pendências, laudos, monitor, celular).
- `apresentacao/`: versão enxuta para apresentações (abas Análise · Avaliação do modelo · Câmera do
  celular). Código próprio; reaproveita só `app/celular.py`, `app/estatico/celular.*` e
  `nucleo/enquadrar.py`. Tem os próprios `estatico/tokens.css` e `estilo.css` (tema claro só). Na
  apresentação o modo celular é **só identificação** (sem leitura da barra de cores).

**Comandos** (na raiz, sempre com o Python do `.venv`):
- Testes: `.venv/Scripts/python.exe -m pytest -q` (pastas `testes` e `tests`, ≈255 testes, ~40 s).
- Pyron para testar sem dados reais: pré-visualização `pyron-demo` (`.claude/launch.json`, porta 8790,
  dados em `saida/dados_demo`). Apresentação: pré-visualização `apresentacao` (porta 8792).
- Abrir de verdade: atalhos "Abrir Pyron" e "Pyron Apresentação" da área de trabalho (`pythonw.exe -m apresentacao`).
- Pacote portátil da apresentação (para outro computador): `.venv/Scripts/python.exe -m apresentacao.empacotar`
  (gera pasta + .zip na Área de Trabalho; apagar os anteriores antes). Nota técnica para o leitor:
  `apresentacao/LEIA-ME-TECNICO.txt`.

**Git:** a interface nova entrou no `main` na Etapa 6 (0.8.0, 26/10/2026). Trabalhar num branch
(`interface-nova` ou um novo por assunto); publicar com push do branch e fast-forward do `main`
(`git push origin <branch>:main`). Antes de publicar, `git fetch` e conferir
`git log HEAD..origin/main`: o colaborador GS87 (Gabriel) também envia commits direto ao `main`
(Postgres, Grafana, BI). Havendo commits dele, integrar com merge (nunca forçar) e rodar os testes.

**Ambiente** (Windows 11 com Controle Inteligente de Aplicativos ligado):
- Detecção na placa de vídeo pelo `onnxruntime-directml` (DLLs assinadas pela Microsoft). O PyTorch
  com CUDA e o pacote `onnx` são bloqueados de forma intermitente pelo SAC: não depender deles em
  tempo de execução (testes que precisam deles se pulam sozinhos).
- Tela de 1536 × 816 úteis: janelas `--start-maximized`; conferir telas nesse tamanho.
- A janela do Edge em modo aplicativo guarda arquivos em cache: o servidor manda `Cache-Control: no-cache`
  em tudo que não é `/api` (middleware `sem_cache_da_interface`), então arquivo novo entra sem `?v=`.
