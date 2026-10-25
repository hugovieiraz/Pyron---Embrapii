// Ilustrações dos estados (docs/interface/2-direcao.md, 6.1): SVG desenhado aqui, em projeção
// isométrica de 30°, luz de cima à esquerda. Cores só por tokens (--ilu-*, --ferro-*, severidade),
// então o mesmo desenho serve aos dois temas. Uso: ilustracao("captura") devolve um <svg>.
//
// Acabamento: faces com gradiente suave (topo mais claro no fundo, laterais mais escuras no pé),
// filete de luz na aresta da frente do topo e sombra difusa no chão. Toda cena cabe na mesma
// moldura 4:3, assentada no chão, então as legendas ficam na mesma altura.
// Movimento (componentes.css): cada peça (<g class="peca">) desce ao lugar em sequência e o
// acento térmico (<g class="acento">) acende por último; só "procurando" tem movimento contínuo.

const C = Math.cos(Math.PI / 6);
const S = 0.5;
const R2 = Math.SQRT2;
const MOLDURA = 4 / 3;
let sequencia = 0;

/** Ponto no espaço (x para a direita-fundo, y para a esquerda-frente, z para cima) na tela. */
const p = (x, y, z = 0) => [(x - y) * C, (x + y) * S - z];
const f = (v) => v.toFixed(2);

