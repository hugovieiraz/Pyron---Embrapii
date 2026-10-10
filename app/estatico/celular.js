"use strict";

// Página do celular: câmera traseira ao vivo, um quadro por vez para o Pyron e as caixas de volta.
// O próximo quadro só sai quando a resposta do anterior chega: o ritmo é o que o computador aguenta,
// e o quadro analisado é sempre o mais novo.

const T = TEXTOS.celular;
const $ = (s) => document.querySelector(s);
const TOKEN = location.pathname.split("/")[2] || "";
const BASE = `/c/${TOKEN}`;
// O Pyron recorta só o termograma do quadro: mandar 960 deixa o recorte com detalhe para o detector (640).
const LADO_QUADRO = 960;
const LADO_CAPTURA = 1280; // a captura vira inspeção e merece mais detalhe
const QUALIDADE_JPEG = 0.72;
const ESPERA_ERRO_MS = 1500;
const ESPERA_PAUSA_MS = 200;
const JANELA_RITMO = 8; // análises usadas na média de análises por segundo
const PASSOS_ZOOM = [1, 2, 3];

const video = $("#video");
const foto = $("#foto-img");
const estado = {
  ativo: false, pausado: false, capturando: false, fonte: video,
  ultimas: [], area: null, tempos: [], ritmo: null, classes: [],
  lugares: new Map(), // chave da detecção → lugar do rótulo no quadro passado
  trilha: null, zooms: [], zoom: 0,
};

const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
const numero = (v, casas = 1) => v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
const token = (nome) => parseFloat(getComputedStyle(document.documentElement).getPropertyValue(nome)) || 0;

async function api(caminho, opcoes = {}) {
  const r = await fetch(BASE + caminho, opcoes);
  const corpo = await r.json().catch(() => null);
  if (!r.ok) throw new Error((corpo && corpo.erro) || T.erroServidor(r.status));
  return corpo;
}

function status(tipo, texto) {
  const s = $("#status");
  s.className = `cel-status ${tipo}`;
  s.lastElementChild.textContent = texto;
}

let relogioAviso = null;
function avisar(texto, erro = false) {
  const a = $("#aviso");
  a.textContent = texto;
  a.classList.toggle("erro", erro);
  a.hidden = false;
  clearTimeout(relogioAviso);
  relogioAviso = setTimeout(() => { a.hidden = true; }, erro ? 6000 : 3000);
}

// ------------------------------------------------------------------ câmera, zoom e quadros

async function ligarCamera() {
  $("#inicio-nota").textContent = "";
  if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    $("#inicio-nota").textContent = T.semCameraAoVivo;
    $("#btn-foto").hidden = false;
    return;
  }
  try {
    const fluxo = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      audio: false,
    });
    video.srcObject = fluxo;
    await video.play();
    prepararZoom(fluxo.getVideoTracks()[0]);
  } catch (e) {
    $("#inicio-nota").textContent = e && e.name === "NotAllowedError" ? T.cameraNegada : T.cameraFalhou(e && e.message);
    $("#btn-foto").hidden = false;
    return;
  }
  $("#inicio").hidden = true;
  $("#base").hidden = false;
  manterTelaAcesa();
  estado.ativo = true;
  ciclo();
}

/** Zoom da própria câmera, quando o celular deixa: enche a tela com o termograma sem chegar perto. */
function prepararZoom(trilha) {
  const cap = trilha && trilha.getCapabilities ? trilha.getCapabilities() : {};
  if (!cap.zoom) return;
  estado.trilha = trilha;
  estado.zooms = PASSOS_ZOOM.filter((z) => z >= cap.zoom.min && z <= cap.zoom.max);
  if (estado.zooms.length < 2) return;
  estado.zoom = 0;
  $("#btn-zoom").hidden = false;
}

async function trocarZoom() {
  estado.zoom = (estado.zoom + 1) % estado.zooms.length;
  const z = estado.zooms[estado.zoom];
  try {
    await estado.trilha.applyConstraints({ advanced: [{ zoom: z }] });
    $("#btn-zoom").textContent = T.zoom(z);
  } catch {
    avisar(T.zoomFalhou, true);
  }
}

/** O quadro atual da câmera em JPEG, com o lado maior reduzido a ``lado``. */
function quadroAtual(lado) {
  const w = video.videoWidth;
  const h = video.videoHeight;
  if (!w || !h) return Promise.resolve(null);
  const k = Math.min(1, lado / Math.max(w, h));
  const tela = document.createElement("canvas");
  tela.width = Math.round(w * k);
  tela.height = Math.round(h * k);
  tela.getContext("2d").drawImage(video, 0, 0, tela.width, tela.height);
  return new Promise((ok) => tela.toBlob(ok, "image/jpeg", QUALIDADE_JPEG));
}

