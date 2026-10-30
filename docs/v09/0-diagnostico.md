# Pyron 0.9 · F0 · Diagnóstico e pré-voo

Data: 30/10/2026. Branch `v09-f0-diagnostico`, criado a partir de `site-e-time` (9471ea7, ainda não publicado).
Fase somente de leitura e medição: nenhum código do aplicativo mudou e nada foi instalado.

## 1. Máquina e ambiente desta fase

| Item | Valor |
|---|---|
| Computador | Acer Nitro AN515-55, Intel Core i5-10300H, 15,8 GB de RAM |
| Placas | NVIDIA GeForce GTX 1650 4 GB (capacidade 7.5, driver 621.01) e Intel UHD |
| Windows | 11 Home Single Language 10.0.26200 |
| Controle Inteligente de Aplicativos (SAC) | **desligado** (`VerifiedAndReputablePolicyState = 0`; só lido, nada alterado) |
| Python do `.venv` | 3.12.10 |
| ONNX Runtime | `onnxruntime-directml` 1.24.4: `DmlExecutionProvider`, `CPUExecutionProvider` |
| PyTorch | 2.11.0+cu128; CUDA Toolkit 13.3 no PATH |
| Rust (`rustup`, `cargo`, `rustc`) | não instalado |
| Caddy, Tailscale | não instalados |
| OpenSSL | o do Git (`/mingw64/bin/openssl`) |
| Identidade do Git | `GS87 <gabriel.vieira.eletrica@gmail.com>` |
| Testes rápidos (linha de base) | 373 passaram, 4 pulados, 18 desmarcados (`-m "not lento"`, 193 s) |

**Diferenças em relação ao que o plano e o CLAUDE.md supõem** (detalhes na seção 9): o CLAUDE.md descreve o
notebook com RTX 3050 e SAC ligado; esta máquina tem GTX 1650 com CUDA e SAC desligado. Uma prova de SAC feita
aqui não vale para as máquinas de destino.

## 2. Classificação das rotas de `app/servidor.py`

São 122 rotas `@app.*` (121 HTTP e 1 WebSocket; conferido por script que todas aparecem abaixo) mais 3 montagens de arquivos estáticos. Além dos cinco grupos
pedidos, a classificação precisa de mais dois: **público** (sem sessão) e **envio** (o que o técnico faz: mandar
imagem, vídeo, foto e medida proposta). Sem eles, o técnico ficaria sem conseguir trabalhar ou o grupo "revisão"
ficaria largo demais.

### Público (sem sessão)
- `GET /api/saude` (o `Pyron.exe` confere por ela)
- Estáticos: `/` (interface) e `/marca/…`. A casca precisa carregar antes do login; os dados só saem por `/api`.
- Redirecionamentos `GET /nova`, `GET /nova/`, `GET /antiga` e a montagem `/antiga/…` (interface anterior; pergunta 8).

### Leitura (qualquer perfil com sessão)
- Inspeções: `GET /api/analises`, `GET /api/analises/{id_}`, `GET /api/analises/{id_}/imagem.png`,
  `GET /api/analises/{id_}/temperaturas.csv`, `GET /api/analises/{id_}/foto.jpg`, `GET /api/analises/{id_}/original.jpg`,
  `GET /api/analises/{id_}/miniatura.png`, `GET /api/analises/{id_}/vizinhas`, `GET /api/inspecoes.csv`
- Equipamentos e pendências: `GET /api/equipamentos`, `GET /api/equipamentos/{chave}`, `GET /api/pendencias`
- Alertas e estado: `GET /api/status`, `GET /api/alertas`, `GET /api/alertas/{id_}/whatsapp`,
  `GET /api/monitoramento`, `GET /api/monitoramento/previa`
- Referência: `GET /api/criterios`, `GET /api/paletas`, `GET /api/modelos`, `GET /api/exemplos`,
  `GET /api/exemplos/{nome}/miniatura.jpg`, `GET /api/configuracoes/logo.png`
- `GET /api/configuracoes`: **atenção**, devolve telefones e e-mails do time. Na F1 a resposta precisa ser
  reduzida para quem não é administrador.
- Vídeos: `GET /api/videos`, `GET /api/videos/{id_}`, `GET /api/videos/{id_}/quadros/{n}.jpg`
- Medição: `GET /api/medicao/estado`, `GET /api/medicao/instalar` (andamento), `GET /api/medicao/acelerador`,
  `GET /api/medicao/registro`, `GET /api/medicao/registro.csv`, `GET /api/medicao/fotos`,
  `GET /api/medicao/fotos/{codigo}`, `GET /api/medicao/fotos/{codigo}/miniatura`, `GET /api/medicao/videos/{codigo}`,
  `GET /api/medicao/biblioteca`, `GET /api/medicao/biblioteca/{id_}/miniatura.jpg`, `GET /api/medicao/celular`