class Cena {
  constructor() {
    this.raiz = [];
    this.destino = this.raiz;
    this.defs = [];
    this.feitos = new Set();
    this.min = [Infinity, Infinity];
    this.max = [-Infinity, -Infinity];
    this.id = `ilu${++sequencia}`;
    this.pecas = 0;
  }
  marcar([x, y]) {
    this.min = [Math.min(this.min[0], x), Math.min(this.min[1], y)];
    this.max = [Math.max(this.max[0], x), Math.max(this.max[1], y)];
  }
  por(svg) {
    this.destino.push(svg);
  }
  /** Agrupa o que fn desenha numa peça que entra sozinha (classe "peca", "chao" ou "acento"). */
  peca(fn, classe = "peca") {
    const antes = this.destino;
    this.destino = [];
    fn(this);
    const corpo = this.destino.join("");
    this.destino = antes;
    this.por(`<g class="${classe}" style="--i:${this.pecas++}">${corpo}</g>`);
  }
  pontos(lista) {
    return lista.map((q) => { this.marcar(q); return `${f(q[0])},${f(q[1])}`; }).join(" ");
  }
  poligono(lista, preenchimento, classe = "") {
    this.por(`<polygon points="${this.pontos(lista)}" style="fill:${preenchimento}" class="${classe}"/>`);
  }
  /** Gradiente de uma face de material ("claro" | "escuro"), criado uma vez por desenho. */
  gradiente(mat, face) {
    const id = `${this.id}-${mat}-${face}`;
    if (!this.feitos.has(id)) {
      this.feitos.add(id);
      const base = `var(--ilu-${mat}-${face})`;
      const [x2, y2, de, ate] = face === "topo"
        ? [1, 1, `color-mix(in srgb, ${base}, var(--ilu-luz) 30%)`, base]
        : [0, 1, base, `color-mix(in srgb, ${base}, var(--ilu-oclusao) ${face === "esq" ? 9 : 13}%)`];
      this.defs.push(`<linearGradient id="${id}" x1="0" y1="0" x2="${x2}" y2="${y2}"><stop offset="0" style="stop-color:${de}"/><stop offset="1" style="stop-color:${ate}"/></linearGradient>`);
    }
    return `url(#${id})`;
  }
  material(mat) {
    if (typeof mat !== "string") return mat;
    return { topo: this.gradiente(mat, "topo"), esq: this.gradiente(mat, "esq"), dir: this.gradiente(mat, "dir"), plano: `var(--ilu-${mat}-topo)` };
  }
  /** Caixa de faces visíveis: topo, esquerda (y+d) e direita (x+w). mat = "claro" | "escuro" | {topo, esq, dir}. */
  caixa(x, y, z, w, d, h, mat = "claro", { frente, brilho = true } = {}) {
    const m = this.material(mat);
    this.poligono([p(x, y + d, z), p(x + w, y + d, z), p(x + w, y + d, z + h), p(x, y + d, z + h)], m.esq, "aresta");
    this.poligono([p(x + w, y, z), p(x + w, y + d, z), p(x + w, y + d, z + h), p(x + w, y, z + h)], m.dir, "aresta");
    this.poligono([p(x, y, z + h), p(x + w, y, z + h), p(x + w, y + d, z + h), p(x, y + d, z + h)], m.topo, "aresta");
    if (brilho && w >= 3 && d >= 3) {
      this.por(`<polyline class="brilho" points="${this.pontos([p(x + 0.4, y + d, z + h), p(x + w, y + d, z + h), p(x + w, y + 0.4, z + h)])}"/>`);
    }
    if (frente) frente(this, { x, y, z, w, d, h });
  }
  /** Retângulo desenhado numa face: plano "esq" (y fixo), "dir" (x fixo) ou "topo" (z fixo). */
  naFace(plano, fixo, a0, b0, a1, b1, preenchimento, classe = "") {
    const q = { esq: (a, b) => p(a, fixo, b), dir: (a, b) => p(fixo, a, b), topo: (a, b) => p(a, b, fixo) }[plano];
    this.poligono([q(a0, b0), q(a1, b0), q(a1, b1), q(a0, b1)], preenchimento, classe);
  }
  linhaNaFace(plano, fixo, a0, b0, a1, b1, cor, espessura = 1.6, classe = "") {
    const q = { esq: (a, b) => p(a, fixo, b), dir: (a, b) => p(fixo, a, b), topo: (a, b) => p(a, b, fixo) }[plano];
    this.por(`<polyline class="${classe}" points="${this.pontos([q(a0, b0), q(a1, b1)])}" style="stroke:${cor};stroke-width:${espessura};stroke-linecap:round;fill:none"/>`);
  }
  traco(lista, cor, espessura = 1.6, juncao = "round") {
    this.por(`<polyline points="${this.pontos(lista)}" style="stroke:${cor};stroke-width:${espessura};stroke-linecap:round;stroke-linejoin:${juncao};fill:none"/>`);
  }
  /** Cilindro vertical: corpo em duas metades (esquerda média, direita escura) e tampa clara. */
  cilindro(cx, cy, z, r, h, mat = "claro") {
    const m = this.material(mat);
    const rx = r * R2 * C;
    const ry = r * R2 * S;
    const [bx, by] = p(cx, cy, z);
    const [tx, ty] = p(cx, cy, z + h);
    [[bx - rx, by], [bx + rx, by], [tx - rx, ty], [tx + rx, ty], [bx, by + ry], [tx, ty - ry]].forEach((q) => this.marcar(q));
    this.por(`<path class="aresta" style="fill:${m.esq}" d="M${f(tx - rx)} ${f(ty)} L${f(bx - rx)} ${f(by)} A${f(rx)} ${f(ry)} 0 0 0 ${f(bx)} ${f(by + ry)} L${f(tx)} ${f(ty + ry)} A${f(rx)} ${f(ry)} 0 0 1 ${f(tx - rx)} ${f(ty)}Z"/>`);
    this.por(`<path class="aresta" style="fill:${m.dir}" d="M${f(tx)} ${f(ty + ry)} L${f(bx)} ${f(by + ry)} A${f(rx)} ${f(ry)} 0 0 0 ${f(bx + rx)} ${f(by)} L${f(tx + rx)} ${f(ty)} A${f(rx)} ${f(ry)} 0 0 1 ${f(tx)} ${f(ty + ry)}Z"/>`);
    this.por(`<ellipse class="aresta" cx="${f(tx)}" cy="${f(ty)}" rx="${f(rx)}" ry="${f(ry)}" style="fill:${m.plano ?? m.topo}"/>`);
  }
  /** Elipse deitada num plano z (aro de lupa, selo, tampa), sem corpo. */
  disco(cx, cy, z, r, preenchimento, classe = "aresta") {
    const [x, y] = p(cx, cy, z);
    const rx = r * R2 * C;
    const ry = r * R2 * S;
    this.marcar([x - rx, y - ry]);
    this.marcar([x + rx, y + ry]);
    this.por(`<ellipse class="${classe}" cx="${f(x)}" cy="${f(y)}" rx="${f(rx)}" ry="${f(ry)}" style="fill:${preenchimento}"/>`);
  }
  /** Visto (sinal de conferido) desenhado reto na tela, centrado no ponto (x, y, z), largura l. */
  visto(x, y, z, l, cor, espessura = 1.6) {
    const [cx, cy] = p(x, y, z);
    this.traco([[cx - l * 0.5, cy], [cx - l * 0.15, cy + l * 0.32], [cx + l * 0.5, cy - l * 0.36]], cor, espessura);
  }
  /** Sombra difusa no chão: escura onde a peça toca, sumindo nas bordas. */
  sombra(cx, cy, r, achatar = 1) {
    const id = `${this.id}-sombra`;
    if (!this.feitos.has(id)) {
      this.feitos.add(id);
      this.defs.push(`<radialGradient id="${id}"><stop offset="0" style="stop-color:var(--ilu-sombra-contato)"/><stop offset=".55" style="stop-color:var(--ilu-sombra)"/><stop offset="1" style="stop-color:var(--ilu-sombra);stop-opacity:0"/></radialGradient>`);
    }
    const [x, y] = p(cx, cy, 0);
    const rx = r * R2 * C * 1.18;
    const ry = r * R2 * S * achatar * 1.18;
    this.marcar([x - rx * 0.8, y - ry * 0.8]);
    this.marcar([x + rx * 0.8, y + ry * 0.8]);
    this.por(`<ellipse cx="${f(x)}" cy="${f(y)}" rx="${f(rx)}" ry="${f(ry)}" style="fill:url(#${id})"/>`);
  }
  /** Ligação pontilhada (pontos separados: o estado "procurando" acende um a um, só com opacidade). */
  pontilhado(lista, passo = 3.2, raio = 0.9, { nos = true } = {}) {
    let n = 0;
    for (let i = 0; i < lista.length - 1; i++) {
      const [x0, y0] = p(...lista[i]);
      const [x1, y1] = p(...lista[i + 1]);
      const k = Math.max(1, Math.round(Math.hypot(x1 - x0, y1 - y0) / passo));
      for (let j = 0; j < k; j++) {
        const x = x0 + (x1 - x0) * (j / k);
        const y = y0 + (y1 - y0) * (j / k);
        this.marcar([x, y]);
        this.por(`<circle cx="${f(x)}" cy="${f(y)}" r="${raio}" style="fill:var(--ilu-ponto);--i:${n++}" class="ponto-ligacao"/>`);
      }
    }
    if (nos) for (const q of [lista[0], lista[lista.length - 1]]) {
      const [x, y] = p(...q);
      this.por(`<ellipse cx="${f(x)}" cy="${f(y)}" rx="2.6" ry="1.6" style="fill:var(--ilu-ponto)"/>`);
    }
  }
  /** Imagem térmica: gradiente da paleta ferro (frio embaixo, quente em cima); devolve o url(). */
  ferro(direcao = "vertical") {
    const id = `${this.id}-ferro-${this.defs.length}`;
    const [x2, y2] = direcao === "vertical" ? ["0", "1"] : ["1", "0"];
    const paradas = [5, 4, 3, 2, 1].map((i, k) => `<stop offset="${(k / 4).toFixed(2)}" style="stop-color:var(--ferro-${i})"/>`).join("");
    this.defs.push(`<linearGradient id="${id}" x1="0" y1="0" x2="${x2}" y2="${y2}">${paradas}</linearGradient>`);
    return `url(#${id})`;
  }
  /** Ponto quente: brilho radial da paleta ferro, achatado como se estivesse na face. */
  pontoQuente(x, y, z, r, achatar = 0.8) {
    const id = `${this.id}-quente-${this.defs.length}`;
    this.defs.push(`<radialGradient id="${id}"><stop offset="0" style="stop-color:var(--ferro-6)"/><stop offset=".3" style="stop-color:var(--ferro-5)"/><stop offset=".65" style="stop-color:var(--ferro-4);stop-opacity:.85"/><stop offset="1" style="stop-color:var(--ferro-3);stop-opacity:0"/></radialGradient>`);
    const [cx, cy] = p(x, y, z);
    this.por(`<ellipse cx="${f(cx)}" cy="${f(cy)}" rx="${f(r * 1.25)}" ry="${f(r * achatar * 1.25)}" style="fill:url(#${id})"/>`);
  }
  /** Moldura 4:3 comum: a cena fica centrada na largura e um pouco abaixo do meio (assentada). */
  svg(rotulo, classe) {
    const folga = 3;
    let [x0, y0] = this.min.map((v) => v - folga);
    let w = this.max[0] - this.min[0] + 2 * folga;
    let h = this.max[1] - this.min[1] + 2 * folga;
    if (w / h > MOLDURA) { const nh = w / MOLDURA; y0 -= (nh - h) * 0.6; h = nh; }
    else { const nw = h * MOLDURA; x0 -= (nw - w) / 2; w = nw; }
    const t = document.createElement("template");
    t.innerHTML = `<svg class="ilustracao ${classe}" viewBox="${f(x0)} ${f(y0)} ${f(w)} ${f(h)}" role="img" aria-label="${rotulo}" xmlns="http://www.w3.org/2000/svg"><defs>${this.defs.join("")}</defs>${this.raiz.join("")}</svg>`;
    return t.content.firstElementChild;
  }
}

