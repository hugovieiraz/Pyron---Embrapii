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

const BARRA_MAX = 40; // largura máxima de cada coluna, em unidades do desenho (lida de longe no projetor)

/** Colunas agrupadas: uma cor por série (legenda sempre visível), valor na dica, de 0 a 1. */
function graficoColunas({ titulo, nota, grupos, series, valor }) {
  const L = 1100, A = 260, m = { e: 44, d: 8, c: 12, b: 34 };
  const larguraGrupo = (L - m.e - m.d) / grupos.length;
  const barra = Math.min(BARRA_MAX, (larguraGrupo - 24) / series.length - 2);
  const escalaY = (v) => A - m.b - v * (A - m.b - m.c);
  const filhos = [];
  [0, 0.25, 0.5, 0.75, 1].forEach((g) => {
    filhos.push(svg("line", { class: "grade", x1: m.e, x2: L - m.d, y1: escalaY(g), y2: escalaY(g) }));
    filhos.push(svg("text", { class: "eixo", x: m.e - 8, y: escalaY(g) + 4, "text-anchor": "end" }, pct(g, 0)));
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
      alvo.addEventListener("mousemove", (ev) => dica(ev, `<b>${s.nome}</b><br>${grupo}: <b>${pct(v)}</b>`));
      alvo.addEventListener("mouseleave", semDica);
      filhos.push(forma, alvo);
    });
  });
  const fig = svg("svg", { viewBox: `0 0 ${L} ${A}`, role: "img", "aria-label": titulo }, ...filhos);
  const legenda = el("div", { class: "legenda" }, ...series.map((s) => el("span", { class: "chave" }, el("i", { style: { background: s.cor, borderRadius: "var(--r-p)" } }), s.nome)));
  return el("figure", { class: "grafico", style: { margin: 0 } }, el("figcaption", {}, el("b", {}, titulo), nota ? el("p", { class: "nota" }, nota) : null), legenda, fig);
}

// ------------------------------------------------------------------ peças visuais (medidor, casinhas, faixa)

/** Medidor de 0 a 100%: trilha neutra e a parte cheia na cor da série. O número sempre fica escrito ao lado. */
const medidor = (valor, cor = "var(--serie-1)") =>
  el("div", { class: "medidor", "aria-hidden": "true" }, el("i", { style: { width: `${Math.max(0, Math.min(1, valor)) * 100}%`, background: cor } }));

const indicador = (nome, valor, explica, cor) => el("div", { class: "indicador" },
  el("div", { class: "indicador-cabeca" }, el("span", {}, nome), el("b", {}, pct(valor))),
  medidor(valor, cor),
  explica ? el("p", { class: "nota" }, explica) : null);

/** Uma casinha por peça rotulada à mão: cheia, o modelo achou; vazia, perdeu. */
const casasDasPecas = (achadas, total) => el("div", { class: "casas", role: "img", "aria-label": `${achadas} de ${total} peças achadas` },
  ...Array.from({ length: total }, (_, i) => el("i", { class: i < achadas ? "cheia" : null })));

/** Faixa dividida em partes proporcionais (parte do todo), com o número e o nome embaixo de cada parte. */
const faixa = (partes) => el("div", { class: "faixa" }, ...partes.map((p) => el("div", { class: "faixa-parte", style: { flexGrow: p.n } },
  el("i", { style: { background: p.cor } }), el("b", {}, p.n.toLocaleString("pt-BR")), el("span", {}, p.nome))));

// ------------------------------------------------------------------ aba Modelo

let avaliacao = null;
async function dadosAvaliacao() {
  if (!avaliacao) avaliacao = await api("/api/avaliacao");
  return avaliacao;
}

const EXEMPLO_ETAPAS = "FLIR2618.jpg"; // foto de teste que ilustra o "como funciona" (um para-raio, ponto quente no terminal)
const FAIXA_CINZA = 20; // °C abaixo da máxima que ainda aparecem na matriz em cinza; mais frio fica preto (o céu)

