// Pyron · teste no navegador. Gera um termograma sintético de três buchas (fases A, B e C), pinta na paleta ferro
// e classifica cada conexão com a mesma regra do programa (nucleo/analise.py, critério padrão NBR 15866):
// ΔT contra a mediana das fases, corrigido para plena carga, e % da MTA da temperatura projetada; vale o pior.

const W = 640, H = 420;
const FASES = [{ nome: "A", x: 190 }, { nome: "B", x: 320 }, { nome: "C", x: 450 }];
const MTA_BUCHA = 95; // IEC 60137 (nucleo/referencias.py)
const CRITERIO = {
  similares: [[5.0, "atencao"], [10.1, "programar"], [20.1, "urgente"], [40.1, "imediato"]],
  mta: [[60.1, "atencao"], [70.1, "programar"], [80.1, "urgente"], [100.1, "imediato"]],
  expoente: 2, cargaMinima: 40,
};
const NIVEIS = {
  normal: { rotulo: "Normal", acao: "Nenhuma ação.", prazo: 365 },
  atencao: { rotulo: "Atenção", acao: "Corrigir na próxima manutenção periódica.", prazo: 90 },
  programar: { rotulo: "Programar reparo", curto: "Programar", acao: "Agendar a correção e reinspecionar.", prazo: 30 },
  urgente: { rotulo: "Urgente", acao: "Corrigir o mais rápido possível.", prazo: 7 },
  imediato: { rotulo: "Imediato", acao: "Corrigir imediatamente.", prazo: 1 },
};
const ORDEM = Object.keys(NIVEIS);
// elevação de cada conexão sobre o ambiente (°C), por cenário
const CENARIOS = [
  { id: "normal", texto: "Normal", elevacao: [12.5, 13.2, 12.8] },
  { id: "frouxa", texto: "Conexão frouxa", elevacao: [12.6, 24, 13] },
  { id: "grave", texto: "Falha grave", elevacao: [13, 49, 12.8] },
  { id: "sobrecarga", texto: "Sobrecarga", elevacao: [33, 34, 32.5] },
];

const $ = (id) => document.getElementById(id);
const fmt = (v, casas = 1) => v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
const css = getComputedStyle(document.documentElement);
const cor = (nome) => css.getPropertyValue(`--${nome}`).trim();
const estado = { cenario: "frouxa", carga: 80, ambiente: 25, campo: null, regioes: [] };

// ---------------------------------------------------------------- termograma sintético
let semente = 7;
const aleatorio = () => ((semente = (semente * 16807) % 2147483647) / 2147483647);

function gerarCampo(ambiente, elevacao) {
  semente = 7;
  const t = new Float32Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) t[y * W + x] = ambiente - 6 + 4 * (y / H); // céu mais frio no alto
  const retangulo = (x0, y0, x1, y1, f) => { for (let y = Math.max(0, y0); y < Math.min(H, y1); y++) for (let x = Math.max(0, x0); x < Math.min(W, x1); x++) t[y * W + x] = f(x, y); };
  // pórtico de aço e cabos até as buchas
  retangulo(20, 40, W - 20, 52, () => ambiente + 1.5);
  retangulo(28, 40, 40, 270, () => ambiente + 1);
  retangulo(W - 40, 40, W - 28, 270, () => ambiente + 1);
  // tanque e radiadores
  retangulo(90, 270, 550, H, (x, y) => ambiente + 9 - 3 * ((y - 270) / (H - 270)));
  for (let i = 0; i < 6; i++) retangulo(560 + i * 12, 290, 566 + i * 12, H - 10, () => ambiente + 6);
  for (let i = 0; i < 6; i++) retangulo(18 + i * 12, 290, 24 + i * 12, H - 10, () => ambiente + 6);
  FASES.forEach((f, i) => {
    const quente = ambiente + elevacao[i];
    // corpo de porcelana com saias
    for (let y = 112; y < 270; y++) {
      const meia = 11 + 8 * ((y - 112) / 158);
      const saia = (y % 14) < 5 ? 4 : 0;
      for (let x = Math.round(f.x - meia - saia); x <= f.x + meia + saia; x++) t[y * W + x] = ambiente + 5 + 2 * ((y - 112) / 158) + (saia ? -1.2 : 0);
    }
    // cabo do terminal ao pórtico, aquecido perto da conexão
    for (let y = 52; y < 92; y++) for (let x = f.x - 2; x <= f.x + 2; x++) t[y * W + x] = ambiente + 3 + (quente - ambiente - 3) * Math.exp(-(92 - y) / 14);
    // conexão: núcleo quente com calor espalhado
    for (let y = 70; y < 130; y++) for (let x = f.x - 30; x < f.x + 30; x++) {
      const d2 = ((x - f.x) / 10) ** 2 + ((y - 100) / 9) ** 2;
      const dentro = Math.abs(x - f.x) < 17 && y >= 90 && y < 112;
      const calor = ambiente + (quente - ambiente) * Math.exp(-d2 / 2);
      t[y * W + x] = Math.max(t[y * W + x], dentro ? Math.max(calor, ambiente + 0.6 * (quente - ambiente)) : calor);
    }
  });
  suavizar(t); suavizar(t);
  for (let i = 0; i < t.length; i++) t[i] += (aleatorio() - .5) * .5;
  return t;
}

