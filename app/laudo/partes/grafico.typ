// Histórico do equipamento: a máxima de cada inspeção no tempo (pontos na cor da severidade), a linha que os
// liga e a reta de tendência tracejada. Só primitivas nativas do Typst (sem pacotes). As posições chegam do
// JSON já entre 0 e 1 nos dois eixos (app/laudo_typst.py, _historico).

#let grafico(g, c, altura: 52mm) = layout(tam => {
  let w = tam.width
  let h = altura
  let (me, md, mt, mb) = (30pt, 8pt, 8pt, 18pt)
  let px(x) = me + x * (w - me - md)
  let py(y) = h - mb - y * (h - mt - mb)
  let cinza = rgb(c.cinza)
  box(width: w, height: h, {
    for e in g.eixo_y {
      place(line(start: (me, py(e.y)), end: (w - md, py(e.y)), stroke: 0.4pt + rgb(c.linha)))
      place(dx: 0pt, dy: py(e.y) - 5pt, box(width: me - 4pt, height: 10pt, align(right + horizon, text(size: 6.5pt, fill: cinza, e.rotulo))))
    }
    for e in g.eixo_x {
      let (dx, lado) = if e.ancora == "inicio" { (px(e.x), left) } else if e.ancora == "fim" { (px(e.x) - 60pt, right) } else { (px(e.x) - 30pt, center) }
      place(dx: dx, dy: h - 11pt, box(width: 60pt, align(lado, text(size: 6.5pt, fill: cinza, e.rotulo))))
    }
    if g.tendencia != none {
      let t = g.tendencia
      place(line(start: (px(t.x0), py(t.y0)), end: (px(t.x1), py(t.y1)), stroke: (paint: cinza, thickness: 0.8pt, dash: "dashed")))
    }
    for i in range(g.pontos.len() - 1) {
      let a = g.pontos.at(i)
      let b = g.pontos.at(i + 1)
      place(line(start: (px(a.x), py(a.y)), end: (px(b.x), py(b.y)), stroke: 1.2pt + rgb(c.acento)))
    }
    for p in g.pontos {
      place(dx: px(p.x) - 2.6pt, dy: py(p.y) - 2.6pt, circle(radius: 2.6pt, fill: rgb(p.cor), stroke: 0.6pt + white))
    }
  })
})
