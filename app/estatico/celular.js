"use strict";

// Página do celular: a câmera traseira transmitida ao Pyron, com as peças marcadas por cima, ao vivo.
//
// Transmissão: um WebSocket. Os quadros saem no ritmo das análises (até 15/s), sem fila: se a rede ainda
// não deu conta do anterior, o quadro é pulado. O Pyron analisa sempre o mais novo que tiver.
// Fluidez: a análise leva uns 300 ms e volta atrasada em relação à câmera. Entre uma e outra, o próprio
// celular acompanha o movimento da câmera (compara miniaturas em cinza com um quadro de referência) e
// leva as caixas junto. Cada quadro enviado leva a posição da câmera; a resposta diz qual foi analisado.
// Sem WebSocket (rede que bloqueia), volta ao modo antigo: um quadro por vez, por HTTP.

const T = TEXTOS.celular;
const $ = (s) => document.querySelector(s);
const TOKEN = location.pathname.split("/")[2] || "";
const BASE = `/c/${TOKEN}`;
// O Pyron recorta só o termograma do quadro: mandar 960 deixa o recorte com detalhe para o detector (640).
const LADO_QUADRO = 960;
const LADO_CAPTURA = 1280; // a captura vira inspeção e merece mais detalhe
const QUALIDADE_JPEG = 0.72;
// Quadros por segundo para o computador: acompanha o ritmo das análises (o dobro, mais 2), entre os
// limites. Na CPU (~2,5 análises/s) são ~7; na placa de vídeo, 15. Mandar mais que o computador
// analisa só gasta o celular: cada quadro é um JPEG a codificar.
const QUADROS_POR_S_MIN = 5;
const QUADROS_POR_S_MAX = 15;
const MEDIR_A_CADA_MS = 2000; // o celular conta ao computador quanto gasta em cada etapa
const RASTRO_PESADO_MS = 6; // seguir a câmera passou disso por quadro: segue um quadro sim, outro não
const FILA_MAXIMA = 192 * 1024; // bytes ainda presos no WebSocket: acima disso a rede não deu conta, pula o quadro
const CABECALHO = 16; // número do quadro, trecho do rastro e posição da câmera (x, y), antes do JPEG
const POSICOES_GUARDADAS = 90; // posição da câmera de cada quadro enviado, até a resposta dele chegar
const ESPERA_ERRO_MS = 1500;
const ESPERA_PAUSA_MS = 200;
const TENTATIVAS_WS = 2; // WebSocket que não abriu em nenhuma dessas: a rede bloqueia, vai por HTTP
const LINK_VENCIDO = 4404; // o servidor fecha o WebSocket com isso quando o código do link mudou
const JANELA_RITMO = 8; // análises usadas na média de análises por segundo
const PASSOS_ZOOM = [1, 2, 3];
// Acompanhar a câmera: miniatura em cinza de cada quadro comparada com a de um quadro de referência.
// Comparar com a referência, e não com o quadro anterior, evita somar a cada quadro o erro do pedaço de
// pixel (o movimento lento era subestimado em até 30%); a referência só é trocada quando a cena já andou.
const LARGURA_MINI = 72;
const BUSCA = 3; // pixels da miniatura procurados em volta do deslocamento previsto
const BORDA_MINI = 10; // fica fora da comparação; é também o maior deslocamento até a referência
const TROCA_REFERENCIA = 5; // a cena andou isso (pixels da miniatura) desde a referência: o quadro atual vira a nova
const ERRO_PERDIDO = 24; // diferença média de cinza acima disso: a cena mudou demais, perdeu o rastro
const DESLOCAMENTO_MAXIMO = 0.5; // a câmera andou mais que meia tela desde o quadro analisado: esconde

