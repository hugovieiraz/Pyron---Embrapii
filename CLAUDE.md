# Pyron: regras do projeto

Software de manutenção preditiva por termografia (FastAPI local + interface web em `app/estatico/`,
núcleo em `nucleo/`, treino em `ml/`, lançador `Pyron.exe` em `lancador/`). Textos em português do Brasil.

## 1. Sistema de design (fonte única: `app/estatico/tokens.css`)

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
- A mão da logo é escura: o símbolo vai sempre sobre fundo claro (ladrilho branco, cartão branco).
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
- Commit e push só quando o usuário pedir. O repositório é https://github.com/hugovieiraz/Pyron---Embrapii.
- O dataset ScienceDB 10185 é só para estudo (CC BY-NC-SA); não vai para o repositório.
- O `Pyron.exe` precisa continuar pequeno (≈100 KB, sem recursos embutidos): o Controle Inteligente
  de Aplicativos do Windows bloqueou uma versão de 390 KB. Nunca mexer nessa proteção.
