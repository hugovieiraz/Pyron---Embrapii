// Um registro termográfico: termograma e foto, condições de medição, tabela de pontos, medições,
// temperatura máxima, comparação entre semelhantes e observações. Dados de app/laudo_typst.py (registros[]).

#import "estilo.typ": titulo-secao, titulo-item, pequeno, tabela, chave-valor

#let registro(r, c) = {
  let titulos = {
    if r.secao != none { titulo-secao(r.secao, c) }
    titulo-item(r.titulo, c)
  }
  let imagens = if r.foto != none {
    grid(columns: (88mm, 88mm), image(r.termograma, width: 86mm), image(r.foto, width: 86mm))
  } else {
    align(center, image(r.termograma, width: 120mm)) // sem foto: centralizado, como no laudo em reportlab
  }
  block(width: 100%, breakable: false, { titulos; imagens })
  block(above: 3pt, below: 0pt, pequeno(r.legenda, c))
  v(2mm)
  chave-valor(r.dados, c)
  v(2mm)

  let linhas = if r.pontos.len() > 0 {
    r.pontos.map(p => (p.n, if p.em != "" { (t: p.nome, sub: p.em) } else { p.nome }, p.tmax, p.referencia, p.desvio, p.classe, p.acao))
  } else {
    (("–", "Nenhum ponto avaliado.", "", "", "", "", ""),)
  }
  let faixas = if r.pontos.len() > 0 { r.pontos.map(p => p.cor) } else { none }
  tabela(("Nº", "Ponto", "Tmáx", "Referência", "ΔT / % MTA", "Classificação", "Recomendação"), linhas,
    (9mm, 38mm, 17mm, 30mm, 19mm, 24mm, 39mm), c, faixas: faixas)

  if r.medicoes.len() > 0 {
    v(1.5mm)
    block(breakable: false, {
      pequeno("Pontos e linhas de medição", c)
      tabela(("Nome", "Tipo", "Máxima", "Mínima", "Média"), r.medicoes, (20mm, 50mm, 35mm, 35mm, 36mm), c)
    })
  }
  if r.tmax != none {
    v(2mm)
    par[#text(weight: "bold")[Temperatura máxima nos componentes:] #r.tmax]
  }
  if r.comparacao.len() > 0 {
    v(1.5mm)
    block(breakable: false, {
      pequeno("Comparação entre componentes semelhantes", c)
      tabela(("Componente", "Fase / peça", "Tmáx", "ΔT para a referência"), r.comparacao, (48mm, 58mm, 30mm, 40mm), c)
    })
  }
  if r.observacoes.len() > 0 {
    v(2mm)
    pequeno("Observações", c)
    for o in r.observacoes { block(above: 3pt, below: 0pt, pequeno("• " + o, c)) }
  }
}
