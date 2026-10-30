# Pyron 0.9 · F1 · Modo servidor e controle de acesso

Data: 30/10/2026. Branch `v09-f1-servidor` (sem commit, por pedido do usuário). Máquina: a da F0
(Acer Nitro AN515-55, GTX 1650, Windows 11, SAC desligado).

## Resumo em 3 linhas

1. Feito: `--modo servidor` com login (scrypt, cookie de sessão, perfis do cadastro do time), as 129 rotas
   classificadas e conferidas por teste, comentários com autor, autor no histórico da pendência, registro dos
   laudos emitidos, WAL no SQLite e proteção contra edição simultânea.
2. Feito: tela de entrada, nome e perfil no topo, ações escondidas por perfil, guia de implantação; 0 violações
   do axe em 23 rodadas nos dois temas; 400 testes rápidos passando (27 novos).
3. Pendente: telas de Modelos e Captura ainda mostram ações de administrador para quem não é (o servidor recusa
   com 403); HTTPS dos tablets em aberto (F2); arquivo de dependências do servidor (F4).

## O que mudou

| Onde | O quê |
|---|---|
| `app/acesso.py` (novo) | senha com `hashlib.scrypt`; sessão no cookie `pyron_sessao` (HttpOnly, SameSite=Strict, Secure no HTTPS), 12 h sem uso ou 7 dias; bloqueio após 5 erros em 15 min; recusa de pedido com `Origin` de outro endereço ou `Sec-Fetch-Site: cross-site`; `X-Forwarded-*` só do `--proxy`; perfis; classificação das rotas; linha de comando `python -m app.acesso usuario` e `conferir` |
| `app/servidor.py` | dependência global `acesso.verificar`; rotas `/api/acesso/eu`, `/entrar`, `/sair`, `/senha`, `/api/analises/{id}/comentarios` (GET e POST), `/api/laudos/emitidos`; laudo assinado por quem entrou e registrado (SHA-256 do PDF); `PUT /api/analises/{id}` com `revisao` (409 se outra pessoa gravou antes) dentro da `_trava`; `POST /api/analises` num fio à parte (não para mais o servidor durante a análise); time com `usuario`, `administrador` e `senha_hash` (nunca devolvido), limite de 20; configurações sem telefone, e-mail e pastas para quem não administra; técnico só deixa nota nas pendências urgentes e imediatas; no modo servidor `/antiga` leva a `/`, o celular não liga e `/api/sinal` não existe; não sobe sem administrador com senha |
| `app/armazenamento.py` | esquema 3: `comentarios`, `sessoes`, `laudos_emitidos`, `historico_pendencias.autor`; WAL e espera de 15 s em toda conexão |
| `app/backup.py` | ignora `-wal` e `-shm`; tira as sessões do .zip e da restauração; `python -m app.backup` para backup agendado |
| `app/pendencias.py` | autor no histórico |
| `app/cadastro_medidas.py` | espera de 15 s (sem WAL de propósito: o backup copia esse arquivo como está) |
| `app/iniciar.py` | `--modo`, `--host` (0.0.0.0 só no servidor), `--proxy`; no servidor sem janela e sem auto-encerrar |
| Interface | `js/telas/entrar.js` (estados: pronto, entrando, erro, sem conexão, sessão terminou); `base.js` com `acesso`, `pode()`, evento de sessão vencida; topo com nome, perfil, Trocar senha e Sair; Configurações só para administrador; laudo, Detectar de novo, apagar e definir equipamento conforme o perfil; Análise só leitura para o técnico (ferramentas de edição somem, campos travam); aba Comentários; linha "Acesso ao servidor" no cadastro do time; caixas de marcar de 20 para 24 px (WCAG 2.5.8) |
| Docs | `docs/servidor/implantacao.md`; capturas em `docs/v09/capturas/f1/` |

## Conferido

### Testes

| Bateria | Resultado |
|---|---|
| `pytest -q -m "not lento"` antes da F1 | 373 passaram, 4 pulados |
| `pytest -q -m "not lento"` depois da F1 | 400 passaram, 4 pulados (93 s) |
| `testes/test_acesso.py` | 27 testes: toda rota classificada; sem sessão 401 em toda `/api` menos entrar, sair, eu e saúde; WebSocket recusado; cookie seguro; bloqueio por tentativas; outro site recusado; técnico sem laudo, revisão e administração; engenheiro sem assinatura sem laudo; só local 403 de fora mesmo para administrador; proxy confiável e não confiável; sessão vencida; senha não sai na API; troca de senha derruba as outras sessões; saída do time derruba a sessão; limite de 20; laudo assinado por quem entrou com SHA-256 registrado; comentário com caracteres especiais guardado como texto; 409 na edição simultânea; regra do técnico na pendência; modo local sem login; linha de comando; argumentos do `iniciar`; backup sem sessões |

Os testes antigos rodaram sem nenhuma mudança, o que mostra que o modo local continua igual.

### No navegador (Edge sem janela, 1536 × 816)

Servidor de teste com cópia de `saida/dados_demo` e duas contas (administradora que assina e técnico).

- Tela de entrada, senha errada, entrar, menu da conta, Análise, comentário com `<b>`, `#`, `$`, `@` (aparece
  como texto), diálogo do laudo com "Assina o laudo: Ana Lima, CREA-PB 111", cadastro do time, sair.
- Técnico: sem Região, Ponto e Linha; sem Detectar de novo e Gerar laudo; os 7 campos de Condições travados;
  Configurações mostra "Só administrador" e a engrenagem some do topo.
- Modo local (outra cópia): sem tela de entrada, com todas as ferramentas, responsável do laudo escolhido como
  antes e o salvamento automático funcionando com a revisão.

**axe-core 4.14.0** (WCAG 2.0, 2.1 e 2.2 A e AA e boas práticas), baixado numa pasta temporária fora do projeto,
como na Etapa 6:

| Rodadas | Temas | Violações |
|---|---|---|
| 17 no modo servidor (entrada, entrada com erro, painel, Análise, comentários, laudo, configurações, pendência, telas do técnico) | claro e escuro | 0 |
| 4 no modo local (painel, Análise, configurações) | claro e escuro | 0 |
| 2 no cadastro do time rolado até a linha de acesso | claro | 0, depois de aumentar as caixas de marcar |

O único achado foi anterior à F1: caixas de marcar de 20 px no cadastro do time (`target-size`), que só
apareciam com a linha visível. Elas passaram a 24 px.

## Decisões tomadas nesta fase

- Grupos de rota além dos cinco do plano: **público** e **envio** (ver `0-diagnostico.md`).
- O servidor exige um **administrador** com senha para subir, não apenas um usuário: sem administrador ninguém
  conseguiria cuidar do time.
- Pergunta 8 da F0 sem resposta: no modo servidor `/antiga` e o modo celular ficam desligados.
- O técnico pode deixar nota numa pendência urgente ou imediata (a nota é um comentário); só não muda situação,
  prazo, OS e responsável.
- Sessões ficam no banco (sobrevivem a reiniciar o servidor) e só com o SHA-256 do código.
- No modo servidor, quem não administra troca o tema só na própria tela (o tema guardado é da equipe).

## Pendências

- Modelos (instalar, treinar, ativar) e Captura (pasta monitorada, celular) ainda mostram ações de
  administrador a quem não é; o servidor responde 403 com o motivo.
- Reprocessar (Detectar de novo, Medir, parâmetros da câmera) não confere a revisão; só o salvamento da tela confere.
- `pyproject.toml` sem as dependências do aplicativo; um arquivo de requisitos do servidor entra na F4.
- HTTPS dos tablets: decisão em aberto (F2).