function suavizar(t) {
  const c = Float32Array.from(t);
  for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) {
    let s = 0;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) s += c[(y + dy) * W + x + dx];
    t[y * W + x] = s / 9;
  }
}

// paleta ferro dos tokens, interpolada em 256 tons
function lutFerro() {
  const paradas = [0, 1, 2, 3, 4, 5, 6].map((i) => cor(`ferro-${i}`)).map((h) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16)));
  return Array.from({ length: 256 }, (_, i) => {
    const p = (i / 255) * (paradas.length - 1), a = Math.floor(p), b = Math.min(a + 1, paradas.length - 1), f = p - a;
    return paradas[a].map((v, k) => Math.round(v + (paradas[b][k] - v) * f));
  });
}
const LUT = lutFerro();

// ---------------------------------------------------------------- regra de severidade
const nivelPor = (valor, faixas) => faixas.reduce((n, [limite, nome]) => (valor >= limite ? nome : n), "normal");
const pior = (...niveis) => niveis.reduce((a, b) => (ORDEM.indexOf(b) > ORDEM.indexOf(a) ? b : a), "normal");
const mediana = (v) => { const s = [...v].sort((a, b) => a - b); return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2; };

function classificar(campo, ambiente, carga) {
  const fator = carga < 100 ? (100 / carga) ** CRITERIO.expoente : 1;
  const regioes = FASES.map((f) => {
    const caixa = [f.x - 26, 78, f.x + 26, 122];
    let tmax = -Infinity, px = 0, py = 0;
    for (let y = caixa[1]; y < caixa[3]; y++) for (let x = caixa[0]; x < caixa[2]; x++) if (campo[y * W + x] > tmax) { tmax = campo[y * W + x]; px = x; py = y; }
    return { nome: `Bucha fase ${f.nome}`, fase: f.nome, caixa, tmax, px, py };
  });
  const ref = mediana(regioes.map((r) => r.tmax));
  for (const r of regioes) {
    r.dt = Math.max(r.tmax - ref, 0) * fator;
    r.tProj = ambiente + Math.max(r.tmax - ambiente, 0) * fator;
    r.pctMta = (100 * r.tProj) / MTA_BUCHA;
    r.nivelDt = nivelPor(r.dt, CRITERIO.similares);
    r.nivelMta = nivelPor(r.pctMta, CRITERIO.mta);
    r.nivel = pior(r.nivelDt, r.nivelMta);
    r.criterio = r.nivel === "normal" ? null : [r.nivelDt === r.nivel ? "ΔT entre semelhantes" : null, r.nivelMta === r.nivel ? "% da MTA" : null].filter(Boolean).join(" e ");
  }
  return regioes;
}

// ---------------------------------------------------------------- desenho
const canvas = $("termo");
const g = canvas.getContext("2d");
let faixa = [0, 1];

