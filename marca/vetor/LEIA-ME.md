# Logo nova do Pyron (vetor)

Aprovada pelo Hugo em 25/10. Substitui a logo raster (`marca/pyron_logo.png`).

- **Símbolo**: mão segurando a chama com pixels soltos, vetorizado da imagem de referência
  (`referencia-simbolo.png`), sem redesenho: 97,8 % dos pixels iguais ao original no tamanho dele
  (`conferencia-original-vetor.png` mostra original, vetor e os dois sobrepostos).
- **Palavra PYRON**: fonte Chakra Petch Bold (Google Fonts, SIL Open Font License 1.1, que permite uso
  em logo), convertida em contornos; não precisa da fonte instalada.
- **Cores** (tiradas da própria imagem): mão e texto `#0A0A0A`; chama `#EF5F0C` (fora), `#FEC31F`
  (meio), `#A70F3C` (miolo). No fundo escuro, mão e texto `#E6EAF0`.

| Arquivo | Uso |
|---|---|
| `pyron-logo-cor.svg` | logo horizontal em fundo claro (padrão) |
| `pyron-logo-escuro.svg` | logo horizontal em fundo escuro (tema escuro, tela de abertura) |
| `pyron-logo-preto.svg`, `pyron-logo-branco.svg` | uma cor só (carimbo, impressão, marca-d'água) |
| `pyron-simbolo-*.svg` | só o símbolo, nas mesmas quatro versões |
| `pyron-palavra.svg` | só a palavra PYRON |
| `pyron-icone.svg` | ícone do aplicativo: símbolo claro sobre ladrilho escuro, 256 px |
| `prancha.png` | apresentação: versões, tamanhos reais, ícone e barra da interface |

`scripts/`: como foi feito. `vetorizar.py` traça a imagem (OpenCV); `final.py` monta as versões a
partir de `vetor.json` e `fontes.json` (contornos da Chakra Petch). Não fazem parte do aplicativo.

Pendente: na versão de uma cor, as três camadas da chama viram uma mancha só; para carimbo do laudo,
abrir filetes entre as camadas.