- Cadastro: `GET /api/cadastro/medidas`, `GET /api/cadastro/equipamentos/{chave}/fases`, `GET /api/cadastro/cameras`
- Treinos e avaliações: `GET /api/treinos`, `GET /api/treinos/ambiente`, `GET /api/treinos/{id_}`,
  `GET /api/treinos/{id_}/previsoes.png`, `GET /api/avaliacoes`, `GET /api/avaliacoes/{id_}`,
  `GET /api/avaliacoes/{id_}/arquivos/{nome}`
- Celular: `GET /api/celular`, `GET /api/celular/qr.png`, `WS /api/celular/ws`

### Envio (técnico e engenheiro)
- `POST /api/analises` (nova inspeção), `POST /api/exemplos/{nome}/analisar`
- `POST /api/videos`, `POST /api/videos/{id_}/cancelar`, `POST /api/videos/{id_}/quadros/{n}/inspecao`
- Medição: `POST /api/medicao`, `POST /api/medicao/comparar`, `POST /api/medicao/previa`, `POST /api/medicao/fotos`,
  `POST /api/medicao/referencia`, `POST /api/medicao/plano`, `POST /api/medicao/video/keyframes`,
  `POST /api/medicao/video/medir`, `POST /api/medicao/video/comparar`, `POST /api/medicao/contexto-2d`,
  `PUT /api/medicao/registro/{codigo}` (medida real)
- Cadastro: `POST /api/cadastro/medidas` (só propõe), `POST /api/cadastro/cameras/{nome}/conferir`
- Comentários: rota nova da F1 (seção 4)

### Revisão (engenheiro)
- `PUT /api/analises/{id_}` (regiões, condições, identificação, medições, exibição), `POST /api/analises/identificacao`
- Reprocessar: `POST /api/analises/{id_}/detectar`, `POST /api/analises/{id_}/segmentar`,
  `POST /api/analises/{id_}/classificar`, `POST /api/analises/{id_}/metodologia_completa`,
  `POST /api/analises/{id_}/parametros`, `POST /api/analises/{id_}/escala`, `POST /api/analises/{id_}/auto_identificar`
- `PUT /api/analises/{id_}/acompanhamento` (pendência), `PUT /api/alertas/{id_}`
- `DELETE /api/analises/{id_}`, `DELETE /api/videos/{id_}` (pergunta 7)
- `POST /api/cadastro/escala`

### Laudo (engenheiro com `assina = true` e registro)
- `GET /api/analises/{id_}/laudo.pdf`, `POST /api/laudos`
- `POST /api/cadastro/medidas/{medida_id}/validar` e `POST /api/cadastro/medidas/{medida_id}/rejeitar`: gravam
  nome e registro de quem valida, o que é um ato de responsável técnico.
- **Atenção:** hoje o responsável do laudo vem do pedido (`responsavel=`), não de quem está logado. Na F1 quem
  assina passa a ser o usuário da sessão.

### Administração
- Configurações: `PUT /api/configuracoes`, `POST /api/configuracoes/logo`, `DELETE /api/configuracoes/logo`,
  `GET /api/sistema` (mostra caminhos de pastas)
- Modelos: `PUT /api/modelos/ativo`, `POST /api/modelos/instalar` (grava o .zip em `modelos/`)
- Treinos e avaliações: `POST /api/treinos/rotulos`, `POST /api/treinos/pacote`, `POST /api/treinos`,
  `POST /api/treinos/{id_}/cancelar`, `POST /api/avaliacoes`, `DELETE /api/avaliacoes/{id_}`
- Biblioteca de contexto: `POST /api/videos/{id_}/gravar-pesos`, `POST /api/videos/{id_}/reconhecer-biblioteca`,
  `POST /api/medicao/video/gravar-pesos`, `DELETE /api/medicao/biblioteca/{id_}`
- Câmeras: `POST /api/cadastro/cameras/ficha`, `POST /api/cadastro/cameras/calibrar`,
  `POST /api/cadastro/cameras/{nome}/posicao`
