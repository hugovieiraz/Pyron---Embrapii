---
trigger: always_on
description: Consultar e registrar o diário da equipe antes e depois de cada tarefa
---

# Diário da equipe

Hugo e Gabriel mexem no mesmo `main`, cada um com o seu assistente. Regra pedida pelo Hugo em 31/10/2026:

1. Antes de planejar ou executar qualquer pedido, rode `python ferramentas/novidades_equipe.py` e leia em
   `docs/equipe/diario.md` as entradas sobre o mesmo assunto. Se o outro já fez, está fazendo ou deixou pendência
   sobre aquilo, avise o usuário antes de começar.
2. Ao terminar, acrescente no topo de `docs/equipe/diario.md` uma entrada curta (Feito, Para o outro, Pendente) e
   publique junto com a mudança.

A regra completa está no topo do `CLAUDE.md`.
