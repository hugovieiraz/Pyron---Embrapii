# Plano: nova interface do Pyron

Reformular **do zero** a interface do Pyron completo (`app/estatico`), com as 30 Leis de UX, para uma
interface profissional e técnica. Este arquivo é a lista de tarefas: cada etapa é feita numa conversa
nova, marca as caixas ao terminar e preenche o Registro no fim.

## Como usar (Hugo)

1. Abra uma **conversa nova na pasta `C:\Users\hv392\projetos\termovigia`** para cada etapa.
2. Escolha o modelo e o esforço indicados na etapa (seletor do app, ao lado da caixa de mensagem).
3. Cole o pedido abaixo trocando o número da etapa. Ao final, confira o resultado e aprove antes da próxima.

```text
Siga docs/plano-interface.md e faça a Etapa N inteira, parando no critério de pronto dela.
Antes de começar: git fetch; se houver commits novos no main, integre no branch interface-nova e rode os testes.
No fim: marque as tarefas feitas, preencha o Registro (3 linhas) e faça commit e push do branch.
```

Por que uma conversa por etapa: o histórico de uma conversa longa é relido a cada mensagem e gasta o
limite do plano à toa. Cada conversa nova começa só com o CLAUDE.md, a memória e este plano.

## Regras fixas (valem em todas as etapas)

- **Do zero de verdade:** nova arquitetura de informação, navegação, layout e hierarquia. Não é
  retocar a interface atual. Manter todas as funcionalidades e **não mudar nenhuma rota da API**.
- **Em paralelo:** a interface nova é construída em `app/interface/` e servida em `/nova`. A atual
  continua em `/` funcionando até a Etapa 6. Assim nada quebra no meio e o trabalho do Gabriel segue.
- **Branch:** `interface-nova`, criado a partir do `main`. No início de cada etapa, trazer o `main`
  (merge, nunca forçar). Publicar o branch ao fim de cada etapa; o `main` só recebe na Etapa 6.
- **Design:** seguir o `CLAUDE.md` (tokens como fonte única, tema claro industrial, estados de
  carregamento/vazio/erro, movimento 150/250/400 ms, `prefers-reduced-motion`). A skill
  `frontend-design` ajuda na direção, mas o `CLAUDE.md` vale acima dela.
- **Skills:** `laws-of-ux` (decidir), `laws-of-ux-review` (nota 0–60), `laws-of-ux-checklist`
  (12 itens), `web-design-guidelines` (revisão técnica), `dataviz` (gráficos e indicadores),
  `gsd-sketch` (esboços).
- **Público:** técnicos e engenheiros de manutenção de subestação; notebook 1536 × 816 e projetor.
- **Textos:** português técnico e sóbrio, sem tom pessoal nem de IA; textos do JS em `textos.js`.
- **Testes e conferência:** `.venv/Scripts/python.exe -m pytest testes -q`, `node --check` nos `.js`,
  capturas em 1536 × 816 pela pré-visualização `pyron-demo` (nunca com os dados reais).
- **Economia:** ler arquivos grandes por partes (o `app.js` tem milhares de linhas); não repetir
  auditorias já registradas; resumir no Registro em vez de reexplicar.

## Etapa 0 · Integrar a medição de equipamentos do Gabriel
Modelo: **Sonnet** ou Opus com esforço **médio**.
- [ ] `git fetch`; ler os commits novos do `main` (o que mudou na API, no banco e nas telas).
- [ ] Criar o branch `interface-nova` a partir do `main` atualizado; rodar os testes.
- [ ] Anotar no Registro a janela/tela nova de medição: rotas, dados, ações do usuário.
- **Pronto quando:** testes passam e a tela de medição está descrita para entrar no inventário.

## Etapa 1 · Diagnóstico (sem mexer em código)
Modelo: **Opus**, esforço **alto**.
- [ ] Inventário das telas (Painel, Inspeções, Análise, Equipamentos, Medição, Pendências,
      Monitoramento, Vídeo, Celular, Modelos, Avaliação, Configurações, Sobre): para cada uma, a
      tarefa do usuário, os dados, as ações e a frequência de uso.
- [ ] `laws-of-ux-review` em cada tela: nota 0–60 e os 3 problemas principais.
- [ ] `web-design-guidelines` nos arquivos da interface (achados com arquivo:linha).
- [ ] Capturas atuais em 1536 × 816 em `saida/capturas/antes/`.
- [ ] Proposta de arquitetura: navegação nova (no máximo 7 itens no primeiro nível), agrupamento das
      telas e o fluxo principal (inspecionar → analisar → registrar pendência → laudo).
- **Entregável:** `docs/interface/1-diagnostico.md`.
- **Pronto quando:** o Hugo aprovou a navegação proposta.

## Etapa 2 · Direção visual (três caminhos)
Modelo: **Opus**, esforço **alto**.
- [ ] Brief curto: assunto, público, tarefa principal, tom (técnico, industrial, sóbrio).
- [ ] Três direções **realmente diferentes** (estrutura, densidade, hierarquia, tipografia) para o
      **Painel** e a **Análise**, em HTML estático com dados de demonstração, todas dentro das regras
      do `CLAUDE.md`.
- [ ] Mostrar as três lado a lado (Artifact privado ou navegador) com prós e contras em palavras
      simples, sem jargão de design.
- **Entregável:** `docs/interface/2-direcoes/` e a escolha registrada.
- **Pronto quando:** o Hugo escolheu uma direção (ou a combinação de partes de duas).

## Etapa 3 · Sistema visual e estrutura
Modelo: **Opus**, esforço **alto**.
- [ ] Tokens da direção escolhida (ajustar `tokens.css` só se a direção pedir; valor novo entra lá primeiro).
- [ ] Componentes base em `app/interface/`: botões, campos, cartões, tabelas, selos de severidade,
      estados (esqueleto, vazio, erro, sem conexão), diálogos, avisos.
- [ ] Página de catálogo dos componentes, para conferência visual.
- [ ] Casca: navegação nova, cabeçalho, roteamento, atalhos de teclado; servir em `/nova`.
- **Pronto quando:** catálogo aprovado; foco visível, contraste ≥ 4,5:1 e alvos ≥ 44 px conferidos.

## Etapa 4 · Tela de referência
Modelo: **Opus**, esforço **alto**.
- [ ] Construir a **Análise** completa na interface nova, ligada à API real.
- [ ] Capturas antes/depois; `laws-of-ux-checklist` 12/12; nota ≥ 50/60.
- **Pronto quando:** o Hugo aprovou. Esta tela vira o padrão das outras.

## Etapa 5 · Demais telas (uma conversa por grupo)
Modelo: **Sonnet** ou Opus com esforço **médio** (o padrão já está decidido).
- [ ] 5a · Painel e Inspeções
- [ ] 5b · Equipamentos, Medição (Gabriel) e Pendências
- [ ] 5c · Monitoramento, Vídeo e Celular
- [ ] 5d · Modelos, Avaliação, Configurações e Sobre
- Em cada grupo: mesmo padrão da Etapa 4, checklist 12/12, capturas antes/depois, testes.

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
| plano | 25/10/2026 | Plano criado | Construir em paralelo em `/nova`, branch `interface-nova` | Etapa 0 quando o push do Gabriel chegar |