async function desenharModelo() {
  const aba = $("#aba-modelo");
  aba.replaceChildren(el("div", { class: "cartao esqueleto", style: { height: "var(--apr-visor-max)" } }));
  try {
    const [est, av] = [estadoModelo || (await api("/api/estado")), await dadosAvaliacao()];
    const tl = av.treino_local;
    const figuras = [1, 2, 3, 4].map(() => el("div", { class: "etapa-figura esqueleto" }));
    const etapa = (n, titulo, texto) => el("div", { class: "etapa" },
      el("div", { class: "etapa-cabeca" }, el("span", { class: "passo" }, n), el("b", {}, titulo)), figuras[n - 1], el("p", {}, texto));
    const fato = (rotulo, valor) => el("div", { class: "fato" }, el("span", {}, rotulo), el("b", {}, valor));
    const destaque = (numero, texto) => el("div", { class: "destaque" }, el("b", {}, numero), el("span", {}, texto));
    const exemplo = el("p", { class: "nota" });
    const f = av.fotos;
    aba.replaceChildren(
      el("div", { class: "cartao" },
        el("h2", {}, "Como funciona"),
        el("div", { class: "etapas" },
          etapa(1, "Foto da câmera", "O JPEG da FLIR traz a imagem colorida e, gravada junto, a temperatura de cada ponto do sensor."),
          etapa(2, "Identificação", `O RF-DETR olha a imagem colorida (reduzida para ${est.modelo.entrada.join(" × ")}) e marca o para-raio, as saias e os terminais.`),
          etapa(3, "Temperatura", "Cada ponto do sensor é um número em °C (160 × 120 = 19.200 medidas na FLIR C5). As caixas são levadas para essa matriz."),
          etapa(4, "Ponto mais quente", "Dentro da caixa de cada para-raio, o ponto de maior temperatura e a peça onde ele está.")),
        exemplo),
      el("div", { class: "cartao" },
        el("h2", {}, est.modelo.nome),
        el("p", { class: "texto-medida" }, "Detector de objetos do tipo transformer (DETR) com base DINOv2, licença Apache 2.0: recebe a imagem inteira e devolve, de uma vez, as caixas e o tipo de cada peça, sem etapas de proposta de regiões."),
        el("div", { class: "fato" }, el("span", {}, "Peças que reconhece"),
          el("div", { class: "pecas-chaves" }, ...Object.entries(COR_PECA).map(([classe, cor]) => el("span", { class: "etiqueta" }, el("i", { style: { background: cor } }), nomeDaClasse(classe))))),
        el("div", { class: "fatos" },
          fato("Entrada", `imagem colorida ${est.modelo.entrada.join(" × ")} pixels`),
          fato("Confiança mínima", pct(est.modelo.limiar, 0)),
          fato("Onde roda agora", est.pronto ? est.motor : T.carregandoModelo),
          fato("Tempo por foto", `~70 ms na placa de vídeo · ${fmt(tl.ms_por_foto_cpu, 0)} ms no processador`),
          fato("Formato", "ONNX (o mesmo arquivo no processador ou na placa)"))),
      el("div", { class: "cartao" },
        el("h2", {}, "Treino"),
        el("div", { class: "destaques" },
          destaque((f.treino + f.validacao + f.teste).toLocaleString("pt-BR"), "fotos térmicas de para-raios, rotuladas no CVAT"),
          destaque(tl.dados.caixas.toLocaleString("pt-BR"), "peças marcadas à mão, uma caixa por peça"),
          destaque(`${fmt(tl.duracao_min, 0)} min`, "de treino na placa de vídeo deste notebook (RTX 3050)"),
          destaque(String(av.comparacao.modelos.length), "detectores treinados e comparados (aba Avaliação)")),
        el("h3", {}, "Como as fotos foram divididas"),
        faixa([
          { n: f.treino, nome: "treino: o modelo aprende com elas", cor: "var(--serie-1)" },
          { n: f.validacao, nome: "validação: escolhe a melhor rodada", cor: "var(--serie-2)" },
          { n: f.teste, nome: "teste: nunca vistas, medem o resultado", cor: "var(--serie-3)" }])),
      el("div", { class: "cartao" },
        el("h2", {}, "Limitações"),
        el("ul", { class: "lista" }, ...est.modelo.limitacoes.map((t) => el("li", {}, t)))));
    ilustrarEtapas(figuras, exemplo);
  } catch (e) {
    aba.replaceChildren(el("div", { class: "erro-caixa", role: "alert" }, e.message));
  }
}

