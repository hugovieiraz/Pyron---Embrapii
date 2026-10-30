# Pyron 0.9 · F2 · Tablet: aplicativo instalável (PWA) e toque

Data: 30/10/2026. Branch `v09-f1-servidor` (a F2 seguiu no mesmo branch, sem commit, por pedido do usuário).
Máquina: a da F0 (Acer Nitro AN515-55, Windows 11, Edge 1536 × 816; tablets emulados no Edge sem janela).
HTTPS escolhido pelo usuário: Tailscale, plano gratuito.

## Resumo em 3 linhas

1. Feito: manifest com cores dos tokens e ícones 192, 512, maskable e 180 do gerador da marca; service worker
   (rede primeiro, casca com a versão no nome, nunca `/api` nem PDF); porta reservada ao `tailscale serve`.
2. Feito: pinça, arrasto com dois dedos, toque duplo e alças de 44 px no palco; toque longo abre o menu das
   listas; layout sem rolagem lateral nos 5 tamanhos; laudo com Compartilhar; 0 violações do axe em 34 rodadas.
3. Pendente: instalar de verdade num iPad e num Android pela rede Tailscale (precisa do Tailscale instalado e
   da conta); conferir os cabeçalhos reais do `tailscale serve`; plano gratuito é só para uso não comercial.

## Decisões

- **Porta reservada ao proxy** (`--porta-proxy`). A página oficial do `tailscale serve` (validada em 20/01/2026)
  documenta só os cabeçalhos de identidade (`Tailscale-User-Login`, `-Name`, `-Profile-Pic`), não o
  `X-Forwarded-For`. Pelo desenho da F1, um pedido de 127.0.0.1 sem `X-Forwarded-For` contaria como "deste
  computador". Com a porta própria, tudo que chega por ela é de fora e em HTTPS, com ou sem cabeçalhos. As
  tentativas de senha contam pelo `X-Forwarded-For` se vier e, senão, pelo login do Tailscale.
- **`Origin`.** O `tailscale serve` pode entregar o pedido com o Host dele (127.0.0.1). Nesse caso o Pyron aceita
  quando o navegador declara `Sec-Fetch-Site: same-origin`, ou quando o `Origin` está em `--origem`. Outro site
  continua recusado.
- **Só no modo servidor.** O manifest, os metadados do iPad e o service worker entram por `js/aplicativo.js`
  quando `/api/acesso/eu` diz "servidor". O `index.html` não mudou: o Pyron.exe e a janela local seguem como antes.
- **Cores do manifest.** `theme_color` é `--superficie` (o topo) e `background_color` é `--fundo-trabalho`, os dois
  do tema claro (o manifest só aceita um valor; o tema claro é o padrão).
- **Sem rede.** A tela lembra neste aparelho o último modo visto, só para escolher os textos. Quando a conexão
  volta, ela recarrega e pede a entrada se precisar. Nenhuma permissão vem dessa lembrança.
- **"Abrir pasta" e "Restaurar backup"** só aparecem quando a tela está no próprio computador dos dados
  (endereço 127.0.0.1 ou localhost), dentro ou fora do Pyron.exe.
- **Toque longo** abre o menu ao soltar o dedo, não durante: o soltar fora de um menu já aberto o fecharia.

## O que mudou

| Onde | O quê |
|---|---|
| `app/interface/manifest.webmanifest`, `app/interface/sw.js` | novos |
| `app/interface/js/aplicativo.js` | registra manifest, ícone do iPad e service worker; avisa e recarrega com versão nova |
| `marca/gerar_marca.py` | `--pwa` e `gerar_pwa()`: `icone-app-192`, `-512`, `-mascara-512` (zona segura de 80 %) e `-180` (sem transparência), vetor `pyron-icone-mascara.svg` |
| `app/acesso.py` | `porta_proxy`, `origens`; `python -m app.acesso cabecalhos` para conferir o proxy |
| `app/iniciar.py` | `--porta-proxy` (segunda porta só em 127.0.0.1, no mesmo processo) e `--origem` |
| `app/servidor.py` | tipo `application/manifest+json` registrado no código |
| `js/analise/palco.js` | pinça, arrasto com dois dedos, toque duplo; alças de 44 px no toque (`telas.css`) |
| `js/componentes.js` | `toqueLongo()`; a tabela abre `aoMenu` no toque longo sem abrir dois menus no Android |
| `js/laudo.js` | botão Compartilhar (Web Share com o PDF) quando o aparelho permite |
| `js/casca.js`, CSS | topo encolhe (até 1280 px: Buscar e conta só com ícone; até 960 px: navegação por ícones); Análise e Pendências empilham em retrato; ferramentas do palco só com ícone até 1280 px; textos de "sem conexão" do servidor |
| `js/conferir.js` | rótulo de controle desabilitado fora da regra de contraste (WCAG 1.4.3) |
| Docs | `docs/servidor/tablet.md` (Tailscale, iPad, Android), `docs/servidor/implantacao.md`; capturas em `docs/interface/capturas/v09/` |

