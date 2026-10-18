"use strict";

// Pyron · Apresentação: análise das fotos (peças e ponto mais quente), o modelo e a avaliação.

const T = {
  carregandoModelo: "Carregando o modelo…",
  motor: (m) => `Modelo pronto · ${m}`,
  erroModelo: (e) => `O modelo não carregou: ${e}`,
  semAcervo: "As fotos de teste não estão neste computador. Envie uma foto da câmera FLIR.",
  vazioTitulo: "Escolha uma foto",
  vazioTexto: "Clique numa foto de teste acima ou envie uma foto da câmera FLIR (o JPEG original, com os dados de temperatura).",
  analisando: "Analisando…",
  naoVista: "Foto de teste · não vista no treino",
  enviada: "Foto enviada",
  semTemperatura: "Esta foto não tem os dados de temperatura da câmera (print ou foto de tela): só a identificação das peças.",
  nenhumParaRaio: "Nenhum para-raio identificado nesta foto.",
  paraRaio: (n) => `Para-raio ${n}`,
  confianca: (p) => `confiança ${p}%`,
  pontoQuente: "ponto mais quente",
  onde: (parte) => (/^Saias/.test(parte) ? `nas ${parte}` : `no ${parte}`),
  maxPorParte: "Máxima em cada peça",
  pecas: "Peças",
  pontoMaisQuente: "Ponto mais quente",
  camera: (i) => [i.camera, i.sensor ? `sensor ${i.sensor}` : "", i.emissividade ? `emissividade ${String(i.emissividade).replace(".", ",")}` : ""].filter(Boolean).join(" · "),
  tempos: (ms, motor) => `Leitura ${ms.leitura} ms · identificação ${ms.deteccao} ms (${motor}) · ponto mais quente ${ms.temperatura} ms`,
  erroAnalise: "Não consegui analisar esta foto",
  soltar: "Solte a foto da câmera para analisar",
};

const $ = (s, raiz = document) => raiz.querySelector(s);
const el = (tag, props = {}, ...filhos) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null) continue;
    if (k === "class") n.className = v;
    else if (k === "style") Object.assign(n.style, v);
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const f of filhos.flat()) if (f != null && f !== false) n.append(f instanceof Node ? f : document.createTextNode(String(f)));
  return n;
};
const svg = (tag, props = {}, ...filhos) => {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(props)) if (v != null) n.setAttribute(k, v);
  for (const f of filhos.flat()) if (f != null) n.append(f instanceof Node ? f : document.createTextNode(String(f)));
  return n;
};
const fmt = (v, casas = 1) => (v == null ? "–" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }));
const pct = (v, casas = 1) => `${fmt(v * 100, casas)}%`;
const icone = (d) => svg("svg", { class: "ic", viewBox: "0 0 24 24", "aria-hidden": "true" }, svg("path", { d }));

// Cor de cada peça: a ordem das séries do Pyron (azul, âmbar, verde-azulado, violeta), validada para daltonismo.
const COR_PECA = { para_raio: "var(--serie-1)", aletas_isoladoras: "var(--serie-4)", terminal_superior: "var(--serie-2)", terminal_inferior: "var(--serie-3)" };
const COR_MODELO = ["var(--serie-1)", "var(--serie-4)", "var(--serie-2)", "var(--serie-3)"];

async function api(caminho, opcoes) {
  const r = await fetch(caminho, opcoes);
  const corpo = await r.json().catch(() => null);
  if (!r.ok) throw new Error((corpo && corpo.detail) || `erro ${r.status}`);
  return corpo;
}

// ------------------------------------------------------------------ abas

const ABAS = ["analise", "modelo", "avaliacao", "celular"];
const carregadas = new Set();
function mostrarAba(nome) {
  for (const a of ABAS) {
    $(`#tab-${a}`).setAttribute("aria-selected", String(a === nome));
    $(`#aba-${a}`).hidden = a !== nome;
  }
  if (nome === "modelo" && !carregadas.has(nome)) { carregadas.add(nome); desenharModelo(); }
  if (nome === "avaliacao" && !carregadas.has(nome)) { carregadas.add(nome); desenharAvaliacao(); }
  if (nome === "celular") carregarCelular();
  else pararCelular();
}
ABAS.forEach((a) => $(`#tab-${a}`).addEventListener("click", () => mostrarAba(a)));
document.addEventListener("keydown", (ev) => {
  if (ev.target.closest("input, textarea") || ev.ctrlKey || ev.altKey) return;
  const i = ["1", "2", "3", "4"].indexOf(ev.key);
  if (i >= 0) mostrarAba(ABAS[i]);
});

// ------------------------------------------------------------------ estado do modelo

let estadoModelo = null;
async function acompanharModelo() {
  for (let i = 0; i < 120; i++) {
    try {
      estadoModelo = await api("/api/estado");
      const m = $("#motor");
      if (estadoModelo.erro) { m.className = "motor erro"; m.lastElementChild.textContent = T.erroModelo(estadoModelo.erro); return; }
      if (estadoModelo.pronto) { m.className = "motor pronto"; m.lastElementChild.textContent = T.motor(estadoModelo.motor); return; }
    } catch { /* o servidor ainda está subindo */ }
    await new Promise((ok) => setTimeout(ok, 500));
  }
}

// ------------------------------------------------------------------ galeria

let selecionado = null;
async function montarGaleria() {
  const g = $("#galeria");
  g.replaceChildren(...Array.from({ length: 8 }, () => el("div", { class: "foto esqueleto", style: { height: "var(--apr-miniatura)" } })));
  try {
    const exemplos = (await api("/api/exemplos")).filter((e) => e.disponivel);
    if (!exemplos.length) { g.replaceChildren(); $("#galeria-nota").textContent = T.semAcervo; return; }
    $("#galeria-nota").textContent = `${exemplos.length} fotos que o modelo nunca viu no treino. Clique numa para analisar.`;
    g.replaceChildren(...exemplos.map((e) => el("button", { type: "button", class: "foto", "aria-pressed": "false", "data-nome": e.nome, onclick: (ev) => analisarExemplo(e.nome, ev.currentTarget) },
      el("img", { src: `/api/exemplos/${encodeURIComponent(e.nome)}/miniatura.jpg`, alt: e.nome, loading: "lazy" }),
      el("span", {}, e.nome.replace(/\.jpe?g$/i, "")))));
  } catch (e) {
    g.replaceChildren(el("p", { class: "nota" }, e.message));
  }
}