const porcento = (v) => `${v * 100}%`;
const quadroEtapa = (src, extras = []) => el("div", { class: "etapa-quadro" }, el("img", { src, alt: "" }), el("div", { class: "camada" }, ...extras));
const caixaEtapa = (caixa, cor) => el("div", { class: "caixa-etapa", style: {
  left: porcento(caixa[0]), top: porcento(caixa[1]), width: porcento(caixa[2] - caixa[0]), height: porcento(caixa[3] - caixa[1]), borderColor: cor } });

/** As quatro etapas com uma foto de teste de verdade. Sem o acervo ou sem o modelo, ficam só os textos. */
async function ilustrarEtapas(figuras, legenda) {
  try {
    const exemplos = (await api("/api/exemplos")).filter((e) => e.disponivel);
    if (!exemplos.length) throw new Error(T.semAcervo);
    const nome = (exemplos.find((e) => e.nome === EXEMPLO_ETAPAS) || exemplos[0]).nome;
    const r = await api(`/api/exemplos/${encodeURIComponent(nome)}/analisar`, { method: "POST" });
    const pr = r.para_raios.find((x) => x.ponto);
    figuras[0].replaceChildren(quadroEtapa(r.imagem));
    figuras[1].replaceChildren(quadroEtapa(r.imagem, r.pecas.map((d) => caixaEtapa(d.caixa, COR_PECA[d.classe]))));
    figuras[2].replaceChildren(r.matriz ? matrizEtapa(r.matriz, pr) : quadroEtapa(r.imagem));
    const quente = [];
    if (pr) {
      const [x, y] = pr.ponto;
      quente.push(caixaEtapa(pr.caixa, "var(--branco)"), el("div", { class: "mira", style: { left: porcento(x), top: porcento(y) } }),
        el("span", { class: "mira-rotulo num etapa-rotulo", style: x > 0.6 ? { right: `calc(${porcento(1 - x)} + var(--e-4))`, top: porcento(y) } : { left: `calc(${porcento(x)} + var(--e-4))`, top: porcento(y) } },
          `${fmt(pr.tmax)} °C`));
    }
    figuras[3].replaceChildren(quadroEtapa(r.imagem, quente));
    figuras.forEach((fig) => fig.classList.remove("esqueleto"));
    legenda.textContent = `Exemplo: ${nome.replace(/\.jpe?g$/i, "")}, uma das ${avaliacao.fotos.teste} fotos de teste${pr ? `. Ponto mais quente: ${fmt(pr.tmax)} °C ${T.onde(pr.onde)}` : ""}.`;
  } catch {
    figuras.forEach((fig) => fig.remove());
  }
}

