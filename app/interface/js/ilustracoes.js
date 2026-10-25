// Ilustrações dos estados (docs/interface/2-direcao.md, 6.1): SVG desenhado aqui, em projeção
// isométrica de 30°, luz de cima à esquerda. Cores só por tokens (--ilu-*, --ferro-*, severidade),
// então o mesmo desenho serve aos dois temas. Uso: ilustracao("captura") devolve um <svg>.

const C = Math.cos(Math.PI / 6);
const S = 0.5;
const R2 = Math.SQRT2;
let sequencia = 0;

/** Ponto no espaço (x para a direita-fundo, y para a esquerda-frente, z para cima) na tela. */
const p = (x, y, z = 0) => [(x - y) * C, (x + y) * S - z];

class Cena {
  constructor() {
    this.partes = [];
    this.defs = [];
    this.min = [Infinity, Infinity];
    this.max = [-Infinity, -Infinity];
    this.id = `ilu${++sequencia}`;
  }
  marcar([x, y]) {
    this.min = [Math.min(this.min[0], x), Math.min(this.min[1], y)];
    this.max = [Math.max(this.max[0], x), Math.max(this.max[1], y)];
  }
  pontos(lista) {
    return lista.map((q) => { this.marcar(q); return `${q[0].toFixed(2)},${q[1].toFixed(2)}`; }).join(" ");
  }
  poligono(lista, preenchimento, classe = "") {
    this.partes.push(`<polygon points="${this.pontos(lista)}" style="fill:${preenchimento}" class="${classe}"/>`);
  }
  /** Caixa de faces visíveis: topo, esquerda (y+d) e direita (x+w). mat = "claro" | "escuro" | {topo, esq, dir}. */
  caixa(x, y, z, w, d, h, mat = "claro", { frente } = {}) {
    const m = typeof mat === "string" ? { topo: `var(--ilu-${mat}-topo)`, esq: `var(--ilu-${mat}-esq)`, dir: `var(--ilu-${mat}-dir)` } : mat;
    this.poligono([p(x, y + d, z), p(x + w, y + d, z), p(x + w, y + d, z + h), p(x, y + d, z + h)], m.esq, "aresta");
    this.poligono([p(x + w, y, z), p(x + w, y + d, z), p(x + w, y + d, z + h), p(x + w, y, z + h)], m.dir, "aresta");
    this.poligono([p(x, y, z + h), p(x + w, y, z + h), p(x + w, y + d, z + h), p(x, y + d, z + h)], m.topo, "aresta");
    if (frente) frente(this, { x, y, z, w, d, h });
  }
  /** Retângulo desenhado numa face: plano "esq" (y fixo), "dir" (x fixo) ou "topo" (z fixo). */
  naFace(plano, fixo, a0, b0, a1, b1, preenchimento, classe = "") {
    const q = { esq: (a, b) => p(a, fixo, b), dir: (a, b) => p(fixo, a, b), topo: (a, b) => p(a, b, fixo) }[plano];
    this.poligono([q(a0, b0), q(a1, b0), q(a1, b1), q(a0, b1)], preenchimento, classe);
  }
  linhaNaFace(plano, fixo, a0, b0, a1, b1, cor, espessura = 1.6) {
    const q = { esq: (a, b) => p(a, fixo, b), dir: (a, b) => p(fixo, a, b), topo: (a, b) => p(a, b, fixo) }[plano];
    this.partes.push(`<polyline points="${this.pontos([q(a0, b0), q(a1, b1)])}" style="stroke:${cor};stroke-width:${espessura};stroke-linecap:round;fill:none"/>`);
  }
  traco(lista, cor, espessura = 1.6, juncao = "round") {
    this.partes.push(`<polyline points="${this.pontos(lista)}" style="stroke:${cor};stroke-width:${espessura};stroke-linecap:round;stroke-linejoin:${juncao};fill:none"/>`);
  }
  /** Cilindro vertical: corpo em duas metades (esquerda média, direita escura) e tampa clara. */
  cilindro(cx, cy, z, r, h, mat = "claro") {
    const m = typeof mat === "string" ? { topo: `var(--ilu-${mat}-topo)`, esq: `var(--ilu-${mat}-esq)`, dir: `var(--ilu-${mat}-dir)` } : mat;
    const rx = r * R2 * C;
    const ry = r * R2 * S;
    const [bx, by] = p(cx, cy, z);
    const [tx, ty] = p(cx, cy, z + h);
    [[bx - rx, by], [bx + rx, by], [tx - rx, ty], [tx + rx, ty], [bx, by + ry]].forEach((q) => this.marcar(q));
    const f = (v) => v.toFixed(2);
    this.partes.push(`<path class="aresta" style="fill:${m.esq}" d="M${f(tx - rx)} ${f(ty)} L${f(bx - rx)} ${f(by)} A${f(rx)} ${f(ry)} 0 0 0 ${f(bx)} ${f(by + ry)} L${f(tx)} ${f(ty + ry)} A${f(rx)} ${f(ry)} 0 0 1 ${f(tx - rx)} ${f(ty)}Z"/>`);
    this.partes.push(`<path class="aresta" style="fill:${m.dir}" d="M${f(tx)} ${f(ty + ry)} L${f(bx)} ${f(by + ry)} A${f(rx)} ${f(ry)} 0 0 0 ${f(bx + rx)} ${f(by)} L${f(tx + rx)} ${f(ty)} A${f(rx)} ${f(ry)} 0 0 1 ${f(tx)} ${f(ty + ry)}Z"/>`);
    this.partes.push(`<ellipse class="aresta" cx="${f(tx)}" cy="${f(ty)}" rx="${f(rx)}" ry="${f(ry)}" style="fill:${m.topo}"/>`);
  }
  /** Sombra suave no chão (elipse no plano z = 0). */
  sombra(cx, cy, r, achatar = 1) {
    const [x, y] = p(cx, cy, 0);
    const rx = r * R2 * C;
    const ry = r * R2 * S * achatar;
    this.marcar([x - rx, y - ry]);
    this.marcar([x + rx, y + ry]);
    this.partes.push(`<ellipse cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" rx="${rx.toFixed(2)}" ry="${ry.toFixed(2)}" style="fill:var(--ilu-sombra)" class="sombra-chao"/>`);
  }
  /** Ligação pontilhada (pontos separados: o estado "procurando" acende um a um, só com opacidade). */
  pontilhado(lista, passo = 3.2, raio = 0.9, { nos = true } = {}) {
    const trechos = [];
    for (let i = 0; i < lista.length - 1; i++) trechos.push([p(...lista[i]), p(...lista[i + 1])]);
    let n = 0;
    for (const [[x0, y0], [x1, y1]] of trechos) {
      const comp = Math.hypot(x1 - x0, y1 - y0);
      const k = Math.max(1, Math.round(comp / passo));
      for (let j = 0; j < k; j++) {
        const t = j / k;
        const x = x0 + (x1 - x0) * t;
        const y = y0 + (y1 - y0) * t;
        this.marcar([x, y]);
        this.partes.push(`<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="${raio}" style="fill:var(--ilu-ponto);--i:${n++}" class="ponto-ligacao"/>`);
      }
    }
    if (nos) for (const q of [lista[0], lista[lista.length - 1]]) {
      const [x, y] = p(...q);
      this.partes.push(`<ellipse cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" rx="2.6" ry="1.6" style="fill:var(--ilu-ponto)"/>`);
    }
  }
  /** Gradiente da paleta ferro (o acento térmico); devolve o url() para usar como preenchimento. */
  ferro(direcao = "vertical") {
    const id = `${this.id}-ferro-${this.defs.length}`;
    const [x2, y2] = direcao === "vertical" ? ["0", "1"] : ["1", "0"];
    const paradas = [6, 5, 4, 3, 2, 1].map((i, k) => `<stop offset="${(k / 5).toFixed(2)}" style="stop-color:var(--ferro-${i})"/>`).join("");
    this.defs.push(`<linearGradient id="${id}" x1="0" y1="0" x2="${x2}" y2="${y2}">${paradas}</linearGradient>`);
    return `url(#${id})`;
  }
  /** Ponto quente: brilho radial da paleta ferro. */
  pontoQuente(x, y, z, r) {
    const id = `${this.id}-quente-${this.defs.length}`;
    this.defs.push(`<radialGradient id="${id}"><stop offset="0" style="stop-color:var(--ferro-6)"/><stop offset=".35" style="stop-color:var(--ferro-5)"/><stop offset=".7" style="stop-color:var(--ferro-4);stop-opacity:.85"/><stop offset="1" style="stop-color:var(--ferro-3);stop-opacity:0"/></radialGradient>`);
    const [cx, cy] = p(x, y, z);
    this.partes.push(`<ellipse cx="${cx.toFixed(2)}" cy="${cy.toFixed(2)}" rx="${(r * 1.25).toFixed(2)}" ry="${r.toFixed(2)}" style="fill:url(#${id})"/>`);
  }
  svg(rotulo, classe) {
    const folga = 4;
    const [x0, y0] = this.min.map((v) => v - folga);
    const [x1, y1] = this.max.map((v) => v + folga);
    const vb = `${x0.toFixed(1)} ${y0.toFixed(1)} ${(x1 - x0).toFixed(1)} ${(y1 - y0).toFixed(1)}`;
    const t = document.createElement("template");
    t.innerHTML = `<svg class="ilustracao ${classe}" viewBox="${vb}" role="img" aria-label="${rotulo}" xmlns="http://www.w3.org/2000/svg"><defs>${this.defs.join("")}</defs>${this.partes.join("")}</svg>`;
    return t.content.firstElementChild;
  }
}

