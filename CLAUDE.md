# Pyron: regras do projeto

Software de manutenção preditiva por termografia (FastAPI local + interface web em `app/estatico/`,
núcleo em `nucleo/`, treino em `ml/`, lançador `Pyron.exe` em `lancador/`). Textos em português do Brasil.

## Base de Conhecimento e Segundo Cérebro (Shlomo)
- O projeto é embasado pelo cofre Zettelkasten **Shlomo** (`D:/hd_central/Antigravity projetos/Shlomo/`) e pelo índice
  canônico `SHLOMO_KNOWLEDGE_BASE.md`.
- **Requisitos e física:** consultar `Pyron Embrapii - Visão Geral e Roteiro de Requisitos.md` e
  `Pyron Embrapii - Referências e Limiares de Temperatura.md` para normas ABNT NBR 15572/15866, NETA MTS, física de
  degradação e modelo de Arrhenius.
- **Engenharia de Software:** respeitar estritamente Clean Code (SOLID, funções pequenas, SRP, Boy Scout Rule) conforme
  documentado no atlas do Shlomo.

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
- **Medir foto** (Captura › Medir foto, `js/captura/medir.js`; roteiro em `docs/07_roteiro_medicao_geral.md`): medida
  de objeto qualquer em foto comum. Núcleo em `nucleo/medicao/` (`medir()` no `__init__`; `geometria.py` só NumPy;
  `profundidade.py` Depth Anything 3 Metric (padrão, Apache 2.0) e MoGe-2 (reserva); `segmentar.py` SAM 2.1 pelo `transformers`; `plano_ref.py` sem modelo, por homografia;
  `referencia_auto.py` acha o post-it rosa (8 cm) pela cor;
  `modelos.py` pesos em `modelos/medicao/`). API `/api/medicao`, `/api/medicao/estado`, `/api/medicao/plano`, `/api/medicao/referencia` e `/api/medicao/comparar`
  (mede nos dois modelos, sem e com referência, e grava em `registro.py`: fotos com os bytes originais). O celular só tira e envia a foto:
  `/c/{token}/medir` (`app/estatico/medir_celular.*`, QR em "Fotos do celular"), original sem recomprimir; a medida é sempre no
  computador. Fotos guardadas na faixa com setas (`/api/medicao/fotos`), zoom, nome do objeto e "Medir: Os dois / Com / Sem post-it";
  histórico e CSV em Modelos › Medição.
  Vídeo: "Abrir vídeo" ou "Gravar vídeo" no celular; `video_keyframes.comparar_video` (quadros nítidos, pista seguida, mediana por
  modelo e modo), `/api/medicao/video/comparar`, vídeos em `<dados>/medicao/videos/`. Estado, erro e o botão Instalar: Modelos › Medição
  (`js/modelos/medicao.js`, `/api/medicao/instalar`; pacotes que faltam + pesos por `nucleo/medicao/instalar.py`, que nunca troca o torch). Placa de vídeo: seção em Modelos › Medição (`modelos.placa()`, motivo de não usar) e
  `python -m nucleo.medicao.placa --instalar` com o Pyron fechado (testa o PyTorch com CUDA numa pasta à parte antes de trocar).
  Licenças: só MIT e Apache 2.0 (nada CC BY-NC, AGPL, GPL; Depth Pro fora). Sem os pesos, a aba abre no modo
  "Retângulo de referência".
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
  os arquivos gerados à mão. O ícone dentro do `Pyron.exe` só muda ao recompilar (`lancador/construir.py`); desde 26/10 é só o símbolo, sem fundo
  (mão clara com contorno escuro), e a abertura do .exe é a logo solta com sombra (`marca/abertura.png`), sem janela.
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

**Site (`site/`, 28/10/2026):** landing (`index.html`) e teste no navegador (`teste.html`), HTML/CSS/JS puro, estático
(publicável em GitHub Pages). Valores só de `site/tokens.css`: palco grafite do app como fundo, cor da chama da marca
na ação principal (no app a ação continua cobalto), paleta ferro e severidade só como dado. O teste gera um termograma
sintético de três buchas e classifica com a mesma regra de `nucleo/analise.py` (critério padrão, MTA da bucha 95 °C):
mudou a regra ou o critério padrão, mudar `site/teste.js` junto. O botão de download fica "em breve" até haver
instalador; o e-mail de contato em `site/site.js` é provisório. Imagens em WebP (`site/img/`): fotos de contexto
ilustrativas vindas do modelo de design e telas reais capturadas do `pyron-demo`. Pré-visualização: `esbocos`
(porta 8794) em `/site/`.

