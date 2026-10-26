// Captura › Medir foto (docs/07_roteiro_medicao_geral.md, fase 5): medir um objeto qualquer numa foto comum.
// Abrir a foto, clicar no objeto (ou arrastar uma caixa, ou marcar duas pontas) e ver altura, largura e
// comprimento com a margem de erro; uma referência de tamanho conhecido na foto corrige a escala.
// O servidor faz tudo (POST /api/medicao): profundidade do MoGe-2, contorno do SAM 2.1 e geometria em 3D.
// Sem modelo nenhum (ou sem os pesos instalados), o modo "Retângulo de referência" mede no plano de uma folha
// A4 ou de um cartão: 4 cantos e 2 pontas, por homografia (POST /api/medicao/plano).
import { TEXTOS as T } from "../../textos.js";
import { el, api, fmt, json, lerNumero } from "../base.js";
import { botao, avisar, barraFerramentas, campo, esqueleto, estadoVazio, ocupado, secao } from "../componentes.js";

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

  let foto = null;           // { arquivo, url, largura, altura }
  let modo = estado.pronto ? "ponto" : "plano"; // ponto | caixa | pontos (com os modelos) | plano (sem modelo)
  let cantos = [];           // modo plano: cantos do retângulo de referência
  let pontoPlano = null;     // modo plano: a primeira ponta da medida
  let medidasPlano = [];     // modo plano: [{ pontos, r }]
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
  const autos = Object.entries(estado.referencias_auto || {});
  const objetoRef = campo({ rotulo: M.objetoReferencia, valor: "", opcoes: [{ valor: "", texto: M.nenhuma },
    ...autos.map(([id, r]) => ({ valor: `auto:${id}`, texto: `${r.nome} ${M.autoSufixo}` })),
    ...refs.map(([id, r]) => ({ valor: id, texto: r.nome })), { valor: "outro", texto: M.outro }] });
  const ladoRef = campo({ rotulo: M.medidaReferencia, valor: "comprimento", opcoes: Object.entries(M.lados).map(([valor, texto]) => ({ valor, texto })) });
  const tamanhoRef = campo({ rotulo: M.tamanho, tipo: "number", unidade: "cm" });
  const marcarRef = botao({ texto: M.marcarReferencia, icone: "regua", onclick: () => comecarReferencia() });
  const tirarRef = botao({ texto: M.tirarReferencia, variante: "fantasma", compacto: true, onclick: () => { pistaRef = null; desenharReferencia(); remedir(); } });
  const notaRef = el("p", { class: "nota", role: "status" });
  const corpoRef = el("div", { class: "grupo-campos" }, el("p", { class: "nota" }, M.referenciaTexto), objetoRef, ladoRef, tamanhoRef, el("div", { class: "grupo-btn" }, marcarRef, tirarRef), notaRef);
  const retangulos = refs.filter(([, r]) => r.largura != null);
  const retRef = campo({ rotulo: M.retangulo, valor: autos.length ? `auto:${autos[0][0]}` : retangulos[0]?.[0] || "outro", opcoes: [
    ...autos.map(([id, r]) => ({ valor: `auto:${id}`, texto: r.nome })),
    ...retangulos.map(([id, r]) => ({ valor: id, texto: r.nome })), { valor: "outro", texto: M.outro }] });
  const ladoMaior = campo({ rotulo: M.ladoMaior, tipo: "number", unidade: "cm" });
  const ladoMenor = campo({ rotulo: M.ladoMenor, tipo: "number", unidade: "cm" });
  const acharPostit = botao({ texto: M.acharPostit, icone: "detectar", onclick: () => ocupado(acharPostit, achar) });
  const refazerCantos = botao({ texto: M.refazerCantos, variante: "fantasma", compacto: true, onclick: () => { cantos = []; pontoPlano = null; medidasPlano = []; atualizarTudo(); palco.focus({ preventScroll: true }); } });
  const corpoPlano = el("div", { class: "grupo-campos" }, el("p", { class: "nota" }, M.planoTexto), retRef, ladoMaior, ladoMenor, el("div", { class: "grupo-btn" }, acharPostit, refazerCantos));
  const secaoRef = secao({ titulo: M.referenciaTitulo, conteudo: [corpoRef] });
  const secaoPlano = secao({ titulo: M.planoTitulo, conteudo: [corpoPlano] });
  const avisoModelos = estado.pronto ? null : el("div", { class: "aviso-modelos" }, el("p", { class: "nota" }, M.semModelosNota), el("code", { class: "mono comando-medir" }, M.comandoInstalar));
  const painel = el("aside", { class: "painel-medir", "aria-label": M.resultado },
    el("section", {}, el("div", { class: "titulo-bloco" }, el("h2", {}, M.resultado)), caixaResultado),
    secaoPlano, secaoRef,
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
      acoes: [botao({ texto: M.abrir, icone: "foto", variante: "primario", onclick: () => entrada.click() })] }));
    caixaResultado.replaceChildren(el("p", { class: "nota" }, M.semResultado));
    caixaDetalhes.replaceChildren();
  }

  function dica() {
    if (medindo) return [el("b", {}, M.medindo), " ", el("span", {}, M.medindoNota)];
    if (modo === "plano") return cantos.length < 4 ? M.dicaModo.cantos(cantos.length + 1) : pontoPlano ? M.dicaModo.pontosSegundo : M.dicaModo.plano;
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
      marca(pista, "marca-obj");
      if (primeiroPonto) marca({ ponto: primeiroPonto }, "marca-obj");
    }
    if (rascunho) marca({ caixa: rascunho }, "marca-rascunho");
    if (document.activeElement === palco) filhos.push(svg("circle", { cx: mira.x * W, cy: mira.y * H, r: Math.max(W, H) * 0.012, class: "mira" }));
    camada.replaceChildren(...filhos);
  }

  function desenharResultado() {
    if (modo === "plano") { desenharResultadoPlano(); return; }
    if (medindo) { caixaResultado.replaceChildren(esqueleto.linhas(3)); return; }
    if (!resultado) { caixaResultado.replaceChildren(el("p", { class: "nota" }, M.semResultado)); caixaDetalhes.replaceChildren(); return; }
    const r = resultado;
    const linhas = ORDEM.filter((k) => r[`${k}_cm`] != null).map((k, i) => el("div", { class: i === 0 ? "leitura-medir principal" : "leitura-medir" },
      el("span", { class: "rotulo" }, M.nomes[k]),
      el("b", { class: "num" }, M.valor(fmt(r[`${k}_cm`], 1))),
      el("span", { class: "num mais" }, M.mais(fmt(r.incerteza_cm[k], 1)))));
    const metodo = r.metodo === "sem referência" ? M.semReferencia : M.comReferencia(r.metodo);
    const p = r.no_plano_da_referencia;
    const noPlano = p && p.comprimento_cm != null
      ? el("p", { class: "nota" }, M.noPlano(fmt(p.comprimento_cm, 1), fmt(p.largura_cm, 1), fmt(p.incerteza_cm.comprimento, 1), fmt(p.incerteza_cm.largura, 1))) : null;
    caixaResultado.replaceChildren(el("div", { class: "leituras-medir" }, linhas),
      el("p", { class: "nota" }, [M.forma[r.forma], r.vertical && r.forma !== "distância" && r.altura_cm != null ? `, ${M.vertical[r.vertical]}` : "", "."].join("")),
      el("p", { class: r.metodo === "sem referência" ? "nota aviso-escala" : "nota" }, metodo), noPlano);
    const tempos = Object.entries(r.tempos_ms || {}).map(([k, v]) => `${M.etapas[k] || k} ${M.segundos(fmt(v / 1000, 1))}`).join(", ");
    caixaDetalhes.replaceChildren(
      el("p", {}, M.lente[r.lente] || ""),
      el("p", {}, M.modelosUsados(r.modelos?.profundidade || T.geral.semValor, r.modelos?.contorno || T.geral.semValor)),
      el("p", { class: "nota" }, M.tempos(tempos)));
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
  function abrir(arquivo) {
    if (foto) URL.revokeObjectURL(foto.url);
    const url = URL.createObjectURL(arquivo);
    const img = new Image();
    img.onload = () => {
      foto = { arquivo, url, largura: img.naturalWidth, altura: img.naturalHeight };
      pista = pistaRef = primeiroPonto = resultado = pontoPlano = null;
      cantos = []; medidasPlano = [];
      alvo = "objeto";
      imagem.src = url;
      quadro.style.setProperty("--proporcao", String(foto.largura / foto.altura));
      area.replaceChildren(palco);
      desenharReferencia(); atualizarTudo();
      palco.focus({ preventScroll: true });
    };
    img.onerror = () => { URL.revokeObjectURL(url); avisar(M.erroMedir, { erro: true }); };
    img.src = url;
  }

  function escolherModo(id) {
    modo = id;
    primeiroPonto = pontoPlano = null;
    alvo = "objeto";
    atualizarTudo();
  }

  function limpar() {
    pista = pistaRef = primeiroPonto = resultado = pontoPlano = null;
    cantos = []; medidasPlano = [];
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
    } else if (ev.key === "Escape" && (primeiroPonto || pontoPlano || alvo === "referencia")) {
      primeiroPonto = pontoPlano = null; alvo = "objeto"; atualizarHud(); desenharCamada();
    }
  });
  palco.addEventListener("focus", () => desenharCamada());
  palco.addEventListener("blur", () => desenharCamada());

  desenharReferencia();
  atualizarTudo();
  desenharVazio();
  return () => { geracao++; if (foto) URL.revokeObjectURL(foto.url); };
}