async function ciclo() {
  while (estado.ativo) {
    if (estado.pausado || document.hidden) {
      await esperar(ESPERA_PAUSA_MS);
      continue;
    }
    const blob = await quadroAtual(LADO_QUADRO);
    if (!blob) {
      await esperar(ESPERA_PAUSA_MS);
      continue;
    }
    try {
      const r = await api("/quadro", { method: "POST", body: blob, headers: { "Content-Type": "image/jpeg" } });
      if (estado.pausado) continue;
      registrarRitmo();
      receber(r);
    } catch (e) {
      status("erro", e instanceof TypeError ? T.semConexao : e.message);
      await esperar(ESPERA_ERRO_MS);
    }
  }
}

function receber(r) {
  estado.ultimas = r.deteccoes;
  estado.area = r.area;
  desenhar();
  const ritmo = estado.ritmo ? ` · ${T.ritmo(numero(estado.ritmo))}` : "";
  status(r.area ? "ao-vivo" : "", (r.area ? T.aoVivo : T.procurandoCurto) + ritmo);
}

function registrarRitmo() {
  estado.tempos.push(performance.now());
  if (estado.tempos.length > JANELA_RITMO) estado.tempos.shift();
  const t = estado.tempos;
  if (t.length >= 2) estado.ritmo = (1000 * (t.length - 1)) / (t[t.length - 1] - t[0]);
}

// ------------------------------------------------------------------ caixas, rótulos e legenda

/** Onde a imagem aparece na tela: vídeo em "cover" (preenche), foto em "contain" (inteira). */
function areaDaImagem() {
  const fonte = estado.fonte;
  const W = $("#caixas").clientWidth;
  const H = $("#caixas").clientHeight;
  const iw = fonte === video ? video.videoWidth : foto.naturalWidth;
  const ih = fonte === video ? video.videoHeight : foto.naturalHeight;
  if (!iw || !ih) return null;
  const s = fonte === video ? Math.max(W / iw, H / ih) : Math.min(W / iw, H / ih);
  return { x: (W - iw * s) / 2, y: (H - ih * s) / 2, w: iw * s, h: ih * s };
}

/** Garante ``n`` filhos com a classe dada na camada; devolve os ``n`` primeiros e esconde o resto. */
function reaproveitar(camada, classe, n, criar) {
  let filhos = [...camada.querySelectorAll(`.${classe}`)];
  while (filhos.length < n) {
    const novo = criar();
    camada.append(novo);
    filhos.push(novo);
  }
  filhos.forEach((f, i) => { f.hidden = i >= n; });
  return filhos.slice(0, n);
}

