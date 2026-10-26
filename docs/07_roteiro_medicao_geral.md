# Roteiro: medir objetos em foto comum (para rodar numa sessão na nuvem)

Data: 26/10/2026. Base: `docs/05_pesquisa_medicao_dimensional.md` (pesquisa) e `docs/06_plano_medicao.md`
(diagnóstico do código atual). Este roteiro é o que a sessão na nuvem executa, fase por fase, até o critério de
pronto de cada uma.

## 0. Objetivo e decisões já tomadas

**Objetivo:** dada uma foto comum (celular, câmera), medir o comprimento, a altura e a largura de um objeto
qualquer (guarda-roupa, porta, régua) **sem precisar de régua na foto**. Uma referência de tamanho conhecido na
foto, quando houver, corrige a escala. Os objetos de medida conhecida servem de gabarito: o modelo não lê as
marcações, estima, e a gente compara com o valor real.

**Decisões** (não rediscutir; motivo ao lado):

| Decisão | Motivo |
|---|---|
| Profundidade métrica com **MoGe-2** (Microsoft) | uma foto só dá os pontos em metros e a lente da câmera; licença MIT, confirmada no arquivo oficial |
| Contorno com **SAM 2.1** pelo `transformers` (`Sam2Model`, já instalado aqui: transformers 5.17) | licença Apache 2.0; aceita ponto ou caixa como pista; não precisa de pacote novo |
| Medida em 3D (pontos do objeto em metros), não em pixels | aguenta foto de lado e objetos a distâncias diferentes |
| Sem referência: mostra a medida estimada **com a incerteza**; com referência: corrige a escala | a validação diz quanto cada modo erra |
| Fica de fora o **Depth Pro** (Apple) | licença "pessoal", incerta para produto vendido |
| Fica de fora tudo que for CC BY-NC, AGPL ou GPL | o Pyron será vendido |
| Código em português, módulos novos em `nucleo/medicao/` | regra do projeto (`CLAUDE.md`, seção 4) |

**Pesos** (Hugging Face, conferidos em 26/10/2026):

| Modelo | Arquivo | Tamanho | Licença |
|---|---|---|---|
| `Ruicheng/moge-2-vitl-normal` | `model.pt` | 1 262 MB | MIT |
| `Ruicheng/moge-2-vitb-normal` | `model.pt` | 400 MB | MIT |
| `Ruicheng/moge-2-vits-normal` | `model.pt` | 134 MB | MIT |
| `facebook/sam2.1-hiera-small` | `model.safetensors` | 176 MB | Apache 2.0 |
| `facebook/sam2.1-hiera-base-plus` | `model.safetensors` | 308 MB | Apache 2.0 |

## 1. Antes de abrir a sessão na nuvem (feito pelo Hugo, no computador)

1. Tirar as fotos de gabarito com o celular, em JPEG original (sem recorte e sem mandar pelo WhatsApp, que tira
   os dados da lente):

   | Objeto | Medida real | Fotos |
   |---|---|---|
   | Régua | 30 cm | 3: de frente a ~50 cm, de frente a ~1 m, inclinada |
   | Folha A4 | 29,7 × 21,0 cm | 3: na mesa, na parede, segurada |
   | Cartão de banco ou de plano (tamanho ID-1) | 8,56 × 5,40 cm | 2 |
   | Guarda-roupa | medir com trena: altura e largura | 3: de frente, de lado, de longe |
   | Porta | medir com trena | 2 |
   | Cena com duas referências juntas (A4 e régua no mesmo plano) | as duas | 3 |

2. Pôr as fotos em `testes/gabarito/` (a pasta `dados/` fica fora do git) e preencher
   `testes/gabarito/gabarito.csv`:

   ```
   arquivo,objeto,medida,valor_cm,referencia_na_foto,observacao
   regua_frente_50cm.jpg,regua,comprimento,30.0,,de frente a 50 cm
   a4_parede.jpg,folha_a4,altura,29.7,,colada na parede
   a4_parede.jpg,folha_a4,largura,21.0,,
   guarda_roupa_frente.jpg,guarda_roupa,altura,212.0,,medido com trena
   duas_ref_1.jpg,regua,comprimento,30.0,folha_a4,A4 ao lado da régua
   ```

3. Fazer commit e push (`git push origin interface-nova:main`, conferindo antes `git log HEAD..origin/main`).
   As fases 1 a 3 não dependem das fotos e podem começar antes.

## 2. Fases (na nuvem)

