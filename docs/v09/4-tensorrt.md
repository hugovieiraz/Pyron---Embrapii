# Pyron 0.9 · F4 · TensorRT (e CUDA) pelo ONNX Runtime

Data: 30/10/2026. Sem commit (pedido do usuário); mesmo branch `v09-f1-servidor`.
Máquina: Acer Nitro AN515-55, Intel Core i5-10300H, 15,8 GB, **NVIDIA GeForce GTX 1650 4 GB** (Turing, sm75,
driver 621.01), Windows 11 10.0.26200, SAC desligado. É a placa de teste autorizada pelo usuário; **o servidor NVIDIA
de verdade ainda não existe**, então os números abaixo valem para esta placa.

## Resumo em 3 linhas

1. Feito: escolha do provedor num lugar só (`PYRON_ACELERADOR`, auto = TensorRT > CUDA > DirectML > CPU), cache do motor,
   perfil de formas pelo cartão, montagem do motor em outro processo, estado "Preparando a placa…" em `/api/sistema` e em
   Modelos, `python -m nucleo.detectores.benchmark` (tempo, paridade e sobrecarga), ambiente `.venv-gpu` separado.
2. Medido na GTX 1650: TensorRT FP32 com paridade total com a CPU e 6 vezes mais rápido que ela (27 ms contra 163 ms);
   sobrecarga do ONNX Runtime de 2%, longe dos 15% que justificariam C++ à mão.
3. Pendente: **TensorRT FP16 fora da tolerância numa imagem** (decisão sua; padrão ficou FP32); repetir no servidor
   real e com o modelo treinado da equipe, que não está neste computador.

## O modelo usado

O modelo treinado da equipe (RF-DETR, para-raios) não está neste computador. Para medir, exportei o **RF-DETR Nano
pré-treinado em COCO** (Apache 2.0) pelo próprio pacote `rfdetr`, na mesma arquitetura (DINOv2 + atenção deformável),
no mesmo formato de saída (`dets` + `labels`) e com cartão do Pyron (`imagem_exibida`, 384 × 384, limiar 0,30). As
classes COCO não acham componentes elétricos; para comparar provedores isso não importa: a pergunta é se a CPU e a
placa dão o mesmo resultado na mesma rede. O modelo ficou fora do repositório (`D:\hd_central\pyron-f4`).

Conjunto fixo: as inspeções gravadas em `app/dados_app` (imagem original + matriz de temperatura). 37 imagens; 25
foram puladas porque são arquivos de 2 KB vazios (15 em `app/dados_app` e as 10 da demonstração, cujos termogramas
são desenhados a partir das matrizes). Nada foi escrito nas pastas de dados.

## Paridade contra a CPU

Critério do plano: mesmas classes; IoU >= 0,95; diferença de nota <= 0,02; Tmáx igual quando a caixa é a mesma
(a Tmáx vem da matriz, não do modelo).

| Provedor | Classes iguais | IoU mínima | Δ nota máx. | Tmáx igual (caixas iguais) | Resultado |
|---|---|---|---|---|---|
| DirectML (`.venv`) | 37/37 | 1,0000 | 0,000 | 19/19 | passa |
| CUDA | 37/37 | 0,9999 | 0,000 | 19/19 | passa |
| TensorRT FP32 | 37/37 | 0,9999 | 0,000 | 19/19 | passa |
| TensorRT FP16 | 36/37 | 0,9922 | 0,011 | 16/16 | **fora da tolerância** |

O caso do FP16 (imagem `dados_app/c19e73e1`) é de borda de limiar: na CPU, uma detecção tem nota 0,303 e passa
o limiar de 0,30; no FP16, a mesma detecção tem 0,291 e fica de fora. A diferença de nota (0,012) está dentro da
tolerância, mas a detecção some. **Por isso o padrão ficou em FP32** e o FP16 é opção (`PYRON_TRT_FP16=1`).
Com o modelo da equipe (limiar 0,4 e outras notas), o resultado pode ser outro: vale repetir a paridade com ele.

## Tempo

`detectar()` inteiro (preparo da imagem em Python, rede, leitura da saída), 37 imagens × 3 passadas = 111 medidas,
depois de 3 de aquecimento. 30/10/2026 18:32. Resultados brutos em `docs/v09/medidas-f4/`.

| Provedor | Montagem com cache vazio | Montagem com cache | p50 | p95 | Imagens/s |
|---|---|---|---|---|---|
| CPU | 0,5 s | 2,1 s | 163 ms | 193 ms | 6,0 |
| DirectML (`.venv`) | 1,1 s | | 36 ms | 40 ms | 27,3 |
| CUDA | 1,1 s | 0,9 s | 35 ms | 39 ms | 27,9 |
| TensorRT FP32 | **23 s** | 1,8 s | 27 ms | 30 ms | 36,0 |
| TensorRT FP16 | **94 s** | 1,4 s | 26 ms | 30 ms | 36,6 |

Na GTX 1650, o FP16 quase não ganha do FP32 (a Turing de entrada não tem núcleos tensoriais). Numa placa maior,
a diferença tende a crescer; medir lá.

### Sobrecarga do ONNX Runtime

Pelo perfil do próprio ONNX Runtime (`--sobrecarga`): tempo de cada `model_run` contra a soma dos kernels dentro dele.

| Provedor | Execução | Kernels | Parte do ONNX Runtime |
|---|---|---|---|
| CUDA | 27,6 ms | 17,5 ms | 36,6 % |
| TensorRT FP32 | 20,6 ms | 20,2 ms | 2,0 % |
| TensorRT FP16 | 20,1 ms | 19,7 ms | 2,0 % |

