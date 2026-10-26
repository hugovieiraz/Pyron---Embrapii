"use strict";

// Medir objeto pelo celular: a foto (câmera ou galeria) vai inteira para o Pyron do computador, byte por byte (sem
// recomprimir: qualidade e metadados intactos); um toque no objeto (ou dois, nas pontas) e o computador mede nos dois
// modelos de profundidade, sem e com o post-it. As medidas também aparecem no computador (Captura › Medir foto).

const T = TEXTOS.medirCelular;
const BASE = location.pathname.replace(/\/medir\/?$/, "");
const ORDEM = ["altura", "comprimento", "largura", "espessura", "distancia"];
const SVG = "http://www.w3.org/2000/svg";
const $ = (s) => document.querySelector(s);

const estado = { foto: null, largura: 0, altura: 0, modo: "ponto", ref: true, primeiro: null, medidas: [], contorno: [], contornoRef: [] };

const numero = (v) => v.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function el(tag, props = {}, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const f of filhos.flat()) if (f != null && f !== false) n.append(f instanceof Node ? f : document.createTextNode(String(f)));
  return n;
}

function svg(tag, attrs) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
}

async function api(caminho, opcoes = {}) {
  let r;
  try {
    r = await fetch(BASE + caminho, opcoes);
  } catch {
    throw new Error(T.semConexao);
  }
  const corpo = await r.json().catch(() => null);
  if (!r.ok) throw new Error((corpo && corpo.erro) || T.erroServidor(r.status));
  return corpo;
}

const erro = (texto) => { $("#erro").textContent = texto || ""; };

function segmentado(no, opcoes, valor, aoMudar) {
  no.replaceChildren(...opcoes.map(([v, texto]) => el("button", { type: "button", "aria-pressed": String(v === valor),
    onclick: (ev) => { [...no.children].forEach((b) => b.setAttribute("aria-pressed", String(b === ev.currentTarget))); aoMudar(v); } }, texto)));
}

function dica() {
  $("#dica").textContent = estado.modo === "pontos" ? (estado.primeiro ? T.toqueSegundo : T.toquePrimeiro) : T.toque;
}

// ---------------------------------------------------------------- foto
async function escolher(arquivo) {
  if (!arquivo) return;
  erro("");
  Object.assign(estado, { foto: null, primeiro: null, medidas: [], contorno: [], contornoRef: [] });
  $("#inicio").hidden = true;
  $("#area-foto").hidden = false;
  $("#resultados").replaceChildren();
  $("#dica").textContent = T.enviando;
  const img = $("#foto");
  const url = URL.createObjectURL(arquivo);
  try {
    // o próprio arquivo como corpo: os bytes que a câmera gravou, com EXIF e tudo
    const r = await api("/medir/foto", { method: "POST", body: arquivo, headers: { "Content-Type": arquivo.type || "application/octet-stream" } });
    estado.foto = r.id;
    $("#nota-pc").textContent = T.enviada(numero(arquivo.size / 1048576));
  } catch (e) {
    erro(e.message);
    $("#dica").textContent = "";
    return;
  }
  img.onload = () => { estado.largura = img.naturalWidth; estado.altura = img.naturalHeight; desenhar(); dica(); };
  img.onerror = () => { img.onerror = null; img.src = `${BASE}/medir/${estado.foto}/previa`; };  // HEIC: prévia do computador
  img.src = url;
}

// ---------------------------------------------------------------- toque e medida
$("#quadro").addEventListener("click", (ev) => {
  if (!estado.foto || !estado.largura) return;
  const b = $("#foto").getBoundingClientRect();
  const p = [Math.round((ev.clientX - b.left) / b.width * estado.largura), Math.round((ev.clientY - b.top) / b.height * estado.altura)];
  if (estado.modo === "pontos") {
    if (!estado.primeiro) { estado.primeiro = p; desenhar(); dica(); return; }
    const par = [estado.primeiro, p];
    estado.primeiro = null;
    medir({ pontos: par });
  } else medir({ ponto: p });
});