function marcar(botao) {
  document.querySelectorAll(".foto[aria-pressed='true']").forEach((b) => b.setAttribute("aria-pressed", "false"));
  if (botao) { botao.setAttribute("aria-pressed", "true"); botao.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" }); }
}

async function analisarExemplo(nome, botao) {
  marcar(botao);
  selecionado = nome;
  carregandoAnalise();
  try {
    const r = await api(`/api/exemplos/${encodeURIComponent(nome)}/analisar`, { method: "POST" });
    if (selecionado === nome) mostrarAnalise(r);
  } catch (e) {
    if (selecionado === nome) erroAnalise(e);
  }
}

async function analisarArquivos(arquivos) {
  for (const arquivo of arquivos) {
    const url = URL.createObjectURL(arquivo);
    const botao = el("button", { type: "button", class: "foto foto-enviada", "aria-pressed": "false" }, el("img", { src: url, alt: arquivo.name }), el("span", {}, arquivo.name));
    const g = $("#galeria");
    g.prepend(botao);
    let resultado = null;
    const abrir = async () => {
      marcar(botao);
      selecionado = botao;
      if (resultado) return mostrarAnalise(resultado);
      carregandoAnalise();
      try {
        const corpo = new FormData();
        corpo.append("arquivo", arquivo);
        resultado = await api("/api/analisar", { method: "POST", body: corpo });
        if (selecionado === botao) mostrarAnalise(resultado);
      } catch (e) {
        if (selecionado === botao) erroAnalise(e);
      }
    };
    botao.addEventListener("click", abrir);
    await abrir();
  }
}

$("#arquivo").addEventListener("change", (ev) => { analisarArquivos([...ev.target.files]); ev.target.value = ""; });
let arrastando = 0;
document.addEventListener("dragenter", (ev) => { if (ev.dataTransfer.types.includes("Files")) { arrastando++; $("#soltar").hidden = false; } });
document.addEventListener("dragleave", () => { if (--arrastando <= 0) { arrastando = 0; $("#soltar").hidden = true; } });
document.addEventListener("dragover", (ev) => ev.preventDefault());
document.addEventListener("drop", (ev) => {
  ev.preventDefault();
  arrastando = 0;
  $("#soltar").hidden = true;
  const fotos = [...ev.dataTransfer.files].filter((f) => /jpe?g$/i.test(f.name) || f.type === "image/jpeg");
  if (fotos.length) { mostrarAba("analise"); analisarArquivos(fotos); }
});

// ------------------------------------------------------------------ análise

function vazioAnalise() {
  $("#analise").replaceChildren(el("div", { class: "vazio" },
    icone("M4 7h3l2-3h6l2 3h3v12H4z M12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8"),
    el("h3", {}, T.vazioTitulo), el("p", {}, T.vazioTexto)));
}

function carregandoAnalise() {
  $("#analise").replaceChildren(el("div", { class: "analise", "aria-busy": "true" },
    el("div", { class: "esqueleto", style: { height: "var(--apr-visor-max)" } }),
    el("div", { class: "resultado" }, ...[1, 2, 3].map(() => el("div", { class: "esqueleto", style: { height: "var(--e-24)" } })))));
}

function erroAnalise(e) {
  $("#analise").replaceChildren(el("div", { class: "erro-caixa", role: "alert" }, el("b", {}, T.erroAnalise), el("p", {}, e.message)));
}

let atual = null;
const exibir = { pecas: true, quente: true };

function mostrarAnalise(r) {
  atual = r;
  const img = el("img", { src: r.imagem, alt: `Termograma ${r.arquivo}` });
  const camada = el("div", { class: "camada" });
  const leitura = el("div", { class: "leitura num", hidden: "" });
  const quadro = el("div", { class: "quadro" }, img, camada, leitura);
  const controle = (chave, texto) => el("label", {}, el("input", { type: "checkbox", checked: exibir[chave] ? "" : null,
    onchange: (ev) => { exibir[chave] = ev.target.checked; desenharCamada(); } }), texto);
  const legenda = el("div", { class: "legenda" }, ...Object.entries(COR_PECA).map(([classe, cor]) =>
    el("span", { class: "chave nota" }, el("i", { style: { background: cor } }), nomeDaClasse(classe))));
  const visor = el("div", { class: "visor" }, quadro, el("div", { class: "controles" }, controle("pecas", T.pecas), controle("quente", T.pontoMaisQuente), legenda));
  $("#analise").replaceChildren(el("div", { class: "analise" }, visor, painelResultado(r)));

  if (r.matriz) {
    quadro.addEventListener("mousemove", (ev) => {
      const caixa = img.getBoundingClientRect();
      const fx = (ev.clientX - caixa.left) / caixa.width;
      const fy = (ev.clientY - caixa.top) / caixa.height;
      if (fx < 0 || fy < 0 || fx >= 1 || fy >= 1) { leitura.hidden = true; return; }
      const m = r.matriz;
      const v = m.valores[Math.floor(fy * m.altura) * m.largura + Math.floor(fx * m.largura)];
      leitura.textContent = `${fmt(v)} °C`;
      leitura.style.left = `${ev.clientX - caixa.left}px`;
      leitura.style.top = `${ev.clientY - caixa.top}px`;
      leitura.hidden = false;
    });
    quadro.addEventListener("mouseleave", () => { leitura.hidden = true; });
  }
  img.decode().catch(() => {}).then(desenharCamada);
}

function nomeDaClasse(classe) {
  return { para_raio: "Para-raio", aletas_isoladoras: "Saias", terminal_superior: "Terminal Superior", terminal_inferior: "Terminal Inferior" }[classe] || classe;
}

/** Caixas, rótulos (sem cobrir uns aos outros, rotulos.js) e o ponto mais quente de cada para-raio. */
function desenharCamada() {
  const camada = $(".quadro .camada");
  if (!camada || !atual) return;
  const W = camada.clientWidth;
  const H = camada.clientHeight;
  const p = (v) => `${v * 100}%`;
  const filhos = [];
  if (exibir.pecas) {
    const rotulos = atual.pecas.map((d) => el("span", { class: "rotulo" }, el("i", { style: { background: COR_PECA[d.classe] } }), d.nome));
    filhos.push(...atual.pecas.map((d) => el("div", { class: `caixa ${d.classe}`, style: { left: p(d.caixa[0]), top: p(d.caixa[1]), width: p(d.caixa[2] - d.caixa[0]), height: p(d.caixa[3] - d.caixa[1]) } })), ...rotulos);
    camada.replaceChildren(...filhos);
    const chaves = chavesDasDeteccoes(atual.pecas);
    const itens = atual.pecas.map((d, i) => ({ chave: chaves[i], largura: rotulos[i].offsetWidth, altura: rotulos[i].offsetHeight,
      caixa: { x: d.caixa[0] * W, y: d.caixa[1] * H, w: (d.caixa[2] - d.caixa[0]) * W, h: (d.caixa[3] - d.caixa[1]) * H } }));
    const margem = 4;
    posicionarRotulos(itens, { x0: margem, y0: margem, x1: W - margem, y1: H - margem }, new Map(), margem)
      .forEach((pos, i) => { rotulos[i].style.transform = `translate(${Math.round(pos.x)}px, ${Math.round(pos.y)}px)`; });
  } else {
    camada.replaceChildren();
  }
  if (exibir.quente) {
    for (const pr of atual.para_raios.filter((x) => x.ponto)) {
      const mira = el("div", { class: "mira", style: { left: p(pr.ponto[0]), top: p(pr.ponto[1]) } });
      const texto = el("span", { class: "mira-rotulo num" }, `${fmt(pr.tmax)} °C`);
      camada.append(mira, texto);
      // à direita do marcador; à esquerda quando não cabe
      const x = pr.ponto[0] * W;
      const y = pr.ponto[1] * H;
      const largura = texto.offsetWidth;
      const esquerda = x + 16 + largura > W;
      texto.style.left = `${esquerda ? x - 16 - largura : x + 16}px`;
      texto.style.top = `${Math.max(0, y - texto.offsetHeight / 2)}px`;
    }
  }
}
window.addEventListener("resize", desenharCamada);

function painelResultado(r) {
  const cabeca = el("div", { class: "resultado-cabeca" },
    el("h3", {}, r.arquivo),
    el("span", { class: `selo${r.exemplo ? "" : " cinza"}` }, r.exemplo ? T.naoVista : T.enviada));
  const blocos = [cabeca];
  if (!r.radiometrica) blocos.push(el("p", { class: "aviso" }, T.semTemperatura));
  if (!r.para_raios.length) blocos.push(el("p", { class: "nota" }, T.nenhumParaRaio));
  for (const pr of r.para_raios) {
    const linhas = (pr.partes || []).slice().sort((a, b) => b.tmax - a.tmax).map((q, i) =>
      el("tr", { class: i === 0 && q.tmax === pr.tmax ? "maior" : null }, el("td", {}, q.nome), el("td", { class: "num" }, `${fmt(q.tmax)} °C`)));
    blocos.push(el("article", { class: "para-raio" },
      el("div", { class: "para-raio-cabeca" },
        el("span", { class: "chave" }, el("i", { style: { background: COR_PECA.para_raio, width: "var(--e-3)", height: "var(--e-3)", borderRadius: "50%" } }), el("b", {}, T.paraRaio(pr.numero))),
        el("span", { class: "nota" }, T.confianca(Math.round(pr.confianca * 100)))),
      pr.tmax != null
        ? el("div", { class: "quente" }, el("b", { class: "num" }, `${fmt(pr.tmax)} °C`), el("span", {}, `${T.pontoQuente} ${T.onde(pr.onde)}`))
        : null,
      linhas.length ? el("table", { class: "partes", "aria-label": T.maxPorParte }, el("tbody", {}, ...linhas)) : null));
  }
  const rodape = el("div", { class: "rodape" });
  if (r.info && (r.info.camera || r.info.sensor)) rodape.append(el("p", { class: "nota" }, T.camera(r.info)));
  rodape.append(el("p", { class: "nota num" }, T.tempos(r.ms, r.motor)));
  blocos.push(rodape);
  return el("aside", { class: "resultado" }, ...blocos);
}

// ------------------------------------------------------------------ dica (tooltip) dos gráficos

function dica(ev, html) {
  const d = $("#dica");
  d.innerHTML = html;
  d.hidden = false;
  const x = Math.min(window.innerWidth - d.offsetWidth - 8, ev.clientX + 14);
  d.style.left = `${x}px`;
  d.style.top = `${ev.clientY + 14}px`;
}
const semDica = () => { $("#dica").hidden = true; };

/** Gráfico de linha de uma série: eixo y de 0 (ou do mínimo) ao máximo, mira e dica ao passar o mouse. */
function graficoLinha({ titulo, nota, xs, ys, formato, casasValor = 2, destaque, yMin = 0 }) {
  const L = 560, A = 220, m = { e: 44, d: 16, c: 12, b: 28 };
  // eixo em números redondos: passo de 1, 2, 2,5 ou 5 (× potência de 10), até 5 intervalos
  const bruto = (Math.max(...ys) - yMin) / 5;
  const potencia = 10 ** Math.floor(Math.log10(bruto));
  const passo = [1, 2, 2.5, 5, 10].map((k) => k * potencia).find((p) => p >= bruto);
  const y0 = Math.floor(yMin / passo) * passo;
  const yMax = Math.ceil(Math.max(...ys) / passo) * passo;
  const escalaX = (x) => m.e + ((x - xs[0]) / (xs[xs.length - 1] - xs[0])) * (L - m.e - m.d);
  const escalaY = (y) => A - m.b - ((y - y0) / (yMax - y0)) * (A - m.b - m.c);
  const grade = Array.from({ length: Math.round((yMax - y0) / passo) + 1 }, (_, i) => y0 + i * passo);
  const caminho = xs.map((x, i) => `${i ? "L" : "M"}${escalaX(x).toFixed(1)},${escalaY(ys[i]).toFixed(1)}`).join(" ");
  const mira = svg("line", { class: "mira-grafico", y1: m.c, y2: A - m.b, visibility: "hidden" });
  const ponto = svg("circle", { class: "ponto", r: 5, fill: "var(--serie-1)", visibility: "hidden" });
  const fig = svg("svg", { viewBox: `0 0 ${L} ${A}`, role: "img", "aria-label": titulo },
    ...grade.map((g) => svg("line", { class: "grade", x1: m.e, x2: L - m.d, y1: escalaY(g), y2: escalaY(g) })),
    ...grade.map((g) => svg("text", { class: "eixo", x: m.e - 8, y: escalaY(g) + 4, "text-anchor": "end" }, formato(g))),
    ...[xs[0], xs[Math.floor(xs.length / 2)], xs[xs.length - 1]].map((x) => svg("text", { class: "eixo", x: escalaX(x), y: A - 8, "text-anchor": "middle" }, `época ${x}`)),
    svg("path", { class: "linha", d: caminho, stroke: "var(--serie-1)" }),
    destaque ? svg("circle", { class: "ponto", r: 5, fill: "var(--serie-1)", cx: escalaX(destaque.x), cy: escalaY(destaque.y) }) : null,
    destaque ? svg("text", { class: "valor", x: escalaX(destaque.x), y: escalaY(destaque.y) - 12, "text-anchor": "middle" }, destaque.texto) : null,
    mira, ponto);
  const alvo = svg("rect", { class: "alvo", x: m.e, y: m.c, width: L - m.e - m.d, height: A - m.b - m.c });
  alvo.addEventListener("mousemove", (ev) => {
    const caixa = fig.getBoundingClientRect();
    const xv = ((ev.clientX - caixa.left) / caixa.width) * L;
    let i = 0;
    xs.forEach((x, k) => { if (Math.abs(escalaX(x) - xv) < Math.abs(escalaX(xs[i]) - xv)) i = k; });
    mira.setAttribute("x1", escalaX(xs[i])); mira.setAttribute("x2", escalaX(xs[i])); mira.setAttribute("visibility", "visible");
    ponto.setAttribute("cx", escalaX(xs[i])); ponto.setAttribute("cy", escalaY(ys[i])); ponto.setAttribute("visibility", "visible");
    dica(ev, `Época <b>${xs[i]}</b><br>${titulo}: <b>${fmt(ys[i], casasValor)}</b>`);
  });
  alvo.addEventListener("mouseleave", () => { mira.setAttribute("visibility", "hidden"); ponto.setAttribute("visibility", "hidden"); semDica(); });
  fig.append(alvo);
  return el("figure", { class: "grafico", style: { margin: 0 } }, el("figcaption", {}, el("b", {}, titulo), nota ? el("p", { class: "nota" }, nota) : null), fig);
}

/** Colunas agrupadas: uma cor por série (legenda sempre visível), valor na dica, de 0 a 1. */
function graficoColunas({ titulo, nota, grupos, series, valor }) {
  const L = 560, A = 230, m = { e: 40, d: 8, c: 12, b: 34 };
  const larguraGrupo = (L - m.e - m.d) / grupos.length;
  const barra = Math.min(24, (larguraGrupo - 24) / series.length - 2);
  const escalaY = (v) => A - m.b - v * (A - m.b - m.c);
  const filhos = [];
  [0, 0.25, 0.5, 0.75, 1].forEach((g) => {
    filhos.push(svg("line", { class: "grade", x1: m.e, x2: L - m.d, y1: escalaY(g), y2: escalaY(g) }));
    filhos.push(svg("text", { class: "eixo", x: m.e - 8, y: escalaY(g) + 4, "text-anchor": "end" }, fmt(g, 2)));
  });
  grupos.forEach((grupo, gi) => {
    const inicio = m.e + gi * larguraGrupo + (larguraGrupo - series.length * (barra + 2)) / 2;
    filhos.push(svg("text", { class: "eixo", x: m.e + (gi + 0.5) * larguraGrupo, y: A - 12, "text-anchor": "middle" }, grupo));
    series.forEach((s, si) => {
      const v = valor(s, grupo);
      const x = inicio + si * (barra + 2);
      const y = escalaY(v);
      const altura = escalaY(0) - y;
      const raio = Math.min(4, altura);
      // ponta arredondada (4 px), base reta
      const d = `M${x},${escalaY(0)} V${y + raio} Q${x},${y} ${x + raio},${y} H${x + barra - raio} Q${x + barra},${y} ${x + barra},${y + raio} V${escalaY(0)} Z`;
      const forma = svg("path", { d, fill: s.cor });
      const alvo = svg("rect", { class: "alvo", x: x - 1, y: m.c, width: barra + 2, height: A - m.b - m.c });
      alvo.addEventListener("mousemove", (ev) => dica(ev, `<b>${s.nome}</b><br>${grupo}: <b>${fmt(v, 3)}</b>`));
      alvo.addEventListener("mouseleave", semDica);
      filhos.push(forma, alvo);
    });
  });
  const fig = svg("svg", { viewBox: `0 0 ${L} ${A}`, role: "img", "aria-label": titulo }, ...filhos);
  const legenda = el("div", { class: "legenda" }, ...series.map((s) => el("span", { class: "chave nota" }, el("i", { style: { background: s.cor, borderRadius: "var(--r-p)" } }), s.nome)));
  return el("figure", { class: "grafico", style: { margin: 0 } }, el("figcaption", {}, el("b", {}, titulo), nota ? el("p", { class: "nota" }, nota) : null), legenda, fig);
}

// ------------------------------------------------------------------ aba Modelo

let avaliacao = null;
async function dadosAvaliacao() {
  if (!avaliacao) avaliacao = await api("/api/avaliacao");
  return avaliacao;
}

async function desenharModelo() {
  const aba = $("#aba-modelo");
  aba.replaceChildren(el("div", { class: "cartao esqueleto", style: { height: "var(--apr-visor-max)" } }));
  try {
    const [est, av] = [estadoModelo || (await api("/api/estado")), await dadosAvaliacao()];
    const tl = av.treino_local;
    const h = tl.historico;
    const etapa = (n, titulo, texto) => el("div", { class: "etapa" }, el("span", { class: "passo" }, n), el("b", {}, titulo), el("p", {}, texto));
    const fato = (rotulo, valor) => el("div", { class: "fato" }, el("span", {}, rotulo), el("b", {}, valor));
    const melhor = h.map50_validacao.indexOf(Math.max(...h.map50_validacao));
    aba.replaceChildren(
      el("div", { class: "cartao" },
        el("h2", {}, "Como funciona"),
        el("div", { class: "etapas" },
          etapa(1, "Foto da câmera", "O JPEG da FLIR traz a imagem colorida e, gravada junto, a temperatura de cada ponto do sensor (160 × 120 na FLIR C5)."),
          etapa(2, "Identificação", `O RF-DETR olha a imagem colorida (reduzida para ${est.modelo.entrada.join(" × ")}) e marca o para-raio, as saias e os terminais.`),
          etapa(3, "Temperatura", "Cada caixa é levada para a matriz de temperatura do sensor, no mesmo lugar da imagem."),
          etapa(4, "Ponto mais quente", "Dentro da caixa de cada para-raio, o ponto de maior temperatura e a peça onde ele está."))),
      el("div", { class: "cartao" },
        el("h2", {}, est.modelo.nome),
        el("p", {}, "Detector de objetos do tipo transformer (DETR) com base DINOv2, licença Apache 2.0: recebe a imagem inteira e devolve, de uma vez, as caixas e o tipo de cada peça, sem etapas de proposta de regiões."),
        el("div", { class: "fatos" },
          fato("Peças que reconhece", est.modelo.classes.join(", ")),
          fato("Entrada", `imagem colorida ${est.modelo.entrada.join(" × ")} pixels`),
          fato("Confiança mínima", pct(est.modelo.limiar, 0)),
          fato("Onde roda agora", est.pronto ? est.motor : T.carregandoModelo),
          fato("Tempo por foto", `${fmt(tl.ms_por_foto_cpu, 0)} ms no processador · ~70 ms na placa de vídeo`),
          fato("Formato", "ONNX (o mesmo arquivo no processador ou na placa)"))),
      el("div", { class: "cartao" },
        el("h2", {}, "Treino"),
        el("div", { class: "destaques" },
          el("div", { class: "destaque" }, el("b", { class: "num" }, av.fotos.treino + av.fotos.validacao + av.fotos.teste), el("span", {}, `fotos rotuladas no CVAT: ${av.fotos.treino} treino, ${av.fotos.validacao} validação, ${av.fotos.teste} teste`)),
          el("div", { class: "destaque" }, el("b", { class: "num" }, tl.dados.caixas.toLocaleString("pt-BR")), el("span", {}, "peças marcadas à mão (caixas)")),
          el("div", { class: "destaque" }, el("b", { class: "num" }, `${fmt(tl.duracao_min, 0)} min`), el("span", {}, "de treino na RTX 3050 deste notebook")),
          el("div", { class: "destaque" }, el("b", { class: "num" }, `época ${melhor + 1}`), el("span", {}, `a melhor de ${h.epocas_map.length} (o treino para depois de ${tl.configuracao.paciencia} épocas sem melhorar)`))),
        el("div", { class: "graficos" },
          graficoLinha({ titulo: "Erro no treino (perda)", nota: "Cai à medida que o modelo aprende.", xs: h.epocas_perda, ys: h.perda_treino, formato: (v) => fmt(v, 0) }),
          graficoLinha({ titulo: "Acerto na validação (mAP50)", nota: "Medido a cada época em fotos fora do treino.", xs: h.epocas_map, ys: h.map50_validacao, formato: (v) => fmt(v, 1), casasValor: 3, yMin: 0.6,
            destaque: { x: h.epocas_map[melhor], y: h.map50_validacao[melhor], texto: fmt(h.map50_validacao[melhor], 3) } }))),
      el("div", { class: "cartao" },
        el("h2", {}, "Limitações"),
        el("ul", { class: "lista" }, ...est.modelo.limitacoes.map((t) => el("li", {}, t)))));
  } catch (e) {
    aba.replaceChildren(el("div", { class: "erro-caixa", role: "alert" }, e.message));
  }
}

// ------------------------------------------------------------------ aba Avaliação

async function desenharAvaliacao() {
  const aba = $("#aba-avaliacao");
  aba.replaceChildren(el("div", { class: "cartao esqueleto", style: { height: "var(--apr-visor-max)" } }));
  try {
    const av = await dadosAvaliacao();
    const local = av.treino_local.teste;
    const totalPecas = local.acertos + local.perdidos;
    const modelos = [...av.comparacao.modelos.map((m, i) => ({ ...m, cor: COR_MODELO[i] }))];
    const linhaLocal = { nome: "RF-DETR Medium · treino neste notebook (o usado aqui)", ...local, ms_por_foto: av.treino_local.ms_por_foto_cpu, usado: true };
    const colunas = [["mAP50", "mAP50", 3], ["mAP50-95", "mAP50-95", 3], ["Precisão", "precisao", 3], ["Revocação", "revocacao", 3], ["F1", "F1", 3],
      ["Acertos", "acertos", 0], ["Falsos", "falsos", 0], ["Perdidos", "perdidos", 0]];
    const melhorDe = (chave) => (["falsos", "perdidos"].includes(chave) ? Math.min : Math.max)(...modelos.map((m) => m[chave]));
    const tabela = el("table", { class: "tabela" },
      el("thead", {}, el("tr", {}, el("th", {}, "Modelo"), ...colunas.map(([t]) => el("th", {}, t)), el("th", {}, "ms por foto"))),
      el("tbody", {},
        ...modelos.map((m) => el("tr", {}, el("td", {}, el("span", { class: "chave" }, el("i", { style: { background: m.cor } }), m.nome)),
          ...colunas.map(([, k, c]) => el("td", { class: `num${m[k] === melhorDe(k) ? " melhor" : ""}` }, fmt(m[k], c))),
          el("td", { class: "num" }, `${fmt(m.ms_por_foto, 0)} (T4)`))),
        el("tr", { class: "usado" }, el("td", {}, linhaLocal.nome), ...colunas.map(([, k, c]) => el("td", { class: "num" }, fmt(linhaLocal[k], c))),
          el("td", { class: "num" }, `${fmt(linhaLocal.ms_por_foto, 0)} (CPU)`))));
    const classes = av.classes;
    const grafico = graficoColunas({
      titulo: "Acerto por peça (AP50), nas 27 fotos de teste",
      nota: "O para-raio e as saias quase sempre; o terminal inferior, pequeno e às vezes escondido pela estrutura, é o ponto fraco dos três.",
      grupos: classes, series: modelos, valor: (s, classe) => s.por_classe[classe].AP50 });
    const tabelaClasses = el("table", { class: "tabela" },
      el("thead", {}, el("tr", {}, el("th", {}, "Peça"), ...modelos.map((m) => el("th", {}, m.nome)), el("th", {}, "RF-DETR (este notebook)"))),
      el("tbody", {}, ...classes.map((c) => el("tr", {}, el("td", {}, c),
        ...modelos.map((m) => el("td", { class: "num" }, fmt(m.por_classe[c].AP50, 3))),
        el("td", { class: "num" }, fmt(local.por_classe[c].AP50, 3))))));
    const figura = (grupo, arquivo, legenda) => el("button", { type: "button", class: "figura", onclick: () => ampliar(`/api/figuras/${grupo}/${arquivo}`, legenda) },
      el("img", { src: `/api/figuras/${grupo}/${arquivo}`, alt: legenda, loading: "lazy" }), el("span", {}, legenda));
    const nomesFiguras = { "metricas.png": "Métricas dos três detectores", "curvas.png": "Curvas de treino (Colab)", "pecas_perdidas.png": "Peças perdidas por tipo e tamanho",
      "piores_fotos.png": "As fotos com mais erros" };
    const figurasComparacao = av.figuras.comparacao.map((f) => figura("comparacao", f, nomesFiguras[f] || `Teste, fotos ${f.match(/\d+_a_\d+/)?.[0].replace("_a_", " a ") || ""} (3 detectores)`));
    const figurasLocal = av.figuras.treino_local.map((f) => figura("treino_local", f, `Teste, fotos ${f.match(/\d+_a_\d+/)?.[0].replace("_a_", " a ") || ""} (RF-DETR deste notebook)`));

    aba.replaceChildren(
      el("div", { class: "cartao" },
        el("h2", {}, "O modelo usado aqui, nas 27 fotos de teste"),
        el("p", { class: "nota" }, `Fotos que ficaram fora do treino, com ${totalPecas} peças rotuladas à mão para conferir.`),
        el("div", { class: "destaques" },
          el("div", { class: "destaque" }, el("b", { class: "num" }, `${local.acertos} de ${totalPecas}`), el("span", {}, "peças achadas")),
          el("div", { class: "destaque" }, el("b", { class: "num" }, pct(local.precisao)), el("span", {}, "precisão: das caixas marcadas, quantas estavam certas")),
          el("div", { class: "destaque" }, el("b", { class: "num" }, pct(local.revocacao)), el("span", {}, "revocação: das peças que existiam, quantas ele achou")),
          el("div", { class: "destaque" }, el("b", { class: "num" }, fmt(local.mAP50, 3)), el("span", {}, "mAP50: acerto médio, caixa certa quando cobre ao menos metade da peça")),
          el("div", { class: "destaque" }, el("b", { class: "num" }, `${fmt(local.erro_Tmax_mediano_C, 1)} °C`), el("span", {}, `erro da temperatura máxima por peça (mediana; 90% até ${fmt(local.erro_Tmax_p90_C, 2)} °C), contra as caixas rotuladas`)))),
      el("div", { class: "cartao" },
        el("h2", {}, "Comparação de detectores"),
        el("p", { class: "nota" }, `Os três treinados com as mesmas fotos e a mesma divisão, no ${av.comparacao.onde}. Diferença de mAP50 abaixo de 0,02: empate técnico. Em negrito, o melhor de cada coluna.`),
        el("div", { class: "rolar" }, tabela),
        el("div", { class: "graficos" }, grafico),
        el("div", { class: "rolar" }, tabelaClasses)),
      el("div", { class: "cartao" },
        el("h2", {}, "Figuras do teste"),
        el("p", { class: "nota" }, "Verde: peça achada; vermelho: peça perdida; amarelo: caixa a mais. Clique para ampliar."),
        el("div", { class: "figuras" }, ...figurasLocal, ...figurasComparacao)),
      el("p", { class: "nota" }, "Fotos: Infrared Power Equipment Dataset (ScienceDB 10185, doi 10.57760/sciencedb.10185), licença CC BY-NC-SA 4.0, uso não comercial."));
  } catch (e) {
    aba.replaceChildren(el("div", { class: "erro-caixa", role: "alert" }, e.message));
  }
}

function ampliar(src, legenda) {
  const d = $("#lupa");
  $("img", d).src = src;
  $("img", d).alt = legenda;
  $("p", d).textContent = legenda;
  d.showModal();
}
$("#lupa-fechar").addEventListener("click", () => $("#lupa").close());
$("#lupa").addEventListener("click", (ev) => { if (ev.target === ev.currentTarget) ev.currentTarget.close(); });

// ------------------------------------------------------------------ aba Câmera do celular
// O celular abre uma página do Pyron pelo QR code, transmite a câmera e recebe as caixas; aqui aparece o
// vídeo dele (WebSocket: mensagem binária = quadro com o cabeçalho do celular; texto = resultado).

const C = {
  passos: [
    "Deixe o celular e o computador no mesmo Wi-Fi.",
    "Ligue a conexão aqui e leia o QR code com a câmera do celular.",
    "O celular avisa que a conexão não é particular (o certificado é do próprio Pyron): toque em Avançado › Continuar.",
    "Permita a câmera e aponte para uma imagem térmica, na tela do computador por exemplo, com a barra de cores no quadro.",
  ],
  ligar: "Ligar conexão com o celular",
  desligar: "Desligar",
  copiar: "Copiar",
  abra: "Abra no celular",
  avisoCertificado: "No aviso de conexão não particular, toque em Avançado › Continuar.",
  conectado: "Celular conectado",
  esperando: "Esperando o celular abrir a página",
  desconectado: (s) => `Sem quadros há ${s} s: o celular saiu da página ou perdeu o Wi-Fi`,
  espelho: "O que o celular está vendo",
  esperandoTitulo: "Esperando o celular",
  esperandoTexto: "Abra o link no celular e ligue a câmera. O vídeo aparece aqui.",
  ritmo: (q, a, ms) => [q != null ? `vídeo ${fmt(q, 0)} quadros/s` : "", a != null ? `${fmt(a, 1)} análises/s` : "", ms != null ? `detector ${ms} ms` : ""].filter(Boolean).join(" · "),
  nenhuma: "Nenhuma peça confirmada no último quadro.",
  semTermograma: "Nenhuma imagem térmica no quadro.",
  escalaLida: (min, max) => `Barra de cores lida: ${min} a ${max} °C. Temperaturas estimadas pelas cores.`,
  escalaLendo: "Barra de cores achada: lendo os números da escala…",
  nota: "A foto do celular não traz os dados do sensor: a temperatura é estimada pelas cores da barra (erro típico de 0,5 °C), não medida.",
  rede: "O Windows pode perguntar se o Pyron pode usar a rede: permita em redes privadas. A conexão fica só na sua rede, com um código no link, e desliga quando você desligar aqui ou fechar o aplicativo.",
};
const CABECALHO_CELULAR = 16;
const celularEstado = { relogio: null, esp: null };

async function carregarCelular() {
  const aba = $("#aba-celular");
  if (!aba.childElementCount) aba.replaceChildren(el("div", { class: "cartao esqueleto", style: { height: "var(--apr-visor-max)" } }));
  try {
    desenharCelular(await api("/api/celular"));
  } catch (e) {
    aba.replaceChildren(el("div", { class: "erro-caixa", role: "alert" }, e.message));
  }
}

function pararCelular() {
  clearInterval(celularEstado.relogio);
  celularEstado.relogio = null;
  const esp = celularEstado.esp;
  celularEstado.esp = null;
  if (esp) esp.ws.close();
}

function desenharCelular(c) {
  const aba = $("#aba-celular");
  pararCelular();
  if (!c.ligado) {
    const botao = el("button", { type: "button", class: "btn", onclick: (ev) => ligarCelular(ev.currentTarget) }, C.ligar);
    aba.replaceChildren(el("div", { class: "cartao celular-ligar" },
      el("h2", {}, "Câmera do celular"),
      el("p", {}, "Aponte a câmera do celular para uma imagem térmica e o modelo identifica o para-raio e as peças ao vivo, sem instalar nada no celular."),
      el("ol", { class: "lista" }, ...C.passos.map((p) => el("li", {}, p))),
      el("div", {}, botao),
      el("p", { class: "nota" }, C.nota),
      el("p", { class: "nota" }, C.rede)));
    return;
  }
  aba.replaceChildren(el("div", { class: "celular-grade" },
    el("div", { class: "cartao celular-conectar" },
      el("h2", {}, C.abra),
      el("img", { class: "celular-qr", src: `/api/celular/qr.png?v=${encodeURIComponent(c.url)}`, alt: "QR code com o endereço para o celular" }),
      el("div", { class: "celular-link" }, el("code", { class: "celular-url" }, c.url),
        el("button", { type: "button", class: "btn btn-fantasma", onclick: () => navigator.clipboard.writeText(c.url).catch(() => {}) }, C.copiar)),
      el("p", { class: "nota" }, C.avisoCertificado),
      el("span", { class: "linha-estado", id: "celular-status" }),
      el("button", { type: "button", class: "btn btn-fantasma", onclick: (ev) => desligarCelular(ev.currentTarget) }, C.desligar)),
    el("div", { class: "cartao" },
      el("div", { class: "cartao-cabeca" }, el("h2", {}, C.espelho), el("span", { class: "nota num", id: "celular-ritmo" })),
      el("div", { id: "celular-espelho" }, el("div", { class: "vazio" }, el("h3", {}, C.esperandoTitulo), el("p", {}, C.esperandoTexto))),
      el("div", { class: "celular-achados", id: "celular-achados" }),
      el("p", { class: "nota" }, C.nota))));
  abrirEspelho();
  atualizarCelular(c);
  celularEstado.relogio = setInterval(async () => {
    try {
      const novo = await api("/api/celular");
      if (!novo.ligado) return desenharCelular(novo);
      atualizarCelular(novo);
    } catch { /* tenta de novo no próximo ciclo */ }
  }, 800);
}

function atualizarCelular(c) {
  const u = c.ultimo;
  const s = $("#celular-status");
  if (!s) return;
  s.className = `linha-estado${c.conectado ? " ok" : ""}`;
  s.replaceChildren(el("i"), el("span", {}, c.conectado ? C.conectado : u ? C.desconectado(fmt(u.ha_s, 0)) : C.esperando));
  $("#celular-ritmo").textContent = u && c.conectado ? C.ritmo(u.quadros_por_s, u.analises_por_s, u.ms) : "";
}

async function ligarCelular(botao) {
  botao.disabled = true;
  try {
    desenharCelular(await api("/api/celular/ligar", { method: "POST" }));
  } catch (e) {
    botao.disabled = false;
    $("#aba-celular .cartao").append(el("p", { class: "erro-caixa", role: "alert" }, e.message));
  }
}

async function desligarCelular(botao) {
  botao.disabled = true;
  desenharCelular(await api("/api/celular/desligar", { method: "POST" }));
}

function abrirEspelho() {
  const ws = new WebSocket(`ws://${location.host}/api/celular/ws`);
  ws.binaryType = "arraybuffer";
  const esp = { ws, pendente: null, decodificando: false, posicao: null, resultado: null, lugares: new Map(), largura: 0, altura: 0 };
  celularEstado.esp = esp;
  ws.addEventListener("message", (ev) => {
    if (celularEstado.esp !== esp) return;
    if (typeof ev.data === "string") {
      esp.resultado = JSON.parse(ev.data);
      desenharResultadoCelular(esp);
      desenharAchadosCelular(esp);
      return;
    }
    esp.pendente = ev.data; // o mais novo substitui o que esperava: sem fila
    if (!esp.decodificando) mostrarQuadros(esp);
  });
  ws.addEventListener("close", () => {
    if (celularEstado.esp === esp) setTimeout(() => { if (celularEstado.esp === esp) abrirEspelho(); }, 1600);
  });
}

async function mostrarQuadros(esp) {
  esp.decodificando = true;
  try {
    while (esp.pendente && celularEstado.esp === esp) {
      const dados = esp.pendente;
      esp.pendente = null;
      if (dados.byteLength <= CABECALHO_CELULAR) continue;
      const cab = new DataView(dados, 0, CABECALHO_CELULAR);
      const x = cab.getFloat32(8, true);
      const y = cab.getFloat32(12, true);
      let imagem;
      try {
        imagem = await createImageBitmap(new Blob([new Uint8Array(dados, CABECALHO_CELULAR)], { type: "image/jpeg" }));
      } catch {
        continue;
      }
      esp.posicao = Number.isFinite(x) && Number.isFinite(y) ? { x, y, trecho: cab.getUint32(4, true) } : null;
      desenharQuadro(esp, imagem);
    }
  } finally {
    esp.decodificando = false;
  }
}

function desenharQuadro(esp, imagem) {
  const espelho = $("#celular-espelho");
  if (!espelho) return imagem.close();
  let quadro = $(".celular-quadro", espelho);
  if (!quadro) {
    quadro = el("div", { class: "celular-quadro" }, el("canvas", { role: "img", "aria-label": "Vídeo da câmera do celular" }), el("div", { class: "celular-caixas" }));
    espelho.replaceChildren(quadro);
  }
  const tela = $("canvas", quadro);
  const mudou = tela.width !== imagem.width || tela.height !== imagem.height;
  if (mudou) { tela.width = imagem.width; tela.height = imagem.height; }
  tela.getContext("2d").drawImage(imagem, 0, 0);
  imagem.close();
  if (mudou || esp.largura !== tela.clientWidth) desenharResultadoCelular(esp);
  else moverCaixas(esp);
}

/** Quanto a câmera andou do quadro analisado ao quadro na tela (fração), ou null se não dá para saber. */
function deslocamento(esp) {
  const r = esp.resultado;
  if (!r || !r.posicao || !esp.posicao) return { x: 0, y: 0 };
  if (r.posicao.trecho !== esp.posicao.trecho) return null;
  const d = { x: esp.posicao.x - r.posicao.x, y: esp.posicao.y - r.posicao.y };
  return Math.hypot(d.x, d.y) > 0.5 ? null : d;
}

function moverCaixas(esp) {
  const camada = $("#celular-espelho .celular-caixas");
  if (!camada) return;
  const d = deslocamento(esp);
  camada.classList.toggle("sumido", !d);
  if (d) camada.style.transform = `translate3d(${(d.x * esp.largura).toFixed(1)}px, ${(d.y * esp.altura).toFixed(1)}px, 0)`;
}

const temperaturaPeca = (d) => (d.tmax != null ? `${d.tmax_acima ? "≥ " : ""}${fmt(d.tmax)} °C` : null);

function desenharResultadoCelular(esp) {
  const quadro = $("#celular-espelho .celular-quadro");
  const r = esp.resultado;
  if (!quadro || !r) return;
  const pct = (v) => `${v * 100}%`;
  const caixaEm = (b) => ({ left: pct(b[0]), top: pct(b[1]), width: pct(b[2] - b[0]), height: pct(b[3] - b[1]) });
  const rotulos = r.deteccoes.map((d) => el("span", { class: "rotulo" }, el("i", { style: { background: COR_PECA[d.classe] } }),
    temperaturaPeca(d) ? `${d.nome} · ${temperaturaPeca(d)}` : d.nome));
  const barra = r.escala && r.escala.barra;
  $(".celular-caixas", quadro).replaceChildren(
    ...(r.area ? [el("div", { class: "celular-area", style: caixaEm(r.area) })] : []),
    ...(barra ? [el("div", { class: "celular-barra", style: caixaEm(barra) })] : []),
    ...r.deteccoes.map((d) => el("div", { class: `caixa ${d.classe}`, style: caixaEm(d.caixa) })),
    ...rotulos);
  const W = quadro.clientWidth;
  const H = quadro.clientHeight;
  esp.largura = W;
  esp.altura = H;
  const chaves = chavesDasDeteccoes(r.deteccoes);
  const itens = r.deteccoes.map((d, i) => ({ chave: chaves[i], largura: rotulos[i].offsetWidth, altura: rotulos[i].offsetHeight,
    caixa: { x: d.caixa[0] * W, y: d.caixa[1] * H, w: (d.caixa[2] - d.caixa[0]) * W, h: (d.caixa[3] - d.caixa[1]) * H } }));
  posicionarRotulos(itens, { x0: 4, y0: 4, x1: W - 4, y1: H - 4 }, esp.lugares, 4)
    .forEach((p, i) => { rotulos[i].style.transform = `translate(${Math.round(p.x)}px, ${Math.round(p.y)}px)`; });
  moverCaixas(esp);
}

function desenharAchadosCelular(esp) {
  const lista = $("#celular-achados");
  const r = esp.resultado;
  if (!lista || !r) return;
  const pecas = [...r.deteccoes].sort((a, b) => a.caixa[1] - b.caixa[1]);
  const itens = pecas.length
    ? pecas.map((d) => el("span", { class: "etiqueta" }, el("i", { style: { background: COR_PECA[d.classe] } }),
      [d.nome, `${Math.round(d.confianca * 100)}%`, temperaturaPeca(d)].filter(Boolean).join(" · ")))
    : [el("span", { class: "nota" }, r.area ? C.nenhuma : C.semTermograma)];
  if (r.escala) itens.push(el("span", { class: "nota" }, r.escala.estado === "lida" ? C.escalaLida(fmt(r.escala.min), fmt(r.escala.max)) : C.escalaLendo));
  lista.replaceChildren(...itens);
}

// ------------------------------------------------------------------ sinal para o lançador e início

const avisarServidor = () => fetch("/api/sinal", { method: "POST" }).catch(() => {});
avisarServidor();
setInterval(avisarServidor, 10000);

vazioAnalise();
montarGaleria();
acompanharModelo();
