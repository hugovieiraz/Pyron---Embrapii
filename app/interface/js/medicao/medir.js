// Medição › Medir: medir um objeto qualquer numa foto comum (docs/07_roteiro_medicao_geral.md, fase 5).
// Abrir a foto, clicar no objeto (ou arrastar uma caixa, ou marcar duas pontas) e ver altura, largura, comprimento e
// espessura com a margem de erro; uma referência de tamanho conhecido (o post-it rosa, achado sozinho pela cor) corrige a escala.
// Cada marca mede UMA vez e mostra UM resultado, que a marca seguinte substitui: nada de medida guardada. O servidor mede
// com o modelo padrão (POST /api/medicao/comparar com `modelo`, sem `registrar`, então nada vai para o registro): com a
// referência quando ela vale, senão pela escala do próprio modelo. Contorno do SAM 2.1 e geometria em 3D.
// A foto aberta só fica na faixa de fotos (POST /api/medicao/fotos) para passar de uma para outra; as do celular chegam por ali.
// Sem modelo nenhum (ou sem os pesos instalados), o modo "Retângulo de referência" mede no plano de uma folha
// A4 ou de um cartão: 4 cantos e 2 pontas, por homografia (POST /api/medicao/plano).
import { TEXTOS as T } from "../../textos.js";
import { el, api, fmt, json, lerNumero } from "../base.js";
import { botao, avisar, barraFerramentas, campo, esqueleto, estadoVazio, ocupado, secao } from "../componentes.js";
import { endereco } from "../rotas.js";

const M = T.medir;
const SVG = "http://www.w3.org/2000/svg";
const ORDEM = ["altura", "comprimento", "largura", "espessura", "distancia"];
const QUADROS_VIDEO = 4;  // quadros nítidos medidos por vídeo
const PASSO_TECLADO = 0.01; // mira do teclado: 1 % da foto por seta (Shift: 5 %)
const CAIXA_MINIMA = 0.01;  // arrasto menor que 1 % da foto vale como clique

function svg(tag, attrs = {}) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  return n;
}

