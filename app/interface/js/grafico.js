// Gráfico de uma série no tempo (máxima do equipamento por inspeção). Uma série, um eixo: linha neutra de
// 2 px, pontos na cor da severidade com anel da superfície, grade fina, reta de tendência tracejada e a
// dica ao passar o mouse ou focar o ponto. Redesenha na largura real (texto sempre em 14 px).
import { TEXTOS as T } from "../textos.js";
import { el, icone, fmt, data as dataCurta } from "./base.js";
import { ESQUENTANDO } from "./situacao.js";

const SVG = "http://www.w3.org/2000/svg";
const s = (tag, attrs = {}, ...filhos) => {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  n.append(...filhos);
  return n;
};

/** Passo "redondo" para a escala (1, 2, 5 × 10ⁿ) com cerca de 4 divisões. */
function marcasY(min, max) {
  const bruto = (max - min) / 4 || 1;
  const base = 10 ** Math.floor(Math.log10(bruto));
  const passo = [1, 2, 5, 10].map((m) => m * base).find((p) => p >= bruto);
  const lo = Math.floor(min / passo) * passo;
  const hi = Math.ceil(max / passo) * passo;
  const marcas = [];
  for (let v = lo; v <= hi + passo / 2; v += passo) marcas.push(+v.toFixed(6));
  return marcas;
}

/** Reta de mínimos quadrados sobre (tempo, valor): a mesma conta do servidor, só para desenhar. */
function reta(pts) {
  if (pts.length < 3) return null;
  const xs = pts.map((p) => p.t), ys = pts.map((p) => p.valor);
  const mx = xs.reduce((a, b) => a + b) / xs.length, my = ys.reduce((a, b) => a + b) / ys.length;
  const sxx = xs.reduce((a, x) => a + (x - mx) ** 2, 0);
  if (!sxx) return null;
  const k = xs.reduce((a, x, i) => a + (x - mx) * (ys[i] - my), 0) / sxx;
  return (t) => my + k * (t - mx);
}

/** Eixo x em datas (padrão): o valor é o instante em ms; uma data só abre meio mês para cada lado. */
const EIXO_DATAS = { de: (p) => Date.parse(p.data), rotulo: (t) => dataCurta(new Date(t).toISOString()), folga: 864e5 * 15 };

/**
 * graficoSerie({ titulo, pontos: [{ id, data, valor, severidade, rotulo }], unidade, tendencia, href(p), aoEscolher(p),
 *                eixo: { de(p), rotulo(v), folga }, comPonto(p), aoClicar(x) })
 * Devolve { no, encerrar, cursor(x) }. Pontos sem valor ficam de fora (inspeção sem temperatura).
 * comPonto escolhe quais pontos ganham marca (vídeo: só os fora do normal); aoClicar recebe o x do clique no traçado.
 */