- Monitor: `PUT /api/monitoramento`, `POST /api/monitoramento/verificar`
- `POST /api/medicao/acelerador/benchmark`
- Backup: `GET /api/backup.zip` (leva todos os dados)
- Celular: `POST /api/celular/ligar`, `POST /api/celular/desligar` (abre outra porta na rede; pergunta 8)

### Só local (403 fora do loopback, mesmo para administrador)
- `POST /api/sistema/abrir-pasta`, `POST /api/encerrar`, `POST /api/sinal`, `POST /api/backup/restaurar`
- `POST /api/medicao/instalar`: roda `pip` e baixa pesos, por isso fica junto dos instaladores.

### Rotas fora de `servidor.py`
O servidor do celular (`app/celular.py › criar_app`) é outro aplicativo, em outra porta, com rotas `/c/{token}/…`
protegidas pelo código do link (`secrets.token_urlsafe(6)`, 48 bits, novo a cada vez que liga). Ele não passa
pelo controle de acesso da F1 e continua como está; a apresentação depende dele.

## 3. Interface em "/" e onde entram o service worker e o manifest

- `app.mount("/", StaticFiles(directory=app/interface, html=True))` é a última montagem; as rotas `/api/*` vêm
  antes. Um arquivo `app/interface/sw.js` sai em `/sw.js` e um `app/interface/manifest.webmanifest` sai em
  `/manifest.webmanifest`, sem rota nova. O escopo do service worker fica na raiz sem o cabeçalho
  `Service-Worker-Allowed`.
- O tipo MIME do `.webmanifest` vem do `mimetypes` do Python, que no Windows também lê o registro. Aqui saiu
  `application/manifest+json`. Num servidor Linux convém registrar o tipo no código, para não depender da máquina.
- O middleware `sem_cache_da_interface` põe `Cache-Control: no-cache` em tudo que não começa com `/api/`. Isso
  já serve ao `sw.js`: o navegador confere a versão a cada navegação.
- Os ícones da página vêm de `/marca/icone-janela-*.png`. Faltam 192, 512 e maskable em `marca/gerar_marca.py`.
- O `theme-color` hoje é trocado pelo JavaScript conforme o tema (`aplicarTema()` em `casca.js`). O manifest só
  aceita um valor fixo; o teste da F2 precisa saber qual token comparar (claro ou escuro).
- A versão do servidor chega à interface por `/api/status` (`definirVersaoServidor`), e a casca já recarrega
  quando a conexão volta com outra versão. O service worker pode reaproveitar esse ponto.
- O `/antiga` fica dentro do escopo "/" do service worker; a F2 precisa deixá-lo fora do cache.

## 4. O que já existe para comentar

| Onde | O que guarda | Autor | Data |
|---|---|---|---|
| `identificacao.observacoes` da inspeção | um texto livre, sai no laudo | não | não |
| `acompanhamento.nota` da pendência | a última nota, até 500 caracteres | não | não |
| `acompanhamento.historico` e tabela `historico_pendencias` | status e nota, até 50 entradas | **não** | sim |
| `acompanhamento.responsavel` | quem cuida da pendência (texto livre) | não é autor | não |

**Falta um registro de comentários com autor e data.** O histórico da pendência tem data mas não autor, e só
existe para inspeções fora do normal. A tabela `comentarios` da F1 (inspeção, região opcional, autor, data, texto)
cobre o caso, e o histórico da pendência ganha o autor na mesma migração. O laudo também não deixa rastro: é
gerado a cada pedido e nada registra quem emitiu nem quando.

## 5. Concorrência com vários usuários

- **SQLite sem WAL.** `journal_mode = delete` (conferido no banco de demonstração). Cada operação abre e fecha
  uma conexão com a espera padrão de 5 s. Com escrita e leitura ao mesmo tempo, leitores esperam o escritor.
  Ligar o WAL resolve o grosso disso, mas cria os arquivos `-wal` e `-shm`, e o backup precisa passar a usar a
  API de backup do SQLite em vez de copiar o arquivo.
- **Escrita sem controle de versão.** `PUT /api/analises/{id_}` lê, altera e grava o JSON inteiro da inspeção sem
  a `_trava` e sem número de versão. Dois engenheiros editando a mesma inspeção: vale a edição de quem gravou por
  último, sem aviso. A F1 precisa de um número de revisão com resposta 409 quando ele mudou.
- **`POST /api/analises` para o servidor inteiro.** A rota é `async` e roda a análise (segundos) direto no laço
  de eventos, segurando um `threading.Lock`. Enquanto uma imagem é analisada, nenhum outro pedido é atendido,
  nem `/api/saude`. As rotas de medição já usam `run_in_threadpool`; esta precisa do mesmo.