A sessão na nuvem é Linux e provavelmente **sem placa de vídeo**: todo código escolhe o dispositivo sozinho
(`cuda` se houver, senão `cpu`) e nada depende do Windows, do DirectML ou de `dados/` e `app/dados_app/`.
Cada fase termina com commit no branch `medicao-geral` (nunca direto no `main`, que recebe commits do Gabriel) e
os testes passando: `python -m pytest -q`.

### Fase 1: geometria, sem modelo nenhum

`nucleo/medicao/geometria.py`, funções puras sobre NumPy:
- `extensoes(pontos, mascara)`: pontos (H × W × 3, metros) e máscara → comprimento, altura e largura pelos eixos
  principais (PCA) dos pontos do objeto, com percentis 2 a 98 para descartar pontas soltas;
- `plano(pontos, mascara)`: ajuste de plano (RANSAC simples) para objetos planos (régua, A4, porta) e medidas
  dentro do plano;
- `distancia(pontos, p1, p2)`: distância 3D entre dois pixels clicados (mediana de uma vizinhança de 5 × 5);
- `corrigir_escala(medidas, referencia_estimada, referencia_real)`: fator único aplicado à cena;
- `incerteza(...)`: soma do erro de pixel (1 px de cada lado, convertido em metros pela profundidade local) com a
  dispersão dos pontos.

Testes em `testes/test_medicao_geometria.py` com cenas sintéticas: plano de 2,10 × 0,90 m a 3 m de uma câmera
pinhole conhecida, o mesmo plano girado 30°, régua de 0,30 m a 0,5 m, e ruído gaussiano na profundidade.
**Pronto quando:** erro abaixo de 0,5 % nas cenas sem ruído e a incerteza cobrindo o erro nas com ruído.

### Fase 2: adaptadores dos modelos

- `nucleo/medicao/profundidade.py`: carrega o MoGe-2 só quando usado (`pip install git+https://github.com/microsoft/MoGe.git`),
  escolhe o dispositivo, devolve pontos em metros, máscara de pixels válidos e a lente estimada; aceita a lente do
  EXIF quando existir (focal em 35 mm equivalente → pixels).
- `nucleo/medicao/segmentar.py`: `Sam2Model` e `Sam2Processor` do `transformers` com `facebook/sam2.1-hiera-small`;
  `mascara_por_ponto(imagem, (x, y))` e `mascara_por_caixa(imagem, caixa)`; o codificador roda uma vez por imagem.
- Pesos baixados para `modelos/medicao/` (fora do git, como os outros modelos).
- Testes pulam sozinhos se o pacote ou os pesos não estiverem (como os de PyTorch hoje).
- **Pronto quando:** uma foto qualquer passa de ponta a ponta (ponto clicado → máscara → medidas) na CPU, com o
  tempo de cada etapa anotado.

### Fase 3: avaliação com o gabarito

`ml/avaliar_medicao.py`: lê `testes/gabarito/gabarito.csv`, mede cada objeto (o ponto da pista é o centro do
objeto, marcado uma vez num `testes/gabarito/pistas.json`) e grava `saida/medicao/relatorio.json` e uma tabela
em Markdown com, para cada foto:
- valor real, estimado sem referência, estimado com referência, erro absoluto e relativo;
- tempo por etapa;
- MoGe-2 ViT-S, ViT-B e ViT-L lado a lado.

Sem fotos ainda: rodar nas cenas sintéticas e deixar pronto. **Pronto quando:** o relatório sai para todas as
fotos do gabarito, com erro mediano e intervalo de 95 % por modelo e por modo (com e sem referência).

### Fase 4: API

No `app/servidor.py`:
- `POST /api/medicao` (imagem + ponto, caixa ou dois pontos; referência opcional com o tamanho real) → medidas
  em cm, incerteza, método e tempos;
- `GET /api/medicao/estado` (modelos instalados, dispositivo).

Testes com o `TestClient`, com os modelos substituídos por falsos (os testes não baixam nada). **Pronto quando:**
os testes passam sem os pesos e o endpoint responde em foto real com os pesos.

### Fase 5: tela

Aba **Medir foto** em Captura (`js/captura/medir.js`, padrão de `telaComAbas`, `docs/interface/5c-captura.md`):
- abrir uma foto; clicar no objeto (mostra o contorno do SAM);
- resultado: altura, largura e comprimento, com ± e o método;
- opcional: marcar uma referência e informar o tamanho (régua, A4, cartão em lista pronta);
- estados de carregando, vazio e erro como nas outras telas;
- seguir `CLAUDE.md` seção 0 (tokens, nada abaixo de 14 px, alvo de 44 px, cobalto só na ação).

