# Acabamento: ilustrações, animações e toques finais

Feito numa conversa na nuvem em 25/10, para a próxima conversa implementar. A parte 1 já está no
código (branch `interface-nova`); as partes 2 a 4 são a lista do que fazer, em ordem de prioridade.
Referência de nível: FLIR Thermal Studio (`2-direcao.md`, seção 6).

Capturas: `capturas/etapa3b/ilustracoes-antes-claro.png` (antes) e `ilustracoes-claro.png` /
`ilustracoes-escuro.png` (depois).

## 1. Já feito: ilustrações v2

**Motor (`js/ilustracoes.js`)**
- **Moldura comum 4:3**: toda cena cabe na mesma moldura, centrada na largura e assentada no chão.
  Antes cada uma tinha a escala do próprio conteúdo (a Captura saía pequena e as legendas desalinhavam).
- **Volume**: faces com gradiente suave (topo mais claro no fundo, laterais escurecendo no pé),
  filete de luz na aresta da frente do topo (`.brilho`) e sombra difusa no chão (gradiente radial,
  escura onde a peça toca). É o que dava o ar "colado" de antes.
- **Peças** (`c.peca(fn, classe)`): cada cena é dividida em até 6 grupos que entram em sequência.
  Classes: `chao` (sombra, só aparece), `peca` (desce 4 px ao lugar), `acento` (o dado térmico,
  acende por último).
- Novos utilitários: `disco()` (elipse deitada), `visto()` (sinal de conferido reto na tela),
  `termovisor()` e `folha()` (peças reutilizáveis).

**Tokens novos (`tokens.css`, claro e escuro)**: `--ilu-sombra-contato`, `--ilu-luz`,
`--ilu-oclusao`, `--ilu-brilho`.

**Movimento (`componentes.css`)**: `surgir` e `assentar` (entrada, uma vez, 400 ms, 60 ms entre
peças) e `varrer` (linhas de varredura no estado `procurando`). Só `transform` e `opacity`;
`prefers-reduced-motion` desliga tudo (regra global do `base.css`). Loop só em `procurando`.

**Cenas: as 6 corrigidas e 4 novas, e onde usar cada uma**

| Nome | Desenho | Onde entra |
|---|---|---|
| `captura` | termovisor apontado para isolador sobre base | Captura sem câmera; `procurando` enquanto busca a câmera |
| `inspecoes` | pasta aberta com termogramas | Inspeções vazia; também na camada de soltar arquivos |
| `pendencias` | prancheta com a lista conferida | Pendências zeradas (estado bom, não vazio) |
| `equipamentos` | transformador com radiador, buchas e placa | Equipamentos vazio |
| `sem-conexao` | notebook com o cabo solto | Sem conexão; `procurando` enquanto tenta reconectar |
| `modelos` | placa com o chip e componentes | Modelos sem detector instalado |
| `analise` (nova) | termograma de pé com a mira no ponto quente | Análise sem regiões; `procurando` = processando a imagem |
| `laudo` (nova) | folha com termograma e carimbo de conferido | Laudo gerado (com "Abrir PDF" e "Mostrar na pasta") |
| `busca` (nova) | lupa sobre folha | Busca (Ctrl+K) e filtros sem resultado |
| `celular` (nova) | celular de pé com o código ligado ao notebook | Captura › Celular: aguardando o celular (`procurando`) |

Correções nas antigas: radiador ligado ao tanque por coletores e trafo sobre trilhos; prendedor da
prancheta assentado; pasta lida como pasta (fundo alto com aba, frente baixa); termovisor maior e
isolador sobre base de concreto; placa com capacitores.

Conferido: testes da interface (10/10), `node --check`, os dois temas.

## 2. Toques finais: prioridade alta (Etapas 4 e 5)

**Etapa 4 (25/10):** feitos 1, 2, 3, 4, 6, 8, 9 e 10; o 5 (cortina) foi descartado porque a foto da FLIR C5
não é alinhada ao termograma, e o 7 fica para a tela Inspeções (5a). Detalhes em `4-analise.md`.