const video = $("#video");
const foto = $("#foto-img");
const estado = {
  ativo: false, pausado: false, capturando: false, fonte: video,
  ultimas: [], area: null, escala: null, base: null, // última análise e a posição da câmera no quadro dela
  tempos: [], ritmo: null, classes: [],
  lugares: new Map(), // chave da detecção → lugar do rótulo no quadro passado
  trilha: null, zooms: [], zoom: 0,
};
// Transmissão: o WebSocket, o número do último quadro e a posição da câmera em cada quadro enviado.
const envio = { ws: null, abriu: false, falhas: 0, http: false, numero: 0, ultimo: 0, ocupado: false, posicoes: new Map() };
// Medidas do próprio celular, somadas desde o último envio ao computador.
const medidas = { desde: performance.now(), camera: 0, enviados: 0, rastroMs: 0, rastros: 0, jpegMs: 0, jpegs: 0, pular: false, vez: 0 };
// Rastro da câmera, em pixels da miniatura: quanto a cena andou desde o começo do trecho (x, y), a
// miniatura de referência e onde a cena estava nela (rx, ry), e o último passo (vx, vy) para prever o próximo.
const rastro = { tela: null, ctx: null, w: 0, h: 0, referencia: null, rx: 0, ry: 0, x: 0, y: 0, vx: 0, vy: 0, trecho: 0 };

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

// ------------------------------------------------------------------ câmera e zoom

async function ligarCamera() {
  $("#inicio-nota").textContent = "";
  if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    $("#inicio-nota").textContent = T.semCameraAoVivo;
    $("#btn-foto").hidden = false;
    return;
  }
  try {
    const fluxo = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: { ideal: 30 } },
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
  status("", T.conectando);
  conectar();
  aCadaQuadro();
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
    perderRastro(); // a cena muda de tamanho: as caixas antigas não servem mais
  } catch {
    avisar(T.zoomFalhou, true);
  }
}

/** O quadro atual da câmera em JPEG, com o lado maior reduzido a ``lado``. */
const telas = new Map(); // uma tela por tamanho, reaproveitada a cada quadro
function quadroAtual(lado) {
  const w = video.videoWidth;
  const h = video.videoHeight;
  if (!w || !h) return Promise.resolve(null);
  const k = Math.min(1, lado / Math.max(w, h));
  if (!telas.has(lado)) telas.set(lado, document.createElement("canvas"));
  const tela = telas.get(lado);
  tela.width = Math.round(w * k);
  tela.height = Math.round(h * k);
  tela.getContext("2d").drawImage(video, 0, 0, tela.width, tela.height);
  return new Promise((ok) => tela.toBlob(ok, "image/jpeg", QUALIDADE_JPEG));
}

// ------------------------------------------------------------------ acompanhar o movimento da câmera

/** Miniatura em cinza do quadro do vídeo, sem a média (a câmera muda a exposição sozinha). */
function miniatura() {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) return null;
  const w = LARGURA_MINI;
  const h = Math.round((LARGURA_MINI * vh) / vw);
  if (rastro.w !== w || rastro.h !== h) { // primeiro quadro ou o celular girou
    rastro.tela = Object.assign(document.createElement("canvas"), { width: w, height: h });
    rastro.ctx = rastro.tela.getContext("2d", { willReadFrequently: true });
    rastro.ctx.imageSmoothingQuality = "high"; // reduz com média: a tela filmada não vira chuvisco
    rastro.w = w;
    rastro.h = h;
    perderRastro();
  }
  rastro.ctx.drawImage(video, 0, 0, w, h);
  const px = rastro.ctx.getImageData(0, 0, w, h).data;
  const cinza = new Float32Array(w * h);
  let soma = 0;
  for (let i = 0, j = 0; i < cinza.length; i++, j += 4) {
    const v = 0.299 * px[j] + 0.587 * px[j + 1] + 0.114 * px[j + 2];
    cinza[i] = v;
    soma += v;
  }
  const media = soma / cinza.length;
  for (let i = 0; i < cinza.length; i++) cinza[i] -= media;
  return cinza;
}