**Pronto quando:** `pytest -q` passando, `node --check` nos `.js`, e contraste e alvos com 0 falhas no `?conferir`.

### Fase 6: otimização (no computador do Hugo, com a RTX 3050)

Na nuvem não há placa de vídeo nem Windows; esta fase volta para o computador. Ver a parte C.

## 3. Como a sessão deve trabalhar

- Ler antes: `CLAUDE.md`, este roteiro, `docs/05_pesquisa_medicao_dimensional.md`, `docs/06_plano_medicao.md`.
- Uma fase por vez, commit no fim de cada uma, com o que foi medido na mensagem.
- Pedir antes de baixar algo que não esteja na lista de pesos acima.
- Números medidos, não supostos. Disse "testado", rodou.
- Ao terminar ou ao faltar crédito: escrever o estado em `docs/07_roteiro_medicao_geral.md`, seção 6
  (Registro), e fazer push do branch.

Texto para colar ao abrir a sessão na nuvem:

> Siga docs/07_roteiro_medicao_geral.md a partir da primeira fase não marcada no Registro (seção 6). Trabalhe no
> branch medicao-geral, faça commit e push ao fim de cada fase e anote no Registro o que foi feito e medido.
> Não baixe nada fora da lista de pesos do roteiro sem perguntar.

---

## Parte B: roteiro de pesquisa (modelos atuais)

O que comparar, sempre no gabarito da seção 1, com licença conferida no arquivo oficial antes de entrar no código.

**Profundidade e geometria de uma foto**

| Modelo | Licença (situação em 26/10/2026) | Por que olhar |
|---|---|---|
| MoGe-2 (Microsoft, 2025) | MIT, conferida | escolhido; pontos em metros e lente |
| Depth Anything V2, versão métrica interna (Hypersim, pequena) | Apache 2.0 segundo a documentação da Lightly, **conferir no cartão oficial** | leve; só para ambiente interno |
| Depth Anything V2, versão métrica externa | CC BY-NC-SA | fora (não comercial) |
| UniDepth V2 | **conferir** | estima a lente junto |
| Metric3D v2 | uma cópia do repositório diz "não comercial", **conferir** | bom nos testes externos da revisão de 2025 |
| Depth Pro (Apple) | licença "pessoal" | fora, a não ser que a Apple esclareça |
| Depth Anything 3 e sucessores do MoGe | **conferir se existem e a licença** | acompanhar novidades de 2026 |

**Várias fotos (mais precisão, objeto grande)**

| Modelo | Licença | Uso |
|---|---|---|
| VGGT (Meta, CVPR 2025) | **conferir** (há versão com licença comercial separada) | 3 a 10 fotos em volta do objeto; escala por referência |
| MASt3R / DUSt3R | CC BY-NC-SA | fora |
| COLMAP | BSD | clássico, sem aprendizado; referência de comparação |

**Achar o objeto pelo nome (sem clicar)**

| Modelo | Licença | Uso |
|---|---|---|
| SAM 3 (Meta, nov. 2025) | SAM License (própria; resumos dizem que permite uso comercial, **conferir o texto**) | "wardrobe" → todas as máscaras |
| Grounding DINO | Apache 2.0 | texto → caixa, depois SAM 2 |
| OWLv2 (Google) | Apache 2.0 | texto → caixa, leve |
| Florence-2 (Microsoft) | MIT | texto → caixa e legenda |
| YOLO-World | GPL | fora |

**Perguntas que a pesquisa responde, com número:**
1. Qual o erro do MoGe-2 sem referência no gabarito (mediana e 95 %), por distância?
2. Quanto a referência na foto reduz esse erro?
3. ViT-S, ViT-B ou ViT-L: quanto se perde de acerto para ganhar tempo?
4. A lente do EXIF melhora a escala em relação à lente estimada pelo modelo?
5. SAM 2 com um clique basta para guarda-roupa e porta, ou precisa de caixa?
6. Para o termograma (160 × 120), alguma dessas abordagens serve? (Hipótese: não, por resolução; medir.)

## Parte C: programação da otimização (computador do Hugo)

Sempre medir antes e depois, na RTX 3050 e na CPU, com a mesma foto.

