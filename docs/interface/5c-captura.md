# Etapa 5c · Captura (pasta monitorada, vídeo, celular, alertas)

Data: 26/10/2026. Rota `/nova/#captura` com as abas `#captura` (pasta), `#captura/video`, `#captura/video/<id>`,
`#captura/celular` e `#captura/alertas`, ligadas à API real. Código: a casca das abas em
`app/interface/js/telas/captura.js` e um módulo por aba em `app/interface/js/captura/` (`pasta.js`, `video.js`,
`celular.js`, `alertas.js`), no padrão da Análise (`js/analise/`); `js/rotulos.js` (rótulos das caixas sem se
cobrir) e `js/grafico.js` ampliado (eixo de tempo, clique e cursor). Layout em `app/interface/telas.css`.
Capturas: `docs/interface/capturas/etapa5c/`. As imagens térmicas são do dataset de estudo ScienceDB 10185
(CC BY-NC-SA) e o vídeo é `dados/video_demo.mp4`.

## 1. Estrutura em 1536 × 816

Cabeçalho "Captura" com o estado da pasta monitorada (ligada, com erro ou desligada) e as quatro abas
(decisão da Etapa 1: Monitoramento, Vídeo e Celular viram uma tela; os alertas são o resultado delas). Trocar de
aba não recarrega a tela; o endereço acompanha. A aba Alertas mostra quantos estão pendentes.

| Aba | Primário | Conteúdo |
|---|---|---|
| Pasta monitorada | **Ligar monitoramento** (ligada: Verificar agora e Desligar, secundários) | à esquerda, "Pasta da câmera" (caminho, intervalo, subpastas, instalação e equipamento) e "Alerta" (nível a partir do qual avisa, janela sem repetir, quem recebe pelo WhatsApp); à direita, o estado (ponto, pasta, última verificação, última imagem, analisadas, alertas gerados) e a prévia da mensagem recolhida. Tudo salva sozinho ("Salvo às 01:32") |
| Vídeo | **Enviar vídeo** | ritmo (ao vivo com velocidade ou um quadro a cada intervalo), modelo, escala fixa recolhida; envio com barra de andamento; tabela dos vídeos (primeiro quadro, duração, ritmo, quadros, máxima, situação com andamento) |
| Vídeo aberto | **Salvar quadro como inspeção** | quadro com as regiões e a leitura acima dele (Ao vivo/Pausado, instante, ms, escala); reproduzir, linha do tempo, velocidade, Voltar ao vivo; à direita, quatro números (quadros, ritmo, tempo por quadro, máxima), a máxima no tempo com cursor, momentos com anomalia e o que há no quadro |
| Celular | **Ligar conexão com o celular** | desligado: ilustração, uma linha e o modelo usado; ligado: QR e endereço (Copiar), estado da conexão e Desligar à esquerda; o que o celular está vendo à direita, com as peças marcadas e a barra de cores lida |
| Alertas | (sem primário: ação por linha) | filtro Pendentes · Enviados · Resolvidos · Todos com contagem; tabela (severidade, quando, inspeção, resumo, situação) com WhatsApp e Resolver |

## 2. Decisões e motivo

