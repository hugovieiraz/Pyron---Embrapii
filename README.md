<p align="center"><img src="app/estatico/marca/logo.png" alt="Pyron: Manutenção Preditiva, Termografia Digital" width="260"></p>

# Pyron

Manutenção preditiva por termografia para ativos elétricos, começando por transformadores e
equipamentos de subestação. Lê a temperatura de cada pixel, encontra componentes e pontos quentes,
compara cada um com o limite do componente e com as outras fases, classifica a severidade e gera o
laudo.

**Estado:** MVP 0.1 (aplicativo local funcionando; detector de componentes aguardando rótulos).

## Abrir o aplicativo

Dois cliques em **`Pyron.exe`** na área de trabalho. Aparece a tela de abertura, o motor carrega
em poucos segundos e a interface abre numa janela própria (Edge em modo aplicativo, sem barra de
endereço). Tudo roda só neste computador, em `http://127.0.0.1:8765`. Não há console nem nada para
encerrar: o servidor se desliga sozinho quando a última janela é fechada.

O `.exe` é um lançador pequeno (C#, compilado pelo `csc.exe` que vem com o Windows) que guarda o
caminho desta pasta. Para gerar de novo, por exemplo depois de mover o projeto:

```bash
.venv/Scripts/python.exe lancador/construir.py
```

Sem o `.exe`, pela pasta do projeto:

```bash
.venv/Scripts/python.exe -m app.iniciar --janela
```

Diagnóstico: `Pyron.exe --verificar` sobe o servidor escondido, confere se respondeu e desliga; o
resultado fica em `app/dados_app/verificacao.txt`. Erros do servidor ficam em
`app/dados_app/servidor.log`.

> O lançador não é assinado digitalmente. Com o Controle Inteligente de Aplicativos do Windows
> ligado, uma versão com a logo embutida (390 KB) foi bloqueada; a versão atual (≈100 KB, logo lida
> da pasta do projeto) passa. Para distribuir a clientes, o caminho é assinar o executável.

## Como a severidade é decidida

Temperatura sozinha não diz nada; o Pyron compara cada região com duas referências da NBR 15866 e
fica com a pior:

1. **Máxima temperatura admissível (MTA) do componente**, com a temperatura projetada para plena
   carga: `T_proj = T_amb + (T − T_amb) · (100 / carga)²`. Faixas: > 60% da MTA atenção, > 70%
   programar, > 80% urgente, > 100% imediato. A biblioteca de componentes (Configurações) traz as
   MTAs de partida com a fonte de cada uma e pode ser editada.
2. **ΔT entre componentes semelhantes** (as três fases): 5–10 °C atenção, > 10–20 programar,
   > 20–40 urgente, > 40 imediato. Para-raios e isoladores aquecem por fuga, não por carga: faixas
   próprias (2 / 5 / 10 °C) e sem correção de carga.

Também mostra até que carga o componente chega à MTA. Os detalhes e as fontes estão em
[`docs/04_referencias_de_temperatura.md`](docs/04_referencias_de_temperatura.md).

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `nucleo/` | Motor sem interface: leitura radiométrica FLIR (`flir.py`), inversão de paleta (`paleta.py`), entrada única (`entrada.py`), referências de temperatura (`referencias.py`), medição e severidade (`analise.py`), desenho (`render.py`), detectores (`detectores/`) |
| `app/` | Servidor local (FastAPI), laudo em PDF, inspeções salvas e interface web (`estatico/`) |
| `lancador/` | `Pyron.exe`: fonte C# e script de construção |
| `marca/` | Logo original e o script que gera símbolo, ícones e favicon (`gerar_marca.py`) |
| `ml/` | Treino de detectores a partir de rótulos do CVAT, avaliação e exportação ONNX |
| `modelos/` | Modelos treinados instalados (ver `modelos/LEIA-ME.md`) |
| `experimentos/` | Inventário do dataset (`e00`) e avaliação da inversão de paleta (`e01`) |
| `ferramentas/` | Download do dataset de estudo |
| `testes/` | `pytest -q` |
| `docs/` | Visão e roteiro, pesquisa, estudos |

## Documentos

| Documento | Conteúdo |
|---|---|
| [`docs/00_visao_requisitos_roteiro.md`](docs/00_visao_requisitos_roteiro.md) | Visão, requisitos, arquitetura, propostas e roteiro de fases |
| [`docs/01_pesquisa_pratica_dados_ferramentas.md`](docs/01_pesquisa_pratica_dados_ferramentas.md) | Como os profissionais trabalham, datasets e ferramentas |
| [`docs/02_estudo_dataset_subestacao.md`](docs/02_estudo_dataset_subestacao.md) | Plano do estudo com o dataset público |
| [`docs/04_referencias_de_temperatura.md`](docs/04_referencias_de_temperatura.md) | Normas, MTAs, projeção para plena carga e tabelas de prioridade |
| [`modelos/LEIA-ME.md`](modelos/LEIA-ME.md) | Como um modelo treinado entra no software |

## Instalação do zero

```bash
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install numpy pillow scipy matplotlib pytest rapidocr-onnxruntime onnx onnxruntime fastapi "uvicorn[standard]" python-multipart reportlab httpx
.venv/Scripts/python.exe ferramentas/baixar_sciencedb.py   # dataset de estudo (CC BY-NC-SA 4.0, só estudo)
.venv/Scripts/python.exe experimentos/e00_inventario.py
.venv/Scripts/python.exe lancador/construir.py              # gera o Pyron.exe na área de trabalho
```

Para treinar detectores (`ml/`), instale também PyTorch com CUDA (`torch` e `torchvision`, índice
cu126 do pytorch.org).

Os dados (`dados/`), resultados (`saida/`), inspeções salvas (`app/dados_app/`) e os modelos
treinados não vão para o repositório.
