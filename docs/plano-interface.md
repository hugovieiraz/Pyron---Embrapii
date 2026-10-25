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

## Etapa 0 · Integrar a medição de equipamentos do Gabriel
Modelo: **Sonnet** ou Opus com esforço **médio**.
- [ ] `git fetch`; ler os commits novos do `main` (API, banco, telas).
- [ ] Criar o branch `interface-nova` a partir do `main` atualizado; rodar os testes.
- [ ] Descrever no Registro a funcionalidade de medição: rotas, dados, ações do usuário.
- **Pronto quando:** testes passam e a medição está descrita para entrar no inventário.

## Etapa 1 · Diagnóstico e nova arquitetura (sem mexer em código)
Modelo: **Opus**, esforço **alto**.
- [ ] Inventário de todas as telas atuais (Painel, Inspeções, Análise, Equipamentos, Medição,
      Pendências, Monitoramento, Vídeo, Celular, Modelos, Avaliação, Configurações, Sobre): tarefa do
      usuário, dados, ações, frequência de uso e o que é excesso (texto, opção, tela).
- [ ] `laws-of-ux-review` em cada tela: nota 0–60 e os problemas principais.
- [ ] `web-design-guidelines` nos arquivos da interface (achados com arquivo:linha).
- [ ] Capturas atuais em 1536 × 816 em `saida/capturas/antes/`.
- [ ] **Decidir** a nova arquitetura: telas que ficam, juntam, saem; navegação (no máximo 7 itens no
      primeiro nível); fluxo principal (inspecionar → analisar → pendência → laudo); o que vai para
      Configurações ou para o manual.
- **Entregável:** `docs/interface/1-diagnostico.md` com as decisões e o motivo de cada uma.
- **Pronto quando:** arquitetura decidida e registrada, inclusive a lista do que sai da interface.

## Etapa 2 · Direção visual
Modelo: **Opus**, esforço **alto**.
- [ ] Brief: assunto, público, tarefa principal, tom (técnico, industrial, sóbrio).
- [ ] Explorar três direções diferentes (estrutura, densidade, hierarquia, tipografia) em esboços
      HTML do **Painel** e da **Análise**, com dados de demonstração.
- [ ] **Escolher** uma, pelos critérios: leitura em 1536 × 816 e no projetor, densidade de dados,
      Leis de UX, consistência com o `CLAUDE.md`. Registrar o motivo.
- **Entregável:** `docs/interface/2-direcao.md` (escolha + motivo) e os esboços em `docs/interface/esbocos/`.
- **Pronto quando:** direção escolhida e registrada.

## Etapa 3 · Sistema visual e estrutura
Modelo: **Opus**, esforço **alto**.
- [ ] Tokens da direção escolhida (valor novo entra em `tokens.css` primeiro).
- [ ] Componentes base em `app/interface/`: botões, campos, cartões, tabelas, selos de severidade,
      estados (esqueleto, vazio, erro, sem conexão), diálogos, avisos.
- [ ] Página de catálogo dos componentes, para conferência.
- [ ] Casca: navegação nova, cabeçalho, roteamento, atalhos; servir em `/nova`.
- **Pronto quando:** catálogo completo; foco visível, contraste ≥ 4,5:1 e alvos ≥ 44 px conferidos.

## Etapa 4 · Tela de referência
Modelo: **Opus**, esforço **alto**.
- [ ] Construir a **Análise** completa na interface nova, ligada à API real.
- [ ] Capturas antes/depois; `laws-of-ux-checklist` 12/12; nota ≥ 50/60.
- **Pronto quando:** os critérios acima passam. Esta tela vira o padrão das outras.

## Etapa 5 · Demais telas (uma conversa por grupo)
Modelo: **Sonnet** ou Opus com esforço **médio** (o padrão já está decidido).
- Os grupos seguem a arquitetura decidida na Etapa 1 (o agrupamento abaixo é o ponto de partida):
- [ ] 5a · Painel e Inspeções
- [ ] 5b · Equipamentos, Medição e Pendências
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
| plano | 25/10/2026 | Plano criado | Claude decide produto e design; construir em `/nova`, branch `interface-nova` | Etapa 0 quando o push do Gabriel chegar |

### Saiu da interface (com motivo, para poder voltar)

| Função ou tela | Para onde foi | Motivo |
|---|---|---|