// ---------------------------------------------------------------- peças reutilizadas
const PAPEL = { topo: "var(--ilu-tela)", esq: "var(--ilu-claro-esq)", dir: "var(--ilu-claro-dir)" };

/** Isolador de porcelana com saias, sobre base, com terminal no alto. */
function isolador(c, x, y, z, { saias = 5, r = 3, alto = 30 } = {}) {
  c.caixa(x - 5, y - 5, z, 10, 10, 3, "escuro");
  const passo = alto / saias;
  for (let i = 0; i < saias; i++) {
    const zi = z + 3 + i * passo;
    c.cilindro(x, y, zi, r * 0.62, passo * 0.55, "claro");
    c.cilindro(x, y, zi + passo * 0.55, r * 1.45, passo * 0.2, "claro");
  }
  c.cilindro(x, y, z + 3 + alto, r * 0.85, 2.6, "escuro");
  c.cilindro(x, y, z + 5.6 + alto, r * 0.35, 3, "escuro");
}

/** Notebook aberto: base com teclado e tela de pé no fundo. */
function notebook(c, x, y, { tela } = {}) {
  const w = 42, d = 30;
  c.caixa(x, y, 0, w, d, 2.2, "claro");
  c.naFace("topo", 2.2, x + 4, y + 9, x + w - 4, y + 21, "var(--ilu-claro-dir)");
  for (let i = 0; i < 4; i++) c.linhaNaFace("topo", 2.2, x + 6, y + 11.5 + i * 2.6, x + w - 6, y + 11.5 + i * 2.6, "var(--ilu-claro-esq)", 0.9);
  c.naFace("topo", 2.2, x + 15, y + 23, x + w - 15, y + 28, "var(--ilu-claro-esq)");
  c.caixa(x, y - 1.6, 2.2, w, 1.6, 27, "claro", { brilho: false });
  c.naFace("esq", y, x + 2.2, 4.2, x + w - 2.2, 27.4, "var(--ilu-tela)");
  tela?.(c, { x, y, w });
}