export function graficoSerie({ titulo, pontos, unidade = " °C", tendencia = false, href, aoEscolher, eixo = EIXO_DATAS, comPonto = () => true, aoClicar }) {
  const area = el("div", { class: "grafico-area" });
  const dica = el("div", { class: "dica-grafico", role: "status", hidden: true });
  const no = el("figure", { class: "grafico" }, area, dica);
  const pts = pontos.filter((p) => p.valor != null).map((p) => ({ ...p, t: eixo.de(p) })).sort((a, b) => a.t - b.t);
  let escalaX = null;
  let marcaCursor = null;
  let posCursor = null;

  function desenhar() {
    const L = Math.round(area.clientWidth), A = Math.round(area.clientHeight);
    if (!L || !A || !pts.length) { area.replaceChildren(); return; }
    const m = { e: 52, d: 72, t: 16, b: 36 };
    let [t0, t1] = [pts[0].t, pts[pts.length - 1].t];
    if (t1 - t0 < (eixo.folga || 1) / 15) { t0 -= eixo.folga || 1; t1 += eixo.folga || 1; }
    const vs = pts.map((p) => p.valor);
    const marcas = marcasY(Math.min(...vs), Math.max(...vs));
    const [lo, hi] = [marcas[0], marcas[marcas.length - 1]];
    const x = (t) => m.e + ((t - t0) / (t1 - t0)) * (L - m.e - m.d);
    const y = (v) => m.t + (1 - (v - lo) / (hi - lo || 1)) * (A - m.t - m.b);
    escalaX = { x, inverso: (px) => t0 + ((px - m.e) / (L - m.e - m.d)) * (t1 - t0) };

    const svg = s("svg", { width: L, height: A, viewBox: `0 0 ${L} ${A}`, role: href || aoEscolher ? "group" : "img", "aria-label": titulo }); // com pontos que abrem a inspeção, é um grupo (img não pode ter botões dentro)
    for (const v of marcas) {
      svg.append(s("line", { x1: m.e, x2: L - m.d, y1: y(v), y2: y(v), class: "grade" }),
        s("text", { x: m.e - 8, y: y(v), class: "eixo", "text-anchor": "end", "dominant-baseline": "middle" }, fmt(v, 0)));
    }
    // rótulos do eixo x: os dos pontos (um por rótulo), pulando os que ficariam a menos de 96 px do anterior;
    // com muitos pontos (vídeo), início, meio e fim
    const unicos = pts.length > 60 ? [t0, (t0 + t1) / 2, t1] : [...new Map(pts.map((p) => [eixo.rotulo(p.t), p.t])).values()];
    const rotulos = [];
    for (const t of unicos) if (!rotulos.length || x(t) - x(rotulos[rotulos.length - 1]) >= 96) rotulos.push(t);
    if (rotulos.length > 1 && x(unicos[unicos.length - 1]) - x(rotulos[rotulos.length - 2]) >= 96) rotulos[rotulos.length - 1] = unicos[unicos.length - 1];
    rotulos.forEach((t, i) => svg.append(s("text", { x: x(t), y: A - 10, class: "eixo", "text-anchor": rotulos.length > 1 && i === 0 ? "start" : i === rotulos.length - 1 && rotulos.length > 1 ? "end" : "middle" }, eixo.rotulo(t))));

    const f = tendencia ? reta(pts) : null;
    if (f) svg.append(s("line", { x1: x(pts[0].t), y1: y(f(pts[0].t)), x2: x(pts[pts.length - 1].t), y2: y(f(pts[pts.length - 1].t)), class: "reta-tendencia" }));
    if (pts.length > 1) svg.append(s("path", { d: pts.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)} ${y(p.valor).toFixed(1)}`).join(" "), class: "linha-serie" }));
    if (aoClicar) {
      const fundo = s("rect", { x: m.e, y: m.t, width: L - m.e - m.d, height: A - m.t - m.b, class: "fundo-clicavel" });
      fundo.addEventListener("click", (ev) => aoClicar(escalaX.inverso(ev.clientX - svg.getBoundingClientRect().left)));
      svg.append(fundo);
    }
    const cruz = s("line", { y1: m.t, y2: A - m.b, class: "cruz", visibility: "hidden" });
    marcaCursor = s("line", { y1: m.t, y2: A - m.b, class: "cursor-grafico", visibility: "hidden" });
    svg.append(cruz, marcaCursor);

    for (const p of pts.filter(comPonto)) {
      const texto = T.grafico.ponto(eixo.rotulo(p.t), fmt(p.valor, 1, unidade), T.niveis[p.severidade] || p.severidade);
      const ponto = s("circle", { cx: x(p.t), cy: y(p.valor), r: 5, class: "ponto-serie", style: `--sev: var(--${p.severidade || "sem_medida"})` });
      const alvo = s("circle", { cx: x(p.t), cy: y(p.valor), r: 22, class: "alvo-ponto" }); // 44 px de alvo
      const g = href ? s("a", { href: href(p), "aria-label": texto }, alvo, ponto)
        : aoEscolher ? s("g", { tabindex: "0", role: "button", "aria-label": texto, class: "ponto-escolher" }, alvo, ponto) : s("g", {}, alvo, ponto);
      if (aoEscolher && !href) {
        g.addEventListener("click", () => aoEscolher(p));
        g.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); aoEscolher(p); } });
      }
      const mostrar = () => {
        cruz.setAttribute("x1", x(p.t)); cruz.setAttribute("x2", x(p.t)); cruz.setAttribute("visibility", "visible");
        dica.replaceChildren(el("b", {}, fmt(p.valor, 1, unidade)), el("span", {}, eixo.rotulo(p.t)), el("span", {}, [T.niveis[p.severidade], p.rotulo].filter(Boolean).join(", ")));
        dica.hidden = false;
        const esq = x(p.t) + 12 + dica.offsetWidth > L ? x(p.t) - 12 - dica.offsetWidth : x(p.t) + 12;
        dica.style.transform = `translate(${Math.round(esq)}px, ${Math.round(Math.max(0, y(p.valor) - dica.offsetHeight / 2))}px)`;
      };
      const esconder = () => { cruz.setAttribute("visibility", "hidden"); dica.hidden = true; };
      g.addEventListener("pointerenter", mostrar);
      g.addEventListener("pointerleave", esconder);
      g.addEventListener("focus", mostrar);
      g.addEventListener("blur", esconder);
      svg.append(g);
    }
    // rótulo direto só no último ponto (o valor que importa agora)
    const u = pts[pts.length - 1];
    svg.append(s("text", { x: x(u.t) + 12, y: y(u.valor), class: "rotulo-fim", "dominant-baseline": "middle" }, fmt(u.valor, 1, unidade)));
    area.replaceChildren(svg);
    if (posCursor != null) cursor(posCursor);
  }

  /** Linha vertical no instante x (o quadro na tela do vídeo); null esconde. */
  function cursor(t) {
    posCursor = t;
    if (!marcaCursor || !escalaX) return;
    if (t == null) { marcaCursor.setAttribute("visibility", "hidden"); return; }
    const px = escalaX.x(t);
    marcaCursor.setAttribute("x1", px); marcaCursor.setAttribute("x2", px); marcaCursor.setAttribute("visibility", "visible");
  }

  const observador = new ResizeObserver(() => desenhar());
  observador.observe(area);
  return { no, cursor, encerrar: () => observador.disconnect() };
}

/** Tendência da máxima em °C por mês, com seta; sem pontos suficientes, diz por quê no title. */
export function seloTendencia(t) {
  const E = T.equipamentos;
  if (!t) return el("span", { class: "tendencia fraco", title: E.semTendenciaDica }, E.semTendencia);
  const v = t.por_mes;
  const tipo = v > ESQUENTANDO ? "sobe" : v < -ESQUENTANDO ? "desce" : "estavel";
  const titulo = E.tendenciaDica(fmt(t.r2, 2), t.n) + (t.r2 < 0.3 ? E.tendenciaInstavel : "");
  return el("span", { class: `tendencia ${tipo}`, title: titulo }, icone(tipo, "ic p"), E.porMes(`${v > 0 ? "+" : ""}${fmt(v, 1)}`));
}

/** Linha pequena da máxima por inspeção (sem eixo); o último ponto na cor da severidade. */
export function miniSerie(serie) {
  const pts = serie.filter((p) => p.t_max != null);
  const L = 96, A = 28, m = 4;
  const svg = s("svg", { width: L, height: A, viewBox: `0 0 ${L} ${A}`, class: "mini-serie", "aria-hidden": "true" });
  if (!pts.length) return svg;
  const ts = pts.map((p) => Date.parse(p.data)), vs = pts.map((p) => p.t_max);
  const [t0, t1, v0, v1] = [Math.min(...ts), Math.max(...ts), Math.min(...vs), Math.max(...vs)];
  const x = (t) => (t1 > t0 ? m + ((t - t0) / (t1 - t0)) * (L - 2 * m) : L / 2);
  const y = (v) => (v1 > v0 ? A - m - ((v - v0) / (v1 - v0)) * (A - 2 * m) : A / 2);
  if (pts.length > 1) svg.append(s("path", { d: pts.map((p, i) => `${i ? "L" : "M"}${x(ts[i]).toFixed(1)} ${y(p.t_max).toFixed(1)}`).join(" "), class: "linha-serie" }));
  const u = pts.length - 1;
  svg.append(s("circle", { cx: x(ts[u]), cy: y(vs[u]), r: 4, class: "ponto-serie", style: `--sev: var(--${pts[u].severidade || "sem_medida"})` }));
  return svg;
}