No TensorRT, o motor inteiro é um kernel só e o ONNX Runtime custa 2%. **Não proponho C++ à mão** (o plano só pede
acima de 15%). O que sobra entre os 20 ms da rede e os 27 ms do `detectar()` é o preparo da imagem em Python.

## O que mudou

| Onde | O quê |
|---|---|
| `nucleo/detectores/provedores.py` (novo) | `PYRON_ACELERADOR`; ordem automática; opções do TensorRT (FP32 padrão, cache do motor e de tempos, perfil min/opt/max pelo cartão quando a entrada tem dimensão variável); CUDA; DirectML; sessão da CPU de referência; bibliotecas NVIDIA no caminho de DLLs; `disable_fallback` e conferência depois da primeira conta; montagem do motor em outro processo; `situacao()` |
| `nucleo/detectores/onnx_modelo.py` | a sessão de referência sai de `provedores.criar_sessao(…, "cpu")` |
| `nucleo/detectores/placa.py` | `DetectorAcelerado` (TensorRT, CUDA ou DirectML); `DetectorDirectML` continua como nome antigo; `situacao()` diz "carregando" com o acelerador |
| `app/servidor.py` | `/api/sistema` e `/api/modelos` trazem `acelerador` e onde o modelo ativo roda; no modo servidor, o modelo já sobe na placa (`_preaquecer`) |
| `js/modelos/emuso.js` | "Preparando a placa de vídeo (TensorRT)…" e "O modelo em uso roda na placa de vídeo (TensorRT)", atualizado a cada 5 s enquanto prepara |
| `nucleo/detectores/benchmark.py` (novo) | tempo (p50, p95, imagens/s, montagem), `--paridade`, `--sobrecarga` |
| `requirements-servidor-gpu.txt` (novo) | ambiente do servidor; `.venv-gpu` no `.gitignore` |

## Problemas encontrados e resolvidos (todos com teste)

1. **TensorRT 11 não serve.** O pip instala o 11.4; o ONNX Runtime 1.24 procura `nvinfer_10.dll`. Fixado o
   `tensorrt-cu12-libs==10.16.1.11`. A GTX 1650 (sm75) funciona com ele.
2. **Biblioteca auxiliar do cuDNN fora do caminho.** O cuDNN 9 carrega as "engines" sob demanda; sem a pasta
   `nvidia/*/bin` no caminho de DLLs, a primeira convolução falhava.
3. **Volta silenciosa para a CPU.** Quando a placa falha durante a conta, o ONNX Runtime passa para a CPU sozinho e
   continua ("Falling back… and retrying"); com opção inválida do TensorRT, idem. Agora a sessão de placa tem
   `disable_fallback()` e é conferida depois da primeira conta: erro na placa é erro.
4. **Cache do motor que não grava.** No Windows, caminho acima de 260 caracteres faz a gravação do motor falhar sem
   erro (o motor seria montado de novo, por minutos, a cada subida). O cache vai para `PYRON_CACHE_TRT` ou, se
   `<dados>/cache_trt` ficar longo demais, `%LOCALAPPDATA%\Pyron\cache_trt`.
5. **Servidor parado durante a montagem.** Criar a sessão do ONNX Runtime segura o interpretador Python o tempo todo;
   com o TensorRT montando o motor, o servidor ficou 117 s sem responder nem `/api/saude`, mesmo com a montagem em
   outro fio. Agora a montagem roda em outro processo: o servidor responde em 7 s, mostra "Preparando a placa…" e
   só pausa cerca de 1 s quando lê o motor pronto.

## Conferido

| Bateria | Resultado |
|---|---|
| `pytest -q -m "not lento"` (`.venv`) | 439 passaram, 4 pulados (eram 418 na F3) |
| `testes/test_provedores.py` (16) | ordem automática e pedidos explícitos com o ONNX Runtime simulado; variáveis; opções e perfil do TensorRT; listas de provedores; sessão que não assume ou larga a placa; cache fora de caminho longo; montagem em outro processo; placa e `/api/sistema` seguindo a escolha |
| `testes/test_benchmark.py` (5) | IoU; casamento por classe; Tmáx na matriz (inclusive sem temperatura); paridade que passa e que reprova; imagens que não abrem |
| Modo local (`.venv`, DirectML) | o automático escolhe DirectML, como antes; paridade 37/37 |
| Pyron completo no `.venv-gpu`, modo servidor, cache vazio | responde em 7 s; Modelos mostra "Preparando a placa de vídeo (TensorRT)…" e depois "roda na placa de vídeo (TensorRT)"; axe sem violações (`docs/v09/capturas/f4/`) |

## Pendências e decisões suas

- **FP16:** aceitar FP16 como padrão no servidor real (ganho pequeno nesta placa; uma detecção perdida na borda do
  limiar), ou manter FP32? Hoje: FP32.
- **Servidor real e modelo da equipe:** repetir no servidor NVIDIA, com o modelo treinado:
  `python -m nucleo.detectores.benchmark --modelo modelos/<id> --paridade` e depois sem `--paridade`.
- **Dockerfile:** não feito (o plano pedia aprovação antes).
- **`.venv-gpu`** ocupa cerca de 7 GB neste computador (CUDA, cuDNN, TensorRT e o PyTorch de CPU usado só para
  exportar o modelo de teste). Pode ser apagado; o `requirements-servidor-gpu.txt` refaz o ambiente (sem PyTorch).
