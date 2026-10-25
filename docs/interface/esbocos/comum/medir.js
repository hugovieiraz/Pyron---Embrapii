// Com "?medir" no endereço, grava no <body data-medidas> o que a Etapa 2 compara entre as direções.
addEventListener("load", () => {
  if (!location.search.includes("medir")) return;
  setTimeout(() => {
    const H = innerHeight, W = innerWidth;
    const visivel = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.top >= 0 && r.bottom <= H + 1 && r.left >= 0 && r.right <= W + 1; };
    const tela = document.querySelector(".tela.ativa");
    const img = document.querySelector("#img").getBoundingClientRect();
    const textos = [...tela.querySelectorAll("*")].filter((e) => [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) && visivel(e));
    const tamanhos = textos.map((e) => parseFloat(getComputedStyle(e).fontSize));
    const sel = (s) => [...tela.querySelectorAll(s)];
    const linhas = sel("tr.lin, .item, .grande");
    const regioes = sel(".reg, .chip");
    document.body.dataset.medidas = JSON.stringify({
      janela: [W, H],
      tela: tela.id,
      termograma: [Math.round(img.width), Math.round(img.height)],
      fracaoTermograma: +((img.width * img.height) / (W * H)).toFixed(3),
      linhasPainel: `${linhas.filter(visivel).length}/${linhas.length}`,
      regioes: `${regioes.filter(visivel).length}/${regioes.length}`,
      fonteMinima: Math.min(...tamanhos),
      fontePorTexto: tamanhos.length ? +(tamanhos.filter((t) => t <= 12).length / tamanhos.length).toFixed(2) : 0,
      controles: sel("button, a").filter(visivel).length + document.querySelectorAll("nav a").length,
    });
  }, 400);
});
