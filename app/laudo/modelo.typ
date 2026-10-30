// Relatório de inspeção termográfica do Pyron (0.9, F3): o mesmo conteúdo do laudo em reportlab (app/laudo.py).
// Estrutura segundo a ABNT NBR 15572 e avaliação segundo a ABNT NBR 15866.
// Os dados vêm só de dados.json, montado por app/laudo_typst.py. Nenhum texto do usuário é escrito neste
// arquivo: uma string do JSON aparece como texto e nunca vira marcação nem código.

#import "partes/estilo.typ": titulo-secao, titulo-item, pequeno, tabela, chave-valor
#import "partes/grafico.typ": grafico
#import "partes/registro.typ": registro

#let d = json("dados.json")
#let c = d.cores

#set document(title: "Relatório de inspeção termográfica " + d.numero, author: d.autor)
#set text(font: ("Noto Sans", "Noto Sans Math"), size: 9pt, lang: "pt", region: "br", hyphenate: false)
#set par(leading: 0.62em, spacing: 0.85em)
#set table.cell(breakable: false) // uma linha de tabela nunca fica partida entre duas páginas
#set page(
  paper: "a4",
  margin: (left: 17mm, right: 17mm, top: 14mm, bottom: 18mm),
  footer: context {
    set text(size: 7pt, fill: rgb(c.cinza))
    line(length: 100%, stroke: 0.5pt + rgb(c.linha))
    v(-3pt)
    grid(columns: (1fr, auto), d.rodape, [Página #counter(page).get().first() de #counter(page).final().first()])
  },
)

// ---------------------------------------------------------------- cabeçalho
#{
  let marca = {
    text(size: 12pt, weight: "bold", fill: rgb(c.azul), if d.empresa.nome != "" { d.empresa.nome } else { "Inspeção termográfica" })
    if d.empresa.subtitulo != "" { linebreak(); text(size: 8pt, fill: rgb(c.cinza), d.empresa.subtitulo) }
  }
  let numero = align(right, text(size: 8pt, fill: rgb(c.cinza))[Relatório nº #text(weight: "bold", d.numero) \ Emissão: #d.emissao])
  let celulas = if d.logo != none { (image(d.logo.arquivo, width: d.logo.largura_mm * 1mm), marca, numero) } else { (marca, numero) }
  let colunas = if d.logo != none { (d.logo.largura_mm * 1mm + 4mm, 1fr, 66mm) } else { (1fr, 66mm) }
  block(width: 100%, stroke: (bottom: 1.2pt + rgb(c.acento)), inset: (bottom: 6pt), grid(columns: colunas, align: bottom, ..celulas))
}

#v(5mm)
#block(below: 7pt, text(size: 15pt, weight: "bold", fill: rgb(c.azul))[Relatório de inspeção termográfica])
#text(size: 9pt, fill: rgb(c.cinza), d.subtitulo)

// ---------------------------------------------------------------- 1. identificação
#titulo-secao("1. Identificação", c)
#chave-valor(d.identificacao, c)

// ---------------------------------------------------------------- 2. normas e critério
#titulo-secao("2. Normas e critério de avaliação", c)
#for (codigo, titulo) in d.normas { par[#text(weight: "bold", codigo) — #titulo] }
#v(2mm)
#par[Cada componente é avaliado pela temperatura máxima medida em sua área. Em partes que conduzem corrente, a temperatura é comparada com a máxima temperatura admissível (MTA) do componente, após projeção para plena carga: T#sub[proj] = T#sub[amb] + (T#sub[medida] − T#sub[amb]) × (100 / carga)#super[2]. Componentes iguais de fases diferentes são comparados entre si (#(d.delta)T para a mediana dos semelhantes). Em para-raios e isoladores, cujo aquecimento é dielétrico, vale o #(d.delta)T entre semelhantes, sem projeção de carga.]
#v(2mm)
#tabela(("Critério", "Classificação"), d.criterio, (62mm, 114mm), c)
#v(2mm)
#tabela(("Classificação", "Recomendação"), d.acoes.map(a => (a.rotulo, a.acao)), (40mm, 136mm), c, faixas: d.acoes.map(a => a.cor))

// ---------------------------------------------------------------- 3. resumo (várias imagens) e histórico
#if d.resumo != none {
  titulo-secao("3. Resumo dos resultados", c)
  tabela(("Item", "Equipamento / imagem", "Tmáx", "Local da Tmáx", "Classificação"),
    d.resumo.map(r => (r.item, (t: r.equipamento, sub: r.arquivo), r.tmax, r.onde, r.classe)),
    (14mm, 62mm, 22mm, 46mm, 32mm), c, faixas: d.resumo.map(r => r.cor))
  if d.historico != none {
    block(breakable: false, {
      v(3mm)
      titulo-item("Histórico do equipamento", c)
      par(text(d.historico.texto))
      grafico(d.historico, c)
    })
  }
}

// ---------------------------------------------------------------- 4. registros termográficos
#for r in d.registros {
  if d.registros.len() > 1 { pagebreak(weak: true) } // cada registro começa numa página
  registro(r, c)
}

// ---------------------------------------------------------------- conclusão
#titulo-secao(d.conclusao.secao, c)
#block(width: 100%, fill: rgb(c.fundo), stroke: (left: 4pt + rgb(d.conclusao.cor)), inset: (left: 8pt, rest: 6pt))[#text(weight: "bold", d.conclusao.rotulo + ".") #d.conclusao.texto]
#if d.conclusao.achados.len() > 0 {
  v(2mm)
  tabela(("Equipamento", "Ponto", "Classificação", "Recomendação"), d.conclusao.achados, (46mm, 40mm, 32mm, 58mm), c)
}
#if d.conclusao.nao_avaliadas != none {
  v(2mm)
  par(text("Não avaliados (sem a mesma peça de outra fase para comparar): " + d.conclusao.nao_avaliadas + "."))
}
#v(2mm)
#pequeno("A inspeção termográfica reflete as condições do instante da medição e não substitui outros ensaios.", c)

// ---------------------------------------------------------------- referências de temperatura
#if d.referencias != none {
  titulo-secao(d.referencias.secao, c)
  tabela(("Componente", "MTA", "Fonte"), d.referencias.linhas, (40mm, 46mm, 90mm), c)
}

// ---------------------------------------------------------------- responsável técnico
#v(4mm)
#block(breakable: false, {
  let a = d.assinatura
  titulo-secao(a.secao, c)
  grid(columns: (88mm, 88mm), row-gutter: 5pt,
    pequeno("Responsável técnico", c), pequeno("Registro profissional", c),
    { text(weight: "bold", a.nome); if a.funcao != "" { linebreak(); text(a.funcao) } }, text(a.registro),
    pequeno("ART nº", c), pequeno("Local e data", c),
    text(a.art), text("_________________________, ____/____/______"),
    { v(10mm); line(length: 75mm, stroke: 0.5pt); text("Assinatura") }, [],
  )
  v(3mm)
  pequeno("Código de conferência dos dados avaliados (SHA-256): " + d.conferencia, c)
})
