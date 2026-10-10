"use strict";

// Página do celular: câmera traseira ao vivo, um quadro por vez para o Pyron e as caixas de volta.
// O próximo quadro só sai quando a resposta do anterior chega: o ritmo é o que o computador aguenta,
// e o quadro analisado é sempre o mais novo.

const T = TEXTOS.celular;
const $ = (s) => document.querySelector(s);
const TOKEN = location.pathname.split("/")[2] || "";
const BASE = `/c/${TOKEN}`;
const LADO_QUADRO = 640; // o detector trabalha em 640: maior que isso só pesa na rede
const LADO_CAPTURA = 1280; // a captura vira inspeção e merece mais detalhe
const QUALIDADE_JPEG = 0.72;
const ESPERA_ERRO_MS = 1500;
const ESPERA_PAUSA_MS = 200;
const JANELA_RITMO = 8; // análises usadas na média de análises por segundo

const video = $("#video");
const foto = $("#foto-img");
const estado = { ativo: false, pausado: false, capturando: false, ultimas: [], tempos: [], fonte: video };

const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
const numero = (v, casas = 1) => v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

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

// ------------------------------------------------------------------ câmera e quadros

async function ligarCamera() {
  $("#inicio-nota").textContent = "";
  if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    $("#inicio-nota").textContent = T.semCameraAoVivo;
    $("#btn-foto").hidden = false;
    return;
  }
  try {
    video.srcObject = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    await video.play();
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
      estado.ultimas = r.deteccoes;
      desenhar();
      status("ao-vivo", T.aoVivo);
    } catch (e) {
      status("erro", e instanceof TypeError ? T.semConexao : e.message);
      await esperar(ESPERA_ERRO_MS);
    }
  }
}

function registrarRitmo() {
  estado.tempos.push(performance.now());
  if (estado.tempos.length > JANELA_RITMO) estado.tempos.shift();
  const t = estado.tempos;
  if (t.length >= 2) $("#ritmo").textContent = T.ritmo(numero((1000 * (t.length - 1)) / (t[t.length - 1] - t[0])));
}

// ------------------------------------------------------------------ caixas sobre a imagem

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

function desenhar() {
  const camada = $("#caixas");
  const area = areaDaImagem();
  const lista = area ? estado.ultimas : [];
  while (camada.children.length < lista.length) {
    const caixa = document.createElement("div");
    caixa.className = "cel-caixa";
    caixa.append(document.createElement("span"));
    camada.append(caixa);
  }
  [...camada.children].forEach((caixa, i) => {
    const d = lista[i];
    caixa.hidden = !d;
    if (!d) return;
    const [x0, y0, x1, y1] = d.caixa;
    const topo = area.y + y0 * area.h;
    caixa.style.transform = `translate(${area.x + x0 * area.w}px, ${topo}px)`;
    caixa.style.width = `${(x1 - x0) * area.w}px`;
    caixa.style.height = `${(y1 - y0) * area.h}px`;
    // Perto do topo, o rótulo ficaria embaixo da barra do Pyron: vai para baixo da caixa.
    caixa.classList.toggle("baixo", topo < $(".cel-topo").offsetHeight + caixa.firstChild.offsetHeight);
    caixa.firstChild.textContent = T.rotulo(d.nome, Math.round(d.confianca * 100));
  });
  $("#lista").textContent = estado.pausado ? T.pausado : resumo(lista);
}

function resumo(lista) {
  if (!lista.length) return T.nadaAchado;
  const contagem = new Map();
  for (const d of lista) contagem.set(d.nome, (contagem.get(d.nome) || 0) + 1);
  return [...contagem].map(([nome, n]) => (n > 1 ? `${n} × ${nome}` : nome)).join(" · ");
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
    const r = await api("/quadro", { method: "POST", body: arquivo, headers: { "Content-Type": arquivo.type || "image/jpeg" } });
    estado.ultimas = r.deteccoes;
    desenhar();
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

api("/modelo")
  .then((m) => {
    $("#modelo").textContent = m.nome;
    status("", T.pronto);
  })
  .catch((e) => {
    $("#inicio-nota").textContent = e instanceof TypeError ? T.semConexao : e.message;
    status("erro", T.semModelo);
  });