| Decisão | Motivo |
|---|---|
| Quatro abas numa tela, um módulo por aba | Decisão da Etapa 1; mesma organização da Análise (`js/analise/`) |
| Só a fonte que funciona: a pasta. RTSP, SDK da FLIR e o envio automático pelo WhatsApp Business não aparecem | Etapa 1 ("só fontes que funcionam"): a tela antiga mostrava opções "Em breve" |
| Configuração da pasta salva sozinha, com "Salvo às …"; Ligar valida a pasta e mostra o erro do servidor no próprio formulário | Padrão da Análise; o erro aparece onde se corrige (Postel e Peak-End) |
| Responsável sem telefone ainda não vai para o servidor | Salvando a cada letra, o servidor recusava o WhatsApp vazio enquanto a pessoa digitava o nome |
| O erro guardado de antes de ligar some ao ligar | No teste, a pasta inexistente deixou "Com erro" depois de ligar com a pasta certa |
| Sem pasta definida: a ilustração `captura` e uma frase no bloco de estado, ao lado do formulário | O formulário é a própria ação; a ilustração não empurra os campos para baixo |
| Alertas: WhatsApp abre a mensagem pronta para cada responsável (menu se houver mais de um) e marca "Enviado"; Resolver tem Desfazer | O Pyron não envia sozinho; Desfazer em vez de confirmar (padrão da Análise) |
| Contador da aba Alertas e o do sino atualizam juntos | Evento `pyron:alertas` ouvido pela casca |
| Vídeo: o quadro se ajusta à altura da janela pela proporção do vídeo; a leitura vai acima do quadro | Na primeira captura os controles ficaram abaixo da dobra e a leitura cobria o canto do vídeo |
| Gráfico do vídeo com o mesmo componente do equipamento (`graficoSerie`), eixo em minutos e segundos, pontos só nos quadros fora do normal, clique leva ao instante, cursor no quadro da tela | Componente que aparece 2+ vezes vira um só; centenas de pontos todos marcados viravam ruído |
| Celular desligado: uma linha e o QR depois de ligar (os 4 passos e os dois parágrafos saíram) | Etapa 1 (ajuda no ponto de uso; o detalhe vai para o manual) |
| Celular: as caixas das peças com a cor da classe (`--serie-*`), rótulos fora da caixa sem se cobrir (`js/rotulos.js`) | Mesma regra da página do celular; a cor é identidade de peça, não severidade (a foto do celular não tem temperatura medida) |
| `js/rotulos.js` é uma cópia em módulo de `app/estatico/rotulos.js` | A página do celular (`/e/`) continua usando a versão antiga até a Etapa 6; ali a página do celular passa a usar o módulo |

## 3. Conferido no navegador

Roteiros no Edge sem janela (protocolo de depuração), 1536 × 816, nos dados de demonstração e numa pasta vazia
de rascunho (`pyron-vazio`, apagada depois pela Lixeira):
- Pasta: pasta inexistente → "A pasta C:/nao/existe não existe ou não está acessível." no formulário; pasta
  real, nível Atenção e um responsável → "Salvo às 01:32"; Ligar → Vigiando; uma imagem copiada para a pasta
  entrou depois de ficar estável e gerou o alerta (Programar, FLIR1552.jpg); a aba mostrou "Analisadas 1,
  Alertas gerados 1"; desligado no fim.
- Alertas: WhatsApp abriu `wa.me/5583999990000?text=…` (abertura interceptada no teste) e marcou Enviado;
  Resolver e Desfazer voltaram a Enviado; contadores da aba e do sino acompanharam.
- Vídeo: `video_demo.mp4` (60 s, 600 quadros) com um quadro a cada 0,5 s: durante a análise, "Ao vivo", 101
  quadros, 2,0 q/s, 131 ms por quadro e a curva da máxima; concluído com 120 quadros; linha do tempo, → e
  reproduzir (0:10,0 → 0:11,5); Salvar quadro criou a inspeção (1 → 2); vídeo inexistente com o estado próprio.
- Celular: desligado com os dados reais; o estado ligado foi conferido com a resposta da API simulada só no
  navegador de teste. **A conexão de verdade com um celular não foi ligada nesta etapa**: ela abre um servidor
  na rede local e o Windows pode pedir permissão de firewall. O código do espelho veio da tela antiga, que já
  funcionava com o celular.

## 4. Medidas

**Contraste e alvos** (`js/conferir.js`), claro, escuro e toque: 0 falhas em todas as abas e estados.

| Estado | Textos | Alvos |
|---|---|---|
| Pasta desligada / ligada com responsável | 48 / 49 | 28 / 32 |
| Vídeo, lista vazia / com um vídeo | 29 / 43 | 23 / 25 |
| Vídeo aberto | 53 a 57 | 23 |
| Celular desligado / ligado | 20 / 24 | 16 / 17 |
| Alertas vazio / com um alerta | 17 / 38 | 15 / 22 |

