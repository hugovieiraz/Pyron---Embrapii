# Diário da equipe

Recados entre o Hugo e o Gabriel (e os assistentes de cada um) sobre o que foi feito no Pyron, para ninguém
refazer o trabalho do outro. Entrada mais nova no topo. O gancho de início de sessão
(`ferramentas/novidades_equipe.py`) mostra ao Claude de cada um as entradas novas da outra pessoa.

Modelo de entrada (curta; o detalhe fica no commit):

```
## DD/MM/AAAA · Nome
- Feito: o que mudou e onde (commits).
- Para o outro: o que não precisa refazer, o que mudou de regra, cuidados.
- Pendente: o que ficou para depois ou espera decisão.
```

## 31/10/2026 · Hugo (3): modelos, Análise e Medição

- Feito (`fc28080`, `7f67f51`, `477394d`): pedido do Hugo para simplificar a inspeção e separar a medição da térmica.
  - Modelo térmico único: para-raios + pontos quentes. `_modelo_termico()` em `app/servidor.py` resolve o ativo
    (combinado do config, combinado do treinado do config ou o primeiro combinado normal; sem treinado, a regra).
    `/api/modelos` marca `principal` no que a tela mostra. Modelos › Em uso e Captura › Vídeo não oferecem mais troca.
  - Análise: lista de regiões voltou para a lateral (Resumo), com "anterior / 2 de 14 / próxima" no detalhe; a faixa
    horizontal saiu. "Detectar de novo" saiu; no lugar, chaves liga/desliga Para-raios, Pontos quentes e Medição
    (pontos e linhas de temperatura), componente `chaves()` em `js/componentes.js`. A seção Dimensões (SAM 2) saiu da Análise.
  - Ponto quente sem anomalia não vira caixa: sai se a severidade é normal e o ΔT do entorno fica abaixo do 1º limite
    de `similares` (5 °C na NBR). O ponto mais quente da cena vem da matriz inteira (`nucleo/analise.py`).
  - Medição virou tela do topo (Painel · Inspeções · Equipamentos · Pendências · Captura · Medição · Modelos), abas
    Medir e Modelos em `js/medicao/`. `#captura/medir` e `#modelos/medicao` redirecionam. Medir só por duas pontas que
    o usuário marca (o modelo de profundidade dá a distância entre elas) ou pelo retângulo de referência; saíram
    "Clicar no objeto", "Caixa em volta", as cotas automáticas e a biblioteca de pesos. Uma medida por vez, nada gravado.
- Para o outro: `/api/medicao/comparar` e `/api/medicao/video/comparar` só gravam no registro com `registrar=true`
  e aceitam `modelo` (`da3` ou `moge`) para rodar um só. O backend do SAM 2 + DINOv2, do auto_identificar, da
  redetecção e do registro continua; só a tela deixou de usar. Testes que esperavam o treinado sozinho como ativo
  mudaram (`test_avaliacoes.py`, `test_componentes_pontos.py`).
- Para o outro: feito com o orquestrador alethe. Claude Sonnet escreveu a tela Medição e a medida por duas pontas;
  Codex (ChatGPT) escreveu a resolução do modelo no servidor e revisou o código (achou 2 defeitos, corrigidos em
  `7f67f51`); Antigravity revisou a UX (aplicados `role="switch"` nas chaves e texto mais curto). Integração e
  testes pelo Claude Opus do Hugo: suíte completa com 455 passando, 9 pulados.
- Pendente (Hugo): testar a medida por duas pontas com fotos reais e o vídeo (as pontas dos quadros 2 a 4 vêm do
  fluxo óptico). `testes/test_video.py::test_video_de_ponta_a_ponta` falhou uma vez na suíte rápida por tempo e
  passou 3 de 3 sozinho.

## 31/10/2026 · Hugo (2)

- Feito: a regra do diário também vale no Antigravity. Bloco novo "Diário da equipe" no começo de
  `.agents/agents/orchestrator.md` (o resto do arquivo ficou igual) e regra em `.agents/rules/diario-equipe.md`.
- Para o outro: Gabriel, confira se o seu Antigravity lê `.agents/rules/`; se o caminho for outro, mova o arquivo.
  O bloco no `orchestrator.md` vale de qualquer jeito.
- Feito: gancho SessionStart em `.claude/settings.json` (criado pelo Hugo; o modo automático não deixa o assistente
  criar esse arquivo). Ao abrir o Claude Code no projeto, roda `ferramentas/novidades_equipe.py` sozinho.
- Feito: o script agora mostra do diário só o que a outra pessoa escreveu (antes mostrava também as suas entradas).
- Para o outro: Gabriel, no primeiro `git pull` o seu Claude Code pode pedir para confiar no gancho novo; é este script.

## 31/10/2026 · Hugo

- Feito: integrei a 0.9 inteira do branch `v09-f1-servidor` no `main` (merge `f566928`), sem conflito; suíte
  completa com 445 testes passando e 9 pulados (o do Typst pula aqui: o pacote `typst` não está instalado).
- Feito: trava no `config.json` (`b1155b1`, `app/servidor.py`, `_TRAVA_CONFIG`). Desde a migração dos destinatários
  para o time, a leitura do config também grava; a thread do monitor e o pedido da tela gravavam juntos e uma
  leitura no meio pegava o JSON pela metade e caía no padrão (monitor desligado). Era a falha intermitente de
  `test_pasta_vigiada_analisa_o_novo_e_alerta_uma_vez`. O `python -m app.acesso usuario` grava o config em outro
  processo e fica fora da trava (uso manual).
- Feito: tirei do `CLAUDE.md` a seção do Shlomo (`0939cd6`); a nota no topo do `CLAUDE.md` explica o motivo.
  Gabriel: a instrução de consultar o cofre pode ir no seu `~/.claude/CLAUDE.md`.
- Feito: `marca/gerar_marca.py` espera o Edge gravar a imagem (`3e14e81`). O Edge atualizado volta antes de gravar o
  PNG no modo sem janela, e a geração do ícone (e por isso o `lancador/construir.py`) falhava. Recompilei o `Pyron.exe`.
- Feito: documento técnico do Pyron para a coordenação (funcionalidades, arquitetura, números e melhorias), fora do
  repositório. Entre as melhorias: `pyproject.toml` sem FastAPI e uvicorn nas dependências, `armazenamento.listar()`
  lendo o JSON de todas as inspeções a cada pedido e `app/servidor.py` com 3.346 linhas.
- Para o outro: este diário e o gancho em `.claude/settings.json` são novos. Ao abrir uma sessão do Claude Code no
  projeto, ele busca o GitHub e mostra os seus commits e recados novos. Se usar outra ferramenta (Antigravity), leia
  este arquivo à mão ou rode `python ferramentas/novidades_equipe.py`.
- Feito: integrei os commits do Gabriel de 30/10 à noite (0.9.0 com Typst como padrão, Pyron desktop em Tauri F5 e
  licenças do Tauri); 450 testes passando, 9 pulados; a interface abre sem erro no console.
- Para o outro: regra nova no topo do `CLAUDE.md`. Antes de planejar ou mexer em qualquer coisa, consultar as novidades
  (script + este diário); ao terminar cada tarefa, registrar aqui.
- Pendente (Hugo): confirmar que o visual do laudo em Typst está aprovado. O commit `0688af3` diz "visual aprovado",
  mas o Hugo não tinha visto. Neste computador o pacote `typst` não está instalado, então o laudo continua saindo pelo
  reportlab.
- Pendente (Gabriel): dizer se o branch `v09-f1-servidor` pode ser apagado.
