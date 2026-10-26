# Etapa 6 · Troca e acabamento

Data: 26/10/2026. Versão 0.8.0. A interface nova (`app/interface`) passou a ser a principal, em `/`; `/nova` e `/nova/`
redirecionam para `/`. A anterior (`app/estatico`) fica em `/antiga` por esta versão, com link em Configurações ›
Sobre, e sai na próxima. A marca é servida em `/marca` para as duas. Capturas em `docs/interface/capturas/etapa6/`.

## 1. Troca

| O que | Como ficou |
|---|---|
| Endereço principal | `/` serve `app/interface/index.html`; os módulos em `/js/…`, os estilos em `/tokens.css` etc. |
| Interface anterior | `/antiga/` (o atalho "Abrir a interface nova" da busca dela leva a `/`) |
| Versão | 0.7.7 → 0.8.0 no servidor e nas duas interfaces (elas conferem a versão do servidor quando uma rota dá 404) |
| Tema escuro | já estava em todas as telas (Etapas 3 a 5); conferido de novo com o axe nos dois temas |
| Barra de título | `meta theme-color` na cor do topo (`--superficie`), trocada junto com o tema: branca no claro, `#151A21` no escuro |

## 2. Revisão com web-design-guidelines

Regras buscadas em `vercel-labs/web-interface-guidelines` (command.md) e conferidas no código de `app/interface`.

**Corrigido**
- `index.html` + `js/casca.js:214` - sem `theme-color`: a janela do Edge em modo aplicativo ficava com a barra de título fora do tema → meta criada e atualizada pelo tema
- `textos.js:294`, `:347`, `:626` - aspas retas em volta do termo buscado e do nome do critério → aspas curvas “ ”
- `base.css:6` - sem `touch-action: manipulation` (espera do toque duplo em tela de toque) e realce de toque padrão → definidos no `html`
- `componentes.css:238`, `:268`, `:336`, `telas.css:322` - rolagem do diálogo, da busca e dos painéis passava para a página no fim → `overscroll-behavior: contain`
- `js/configuracoes/criterio.js:19`, `componentes.js:15` - sair do critério ou dos componentes com mudança sem salvar perdia tudo, sem aviso → `vigiarAlteracoes()` e `podeSair()` (`js/componentes.js:387`): trocar de tela (`js/casca.js:229`), de aba (`js/telaAbas.js:21`) ou fechar a janela pergunta "Sair sem salvar?"; Cancelar devolve o endereço anterior sem remontar a tela

**Conferido sem achado**: sem `transition: all`; zoom não bloqueado; todo `outline: none` tem substituto (`:focus-visible` com anel, menu com fundo, campo com borda e sombra); números com `tabular-nums`; datas e números por `Intl` (`js/base.js`); reticências "…" nos textos; `prefers-reduced-motion`; `color-scheme` claro e escuro; `aria-live`/`role="status"` nos avisos e no "Salvo"; link para pular ao conteúdo; listas longas paginadas (Inspeções, "Mostrar mais"); campos com `autocomplete="off"` e `spellcheck="false"` onde o texto é nome ou caminho.

**Aceito, com motivo**: figuras do treino e da avaliação sem `width`/`height` (tamanho vem do caderno do Colab; ficam em seções recolhidas e com `loading="lazy"`, o que evita o salto de layout ao abrir a tela); item de menu com foco marcado pelo fundo, como nos menus do Windows.

## 3. Acessibilidade: axe e Lighthouse

Baixados com autorização do usuário para uma pasta temporária (axe-core 4.14.0 e lighthouse 13.5.0, fora do projeto).

**axe** (WCAG 2.0/2.1/2.2 A e AA e boas práticas), dentro do Edge sem janela, com as seções recolhidas abertas: 21
telas e abas (Painel, Inspeções, duas análises, Equipamentos, um equipamento, Pendências, as 4 abas da Captura, as
3 de Modelos, as 6 de Configurações e um endereço inexistente) nos temas claro e escuro, 42 rodadas.

| Achado (impacto) | Onde | Correção |
|---|---|---|
| `label-content-name-mismatch` (sério) | link Pendências na navegação, todas as telas: nome "Pendências, 5 pendências vencidas", texto visível "Pendências5" | sem `aria-label`; o número fica escondido do leitor e um texto `.so-leitor` dentro do link diz ", 5 pendências vencidas" (`js/casca.js:187`) |
| `label-content-name-mismatch` (sério) | limites da escala na Análise: nome "Máximo da escala", texto "67,5 °C" | nome começa pelo valor: "67,5 °C, máximo da escala" (`js/analise/palco.js:145`) |
| `aria-prohibited-attr` (sério) | esqueleto de carregamento com `aria-label` sem papel | `role="status"` nos esqueletos (`js/componentes.js:210`) |
| `nested-interactive` (sério) | gráfico do equipamento: pontos com link dentro de `role="img"` | `role="group"` quando os pontos são links ou botões (`js/grafico.js:70`) |
| `color-contrast` (sério) | Critério: grupo "ΔT sobre o ambiente" desligado com opacidade 0,5 (12 textos) | sem opacidade; os campos do grupo ficam desabilitados (o valor fica guardado) |
| `page-has-heading-one` (moderado) | endereço inexistente sem `h1` | "Tela não encontrada" como `h1`, com o endereço e o botão para o Painel |