/** Diferença média entre ``a`` e ``b`` com a cena deslocada de (dx, dy) em ``b``, fora da borda. */
function diferenca(a, b, w, h, dx, dy) {
  const m = BORDA_MINI;
  let soma = 0;
  for (let y = m; y < h - m; y++) {
    const ia = y * w;
    const ib = (y + dy) * w + dx;
    for (let x = m; x < w - m; x++) soma += Math.abs(a[ia + x] - b[ib + x]);
  }
  return soma / ((w - 2 * m) * (h - 2 * m));
}

/**
 * Pedaço de pixel entre três custos vizinhos, entre −0,5 e 0,5. A diferença absoluta cresce em "V"
 * em volta do mínimo, então o ajuste é de duas retas com a mesma inclinação (não uma parábola, que
 * puxa o resultado para o pixel inteiro).
 */
function fracao(antes, meio, depois) {
  const subida = Math.max(antes, depois) - meio;
  return subida > 0 ? Math.max(-0.5, Math.min(0.5, (antes - depois) / (2 * subida))) : 0;
}

/**
 * Quanto a cena andou da miniatura ``a`` para a ``b``, em pixels da miniatura. Procura em volta do
 * deslocamento previsto (px, py) e recentra se o melhor ficou na beira da busca. Devolve também a
 * diferença que sobrou, para saber se a cena é a mesma.
 */
function casar(a, b, w, h, px, py) {
  const lado = 2 * BUSCA + 1;
  const limite = BORDA_MINI - 1;
  const prender = (v) => Math.max(-limite + BUSCA, Math.min(limite - BUSCA, Math.round(v)));
  let cx = prender(px);
  let cy = prender(py);
  let custos;
  let melhor;
  for (let volta = 0; volta < 3; volta++) {
    custos = new Float32Array(lado * lado);
    melhor = 0;
    for (let j = 0; j < lado; j++) {
      for (let i = 0; i < lado; i++) {
        const k = j * lado + i;
        custos[k] = diferenca(a, b, w, h, cx + i - BUSCA, cy + j - BUSCA);
        if (custos[k] < custos[melhor]) melhor = k;
      }
    }
    const i = melhor % lado;
    const j = Math.floor(melhor / lado);
    const nx = prender(cx + i - BUSCA);
    const ny = prender(cy + j - BUSCA);
    const naBeira = i === 0 || i === lado - 1 || j === 0 || j === lado - 1;
    if (!naBeira || (nx === cx && ny === cy)) break;
    cx = nx;
    cy = ny;
  }
  const i = melhor % lado;
  const j = Math.floor(melhor / lado);
  const c = (ii, jj) => custos[jj * lado + ii];
  const fx = i > 0 && i < lado - 1 ? fracao(c(i - 1, j), c(i, j), c(i + 1, j)) : 0;
  const fy = j > 0 && j < lado - 1 ? fracao(c(i, j - 1), c(i, j), c(i, j + 1)) : 0;
  return { x: cx + i - BUSCA + fx, y: cy + j - BUSCA + fy, erro: custos[melhor] };
}

/** A cena mudou demais (sacudiu, trocou o zoom): começa outro trecho; as caixas antigas somem. */
function perderRastro() {
  rastro.trecho += 1;
  rastro.referencia = null;
  rastro.x = rastro.y = rastro.rx = rastro.ry = rastro.vx = rastro.vy = 0;
}

function rastrear() {
  const atual = miniatura();
  if (!atual) return;
  if (!rastro.referencia) {
    rastro.referencia = atual;
    return;
  }
  // previsto: onde a cena estava no quadro anterior, mais o último passo (a mão anda com ritmo)
  const px = rastro.x - rastro.rx + rastro.vx;
  const py = rastro.y - rastro.ry + rastro.vy;
  const d = casar(rastro.referencia, atual, rastro.w, rastro.h, px, py);
  if (d.erro > ERRO_PERDIDO) {
    perderRastro();
    rastro.referencia = atual;
    return;
  }
  const x = rastro.rx + d.x;
  const y = rastro.ry + d.y;
  rastro.vx = x - rastro.x;
  rastro.vy = y - rastro.y;
  rastro.x = x;
  rastro.y = y;
  if (Math.max(Math.abs(d.x), Math.abs(d.y)) > TROCA_REFERENCIA) {
    rastro.referencia = atual;
    rastro.rx = x;
    rastro.ry = y;
  }
}