1. **Perfil por etapa:** abrir a imagem, MoGe-2, codificador do SAM, decodificador do SAM e geometria, em ms.
2. **Resolução de entrada do MoGe-2** (o parâmetro de número de tokens): curva de tempo × erro no gabarito.
3. **Meia precisão (fp16) na placa de vídeo:** tempo, memória e erro.
4. **Codificador do SAM uma vez por foto**, guardado em cache; cliques seguintes só no decodificador (<50 ms).
5. **Pré-carregar os modelos em segundo plano** quando a aba Medir abrir, para o primeiro clique não esperar.
6. **ONNX + `onnxruntime-directml`:** exportar o SAM 2 (codificador e decodificador) e tentar o MoGe-2. É o
   caminho que o Controle Inteligente de Aplicativos deixa rodar sempre (o PyTorch com CUDA é barrado de vez em
   quando). Conferir que o erro não muda.
7. **INT8** (como `ml/otimizar.py` faz no RF-DETR) no decodificador do SAM e, se o erro aguentar, no MoGe-2.
8. **Memória:** caber nos 4 GB com o RF-DETR também carregado; descarregar o que não estiver em uso.

Meta de partida (rever com os números): menos de 3 s da foto aberta ao primeiro resultado na RTX 3050, e menos
de 0,1 s por clique seguinte.

## Parte D: integração com o Python do Pyron

```
nucleo/medicao/
    __init__.py         medir(imagem, pista, referencia=None) -> Medida  (a única função que o resto usa)
    geometria.py        fase 1: extensões, plano, distância, escala, incerteza (só NumPy)
    profundidade.py     fase 2: MoGe-2, carregado sob demanda; devolve pontos, válidos, lente
    segmentar.py        fase 2: SAM 2 pelo transformers; cache do codificador por foto
    modelos.py          onde ficam os pesos, o que está instalado, dispositivo (cuda, cpu, directml)
ml/avaliar_medicao.py   fase 3: relatório do gabarito
app/servidor.py         fase 4: /api/medicao e /api/medicao/estado
app/interface/js/captura/medir.js   fase 5: aba Medir foto
testes/test_medicao_*.py            sintéticos (sem pesos) + reais (pulam sem pesos)
```

`Medida` (dataclass): `altura_cm`, `largura_cm`, `comprimento_cm`, `incerteza_cm`, `metodo` ("sem referência",
"referência: folha A4"), `contorno` (polígono para desenhar), `tempos_ms`.

Dependências novas num grupo opcional do `pyproject.toml` (`[medicao]`): `moge` (GitHub da Microsoft). O
`transformers` e o `torch` já estão no ambiente.

## Parte E: melhores modelos e treino maior

**Para medir em foto comum, o MoGe-2 não precisa de treino** (foi treinado pela Microsoft em milhões de imagens).
Treinar só vale depois que o gabarito (fase 3) mostrar um erro que se repete. Em ordem de custo:

| Passo | O que é | Dados necessários | Onde roda | Quando fazer |
|---|---|---|---|---|
| 1. Calibração de escala por câmera | um fator único por celular, ajustado no gabarito | as fotos da seção 1 | qualquer lugar, segundos | se o erro sem referência for sempre para o mesmo lado (por exemplo, sempre 6 % a mais) |
| 2. Lente pelo EXIF | usar a focal gravada pelo celular no lugar da estimada | nenhum | qualquer lugar | se a pergunta 4 da parte B mostrar ganho |
| 3. Modelo maior | ViT-L no lugar do ViT-B; resolução de entrada maior | nenhum | placa de vídeo | se o tempo couber (parte C, item 2) |
| 4. Ajuste fino do MoGe-2 com profundidade real | treinar mais com fotos da casa e da subestação que tenham a profundidade medida | centenas de fotos com profundidade de verdade: celular com LiDAR (iPhone ou iPad Pro), câmera de profundidade (Kinect, RealSense) ou várias fotos reconstruídas no COLMAP com escala | GPU de 24 GB ou mais (Colab Pro ou nuvem); os 4 GB da RTX 3050 não bastam para o ViT-L | só se 1 a 3 não chegarem à meta |
| 5. Ajuste fino do detector por texto (OWLv2 ou Grounding DINO) | ensinar "para-raio", "bucha", "seccionadora" em foto visível | fotos visíveis rotuladas com caixas (CVAT) | Colab ou a RTX 3050 com lote pequeno | quando a medida for usada em equipamento de subestação fotografado com celular |

**Treino maior do detector térmico (RF-DETR)** (o que já existe para os para-raios):
- o treino de 30/09 parou sozinho em 18 min (paciência 20, de 100 épocas): **com os mesmos 111 fotos, mais horas
  não ajudam**; o ganho vem de mais fotos rotuladas (as 895 do ScienceDB estão sem rótulo; ver
  `docs/06_plano_medicao.md`, seção 5);