**Termograma (Análise), o coração do produto**
1. **Mira com leitura ao vivo** (como o medidor pontual da FLIR): cursor em cruz sobre o termograma,
   com a temperatura do pixel num rótulo que segue o mouse (fonte mono, `tabular-nums`).
   Alt fixa um ponto de leitura; Esc limpa.
2. **Escala de cores ligada ao cursor**: um marcador corre na barra da paleta mostrando onde a
   temperatura do pixel cai. Faixa mín–máx editável arrastando as pontas da barra.
3. **Ligação lista ↔ imagem**: passar o mouse numa região da lista realça a caixa no termograma, e
   o contrário. A selecionada ganha contorno mais grosso e alças; as outras ficam a 60 %.
4. **Zoom e arrasto**: roda do mouse com zoom no ponto do cursor, espaço + arrastar para mover,
   0 para encaixar. Indicador de zoom (100 %) na barra de ferramentas.
5. **Cortina visível × térmica**, quando houver as duas imagens: divisor arrastável.

**Estados e retorno**
6. **Botão ocupado**: ao salvar, analisar ou gerar laudo, o botão mostra o giro dentro dele, mantém
   a largura e fica indisponível. Nada de giro no meio da tela.
7. **Progresso de importação num lugar fixo** (barra determinada "12 de 40" no topo de Inspeções),
   no lugar do aviso que some. Ao terminar: aviso com "Abrir".
8. **Desfazer em vez de confirmar** para ações reversíveis (excluir região, arquivar inspeção):
   `avisar(texto, { acao: { rotulo: "Desfazer" } })` já existe. Diálogo só para o que não volta.
9. **"Salvo"** discreto no cabeçalho da Análise ("Salvo · há 2 min"), em vez de aviso a cada edição.
10. **Camada de soltar arquivos com a ilustração `inspecoes`** no lugar do ícone (`ligarSoltar()` na casca).

## 3. Toques finais: prioridade média

11. **Barra de status no rodapé** (24 px, texto 14 px): servidor ● conectado, câmera, detector
    carregado, versão. Clicar abre o item correspondente. Padrão de software técnico.
12. **Dica com atalho** nos botões da barra de ferramentas: "Importar · Ctrl+I", aparece em 600 ms.
13. **Menu de contexto** (botão direito) nas linhas das tabelas e nas regiões: Abrir, Renomear,
    Exportar, Excluir. Usa o `menu()` que já existe.
14. **Migalhas no cabeçalho do detalhe**: Inspeções › Subestação X › IR_0012.jpg.
15. **Números do Painel entrando uma vez**: contagem de 0 ao valor em 400 ms na primeira carga;
    nunca de novo ao atualizar (a mudança aparece só no número).
16. **Datas relativas** ("há 3 dias") com a data completa no `title`; temperaturas sempre com
    `font-variant-numeric: tabular-nums` e a unidade em `--texto-3`.
17. **Texto longo cortado com reticências** e o texto inteiro no `title` (nomes de arquivo, caminhos).

## 4. Toques finais: primeira impressão

18. **Tela de abertura** enquanto o servidor sobe: logo, nome, versão e uma barra fina de progresso,
    fundo branco (ou grafite no escuro). Some com `surgir` invertido quando `/api/status` responde.
19. **Primeira execução**: três passos lado a lado com as ilustrações `inspecoes` → `analise` →
    `laudo` ("Importe", "Analise", "Gere o laudo"), um botão primário "Importar termogramas" e
    "Usar dados de demonstração". Só aparece sem nenhuma inspeção.
20. **Sobre** (em Configurações): logo, versão, créditos, licença do dataset, sem texto longo.

## 5. Etapa 3c: estilo FLIR (pedido do Hugo em 25/10) · cancelada

**Cancelada em 25/10:** o Hugo esclareceu que a FLIR é só referência de sobriedade, e a medição mostrou
a cor de estrutura em menos de 1 % da tela (tabela em `docs/plano-interface.md`, Etapa 3c). A direção C
continua; o texto abaixo fica como registro do que foi proposto.