/** Posição atual da câmera em fração do quadro (o mesmo para qualquer tamanho de imagem). */
const posicaoAtual = () => ({ x: rastro.w ? rastro.x / rastro.w : 0, y: rastro.h ? rastro.y / rastro.h : 0, trecho: rastro.trecho });

/** A cada quadro novo da câmera: segue o movimento, manda o quadro se for a vez e move as caixas. */
function aCadaQuadro() {
  if (!estado.ativo) return;
  const proximo = () => aCadaQuadro();
  if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(proximo);
  else requestAnimationFrame(proximo);
  if (document.hidden) return;
  medidas.camera += 1;
  medidas.vez += 1;
  if (!medidas.pular || medidas.vez % 2 === 0) {
    const t = performance.now();
    rastrear();
    medidas.rastroMs += performance.now() - t;
    medidas.rastros += 1;
  }
  if (!estado.pausado && !envio.http) talvezEnviar();
  moverCamadas();
  enviarMedidas();
}

/** Quadros por segundo a mandar: o dobro do ritmo das análises, mais 2, entre os limites. */
function quadrosPorSegundo() {
  if (!estado.ritmo) return 8;
  return Math.max(QUADROS_POR_S_MIN, Math.min(QUADROS_POR_S_MAX, 2 * estado.ritmo + 2));
}

/** A cada tanto, conta ao computador o que o celular está gastando (para achar onde está lento). */
function enviarMedidas() {
  const agora = performance.now();
  const dt = (agora - medidas.desde) / 1000;
  if (dt * 1000 < MEDIR_A_CADA_MS) return;
  const rastroMs = medidas.rastros ? medidas.rastroMs / medidas.rastros : 0;
  medidas.pular = rastroMs > RASTRO_PESADO_MS;
  const ws = envio.ws;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      tipo: "medidas",
      camera_por_s: +(medidas.camera / dt).toFixed(1),
      enviados_por_s: +(medidas.enviados / dt).toFixed(1),
      alvo_por_s: +quadrosPorSegundo().toFixed(1),
      rastro_ms: +rastroMs.toFixed(1),
      rastro_metade: medidas.pular,
      jpeg_ms: medidas.jpegs ? +(medidas.jpegMs / medidas.jpegs).toFixed(1) : null,
      lado: [video.videoWidth, video.videoHeight],
    }));
  }
  Object.assign(medidas, { desde: agora, camera: 0, enviados: 0, rastroMs: 0, rastros: 0, jpegMs: 0, jpegs: 0 });
}

// ------------------------------------------------------------------ transmissão (WebSocket) e respostas

