# Pyron 0.9 · F3 · Laudo em Typst

Data: 30/10/2026. Sem commit (pedido do usuário); mesmo branch `v09-f1-servidor`. Máquina: a da F0 (Acer Nitro
AN515-55, i5-10300H, Windows 11, SAC desligado). Fonte escolhida pelo usuário: Noto Sans.

> **Atualização de 30/10/2026:** visual aprovado pelo usuário; o padrão agora é `laudo.motor = "typst"`
> (`app/servidor.py`, `CONFIG_PADRAO`). Typst indisponível continua caindo no reportlab.

## Resumo em 3 linhas

1. Feito: `app/laudo_typst.py` com as mesmas assinaturas do laudo atual, modelo em `app/laudo/` (sem pacotes do
   Typst Universe), escolha por `laudo.motor` (padrão continua "reportlab"), Noto Sans vendorizada com licença.
2. Feito: dados só por JSON (teste com `#panic`, colchetes soltos, `$`, `@`, `<`, `\`, crases), as duas rotas nos
   dois motores, pasta temporária apagada; Typst de 2 a 3,5 vezes mais rápido, com o mesmo número de páginas.
3. Pendente: **sua aprovação do visual** (`docs/v09/laudo/`) para trocar o padrão; prova do SAC do `.pyd` numa
   máquina com ele ligado; tela para escolher o motor (hoje é pela API ou pelo `config.json`).

## Como funciona

| Peça | O quê |
|---|---|
| `app/laudo_typst.py` | `gerar()` e `gerar_relatorio()` com as assinaturas de `app/laudo.py`; `montar_dados()` prepara todos os textos e números (reusa as funções do laudo atual: número do relatório, normas, observações, formatação) e grava as imagens |
| `app/laudo/modelo.typ` e `app/laudo/partes/` | cabeçalho com empresa e logo, número, normas e critério, resumo, histórico (gráfico só com `line`, `circle` e `place`), registros, conclusão, referências, responsável técnico, rodapé "Página x de y" |
| `app/laudo/fontes/` | Noto Sans Regular, SemiBold, Bold e Italic; Noto Sans Math só para o "≥" (a Noto Sans não tem ≥, ≤, √ nem ≈); licenças OFL e `LEIA-ME.txt` com a origem |
| Configuração | `PUT /api/configuracoes {"laudo": {"motor": "typst"}}` (recusa se o Typst não carregar). Quem administra pode comparar num pedido só: `GET /api/analises/{id}/laudo.pdf?motor=typst` ou `"motor"` no corpo de `POST /api/laudos` |
| Se o Typst falhar ao carregar | pacote ausente ou DLL barrada pelo Windows: o laudo sai pelo reportlab |

**Segurança.** Cada laudo usa uma pasta temporária própria com o modelo, o `dados.json` e as imagens, apagada no
fim. O modelo lê os dados com `json("dados.json")`; uma string do JSON aparece como texto e nunca vira marcação.
Não há `eval` no modelo, e nenhum texto do usuário é colado no código. O teste põe `#panic("injetado")` e colchetes
soltos no equipamento, na instalação, nas observações, nos nomes das regiões, na empresa, no responsável e na ART: se
algum fosse interpretado, a compilação pararia.

**Fontes.** O compilador carrega só `app/laudo/fontes/`, sem as fontes do sistema nem as embutidas no Typst, para o
PDF sair igual no Windows e no Linux. Um compilador por processo (as fontes são lidas uma vez), uma compilação por vez.

**Diferença de conteúdo em relação ao reportlab (uma, de propósito):** o laudo em Typst traz no fim o "Código de
conferência dos dados avaliados (SHA-256)", calculado sobre inspeções, regiões, medidas, classificação e quem assina.
Quem tiver o banco refaz a conta (`laudo_typst.codigo_conferencia`) e confere que o laudo descreve aqueles dados. O
SHA-256 do PDF entregue continua registrado em `laudos_emitidos` (F1).

## Tempo dos dois motores

Método igual ao da F0: cópia de `saida/dados_demo` (10 inspeções), uma geração de aquecimento, depois 5 repetições
(3 para 50). O conjunto de 50 é o de 10 repetido cinco vezes. Responsável padrão, sem logo. Máquina da seção acima,
30/10/2026 14:26.

| Caso | reportlab (mediana) | Typst (mediana) | Páginas (reportlab / Typst) | PDF (reportlab / Typst) |
|---|---|---|---|---|
| Primeiro laudo do processo | 148 ms | 70 ms | 3 / 3 | |
| 1 inspeção | 111 ms | 32 ms | 3 / 3 | 322 KB / 260 KB |
| 10 inspeções | 693 ms | 219 ms | 13 / 13 | 1665 KB / 1460 KB |
| 50 inspeções (10 × 5) | 1944 ms | 1024 ms | 56 / 55 | 1754 KB / 2087 KB |

Com 50, o PDF do Typst é maior porque cada imagem repetida entra de novo; o reportlab reaproveita imagens iguais.
Com 50 inspeções diferentes, os dois carregam 50 imagens distintas. Isso não foi medido.

## Comparação das páginas

`docs/v09/laudo/` (reportlab à esquerda, Typst à direita; páginas do Edge, visualizador de PDF):

| Arquivo | O que mostra |
|---|---|
| `lado-1-p01.jpg` a `lado-1-p03.jpg` | laudo de 1 inspeção, as 3 páginas |
| `lado-10-p01.jpg`, `lado-10-p02.jpg` | laudo de 10 inspeções: identificação, critério e resumo |
| `lado-equip-p02.jpg` | histórico do equipamento (3 inspeções do BANCO-CAP-01, com a tendência) |
| `lado-equip-p06.jpg` | conclusão e responsável técnico, com o código de conferência |
| `exemplo-reportlab.pdf`, `exemplo-typst.pdf` | os dois PDFs de 1 inspeção, para abrir e comparar |

O conteúdo é o mesmo. O visual muda na fonte (Noto Sans no lugar da Arial), nos códigos das normas em negrito e no
espaçamento um pouco mais justo do Typst.

Ajustes feitos durante a comparação:
- **Símbolo ≥:** saía como caixa vazia; entrou a Noto Sans Math como reserva.
- **Tabela de identificação:** tinha bordas pretas; agora só tem as linhas finas.
- **Linhas de tabela:** uma linha do resumo se partia entre páginas; agora nenhuma se parte.
- **Termograma sem foto:** ficava à esquerda; agora fica centralizado, como no reportlab.
- **Subtítulo:** estava colado ao título; ganhou espaço.

## Conferido

| Bateria | Resultado |
|---|---|
| `pytest -q -m "not lento"` | 418 passaram, 4 pulados (eram 410 na F2) |
| `testes/test_laudo_typst.py` (8 novos) | assinaturas iguais; só as fontes do projeto; modelo sem `eval` e lendo o JSON; as duas rotas nos dois motores; padrão reportlab e queda para o reportlab com o Typst barrado; texto malicioso não executa; textos ficam literais no JSON; pasta temporária apagada e código de conferência muda com quem assina |

## Pendências

- **Aprovação do visual** para trocar o padrão para "typst" (`PUT /api/configuracoes {"laudo": {"motor": "typst"}}`).
- **SAC:** o `typst` traz um `.pyd` próprio (`_typst.pyd`). Aqui o SAC está desligado; a prova de que ele carrega com
  o SAC ligado fica para uma máquina com ele ligado (decisão de 30/10/2026). Se for barrado, o laudo segue no reportlab.
- **Tela:** a escolha do motor ainda não aparece em Configurações; pode entrar junto da troca do padrão.