/** A matriz de temperatura em cinza (mais quente, mais claro) e os números em volta do ponto mais quente. */
function matrizEtapa(m, pr) {
  const tela = el("canvas", { width: m.largura, height: m.altura, class: "matriz-etapa" });
  const ctx = tela.getContext("2d");
  const pixels = ctx.createImageData(m.largura, m.altura);
  const baixo = Math.max(m.min, m.max - FAIXA_CINZA);
  m.valores.forEach((v, i) => {
    const g = Math.round(255 * Math.min(1, Math.max(0, ((v ?? baixo) - baixo) / (m.max - baixo || 1))));
    pixels.data.set([g, g, g, 255], i * 4);
  });
  ctx.putImageData(pixels, 0, 0);
  const quadro = el("div", { class: "etapa-quadro" }, tela);
  if (!pr) return quadro;
  const cx = Math.floor(pr.ponto[0] * m.largura);
  const cy = Math.floor(pr.ponto[1] * m.altura);
  const celulas = [];
  for (let dy = -1; dy <= 1; dy++) {
    for (let dx = -1; dx <= 1; dx++) {
      const x = Math.min(m.largura - 1, Math.max(0, cx + dx));
      const y = Math.min(m.altura - 1, Math.max(0, cy + dy));
      celulas.push(el("span", { class: dx || dy ? null : "centro" }, fmt(m.valores[y * m.largura + x])));
    }
  }
  const lado = pr.ponto[0] > 0.5 ? { left: "var(--e-2)" } : { right: "var(--e-2)" };
  quadro.append(el("div", { class: "camada" },
    el("div", { class: "lupa-matriz", style: { left: porcento((cx - 1) / m.largura), top: porcento((cy - 1) / m.altura), width: porcento(3 / m.largura), height: porcento(3 / m.altura) } }),
    el("div", { class: "numeros num", style: lado, "aria-label": "Temperaturas em volta do ponto mais quente, em °C" }, ...celulas)));
  return quadro;
}

// ------------------------------------------------------------------ aba Avaliação

const FAMILIA = {
  "Faster R-CNN": "Rede convolucional de duas etapas: primeiro propõe regiões, depois classifica. Base MobileNetV3.",
  "YOLO26S": "Detector de uma etapa só, da família YOLO (Ultralytics), tamanho small.",
  "RF-DETR Medium": "Transformer (DETR) com base DINOv2, da Roboflow. Licença Apache 2.0.",
};