/** Termovisor de pistola com a tela virada para quem olha (lente para o fundo à direita), escala k. */
function termovisor(c, x, y, k = 1, { imagem = true } = {}) {
  const b = (dx, dy, dz, w, d, h, mat, op) => c.caixa(x + dx * k, y + dy * k, dz * k, w * k, d * k, h * k, mat, op);
  b(3.5, -6, 23, 8, 6, 8, "escuro", { frente: (cc, q) => cc.naFace("dir", q.x + q.w, q.y + 1.2 * k, q.z + 1.4 * k, q.y + q.d - 1.2 * k, q.z + q.h - 1.4 * k, "var(--ilu-escuro-esq)") });
  b(4.5, 5, 0, 6, 5, 17, "escuro");
  b(4.5, 3.4, 11, 6, 1.6, 4, "escuro", { brilho: false });
  b(0, 0, 17, 15, 10, 17, "escuro", {
    frente: (cc, q) => {
      cc.naFace("esq", q.y + q.d, q.x + 1.2 * k, q.z + 1.2 * k, q.x + q.w - 1.2 * k, q.z + q.h - 1.2 * k, "var(--ilu-escuro-dir)");
      if (imagem) cc.peca(() => cc.naFace("esq", q.y + q.d, q.x + 1.9 * k, q.z + 3.6 * k, q.x + q.w - 1.9 * k, q.z + q.h - 1.9 * k, cc.ferro()), "acento");
      else cc.naFace("esq", q.y + q.d, q.x + 1.9 * k, q.z + 3.6 * k, q.x + q.w - 1.9 * k, q.z + q.h - 1.9 * k, "var(--ilu-escuro-esq)");
      cc.naFace("esq", q.y + q.d, q.x + 5.5 * k, q.z + 1.3 * k, q.x + q.w - 5.5 * k, q.z + 2.6 * k, "var(--ilu-escuro-topo)");
    },
  });
}

