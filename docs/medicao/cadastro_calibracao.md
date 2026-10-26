# Cadastro de equipamentos medidos e calibração de câmeras (26/10/2026)

Código: `nucleo/medicao/camera.py`, `app/cadastro_medidas.py` e as rotas `/api/cadastro/*` em `app/servidor.py`.
Testes: `testes/test_medicao_cadastro.py` (fotos sintéticas; ainda sem foto real).

## Ideia

**A escala vem de algo medido uma vez e guardado, e não de um modelo a cada foto.** Os "pesos" que valem para
qualquer foto depois são de dois tipos:

1. **O perfil de cada câmera:** focal, centro óptico e distorção da lente. Não há rede neural nem treino; esses
   parâmetros físicos valem para todas as fotos daquela câmera.
2. **As medidas de cada equipamento**, validadas por engenheiro. Uma vez cadastrado, cada componente vira
   referência de escala em toda foto futura do equipamento, com qualquer câmera cadastrada.

## Câmera

| Tipo | Como se cadastra | Folha |
|---|---|---|
| Celular ou câmera visual | `calibrar`: de 5 a 20 fotos da folha ChArUco em ângulos variados | uma vez por câmera |
| Térmica (não enxerga a folha) | `perfil_da_ficha`: resolução e campo de visão da ficha técnica; conferir em bancada | nunca |
| Câmera fixa | perfil, mais **uma** foto de instalação com a folha (plano de referência e pontos da cena) | uma vez na instalação |

- **Outra resolução:** com a mesma proporção, o perfil é reescalado sozinho, inclusive em foto de pé ou deitada.
  Foto cortada é recusada.
- **Câmera fixa:** cada foto nova é comparada com a de instalação (pontos ORB e homografia com RANSAC). Se a câmera
  mexeu mais de 2 px, a posição deixa de valer e o programa pede nova calibração.

Medido no sintético: a calibração achou a focal com erro menor que 1 %, o centro óptico com menos de 10 px de
diferença e a distorção da lente simulada. Uma câmera parada deu deslocamento menor que 1 px; deslocada 12 px, foi
recusada.

## Medida de um equipamento

**Estados de uma medida:**
- **proposta:** registrada pelo programa ou por uma pessoa, com método, incerteza e origem;
- **validada** ou **rejeitada:** decidida por engenheiro;
- **substituída:** uma validada que foi trocada por outra.

**Regras:**
- A validação exige o nome do engenheiro e o registro profissional (CREA).
- Quem registrou a medida não pode validá-la.
- A rejeição exige motivo.
- Medida validada não se edita: corrigir é propor uma nova que a substitui. A antiga fica como substituída, e todo
  passo vai para o histórico (quem, quando, o quê).
- Só uma medida validada por componente e medida ao mesmo tempo (garantido por um índice único no banco).
- **Só medida validada dá escala.** A rota `/api/cadastro/escala` recusa as outras.

**Conferência das fases:** componentes da mesma classe e medida nas fases A, B e C são comparados. Diferença acima
de 3 % sinaliza para o engenheiro antes da validação.

**Banco próprio:** `cadastro_medidas.sqlite`, na pasta de dados. Fica ligado às inspeções pela chave do equipamento
(`app.equipamentos.chave`) e não muda o esquema do banco de inspeções.

## Escala de uma foto nova

Entram o componente cadastrado e validado, a câmera cadastrada e o tamanho dele em pixels na foto (que virá do
detector e do contorno). Saem:
- px por cm;
- distância até a câmera;
- incerteza, que soma a da medida cadastrada e 1 px em cada ponta.

Exemplo de conta: para-raio de 120 cm na FLIR C5 (54° em 160 px) ocupando 37,7 px dá 5,0 m. Cada pixel ali vale
3,2 cm, então 1 px de erro em cada ponta dá ±5 %.

## Rotas

| Rota | O que faz |
|---|---|
| `GET /api/cadastro/cameras` | câmeras cadastradas |
| `POST /api/cadastro/cameras/ficha` | câmera pela ficha técnica |
| `POST /api/cadastro/cameras/calibrar` | câmera pelas fotos da folha |
| `POST /api/cadastro/cameras/{nome}/posicao` | câmera fixa: foto de instalação |
| `POST /api/cadastro/cameras/{nome}/conferir` | a câmera fixa mexeu? |
| `GET/POST /api/cadastro/medidas` | listar e propor medidas |
| `POST /api/cadastro/medidas/{id}/validar` e `/rejeitar` | decisão do engenheiro |
| `GET /api/cadastro/equipamentos/{chave}/fases` | conferência das fases |
| `POST /api/cadastro/escala` | escala de uma foto por um componente validado |

## Falta

- A tela (cadastro, fila de validação do engenheiro, calibração de câmera).
- Ligar o detector (RF-DETR) e o contorno ao `/api/cadastro/escala`, para que o tamanho em pixels saia sozinho.
- Validar em foto real: calibrar um celular de verdade, conferir a FLIR C5 em bancada e medir componentes
  conhecidos.