## Conferido

### Testes

| Bateria | Resultado |
|---|---|
| `pytest -q -m "not lento"` | 410 passaram, 4 pulados (eram 400 na F1) |
| `testes/test_pwa.py` (10 novos) | cores do manifest iguais aos tokens; ícones nos tamanhos certos e vindos do gerador; o sw.js nunca guarda `/api` nem PDF e confere a regra antes de responder; todo módulo da interface está na casca; o modo local não registra o aplicativo; manifest e sw.js públicos com o tipo certo; porta do proxy sempre de fora e em HTTPS; porta principal continua local; origem configurada; tentativas por login do Tailscale |

### No navegador (Edge sem janela, servidor de teste com cópia de `saida/dados_demo`)

| Conferência | Resultado |
|---|---|
| Instalabilidade (`Page.getInstallabilityErrors`, o mesmo de DevTools › Application) | nenhum erro; manifest lido sem erros |
| Service worker | registrado como `/sw.js?v=0.8.0`, controla a página; cache `pyron-casca-0.8.0` com 62 arquivos, 0 de `/api`, 0 PDF, também depois de abrir inspeções e gerar laudo |
| Sem rede (emulado) | a casca abre do cache, a faixa e a tela dizem "Sem conexão" com a dica do Tailscale; com a rede de volta, a tela recarrega sozinha no Painel |
| Pinça (dedos de 100 para 500 px) | zoom de 100 % para 500 % |
| Dois dedos arrastando | a imagem acompanha |
| Toque duplo | volta a 100 % |
| Ferramenta Ponto no toque | o ponto entra ao soltar o dedo; uma pinça começada com ela ligada não marca ponto |
| Toque longo numa linha de Inspeções | abre o menu (Abrir, Gerar laudo, Definir equipamento, Ver equipamento, Apagar) e não navega |
| Laudo pronto | Compartilhar, Salvar PDF e Abrir laudo |
| Sessão encerrada no servidor durante o uso | tela de entrada com "A sessão terminou"; ao entrar, volta para a tela em que estava |
| Largura da página nos 5 tamanhos (1536 × 816, 1024 × 768, 1180 × 820, 820 × 1180, 800 × 1280) | igual à da janela em todos (antes da F2: 1202 px nos tamanhos de tablet) |
| `conferir.js` com `?toque` (contraste e alvos de 44 px), 7 telas, 1024 × 768 e 820 × 1180, claro e escuro | nenhum achado depois de corrigir as setas da Análise (31 px de largura a 1024 px) |
| axe-core 4.14.0 | 0 violações em 34 rodadas (28 no tablet, 2 de reconferência, sessão terminada, Pendências em retrato, modo local) |
| Modo local | sem manifest, sem service worker, navegação com texto, "Abrir a pasta" e "Restaurar backup" à vista |
| Roteiro da F1 repetido | 17 rodadas do axe sem violações; técnico continua sem ferramentas de edição e sem Configurações |

Capturas: `docs/interface/capturas/v09/` (Painel e Análise nos 5 tamanhos, Inspeções a 1024, Pendências em
retrato, pinça, sem rede, laudo pronto, toque longo).

## Pendências

- **Aparelhos reais.** Instalar no iPad (Safari) e no Android (Chrome) pela rede Tailscale. Precisa do Tailscale
  no servidor e nos tablets, com a conta da equipe; não foi instalado nesta fase.
- **Cabeçalhos reais do `tailscale serve`:** rodar uma vez `python -m app.acesso cabecalhos --porta 8766` e anotar
  aqui se vem `X-Forwarded-For`.
- **Licença de uso do Tailscale:** o plano gratuito é para uso não comercial (até 6 usuários). Para produção na
  empresa, plano pago.
- **Safari e Web Share.** O botão Compartilhar foi visto no Edge do Windows; no iPad depende do `navigator.canShare`
  com arquivos (iPadOS 15 ou mais novo).
- Modelos e Captura ainda mostram ações de administrador para quem não é (pendência da F1).