**Time operacional** (Configurações › Empresa e time): `responsaveis` no `config.json` com perfil (engenheiro ou
técnico), função, registro, e-mail, telefone e `assina`. Só quem assina (com registro) aparece no laudo e pode ser o
padrão; o campo Responsável da pendência sugere todo o time. Cadastros antigos viram engenheiro que assina.
Alertas do monitor: quem recebe pelo WhatsApp é quem do time tem `alertas` (nível a partir do qual recebe, com
telefone válido); a Pasta monitorada só mostra a lista (`_destinatarios()` em `servidor.py`). A lista antiga
`monitoramento.destinatarios` migra para o time na primeira leitura (mesmo telefone ou membro novo que não assina).

**Dois aplicativos no mesmo repositório:**
- `app/` + `nucleo/` + `ml/`: o Pyron completo (inspeções, equipamentos, pendências, laudos, monitor, celular).
- `apresentacao/`: versão enxuta para apresentações (abas Análise · Avaliação do modelo · Câmera do
  celular). Código próprio; reaproveita só `app/celular.py`, `app/estatico/celular.*` e
  `nucleo/enquadrar.py`. Tem os próprios `estatico/tokens.css` e `estilo.css` (tema claro só). Na
  apresentação o modo celular é **só identificação** (sem leitura da barra de cores).

**Comandos** (na raiz, sempre com o Python do `.venv`):
- Testes: no dia a dia `.venv/Scripts/python.exe -m pytest -q -m "not lento"` (≈370 testes, ~85 s); antes de publicar no
  `main`, `pytest -q` completo (≈390, 2 a 3 min). `lento` = carrega PyTorch e os modelos de medição ou do SAM 2. O que
  sobra de tempo vem dos testes de medição com cenas sintéticas de 1000 × 800 (1 a 4 s cada); medido em 28/10/2026.
- Pyron para testar sem dados reais: pré-visualização `pyron-demo` (`.claude/launch.json`, porta 8790,
  dados em `saida/dados_demo`). Apresentação: pré-visualização `apresentacao` (porta 8792).
- Medição em foto: tudo de uma vez `.venv/Scripts/python.exe -m nucleo.medicao.instalar` (ou o botão em Modelos › Medição). À mão: `.venv/Scripts/pip install --no-deps git+https://github.com/microsoft/MoGe.git` (mais o
  extra `[medicao]` do `pyproject.toml`), DA3 `pip install --no-deps --ignore-requires-python git+https://github.com/ByteDance-Seed/Depth-Anything-3.git`
  (só a rede; a API dele puxa o `evo`, GPL), pesos `python -m nucleo.medicao.modelos --baixar da3 vitl small`, avaliação no
  gabarito `python -m ml.avaliar_medicao` (fotos e medidas reais em `testes/gabarito/`); fotos por pasta (uma
  subpasta por objeto e `medidas.csv`): `python -m ml.avaliar_medicao --pasta <pasta> --modelos vitl`.
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
- Detecção na placa de vídeo pelo `onnxruntime-directml` (DLLs assinadas pela Microsoft). Atenção: o `rapidocr-onnxruntime` depende do
  `onnxruntime` comum (só CPU), que ocupa o mesmo módulo e tira o DirectML. Em 28/10/2026 o `.venv` estava assim;
  corrigido com `pip uninstall -y onnxruntime` e `pip install onnxruntime-directml==1.24.4` (repetir depois de
  instalar ou atualizar o RapidOCR; conferir com `onnxruntime.get_available_providers()`).
  Imagem que chega sozinha (`FONTES_AUTOMATICAS`: monitor, celular, vídeo): o modelo escolhido roda na placa
  quando pronta (`_na_placa`), sem SAM 2 (fica no botão Medir da Análise) e sem o `sam2-dinov2` (vira pontos
  quentes, com aviso em `avisos_analise`); com o monitor ligado, modelo e OCR carregam ao subir (`_preaquecer`). Leitura de imagem estimada: OCR com detecção
  até 320 px e cache de recortes (`OCRPreguicoso`), projeção na paleta por cor distinta e mediana do OpenCV, todos
  conferidos idênticos nas imagens de `app/dados_app`. O PyTorch
  com CUDA e o pacote `onnx` são bloqueados de forma intermitente pelo SAC: não depender deles em
  tempo de execução (testes que precisam deles se pulam sozinhos).
- Segunda máquina de desenvolvimento (GS87, desde 30/10/2026): Acer Nitro com GTX 1650 4 GB, CUDA 13.3 e **SAC
  desligado**. Prova de bloqueio do SAC só vale numa máquina com ele ligado. Testes rápidos lá: ~190 s.