- com dados novos, uma noite de treino na RTX 3050 (cerca de 10 h):
  1. pré-rótulo automático das fotos novas com o RF-DETR atual e o SAM 2 (minutos), revisão no CVAT (horas de
     trabalho humano);
  2. validação cruzada em 5 partes do RF-DETR Medium (cerca de 2 h): acerto com margem;
  3. treino final com multiescala, resolução 800 e mais aumentos de dados (3 a 4 h);
  4. RF-DETR com máscara (segmentação), com as máscaras do SAM 2 revisadas (3 a 4 h);
- modelos maiores (RF-DETR Large) e lotes maiores pedem mais de 4 GB: Colab com A100 ou L4, que o
  `ml/pacote.py` já prepara;
- comando de partida: `ml/rfdetr_local.py` (a configuração do treino de 30/09 está em
  `modelos/para-raios-rfdetr-local-20260930-1627/relatorio.json`).

**Como saber se o modelo novo é melhor:** o mesmo conjunto de teste, separado antes de qualquer treino e nunca
usado para ajustar nada; para a medida, o gabarito da seção 1; para o detector, o AP50 por classe e o erro de
comprimento entre os terminais (as pontas da medida).

## 4. Riscos

- **Sem placa de vídeo na nuvem:** o MoGe-2 ViT-L na CPU leva segundos a dezenas de segundos por foto. Dá para
  avaliar, não para medir o tempo real; o tempo real se mede na fase 6.
- **Rede da nuvem:** se o Hugging Face ou o GitHub estiverem bloqueados, as fases 1 e 4 (com falsos) andam; as
  2 e 3 ficam para o computador.
- **Objetos finos ou brilhantes** (régua de metal, vidro): a profundidade estimada piora; o gabarito mostra o
  quanto.
- **Foto muito de lado:** a medida 3D ajuda, mas a parte escondida do objeto não aparece; registrar o ângulo.

## 5. Ao terminar tudo

Juntar o branch `medicao-geral` no `main` com merge (conferindo antes os commits do Gabriel), atualizar
`docs/Pyron_Funcionalidades.pdf` com a aba nova e o `CLAUDE.md` (seção 0) com a estrutura de `nucleo/medicao/`.

## 6. Registro

