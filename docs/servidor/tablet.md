# Pyron no tablet (iPad e Android) pelo Tailscale

Para quem prepara o servidor do Pyron e os tablets da equipe. Escolha de 30/10/2026: HTTPS pelo Tailscale,
plano gratuito. O tablet usa o Pyron como aplicativo instalado (PWA): ícone na tela de início, tela cheia,
sem barra do navegador. Os dados continuam todos no servidor.

## Antes de começar: limites do plano gratuito

Lido na página de preços do Tailscale em 30/10/2026 (<https://tailscale.com/pricing>):

- O plano gratuito (Personal) tem até 6 usuários do Tailscale e aparelhos ilimitados.
- Ele é "só para uso não comercial" ("only suitable for non-commercial use"). O uso pela empresa em produção
  pede um plano pago (Standard, US$ 8 por usuário por mês, na mesma data). Para o período de teste, serve.
- Usuário do Tailscale não é usuário do Pyron. Os tablets podem entrar todos com uma única conta do Tailscale
  da equipe (conta 1 usuário). Cada pessoa continua com o próprio usuário e senha no Pyron.
- O certificado HTTPS do Tailscale publica o nome da máquina e o nome da rede (tailnet) num registro público de
  certificados. Não use nome de máquina com informação sensível.

## 1. No servidor

1. Instale o Tailscale (<https://tailscale.com/download>) e entre com a conta da equipe.
2. No painel do Tailscale (DNS), ligue o **MagicDNS** e, em **HTTPS Certificates**, **Enable HTTPS**.
3. Suba o Pyron no modo servidor com uma porta reservada ao Tailscale (só em 127.0.0.1):

   ```
   python -m app.iniciar --modo servidor --porta 8765 --porta-proxy 8766
   ```

   Tudo que chega pela porta 8766 conta como acesso de fora, em HTTPS. As rotas "só deste computador" ficam
   fechadas por ela, mesmo que o Tailscale entregue o pedido a partir de 127.0.0.1. A porta 8765 continua para
   quem usa o próprio computador do servidor.
4. Publique a porta 8766 na rede do Tailscale, com HTTPS:

   ```
   tailscale serve --bg 8766
   tailscale serve status
   ```

   O `status` mostra o endereço, no formato `https://<máquina>.<tailnet>.ts.net`. Se o comando reclamar da sintaxe,
   confira com `tailscale serve --help` (a forma muda entre versões do Tailscale).
5. Se quiser que o Pyron confira o endereço exato, repita-o no início:
   `--origem https://<máquina>.<tailnet>.ts.net`. Sem isso, o Pyron aceita o pedido quando o próprio
   navegador declara que é do mesmo site.

Como serviço do Windows ou do Linux, veja `docs/servidor/implantacao.md`. Basta acrescentar `--porta-proxy 8766`
à linha de comando. O `tailscale serve --bg` já fica valendo depois de reiniciar.

### Conferência única dos cabeçalhos

A documentação do `tailscale serve` não diz se ele envia `X-Forwarded-For`. O Pyron funciona sem ele: as
tentativas de senha passam a contar pelo login do Tailscale (`Tailscale-User-Login`). Para registrar o que de
fato chega, faça uma vez, com o Pyron parado:

```
python -m app.acesso cabecalhos --porta 8766
```

Abra o endereço `https://<máquina>.<tailnet>.ts.net` no tablet: a página e o console mostram os cabeçalhos
recebidos. Anote o resultado em `docs/v09/2-tablet.md` (seção "Pendências") e pare com Ctrl+C.

## 2. No iPad (Safari)

1. Instale o app **Tailscale** da App Store, entre com a conta da equipe e deixe a VPN ligada.
2. No **Safari**, abra `https://<máquina>.<tailnet>.ts.net`. Deve aparecer a tela "Entrar no Pyron", com
   cadeado e sem aviso de certificado.
3. Entre com o seu usuário e senha do Pyron.
4. Toque em **Compartilhar** (quadrado com seta) e depois em **Adicionar à Tela de Início**. Confirme o nome
   "Pyron".
5. Abra pelo ícone novo: o Pyron ocupa a tela toda, sem a barra do Safari.

No iPad, o laudo abre com "Abrir laudo" e pode ir para o Arquivos, o e-mail ou o WhatsApp pelo botão
**Compartilhar** do próprio diálogo do laudo.

## 3. No Android (Chrome)

1. Instale o app **Tailscale** da Play Store, entre com a conta da equipe e ligue a VPN.
2. No **Chrome**, abra `https://<máquina>.<tailnet>.ts.net` e entre com o usuário e a senha do Pyron.
3. Menu **⋮** e depois **Instalar app** (em algumas versões, **Adicionar à tela inicial** e depois **Instalar**).
4. Abra pelo ícone novo.

## 4. Como o aplicativo se comporta

- **Sempre pela rede.** O aparelho guarda só a casca da tela (páginas, estilos e ícones) para abrir mesmo sem
  rede e avisar "Sem conexão". Inspeções, imagens e laudos nunca ficam guardados no aparelho. Não há edição sem
  rede nesta versão.
- **Atualização.** Quando o servidor muda de versão, a tela avisa e recarrega sozinha.
- **Toque.** No termograma: dois dedos aproximam e afastam (zoom) e arrastam a imagem. Dois toques rápidos
  voltam ao enquadramento. As alças das regiões aceitam o dedo inteiro. Nas listas, segurar uma linha abre o
  menu dela, como o botão direito no computador.
- **Retrato.** Em pé, a Análise mostra o termograma em cima e o painel embaixo. A navegação do topo fica só com
  os ícones.
- **Sessão.** Termina com 12 h sem uso (ou 7 dias). A tela pede a senha de novo e volta para onde estava.
- **Fora do tablet.** "Abrir pasta" e "Restaurar backup" só aparecem no próprio computador do servidor.

## 5. Problemas comuns

| Sintoma | O que fazer |
|---|---|
| Aviso de certificado ou página não abre | Confira se a VPN do Tailscale está ligada no tablet e se o HTTPS está ativo no painel do Tailscale. |
| "No modo servidor, só se entra por HTTPS" | O Tailscale está apontando para a porta principal (8765). Use `tailscale serve --bg 8766`, a porta passada em `--porta-proxy`. |
| "Pedido de outro endereço recusado" | Passe o endereço público em `--origem https://<máquina>.<tailnet>.ts.net`. |
| Não aparece "Instalar app" ou "Adicionar à Tela de Início" | O endereço precisa ser o `https://…ts.net`, não o IP. Entre no Pyron uma vez antes de instalar. |
| Mais de 6 pessoas no Tailscale | Use uma conta do Tailscale da equipe em todos os tablets, ou passe para um plano pago. |
