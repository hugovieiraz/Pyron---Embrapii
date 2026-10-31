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
