// Captura › Medir foto (docs/07_roteiro_medicao_geral.md, fase 5): medir um objeto qualquer numa foto comum.
// Abrir a foto, clicar no objeto (ou arrastar uma caixa, ou marcar duas pontas) e ver altura, largura e
// comprimento com a margem de erro; uma referência de tamanho conhecido na foto corrige a escala.
// O servidor faz tudo (POST /api/medicao): profundidade do MoGe-2, contorno do SAM 2.1 e geometria em 3D.
import { TEXTOS as T } from "../../textos.js";
import { el, api, fmt, lerNumero } from "../base.js";
import { botao, avisar, barraFerramentas, campo, esqueleto, estadoVazio, secao } from "../componentes.js";

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

export async function montar(no) {
  const estado = await api("/api/medicao/estado");
  if (!estado.pronto) { desenharSemModelos(no, estado); return null; }

  let foto = null;           // { arquivo, url, largura, altura }
  let modo = "ponto";        // ponto | caixa | pontos
  let alvo = "objeto";       // objeto | referencia: o que a próxima marca na foto define
  let pista = null;          // pista do objeto (enviada ao servidor)
  let pistaRef = null;       // pista da referência
  let primeiroPonto = null;  // modo "pontos": a primeira ponta
  let resultado = null;
  let medindo = false;
  let geracao = 0;
  let mira = { x: 0.5, y: 0.5 };

  // ---------------------------------------------------------------- ferramentas e palco
  const entrada = el("input", { type: "file", accept: "image/jpeg,image/png,image/webp", hidden: true, onchange: () => { if (entrada.files[0]) abrir(entrada.files[0]); entrada.value = ""; } });
  const barra = el("div");
  const imagem = el("img", { class: "foto-medir", alt: "", draggable: "false" });
  const camada = svg("svg", { class: "camada-medir", "aria-hidden": "true", preserveAspectRatio: "none" });
  const quadro = el("div", { class: "quadro-medir" }, imagem, camada);
  const hud = el("p", { class: "hud-medir", role: "status" });
  const palco = el("div", { class: "palco-medir", tabindex: "0", "aria-label": M.palco }, hud, quadro);
  const area = el("div", { class: "coluna-medir" }, palco);

  // ---------------------------------------------------------------- painel: resultado, referência, detalhes
  const caixaResultado = el("div", { class: "resultado-medir", "aria-live": "polite" });
  const caixaDetalhes = el("div", { class: "detalhes-medir" });
  const refs = Object.entries(estado.referencias || {});
  const objetoRef = campo({ rotulo: M.objetoReferencia, valor: "", opcoes: [{ valor: "", texto: M.nenhuma }, ...refs.map(([id, r]) => ({ valor: id, texto: r.nome })), { valor: "outro", texto: M.outro }] });
  const ladoRef = campo({ rotulo: M.medidaReferencia, valor: "comprimento", opcoes: Object.entries(M.lados).map(([valor, texto]) => ({ valor, texto })) });
  const tamanhoRef = campo({ rotulo: M.tamanho, tipo: "number", unidade: "cm" });
  const marcarRef = botao({ texto: M.marcarReferencia, icone: "regua", onclick: () => comecarReferencia() });
  const tirarRef = botao({ texto: M.tirarReferencia, variante: "fantasma", compacto: true, onclick: () => { pistaRef = null; desenharReferencia(); remedir(); } });
  const notaRef = el("p", { class: "nota", role: "status" });
  const corpoRef = el("div", { class: "grupo-campos" }, el("p", { class: "nota" }, M.referenciaTexto), objetoRef, ladoRef, tamanhoRef, el("div", { class: "grupo-btn" }, marcarRef, tirarRef), notaRef);
  const painel = el("aside", { class: "painel-medir", "aria-label": M.resultado },
    el("section", {}, el("div", { class: "titulo-bloco" }, el("h2", {}, M.resultado)), caixaResultado),
    secao({ titulo: M.referenciaTitulo, conteudo: [corpoRef] }),
    secao({ titulo: M.detalhes, aberta: false, conteudo: [caixaDetalhes] }));

  const grade = el("div", { class: "medir-grade" }, area, painel);
  no.append(entrada, barra, grade);

  objetoRef.querySelector("select").addEventListener("change", desenharReferencia);
  const seletorLado = ladoRef.querySelector("select");
  const campoTamanho = tamanhoRef.querySelector("input");
  seletorLado.addEventListener("change", () => { if (objetoRef.querySelector("select").value !== "outro") desenharReferencia(); remedir(); });
  campoTamanho.addEventListener("change", () => remedir());

  // ---------------------------------------------------------------- desenho
  function desenharBarra() {
    const ferramenta = (id, icone) => ({ texto: M[id], icone, pressionado: modo === id, indisponivel: foto ? null : M.dicaModo.ponto, onclick: () => escolherModo(id) });
    barra.replaceChildren(barraFerramentas({
      rotulo: M.ferramentas,
      grupos: [[{ texto: foto ? M.trocar : M.abrir, icone: "foto", onclick: () => entrada.click() }],
        [ferramenta("ponto", "ponto"), ferramenta("caixa", "regiao"), ferramenta("pontos", "linha")]],
      direita: [{ texto: M.limpar, icone: "x", indisponivel: foto ? null : M.dicaModo.ponto, onclick: () => limpar() }],
    }));
  }

  function desenharVazio() {
    area.replaceChildren(estadoVazio({ icone: "regua", titulo: M.vazioTitulo, texto: M.vazioTexto,
      acoes: [botao({ texto: M.abrir, icone: "foto", variante: "primario", onclick: () => entrada.click() })] }));
    caixaResultado.replaceChildren(el("p", { class: "nota" }, M.semResultado));
    caixaDetalhes.replaceChildren();
  }

  function dica() {
    if (medindo) return [el("b", {}, M.medindo), " ", el("span", {}, M.medindoNota)];
    if (alvo === "referencia") return M.dicaModo.referencia;
    if (modo === "pontos" && primeiroPonto) return M.dicaModo.pontosSegundo;
    return M.dicaModo[modo];
  }
  const atualizarHud = () => hud.replaceChildren(...[dica()].flat());

  function desenharCamada(rascunho = null) {
    if (!foto) return;
    const { largura: W, altura: H } = foto;
    camada.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const filhos = [];
    const poligonos = (lista, classe) => lista.forEach((p) => {
      const pts = p.map((q) => q.join(",")).join(" ");
      filhos.push(svg("polygon", { points: pts, class: `${classe} sombra` }), svg("polygon", { points: pts, class: classe }));
    });
    if (resultado) { poligonos(resultado.contorno_referencia || [], "contorno-ref"); poligonos(resultado.contorno || [], "contorno-obj"); }
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
    marca(pistaRef, "marca-ref");
    marca(pista, "marca-obj");
    if (primeiroPonto) marca({ ponto: primeiroPonto }, "marca-obj");
    if (rascunho) marca({ caixa: rascunho }, "marca-rascunho");
    if (document.activeElement === palco) filhos.push(svg("circle", { cx: mira.x * W, cy: mira.y * H, r: Math.max(W, H) * 0.012, class: "mira" }));
    camada.replaceChildren(...filhos);
  }

  function desenharResultado() {
    if (medindo) { caixaResultado.replaceChildren(esqueleto.linhas(3)); return; }
    if (!resultado) { caixaResultado.replaceChildren(el("p", { class: "nota" }, M.semResultado)); caixaDetalhes.replaceChildren(); return; }
    const r = resultado;
    const linhas = ORDEM.filter((k) => r[`${k}_cm`] != null).map((k, i) => el("div", { class: i === 0 ? "leitura-medir principal" : "leitura-medir" },
      el("span", { class: "rotulo" }, M.nomes[k]),
      el("b", { class: "num" }, M.valor(fmt(r[`${k}_cm`], 1))),
      el("span", { class: "num mais" }, M.mais(fmt(r.incerteza_cm[k], 1)))));
    const metodo = r.metodo === "sem referência" ? M.semReferencia : M.comReferencia(r.metodo);
    caixaResultado.replaceChildren(el("div", { class: "leituras-medir" }, linhas),
      el("p", { class: "nota" }, [M.forma[r.forma], r.vertical && r.forma !== "distância" && r.altura_cm != null ? `, ${M.vertical[r.vertical]}` : "", "."].join("")),
      el("p", { class: r.metodo === "sem referência" ? "nota aviso-escala" : "nota" }, metodo));
    const tempos = Object.entries(r.tempos_ms || {}).map(([k, v]) => `${M.etapas[k] || k} ${M.segundos(fmt(v / 1000, 1))}`).join(", ");
    caixaDetalhes.replaceChildren(
      el("p", {}, M.lente[r.lente] || ""),
      el("p", {}, M.modelosUsados(r.modelos?.profundidade || T.geral.semValor, r.modelos?.contorno || T.geral.semValor)),
      el("p", { class: "nota" }, M.tempos(tempos)));
  }

  function desenharReferencia() {
    const escolha = objetoRef.querySelector("select").value;
    const pronta = estado.referencias?.[escolha];
    ladoRef.hidden = !escolha || (pronta && pronta.largura == null);
    tamanhoRef.hidden = escolha !== "outro";
    if (pronta) campoTamanho.value = fmt(pronta[seletorLado.value === "largura" && pronta.largura != null ? "largura" : "comprimento"], 2);
    marcarRef.disabled = !escolha || !foto;
    tirarRef.hidden = !pistaRef;
    notaRef.textContent = pistaRef ? M.referenciaMarcada : "";
    desenharCamada();
  }

  function referencia() {
    const escolha = objetoRef.querySelector("select").value;
    if (!pistaRef || !escolha) return null;
    const pronta = estado.referencias?.[escolha];
    const lado = pronta && pronta.largura == null ? "comprimento" : seletorLado.value;
    const tamanho = pronta ? pronta[lado === "largura" ? "largura" : "comprimento"] : lerNumero(campoTamanho.value);
    if (!(tamanho > 0)) return null;
    return { ...pistaRef, tamanho_cm: tamanho, medida: lado, nome: pronta ? pronta.nome : "" };
  }

  // ---------------------------------------------------------------- ações
  function abrir(arquivo) {
    if (foto) URL.revokeObjectURL(foto.url);
    const url = URL.createObjectURL(arquivo);
    const img = new Image();
    img.onload = () => {
      foto = { arquivo, url, largura: img.naturalWidth, altura: img.naturalHeight };
      pista = pistaRef = primeiroPonto = resultado = null;
      alvo = "objeto";
      imagem.src = url;
      quadro.style.setProperty("--proporcao", String(foto.largura / foto.altura));
      area.replaceChildren(palco);
      desenharBarra(); desenharReferencia(); desenharResultado(); atualizarHud(); desenharCamada();
      palco.focus({ preventScroll: true });
    };
    img.onerror = () => { URL.revokeObjectURL(url); avisar(M.erroMedir, { erro: true }); };
    img.src = url;
  }

  function escolherModo(id) {
    modo = id;
    primeiroPonto = null;
    desenharBarra(); atualizarHud(); desenharCamada();
  }

  function limpar() {
    pista = pistaRef = primeiroPonto = resultado = null;
    alvo = "objeto";
    geracao++;
    medindo = false;
    desenharReferencia(); desenharResultado(); atualizarHud(); desenharCamada();
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
      if (pista) medir();
      return;
    }
    pista = p;
    medir();
  }

  function remedir() { if (pista && !medindo) medir(); }

  async function medir() {
    const minha = ++geracao;
    medindo = true;
    desenharResultado(); atualizarHud(); desenharCamada();
    const dados = new FormData();
    dados.append("arquivo", foto.arquivo);
    dados.append("pista", JSON.stringify(pista));
    const ref = referencia();
    if (ref) dados.append("referencia", JSON.stringify(ref));
    try {
      const r = await api("/api/medicao", { method: "POST", body: dados });
      if (minha !== geracao) return;
      resultado = r;
    } catch (e) {
      if (minha !== geracao) return;
      resultado = null;
      avisar(`${M.erroMedir} ${e.message}`, { erro: true });
    } finally {
      if (minha === geracao) { medindo = false; desenharResultado(); atualizarHud(); desenharCamada(); }
    }
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
    if (!foto || medindo || ev.button !== 0) return;
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
    if (!foto || medindo) return;
    const passo = ev.shiftKey ? PASSO_TECLADO * 5 : PASSO_TECLADO;
    const d = { ArrowLeft: [-passo, 0], ArrowRight: [passo, 0], ArrowUp: [0, -passo], ArrowDown: [0, passo] }[ev.key];
    if (d) {
      ev.preventDefault();
      mira = { x: Math.min(1, Math.max(0, mira.x + d[0])), y: Math.min(1, Math.max(0, mira.y + d[1])) };
      desenharCamada();
    } else if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      clicar(mira.x * foto.largura, mira.y * foto.altura);
    } else if (ev.key === "Escape" && (primeiroPonto || alvo === "referencia")) {
      primeiroPonto = null; alvo = "objeto"; atualizarHud(); desenharCamada();
    }
  });
  palco.addEventListener("focus", () => desenharCamada());
  palco.addEventListener("blur", () => desenharCamada());

  desenharBarra();
  desenharReferencia();
  desenharVazio();
  return () => { geracao++; if (foto) URL.revokeObjectURL(foto.url); };
}

function desenharSemModelos(no, estado) {
  const faltam = Object.entries(estado.pacotes || {}).filter(([, ok]) => !ok).map(([nome]) => nome);
  no.replaceChildren(el("div", { class: "vazio-medir" }, estadoVazio({ icone: "regua", titulo: M.semModelosTitulo, texto: M.semModelosTexto }),
    el("code", { class: "mono comando-medir" }, M.comandoInstalar),
    faltam.length ? el("p", { class: "nota" }, M.faltaPacote(faltam.join(", "))) : null));
}