function desenhar() {
  const t = estado.campo;
  let lo = Infinity, hi = -Infinity;
  for (const v of t) { if (v < lo) lo = v; if (v > hi) hi = v; }
  faixa = [lo, hi];
  const img = g.createImageData(W, H);
  for (let i = 0; i < t.length; i++) {
    const [r, gr, b] = LUT[Math.max(0, Math.min(255, Math.round(((t[i] - lo) / (hi - lo)) * 255)))];
    img.data[i * 4] = r; img.data[i * 4 + 1] = gr; img.data[i * 4 + 2] = b; img.data[i * 4 + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  g.font = `600 14px ${cor("fonte-num")}`;
  for (const r of estado.regioes) {
    const [x0, y0, x1, y1] = r.caixa;
    g.lineWidth = 2;
    g.strokeStyle = cor(r.nivel === "normal" ? "marca-imagem" : r.nivel);
    g.strokeRect(x0 + .5, y0 + .5, x1 - x0, y1 - y0);
    const rotulo = `${r.fase} ${fmt(r.tmax)} °C`;
    const largura = g.measureText(rotulo).width + 12;
    g.fillStyle = cor("rotulo-imagem");
    g.fillRect(x0, y0 - 24, largura, 22);
    g.fillStyle = cor("marca-imagem");
    g.fillText(rotulo, x0 + 6, y0 - 8);
    // ponto mais quente
    g.beginPath(); g.arc(r.px, r.py, 4, 0, Math.PI * 2); g.lineWidth = 2; g.strokeStyle = cor("marca-imagem"); g.stroke();
  }
  $("escala-min").textContent = `${fmt(lo)} °C`;
  $("escala-max").textContent = `${fmt(hi)} °C`;
}

function painel() {
  const regioes = estado.regioes;
  const geral = pior(...regioes.map((r) => r.nivel));
  const n = NIVEIS[geral];
  const pior_ = regioes.reduce((a, b) => (ORDEM.indexOf(b.nivel) > ORDEM.indexOf(a.nivel) || (b.nivel === a.nivel && b.tmax > a.tmax) ? b : a));
  const resumo = $("resumo");
  resumo.style.setProperty("--cor-nivel", cor(geral));
  resumo.replaceChildren(...[
    el("span", { class: "estrutura" }, "Resultado"),
    el("div", { class: "linha-resumo" }, el("b", {}, n.rotulo), el("span", { class: `selo ${geral}` }, geral === "normal" ? "sem anomalia" : `${pior_.nome}, ${fmt(pior_.tmax)} °C`)),
    el("p", {}, geral === "normal"
      ? "As três fases estão parecidas e longe da máxima admissível."
      : `${n.acao} Prazo sugerido: ${n.prazo === 1 ? "1 dia" : `${n.prazo} dias`}. Disparou por ${pior_.criterio}.`),
    estado.carga < CRITERIO.cargaMinima ? el("p", {}, `Carga de ${estado.carga} % abaixo de ${CRITERIO.cargaMinima} %: a projeção para plena carga é pouco confiável.`) : null,
  ].filter(Boolean));
  $("regioes").replaceChildren(...regioes.map((r) => el("tr", { "data-fase": r.fase },
    el("th", { scope: "row" }, `Fase ${r.fase}`),
    el("td", { class: "dir" }, `${fmt(r.tmax)} °C`),
    el("td", { class: "dir" }, `${fmt(r.dt)} °C`),
    el("td", { class: "dir" }, `${fmt(r.pctMta)} %`),
    el("td", {}, el("span", { class: `selo ${r.nivel}` }, NIVEIS[r.nivel].curto || NIVEIS[r.nivel].rotulo)))));
}

function el(tag, attrs = {}, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  n.append(...filhos.filter((f) => f != null));
  return n;
}

function atualizar({ gerar = true } = {}) {
  const c = CENARIOS.find((x) => x.id === estado.cenario);
  if (gerar) estado.campo = gerarCampo(estado.ambiente, c.elevacao);
  estado.regioes = classificar(estado.campo, estado.ambiente, estado.carga);
  desenhar();
  painel();
}

// ---------------------------------------------------------------- controles
const grupo = $("cenarios");
for (const c of CENARIOS) {
  grupo.append(el("button", { type: "button", "aria-pressed": String(c.id === estado.cenario), "data-id": c.id }, c.texto));
}
grupo.addEventListener("click", (ev) => {
  const b = ev.target.closest("button");
  if (!b) return;
  estado.cenario = b.dataset.id;
  grupo.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  atualizar();
});
$("carga").addEventListener("input", (ev) => { estado.carga = +ev.target.value; $("carga-valor").textContent = `${estado.carga} %`; atualizar({ gerar: false }); });
$("ambiente").addEventListener("input", (ev) => { estado.ambiente = +ev.target.value; $("ambiente-valor").textContent = `${estado.ambiente} °C`; atualizar(); });

// leitura do ponto sob o cursor ou o dedo
const mira = $("mira");
function ler(ev) {
  const caixa = canvas.getBoundingClientRect();
  const x = Math.floor(((ev.clientX - caixa.left) / caixa.width) * W), y = Math.floor(((ev.clientY - caixa.top) / caixa.height) * H);
  if (x < 0 || y < 0 || x >= W || y >= H) { mira.hidden = true; return; }
  mira.hidden = false;
  mira.style.left = `${((x + .5) / W) * 100}%`;
  mira.style.top = `${((y + .5) / H) * 100}%`;
  $("mira-valor").textContent = `${fmt(estado.campo[y * W + x])} °C`;
}
canvas.addEventListener("pointermove", ler);
canvas.addEventListener("pointerdown", ler);
canvas.addEventListener("pointerleave", () => { mira.hidden = true; });

atualizar();