function conectar() {
  if (!estado.ativo || envio.http) return;
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${BASE}/ws`);
  ws.binaryType = "arraybuffer";
  envio.ws = ws;
  ws.addEventListener("open", () => {
    envio.abriu = true;
    envio.falhas = 0;
    status("", T.procurandoCurto);
  });
  ws.addEventListener("message", (ev) => {
    if (typeof ev.data !== "string") return;
    const r = JSON.parse(ev.data);
    if (r.tipo === "erro") status("erro", r.mensagem);
    else if (!estado.pausado) receber(r);
  });
  ws.addEventListener("close", (ev) => {
    envio.ws = null;
    envio.ocupado = false;
    if (!estado.ativo) return;
    if (ev.code === LINK_VENCIDO) {
      estado.ativo = false;
      status("erro", T.linkVencido);
      return;
    }
    envio.falhas += 1;
    if (!envio.abriu && envio.falhas >= TENTATIVAS_WS) { // a rede não deixa: quadro a quadro por HTTP
      envio.http = true;
      avisar(T.semTransmissao);
      cicloHttp();
      return;
    }
    status("erro", T.semConexao);
    setTimeout(conectar, ESPERA_ERRO_MS);
  });
}

function guardarPosicao(numeroQuadro, posicao) {
  envio.posicoes.set(numeroQuadro, posicao);
  if (envio.posicoes.size > POSICOES_GUARDADAS) envio.posicoes.delete(envio.posicoes.keys().next().value);
}

/** Manda o quadro atual se já deu o intervalo e a rede deu conta do anterior. */
function talvezEnviar() {
  const ws = envio.ws;
  const agora = performance.now();
  if (!ws || ws.readyState !== WebSocket.OPEN || envio.ocupado || agora - envio.ultimo < 1000 / quadrosPorSegundo()) return;
  if (ws.bufferedAmount > FILA_MAXIMA) return;
  envio.ocupado = true;
  envio.ultimo = agora;
  const n = (envio.numero = (envio.numero + 1) >>> 0);
  const posicao = posicaoAtual();
  guardarPosicao(n, posicao);
  quadroAtual(LADO_QUADRO)
    .then((blob) => (blob ? blob.arrayBuffer() : null))
    .then((jpeg) => {
      medidas.jpegMs += performance.now() - agora;
      medidas.jpegs += 1;
      if (!jpeg || ws.readyState !== WebSocket.OPEN) return;
      medidas.enviados += 1;
      const msg = new Uint8Array(CABECALHO + jpeg.byteLength);
      const cab = new DataView(msg.buffer);
      cab.setUint32(0, n, true);
      cab.setUint32(4, posicao.trecho >>> 0, true);
      cab.setFloat32(8, posicao.x, true);
      cab.setFloat32(12, posicao.y, true);
      msg.set(new Uint8Array(jpeg), CABECALHO);
      ws.send(msg);
    })
    .finally(() => { envio.ocupado = false; });
}

/** Sem WebSocket: um quadro por vez, o próximo só quando a resposta do anterior chega. */
async function cicloHttp() {
  while (estado.ativo) {
    if (estado.pausado || document.hidden) {
      await esperar(ESPERA_PAUSA_MS);
      continue;
    }
    const posicao = posicaoAtual();
    const blob = await quadroAtual(LADO_QUADRO);
    if (!blob) {
      await esperar(ESPERA_PAUSA_MS);
      continue;
    }
    try {
      const r = await api("/quadro", { method: "POST", body: blob, headers: { "Content-Type": "image/jpeg" } });
      const n = (envio.numero = (envio.numero + 1) >>> 0);
      guardarPosicao(n, posicao);
      if (!estado.pausado) receber({ ...r, quadro: n });
    } catch (e) {
      status("erro", e instanceof TypeError ? T.semConexao : e.message);
      await esperar(ESPERA_ERRO_MS);
    }
  }
}

function receber(r) {
  estado.ultimas = r.deteccoes;
  estado.area = r.area;
  estado.escala = r.escala || null;
  estado.base = envio.posicoes.get(r.quadro) || null;
  registrarRitmo();
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

/**
 * Quanto as caixas da última análise andaram desde o quadro dela (fração do quadro), ou null se não
 * dá para saber (o rastro se perdeu depois daquele quadro, ou a câmera andou demais).
 */
function deslocamento() {
  const base = estado.base;
  if (!base || estado.fonte !== video) return { x: 0, y: 0 }; // foto, ou resposta sem quadro conhecido
  const agora = posicaoAtual();
  if (agora.trecho !== base.trecho) return null;
  const d = { x: agora.x - base.x, y: agora.y - base.y };
  return Math.hypot(d.x, d.y) > DESLOCAMENTO_MAXIMO ? null : d;
}

/** As camadas das caixas e dos rótulos andam juntas com a câmera (só transform: não pesa). */
function moverCamadas() {
  const area = areaDaImagem();
  const d = deslocamento();
  const visivel = Boolean(area && d);
  const transformar = visivel ? `translate3d(${(d.x * area.w).toFixed(1)}px, ${(d.y * area.h).toFixed(1)}px, 0)` : "";
  for (const camada of [$("#caixas"), $("#rotulos")]) {
    camada.classList.toggle("sumido", !visivel);
    if (visivel) camada.style.transform = transformar;
  }
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

/** Texto do rótulo: o nome e, quando a barra de cores foi lida, a máxima estimada da peça ("≥" no topo da escala). */
const textoDaPeca = (d) => (d.tmax != null ? T.comTemperatura(d.nome, T.temperatura(numero(d.tmax), d.tmax_acima)) : d.nome);

/**
 * Caixas e rótulos da última análise. Ficam no lugar do quadro analisado e as camadas é que andam
 * com a câmera (moverCamadas); os rótulos são arrumados onde as caixas estão agora na tela.
 */
function desenhar() {
  const area = areaDaImagem();
  const d = deslocamento() || { x: 0, y: 0 };
  const lista = area ? estado.ultimas : [];
  const noQuadro = (c) => ({ x: area.x + c[0] * area.w, y: area.y + c[1] * area.h, w: (c[2] - c[0]) * area.w, h: (c[3] - c[1]) * area.h });

  // contorno tracejado do termograma e contorno da barra de cores, quando achada
  for (const [guia, caixa] of [[$("#area"), estado.area], [$("#barra"), estado.escala && estado.escala.barra]]) {
    guia.hidden = !(area && caixa);
    if (guia.hidden) continue;
    const g = noQuadro(caixa);
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
  const dx = area ? d.x * area.w : 0;
  const dy = area ? d.y * area.h : 0;
  const itens = lista.map((det, i) => {
    const c = noQuadro(det.caixa);
    posicionar(caixas[i], c.x, c.y);
    caixas[i].style.width = `${c.w}px`;
    caixas[i].style.height = `${c.h}px`;
    rotulos[i].firstChild.style.background = corDaClasse(det.classe, estado.classes);
    rotulos[i].lastChild.textContent = textoDaPeca(det);
    return { chave: chaves[i], caixa: { ...c, x: c.x + dx, y: c.y + dy }, largura: rotulos[i].offsetWidth, altura: rotulos[i].offsetHeight };
  });
  // Os rótulos ficam entre a barra do topo e a base, sem cobrir uns aos outros (onde as caixas estão agora).
  const W = $("#rotulos").clientWidth;
  const margem = token("--e-1");
  const limites = { x0: margem, y0: $(".cel-topo").offsetHeight + margem, x1: W - margem, y1: $("#base").hidden ? window.innerHeight : $("#base").offsetTop - margem };
  posicionarRotulos(itens, limites, estado.lugares, margem).forEach((p, i) => posicionar(rotulos[i], p.x - dx, p.y - dy));

  moverCamadas();
  desenharLegenda(lista);
}

/** Legenda embaixo: uma etiqueta por peça, de cima para baixo, com a cor do tipo e a confiança. */
function desenharLegenda(lista) {
  const ordenadas = [...lista].sort((a, b) => a.caixa[1] - b.caixa[1]);
  $("#legenda").replaceChildren(...ordenadas.map((d) => {
    const chip = Object.assign(document.createElement("span"), { className: "cel-chip" });
    const ponto = document.createElement("i");
    ponto.style.background = corDaClasse(d.classe, estado.classes);
    chip.append(ponto, textoDaPeca(d), Object.assign(document.createElement("b"), { textContent: T.confianca(Math.round(d.confianca * 100)) }));
    return chip;
  }));
  let texto = "";
  if (estado.pausado) texto = T.pausado;
  else if (!lista.length && estado.tempos.length) texto = estado.area ? T.nadaAchado : T.procurando;
  else if (estado.escala && estado.escala.estado === "lida") texto = T.escalaLida(numero(estado.escala.min), numero(estado.escala.max));
  else if (estado.escala) texto = T.escalaLendo;
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
  if (document.hidden) return;
  perderRastro(); // a câmera pode ter mudado de lugar enquanto a página estava escondida
  if (estado.ativo) manterTelaAcesa();
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