- **Um processo do uvicorn com os modelos em memória.** Está certo para a placa (um modelo carregado, uma conta
  por vez em `placa.py`), mas tudo que é pesado disputa a mesma `_trava`. Vários workers duplicariam os modelos na
  memória; a recomendação é continuar com um.
- **Listas carregam tudo.** `armazenamento.listar()` decodifica o JSON de todas as inspeções, e as rotas de
  pendências, equipamentos e vizinhas chamam essa função. Com algumas centenas de inspeções e vários tablets
  atualizando contadores, isso vira gargalo antes do banco.
- **`config.json`** é lido e regravado inteiro a cada mudança, sem trava entre administradores.

## 6. Por que `onnx_modelo.py` força a CPU

A linha existe desde a 0.1 (`503cc51`) e é proposital, não um defeito:

1. `DetectorONNX` é a referência em CPU. A placa entra por subclasse em `placa.py` (`DetectorDirectML`), que monta
   a própria sessão com o que o DirectML exige: `enable_mem_pattern = False`, execução sequencial e uma conta por
   vez na placa (`_trava_placa`).
2. A lista explícita impede que o ONNX Runtime escolha a placa sozinho. Em notebooks com duas placas, a Intel
   integrada vem primeiro e levou ~440 ms por quadro, pior que a CPU; por isso `placa.py` pede
   `device_filter: gpu` e `performance_preference: high_performance`.
3. A sessão da CPU usa metade dos núcleos e sem espera ativa (commit `ff48843`, medido no notebook do Hugo).

Desde `b32175d` (28/10), toda inspeção nova passa por `_na_placa()`, que usa a placa quando ela já está pronta. A
frase de `placa.py` que diz que "a captura que vira inspeção continua no ONNX da CPU" ficou desatualizada. Para a
F4, o ponto único de seleção de providers deve substituir o `_motor()` de `placa.py`, com a CPU mantida como
referência de paridade.

Providers nesta máquina: `DmlExecutionProvider` e `CPUExecutionProvider`, como esperado.

## 7. Prova de SAC

- (a) `pip install typst` e `import typst`: **não feito**, aguarda aprovação. Como o SAC está desligado aqui, a
  prova só mostraria que o pacote funciona. A prova de verdade precisa de uma máquina com o SAC ligado (pergunta 10).
- (b) `rustup` e `cargo` não existem nesta máquina. Nada foi instalado.

## 8. Tempo do laudo atual (reportlab)

Método: script fora do repositório sobre uma cópia de `saida/dados_demo` (10 inspeções, esquema 2), chamando
`laudo.gerar()` e `laudo.gerar_relatorio()` como as rotas fazem, com uma geração de aquecimento antes de medir. O
conjunto de 50 é o de 10 repetido cinco vezes, porque a rota descarta ids repetidos e a demonstração não tem 50
inspeções. Responsável padrão, sem logo. Máquina da seção 1, 30/10/2026 11:50.

| Caso | Mediana | Mín. | Máx. | Páginas | PDF | Repetições |
|---|---|---|---|---|---|---|
| Primeiro laudo, frio (registra fontes) | 515 ms | | | 3 | | 1 |
| 1 inspeção (`gerar`) | 110 ms | 109 ms | 112 ms | 3 | 323 KB | 5 |
| 10 inspeções (`gerar_relatorio`) | 699 ms | 691 ms | 724 ms | 13 | 1667 KB | 5 |
| 50 inspeções (10 × 5) | 1958 ms | 1943 ms | 2072 ms | 56 | 1756 KB | 3 |

O PDF de 50 quase não cresce porque o reportlab reaproveita imagens iguais. Com 50 inspeções diferentes o arquivo
deve passar de 8 MB; isso não foi medido. A importação do servidor levou 14,6 s nesta máquina.

## 9. Conflitos e desvios encontrados

1. **Identidade do Git.** O plano trata o GS87 como "o colaborador que envia direto ao main". Nesta máquina o
   próprio usuário do Git é o GS87, e o outro autor é `hugovieiraz`. A regra de integrar por merge continua; só muda
   quem é o outro.
2. **Placa NVIDIA aqui.** O plano diz que este computador não tem CUDA. Ele tem uma GTX 1650 (4 GB, Turing) e o
   CUDA 13.3. Ela não substitui o servidor, mas permitiria testar a seleção do TensorRT num ambiente separado, sem
   tocar no `.venv` (restrição 6).