| Fase | Data | Feito e medido | Pendências |
|---|---|---|---|
| Gabarito | 26/10 | 6 fotos do Hugo em `testes/gabarito/` (vieram para a raiz do `main` pelo envio do GitHub; movidas no branch). `gabarito.csv` só com o que tem medida: A4, cartão, régua (30 cm de marcação), pessoa (183 cm), pote Fox (altura 3,5 cm), Kindle (17,4 × 12,5 cm, mas está de capa). `pistas.json` com ponto e caixa conferidos numa imagem. As fotos chegaram comprimidas (≈ 900 × 1600, sem EXIF): a pergunta 4 da parte B (lente do EXIF) não tem como ser respondida com elas | sandália e "parte da altura" sem medida (fora); Kindle medido por fora da capa; nenhuma foto com duas referências juntas |
| 1 | 26/10 | `nucleo/medicao/geometria.py` (extensões por PCA, plano por RANSAC com retângulo mínimo no plano, vertical pelo plano de apoio, distância entre dois pixels, correção de escala, incerteza) e `nucleo/medicao/sintetico.py` (cenas por traçado de raios). Pontas por percentil 2 % estendido até a borda, com cada ponto espalhado sobre o próprio pixel (sem isso o percentil anda em degraus e erra até 1 px). Sem ruído: porta 2,10 × 0,90 m a 3 m erro ≤ 0,03 %; girada 30° ≤ 0,05 %; régua 30 cm a 0,5 m 0,01 % (largura 3,5 cm: 0,11 %); armário 2,10 m em pé, altura pelo chão: 0,01 %. Ruído de 1 % na profundidade: erro ≤ 0,61 %, incerteza cobre todos. 19 testes em `testes/test_medicao_geometria.py` (14 s) | — |
| 2 | 26/10 | `nucleo/medicao/profundidade.py` (MoGe-2 sob demanda, lente do EXIF pela focal equivalente em 35 mm, `num_tokens` ajustável), `segmentar.py` (SAM 2.1 pelo `transformers` 5.20, codificador uma vez por foto em cache), `modelos.py` (pastas, estado, dispositivo, `--baixar`), `medir()` em `__init__.py` (decide plano ou volume, projeta os pontos no plano, altura pelo apoio, referência corrige a escala, cache da profundidade por foto). **Hugging Face bloqueado pela rede da nuvem** (`huggingface.co` recusado pelo proxy): sem pesos. O pacote `moge` hoje é a versão 3.0.0 (o MoGe-3 saiu em 18/08/2026); o MoGe-2 entra com `--no-deps`. Conferido com pesos aleatórios na arquitetura certa (config de treino do MoGe-2 ViT-L), CPU de 4 núcleos, sem placa de vídeo: MoGe-2 ViT-L ≈ 16 a 20 s por foto com 3600 tokens e ≈ 4,3 a 5 s com 1200; SAM (Hiera parecido com o small) codificador ≈ 1,2 a 1,4 s, cada clique ≈ 50 ms; geometria 1 a 5 s conforme o tamanho da máscara. 5 testes em `testes/test_medicao_modelos.py` (modelos pequenos aleatórios; o de ponta a ponta pula sem pesos) e 8 em `test_medicao_medir.py` (falsos) | rodar com os pesos: liberar `huggingface.co` na rede do ambiente ou rodar no computador do Hugo |
| 3 | 26/10 | `ml/avaliar_medicao.py`: mede cada foto pelo ponto e pela caixa, ViT-S/B/L, e compara três modos de escala: sem referência, com referência na foto e calibrado pela câmera (fator mediano ajustado nas outras fotos, deixando a medida de fora). Grava `saida/medicao/relatorio.json`, `relatorio.md` e o contorno sobre cada foto. Nas cenas sintéticas (`--sintetico`, erro de escala sorteado com desvio de 8 % e ruído de 1 % na profundidade): sem referência erro mediano 1,0 % (95 %: −4,3 a +5,1 %); com a régua na foto 0,5 %. Achado e corrigido aqui: com ruído, o plano de um objeto pequeno e longe pode sair quase paralelo aos raios; agora só se projeta no plano se ele não estiver de lado e a projeção não mudar o tamanho em mais de 25 % | rodar no gabarito real quando houver pesos |
| 4 | 26/10 | `POST /api/medicao` (foto + pista em JSON: ponto, caixa ou dois pontos; referência opcional com `tamanho_cm`, `medida` e `nome`) → medidas em cm, incerteza, método, forma, contorno, tamanho da imagem e tempos; `GET /api/medicao/estado` (pacotes, pesos, dispositivo, referências prontas: A4, cartão, régua, carta). Sem pacote ou pesos: 503 com o motivo; pista inválida: 422. 13 testes em `testes/test_medicao_api.py` com modelos falsos | conferir o endpoint em foto real com os pesos |
| 5 | 26/10 | Aba **Medir foto** em Captura (`app/interface/js/captura/medir.js`, textos em `textos.js` › `medir`, layout no fim de `telas.css`): barra de ferramentas (Abrir/Trocar foto · Clicar no objeto · Caixa em volta · Dois pontos · Limpar); foto no palco com o contorno do SAM em branco (seleção) e a referência tracejada; teclado: setas movem a mira, Enter marca, Esc cancela; ao lado, Medida (comprimento, largura, altura, espessura ou distância com ±, a forma e o método; sem referência, aviso em amarelo de que a margem é larga), Referência (A4, cartão, régua, carta ou outro tamanho; Marcar na foto) e Como foi medido (lente, modelos, tempo por etapa). Sem modelos: o motivo e o comando de instalação. A API devolve também `contorno_referencia`; plano sem apoio achado não ganha "altura" (cartão na mesa visto de cima). Conferido no Chromium a 1536 × 816 com um medidor falso no servidor (sem pesos): sem erro de JS; `conferir` com 0 falhas de contraste e 0 de alvo no claro, no escuro e no toque, antes e depois de medir; capturas em `docs/interface/capturas/medicao/`. `node --check` nos `.js` | conferir com os modelos de verdade (tempo real de espera na tela) |
| 5b | 26/10 | **Medir sem modelo** (pedido do Hugo: geometria só com as condições de contorno): `nucleo/medicao/plano_ref.py`, um retângulo de tamanho conhecido (A4, cartão, carta ou outro) clicado nos 4 cantos dá a homografia imagem → plano, e qualquer par de pontos no mesmo plano vira distância real; margem por Monte Carlo com 1 px de erro em cada clique. `POST /api/medicao/plano` (não precisa da foto nem dos pesos) e o modo "Retângulo de referência" na aba (sem os pesos, a aba abre nele e mostra o comando de instalação). Sintético: porta de 2,10 m medida pela A4 colada na mesma parede, de frente, girada 30° e 55°: erro < 0,2 %; com 1 px de erro nos cliques, a margem cobre o erro em ≥ 36 de 40 sorteios. Na tela, com a foto `a4_mesa.jpg`: lados da folha 29,7 e 21,0 cm (batem por construção, conferem só a ligação tela → API). Conferido no Chromium: sem erro de JS, `conferir` 0 falhas (claro, escuro, toque) nos dois modos. `CLAUDE.md` (seções 0 e 5) com a medição | foto de teste com a A4 ao lado de um objeto medido com trena no mesmo plano (porta, quadro) para medir o erro de verdade |
| 3 (real) | 26/10 | Hugging Face liberado: pesos baixados (MoGe-2 ViT-S, B, L; SAM 2.1 small e base-plus). **Gabarito real** (`docs/medicao/relatorio_gabarito.md`), sem referência, SAM small, CPU: **ViT-L erro mediano 19 %** (95 %: −6 a +167 %), ViT-B 28 %, ViT-S 47 %. Por foto (ViT-L): pessoa 183 cm → 166 (−9 %); A4 29,7 × 21 → 32,4 × 22,6 (+9 %, +8 %); Kindle de capa 17,4 × 12,5 → 20,1 × 14,9 (+15 %, +19 %; a capa explica parte); cartão 8,56 × 5,40 → 12,0 × 7,5 (+40 %); pote, altura 3,5 → 6,4 (+83 %); régua 30 → 86 (+188 %). O que separa os casos é o contexto da cena, não a distância: de perto sobre fundo liso o MoGe-2 acha a cena mais longe e erra muito para mais. Ponto e caixa deram o mesmo em todas as fotos (pergunta 5 da parte B: um clique basta; o contorno do SAM saiu certo nas 6). Calibração por câmera (deixa uma fora) piorou: ViT-L 22 % (o erro não é um fator constante). Lente: fixar 24 ou 26 mm equivalentes no lugar da estimada não mudou nada (18,5 a 19,8 %): a pergunta 4 fica respondida para estas fotos sem EXIF. Tempo na CPU, primeira medida da foto: ViT-S 11 s, ViT-B 13 s, ViT-L 17 s; cliques seguintes na mesma foto 0,5 a 1 s. Mudanças: padrão agora ViT-L; margem sem referência de 10 % (provisória) para 20 % (o erro mediano medido) e aviso na tela de que de perto sobre fundo liso erra bem mais | fotos com a referência ao lado do objeto (A4 + objeto medido com trena, a 1 e 2 m) para medir o modo com referência em foto real |
| 4 e 5 (real) | 26/10 | Servidor de verdade com os pesos: `POST /api/medicao` na foto da pessoa → 165,7 ± 33,5 cm (real 183, dentro da margem), 34 s na primeira chamada contando carregar os modelos (profundidade 18,5 s, contorno 4,7 s, geometria 0,9 s). Tela no Chromium: um clique na camisa contornou a pessoa inteira; resultado em 1,4 s com a profundidade da foto em cache; sem erro de JS e `conferir` com 0 falhas | — |
| Post-it | 26/10 | Pedido do Hugo: referência de post-it rosa (7,6 cm) e fotos por pasta. `nucleo/medicao/referencia_auto.py` acha o post-it sozinho pela cor (HSV), e cada lado é uma reta ajustada nos pontos onde a cor (a* do Lab) cruza a metade entre dentro e fora (anula o borrão do JPEG). Num post-it colado na perspectiva certa ao lado da A4 da foto do Hugo (cobertura exata, JPEG 92): cantos sem desvio de posição e lados +0,2 a +0,5 % (≈ 0,5 px em 128 px). `medir()` aceita `referencia={"auto": "postit_rosa"}` (corrige a escala da profundidade) e devolve também `no_plano_da_referencia` (homografia dos cantos, sem profundidade); referência retangular por `cantos` + `outro_lado_cm`. API: `POST /api/medicao/referencia` (acha os cantos) e o estado com `referencias_auto`. Tela: "post-it rosa (achar sozinho)" na Referência e "Achar o post-it" no modo sem modelo. `ml/avaliar_medicao.py --pasta`: uma subpasta por objeto, `medidas.csv` (`postit,lado,7.6` dá o tamanho do post-it), pista no centro da foto se não houver `pistas.json`, foto sem post-it entra só sem referência; coluna nova "plano da referência". Resultado na A4 com post-it colado (ViT-L): sem referência +14 a +18 %; **post-it + profundidade +0,1 a +4,6 %; post-it pelo plano −0,9 a +0,2 %** (caso favorável: post-it perfeitamente plano e no mesmo plano). Sintético: quadro de 60 cm a 1,2 m pelo post-it (≈ 69 px) 59,6 cm (pela profundidade); pelo plano do post-it sozinho a margem fica larga (±62 cm: referência 8× menor que o objeto); porta a 3 m com post-it de 25 px: só a profundidade serve. Tela com os modelos de verdade: A4 30,2 × 21,0 cm (± 0,6 e ± 0,5); achado e corrigido: medidas do modo sem modelo trocavam de ordem quando a resposta da segunda chegava antes. Gabarito: diâmetro do pote (7,7 cm) entrou; ViT-L 10,9 cm (+42 %) | as fotos do Hugo com post-it, por pasta |
| Fotos com post-it | 26/10 | 36 fotos do Galaxy S23 (HEIC 1848 × 4000 com EXIF e GPS; ficam fora do git), baixadas do Drive: A4, cartão, pote, Kindle, Hugo e só post-it; tipo pelo nome (ideal, difícil, normal). Novo: leitura de HEIC (`pillow-heif`, BSD-3, no extra `[medicao]`); lente do EXIF pelo quadro 4:3 do sensor (foto 19,5:9 cortada; pela diagonal da foto a focal saía 12 % menor); `ml/avaliar_medicao.py` com grupos por tipo de foto, `so_em` no `medidas.csv` (altura do pote só nas fotos de lado), `usar` no `pistas.json` e `--sem-exif`. Pistas: cartão, Kindle e pote pela cor; A4 (cor igual à do lençol) e Hugo marcados à mão; todos os 31 contornos conferidos (corrigidos: A4 com ponto no texto, pote sem o anel da tampa, Hugo só com a camisa). **Resultado (ViT-L, `docs/medicao/relatorio_postit.md`): post-it achado em 36/36 sem treino; erro mediano sem referência 29,6 %, com post-it + profundidade 8,1 % (normais 8,1 %, difíceis 7,8 %, ideais 13,7 %), só o plano do post-it 15,4 % (ideais 8,2 %, difíceis 122 %).** Hugo sem referência −2 a −4 % (sala com contexto); post-it na mão longe do corpo −66 a −79 %. O modelo sozinho mede o post-it com 14 a 20 cm em close-up (real 8). Lente do EXIF × estimada: igual (29,6 × 30,4 %; 8,1 × 8,2 %). Viés para mais no modo plano (+12,5 %) sugere post-it de 7,6 cm, não 8,0. Licenças conferidas nos cartões oficiais: MoGe-3 ViT-L/G MIT (precisa de FlexGEMM/Triton, só placa de vídeo); Depth Anything 3 Metric Large Apache 2.0 (os outros DA3 são CC BY-NC); SAM 3 licença própria e acesso sob aprovação. Instalar o DA3 foi barrado pela proteção da sessão (código externo fora da lista) | medir de novo o post-it; decidir sobre DA3 e MoGe-3 (este no computador com placa); mais fotos para treinar a correção de escala |
| DA3 | 26/10 | Hugo autorizou o Depth Anything 3 Metric Large (Apache 2.0): `pip install --no-deps --ignore-requires-python` do GitHub oficial + `einops omegaconf addict safetensors`; `ProfundidadeDA3` em `profundidade.py` usa só a rede (a API puxa open3d, pycolmap e o `evo`, GPL); metros = saída · focal / 300 com a focal na resolução processada (lado maior 504); lente do EXIF ou 65° padrão. **Fotos com post-it (31 fotos, 55 medidas): post-it + DA3 5,1 % (normais 5,1 %, difíceis 5,9 %, ideais 4,8 %) contra 8,1 % do MoGe-2; sem referência 19,8 % contra 29,6 %; 2 s por foto contra 20 s.** Pior só no pote (24 % contra 11 %) e no Hugo com post-it na mão. Sem EXIF: 5,9 % com post-it. Média dos dois modelos: 6,1 % (não compensa). Agora é o padrão (`modelos.profundidade_padrao()`), com o MoGe-2 de reserva; `--baixar da3`; `ml/avaliar_medicao.py --modelos da3` | MoGe-3 no computador com placa; correção de escala treinada com post-it (mais fotos) |
