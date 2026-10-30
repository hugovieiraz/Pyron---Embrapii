# Pyron no modo servidor: implantação

Para quem instala o Pyron num computador da equipe (com ou sem placa de vídeo) e libera o acesso para os
engenheiros e técnicos pela rede, pelo navegador ou pelo tablet. Vale a partir da 0.9 (fase F1).

O modo local de sempre não muda: o `Pyron.exe` abre o servidor em `127.0.0.1`, sem login, e ele se desliga
quando a janela fecha. O modo servidor é outro jeito de subir o mesmo programa.

## 1. Como fica montado

```
tablet / notebook ──HTTPS──> Caddy (porta 443) ──HTTP──> Pyron (127.0.0.1:8765, --modo servidor)
```

- O Pyron ouve só o próprio computador (`127.0.0.1`). Quem fala com a rede é o Caddy, que cuida do HTTPS.
- O Pyron só acredita nos cabeçalhos `X-Forwarded-*` que chegam do endereço passado em `--proxy`. Com o
  Caddy no mesmo computador, é `--proxy 127.0.0.1`. Sem isso, o login de fora é recusado (o Pyron não tem
  como saber que a conexão do usuário é HTTPS) e as rotas "só deste computador" ficam fechadas para todos.
- Com o **Tailscale** (escolha de 30/10/2026, passo a passo em `docs/servidor/tablet.md`), o `tailscale serve`
  faz o papel do Caddy. Como ele não documenta se envia `X-Forwarded-For`, o Pyron abre uma segunda porta só para
  ele (`--porta-proxy 8766`): tudo que chega por ela conta como acesso de fora, em HTTPS.
- `--host 0.0.0.0` só é aceito no modo servidor. Mesmo assim, o login exige HTTPS de quem está fora do
  computador, então HTTP puro pela rede não funciona.

## 2. Primeira conta e subida

Na pasta do projeto, com o Python do `.venv`:

```
python -m app.acesso usuario --usuario ana --nome "Ana Lima" --perfil engenheiro --admin --registro "CREA-PB 123456" --assina
python -m app.acesso conferir
python -m app.iniciar --modo servidor --porta 8765 --proxy 127.0.0.1
```

- O primeiro comando pede a senha duas vezes (pelo menos 10 caracteres). Para scripts, a senha pode vir na
  variável `PYRON_SENHA`.
- O servidor não sobe sem ao menos um administrador com usuário e senha.
- As outras contas se criam pela interface: Configurações › Empresa e time, linha "Acesso ao servidor" de cada
  pessoa (usuário, "Definir senha", Administrador). O time tem no máximo 20 pessoas.
- Use `--dados <pasta>` ou `PYRON_DADOS` para os dados ficarem fora da pasta do programa.

### Perfis

| Perfil | Pode |
|---|---|
| Técnico | ver tudo, enviar imagens, vídeos e medidas, comentar, acompanhar pendências de Atenção e Programar (nas Urgentes e Imediatas, só nota) |
| Engenheiro | o do técnico, mais revisar: editar regiões, medições e condições, reprocessar, apagar |
| Engenheiro que assina (com registro) | o do engenheiro, mais emitir laudo. O laudo sai com o nome e o registro de quem está logado, e fica registrado (`GET /api/laudos/emitidos`) |
| Administrador (marca à parte) | configurações, modelos, treinos, monitor e backup |

Rotas que mexem no computador do servidor (abrir pasta, encerrar, restaurar backup, instalar pacotes)
respondem 403 para quem está fora dele, mesmo administrador. A classificação de cada rota está em
`app/acesso.py` e em `docs/v09/0-diagnostico.md`.

### Sessão

Cookie `pyron_sessao` (HttpOnly, SameSite=Strict, Secure no HTTPS). Termina com 12 h sem uso ou 7 dias depois
de entrar. Cinco senhas erradas em 15 minutos bloqueiam aquele usuário naquele endereço por 15 minutos. Trocar
a senha de alguém, tirar a pessoa do time ou apagar o usuário dela encerra as sessões abertas.

## 3. HTTPS

**Tailscale (escolhido):** veja `docs/servidor/tablet.md`. Resumo:

```
python -m app.iniciar --modo servidor --porta 8765 --porta-proxy 8766
tailscale serve --bg 8766
```

**Caddy (alternativa):** <https://caddyserver.com>, licença Apache 2.0, um executável só. Os dois modelos mais comuns:

Domínio próprio, com certificado público automático (o servidor precisa ser alcançável pelo nome):

```
pyron.empresa.com.br {
    reverse_proxy 127.0.0.1:8765
}
```

Rede interna sem domínio público, com a autoridade certificadora do próprio Caddy (o certificado raiz dela
precisa ser instalado em cada tablet e notebook; o passo a passo dos tablets fica para a F2):

```
pyron.interno {
    tls internal
    reverse_proxy 127.0.0.1:8765
}
```

O Caddy já envia `X-Forwarded-For`, `X-Forwarded-Proto` e `X-Forwarded-Host`; não é preciso configurar nada
além do `reverse_proxy`.

## 3b. Placa NVIDIA (TensorRT)

Num servidor com placa NVIDIA, use o ambiente separado `.venv-gpu` (`requirements-servidor-gpu.txt`): ONNX Runtime
com CUDA e TensorRT 10, sem instalar o CUDA no sistema. Na primeira subida, o TensorRT monta o motor do modelo
(de 20 s a alguns minutos, conforme a placa) em outro processo e guarda no cache; nas seguintes, leva 1 a 2 s.
Enquanto monta, Modelos mostra "Preparando a placa…" e as análises seguem no processador.

