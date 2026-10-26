// Captura › Medir foto (docs/07_roteiro_medicao_geral.md, fase 5): medir um objeto qualquer numa foto comum.
// Abrir a foto, clicar no objeto (ou arrastar uma caixa, ou marcar duas pontas) e ver altura, largura e
// comprimento com a margem de erro; uma referência de tamanho conhecido na foto corrige a escala.
// O servidor faz tudo (POST /api/medicao/comparar): cada medida sai nos dois modelos de profundidade (Depth Anything 3
// e MoGe-2), sem e com a referência, lado a lado; com o valor real informado, o registro guarda o erro de cada um
// (GET /api/medicao/registro). Contorno do SAM 2.1 e geometria em 3D.
// Sem modelo nenhum (ou sem os pesos instalados), o modo "Retângulo de referência" mede no plano de uma folha
// A4 ou de um cartão: 4 cantos e 2 pontas, por homografia (POST /api/medicao/plano).
import { TEXTOS as T } from "../../textos.js";
import { el, api, fmt, json, lerNumero } from "../base.js";
import { botao, avisar, barraFerramentas, campo, esqueleto, estadoVazio, ocupado, secao, segmentado } from "../componentes.js";
import { endereco } from "../rotas.js";

const M = T.medir;
const SVG = "http://www.w3.org/2000/svg";
const ORDEM = ["altura", "comprimento", "largura", "espessura", "distancia"];
const PASSO_TECLADO = 0.01; // mira do teclado: 1 % da foto por seta (Shift: 5 %)
const CAIXA_MINIMA = 0.01;  // arrasto menor que 1 % da foto vale como clique

function svg(tag, attrs = {}) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  return n;
}