3. **SAC desligado aqui.** As restrições de SAC vêm do notebook do Hugo. Os testes de bloqueio da F3 e da F5 só
   valem numa máquina com o SAC ligado.
4. **`AGENTS.md` da pasta acima** descreve outro projeto (Lumiére). Não se aplica ao Pyron e foi ignorado.
5. **`Pyron.exe`** em `lancador/dist` tem 60 KB, abaixo do limite de ~100 KB.
6. **Branch de partida.** `site-e-time` tem um commit do GS87 (9471ea7) ainda não enviado. O branch da F0 partiu dele.
7. **Tempo dos testes.** O CLAUDE.md diz ~85 s para os testes rápidos; aqui levaram 193 s. É diferença de máquina.

## 10. Perguntas abertas (portão da F0)

1. **Servidor NVIDIA.** Existe? Qual placa, sistema (Windows ou Linux), driver e se há Docker. Enquanto não houver,
   a GTX 1650 desta máquina pode servir, num ambiente separado, para a validação preliminar da F4?
2. **Acesso remoto e HTTPS para os tablets.** Tailscale (com o HTTPS dele), CA interna instalada nos tablets, ou
   domínio próprio com Caddy e certificado público? Isso define a F2.
3. **Assinatura do laudo.** Basta o nome e o registro de quem está logado, com trilha de auditoria, ou precisa de
   assinatura digital ICP-Brasil no PDF? A segunda traz dependência e licença novas.
4. **Fonte do laudo Typst.** As fontes livres boas são quase todas SIL OFL (IBM Plex Sans, Noto Sans, Source Sans 3).
   Recomendação: aprovar OFL só para fontes, como já acontece com a Chakra Petch da marca. Qual fonte?
5. **Licenças fora de MIT/Apache que o plano vai precisar:** TensorRT e CUDA/cuDNN (licenças da NVIDIA). O `typst`
   do PyPI, o Caddy e o Tauri são Apache 2.0 ou MIT. O cliente do Tailscale é BSD-3, com serviço proprietário.
6. **Tablets.** Quais modelos e versões de iPadOS e Android, quantos usuários ao mesmo tempo, e se há MDM para
   instalar certificado.
7. **Perfis.** Técnico pode mudar o status de uma pendência ou só comentar? Apagar inspeção fica com engenheiro ou só
   com administrador? Administrador vira uma marca nova no cadastro do time (`config.json › responsaveis` só tem
   `engenheiro` e `tecnico`)? O login é pelo e-mail do cadastro?
8. **Modo servidor.** A interface `/antiga` fica fora no modo servidor? O modo celular (segundo servidor em
   `0.0.0.0`) pode ser ligado no servidor ou fica só no modo local?
9. **WAL do SQLite.** Ligar só no modo servidor ou também no local? Nos dois casos o backup passa a usar a API de
   backup do SQLite.
10. **Prova de SAC do Typst.** Aprova `pip install typst` no `.venv` desta máquina, sabendo que aqui o SAC está
    desligado? A prova de verdade fica para uma máquina com o SAC ligado; qual?
11. **Git.** Envio o `site-e-time` antes de começar a F1, ou os branches da 0.9 seguem a partir dele sem publicar?

## 11. Respostas do usuário (30/10/2026)

| # | Decisão |
|---|---|
| 1 | A GTX 1650 desta máquina pode ser usada nos testes da F4, num ambiente separado do `.venv`. |
| 2 | HTTPS em aberto: os formatos gratuitos ainda estão em teste. |
| 3 | Assinatura do laudo: nome e registro de quem está logado. |
| 4 | Fontes SIL OFL aprovadas. |
| 5 | Todas as licenças listadas aprovadas (NVIDIA TensorRT, CUDA e cuDNN incluídas). |
| 6 | Sem previsão de usuários; por ora o time fica limitado a 20 pessoas. |
| 7 | Técnico muda o status da pendência, menos nas urgentes e imediatas. Só engenheiro apaga inspeção. Administrador é uma marca nova no cadastro. Login por nome de usuário e senha definidos no cadastro. |
| 8 | Sem resposta. Suposição da F1: no modo servidor, `/antiga` leva para `/` e o modo celular não liga (só no modo local). |
| 9 | WAL nos dois modos. |
| 10 | `typst` instalado no `.venv` (0.15.0, Apache 2.0; `typst.compile` gerou PDF). A prova de SAC fica para depois. |
| 11 | Não fazer commit por enquanto. O commit local da F0 foi desfeito; as mudanças ficam no disco. |