async function desenharAvaliacao() {
  const aba = $("#aba-avaliacao");
  aba.replaceChildren(el("div", { class: "cartao esqueleto", style: { height: "var(--apr-visor-max)" } }));
  try {
    const av = await dadosAvaliacao();
    const local = av.treino_local.teste;
    const totalPecas = local.acertos + local.perdidos;
    const modelos = av.comparacao.modelos.map((m, i) => ({ ...m, cor: COR_MODELO[i] }));
    const melhor = modelos.reduce((a, b) => (b.mAP50 > a.mAP50 ? b : a));
    const diferenca = (melhor.mAP50 - Math.min(...modelos.map((m) => m.mAP50))) * 100;

    const cartaoModelo = (m) => el("article", { class: `modelo${m === melhor ? " escolhido" : ""}`, style: { borderTopColor: m.cor } },
      el("div", { class: "modelo-cabeca" }, el("h3", {}, m.nome), m === melhor ? el("span", { class: "selo" }, "o escolhido") : null),
      el("p", { class: "modelo-familia" }, FAMILIA[m.nome] || ""),
      el("div", { class: "modelo-numero" }, el("b", {}, pct(m.mAP50)), el("span", {}, "acerto médio (mAP50)")),
      medidor(m.mAP50, m.cor),
      indicador("Precisão", m.precisao, null, m.cor),
      indicador("Revocação", m.revocacao, null, m.cor),
      el("p", { class: "modelo-rodape" }, `${m.acertos} de ${m.acertos + m.perdidos} peças achadas · ${fmt(m.ms_por_foto, 0)} ms por foto`));

    const colunas = [["mAP50", "mAP50", 3], ["mAP50-95", "mAP50-95", 3], ["Precisão", "precisao", 3], ["Revocação", "revocacao", 3], ["F1", "F1", 3],
      ["Acertos", "acertos", 0], ["Falsos", "falsos", 0], ["Perdidos", "perdidos", 0]];
    const melhorDe = (chave) => (["falsos", "perdidos"].includes(chave) ? Math.min : Math.max)(...modelos.map((m) => m[chave]));
    const tabela = el("table", { class: "tabela" },
      el("thead", {}, el("tr", {}, el("th", {}, "Modelo"), ...colunas.map(([t]) => el("th", {}, t)), el("th", {}, "ms por foto"))),
      el("tbody", {},
        ...modelos.map((m) => el("tr", {}, el("td", {}, el("span", { class: "chave" }, el("i", { style: { background: m.cor } }), m.nome)),
          ...colunas.map(([, k, c]) => el("td", { class: `num${m[k] === melhorDe(k) ? " melhor" : ""}` }, fmt(m[k], c))),
          el("td", { class: "num" }, `${fmt(m.ms_por_foto, 0)} (T4)`))),
        el("tr", { class: "usado" }, el("td", {}, "RF-DETR Medium · treinado neste notebook (o usado aqui)"), ...colunas.map(([, k, c]) => el("td", { class: "num" }, fmt(local[k], c))),
          el("td", { class: "num" }, `${fmt(av.treino_local.ms_por_foto_cpu, 0)} (CPU)`))));
    const classes = av.classes;
    const tabelaClasses = el("table", { class: "tabela" },
      el("thead", {}, el("tr", {}, el("th", {}, "Peça (AP50)"), ...modelos.map((m) => el("th", {}, m.nome)), el("th", {}, "RF-DETR (este notebook)"))),
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
        el("h2", {}, "Os três detectores que treinamos"),
        el("p", { class: "nota" }, `Treinados com as mesmas ${av.fotos.treino} fotos, no ${av.comparacao.onde}, e medidos nas mesmas ${av.fotos.teste} fotos de teste, que nenhum deles viu no treino.`),
        el("div", { class: "modelos" }, ...modelos.map(cartaoModelo)),
        el("p", { class: "aviso" }, `Entre o maior e o menor acerto médio há ${fmt(diferenca, 1)} ponto${diferenca >= 2 ? "s" : ""} percentua${diferenca >= 2 ? "is" : "l"}: na prática, um empate técnico. `
          + `O ${melhor.nome} ficou com o maior e tem licença Apache 2.0, livre para um produto comercial (o YOLO é AGPL).`)),
      el("div", { class: "cartao" },
        el("h2", {}, `O modelo deste aplicativo, nas ${av.fotos.teste} fotos de teste`),
        el("p", { class: "nota" }, `${melhor.nome} treinado de novo neste notebook (${fmt(av.treino_local.duracao_min, 0)} min na RTX 3050), com as mesmas fotos. As ${totalPecas} peças das fotos de teste foram marcadas à mão para conferir.`),
        el("div", { class: "resumo" },
          el("div", { class: "resumo-pecas" },
            el("p", { class: "heroi" }, String(local.acertos), el("span", {}, ` de ${totalPecas}`)),
            el("p", { class: "heroi-rotulo" }, "peças achadas"),
            casasDasPecas(local.acertos, totalPecas),
            el("div", { class: "legenda" },
              el("span", { class: "chave" }, el("i", { class: "casa-chave cheia" }), `achada (${local.acertos})`),
              el("span", { class: "chave" }, el("i", { class: "casa-chave" }), `perdida (${local.perdidos})`))),
          el("div", { class: "resumo-indicadores" },
            indicador("Precisão", local.precisao, "Das caixas que o modelo marcou, quantas estavam certas.", "var(--serie-1)"),
            indicador("Revocação", local.revocacao, "Das peças que existiam na foto, quantas ele achou.", "var(--serie-1)"),
            indicador("Acerto médio (mAP50)", local.mAP50, "Conta como certa a caixa que cobre ao menos metade da peça.", "var(--serie-1)")))),
      el("div", { class: "cartao" },
        el("h2", {}, "Acerto por tipo de peça"),
        graficoColunas({
          titulo: `AP50 de cada detector, nas ${av.fotos.teste} fotos de teste`,
          nota: "O para-raio e as saias quase sempre; o terminal inferior, pequeno e às vezes escondido pela estrutura, é o ponto fraco dos três.",
          grupos: classes, series: modelos, valor: (s, classe) => s.por_classe[classe].AP50 }),
        el("details", { class: "detalhes" },
          el("summary", {}, "Ver todos os números"),
          el("p", { class: "nota" }, "Em negrito, o melhor de cada coluna entre os três do Colab."),
          el("div", { class: "rolar" }, tabela),
          el("div", { class: "rolar" }, tabelaClasses))),
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