export async function montar(no, ctx = {}) {
  const estado = await api("/api/medicao/estado");

  let foto = null;           // { arquivo, url, largura, altura }
  let modo = estado.pronto ? "ponto" : "plano"; // ponto | caixa | pontos (com os modelos) | plano (sem modelo)
  let cantos = [];           // modo plano: cantos do retângulo de referência
  let pontoPlano = null;     // modo plano: a primeira ponta da medida
  let medidasPlano = [];     // modo plano: [{ pontos, r }]
  let alvo = "objeto";       // objeto | referencia: o que a próxima marca na foto define
  let medicoes = [];         // cada medida da foto: { n, pista, r (comparação), real, id }; a mais nova por último
  let pistaRef = null;       // pista da referência
  let primeiroPonto = null;  // modo "pontos": a primeira ponta
  let medindo = false;
  let contador = 0;
  const NOMES = Object.fromEntries((estado.modelos || []).map((m) => [m.id, M.colunas[m.id] || m.id]));
  let geracao = 0;
  let mira = { x: 0.5, y: 0.5 };
  let cotaDestacada = null;

  // ---------------------------------------------------------------- ferramentas e palco
  const entrada = el("input", { type: "file", accept: "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif", hidden: true, onchange: () => { if (entrada.files[0]) abrir(entrada.files[0]); entrada.value = ""; } });
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
  const listaMedicoes = el("div", { class: "lista-medicoes", "aria-live": "polite" });
  const blocoComparacao = el("section", { class: "bloco-comparacao", "aria-label": M.comparacaoTitulo },
    el("div", { class: "titulo-bloco" }, el("h2", {}, M.comparacaoTitulo)), listaMedicoes);
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
  // medir com a referência, sem ou os dois: vale para os próximos cliques (cada medida guarda a sua escolha)
  let comoMedir = "ambos";
  try { comoMedir = localStorage.getItem("pyron.medir.como") || "ambos"; } catch { /* sem armazenamento */ }
  const notaComo = el("p", { class: "nota" }, M.comoNota[comoMedir]);
  const seletorComo = segmentado({ rotulo: M.medirComo, valor: comoMedir, opcoes: Object.entries(M.como).map(([valor, texto]) => ({ valor, texto })),
    aoMudar: (v) => { comoMedir = v; notaComo.textContent = M.comoNota[v]; try { localStorage.setItem("pyron.medir.como", v); } catch { /* sem armazenamento */ } } });
  const corpoRef = el("div", { class: "grupo-campos" }, el("p", { class: "nota" }, M.referenciaTexto), objetoRef, ladoRef, tamanhoRef, seletorComo, notaComo, el("div", { class: "grupo-btn" }, marcarRef, tirarRef), notaRef);
  const retangulos = refs.filter(([, r]) => r.largura != null);
  const retRef = campo({ rotulo: M.retangulo, valor: autos.length ? `auto:${autos[0][0]}` : retangulos[0]?.[0] || "outro", opcoes: [
    ...autos.map(([id, r]) => ({ valor: `auto:${id}`, texto: r.nome })),
    ...(autos.length ? [] : [...retangulos.map(([id, r]) => ({ valor: id, texto: r.nome })), { valor: "outro", texto: M.outro }])] });
  const ladoMaior = campo({ rotulo: M.ladoMaior, tipo: "number", unidade: "cm" });
  const ladoMenor = campo({ rotulo: M.ladoMenor, tipo: "number", unidade: "cm" });
  const acharPostit = botao({ texto: M.acharPostit, icone: "detectar", onclick: () => ocupado(acharPostit, achar) });
  const refazerCantos = botao({ texto: M.refazerCantos, variante: "fantasma", compacto: true, onclick: () => { cantos = []; pontoPlano = null; medidasPlano = []; atualizarTudo(); palco.focus({ preventScroll: true }); } });
  const corpoPlano = el("div", { class: "grupo-campos" }, el("p", { class: "nota" }, M.planoTexto), retRef, ladoMaior, ladoMenor, el("div", { class: "grupo-btn" }, acharPostit, refazerCantos));
  const secaoRef = secao({ titulo: M.referenciaTitulo, conteudo: [corpoRef] });
  const secaoPlano = secao({ titulo: M.planoTitulo, conteudo: [corpoPlano] });
  const avisoModelos = estado.pronto ? null : el("div", { class: "aviso-modelos" }, el("p", { class: "nota" }, M.semModelosNota), el("code", { class: "mono comando-medir" }, M.comandoInstalar),
    el("a", { class: "btn compacto", href: endereco("modelos", ["medicao"]) }, M.abrirModelos));
  const secaoResultado = el("section", {}, el("div", { class: "titulo-bloco" }, el("h2", {}, M.resultado)), caixaResultado);
  const caixaRegistro = el("div", { class: "registro-medir" });
  const caixaCelular = el("div", { class: "celular-medir" });
  const secaoCelular = secao({ titulo: M.celularTitulo, conteudo: [el("p", { class: "nota" }, M.celularTexto), caixaCelular] });
  const secaoRegistro = secao({ titulo: M.registroTitulo, conteudo: [el("p", { class: "nota" }, M.registroTexto), caixaRegistro] });
  const painel = el("aside", { class: "painel-medir", "aria-label": M.resultado },
    secaoResultado, secaoPlano, secaoRef, secaoCelular, secaoRegistro,
    secao({ titulo: M.detalhes, aberta: false, conteudo: [caixaDetalhes] }),
    avisoModelos);

  const grade = el("div", { class: "medir-grade" }, area, painel);
  no.append(entrada, barra, grade);

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
      grupos: [[{ texto: foto ? M.trocar : M.abrir, icone: "foto", onclick: () => entrada.click() }],
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
    if (medindo) return [el("b", {}, M.medindoTempo(Math.round((Date.now() - inicioMedida) / 1000))), " ", el("span", {}, M.medindoNota)];
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

    const ultima = [...medicoes].reverse().find((m) => m.r);
    if (ultima && modo !== "plano") {
      poligonos(ultima.r.contorno_referencia || [], "contorno-ref");
      poligonos(ultima.r.contorno || [], "contorno-obj");

      const cotas = ultima.r.cotas || {};
      const res0 = Object.values(ultima.r.resultados || {}).find((x) => x.com_referencia || x.sem_referencia);
      const v0 = res0?.com_referencia || res0?.sem_referencia || {};

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
      medidasPlano.forEach((m) => marca({ pontos: m.pontos }, "marca-obj"));
      if (pontoPlano) marca({ ponto: pontoPlano }, "marca-obj");
    } else {
      marca(pistaRef, "marca-ref");
      medicoes.forEach((m) => marca(m.pista, "marca-obj"));
      if (primeiroPonto) marca({ ponto: primeiroPonto }, "marca-obj");
    }
    if (rascunho) marca({ caixa: rascunho }, "marca-rascunho");
    if (document.activeElement === palco) filhos.push(svg("circle", { cx: mira.x * W, cy: mira.y * H, r: Math.max(W, H) * 0.012, class: "mira" }));
    camada.replaceChildren(...filhos);
  }

  function desenharResultado() {
    secaoResultado.hidden = modo !== "plano";
    blocoComparacao.hidden = modo === "plano";
    if (modo === "plano") { desenharResultadoPlano(); return; }
    if (!medicoes.length) { listaMedicoes.replaceChildren(el("p", { class: "nota" }, M.comparacaoVazia)); caixaDetalhes.replaceChildren(); return; }
    listaMedicoes.replaceChildren(...[...medicoes].reverse().map(cartao));
    const ultima = [...medicoes].reverse().find((m) => m.r);
    const r0 = ultima && Object.values(ultima.r.resultados).find((x) => x.sem_referencia)?.sem_referencia;
    caixaDetalhes.replaceChildren(...(r0 ? [el("p", {}, M.lente[r0.lente] || "")] : []));
  }

  /** Um cartão por medida: linhas = altura, comprimento…; colunas = cada modelo sem e com referência e o valor real. */
  function cartao(m) {
    const fechar = botao({ texto: M.removerMedida, icone: "x", soIcone: true, compacto: true, variante: "fantasma",
      onclick: () => { medicoes = medicoes.filter((x) => x !== m); atualizarTudo(); } });
    const cab = el("div", { class: "cab-cartao" }, el("h3", {}, M.medidaDe(m.n, M.tipoPista[Object.keys(m.pista)[0]])), fechar);
    if (!m.r) return el("article", { class: "cartao-medida" }, cab, el("p", { class: "nota" }, M.medindoModelos), esqueleto.linhas(2));
    const res = m.r.resultados;
    const modelos = Object.keys(res);
    const comRef = modelos.some((k) => res[k].com_referencia);
    // "Com referência" mostra só essas colunas; se a referência não foi achada, cai nas sem referência
    const sem = m.como !== "com" || !comRef;
    const colunas = modelos.flatMap((k) => [...(sem ? [[k, "sem_referencia", NOMES[k] || k]] : []), ...(comRef ? [[k, "com_referencia", M.comRef(NOMES[k] || k)]] : [])]);
    const medidas = ORDEM.filter((q) => colunas.some(([k, modo]) => res[k][modo]?.[`${q}_cm`] != null));
    const celula = (k, modo, q) => {
      const v = res[k][modo];
      if (!v || v[`${q}_cm`] == null) return el("td", {}, T.geral.semValor);
      const erro = m.erros?.[k]?.[modo]?.[q];
      return el("td", {}, el("span", { class: "num valor" }, fmt(v[`${q}_cm`], 1)),
        el("span", { class: "num mais" }, M.mais(fmt(v.incerteza_cm?.[q], 1))),
        erro != null ? el("span", { class: `num erro-medida ${Math.abs(erro) < 0.1 ? "bom" : Math.abs(erro) < 0.25 ? "medio" : "ruim"}` }, M.erroPct(Math.round(erro * 100))) : null);
    };
    const linhas = medidas.map((q) => {
      const real = campoReal(m, q);
      return el("tr", {
        class: "linha-medida",
        onmouseenter: () => { cotaDestacada = q; desenharCamada(); },
        onmouseleave: () => { cotaDestacada = null; desenharCamada(); },
      }, el("th", { scope: "row" }, M.nomes[q]), ...colunas.map(([k, modo]) => celula(k, modo, q)), el("td", {}, real));
    });
    const notas = [];
    for (const k of modelos) {
      if (res[k].erro) notas.push(M.modeloErro(NOMES[k] || k, res[k].erro));
      const ign = res[k].com_referencia?.referencia_ignorada;
      if (ign) notas.push(M.refIgnorada(NOMES[k] || k, ign));
    }
    const tempos = modelos.map((k) => res[k].sem_referencia?.tempos_ms?.total != null
      ? M.temposModelo(NOMES[k] || k, M.segundos(fmt(res[k].sem_referencia.tempos_ms.total / 1000, 1))) : null).filter(Boolean);
    return el("article", { class: "cartao-medida" }, cab, campoNome(m),
      el("div", { class: "rola-tabela" }, el("table", { class: "tabela-comparacao" },
        el("thead", {}, el("tr", {}, el("th", { scope: "col" }, M.colunaMedida), ...colunas.map(([, , nome]) => el("th", { scope: "col" }, nome)), el("th", { scope: "col" }, M.colunaReal))),
        el("tbody", {}, linhas))),
      ...notas.map((t) => el("p", { class: "nota aviso-escala" }, t)),
      tempos.length ? el("p", { class: "nota" }, M.tempos(tempos.join(", "))) : null);
  }

  /** O nome do objeto ("Kindle"): agrupa as medidas em Modelos › Medição. */
  function campoNome(m) {
    const c = campo({ rotulo: M.nomeObjeto, valor: m.nome, marcador: M.nomeMarcador, classe: "campo-nome", autocomplete: "off" });
    const entrada = c.querySelector("input");
    entrada.addEventListener("change", async () => {
      m.nome = entrada.value.trim();
      try { await api(`/api/medicao/registro/${m.id}`, json("PUT", { nome: m.nome })); avisar(M.nomeSalvo); }
      catch (erro) { avisar(erro.message, { erro: true }); }
    });
    return c;
  }

  function campoReal(m, q) {
    const entrada = el("input", { type: "text", inputmode: "decimal", class: "num campo-real", value: m.real[q] != null ? fmt(m.real[q], 1) : "",
      "aria-label": M.realRotulo(M.nomes[q].toLowerCase(), m.n), autocomplete: "off" });
    entrada.addEventListener("change", async () => {
      const v = lerNumero(entrada.value);
      if (v != null && !(v > 0)) return;
      m.real = { ...m.real, [q]: v };
      try {
        const e = await api(`/api/medicao/registro/${m.id}`, json("PUT", { real: m.real }));
        m.erros = e.erros;
        desenharResultado();
        atualizarRegistro();
        avisar(M.realSalvo);
      } catch (erro) { avisar(erro.message, { erro: true }); }
    });
    return entrada;
  }

  async function atualizarRegistro() {
    try {
      const r = await api("/api/medicao/registro?limite=1");
      const linhas = [];
      for (const [modelo, modos] of Object.entries(r.resumo || {})) {
        for (const [modoR, v] of Object.entries(modos)) linhas.push(el("li", {}, M.registroLinha(NOMES[modelo] || modelo, M.modos[modoR], fmt(v.erro_mediano_pct, 1), v.n)));
      }
      caixaRegistro.replaceChildren(linhas.length ? el("ul", { class: "lista-registro" }, linhas) : el("p", { class: "nota" }, M.registroVazio));
    } catch { /* a faixa de conexão já avisa */ }
  }

  function desenharResultadoPlano() {
    const prontas = medidasPlano.filter((m) => m.r);
    if (!prontas.length) { caixaResultado.replaceChildren(el("p", { class: "nota" }, M.semResultado)); caixaDetalhes.replaceChildren(); return; }
    const linhas = medidasPlano.map((m, i) => !m.r ? null : el("div", { class: i === medidasPlano.length - 1 ? "leitura-medir principal" : "leitura-medir" },
      el("span", { class: "rotulo" }, m.r.extrapolacao > 3 ? `${M.medidaN(i + 1)}, ${M.longe}` : M.medidaN(i + 1)),
      el("b", { class: "num" }, M.valor(fmt(m.r.distancia_cm, 1))),
      el("span", { class: "num mais" }, M.mais(fmt(m.r.incerteza_cm, 1)))));
    const ultima = medidasPlano.length - 1;
    caixaResultado.replaceChildren(el("div", { class: "leituras-medir" }, linhas.filter(Boolean).reverse()), el("p", { class: "nota" }, M.planoMetodo));
    if (!medidasPlano[ultima]?.r) caixaResultado.prepend(esqueleto.linhas(1));
    caixaDetalhes.replaceChildren();
  }

  function atualizarTudo() { acharPostit.disabled = !foto; desenharBarra(); desenharResultado(); atualizarHud(); desenharCamada(); secaoPlano.hidden = modo !== "plano"; secaoRef.hidden = modo === "plano"; }

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
    for (const m of medidasPlano.filter((x) => x.r)) await medirPlano(m);
    desenharResultado();
  }

  async function clicarPlano(p) {
    if (cantos.length < 4) { cantos.push(p); atualizarHud(); desenharCamada(); return; }
    if (!pontoPlano) { pontoPlano = p; atualizarHud(); desenharCamada(); return; }
    const m = { pontos: [pontoPlano, p], r: null };
    pontoPlano = null;
    medidasPlano.push(m); // entra na ordem do clique, mesmo que a resposta de outra medida chegue antes
    atualizarHud(); desenharCamada();
    if (!(await medirPlano(m))) medidasPlano = medidasPlano.filter((x) => x !== m);
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
    seletorComo.hidden = notaComo.hidden = !escolha;  // sem referência não há o que escolher
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
  /** Abre a foto. O navegador não mostra HEIC: aí o servidor devolve um JPEG do mesmo tamanho só para a tela
   * (as medidas usam sempre o arquivo original, com os metadados). */
  function abrir(arquivo, previa = null) {
    if (foto) URL.revokeObjectURL(foto.url);
    const url = URL.createObjectURL(previa || arquivo);
    const img = new Image();
    img.onload = () => {
      foto = { arquivo, url, largura: img.naturalWidth, altura: img.naturalHeight, codigo: arquivo.codigo || null };
      pistaRef = primeiroPonto = pontoPlano = null;
      cantos = []; medidasPlano = []; medicoes = [];
      alvo = "objeto";
      geracao++; medindo = false;  // a medida da foto anterior não aparece nesta
      imagem.src = url;
      zoom = 1; quadro.style.width = ""; janela.style.height = ""; janela.classList.remove("ampliada"); rotuloZoom.textContent = M.zoomPct(100);
      quadro.style.setProperty("--proporcao", String(foto.largura / foto.altura));
      area.replaceChildren(palco, faixa, blocoComparacao);
      desenharReferencia(); atualizarTudo();
      palco.focus({ preventScroll: true });
      if (foto.codigo) { trazerMedidasDoCelular(); desenharFaixa(); } else guardarNaFaixa(arquivo);
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
    cantos = []; medidasPlano = []; medicoes = [];
    alvo = "objeto";
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
    if (alvo === "referencia") {
      pistaRef = p;
      alvo = "objeto";
      desenharReferencia();
      atualizarHud();
      if (!referencia()) { avisar(M.semTamanho, { erro: true }); return; }
      remedir();
      return;
    }
    const m = { n: ++contador, pista: p, r: null, real: {}, id: null, erros: null, como: comoMedir, nome: "" };
    medicoes.push(m);
    medir(m);
  }

  /** Referência mudou: as medidas da foto saem de novo (cada uma vira uma entrada nova no registro). */
  function remedir() { medicoes.forEach((m) => { m.r = null; m.erros = null; medir(m); }); }

  // uma comparação por vez no servidor (dois modelos); as medidas esperam na ordem do clique
  let fila = Promise.resolve();
  function medir(m) {
    const minha = geracao;
    if (!medindo) inicioMedida = Date.now();
    medindo = true;
    desenharResultado(); atualizarHud(); desenharCamada();
    fila = fila.then(async () => {
      if (minha !== geracao || !medicoes.includes(m)) return;
      const dados = new FormData();
      dados.append("arquivo", foto.arquivo);
      dados.append("pista", JSON.stringify(m.pista));
      const ref = m.como === "sem" ? null : referencia();
      if (ref) dados.append("referencia", JSON.stringify(ref));
      dados.append("como", m.como);
      try {
        const r = await api("/api/medicao/comparar", { method: "POST", body: dados });
        if (minha !== geracao) return;
        m.r = r; m.id = r.id; m.erros = r.erros;
        if (foto) foto.codigo = r.foto;
        if (Object.keys(m.real).length) {  // o valor real já informado vale também para a medida refeita
          const e = await api(`/api/medicao/registro/${m.id}`, json("PUT", { real: m.real }));
          m.erros = e.erros;
          atualizarRegistro();
        }
      } catch (e) {
        if (minha !== geracao) return;
        medicoes = medicoes.filter((x) => x !== m);
        avisar(`${M.erroMedir} ${e.message}`, { erro: true });
      } finally {
        if (minha === geracao) { medindo = medicoes.some((x) => !x.r); desenharResultado(); atualizarHud(); desenharCamada(); }
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
  let vistas = null;  // fotos do celular que já estavam lá ao abrir a aba (não abrem sozinhas)

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

  async function abrirDoCelular(codigo) {
    const r = await fetch(`/api/medicao/fotos/${codigo}`);
    if (!r.ok) { avisar(M.erroMedir, { erro: true }); return; }
    const blob = await r.blob();
    const arquivo = new File([blob], codigo, { type: blob.type });
    arquivo.codigo = codigo;
    abrir(arquivo);  // ao carregar, traz as medidas que o celular já fez nesta foto
  }

  /** As medidas já guardadas da foto aberta voltam como cartões (sem o contorno, que não fica no registro). */
  async function trazerMedidasDoCelular() {
    if (!foto?.codigo) return;
    const reg = await api("/api/medicao/registro?limite=100");
    const ids = new Set(medicoes.map((m) => m.id));
    const novas = reg.entradas.filter((e) => e.foto === foto.codigo && !ids.has(e.id)).reverse();  // as medidas já guardadas desta foto
    for (const e of novas) medicoes.push({ n: ++contador, pista: e.pista, r: { resultados: e.resultados, contorno: [], contorno_referencia: [] }, real: e.real || {}, id: e.id, erros: e.erros, como: e.como || (e.referencia ? "ambos" : "sem"), nome: e.nome || "" });
    if (novas.length) { desenharResultado(); desenharCamada(); atualizarRegistro(); }
  }

  async function vigiarCelular() {
    try {
      const est = await api("/api/medicao/celular");
      const mudou = est.versao !== celular.versao || est.ligado !== celular.ligado;
      celular = est;
      if (vistas == null) vistas = new Set(est.fotos.map((f) => f.id));
      if (!mudou) return;
      desenharCelular();
      carregarFaixa();
      const nova = est.fotos.find((f) => !vistas.has(f.id));
      if (nova) {
        vistas.add(nova.id);
        if (foto?.codigo !== nova.id) { await abrirDoCelular(nova.id); avisar(M.fotoNovaCelular); }
      }
      await trazerMedidasDoCelular();
    } catch { /* a faixa de conexão já avisa */ }
  }
  const relogioCelular = setInterval(vigiarCelular, 2000);

  desenharReferencia();
  atualizarTudo();
  desenharVazio();
  atualizarRegistro();
  vigiarCelular();
  // outra foto: arrastar para a aba ou colar (Ctrl+V), além do botão
  const fotoDe = (lista) => [...(lista || [])].find((f) => f.type.startsWith("image/") || /\.(heic|heif)$/i.test(f.name));
  const arrastando = (ev) => { if (![...(ev.dataTransfer?.types || [])].includes("Files")) return; ev.preventDefault(); no.classList.add("soltar-foto"); };
  const saiu = (ev) => { if (!no.contains(ev.relatedTarget)) no.classList.remove("soltar-foto"); };
  const soltou = (ev) => {
    no.classList.remove("soltar-foto");
    const f = fotoDe(ev.dataTransfer?.files);
    if (!f) return;
    ev.preventDefault();
    abrir(f);
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
  carregarFaixa();
  // Modelos › Medição abre uma foto guardada por aqui (#captura/medir/<código>)
  const pedida = ctx.partes?.[0];
  if (pedida && /^[0-9a-f]+$/i.test(pedida)) abrirDoCelular(pedida);

  return () => {
    geracao++; clearInterval(relogioCelular); clearInterval(relogioMedida);
    document.removeEventListener("paste", colou);
    removeEventListener("keydown", teclaEspaco); removeEventListener("keyup", teclaEspaco);
    if (foto) URL.revokeObjectURL(foto.url);
  };
}