- **Versão 0.9** (servidor, tablet PWA, laudo Typst, TensorRT, Tauri): plano por fases com portão em `docs/v09/`;
  diagnóstico e classificação das rotas por perfil em `docs/v09/0-diagnostico.md`. Branch por fase (`v09-f0-…`).
- **Modo servidor** (F1, `docs/v09/1-servidor.md`, implantação em `docs/servidor/implantacao.md`):
  `python -m app.iniciar --modo servidor --proxy 127.0.0.1`, com login. O modo local continua o padrão e sem login.
  `app/acesso.py` é a dependência global do FastAPI: **toda rota nova entra em `_GRUPOS_DAS_ROTAS`** (público,
  leitura, envio, revisão, laudo, administração, só local), senão `testes/test_acesso.py` falha e o servidor
  responde 403. Perfis vêm do time (`usuario`, `administrador`, `senha_hash`, nunca devolvido; até 20 pessoas):
  técnico vê, envia e comenta; engenheiro revisa; quem assina emite laudo (assinado por quem entrou e registrado
  em `laudos_emitidos`); administrador configura. Na interface, `pode()` de `js/base.js` só esconde o que o perfil
  não faz; a regra fica no servidor. A Análise salva com `revisao` (409 se outra pessoa gravou antes).
  Banco no esquema 3 com WAL; backup agendado por `python -m app.backup`. Contas: `python -m app.acesso usuario`.
- **Tablet** (F2, `docs/v09/2-tablet.md`, passo a passo em `docs/servidor/tablet.md`): HTTPS pelo Tailscale
  (`tailscale serve --bg 8766` + `--porta-proxy 8766`: tudo que chega por essa porta é de fora e em HTTPS).
  PWA só no modo servidor (`js/aplicativo.js`): `manifest.webmanifest` (cores = tokens `--superficie` e
  `--fundo-trabalho` do tema claro), ícones `icone-app-*` de `python marca/gerar_marca.py --pwa`, `sw.js` rede
  primeiro, cache com a versão no nome, nunca `/api` nem PDF. **Módulo JS novo entra na lista `CASCA` do `sw.js`**
  (`testes/test_pwa.py` confere). Toque: pinça, dois dedos e toque duplo no palco; `toqueLongo()` nas listas.
  Pontos de quebra em `em` (os testes proíbem `px`): 80em (topo e ferramentas só com ícone) e 60em (retrato:
  navegação por ícones, Análise e Pendências empilhadas). Conferir tablet em 1024 × 768, 1180 × 820, 820 × 1180 e 800 × 1280.
- **Laudo em Typst** (F3, `docs/v09/3-laudo.md`): `app/laudo_typst.py` com as assinaturas de `app/laudo.py`; motor
  por `laudo.motor` no `config.json` ("reportlab" padrão até o usuário aprovar o visual; Typst indisponível cai no
  reportlab). Modelo em `app/laudo/modelo.typ` + `partes/`, fontes só de `app/laudo/fontes/` (Noto Sans + Noto Sans
  Math para ≥, OFL). **Texto do usuário só entra por `dados.json`**: nunca montar código Typst com texto, nunca `eval`.
  Mudou o conteúdo do laudo em `laudo.py`? Mudar `montar_dados()` e o modelo junto (os dois têm de dizer o mesmo).
- Tela de 1536 × 816 úteis: janelas `--start-maximized`; conferir telas nesse tamanho.
- Janela do aplicativo: o `Pyron.exe` abre a interface numa janela própria sem a barra de título do Windows
  (`lancador/Janela.cs`, WebView2; DLLs da Microsoft em `lancador/webview2`, carregadas de lá). O topo da
  interface vira a barra: `app-region: drag` e os botões de minimizar, maximizar e fechar (`ligarJanela()` em
  `casca.js`, mensagens `janela:*`). Sem WebView2, cai na janela do Edge (`--app`, maximizada, barra clara pelo
  tema do perfil que `app/iniciar.py` grava em `preparar_perfil_janela`). Ícone da janela e da barra de
  tarefas: o do `Pyron.exe`; da página, `app/estatico/marca/icone-janela-*.png`.
- Ao testar no servidor real (porta 8765), fechar a aba de teste: ela conta como janela aberta e o
  servidor não desliga.
- A janela do Edge em modo aplicativo guarda arquivos em cache: o servidor manda `Cache-Control: no-cache`
  em tudo que não é `/api` (middleware `sem_cache_da_interface`), então arquivo novo entra sem `?v=`.
