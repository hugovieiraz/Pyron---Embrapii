"use strict";

// Fotos para medir: o celular só tira (ou escolhe da galeria) e envia. O arquivo vai inteiro para o Pyron do
// computador, byte por byte (sem recomprimir: qualidade, lente e EXIF intactos); a medida, com ou sem o post-it,
// é feita lá, em Captura › Medir foto, onde a foto nova abre sozinha.

const T = TEXTOS.medirCelular;
const BASE = location.pathname.replace(/\/medir\/?$/, "");
const $ = (s) => document.querySelector(s);
const enviadas = [];  // { arquivo, url, estado: "fila"|"enviando"|"enviada"|"erro", progresso, id, erro }
let enviando = false;

const mb = (bytes) => (bytes / 1048576).toLocaleString("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

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

/** Envia o arquivo como corpo (XMLHttpRequest para ter o progresso: foto de 3 a 8 MB no Wi-Fi leva uns segundos). */
function enviar(item) {
  return new Promise((ok, falha) => {
    const x = new XMLHttpRequest();
    x.open("POST", `${BASE}/medir/foto`);
    x.setRequestHeader("Content-Type", item.arquivo.type || "application/octet-stream");
    x.upload.onprogress = (ev) => { if (ev.lengthComputable) { item.progresso = ev.loaded / ev.total; desenharItem(item); } };
    x.onload = () => {
      let corpo = null;
      try { corpo = JSON.parse(x.responseText); } catch { /* resposta sem JSON */ }
      if (x.status >= 200 && x.status < 300 && corpo) ok(corpo);
      else falha(new Error((corpo && (corpo.erro || corpo.detail)) || T.erroServidor(x.status)));
    };
    x.onerror = () => falha(new Error(T.semConexao));
    x.send(item.arquivo);
  });
}

async function processarFila() {
  if (enviando) return;
  enviando = true;
  for (let item = proximo(); item; item = proximo()) {
    item.estado = "enviando"; item.progresso = 0; desenharItem(item);
    try {
      item.id = (await enviar(item)).id;
      item.estado = "enviada";
      ligado(true);
    } catch (e) {
      item.estado = "erro"; item.erro = e.message;
      ligado(e.message !== T.semConexao);
    }
    desenharItem(item);
  }
  enviando = false;
  $("#nota-pc").textContent = enviadas.some((i) => i.estado === "enviada") ? T.noComputador : "";
}
const proximo = () => enviadas.find((i) => i.estado === "fila");

function adicionar(arquivos) {
  for (const arquivo of arquivos) {
    const item = { arquivo, url: URL.createObjectURL(arquivo), estado: "fila", progresso: 0, id: null, erro: null, n: enviadas.length + 1 };
    enviadas.unshift(item);
    item.no = el("li", { class: "med-item" });
    $("#lista").prepend(item.no);
    desenharItem(item);
  }
  $("#bloco-enviadas").hidden = false;
  processarFila();
}

function desenharItem(item) {
  const miniatura = el("img", { class: "med-mini", src: item.url, alt: "", loading: "lazy" });
  // HEIC no Android: o navegador não mostra; depois de enviada, a prévia vem do computador
  miniatura.onerror = () => { miniatura.onerror = null; if (item.id) miniatura.src = `${BASE}/medir/${item.id}/previa`; else miniatura.classList.add("sem"); };
  const situacao = {
    fila: el("span", { class: "med-situ" }, T.naFila),
    enviando: el("span", { class: "med-situ" }, T.enviando(Math.round(item.progresso * 100))),
    enviada: el("span", { class: "med-situ ok" }, T.enviada),
    erro: el("span", { class: "med-situ ruim" }, item.erro || T.erroEnvio),
  }[item.estado];
  const barra = item.estado === "enviando"
    ? el("span", { class: "med-barra", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(Math.round(item.progresso * 100)), "aria-label": T.progresso },
      el("i", { style: `transform: scaleX(${item.progresso})` }))
    : null;
  const tentar = item.estado === "erro" ? el("button", { class: "cel-btn cel-btn-contorno med-tentar", type: "button", onclick: () => { item.estado = "fila"; processarFila(); } }, T.tentar) : null;
  item.no.replaceChildren(...[miniatura,
    el("span", { class: "med-info" }, el("b", {}, T.foto(item.n)), el("span", { class: "cel-nota" }, `${mb(item.arquivo.size)} MB · ${T.original}`), situacao, barra),
    tentar].filter(Boolean));
}

/** Selo do topo: o computador respondeu ou não. */
function ligado(sim) {
  const s = $("#ligado");
  s.textContent = sim ? T.ligado : T.desligado;
  s.classList.toggle("off", !sim);
}

// ---------------------------------------------------------------- início
$("#subtitulo").textContent = T.subtitulo;
$("#titulo").textContent = T.titulo;
$("#dica").textContent = T.dica;
$("#btn-tirar").textContent = T.tirar;
$("#btn-galeria").textContent = T.galeria;
$("#titulo-enviadas").textContent = T.enviadas;
$("#btn-tirar").addEventListener("click", () => $("#arq-camera").click());
$("#btn-galeria").addEventListener("click", () => $("#arq-galeria").click());
for (const id of ["#arq-camera", "#arq-galeria"]) $(id).addEventListener("change", (ev) => { adicionar([...ev.target.files]); ev.target.value = ""; });
fetch(location.pathname, { cache: "no-store" }).then((r) => ligado(r.ok)).catch(() => ligado(false));