export async function montar(no, ctx = {}) {
  const estado = await api("/api/medicao/estado");
  const modeloPadrao = estado.modelo_padrao;
  const nomeModelo = M.colunas[modeloPadrao] || modeloPadrao;

  let foto = null;           // { arquivo, url, largura, altura, codigo }
  let modo = estado.pronto ? "ponto" : "plano"; // ponto | caixa | pontos (com os modelos) | plano (sem modelo)
  let cantos = [];           // modo plano: cantos do retângulo de referência
  let pontoPlano = null;     // modo plano: a primeira ponta da medida
  let medidaPlano = null;    // modo plano: a medida mostrada, { pontos, r }
  let alvo = "objeto";       // objeto | referencia: o que a próxima marca na foto define
  let medida = null;         // a medida mostrada: { pista, r (resposta do servidor; null enquanto mede), video (nº de quadros), comReferencia, seq }
  let pistaRef = null;       // pista da referência
  let primeiroPonto = null;  // modo "pontos": a primeira ponta
  let medindo = false;
  let sequencia = 0;         // cada pedido de medida leva um número; só o mais novo mostra o resultado
  let biblioteca = [];
  let ultimaPista = null;
  let geracao = 0;
  let mira = { x: 0.5, y: 0.5 };
  let cotaDestacada = null;

  // ---------------------------------------------------------------- ferramentas e palco
  const entrada = el("input", { type: "file", accept: "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif", hidden: true, onchange: () => { if (entrada.files[0]) abrir(entrada.files[0]); entrada.value = ""; } });
  const entradaVideo = el("input", { type: "file", accept: "video/*", hidden: true, onchange: () => { if (entradaVideo.files[0]) abrirVideo(entradaVideo.files[0]); entradaVideo.value = ""; } });
  // vídeo aberto: os quadros nítidos que o servidor escolheu; a pista vale no 1º e segue o objeto nos outros
  let video = null;  // { arquivo, quadros: [{ url, tempo_s, largura, altura }], atual }
  const barra = el("div");
  const imagem = el("img", { class: "foto-medir", alt: "", draggable: "false" });
  const camada = svg("svg", { class: "camada-medir", "aria-hidden": "true", preserveAspectRatio: "none" });
  const quadro = el("div", { class: "quadro-medir" }, imagem, camada);
  const hud = el("p", { class: "hud-medir", role: "status" });
  // zoom: a foto cresce dentro de uma janela que rola por dentro; os cliques usam o retângulo da imagem, então
  // continuam no ponto certo. Ctrl + roda (e a pinça do touchpad) aproxima onde está o cursor; botão do meio ou
  // espaço + arrastar movem a foto.
  const janela = el("div", { class: "janela-medir" }, quadro);
  let zoom = 1, baseLargura = 0, espaco = false;
  const rotuloZoom = el("span", { class: "num nota-palco" }, M.zoomPct(100));
  const controlesZoom = el("div", { class: "zoom-medir", role: "group", "aria-label": M.zoom },
    botao({ texto: M.afastar, icone: "menos", soIcone: true, compacto: true, variante: "fantasma", onclick: () => mudarZoom(zoom / 1.5) }),
    rotuloZoom,
    botao({ texto: M.aproximar, icone: "mais", soIcone: true, compacto: true, variante: "fantasma", onclick: () => mudarZoom(zoom * 1.5) }),
    botao({ texto: M.ajustar, icone: "ajustar", soIcone: true, compacto: true, variante: "fantasma", onclick: () => mudarZoom(1) }));
  const palco = el("div", { class: "palco-medir", tabindex: "0", "aria-label": M.palco }, el("div", { class: "topo-palco" }, hud, controlesZoom), janela);

  /** Zoom de 1× (foto inteira) a 8×, mantendo parado o ponto em (cx, cy) da tela (o centro, sem cursor). */
  function mudarZoom(novo, cx, cy) {
    if (!foto) return;
    novo = Math.min(8, Math.max(1, novo));
    if (zoom === 1) baseLargura = quadro.offsetWidth;
    const jr = janela.getBoundingClientRect(), qr = quadro.getBoundingClientRect();
    cx ??= jr.left + jr.width / 2; cy ??= jr.top + jr.height / 2;
    const fx = (cx - qr.left) / qr.width, fy = (cy - qr.top) / qr.height;
    if (zoom === 1) janela.style.height = `${jr.height}px`;  // a janela fica do tamanho da foto inteira
    zoom = novo;
    quadro.style.width = zoom === 1 ? "" : `${baseLargura * zoom}px`;
    if (zoom === 1) janela.style.height = "";
    janela.scrollLeft = quadro.offsetLeft + fx * quadro.offsetWidth - (cx - jr.left);
    janela.scrollTop = quadro.offsetTop + fy * quadro.offsetHeight - (cy - jr.top);
    janela.classList.toggle("ampliada", zoom > 1);
    rotuloZoom.textContent = M.zoomPct(Math.round(zoom * 100));
  }
  janela.addEventListener("wheel", (ev) => {
    if (!ev.ctrlKey || !foto) return;
    ev.preventDefault();
    mudarZoom(zoom * Math.exp(-ev.deltaY * 0.0025), ev.clientX, ev.clientY);
  }, { passive: false });
  let movendo = null;
  janela.addEventListener("pointerdown", (ev) => {
    if (zoom === 1 || !(ev.button === 1 || (ev.button === 0 && espaco))) return;
    ev.preventDefault(); ev.stopPropagation();
    movendo = { x: ev.clientX, y: ev.clientY, l: janela.scrollLeft, t: janela.scrollTop };
    janela.setPointerCapture(ev.pointerId);
    janela.classList.add("movendo");
  }, { capture: true });
  janela.addEventListener("pointermove", (ev) => {
    if (!movendo) return;
    janela.scrollLeft = movendo.l - (ev.clientX - movendo.x);
    janela.scrollTop = movendo.t - (ev.clientY - movendo.y);
  });
  const pararDeMover = () => { movendo = null; janela.classList.remove("movendo"); };
  janela.addEventListener("pointerup", pararDeMover);
  janela.addEventListener("pointercancel", pararDeMover);
  const teclaEspaco = (ev) => { if (ev.code === "Space" && !ev.target.closest?.("input, textarea, button")) espaco = ev.type === "keydown"; };
  addEventListener("keydown", teclaEspaco);
  addEventListener("keyup", teclaEspaco);
  const area = el("div", { class: "coluna-medir" }, palco);
  // faixa das fotos guardadas (as abertas aqui e as do celular), com setas para passar de uma para outra
  let galeria = [];
  const faixa = el("nav", { class: "faixa-fotos", "aria-label": M.faixa });

  // ---------------------------------------------------------------- painel: resultado, referência, detalhes
  const caixaResultado = el("div", { class: "resultado-medir", "aria-live": "polite" });
  const caixaDetalhes = el("div", { class: "detalhes-medir" });
  const refs = Object.entries(estado.referencias || {});
  const autos = Object.entries(estado.referencias_auto || {});
  // só "Nenhuma" e o post-it rosa (achado sozinho pela cor), a referência das fotos de medir; as outras (A4, cartão,
  // marcar à mão) saíram da lista a pedido. Sem o achador de post-it, voltam as prontas.
  const objetoRef = campo({ rotulo: M.objetoReferencia, valor: autos.length ? `auto:${autos[0][0]}` : "", opcoes: [{ valor: "", texto: M.nenhuma },
    ...autos.map(([id, r]) => ({ valor: `auto:${id}`, texto: r.nome })),
    ...(autos.length ? [] : [...refs.map(([id, r]) => ({ valor: id, texto: r.nome })), { valor: "outro", texto: M.outro }])] });
  const ladoRef = campo({ rotulo: M.medidaReferencia, valor: "comprimento", opcoes: Object.entries(M.lados).map(([valor, texto]) => ({ valor, texto })) });
  const tamanhoRef = campo({ rotulo: M.tamanho, tipo: "number", unidade: "cm" });
  const marcarRef = botao({ texto: M.marcarReferencia, icone: "regua", onclick: () => comecarReferencia() });
  const tirarRef = botao({ texto: M.tirarReferencia, variante: "fantasma", compacto: true, onclick: () => { pistaRef = null; desenharReferencia(); remedir(); } });
  const notaRef = el("p", { class: "nota", role: "status" });
  const corpoRef = el("div", { class: "grupo-campos" }, el("p", { class: "nota" }, M.referenciaTexto), objetoRef, ladoRef, tamanhoRef, el("div", { class: "grupo-btn" }, marcarRef, tirarRef), notaRef);
  const retangulos = refs.filter(([, r]) => r.largura != null);
  const retRef = campo({ rotulo: M.retangulo, valor: autos.length ? `auto:${autos[0][0]}` : retangulos[0]?.[0] || "outro", opcoes: [
    ...autos.map(([id, r]) => ({ valor: `auto:${id}`, texto: r.nome })),
    ...(autos.length ? [] : [...retangulos.map(([id, r]) => ({ valor: id, texto: r.nome })), { valor: "outro", texto: M.outro }])] });
  const ladoMaior = campo({ rotulo: M.ladoMaior, tipo: "number", unidade: "cm" });
  const ladoMenor = campo({ rotulo: M.ladoMenor, tipo: "number", unidade: "cm" });
  const acharPostit = botao({ texto: M.acharPostit, icone: "detectar", onclick: () => ocupado(acharPostit, achar) });
  const refazerCantos = botao({ texto: M.refazerCantos, variante: "fantasma", compacto: true, onclick: () => { cantos = []; pontoPlano = null; medidaPlano = null; atualizarTudo(); palco.focus({ preventScroll: true }); } });
  const corpoPlano = el("div", { class: "grupo-campos" }, el("p", { class: "nota" }, M.planoTexto), retRef, ladoMaior, ladoMenor, el("div", { class: "grupo-btn" }, acharPostit, refazerCantos));
  const secaoRef = secao({ titulo: M.referenciaTitulo, conteudo: [corpoRef] });
  const secaoPlano = secao({ titulo: M.planoTitulo, conteudo: [corpoPlano] });
  const avisoModelos = estado.pronto ? null : el("div", { class: "aviso-modelos" }, el("p", { class: "nota" }, M.semModelosNota), el("code", { class: "mono comando-medir" }, M.comandoInstalar),
    el("a", { class: "btn compacto", href: endereco("medicao", ["modelos"]) }, M.abrirModelos));
  const secaoResultado = el("section", {}, el("div", { class: "titulo-bloco" }, el("h2", {}, M.resultado)), caixaResultado);

  // biblioteca de pesos (contexto do vídeo)
  const campoContexto = campo({ rotulo: M.contextoObjeto, valor: "auto", opcoes: [{ valor: "auto", texto: M.contextoAuto }] });
  const btnMedirContexto = botao({ texto: M.medirComContexto, icone: "modelos", variante: "primario", onclick: () => ocupado(btnMedirContexto, medirComContexto) });
  const caixaResultadoContexto = el("div", { class: "resultado-contexto-caixa", "aria-live": "polite" });
  const listaItensContexto = el("div", { class: "lista-biblioteca-contexto" });
  const corpoContexto = el("div", { class: "grupo-campos" },
    el("p", { class: "nota" }, M.contextoTexto),
    campoContexto,
    el("div", { class: "grupo-btn" }, btnMedirContexto),
    caixaResultadoContexto,
    listaItensContexto);
  const secaoContexto = secao({ titulo: M.contextoTitulo, conteudo: [corpoContexto] });

  const caixaCelular = el("div", { class: "celular-medir" });
  const secaoCelular = secao({ titulo: M.celularTitulo, conteudo: [el("p", { class: "nota" }, M.celularTexto), caixaCelular] });
  const painel = el("aside", { class: "painel-medir", "aria-label": M.resultado },
    secaoResultado, secaoContexto, secaoPlano, secaoRef, secaoCelular,
    secao({ titulo: M.detalhes, aberta: false, conteudo: [caixaDetalhes] }),
    avisoModelos);

  const grade = el("div", { class: "medir-grade" }, area, painel);
  no.append(entrada, entradaVideo, barra, grade);

  objetoRef.querySelector("select").addEventListener("change", () => { campoTamanho.value = ""; desenharReferencia(); remedir(); });
  const seletorLado = ladoRef.querySelector("select");
  const campoTamanho = tamanhoRef.querySelector("input");
  seletorLado.addEventListener("change", () => { if (objetoRef.querySelector("select").value !== "outro") desenharReferencia(); remedir(); });
  campoTamanho.addEventListener("change", () => remedir());
  const seletorRet = retRef.querySelector("select");
  const campoMaior = ladoMaior.querySelector("input"), campoMenor = ladoMenor.querySelector("input");
  function desenharRetangulo() {
    const auto = seletorRet.value.startsWith("auto:") ? estado.referencias_auto?.[seletorRet.value.slice(5)] : null;
    const pronto = auto ? { comprimento: auto.lado_cm, largura: auto.lado_cm } : estado.referencias?.[seletorRet.value];
    if (pronto) { campoMaior.value = fmt(pronto.comprimento, 2); campoMenor.value = fmt(pronto.largura, 2); }
    campoMaior.readOnly = campoMenor.readOnly = Boolean(pronto);
  }
  seletorRet.addEventListener("change", () => { desenharRetangulo(); remedirPlano(); });
  campoMaior.addEventListener("change", () => remedirPlano());
  campoMenor.addEventListener("change", () => remedirPlano());
  desenharRetangulo();

  // ---------------------------------------------------------------- desenho
  function desenharBarra() {
    const ferramenta = (id, icone) => ({ texto: M[id], icone, pressionado: modo === id, onclick: () => escolherModo(id),
      indisponivel: !estado.pronto && id !== "plano" ? M.semModelosCurto : foto ? null : M.dicaModo.ponto });
    barra.replaceChildren(barraFerramentas({
      rotulo: M.ferramentas,
      grupos: [[{ texto: foto ? M.trocar : M.abrir, icone: "foto", onclick: () => entrada.click() }, { texto: M.abrirVideo, icone: "video", onclick: () => entradaVideo.click() }],
        [ferramenta("ponto", "ponto"), ferramenta("caixa", "regiao"), ferramenta("pontos", "linha")], [ferramenta("plano", "escala")]],
      direita: [{ texto: M.limpar, icone: "x", indisponivel: foto ? null : M.dicaModo.ponto, onclick: () => limpar() }],
    }));
  }

  function desenharVazio() {
    area.replaceChildren(estadoVazio({ icone: "regua", titulo: M.vazioTitulo, texto: estado.pronto ? M.vazioTexto : M.planoTexto,
      acoes: [botao({ texto: M.abrir, icone: "foto", variante: "primario", onclick: () => entrada.click() })] }), faixa);
    caixaResultado.replaceChildren(el("p", { class: "nota" }, M.semResultado));
    caixaDetalhes.replaceChildren();
  }

  function dica() {
    const s = Math.round((Date.now() - inicioMedida) / 1000);
    if (medindo) return [el("b", {}, video ? M.medindoVideo(s) : M.medindoTempo(s)), " ", el("span", {}, M.medindoNota)];
    if (video && modo !== "plano") return video.atual === 0 ? M.videoDica : M.videoSoPrimeiro;
    if (modo === "plano") return cantos.length < 4 ? M.dicaModo.cantos(cantos.length + 1) : pontoPlano ? M.dicaModo.pontosSegundo : M.dicaModo.plano;
    if (alvo === "referencia") return M.dicaModo.referencia;
    if (modo === "pontos" && primeiroPonto) return M.dicaModo.pontosSegundo;
    return M.dicaModo[modo];
  }
  const atualizarHud = () => {
    quadro.classList.toggle("medindo", medindo);  // faixa de luz varrendo a foto (telas.css)
    hud.replaceChildren(...[dica()].flat());
  };
  // o tempo corre no aviso enquanto mede (a primeira medida na CPU passa de meio minuto)
  let inicioMedida = 0;
  const relogioMedida = setInterval(() => { if (medindo) atualizarHud(); }, 1000);

  /** O que vale numa medida: com a referência quando ela foi usada, senão a escala do próprio modelo. */
  function valorDe(r) {
    const res = r.resultados?.[modeloPadrao] || r.resultados?.contexto || Object.values(r.resultados || {})[0] || {};
    const usada = Boolean(res.com_referencia) && !res.com_referencia.referencia_ignorada;
    return { res, v: (usada ? res.com_referencia : res.sem_referencia) || {}, usada };
  }

  function desenharCamada(rascunho = null) {
    if (!foto) return;
    const { largura: W, altura: H } = foto;
    camada.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const filhos = [];
    const poligonos = (lista, classe) => lista.forEach((p) => {
      const pts = p.map((q) => q.join(",")).join(" ");
      filhos.push(svg("polygon", { points: pts, class: `${classe} sombra` }), svg("polygon", { points: pts, class: classe }));
    });
    function desenharCota(tipo, pts, valorTexto = "", destaque = false) {
      if (!pts || pts.length < 2) return;
      const [[x1, y1], [x2, y2]] = pts;
      const dx = x2 - x1, dy = y2 - y1;
      const len = Math.hypot(dx, dy);
      if (len < 2) return;
      const nx = -dy / len, ny = dx / len;
      const tamTerm = Math.max(W, H) * 0.014;
      const classe = `cota-${tipo}${destaque ? " cota-destaque" : ""}`;

      filhos.push(svg("line", { x1, y1, x2, y2, class: `cota-linha sombra ${classe}` }));
      filhos.push(svg("line", { x1, y1, x2, y2, class: `cota-linha ${classe}` }));

      filhos.push(svg("line", { x1: x1 - nx * tamTerm, y1: y1 - ny * tamTerm, x2: x1 + nx * tamTerm, y2: y1 + ny * tamTerm, class: `cota-terminador sombra ${classe}` }));
      filhos.push(svg("line", { x1: x1 - nx * tamTerm, y1: y1 - ny * tamTerm, x2: x1 + nx * tamTerm, y2: y1 + ny * tamTerm, class: `cota-terminador ${classe}` }));

      filhos.push(svg("line", { x1: x2 - nx * tamTerm, y1: y2 - ny * tamTerm, x2: x2 + nx * tamTerm, y2: y2 + ny * tamTerm, class: `cota-terminador sombra ${classe}` }));
      filhos.push(svg("line", { x1: x2 - nx * tamTerm, y1: y2 - ny * tamTerm, x2: x2 + nx * tamTerm, y2: y2 + ny * tamTerm, class: `cota-terminador ${classe}` }));

      if (valorTexto) {
        const mx = (x1 + x2) / 2 + nx * (tamTerm * 1.6);
        const my = (y1 + y2) / 2 + ny * (tamTerm * 1.6);
        const bw = valorTexto.length * Math.max(W, H) * 0.0075 + 14;
        const bh = Math.max(W, H) * 0.024;
        filhos.push(svg("rect", { x: mx - bw / 2, y: my - bh / 2, width: bw, height: bh, class: "cota-badge-fundo" }));
        const txt = svg("text", { x: mx, y: my, class: "cota-badge-texto" });
        txt.textContent = valorTexto;
        filhos.push(txt);
      }
    }

    const ultima = medida?.r ? medida : null;
    const doQuadro = (m) => (video && m.r?.quadrosVideo ? m.r.quadrosVideo[video.atual] || {} : null);  // vídeo: o que vale no quadro mostrado
    if (ultima && (modo !== "plano" || ultima.r?.resultados?.contexto)) {
      poligonos(doQuadro(ultima) ? [] : ultima.r.contorno_referencia || [], "contorno-ref");
      poligonos(doQuadro(ultima)?.contorno || ultima.r.contorno || [], "contorno-obj");

      const cotas = doQuadro(ultima) ? (video.atual === 0 ? ultima.r.cotas || {} : {}) : ultima.r.cotas || {};
      const { v: v0 } = valorDe(ultima.r);

      if (cotas.apoio && (!cotaDestacada || cotaDestacada === "altura")) {
        const [[ax1, ay1], [ax2, ay2]] = cotas.apoio;
        filhos.push(svg("line", { x1: ax1, y1: ay1, x2: ax2, y2: ay2, class: "cota-apoio sombra" }));
        filhos.push(svg("line", { x1: ax1, y1: ay1, x2: ax2, y2: ay2, class: "cota-apoio" }));
        const txt = svg("text", { x: (ax1 + ax2) / 2, y: ay1 + Math.max(W, H) * 0.02, class: "cota-badge-texto" });
        txt.textContent = "Apoio (base)";
        filhos.push(txt);
      }

      if (cotas.altura && (!cotaDestacada || cotaDestacada === "altura")) {
        const altTxt = v0.altura_cm != null ? `↕ ${fmt(v0.altura_cm, 1)} cm` : "Altura";
        desenharCota("altura", cotas.altura, altTxt, cotaDestacada === "altura");
      }

      if (cotas.comprimento && (!cotaDestacada || cotaDestacada === "comprimento")) {
        const compTxt = v0.comprimento_cm != null ? `↔ ${fmt(v0.comprimento_cm, 1)} cm` : "Comprimento";
        desenharCota("comprimento", cotas.comprimento, compTxt, cotaDestacada === "comprimento");
      }

      if (cotas.largura && (!cotaDestacada || cotaDestacada === "largura")) {
        const largTxt = v0.largura_cm != null ? `⤢ ${fmt(v0.largura_cm, 1)} cm` : "Largura";
        desenharCota("largura", cotas.largura, largTxt, cotaDestacada === "largura");
      }

      if (cotas.distancia && (!cotaDestacada || cotaDestacada === "distancia")) {
        const distTxt = v0.distancia_cm != null ? `${fmt(v0.distancia_cm, 1)} cm` : "Distância";
        desenharCota("distancia", cotas.distancia, distTxt, cotaDestacada === "distancia");
      }

      if (ultima.r.contorno_referencia?.length && (!cotaDestacada || cotaDestacada === "referencia")) {
        const pRef = ultima.r.contorno_referencia[0];
        if (pRef?.length) {
          const rx = pRef.reduce((s, p) => s + p[0], 0) / pRef.length;
          const ry = pRef.reduce((s, p) => s + p[1], 0) / pRef.length;
          const txtRef = svg("text", { x: rx, y: ry, class: "cota-badge-texto" });
          txtRef.textContent = "Ref. 8 cm";
          filhos.push(txtRef);
        }
      }
    }
    const marca = (p, classe) => {
      if (!p) return;
      if (p.ponto) filhos.push(svg("circle", { cx: p.ponto[0], cy: p.ponto[1], r: Math.max(W, H) * 0.008, class: classe }));
      if (p.caixa) { const [x0, y0, x1, y1] = p.caixa; filhos.push(svg("rect", { x: x0, y: y0, width: x1 - x0, height: y1 - y0, class: `${classe} caixa-marca` })); }
      if (p.pontos) {
        const [[x1, y1], [x2, y2]] = p.pontos;
        filhos.push(svg("line", { x1, y1, x2, y2, class: `${classe} sombra` }), svg("line", { x1, y1, x2, y2, class: classe }));
        p.pontos.forEach(([cx, cy]) => filhos.push(svg("circle", { cx, cy, r: Math.max(W, H) * 0.006, class: classe })));
      }
    };
    if (modo === "plano") {
      if (cantos.length >= 2) {
        const pts = cantos.map((q) => q.join(",")).join(" ");
        const tag = cantos.length === 4 ? "polygon" : "polyline";
        filhos.push(svg(tag, { points: pts, class: "marca-ref sombra" }), svg(tag, { points: pts, class: "marca-ref" }));
      }
      cantos.forEach(([cx, cy]) => filhos.push(svg("circle", { cx, cy, r: Math.max(W, H) * 0.006, class: "marca-ref" })));
      if (medidaPlano) marca({ pontos: medidaPlano.pontos }, "marca-obj");
      if (pontoPlano) marca({ ponto: pontoPlano }, "marca-obj");
    } else {
      marca(pistaRef, "marca-ref");
      if (medida) marca(doQuadro(medida)?.pista || (!video || video.atual === 0 ? medida.pista : null), "marca-obj");
      if (primeiroPonto) marca({ ponto: primeiroPonto }, "marca-obj");
    }
    if (rascunho) marca({ caixa: rascunho }, "marca-rascunho");
    if (document.activeElement === palco) filhos.push(svg("circle", { cx: mira.x * W, cy: mira.y * H, r: Math.max(W, H) * 0.012, class: "mira" }));
    camada.replaceChildren(...filhos);
  }

  /** Uma leitura do resultado: nome da grandeza, valor e a margem. */
  function leitura(rotulo, valor, margem, principal = false, aoPassar = null) {
    return el("div", { class: principal ? "leitura-medir principal" : "leitura-medir", onmouseenter: aoPassar && (() => aoPassar(true)), onmouseleave: aoPassar && (() => aoPassar(false)) },
      el("span", { class: "rotulo" }, rotulo), el("b", { class: "num" }, M.valor(fmt(valor, 1))), el("span", { class: "num mais" }, M.mais(fmt(margem, 1))));
  }

  /** A medida da foto, uma só: altura, comprimento… com a margem, o aviso da referência e como foi medido. */
  function desenharResultado() {
    caixaDetalhes.replaceChildren();
    if (modo === "plano") { desenharResultadoPlano(); return; }
    const r = medida?.r;
    if (medida && !r) { caixaResultado.replaceChildren(esqueleto.linhas(2)); return; }
    if (!r || r.resultados?.contexto) { caixaResultado.replaceChildren(el("p", { class: "nota" }, M.semResultado)); return; }  // a do contexto tem o cartão dela
    const { res, v, usada } = valorDe(r);
    const medidas = ORDEM.filter((q) => v[`${q}_cm`] != null);
    const destacar = (q) => (ligado) => { cotaDestacada = ligado ? q : null; desenharCamada(); };
    const notas = [];
    if (usada) notas.push(el("p", { class: "nota" }, M.comReferencia));
    else if (medida.comReferencia) {
      const motivo = res.erro || res.com_referencia?.referencia_ignorada;
      notas.push(el("p", { class: "nota aviso-escala" }, M.refNaoUsada(motivo)), el("p", { class: "nota" }, M.semReferencia));
    } else notas.push(el("p", { class: "nota" }, M.semReferencia));
    if (medida.video) notas.push(el("p", { class: "nota" }, M.notaVideo(medida.video)));
    caixaResultado.replaceChildren(
      el("div", { class: "leituras-medir" }, medidas.map((q) => leitura(M.nomes[q], v[`${q}_cm`], v.incerteza_cm?.[q], medidas.length === 1, destacar(q)))),
      ...notas);
    const detalhes = [];
    if (v.lente) detalhes.push(el("p", {}, M.lente[v.lente] || ""));
    const total = v.tempos_ms?.total;
    detalhes.push(el("p", { class: "nota" }, M.modeloUsado(nomeModelo, total != null ? M.segundos(fmt(total / 1000, 1)) : "")));
    caixaDetalhes.replaceChildren(...detalhes);
  }

  function desenharResultadoPlano() {
    const r = medidaPlano?.r;
    if (medidaPlano && !r) { caixaResultado.replaceChildren(esqueleto.linhas(1)); return; }
    if (!r) { caixaResultado.replaceChildren(el("p", { class: "nota" }, M.semResultado)); return; }
    caixaResultado.replaceChildren(
      el("div", { class: "leituras-medir" }, leitura(r.extrapolacao > 3 ? `${M.nomes.distancia}, ${M.longe}` : M.nomes.distancia, r.distancia_cm, r.incerteza_cm, true)),
      el("p", { class: "nota" }, M.planoMetodo));
  }

  function atualizarTudo() {
    acharPostit.disabled = !foto;
    btnMedirContexto.disabled = !foto;
    desenharBarra();
    desenharResultado();
    atualizarHud();
    desenharCamada();
    secaoPlano.hidden = modo !== "plano";
    secaoRef.hidden = modo === "plano";
  }

  // ---------------------------------------------------------------- biblioteca de pesos (contexto do vídeo)
  async function carregarBiblioteca() {
    try {
      const bib = await api("/api/medicao/biblioteca").catch(() => ({ itens: [] }));
      biblioteca = bib.itens || [];
    } catch {
      biblioteca = [];
    }
    atualizarOpcoesContexto();
    desenharResumoContexto();
  }

  function atualizarOpcoesContexto() {
    const select = campoContexto.querySelector("select");
    if (!select) return;
    const atual = select.value;
    const opcoes = [
      { valor: "auto", texto: M.contextoAuto },
      ...biblioteca.map((i) => ({
        valor: String(i.id),
        texto: `${i.nome} (${fmt(i.dimensoes_cm?.altura, 1)} cm)`,
      })),
    ];
    select.replaceChildren(...opcoes.map((o) => new Option(o.texto, o.valor)));
    if (opcoes.some((o) => o.valor === atual)) select.value = atual;
    else select.value = "auto";
  }

  function desenharResumoContexto() {
    btnMedirContexto.disabled = !foto;
    if (!biblioteca.length) {
      listaItensContexto.replaceChildren(el("p", { class: "nota" }, M.semBiblioteca));
      return;
    }
    listaItensContexto.replaceChildren(
      el("p", { class: "nota" }, M.bibliotecaItens(biblioteca.length)),
      el("ul", { class: "itens-contexto" }, biblioteca.map((item) => {
        const h = item.dimensoes_cm?.altura;
        const w = item.dimensoes_cm?.largura;
        const dimTxt = h != null && w != null ? `${fmt(h, 1)} × ${fmt(w, 1)} cm` : h != null ? `${fmt(h, 1)} cm` : "";
        const btnApagar = botao({
          texto: M.apagarContexto(item.nome),
          icone: "lixo",
          soIcone: true,
          compacto: true,
          variante: "fantasma",
          onclick: async () => {
            try {
              await api(`/api/medicao/biblioteca/${item.id}`, { method: "DELETE" });
              avisar(M.contextoApagado);
              await carregarBiblioteca();
            } catch (e) {
              avisar(e.message, { erro: true });
            }
          },
        });
        return el("li", { class: "item-contexto-linha" },
          el("div", { class: "info" },
            el("b", { class: "corta" }, item.nome),
            el("span", { class: "sub" }, [item.classe, dimTxt].filter(Boolean).join(" · "))
          ),
          btnApagar
        );
      }))
    );
  }

  async function medirComContexto() {
    if (!foto) {
      entrada.click();
      return;
    }
    const idContexto = campoContexto.querySelector("select")?.value;
    const pista = ultimaPista || { ponto: [Math.round(mira.x * foto.largura), Math.round(mira.y * foto.altura)] };
    const dados = new FormData();
    dados.append("arquivo", foto.arquivo);
    dados.append("pista", JSON.stringify(pista));
    if (idContexto && idContexto !== "auto") {
      dados.append("id_contexto", idContexto);
    }

    medindo = true;
    inicioMedida = Date.now();
    atualizarHud();
    try {
      const res = await api("/api/medicao/contexto-2d", { method: "POST", body: dados });
      processarResultadoContexto(res, pista);
    } catch (e) {
      avisar(`${M.erroMedir} ${e.message}`, { erro: true });
    } finally {
      medindo = false;
      atualizarTudo();
    }
  }

  function processarResultadoContexto(res, pista) {
    const extrairValor = (v) => (typeof v === "object" && v !== null ? v.valor ?? v.altura_cm ?? v.largura_cm ?? v.comprimento_cm ?? null : typeof v === "number" ? v : null);
    const extrairIncerteza = (v) => (typeof v === "object" && v !== null ? v.incerteza ?? null : null);

    const altVal = extrairValor(res.altura);
    const largVal = extrairValor(res.largura);
    const compVal = extrairValor(res.comprimento);
    const altInc = extrairIncerteza(res.altura) ?? (altVal ? altVal * 0.05 : null);
    const largInc = extrairIncerteza(res.largura) ?? (largVal ? largVal * 0.05 : null);
    const compInc = extrairIncerteza(res.comprimento) ?? (compVal ? compVal * 0.05 : null);

    sequencia++;  // a medida em andamento, se houver, não aparece mais
    medida = {
      pista,
      video: 0,
      r: {
        resultados: {
          contexto: {
            sem_referencia: {
              altura_cm: altVal,
              largura_cm: largVal,
              comprimento_cm: compVal,
              incerteza_cm: {
                altura: altInc,
                largura: largInc,
                comprimento: compInc,
              },
              lente: "estimada",
            },
          },
        },
        contorno: res.contorno || [],
        contorno_referencia: [],
        cotas: res.cotas || {},
      },
    };
    desenharResultadoContextoDestaque(res, altVal, largVal, compVal, altInc, largInc, compInc);
  }

  function desenharResultadoContextoDestaque(res, altVal, largVal, compVal, altInc, largInc, compInc) {
    const ctx = res.contexto || {};
    const conf = ctx.confianca != null ? Math.round(ctx.confianca * 100) : null;
    const nome = ctx.nome || ctx.classe || M.resultado;

    const itensMedida = [];
    if (altVal != null) {
      itensMedida.push(el("div", { class: "item-medida" },
        el("span", { class: "rotulo" }, M.nomes.altura),
        el("b", { class: "valor" }, `${fmt(altVal, 1)} cm`),
        altInc != null ? el("span", { class: "nota mais" }, M.mais(fmt(altInc, 1))) : null
      ));
    }
    if (largVal != null) {
      itensMedida.push(el("div", { class: "item-medida" },
        el("span", { class: "rotulo" }, M.nomes.largura),
        el("b", { class: "valor" }, `${fmt(largVal, 1)} cm`),
        largInc != null ? el("span", { class: "nota mais" }, M.mais(fmt(largInc, 1))) : null
      ));
    }
    if (compVal != null) {
      itensMedida.push(el("div", { class: "item-medida" },
        el("span", { class: "rotulo" }, M.nomes.comprimento),
        el("b", { class: "valor" }, `${fmt(compVal, 1)} cm`),
        compInc != null ? el("span", { class: "nota mais" }, M.mais(fmt(compInc, 1))) : null
      ));
    }

    const metas = [];
    if (res.escala_cm_px != null) metas.push(el("span", {}, M.escalaContexto(fmt(res.escala_cm_px, 4))));
    if (res.angulo_inclinacao_graus != null) metas.push(el("span", {}, M.inclinacaoCompensada(fmt(res.angulo_inclinacao_graus, 1))));
    if (res.area_cm2 != null) metas.push(el("span", {}, M.areaCm2(fmt(res.area_cm2, 1))));

    caixaResultadoContexto.replaceChildren(
      el("div", { class: "resultado-contexto-card" },
        el("div", { class: "topo-res" },
          el("b", { class: "corta" }, conf != null ? M.objetoReconhecido(nome, conf) : nome),
          el("span", { class: "selo normal" }, M.contextoTitulo)
        ),
        el("div", { class: "medidas-grade" }, itensMedida),
        metas.length ? el("div", { class: "metas-contexto" }, metas) : null
      )
    );
  }

  function tamanhoPlano() {
    const a = lerNumero(campoMaior.value), b = lerNumero(campoMenor.value);
    return a > 0 && b > 0 ? [a, b] : null;
  }

  async function medirPlano(m) {
    const tamanho = tamanhoPlano();
    if (!tamanho) { avisar(M.planoSemTamanho, { erro: true }); return false; }
    try {
      m.r = await api("/api/medicao/plano", json("POST", { cantos, tamanho_cm: tamanho, pontos: m.pontos }));
      return true;
    } catch (e) {
      avisar(`${M.erroMedir} ${e.message}`, { erro: true });
      return false;
    }
  }

  async function achar() {
    if (!foto) return;
    const escolha = seletorRet.value.startsWith("auto:") ? seletorRet.value.slice(5) : (Object.keys(estado.referencias_auto || {})[0] || "postit_rosa");
    const dados = new FormData();
    dados.append("arquivo", foto.arquivo);
    dados.append("tipo", escolha);
    try {
      const r = await api("/api/medicao/referencia", { method: "POST", body: dados });
      cantos = r.cantos;
      pontoPlano = null;
      if (!seletorRet.value.startsWith("auto:")) { seletorRet.value = `auto:${escolha}`; desenharRetangulo(); }
      await remedirPlano();
      atualizarTudo();
      avisar(M.postitAchado);
    } catch (e) {
      avisar(e.message, { erro: true });
    }
  }

  async function remedirPlano() {
    if (medidaPlano?.r) await medirPlano(medidaPlano);
    desenharResultado();
  }

  async function clicarPlano(p) {
    if (cantos.length < 4) { cantos.push(p); atualizarHud(); desenharCamada(); return; }
    if (!pontoPlano) { pontoPlano = p; atualizarHud(); desenharCamada(); return; }
    const m = { pontos: [pontoPlano, p], r: null };
    pontoPlano = null;
    medidaPlano = m;  // a medida nova substitui a anterior
    atualizarTudo();
    const ok = await medirPlano(m);
    if (medidaPlano !== m) return;  // outra marca veio no meio
    if (!ok) medidaPlano = null;
    atualizarTudo();
  }

  function desenharReferencia() {
    const escolha = objetoRef.querySelector("select").value;
    const auto = escolha.startsWith("auto:") ? estado.referencias_auto?.[escolha.slice(5)] : null;
    const pronta = estado.referencias?.[escolha];
    ladoRef.hidden = !escolha || Boolean(auto) || (pronta && pronta.largura == null);
    tamanhoRef.hidden = escolha !== "outro" && !auto;
    if (auto && !lerNumero(campoTamanho.value)) campoTamanho.value = fmt(auto.lado_cm, 1);
    if (pronta) campoTamanho.value = fmt(pronta[seletorLado.value === "largura" && pronta.largura != null ? "largura" : "comprimento"], 2);
    marcarRef.hidden = Boolean(auto);
    marcarRef.disabled = !escolha || !foto;
    tirarRef.hidden = !pistaRef;
    notaRef.textContent = pistaRef ? M.referenciaMarcada : "";
    desenharCamada();
  }

  function referencia() {
    const escolha = objetoRef.querySelector("select").value;
    if (escolha.startsWith("auto:")) {
      const tamanho = lerNumero(campoTamanho.value);
      return { auto: escolha.slice(5), ...(tamanho > 0 ? { tamanho_cm: tamanho } : {}) };
    }
    if (!pistaRef || !escolha) return null;
    const pronta = estado.referencias?.[escolha];
    const lado = pronta && pronta.largura == null ? "comprimento" : seletorLado.value;
    const tamanho = pronta ? pronta[lado === "largura" ? "largura" : "comprimento"] : lerNumero(campoTamanho.value);
    if (!(tamanho > 0)) return null;
    return { ...pistaRef, tamanho_cm: tamanho, medida: lado, nome: pronta ? pronta.nome : "" };
  }

  // ---------------------------------------------------------------- ações
  /** Abre a foto, sem nenhuma marca de medida. O navegador não mostra HEIC: aí o servidor devolve um JPEG do mesmo
   * tamanho só para a tela (as medidas usam sempre o arquivo original, com os metadados). */
  function abrir(arquivo, previa = null, { comoVideo = false } = {}) {
    if (foto) URL.revokeObjectURL(foto.url);
    const url = URL.createObjectURL(previa || arquivo);
    const img = new Image();
    img.onload = () => {
      if (!comoVideo) video = null;
      foto = { arquivo, url, largura: img.naturalWidth, altura: img.naturalHeight, codigo: arquivo.codigo || null };
      pistaRef = primeiroPonto = pontoPlano = null;
      cantos = []; medidaPlano = null; medida = null;
      alvo = "objeto";
      ultimaPista = null;
      caixaResultadoContexto.replaceChildren();
      geracao++; medindo = false;  // a medida da foto anterior não aparece nesta
      imagem.src = url;
      zoom = 1; quadro.style.width = ""; janela.style.height = ""; janela.classList.remove("ampliada"); rotuloZoom.textContent = M.zoomPct(100);
      quadro.style.setProperty("--proporcao", String(foto.largura / foto.altura));
      area.replaceChildren(palco, faixa);
      desenharReferencia(); atualizarTudo();
      palco.focus({ preventScroll: true });
      if (comoVideo || foto.codigo) desenharFaixa(); else guardarNaFaixa(arquivo);
    };
    img.onerror = async () => {
      URL.revokeObjectURL(url);
      if (previa) { avisar(M.erroMedir, { erro: true }); return; }
      try {
        const dados = new FormData();
        dados.append("arquivo", arquivo);
        const r = await fetch("/api/medicao/previa", { method: "POST", body: dados });
        if (!r.ok) throw new Error(M.erroMedir);
        abrir(arquivo, await r.blob());
      } catch (e) { avisar(e.message, { erro: true }); }
    };
    img.src = url;
  }

  function escolherModo(id) {
    modo = id;
    primeiroPonto = pontoPlano = null;
    alvo = "objeto";
    atualizarTudo();
  }

  function limpar() {
    pistaRef = primeiroPonto = pontoPlano = null;
    cantos = []; medidaPlano = null; medida = null;
    alvo = "objeto";
    ultimaPista = null;
    caixaResultadoContexto.replaceChildren();
    geracao++;
    medindo = false;
    desenharReferencia(); atualizarTudo();
  }

  function comecarReferencia() {
    alvo = "referencia";
    primeiroPonto = null;
    atualizarHud();
    palco.focus({ preventScroll: true });
  }

  /** Uma marca na foto (coordenadas da imagem): vira a pista do objeto ou da referência. */
  function marcar(p) {
    if (alvo !== "referencia") ultimaPista = p;
    if (alvo === "referencia") {
      pistaRef = p;
      alvo = "objeto";
      desenharReferencia();
      atualizarHud();
      if (!referencia()) { avisar(M.semTamanho, { erro: true }); return; }
      remedir();
      return;
    }
    if (video && video.atual !== 0) { avisar(M.videoSoPrimeiro); mostrarQuadro(0); return; }
    caixaResultadoContexto.replaceChildren();
    medida = { pista: p, r: null, video: video ? video.quadros.length : 0, comReferencia: false, seq: 0 };
    medir(medida);
  }

  /** A referência mudou: a medida da foto sai de novo (e continua uma só). */
  function remedir() { if (medida?.seq) { medida.r = null; medir(medida); } }  // a do contexto não tem `seq`: não depende da referência

  // um pedido por vez no servidor; se outra marca chega antes, o pedido velho nem sai
  let fila = Promise.resolve();
  function medir(m) {
    const minha = geracao;
    const seq = m.seq = ++sequencia;
    const vale = () => minha === geracao && m.seq === seq;
    if (!medindo) inicioMedida = Date.now();
    medindo = true;
    desenharResultado(); atualizarHud(); desenharCamada();
    fila = fila.then(async () => {
      if (!vale()) return;
      const dados = new FormData();
      dados.append("arquivo", m.video ? video.arquivo : foto.arquivo);
      dados.append("pista", JSON.stringify(m.pista));
      const ref = referencia();
      m.comReferencia = Boolean(ref);
      if (ref) dados.append("referencia", JSON.stringify(ref));
      dados.append("modelo", modeloPadrao);  // só o modelo padrão; o servidor não guarda nada sem o pedido explícito
      if (m.video) dados.append("max_keyframes", String(QUADROS_VIDEO));
      try {
        const r = await api(m.video ? "/api/medicao/video/comparar" : "/api/medicao/comparar", { method: "POST", body: dados });
        if (!vale()) return;
        m.r = m.video ? deVideo(r) : r;
      } catch (e) {
        if (!vale()) return;
        if (medida === m) medida = null;
        avisar(`${M.erroMedir} ${e.message}`, { erro: true });
      } finally {
        if (vale()) { medindo = false; desenharResultado(); atualizarHud(); desenharCamada(); }
      }
    });
  }

  // ---------------------------------------------------------------- mouse, toque e teclado
  const naImagem = (ev) => {
    const b = imagem.getBoundingClientRect();
    const fx = Math.min(1, Math.max(0, (ev.clientX - b.left) / b.width));
    const fy = Math.min(1, Math.max(0, (ev.clientY - b.top) / b.height));
    return { fx, fy, x: fx * foto.largura, y: fy * foto.altura };
  };
  let arrasto = null;
  quadro.addEventListener("pointerdown", (ev) => {
    if (!foto || ev.button !== 0 || espaco) return;
    ev.preventDefault();
    arrasto = { inicio: naImagem(ev), id: ev.pointerId };
    quadro.setPointerCapture(ev.pointerId);
  });
  quadro.addEventListener("pointermove", (ev) => {
    if (!arrasto || modo !== "caixa") return;
    const a = arrasto.inicio, b = naImagem(ev);
    desenharCamada([Math.min(a.x, b.x), Math.min(a.y, b.y), Math.max(a.x, b.x), Math.max(a.y, b.y)]);
  });
  quadro.addEventListener("pointerup", (ev) => {
    if (!arrasto) return;
    const a = arrasto.inicio, b = naImagem(ev);
    arrasto = null;
    mira = { x: b.fx, y: b.fy };
    if (modo === "caixa" && Math.abs(b.fx - a.fx) > CAIXA_MINIMA && Math.abs(b.fy - a.fy) > CAIXA_MINIMA) {
      marcar({ caixa: [Math.min(a.x, b.x), Math.min(a.y, b.y), Math.max(a.x, b.x), Math.max(a.y, b.y)].map(Math.round) });
    } else clicar(b.x, b.y);
  });
  quadro.addEventListener("pointercancel", () => { arrasto = null; desenharCamada(); });

  function clicar(x, y) {
    const p = [Math.round(x), Math.round(y)];
    if (modo === "plano") { clicarPlano(p); return; }
    if (modo === "pontos" && alvo === "objeto") {
      if (!primeiroPonto) { primeiroPonto = p; atualizarHud(); desenharCamada(); return; }
      const par = [primeiroPonto, p];
      primeiroPonto = null;
      marcar({ pontos: par });
      return;
    }
    marcar({ ponto: p });
  }

  palco.addEventListener("keydown", (ev) => {
    if (!foto) return;
    const passo = ev.shiftKey ? PASSO_TECLADO * 5 : PASSO_TECLADO;
    const d = { ArrowLeft: [-passo, 0], ArrowRight: [passo, 0], ArrowUp: [0, -passo], ArrowDown: [0, passo] }[ev.key];
    if (d) {
      ev.preventDefault();
      mira = { x: Math.min(1, Math.max(0, mira.x + d[0])), y: Math.min(1, Math.max(0, mira.y + d[1])) };
      desenharCamada();
    } else if (ev.key === "+" || ev.key === "=" || ev.key === "-" || ev.key === "0") {
      ev.preventDefault();
      mudarZoom(ev.key === "0" ? 1 : ev.key === "-" ? zoom / 1.5 : zoom * 1.5);
    } else if (ev.key === "Enter" || (ev.key === " " && zoom === 1)) {
      ev.preventDefault();
      clicar(mira.x * foto.largura, mira.y * foto.altura);
    } else if (ev.key === "Escape" && (primeiroPonto || pontoPlano || alvo === "referencia")) {
      primeiroPonto = pontoPlano = null; alvo = "objeto"; atualizarHud(); desenharCamada();
    }
  });
  palco.addEventListener("focus", () => desenharCamada());
  palco.addEventListener("blur", () => desenharCamada());

  // ---------------------------------------------------------------- celular: a foto que chega abre sozinha
  let celular = { versao: -1, fotos: [] };
  let vistas = null;  // fotos e vídeos do celular que já estavam lá ao abrir a aba (não abrem sozinhos)
  let vistasVideo = false;

  function desenharCelular() {
    if (!celular.ligado) {
      const ligar = botao({ texto: M.ligarCelular, icone: "celular", variante: "secundario", onclick: () => ocupado(ligar, async () => {
        try { await api("/api/celular/ligar?para=medicao", { method: "POST" }); await vigiarCelular(); } catch (e) { avisar(e.message, { erro: true }); }
      }) });
      caixaCelular.replaceChildren(el("div", { class: "grupo-btn" }, ligar));
      return;
    }
    caixaCelular.replaceChildren(
      el("img", { class: "qr-medir", src: `/api/celular/qr.png?medir=1&v=${encodeURIComponent(celular.url)}`, alt: M.celularQrAlt }),
      el("code", { class: "mono corta" }, celular.url),
      el("p", { class: "nota" }, M.celularQr),
      el("p", { class: "nota" }, M.fotosCelular));
  }

  /** Abre uma foto guardada (da faixa ou do celular): só a foto, sem medida nenhuma. */
  async function abrirDoCelular(codigo) {
    const r = await fetch(`/api/medicao/fotos/${codigo}`);
    if (!r.ok) { avisar(M.erroMedir, { erro: true }); return; }
    const blob = await r.blob();
    const arquivo = new File([blob], codigo, { type: blob.type });
    arquivo.codigo = codigo;
    abrir(arquivo);
  }

  async function vigiarCelular() {
    try {
      const est = await api("/api/medicao/celular");
      const mudou = est.versao !== celular.versao || est.ligado !== celular.ligado;
      celular = est;
      if (vistas == null) vistas = new Set([...est.fotos, ...(est.videos || [])].map((f) => f.id));
      if (!mudou) return;
      desenharCelular();
      carregarFaixa();
      for (const v of (est.videos || []).filter((x) => !vistas.has(x.id))) {
        vistas.add(v.id);
        if (vistasVideo) { await abrirVideoGuardado(v.id); avisar(M.videoNovoCelular); }
      }
      vistasVideo = true;
      const nova = est.fotos.find((f) => !vistas.has(f.id));
      if (nova) {
        vistas.add(nova.id);
        if (foto?.codigo !== nova.id) { await abrirDoCelular(nova.id); avisar(M.fotoNovaCelular); }
      }
    } catch { /* a faixa de conexão já avisa */ }
  }
  const relogioCelular = setInterval(vigiarCelular, 2000);

  desenharReferencia();
  carregarBiblioteca();
  atualizarTudo();
  desenharVazio();
  vigiarCelular();
  // outra foto: arrastar para a aba ou colar (Ctrl+V), além do botão
  const fotoDe = (lista) => [...(lista || [])].find((f) => f.type.startsWith("image/") || /\.(heic|heif)$/i.test(f.name));
  const videoDe = (lista) => [...(lista || [])].find((f) => f.type.startsWith("video/"));
  const arrastando = (ev) => { if (![...(ev.dataTransfer?.types || [])].includes("Files")) return; ev.preventDefault(); no.classList.add("soltar-foto"); };
  const saiu = (ev) => { if (!no.contains(ev.relatedTarget)) no.classList.remove("soltar-foto"); };
  const soltou = (ev) => {
    no.classList.remove("soltar-foto");
    const f = fotoDe(ev.dataTransfer?.files), v = videoDe(ev.dataTransfer?.files);
    if (!f && !v) return;
    ev.preventDefault();
    if (v && !f) abrirVideo(v); else abrir(f);
  };
  const colou = (ev) => {
    if (ev.target.closest?.("input, textarea")) return;
    const f = fotoDe(ev.clipboardData?.files);
    if (f) { ev.preventDefault(); abrir(f); }
  };
  no.dataset.soltar = M.soltar;
  no.addEventListener("dragover", arrastando);
  no.addEventListener("dragleave", saiu);
  no.addEventListener("drop", soltou);
  document.addEventListener("paste", colou);

  // ---------------------------------------------------------------- faixa de fotos
  const hora = (t) => new Date(t * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

  async function carregarFaixa() {
    try { galeria = (await api("/api/medicao/fotos?limite=60")).fotos.reverse(); } catch { return; }  // da mais antiga (esquerda) à mais nova
    desenharFaixa();
  }

  /** Foto aberta do computador: guarda os bytes originais no Pyron para ela ficar na faixa (e o código evita reenviar). */
  async function guardarNaFaixa(arquivo) {
    const dados = new FormData();
    dados.append("arquivo", arquivo);
    try {
      const { codigo } = await api("/api/medicao/fotos", { method: "POST", body: dados });
      arquivo.codigo = codigo;
      if (foto?.arquivo === arquivo) foto.codigo = codigo;
      await carregarFaixa();
    } catch { /* fica só nesta sessão */ }
  }

  function desenharFaixa() {
    if (video) { desenharFaixaVideo(); return; }
    faixa.hidden = !galeria.length;
    if (!galeria.length) return;
    const i = galeria.findIndex((f) => f.codigo === foto?.codigo);
    const ir = (j) => { if (galeria[j]) abrirDoCelular(galeria[j].codigo); };
    const miniaturas = galeria.map((f, j) => el("button", { type: "button", class: "mini-faixa", "aria-current": j === i ? "true" : null,
      "aria-label": M.fotoDaFaixa(j + 1, galeria.length, hora(f.quando)), title: hora(f.quando), onclick: () => ir(j) },
      el("img", { src: `/api/medicao/fotos/${f.codigo}/miniatura`, alt: "", loading: "lazy", decoding: "async" })));
    const lista = el("div", { class: "trilho-faixa" }, miniaturas);
    faixa.replaceChildren(
      botao({ texto: M.fotoAnterior, icone: "anterior", soIcone: true, desabilitado: i <= 0, onclick: () => ir(i - 1) }),
      lista,
      botao({ texto: M.fotoSeguinte, icone: "proxima", soIcone: true, desabilitado: i < 0 ? galeria.length < 1 : i >= galeria.length - 1, onclick: () => ir(i < 0 ? 0 : i + 1) }),
      el("span", { class: "nota num" }, i >= 0 ? M.posicaoFaixa(i + 1, galeria.length) : ""));
    if (miniaturas[i]) requestAnimationFrame(() => { lista.scrollLeft = miniaturas[i].offsetLeft - (lista.clientWidth - miniaturas[i].offsetWidth) / 2; });  // só a faixa rola, não a página
  }
  // ---------------------------------------------------------------- vídeo
  /** O servidor escolhe os quadros nítidos e espaçados; o 1º abre no palco e os outros vão para a faixa. */
  async function abrirVideo(arquivo) {
    limpar();
    area.replaceChildren(palco, faixa);
    hud.replaceChildren(el("b", {}, M.escolhendoQuadros));
    quadro.classList.add("medindo");
    const dados = new FormData();
    dados.append("arquivo", arquivo);
    dados.append("max_keyframes", String(QUADROS_VIDEO));
    let r;
    try { r = await api("/api/medicao/video/keyframes", { method: "POST", body: dados }); }
    catch (e) { quadro.classList.remove("medindo"); avisar(e.message, { erro: true }); if (!foto) desenharVazio(); return; }
    quadro.classList.remove("medindo");
    if (!r.keyframes.length) { avisar(M.videoSemQuadros, { erro: true }); if (!foto) desenharVazio(); return; }
    video?.quadros.forEach((q) => URL.revokeObjectURL(q.url));
    const quadros = await Promise.all(r.keyframes.map(async (k) => ({ ...k, url: URL.createObjectURL(await (await fetch(k.imagem_base64)).blob()) })));
    video = { arquivo, quadros, atual: 0 };
    const primeiro = await (await fetch(quadros[0].url)).blob();
    abrir(new File([primeiro], "quadro-1.jpg", { type: "image/jpeg" }), null, { comoVideo: true });
  }

  async function abrirVideoGuardado(codigo) {
    const r = await fetch(`/api/medicao/videos/${codigo}`);
    if (!r.ok) { avisar(M.erroMedir, { erro: true }); return; }
    const blob = await r.blob();
    abrirVideo(new File([blob], `${codigo}.mp4`, { type: blob.type || "video/mp4" }));
  }

  /** Mostra outro quadro do vídeo sem perder a medida: a pista e o contorno daquele quadro aparecem nele. */
  function mostrarQuadro(j) {
    if (!video?.quadros[j]) return;
    video.atual = j;
    imagem.src = video.quadros[j].url;
    atualizarHud(); desenharCamada(); desenharFaixa();
  }

  function desenharFaixaVideo() {
    faixa.hidden = false;
    const { quadros, atual } = video;
    const miniaturas = quadros.map((q, j) => el("button", { type: "button", class: "mini-faixa", "aria-current": j === atual ? "true" : null,
      "aria-label": M.quadroDaFaixa(j + 1, quadros.length, fmt(q.tempo_s, 1)), title: M.quadroCurto(fmt(q.tempo_s, 1)), onclick: () => mostrarQuadro(j) },
      el("img", { src: q.url, alt: "" })));
    faixa.replaceChildren(
      botao({ texto: M.fotoAnterior, icone: "anterior", soIcone: true, desabilitado: atual <= 0, onclick: () => mostrarQuadro(atual - 1) }),
      el("div", { class: "trilho-faixa" }, miniaturas),
      botao({ texto: M.fotoSeguinte, icone: "proxima", soIcone: true, desabilitado: atual >= quadros.length - 1, onclick: () => mostrarQuadro(atual + 1) }),
      el("span", { class: "nota num" }, M.posicaoFaixa(atual + 1, quadros.length)));
  }

  /** A resposta do vídeo no formato da foto: a mediana de cada modelo e modo, o ± é o desvio entre os quadros. */
  function deVideo(r) {
    const q0 = r.quadros.find((q) => q.resultados) || {};
    const resultados = {};
    for (const [modelo, modos] of Object.entries(r.consenso)) {
      resultados[modelo] = { sem_referencia: null, com_referencia: null, erro: q0.resultados?.[modelo]?.erro };
      for (const [modoR, c] of Object.entries(modos)) {
        const v = { incerteza_cm: {} };
        for (const [campo, x] of Object.entries(c)) {
          if (x && typeof x === "object") { v[campo] = x.valor; v.incerteza_cm[campo.replace(/_cm$/, "")] = x.desvio_padrao; }
        }
        if (modoR === "com_referencia") v.referencia_ignorada = q0.resultados?.[modelo]?.com_referencia?.referencia_ignorada || "";
        resultados[modelo][modoR] = v;
      }
    }
    const cotas = Object.values(q0.resultados || {}).find((x) => x?.sem_referencia)?.sem_referencia?.cotas || {};
    return { ...r, resultados, cotas, contorno: q0.contorno || [], contorno_referencia: [],
      quadrosVideo: r.quadros.map((q) => ({ pista: q.pista, contorno: q.contorno || [] })) };
  }

  carregarFaixa();
  // um endereço #medicao/medir/<código> abre essa foto guardada
  const pedida = ctx.partes?.[0];
  if (pedida && /^[0-9a-f]+$/i.test(pedida)) abrirDoCelular(pedida);

  return () => {
    geracao++; clearInterval(relogioCelular); clearInterval(relogioMedida);
    document.removeEventListener("paste", colou);
    removeEventListener("keydown", teclaEspaco); removeEventListener("keyup", teclaEspaco);
    if (foto) URL.revokeObjectURL(foto.url);
    video?.quadros.forEach((q) => URL.revokeObjectURL(q.url));
  };
}