const posicionar = (no, x, y) => { no.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`; };

function desenhar() {
  const area = areaDaImagem();
  const lista = area ? estado.ultimas : [];
  const emTela = (c) => ({ x: area.x + c[0] * area.w, y: area.y + c[1] * area.h, w: (c[2] - c[0]) * area.w, h: (c[3] - c[1]) * area.h });

  const guia = $("#area");
  guia.hidden = !(area && estado.area);
  if (!guia.hidden) {
    const g = emTela(estado.area);
    posicionar(guia, g.x, g.y);
    guia.style.width = `${g.w}px`;
    guia.style.height = `${g.h}px`;
  }

  const caixas = reaproveitar($("#caixas"), "cel-caixa", lista.length, () => Object.assign(document.createElement("div"), { className: "cel-caixa" }));
  const rotulos = reaproveitar($("#rotulos"), "cel-rotulo", lista.length, () => {
    const r = Object.assign(document.createElement("span"), { className: "cel-rotulo" });
    r.append(document.createElement("i"), document.createElement("span"));
    return r;
  });
  const chaves = chavesDasDeteccoes(lista);
  const itens = lista.map((d, i) => {
    const c = emTela(d.caixa);
    posicionar(caixas[i], c.x, c.y);
    caixas[i].style.width = `${c.w}px`;
    caixas[i].style.height = `${c.h}px`;
    rotulos[i].firstChild.style.background = corDaClasse(d.classe, estado.classes);
    rotulos[i].lastChild.textContent = d.nome;
    return { chave: chaves[i], caixa: c, largura: rotulos[i].offsetWidth, altura: rotulos[i].offsetHeight };
  });
  // Os rótulos ficam entre a barra do topo e a base, sem cobrir uns aos outros.
  const W = $("#rotulos").clientWidth;
  const margem = token("--e-1");
  const limites = { x0: margem, y0: $(".cel-topo").offsetHeight + margem, x1: W - margem, y1: $("#base").hidden ? window.innerHeight : $("#base").offsetTop - margem };
  posicionarRotulos(itens, limites, estado.lugares, margem).forEach((p, i) => posicionar(rotulos[i], p.x, p.y));

  desenharLegenda(lista);
}

/** Legenda embaixo: uma etiqueta por peça, de cima para baixo, com a cor do tipo e a confiança. */
function desenharLegenda(lista) {
  const ordenadas = [...lista].sort((a, b) => a.caixa[1] - b.caixa[1]);
  $("#legenda").replaceChildren(...ordenadas.map((d) => {
    const chip = Object.assign(document.createElement("span"), { className: "cel-chip" });
    const ponto = document.createElement("i");
    ponto.style.background = corDaClasse(d.classe, estado.classes);
    chip.append(ponto, d.nome, Object.assign(document.createElement("b"), { textContent: T.confianca(Math.round(d.confianca * 100)) }));
    return chip;
  }));
  let texto = "";
  if (estado.pausado) texto = T.pausado;
  else if (!lista.length && estado.tempos.length) texto = estado.area ? T.nadaAchado : T.procurando;
  $("#lista").textContent = texto;
}

// ------------------------------------------------------------------ captura, pausa e modo foto

async function capturar() {
  if (estado.capturando) return;
  estado.capturando = true;
  $("#btn-capturar").disabled = true;
  const flash = $("#flash");
  flash.classList.remove("ativo");
  void flash.offsetWidth;
  flash.classList.add("ativo");
  try {
    const blob = estado.fonte === video ? await quadroAtual(LADO_CAPTURA) : estado.fotoBlob;
    if (!blob) throw new Error(T.semQuadro);
    avisar(T.salvando);
    const r = await api("/capturar", { method: "POST", body: blob, headers: { "Content-Type": "image/jpeg" } });
    avisar(T.salvo(r.regioes));
    if (navigator.vibrate) navigator.vibrate(30);
  } catch (e) {
    avisar(e instanceof TypeError ? T.semConexao : e.message, true);
  } finally {
    estado.capturando = false;
    $("#btn-capturar").disabled = false;
  }
}

function pausar() {
  estado.pausado = !estado.pausado;
  $("#btn-pausar").setAttribute("aria-pressed", String(estado.pausado));
  $("#btn-pausar").textContent = estado.pausado ? T.continuar : T.pausar;
  if (estado.pausado) status("", T.pausado);
  desenhar();
}

/** Sem câmera ao vivo no navegador: tira uma foto, manda e mostra as caixas sobre ela. */
async function analisarFoto(arquivo) {
  if (!arquivo) return;
  estado.fonte = foto;
  estado.fotoBlob = arquivo;
  foto.src = URL.createObjectURL(arquivo);
  await foto.decode().catch(() => {});
  foto.hidden = false;
  video.hidden = true;
  $("#inicio").hidden = true;
  $("#base").hidden = false;
  $("#btn-pausar").hidden = true;
  status("", T.analisando);
  try {
    // Uma foto só não tem o quadro seguinte para confirmar as peças: manda duas vezes.
    await api("/quadro", { method: "POST", body: arquivo, headers: { "Content-Type": arquivo.type || "image/jpeg" } });
    const r = await api("/quadro", { method: "POST", body: arquivo, headers: { "Content-Type": arquivo.type || "image/jpeg" } });
    receber(r);
    status("ao-vivo", T.fotoAnalisada);
  } catch (e) {
    status("erro", e instanceof TypeError ? T.semConexao : e.message);
  }
}

// ------------------------------------------------------------------ tela acesa e início

let travaTela = null;
async function manterTelaAcesa() {
  try {
    if (navigator.wakeLock) travaTela = await navigator.wakeLock.request("screen");
  } catch {
    travaTela = null; // sem bateria suficiente ou sem suporte: a tela pode apagar sozinha
  }
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && estado.ativo) manterTelaAcesa();
});
window.addEventListener("resize", desenhar);

$("#btn-iniciar").addEventListener("click", ligarCamera);
$("#btn-foto").addEventListener("click", () => $("#arquivo-foto").click());
$("#arquivo-foto").addEventListener("change", (ev) => analisarFoto(ev.target.files[0]));
$("#btn-capturar").addEventListener("click", capturar);
$("#btn-pausar").addEventListener("click", pausar);
$("#btn-zoom").addEventListener("click", trocarZoom);

api("/modelo")
  .then((m) => {
    $("#modelo").textContent = m.nome;
    estado.classes = m.classes || [];
    status("", T.pronto);
  })
  .catch((e) => {
    $("#inicio-nota").textContent = e instanceof TypeError ? T.semConexao : e.message;
    status("erro", T.semModelo);
  });