O Hugo mostrou telas do FLIR Thermal Studio e pediu o Pyron nesse estilo: fundo branco (ou preto no
tema escuro), enxuto, profissional, sem cor espalhada na estrutura. Isso vira a Etapa 3c, feita antes
da Etapa 4. Os detalhes o Claude decide pelos critérios do plano (não espera escolha do Hugo):
- ação, aba ativa e seleção em grafite ou preto (branco no tema escuro), sem cobalto; a cor fica
  para o termograma, a severidade e o acento das ilustrações;
- cinzas neutros no lugar da ardósia; corpo de texto em 15 px, tabelas em 14 px; raios de 2 a 4 px;
- título de página grande em peso leve; estados vazios direto no fundo, sem cartão em volta;
- estrutura padrão de tela: barra de ferramentas, área e painel de detalhes à direita com trilho
  de ícones (já existem no catálogo); Configurações como diálogo com categorias à esquerda.

## 6. Logo nova (aprovada pelo Hugo em 25/10)

**Aplicada na Etapa 3b (25/10):** itens 1, 2, 4 e 5 feitos; item 3 feito onde a logo vem dos arquivos
gerados (interface atual, celular, apresentação, tela de abertura, README; o laudo PDF não usa a marca do
Pyron). Pendente: recompilar o `Pyron.exe` para trocar o ícone embutido nele, e o filete entre as camadas
da chama na versão de uma cor (`marca/vetor/LEIA-ME.md`).

Os arquivos estão em `marca/vetor/` (ver o `LEIA-ME.md` de lá): símbolo vetorizado da imagem de
referência, palavra PYRON em Chakra Petch Bold convertida em contornos, versões em cor, escuro,
preto e branco, e o ícone do aplicativo. Nada foi trocado no aplicativo ainda. Falta:

1. **Gerar os arquivos que o aplicativo usa** a partir dos SVG: `app/estatico/marca/simbolo.png`,
   `logo.png`, `icone-64.png`, `icone-192.png` (fundo transparente) e o `pyron.ico` multi-tamanho.
   Reescrever `marca/gerar_marca.py` para partir de `marca/vetor/` em vez de recortar o PNG antigo
   (rasterizar com o Chromium da pré-visualização ou outra ferramenta que funcione com o Controle
   Inteligente de Aplicativos). Respeitar a regra do `Pyron.exe` no `CLAUDE.md` (≈100 KB).
2. **Interface nova** (`app/interface/index.html` e `catalogo.html`): na barra do topo, trocar o
   ícone de 32 px + texto "Pyron" pela logo horizontal em SVG (`pyron-logo-cor.svg` no claro,
   `pyron-logo-escuro.svg` no escuro), com altura de ~28 px; favicon novo.
3. **Interface atual, apresentação, laudo PDF e tela de abertura do lançador**: trocar onde aparece a
   logo antiga (procurar `pyron_logo`, `simbolo.png`, `logo.png`, `icone-`).
4. **`CLAUDE.md`**: a regra "a mão da logo é escura: o símbolo vai sempre sobre fundo claro" muda; agora
   há versão para fundo escuro (`*-escuro.svg`). Registrar as cores da marca e a fonte (Chakra Petch,
   OFL), e que a logo antiga sai. Atualizar também `docs/interface/2-direcao.md`, seção 6.4 (dizia que a
   logo original ficava).
5. Conferir em 16, 32 e 64 px, nos dois temas, e na barra do Windows.

## Pedido para colar na próxima conversa

```text
Leia docs/interface/acabamento.md. A parte 1 já está no branch interface-nova: confira o catálogo
(/nova/catalogo.html, claro e escuro) e use as ilustrações novas nos estados indicados na tabela.
Aplique a logo nova (parte 6). Depois implemente a parte 2 junto com a Etapa 4 (Análise) e as
partes 3 e 4 na Etapa 5. Faça a Etapa 3c (parte 5) antes da Etapa 4. Nada aqui espera escolha
do Hugo: o Claude decide, como manda o plano.
```