Depois das correções: **0 violações nas 42 rodadas** (30 a 48 regras passando por tela; 1 ou 2 itens "a conferir"
por tela, de contraste sobre o termograma e sobre imagens, que o `conferir.js` já mede).

**Lighthouse** (acessibilidade e boas práticas, Edge sem janela, modo desktop): Painel, Inspeções, Análise,
Equipamento, Pendências, Captura, Modelos e Critério com **100 e 100** nas oito.

## 4. Conferido no navegador

- Endereços: `/` (interface nova), `/nova` e `/nova/` (307 para `/`), `/antiga/` (interface anterior com `app.js`),
  `/marca/logo-cor.svg`, `/js/casca.js`.
- Sair sem salvar (Edge sem janela): Atenção do critério de 60,1 para 33 → ir ao Painel abre a pergunta; Cancelar
  mantém a tela, o endereço `#configuracoes/criterio` e o 33; trocar para a aba Componentes pergunta de novo e
  Cancelar volta a aba; Sair sem salvar troca; ir ao Painel depois disso não pergunta. Nada foi salvo.
- No painel do aplicativo (pré-visualização), o evento `close` do `<dialog>` não dispara nem num diálogo de teste
  vazio: a confirmação ali fica presa. É do navegador embutido da pré-visualização; no Edge (sem janela e em modo
  aplicativo) funciona, e é o mesmo diálogo que já servia para restaurar backup e o critério padrão.

## 5. Manual e capturas

`docs/Pyron_Funcionalidades.pdf` (36 páginas, 3,3 MB) gerado de novo por `docs/manual/gerar_manual.py`:
- cores da interface nova (tinta e ardósia nos títulos e cabeçalhos de tabela, cobalto só nos marcadores de lista,
  capa com a faixa grafite do palco);
- navegação no topo, busca, atalhos (V R P L, I, F, 0, Alt + 1 a 6, Alt + 0), Importar termogramas em Inspeções,
  Análise com barra de ferramentas e painel de detalhe, Captura com abas, Modelos com o recomendado, Configurações com
  seis abas, salvamento automático e Desfazer, "Sair sem salvar", interface anterior em Sobre;
- 19 telas capturadas de novo nos dados de demonstração e 3 reaproveitadas da Etapa 5 (Vídeo, Alertas e Avaliação,
  que não existem nos dados de demonstração);
- saíram as figuras sem equivalente: Lado a lado, Conferir e Sem temperatura (sem caso nos dados de demonstração;
  o texto continua), o diálogo de pendência (virou o painel ao lado da lista), Nova análise e a abertura do
  Pyron.exe (a captura era da logo antiga; o Pyron.exe não rodou daqui para capturar de novo). A tabela "Em
  desenvolvimento" saiu: os mesmos itens estão em "Próximos passos".

README (seção Interface, Vídeo, Pasta monitorada) e `CLAUDE.md` (seção 0 e Git) atualizados.

## 6. Critério de pronto

| Tela | Nota (Leis de UX) | Checklist |
|---|---|---|
| Análise (Etapa 4) | 54 de 56 aplicáveis (58/60) | 12/12 |
| Painel e Inspeções (5a) | 57 de 58 (59/60) | 12/12 |
| Equipamentos, Equipamento, Pendências (5b) | 53 de 54 (59/60) | 12/12 |
| Captura (5c) | 58 de 58 (60/60) | 12/12 |
| Modelos e Configurações (5d) | 59 de 60 | 12/12 |

Todas acima de 50/60. As mudanças desta etapa (pergunta ao sair, nomes acessíveis, grupo desligado) não tiram
ponto de nenhuma lei nas telas avaliadas. Testes: 248 passando e 8
pulados (`pytest -q`), com o teste novo da pergunta ao sair e da versão igual nas três pontas.

## 7. Pendências (fora do critério)

- Peak-End do fim do treino (5d): sem retorno próprio quando o treino acaba em outra tela.
- ~~Recompilar o `Pyron.exe`~~ feito no mesmo dia: ícone só com o símbolo (sem fundo) e abertura sem janela, só a
  logo com sombra suave (`app/estatico/marca/abertura.png`); 52 KB; `--verificar` passou e o Controle Inteligente de
  Aplicativos deixou rodar. Na área de trabalho ficou um só `Pyron.exe` ("Abrir Pyron" e o .exe antigo foram para a Lixeira).
- Tirar `/antiga` e `app/estatico` na próxima versão.