// ---------------------------------------------------------------- peças reutilizadas
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
  c.caixa(x, y - 1.6, 2.2, w, 1.6, 27, "claro");
  c.naFace("esq", y, x + 2.2, 4.2, x + w - 2.2, 27.4, "var(--ilu-tela)");
  tela?.(c, { x, y, w });
}

// ---------------------------------------------------------------- as seis cenas
const CENAS = {
  /** Captura sem câmera: termovisor de pistola apontado para um isolador de subestação. */
  captura(c) {
    c.sombra(64, 4, 11, 0.9);
    c.sombra(16, 42, 10, 0.8);
    isolador(c, 64, 4, 0, { saias: 6, alto: 34 });
    // lente saindo da frente do corpo, na direção do isolador (desenhada antes: fica atrás do corpo)
    c.caixa(13.5, 31, 23, 8, 6, 8, "escuro", { frente: (cc, b) => cc.naFace("dir", b.x + b.w, b.y + 1.2, b.z + 1.4, b.y + b.d - 1.2, b.z + b.h - 1.4, "var(--ilu-escuro-esq)") });
    c.pontilhado([[19, 31, 28], [58, 7, 26]], 3.4, 0.85, { nos: false });
    // punho com gatilho, depois o corpo fino com a tela grande atrás (o único acento: a imagem térmica)
    c.caixa(14.5, 42, 0, 6, 5, 17, "escuro");
    c.caixa(14.5, 40.4, 11, 6, 1.6, 4, "escuro");
    c.caixa(10, 37, 17, 15, 10, 17, "escuro", {
      frente: (cc, b) => {
        cc.naFace("esq", b.y + b.d, b.x + 1.2, b.z + 1.2, b.x + b.w - 1.2, b.z + b.h - 1.2, "var(--ilu-escuro-dir)");
        cc.naFace("esq", b.y + b.d, b.x + 1.9, b.z + 3.6, b.x + b.w - 1.9, b.z + b.h - 1.9, cc.ferro());
        cc.naFace("esq", b.y + b.d, b.x + 5.5, b.z + 1.3, b.x + b.w - 5.5, b.z + 2.6, "var(--ilu-escuro-topo)");
      },
    });
  },

  /** Inspeções sem imagem: pasta com termogramas. */
  inspecoes(c) {
    c.sombra(24, 20, 26, 0.7);
    c.caixa(2, 2, 0, 44, 30, 3, "claro");
    // termogramas de pé dentro da pasta, do fundo para a frente; o da frente com a imagem térmica
    c.caixa(8, 8, 3, 30, 1.2, 26, "claro", { frente: (cc, b) => cc.naFace("esq", b.y + b.d, b.x + 2, b.z + 2, b.x + b.w - 2, b.z + b.h - 2, "var(--ilu-claro-esq)") });
    c.caixa(10, 13, 3, 30, 1.2, 24, "claro", { frente: (cc, b) => cc.naFace("esq", b.y + b.d, b.x + 2, b.z + 2, b.x + b.w - 2, b.z + b.h - 2, "var(--ilu-claro-dir)") });
    c.caixa(12, 18, 3, 30, 1.2, 22, "claro", { frente: (cc, b) => cc.naFace("esq", b.y + b.d, b.x + 2, b.z + 2, b.x + b.w - 2, b.z + b.h - 2, cc.ferro()) });
    // aba da frente da pasta
    c.caixa(2, 24, 3, 44, 8, 12, "claro", {
      frente: (cc, b) => {
        cc.naFace("esq", b.y + b.d, b.x + 4, b.z + 6, b.x + 18, b.z + 9, "var(--ilu-claro-dir)");
      },
    });
  },

  /** Pendências zeradas: prancheta com a lista toda conferida. */
  pendencias(c) {
    c.sombra(22, 24, 26, 0.6);
    c.caixa(2, 2, 0, 38, 48, 2.4, "escuro");
    c.caixa(5, 6, 2.4, 32, 41, 0.6, { topo: "var(--ilu-tela)", esq: "var(--ilu-claro-esq)", dir: "var(--ilu-claro-dir)" });
    c.caixa(13, 0, 2.4, 16, 6, 3.2, "claro");
    const z = 3.0;
    for (let i = 0; i < 4; i++) {
      const y = 13 + i * 8.5;
      c.traco([p(9, y + 1.4, z), p(10.6, y + 3, z), p(13.6, y - 0.6, z)], "var(--normal)", 1.9, "round");
      c.linhaNaFace("topo", z, 17, y + 1.2, 33 - (i % 2) * 6, y + 1.2, "var(--ilu-traco)", 1.6);
    }
  },

  /** Equipamentos vazio: transformador com a etiqueta de identificação. */
  equipamentos(c) {
    c.sombra(26, 20, 30, 0.6);
    c.caixa(2, 4, 0, 44, 29, 30, "claro", {
      frente: (cc, b) => {
        // etiqueta de identificação na lateral direita
        cc.naFace("dir", b.x + b.w, b.y + 8, b.z + 10, b.y + 20, b.z + 19, "var(--ilu-tela)");
        cc.linhaNaFace("dir", b.x + b.w, b.y + 10, b.z + 15.6, b.y + 18, b.z + 15.6, "var(--ilu-traco)", 1.2);
        cc.linhaNaFace("dir", b.x + b.w, b.y + 10, b.z + 12.8, b.y + 16, b.z + 12.8, "var(--ilu-traco)", 1.2);
      },
    });
    // aletas do radiador na lateral esquerda, à frente do tanque
    for (let i = 0; i < 5; i++) c.caixa(6 + i * 7, 33, 3, 2, 6, 22, "claro");
    c.cilindro(8, 10, 30, 3.6, 3, "escuro");
    for (const [i, x] of [12, 24, 36].entries()) {
      for (let k = 0; k < 4; k++) {
        c.cilindro(x, 14, 30 + k * 4.2, 1.6, 2.6, "claro");
        c.cilindro(x, 14, 32.6 + k * 4.2, 3, 1.1, "claro");
      }
      c.cilindro(x, 14, 47, 1.4, 3, "escuro");
      if (i === 0) c.pontoQuente(x, 14, 50.5, 3.4);
    }
  },

  /** Sem conexão com o servidor: notebook com o cabo solto. */
  "sem-conexao"(c) {
    c.sombra(30, 22, 30, 0.6);
    c.sombra(78, 26, 7, 0.8);
    notebook(c, 8, 8, {
      tela: (cc, { x, y, w }) => {
        for (let i = 0; i < 5; i++) {
          cc.linhaNaFace("esq", y, x + 6, 22 - i * 3.6, x + w - 10 - (i % 3) * 5, 22 - i * 3.6, "var(--ilu-traco)", 1.3);
        }
      },
    });
    // tomada de rede e o cabo que não chega até ela
    c.caixa(74, 20, 0, 8, 8, 8, "claro", { frente: (cc, b) => cc.naFace("esq", b.y + b.d, b.x + 2.5, b.z + 2.5, b.x + 5.5, b.z + 5.5, "var(--ilu-escuro-dir)") });
    c.traco([p(50, 26, 1.2), p(56, 32, 1.2), p(62, 32, 1.2), p(64, 34, 1.2)], "var(--ilu-escuro-esq)", 2.2);
    c.caixa(64, 32.4, 0.2, 4, 3, 2.4, "escuro");
    c.caixa(67.8, 33, 0.8, 1.4, 1.8, 1.2, { topo: "var(--urgente)", esq: "var(--urgente)", dir: "var(--urgente-texto)" });
    c.pontilhado([[70, 33, 1.4], [78, 28, 4]], 2.6, 0.7, { nos: false });
  },

  /** Modelos sem detector: placa de processamento. */
  modelos(c) {
    c.sombra(26, 22, 30, 0.6);
    c.caixa(2, 2, 0, 46, 40, 2, "claro");
    for (let i = 0; i < 6; i++) {
      c.linhaNaFace("topo", 2, 6, 8 + i * 5.6, 15, 8 + i * 5.6, "var(--ilu-traco)", 1.1);
      c.linhaNaFace("topo", 2, 35, 8 + i * 5.6, 44, 8 + i * 5.6, "var(--ilu-traco)", 1.1);
    }
    // pinos do lado de trás do chip antes dele; os da frente (lado direito) depois
    for (let i = 0; i < 5; i++) c.caixa(15.4, 10 + i * 5.6, 2, 2.2, 1.4, 1, "escuro");
    c.caixa(17.6, 9, 2, 14.8, 26, 4.5, "escuro", {
      frente: (cc, b) => cc.naFace("topo", b.z + b.h, b.x + 2.6, b.y + 4, b.x + b.w - 2.6, b.y + b.d - 4, cc.ferro()),
    });
    for (let i = 0; i < 5; i++) c.caixa(32.4, 10 + i * 5.6, 2, 2.2, 1.4, 1, "escuro");
  },
};

export const NOMES_ILUSTRACOES = Object.keys(CENAS);

/** ilustracao(nome, { rotulo, procurando }): procurando acende o pontilhado em sequência (indicador). */
export function ilustracao(nome, { rotulo = "", procurando = false } = {}) {
  const c = new Cena();
  CENAS[nome](c);
  return c.svg(rotulo, `ilu-${nome}${procurando ? " procurando" : ""}`);
}