async function medir(pista) {
  const n = estado.medidas.length + 1;
  const item = { n, pista, r: null };
  estado.medidas.push(item);
  desenhar(); dica();
  const cartao = el("article", { class: "med-cartao" }, el("h2", {}, T.medida(n)), el("p", { class: "cel-nota" }, T.medindo));
  $("#resultados").prepend(cartao);
  try {
    const corpo = { pista, referencia: estado.ref ? { auto: "postit_rosa" } : null };
    item.r = await api(`/medir/${estado.foto}`, { method: "POST", body: JSON.stringify(corpo), headers: { "Content-Type": "application/json" } });
    estado.contorno = item.r.contorno || [];
    estado.contornoRef = item.r.contorno_referencia || [];
    cartao.replaceWith(resultado(item));
    $("#nota-pc").textContent = T.noComputador;
  } catch (e) {
    estado.medidas = estado.medidas.filter((x) => x !== item);
    cartao.remove();
    erro(e.message);
  }
  desenhar();
}

function resultado(item) {
  const res = item.r.resultados;
  const ids = Object.keys(res);
  const colunas = ids.flatMap((k) => [[k, "sem_referencia", T.modelos[k] || k], [k, "com_referencia", T.comRef(T.modelos[k] || k)]])
    .filter(([k, modo]) => res[k][modo]);
  const medidas = ORDEM.filter((q) => colunas.some(([k, modo]) => res[k][modo][`${q}_cm`] != null));
  const tabela = el("table", { class: "med-tabela" },
    el("thead", {}, el("tr", {}, el("th", {}, ""), ...medidas.map((q) => el("th", {}, T.nomes[q])))),
    el("tbody", {}, colunas.map(([k, modo, nome]) => el("tr", {}, el("th", {}, nome),
      ...medidas.map((q) => el("td", {}, res[k][modo][`${q}_cm`] != null ? numero(res[k][modo][`${q}_cm`]) : "—"))))));
  const avisos = [];
  for (const k of ids) {
    if (res[k].erro) avisos.push(T.erroModelo(T.modelos[k] || k, res[k].erro));
    const ign = res[k].com_referencia && res[k].com_referencia.referencia_ignorada;
    if (ign) avisos.push(T.refIgnorada(T.modelos[k] || k, ign));
  }
  return el("article", { class: "med-cartao" }, el("h2", {}, `${T.medida(item.n)} · cm`), tabela, ...avisos.map((a) => el("p", { class: "med-aviso" }, a)));
}

function desenhar() {
  const c = $("#camada");
  if (!estado.largura) return;
  c.setAttribute("viewBox", `0 0 ${estado.largura} ${estado.altura}`);
  const filhos = [];
  const poli = (lista, classe) => lista.forEach((p) => {
    const pts = p.map((q) => q.join(",")).join(" ");
    filhos.push(svg("polygon", { points: pts, class: `${classe} sombra` }), svg("polygon", { points: pts, class: classe }));
  });
  poli(estado.contornoRef, "ref");
  poli(estado.contorno, "obj");
  const r = Math.max(estado.largura, estado.altura) * 0.008;
  for (const m of estado.medidas) {
    if (m.pista.ponto) filhos.push(svg("circle", { cx: m.pista.ponto[0], cy: m.pista.ponto[1], r }));
    if (m.pista.pontos) {
      const [[x1, y1], [x2, y2]] = m.pista.pontos;
      filhos.push(svg("line", { x1, y1, x2, y2, class: "sombra" }), svg("line", { x1, y1, x2, y2 }));
      m.pista.pontos.forEach(([cx, cy]) => filhos.push(svg("circle", { cx, cy, r })));
    }
  }
  if (estado.primeiro) filhos.push(svg("circle", { cx: estado.primeiro[0], cy: estado.primeiro[1], r }));
  c.replaceChildren(...filhos);
}

// ---------------------------------------------------------------- início
$("#titulo").textContent = T.titulo;
$("#texto").textContent = T.texto;
$("#btn-tirar").textContent = T.tirar;
$("#btn-galeria").textContent = T.galeria;
$("#btn-nova").textContent = T.novaFoto;
$("#btn-tirar").addEventListener("click", () => $("#arq-camera").click());
$("#btn-galeria").addEventListener("click", () => $("#arq-galeria").click());
$("#btn-nova").addEventListener("click", () => $("#arq-camera").click());
for (const id of ["#arq-camera", "#arq-galeria"]) $(id).addEventListener("change", (ev) => { escolher(ev.target.files[0]); ev.target.value = ""; });
segmentado($("#seg-modo"), [["ponto", T.objeto], ["pontos", T.doisPontos]], "ponto", (v) => { estado.modo = v; estado.primeiro = null; desenhar(); dica(); });
segmentado($("#seg-ref"), [[true, T.comPostit], [false, T.semReferencia]], true, (v) => { estado.ref = v; });