/** Folha deitada no chão (ou sobre outra, em z). */
function folha(c, x, y, z, w, d) {
  c.caixa(x, y, z, w, d, 0.7, PAPEL, { brilho: false });
}

// ---------------------------------------------------------------- as cenas
const CENAS = {
  /** Captura sem câmera: termovisor apontado para um isolador de subestação sobre a base. */
  captura(c) {
    c.peca((cc) => { cc.sombra(52, 8, 14, 0.8); cc.sombra(19, 44, 13, 0.75); }, "chao");
    c.peca((cc) => { cc.caixa(40, -4, 0, 24, 24, 3, "claro"); isolador(cc, 52, 8, 3, { saias: 6, alto: 36, r: 3.4 }); });
    c.peca((cc) => cc.pontilhado([[20, 29, 31], [47, 11, 27]], 3.2, 0.85, { nos: false }));
    c.peca((cc) => termovisor(cc, 9, 36, 1.3));
  },

  /** Inspeções sem imagem: pasta aberta com termogramas de pé. */
  inspecoes(c) {
    c.peca((cc) => cc.sombra(24, 18, 28, 0.62), "chao");
    c.peca((cc) => {
      cc.caixa(0, 0, 0, 48, 32, 2, "claro");
      cc.caixa(6, 3, 34, 14, 1.4, 4, "claro", { brilho: false });
      cc.caixa(2, 3, 2, 44, 1.4, 32, "claro", { brilho: false });
    });
    c.peca((cc) => {
      cc.caixa(9, 12, 2, 32, 1.2, 25, "claro", { brilho: false, frente: (k, b) => k.naFace("esq", b.y + b.d, b.x + 2, b.z + 2, b.x + b.w - 2, b.z + b.h - 2, "var(--ilu-escuro-topo)") });
    });
    c.peca((cc) => cc.caixa(13, 21, 2, 32, 1.2, 22, "claro", {
      brilho: false,
      frente: (k, b) => {
        k.naFace("esq", b.y + b.d, b.x + 2, b.z + 2, b.x + b.w - 2, b.z + b.h - 2, k.ferro());
        k.pontoQuente(b.x + 20, b.y + b.d, b.z + 13, 4.2);
      },
    }), "acento");
    c.peca((cc) => cc.caixa(2, 28, 2, 44, 1.4, 13, "claro", {
      brilho: false,
      frente: (k, b) => k.naFace("esq", b.y + b.d, b.x + 4, b.z + 7.5, b.x + 18, b.z + 10.5, "var(--ilu-claro-dir)"),
    }));
  },

  /** Pendências zeradas: prancheta com a lista toda conferida. */
  pendencias(c) {
    c.peca((cc) => cc.sombra(21, 26, 28, 0.6), "chao");
    c.peca((cc) => {
      cc.caixa(2, 2, 0, 38, 50, 2.4, "escuro");
      cc.caixa(5, 8, 2.4, 32, 41, 0.6, PAPEL, { brilho: false });
      cc.caixa(12, 3.5, 2.4, 18, 8, 2.6, "claro");
      cc.caixa(17, 2, 3.6, 8, 3, 1.6, "escuro", { brilho: false });
    });
    const z = 3.0;
    for (let i = 0; i < 4; i++) {
      const y = 16 + i * 8.4;
      c.peca((cc) => {
        cc.naFace("topo", z, 8.2, y - 1.8, 13.4, y + 3.4, "var(--normal-fundo)");
        cc.traco([p(9.2, y + 0.8, z), p(10.8, y + 2.4, z), p(13.4, y - 1.4, z)], "var(--normal)", 1.9, "round");
        cc.linhaNaFace("topo", z, 17, y + 0.8, 33 - (i % 2) * 6, y + 0.8, "var(--ilu-traco)", 1.6);
      }, i === 3 ? "acento" : "peca");
    }
  },

  /** Equipamentos vazio: transformador sobre trilhos, com radiador, buchas e placa de identificação. */
  equipamentos(c) {
    c.peca((cc) => cc.sombra(25, 22, 32, 0.6), "chao");
    c.peca((cc) => {
      cc.caixa(4, 6, 0, 40, 3, 2.4, "escuro", { brilho: false });
      cc.caixa(4, 28, 0, 40, 3, 2.4, "escuro", { brilho: false });
      cc.caixa(2, 4, 2.4, 44, 29, 28, "claro", {
        frente: (k, b) => {
          k.naFace("dir", b.x + b.w, b.y + 8, b.z + 10, b.y + 20, b.z + 19, "var(--ilu-tela)");
          k.linhaNaFace("dir", b.x + b.w, b.y + 10, b.z + 15.6, b.y + 18, b.z + 15.6, "var(--ilu-traco)", 1.2);
          k.linhaNaFace("dir", b.x + b.w, b.y + 10, b.z + 12.8, b.y + 16, b.z + 12.8, "var(--ilu-traco)", 1.2);
        },
      });
    });
    c.peca((cc) => {
      // radiador: dois coletores ligados ao tanque e as aletas penduradas neles
      cc.caixa(5, 33, 24, 36, 3, 1.8, "escuro", { brilho: false });
      cc.caixa(5, 33, 6, 36, 3, 1.8, "escuro", { brilho: false });
      for (let i = 0; i < 5; i++) cc.caixa(7 + i * 7, 33, 5, 2.2, 7, 22, "claro", { brilho: false });
    });
    c.peca((cc) => {
      cc.cilindro(8, 10, 30.4, 3.6, 3, "escuro");
      for (const x of [12, 24, 36]) {
        for (let k = 0; k < 4; k++) {
          cc.cilindro(x, 14, 30.4 + k * 4.2, 1.6, 2.6, "claro");
          cc.cilindro(x, 14, 33 + k * 4.2, 3, 1.1, "claro");
        }
        cc.cilindro(x, 14, 47.4, 1.4, 3, "escuro");
      }
    });
    c.peca((cc) => cc.pontoQuente(12, 14, 50.9, 3.6), "acento");
  },

  /** Sem conexão com o servidor: notebook com o cabo solto da tomada de rede. */
  "sem-conexao"(c) {
    c.peca((cc) => { cc.sombra(29, 22, 30, 0.6); cc.sombra(78, 25, 8, 0.8); }, "chao");
    c.peca((cc) => notebook(cc, 8, 8, {
      tela: (k, { x, y, w }) => {
        k.naFace("esq", y, x + 6, 21, x + 15, 24, "var(--ilu-traco)");
        for (let i = 0; i < 4; i++) k.linhaNaFace("esq", y, x + 6, 17.5 - i * 3.4, x + w - 10 - (i % 3) * 5, 17.5 - i * 3.4, "var(--ilu-traco)", 1.3);
      },
    }));
    c.peca((cc) => cc.caixa(74, 20, 0, 9, 9, 9, "claro", { frente: (k, b) => k.naFace("esq", b.y + b.d, b.x + 2.8, b.z + 2.8, b.x + 6.2, b.z + 6.2, "var(--ilu-escuro-dir)") }));
    c.peca((cc) => {
      cc.traco([p(50, 26, 1.2), p(55, 31, 1.2), p(61, 33, 1.2), p(64, 34, 1.2)], "var(--ilu-escuro-esq)", 2.2);
      cc.caixa(64, 32.6, 0.2, 4.4, 3, 2.6, "escuro", { brilho: false });
    });
    c.peca((cc) => {
      cc.caixa(68.4, 33.2, 0.9, 1.4, 1.8, 1.2, { topo: "var(--urgente)", esq: "var(--urgente)", dir: "var(--urgente-texto)" }, { brilho: false });
      cc.pontilhado([[71, 33, 1.6], [78.4, 29, 4.4]], 2.4, 0.7, { nos: false });
    }, "acento");
  },

  /** Modelos sem detector: placa de processamento com o chip e componentes. */
  modelos(c) {
    c.peca((cc) => cc.sombra(25, 22, 30, 0.6), "chao");
    c.peca((cc) => {
      cc.caixa(2, 2, 0, 46, 40, 2, "claro");
      for (let i = 0; i < 6; i++) {
        cc.linhaNaFace("topo", 2, 6, 8 + i * 5.6, 15, 8 + i * 5.6, "var(--ilu-traco)", 1.1);
        cc.linhaNaFace("topo", 2, 35, 8 + i * 5.6, 44, 8 + i * 5.6, "var(--ilu-traco)", 1.1);
      }
      for (const [x, y] of [[8, 38], [14, 38], [40, 6]]) cc.cilindro(x, y, 2, 1.5, 2.6, "escuro");
      cc.caixa(38, 34, 2, 7, 5, 1.6, "escuro");
    });
    c.peca((cc) => {
      for (let i = 0; i < 5; i++) cc.caixa(15.4, 10 + i * 5.6, 2, 2.2, 1.4, 1, "escuro", { brilho: false });
      cc.caixa(17.6, 9, 2, 14.8, 26, 4.5, "escuro");
      for (let i = 0; i < 5; i++) cc.caixa(32.4, 10 + i * 5.6, 2, 2.2, 1.4, 1, "escuro", { brilho: false });
    });
    c.peca((cc) => cc.naFace("topo", 6.5, 20.2, 13, 29.8, 31, cc.ferro()), "acento");
  },

  /** Análise sem regiões (ou processando): termograma de pé com a mira em volta do ponto quente. */
  analise(c) {
    c.peca((cc) => cc.sombra(24, 22, 26, 0.62), "chao");
    c.peca((cc) => {
      cc.caixa(16, 14, 0, 16, 12, 3, "escuro");
      cc.caixa(22, 16, 3, 4, 3, 10, "escuro", { brilho: false });
    });
    let tela;
    c.peca((cc) => cc.caixa(2, 19, 6, 44, 2, 32, "claro", {
      brilho: false,
      frente: (k, b) => { tela = b; k.naFace("esq", b.y + b.d, b.x + 2, b.z + 2, b.x + b.w - 2, b.z + b.h - 2, "var(--ilu-escuro-dir)"); },
    }));
    c.peca((cc) => {
      const y = tela.y + tela.d;
      cc.naFace("esq", y, tela.x + 2, tela.z + 2, tela.x + tela.w - 2, tela.z + tela.h - 2, cc.ferro());
      cc.pontoQuente(tela.x + 27, y, tela.z + 18, 5.2);
      // mira: quatro cantos em volta do ponto quente
      const [a0, b0, a1, b1, L] = [tela.x + 19, tela.z + 11, tela.x + 35, tela.z + 25, 3.4];
      for (const [a, b, da, db] of [[a0, b0, 1, 1], [a1, b0, -1, 1], [a0, b1, 1, -1], [a1, b1, -1, -1]]) {
        cc.linhaNaFace("esq", y, a, b, a + da * L, b, "var(--ilu-tela)", 1.3);
        cc.linhaNaFace("esq", y, a, b, a, b + db * L, "var(--ilu-tela)", 1.3);
      }
      // linhas de varredura: só aparecem, uma a uma, no estado "procurando" (processando)
      for (let i = 0; i < 6; i++) {
        const z = tela.z + tela.h - 5 - i * 4.4;
        cc.por(`<g class="varredura" style="--i:${i}">`);
        cc.linhaNaFace("esq", y, tela.x + 3, z, tela.x + tela.w - 3, z, "var(--ilu-tela)", 0.8);
        cc.por("</g>");
      }
    }, "acento");
  },

  /** Laudo pronto: folha com cabeçalho, termograma, texto e o carimbo de conferido. */
  laudo(c) {
    c.peca((cc) => cc.sombra(22, 24, 27, 0.6), "chao");
    c.peca((cc) => { folha(cc, 6, 2, 0, 32, 44); folha(cc, 4, 4, 0.7, 32, 44); });
    c.peca((cc) => {
      const z = 1.4;
      cc.naFace("topo", z, 7, 7, 33, 10, "var(--ilu-escuro-esq)");
      for (let i = 0; i < 3; i++) cc.linhaNaFace("topo", z, 21, 15 + i * 3.2, 33 - (i % 2) * 4, 15 + i * 3.2, "var(--ilu-traco)", 1.2);
      for (let i = 0; i < 4; i++) cc.linhaNaFace("topo", z, 8, 28 + i * 3.2, 33 - (i % 3) * 5, 28 + i * 3.2, "var(--ilu-traco)", 1.2);
    });
    c.peca((cc) => cc.naFace("topo", 1.4, 8, 13, 18, 23, cc.ferro()), "acento");
    c.peca((cc) => {
      cc.cilindro(29, 41, 1.4, 4.2, 0.6, "escuro");
      cc.visto(29, 41, 2.0, 6, "var(--ilu-tela)", 1.5);
    });
  },

  /** Busca sem resultado: lupa deitada sobre uma folha em branco. */
  busca(c) {
    c.peca((cc) => cc.sombra(24, 22, 28, 0.6), "chao");
    c.peca((cc) => {
      folha(cc, 4, 4, 0, 34, 42);
      for (let i = 0; i < 5; i++) cc.linhaNaFace("topo", 0.7, 8, 9 + i * 3.4, 34 - (i % 2) * 6, 9 + i * 3.4, "var(--ilu-traco)", 1.2);
    });
    c.peca((cc) => {
      cc.caixa(30, 29.4, 0.7, 18, 3.6, 2.2, "escuro");
      cc.cilindro(22, 31, 0.7, 10, 2.2, "escuro");
      cc.disco(22, 31, 2.9, 8, "var(--ilu-tela)");
      cc.disco(20.6, 29.6, 2.9, 3.4, "var(--ilu-luz)", "");
    });
  },

  /** Conectar o celular: telefone de pé com o código na tela, ligado ao notebook pelo pontilhado. */
  celular(c) {
    c.peca((cc) => { cc.sombra(48, 14, 28, 0.6); cc.sombra(12, 39, 12, 0.8); }, "chao");
    c.peca((cc) => notebook(cc, 30, -4, {
      tela: (k, { x, y, w }) => k.peca(() => k.naFace("esq", y, x + 6, 8, x + w - 6, 24, k.ferro()), "acento"),
    }));
    c.peca((cc) => cc.pontilhado([[16, 32, 18], [38, 0, 14]], 3.2, 0.85, { nos: false }));
    c.peca((cc) => {
      cc.caixa(2, 34, 0, 19, 9, 2.4, "escuro");
      cc.caixa(4, 38, 2.4, 15, 2, 29, "escuro", {
        frente: (k, b) => {
          const y = b.y + b.d;
          k.naFace("esq", y, b.x + 1, b.z + 1.6, b.x + b.w - 1, b.z + b.h - 2.4, "var(--ilu-tela)");
          // código para o celular ler: três quadros de canto e um miolo fixo
          const q = (a, z, n) => k.naFace("esq", y, a, z, a + n, z + n, "var(--ilu-escuro-dir)");
          const [a0, z0, u] = [b.x + 2.6, b.z + 8, 1.4];
          for (const [i, j] of [[0, 0], [0, 5], [5, 5]]) { q(a0 + i * u, z0 + j * u, 2 * u); }
          for (const [i, j] of [[3, 1], [4, 3], [3, 4], [6, 2], [5, 0], [2, 3], [6, 0]]) q(a0 + i * u, z0 + j * u, u);
        },
      });
    });
  },
};

export const NOMES_ILUSTRACOES = Object.keys(CENAS);

/** ilustracao(nome, { rotulo, procurando }): procurando acende o pontilhado e a varredura em sequência (indicador). */
export function ilustracao(nome, { rotulo = "", procurando = false } = {}) {
  const c = new Cena();
  CENAS[nome](c);
  return c.svg(rotulo, `ilu-${nome}${procurando ? " procurando" : ""}`);
}
