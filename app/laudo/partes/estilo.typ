// Estilo do laudo: títulos, tabelas e pares rótulo/valor. As cores chegam do JSON (as mesmas do laudo em
// reportlab, app/laudo.py). Toda string do JSON entra como texto literal: nada aqui avalia texto como código.

#let titulo-secao(t, c) = block(above: 12pt, below: 5pt, sticky: true,
  text(size: 11pt, weight: "bold", fill: rgb(c.azul), t))

#let titulo-item(t, c) = block(above: 6pt, below: 4pt, sticky: true,
  text(size: 10pt, weight: "bold", fill: rgb(c.azul), t))

#let pequeno(t, c) = text(size: 7.5pt, fill: rgb(c.cinza), t)

// Célula: texto simples, ou (t: texto, sub: linha menor em cinza).
#let celula(v, c) = if type(v) == dictionary {
  stack(spacing: 3pt, text(size: 8pt, v.t), text(size: 6.5pt, fill: rgb(c.cinza), v.sub))
} else {
  text(size: 8pt, v)
}

// Tabela com cabeçalho escuro, linha fina entre as linhas e, se houver, a faixa da severidade à esquerda.
#let tabela(cabecalho, linhas, larguras, c, faixas: none) = table(
  columns: larguras,
  inset: (x: 4pt, y: 4pt),
  align: left + horizon,
  fill: (x, y) => if y == 0 { rgb(c.cabecalho) },
  stroke: (x, y) => {
    let s = (:)
    if y > 0 { s.insert("bottom", 0.3pt + rgb(c.linha)) }
    if x == 0 and y > 0 and faixas != none { s.insert("left", 3pt + rgb(faixas.at(y - 1))) }
    if s.len() == 0 { none } else { s }
  },
  table.header(..cabecalho.map(t => text(size: 8pt, weight: "bold", fill: white, t))),
  ..linhas.map(l => l.map(v => celula(v, c))).flatten(),
)

// Pares rótulo (cinza, pequeno) e valor, com a linha fina embaixo de cada par.
#let chave-valor(pares, c, rotulo: 46mm) = table(
  columns: (rotulo, 1fr),
  inset: (x: 4pt, y: 4pt),
  align: left + horizon,
  stroke: (x, y) => (top: none, left: none, right: none, bottom: 0.3pt + rgb(c.linha)),
  ..pares.map(((k, v)) => (text(size: 7.5pt, fill: rgb(c.cinza), k), text(size: 9pt, v))).flatten(),
)