| Variável | Para quê |
|---|---|
| `PYRON_ACELERADOR` | `auto` (padrão: TensorRT > CUDA > DirectML > CPU), `tensorrt`, `cuda`, `directml` ou `cpu` |
| `PYRON_TRT_FP16` | `1` liga o FP16 (padrão FP32; ver `docs/v09/4-tensorrt.md`) |
| `PYRON_CACHE_TRT` | pasta do cache do motor (padrão `<dados>/cache_trt`; no Windows, caminho curto) |

Medir na placa do servidor: `python -m nucleo.detectores.benchmark --modelo modelos/<id> --paridade`, depois sem
`--paridade` para o tempo.

## 4. Deixar rodando como serviço

### Windows (Agendador de Tarefas, sem programa extra)

Em um prompt de administrador, ajustando os caminhos:

```
schtasks /create /tn "Pyron servidor" /sc onstart /ru SYSTEM /rl HIGHEST ^
  /tr "\"C:\Pyron\.venv\Scripts\pythonw.exe\" -m app.iniciar --modo servidor --porta 8765 --proxy 127.0.0.1 --dados D:\PyronDados"
```

A tarefa precisa rodar na pasta do projeto: em "Propriedades › Ações", preencha "Iniciar em" com `C:\Pyron`.
Com `pythonw.exe` não há console; os erros de subida aparecem no Visualizador de Eventos e o log do uvicorn
pode ser redirecionado trocando para `python.exe ... > D:\PyronDados\servidor.log 2>&1` dentro de um `cmd /c`.
O Controle Inteligente de Aplicativos do Windows pode barrar DLLs sem assinatura (PyTorch com CUDA, por
exemplo); se acontecer, o erro aparece no log e não se contorna.

### Linux (systemd)

`/etc/systemd/system/pyron.service`:

```
[Unit]
Description=Pyron (modo servidor)
After=network-online.target

[Service]
User=pyron
WorkingDirectory=/opt/pyron
Environment=PYRON_DADOS=/srv/pyron/dados
ExecStart=/opt/pyron/.venv/bin/python -m app.iniciar --modo servidor --porta 8765 --proxy 127.0.0.1
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```
sudo systemctl daemon-reload && sudo systemctl enable --now pyron
journalctl -u pyron -f
```

## 5. Backup agendado

O backup pela linha de comando não depende de login e pode rodar com o servidor no ar: o banco é copiado pela
API de backup do SQLite. Sessões abertas não vão para o .zip.

```
python -m app.backup --dados D:\PyronDados --saida E:\Backups\Pyron --manter 30
```

Agende uma vez por dia (Agendador de Tarefas no Windows, `systemd timer` ou `cron` no Linux). A pasta de
saída deve ficar em outro disco ou ser sincronizada para fora do servidor. A restauração continua em
Configurações › Dados e backup, feita no próprio computador do servidor (rota "só deste computador").

## 6. Variáveis de ambiente

| Variável | Para quê |
|---|---|
| `PYRON_DADOS` | pasta de dados (banco, imagens, matrizes, configurações) |
| `PYRON_OBJETOS` | onde ficam imagens e matrizes: `local` (padrão, a pasta de dados) ou `s3://bucket/prefixo` (precisa do extra `[nuvem]`) |
| `PYRON_S3_ENDPOINT` | endpoint de S3 compatível (MinIO, R2), com as credenciais nas variáveis padrão da AWS |
| `PYRON_MODO` | `local` ou `servidor`, o mesmo que `--modo` |
| `PYRON_PROXY` | endereços de proxy confiáveis separados por vírgula, o mesmo que `--proxy` |
| `PYRON_PORTA_PROXY` | porta reservada ao proxy HTTPS (Tailscale), o mesmo que `--porta-proxy` |
| `PYRON_ORIGEM` | endereços públicos aceitos no cabeçalho `Origin`, separados por vírgula, o mesmo que `--origem` |
| `PYRON_SENHA` | só para `python -m app.acesso usuario` em scripts |

## 7. Atualizar

1. Gere um backup (`python -m app.backup ...`).
2. Pare o serviço.
3. Atualize o código (`git pull`) e, se a versão nova pedir, as dependências no mesmo `.venv`. Atenção: o
   `pyproject.toml` ainda não lista as dependências do aplicativo (FastAPI, uvicorn, reportlab); um arquivo de
   requisitos do servidor entra na F4 (`requirements-servidor-gpu.txt`).
4. Suba o serviço. O banco se atualiza sozinho na primeira abertura (`PRAGMA user_version`; a 0.9 leva ao
   esquema 3: comentários, sessões e laudos emitidos).
5. Abra `/api/saude` e confira a versão.

## 8. Limites conhecidos desta versão

- Um processo só (um worker do uvicorn), com os modelos em memória. As análises pesadas entram numa fila
  (`_trava`); o servidor continua respondendo aos outros pedidos enquanto uma imagem é analisada.
- A edição da mesma inspeção por duas pessoas é protegida no salvamento da tela de Análise (resposta 409 e
  aviso para recarregar). Reprocessar (Detectar de novo, Medir) não entra nessa conferência.
- O modo celular (segundo servidor na rede) e a interface anterior (`/antiga`) ficam desligados no modo servidor.
- Sem edição offline. O tablet instala o Pyron como aplicativo (PWA, `docs/servidor/tablet.md`); sem rede, ele só
  abre a casca e avisa.