**Proporção de cor** (saturação > 0,35 e brilho > 0,3; estrutura = azul, violeta e cobalto):

| | Estrutura | Total |
|---|---|---|
| Monitoramento antigo / Vídeo antigo / Celular antigo | 16,9 % / 16,5 % / 16,5 % | 17,3 % / 16,8 % / 17,0 % |
| Pasta (claro / escuro / ligada) | 0,8 % / 0,3 % / 0,3 % | 1,0 % / 0,6 % / 0,6 % |
| Vídeo, lista | 0,8 % | 1,1 % |
| Vídeo aberto, fora do quadro térmico (claro e escuro) | 1,0 % | 1,1 % |
| Celular (claro / escuro / ligado) | 0,9 % / 1,0 % / 0,2 % | 1,2 % / 1,2 % / 0,5 % |
| Alertas | 0,2 % | 0,4 % |

## 5. Checklist de UX (12 itens)

| # | Item | Resultado |
|---|---|---|
| 1 | Ação principal em destaque | um primário por aba: Ligar, Enviar vídeo / Salvar quadro, Ligar conexão; Alertas age por linha |
| 2 | No máximo 7 opções por grupo | 4 abas, 4 níveis, 4 filtros de alerta, 5 controles do vídeo |
| 3 | Agrupamento | Pasta da câmera / Alerta / estado; quadro, controles e painel do vídeo |
| 4 | Resposta em < 400 ms | esqueleto na troca de aba, "Salvando…", botões ocupados, barra do envio, "Ao vivo" com o ponto aceso |
| 5 | Convenções | abas, player com linha do tempo e espaço para pausar, QR para o celular |
| 6 | Hover e foco | em todos os controles; pontos do gráfico focáveis |
| 7 | Progresso | envio do vídeo em %, andamento da análise na lista e no "Quadros analisados de 600" |
| 8 | Alvos ≥ 44 px em toque | 0 falhas |
| 9 | Estados vazios | pasta sem definir (`captura`), vídeo sem nenhum (`analise`), celular (`celular`, `procurando` esperando o celular), alertas (`pendencias`), vídeo inexistente (`busca`) |
| 10 | Informação em blocos | seções com título; escala fixa e prévia recolhidas |
| 11 | Hierarquia | título 24, seção 17, números do vídeo 29, corpo 14 a 17 |
| 12 | Complexidade escondida | escala fixa e prévia recolhidas; fontes que não existem fora |

**12/12.**

## 6. Nota pelas 30 Leis de UX

| Lei | Nota | | Lei | Nota |
|---|---|---|---|---|
| Aesthetic-Usability | 2 | | Doherty Threshold | 2 |
| Prägnanz | 2 | | Flow | 2 |
| Von Restorff | 2 | | Goal-Gradient | 2 |
| Similarity | 2 | | Serial Position | 2 |
| Proximity | 2 | | Peak-End | 2 |
| Common Region | 2 | | Zeigarnik | 2 |
| Uniform Connectedness | 2 | | Working Memory | 2 |
| Cognitive Load | 2 | | Jakob | 2 |
| Hick | 2 | | Postel | 2 |
| Miller | 2 | | Tesler | 2 |
| Chunking | 2 | | Occam | 2 |
| Choice Overload | 2 | | Pareto | 2 |
| Cognitive Bias | — | | Selective Attention | 2 |
| Fitts | 2 | | Mental Model | 2 |
| Paradox of the Active User | 2 | | Parkinson | 2 |

**58 de 58 nas 29 leis que se aplicam (60/60).** Achado e corrigido na revisão: na lista de responsáveis cada
linha repetia "Nome" e "WhatsApp", e com três ou mais pessoas o rótulo ficava tão perto da linha de cima quanto
da sua (Proximity); agora os rótulos aparecem só na primeira linha, como cabeçalho, e nas outras ficam para o
leitor de tela.

## 7. O que não entrou

- Ligar o celular de verdade (motivo na seção 3).
- Envio automático pelo WhatsApp e as fontes RTSP e SDK: não existem no servidor (`monitoramento.DISPONIVEL`).
