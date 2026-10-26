// Palco da Análise: termograma, regiões, pontos e linhas, escala de cores, mira com leitura ao vivo,
// zoom e arrasto, e as ferramentas (selecionar, região, ponto, linha). Coordenadas internas sempre em
// pixels da matriz térmica; a tela converte pelo retângulo do canvas (já inclui o zoom).
import { TEXTOS as T } from "../../textos.js";
import { el, temperatura, fmt, token } from "../base.js";
import { barraFerramentas, menu, avisar } from "../componentes.js";

const A = T.analise;
const SVG = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}) => { const n = document.createElementNS(SVG, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); return n; };
const ZOOM_MIN = 1, ZOOM_MAX = 12;
const SEM_ALERTA = new Set(["normal", "nao_avaliado", "sem_medida"]);

export function montarPalco(ctx) {
  // ---------------------------------------------------------------- estrutura
  const canvas = el("canvas", { class: "termo", "aria-hidden": "true" });
  const fundo = el("img", { class: "fundo-imagem", alt: "", hidden: true });
  const linhas = svg("svg", { class: "camada-linhas", preserveAspectRatio: "none", "aria-hidden": "true" });
  const caixas = el("div", { class: "camada-caixas" });
  const rascunho = el("div", { class: "caixa rascunho", hidden: true });
  const quadro = el("div", { class: "quadro" }, canvas, fundo, linhas, caixas, rascunho);
  const leitura = el("div", { class: "mira-leitura", hidden: true, "aria-hidden": "true" });
  const isoRotulo = el("div", { class: "isoterma-rotulo", hidden: true });
  const vista = el("div", { class: "vista", tabindex: "0", role: "application", "aria-label": A.palco, "aria-roledescription": A.palco }, quadro, leitura, isoRotulo);

  const barraCanvas = el("canvas", { class: "barra-cores", width: "1", height: "256", "aria-hidden": "true" });
  const marcador = el("span", { class: "marcador-cores", hidden: true });
  const marcaIso = el("span", { class: "marcador-iso", hidden: true });
  const trilhoCores = el("div", { class: "trilho-cores", title: A.isotermaDica }, barraCanvas, marcador, marcaIso);
  const btnMax = el("button", { type: "button", class: "limite-escala compacto", "aria-label": A.escalaMax, title: A.escalaMax });
  const btnMin = el("button", { type: "button", class: "limite-escala compacto", "aria-label": A.escalaMin, title: A.escalaMin });
  const marcasMeio = el("div", { class: "marcas-escala", "aria-hidden": "true" });
  const escala = el("div", { class: "escala-cores" }, btnMax, el("div", { class: "corpo-escala" }, trilhoCores, marcasMeio), btnMin);

  // ---------------------------------------------------------------- barra de ferramentas
  const nomesPaletas = Object.keys(ctx.paletas);
  const barra = barraFerramentas({
    rotulo: A.ferramentas,
    grupos: [
      [
        { chave: "selecionar", texto: A.selecionar, icone: "selecionar", atalho: "V", pressionado: true, onclick: () => usar("selecionar") },
        { chave: "regiao", texto: A.regiao, icone: "regiao", atalho: "R", pressionado: false, onclick: () => usar("regiao") },
        { chave: "ponto", texto: A.ponto, icone: "ponto", atalho: "P", pressionado: false, onclick: () => usar("ponto") },
        { chave: "linha", texto: A.linha, icone: "linha", atalho: "L", pressionado: false, onclick: () => usar("linha") },
      ],
      [
        { chave: "paleta", texto: A.paleta, icone: "tema" },
        { chave: "escala", texto: A.escala, icone: "escala" },
        { chave: "camadas", texto: A.camadas, icone: "camadas" },
      ],
    ],
    direita: [{ chave: "zoom", texto: A.zoom(100), dica: A.zoomDica, onclick: () => encaixar() }],
  });
  const ferramenta = (chave) => barra.querySelector(`[data-chave="${chave}"]`);
  const menuPaleta = menu(ferramenta("paleta"), nomesPaletas.map((p) => ({ texto: A.paletas[p] || p, marcado: false, executar: () => { ctx.paleta = p; ctx.salvarExibicao(); ctx.mudou("exibicao"); } })));
  const menuEscala = menu(ferramenta("escala"), [
    { texto: A.escalaEquipamento, marcado: false, executar: () => trocarFaixa("equipamento") },
    { texto: A.escalaCena, marcado: false, executar: () => trocarFaixa("cena") },
    { texto: A.escalaManual, marcado: false, executar: () => editarLimite(btnMax) },
    { separador: true },
    { texto: `${A.isoterma} (I)`, marcado: false, executar: () => alternarIsoterma() },
  ]);
  const itensCamadas = [["regioes", A.camRegioes], ["rotulos", A.camRotulos], ["pontos", A.camPontos], ["contornos", A.camContornos]];
  const menuCamadas = menu(ferramenta("camadas"), [
    ...itensCamadas.map(([k, t]) => ({ texto: t, marcado: false, executar: () => { ctx.camadas[k] = !ctx.camadas[k]; ctx.guardarCamadas(); ctx.mudou("exibicao"); } })),
    { separador: true },
    { texto: `${A.foto} (F)`, marcado: false, executar: () => alternarFoto() },
  ]);
  const marcarMenu = (m, ativos) => [...m.querySelectorAll('[role="menuitemradio"]')].forEach((b, i) => b.setAttribute("aria-checked", String(Boolean(ativos[i]))));

  function atualizarBarra() {
    for (const f of ["selecionar", "regiao", "ponto", "linha"]) ferramenta(f).setAttribute("aria-pressed", String(ctx.ferramenta === f));
    const escalaBtn = ferramenta("escala");
    if (ctx.a.sem_temperatura) escalaBtn.setAttribute("aria-disabled", "true"); else escalaBtn.removeAttribute("aria-disabled");
    const itemFoto = [...menuCamadas.querySelectorAll('[role="menuitemradio"]')].at(-1);
    if (ctx.a.tem_foto) { itemFoto.removeAttribute("aria-disabled"); itemFoto.title = ""; } else { itemFoto.setAttribute("aria-disabled", "true"); itemFoto.title = A.semFoto; }
    marcarMenu(menuPaleta, nomesPaletas.map((p) => p === ctx.paleta));
    marcarMenu(menuEscala, [...["equipamento", "cena", "manual"].map((m) => m === ctx.faixa.modo), ctx.isoterma.ligada]);
    marcarMenu(menuCamadas, [...itensCamadas.map(([k]) => ctx.camadas[k]), ctx.foto]);
    ferramenta("zoom").querySelector(".rotulo").textContent = A.zoom(Math.round(zoom.k * 100));
  }

  function usar(f) {
    ctx.ferramenta = f;
    vista.dataset.ferramenta = f;
    ctx.mudou("ferramenta");
  }

  // ---------------------------------------------------------------- desenho do termograma
  const fora = document.createElement("canvas");
  function desenharImagem() {
    const a = ctx.a;
    const m = ctx.m;
    vista.classList.toggle("sem-temperatura", Boolean(a.sem_temperatura));
    canvas.hidden = Boolean(a.sem_temperatura) || ctx.foto;
    fundo.hidden = !(a.sem_temperatura || ctx.foto);
    if (!fundo.hidden) {
      const fonte = ctx.foto ? `/api/analises/${a.id}/foto.jpg` : `/api/analises/${a.id}/original.jpg`;
      if (fundo.getAttribute("src") !== fonte) fundo.src = fonte;
    }
    if (!m) return;
    const { W, H, valores } = m;
    const [lo, hi] = ctx.faixaAtual();
    const lut = ctx.paletas[ctx.paleta];
    const iso = ctx.isoterma.ligada ? ctx.isoterma.valor : null;
    canvas.width = W;
    canvas.height = H;
    const c = canvas.getContext("2d");
    const img = c.createImageData(W, H);
    const d = img.data;
    const k = 255 / Math.max(hi - lo, 1e-6);
    let acima = 0;
    for (let i = 0; i < valores.length; i++) {
      const v = valores[i];
      const j = i * 4;
      if (!Number.isFinite(v)) { d[j + 3] = 0; continue; }
      let n = ((v - lo) * k) | 0;
      n = n < 0 ? 0 : n > 255 ? 255 : n;
      const cor = lut[n];
      if (iso != null && v < iso) {
        const cinza = (0.2126 * cor[0] + 0.7152 * cor[1] + 0.0722 * cor[2]) * 0.5;
        d[j] = d[j + 1] = d[j + 2] = cinza;
      } else {
        d[j] = cor[0]; d[j + 1] = cor[1]; d[j + 2] = cor[2];
        if (iso != null) acima++;
      }
      d[j + 3] = 255;
    }
    c.putImageData(img, 0, 0);
    // escala de cores (vertical: quente em cima)
    const bc = barraCanvas.getContext("2d");
    const faixa = bc.createImageData(1, 256);
    for (let y = 0; y < 256; y++) {
      const n = 255 - y;
      const v = lo + (n / 255) * (hi - lo);
      const cor = lut[n];
      const apagar = iso != null && v < iso;
      const cinza = (0.2126 * cor[0] + 0.7152 * cor[1] + 0.0722 * cor[2]) * 0.5;
      faixa.data.set(apagar ? [cinza, cinza, cinza, 255] : [cor[0], cor[1], cor[2], 255], y * 4);
    }
    bc.putImageData(faixa, 0, 0);
    btnMax.textContent = temperatura(hi);
    btnMin.textContent = temperatura(lo);
    marcasMeio.replaceChildren(...[0.25, 0.5, 0.75].map((f) => el("span", { style: { top: `${(1 - f) * 100}%` } }, fmt(lo + f * (hi - lo), 1))));
    isoRotulo.hidden = iso == null;
    marcaIso.hidden = iso == null;
    if (iso != null) {
      const area = (acima / Math.max(m.validos, 1)) * 100;
      isoRotulo.textContent = A.isotermaRotulo(temperatura(iso), fmt(area, area < 1 ? 2 : 1, " %"));
      marcaIso.style.top = `${(1 - (iso - lo) / Math.max(hi - lo, 1e-6)) * 100}%`;
    }
    escala.hidden = Boolean(a.sem_temperatura);
  }

  // ---------------------------------------------------------------- regiões, pontos e linhas por cima
  const pct = (v, total) => `${(v / total) * 100}%`;
  function desenharSobreposicao() {
    const a = ctx.a;
    const W = ctx.m?.W || a.matriz_info.largura;
    const H = ctx.m?.H || a.matriz_info.altura;
    linhas.setAttribute("viewBox", `0 0 ${W} ${H}`);
    linhas.replaceChildren();
    caixas.replaceChildren();
    caixas.classList.toggle("com-selecao", Boolean(ctx.sel));
    caixas.hidden = ctx.foto;
    linhas.style.display = ctx.foto ? "none" : "";
    const visivel = (r) => (r.classe === "ponto_quente" ? ctx.camadas.pontos : ctx.camadas.regioes) || r.id === ctx.sel;
    for (const r of a.regioes.filter(visivel)) {
      const [x0, y0, x1, y1] = r.caixa;
      const sel = r.id === ctx.sel;
      const caixa = el("div", {
        class: `caixa sev-${r.severidade}${sel ? " selecionada" : ""}`, dataset: { id: r.id },
        style: { left: pct(x0, W), top: pct(y0, H), width: pct(x1 - x0, W), height: pct(y1 - y0, H) },
        title: `${r.nome} · ${temperatura(r.medida?.t_max)}`,
      });
      if (ctx.camadas.rotulos && (sel || !SEM_ALERTA.has(r.severidade))) caixa.append(el("span", { class: "etq" }, `${r.nome} · ${temperatura(r.medida?.t_max)}`));
      if (sel && ctx.ferramenta === "selecionar") for (const canto of ["no", "ne", "so", "se"]) caixa.append(el("span", { class: `alca ${canto}`, dataset: { canto } }));
      caixas.append(caixa);
      const contorno = r.segmentacao?.contorno;
      if (ctx.camadas.contornos && contorno?.length > 2) {
        linhas.append(svg("polygon", { points: contorno.map(([x, y]) => `${x},${y}`).join(" "), class: `contorno sev-${r.severidade}${sel ? " selecionado" : ""}` }));
      }
    }
    const pq = a.resumo?.ponto_mais_quente;
    if (pq && !a.sem_temperatura) caixas.append(el("span", { class: "alvo-quente", style: { left: pct(pq.x + 0.5, W), top: pct(pq.y + 0.5, H) }, title: A.maisQuente(temperatura(pq.t_max)) }));
    for (const med of a.medicoes || []) {
      const v = med.valor || {};
      if (med.tipo === "ponto") {
        caixas.append(el("span", { class: "mira-ponto", style: { left: pct(med.x + 0.5, W), top: pct(med.y + 0.5, H) } }, el("span", { class: "etq" }, `${med.nome || ""} ${temperatura(v.t)}`.trim())));
      } else {
        linhas.append(svg("line", { x1: med.x0 + 0.5, y1: med.y0 + 0.5, x2: med.x1 + 0.5, y2: med.y1 + 0.5, class: "linha-medicao" }));
        const mx = v.x_max ?? (med.x0 + med.x1) / 2, my = v.y_max ?? (med.y0 + med.y1) / 2;
        caixas.append(el("span", { class: "mira-ponto linha", style: { left: pct(mx + 0.5, W), top: pct(my + 0.5, H) } }, el("span", { class: "etq" }, `${med.nome || ""} ${A.linhaMax(temperatura(v.t_max))}`.trim())));
      }
    }
  }

  // ---------------------------------------------------------------- zoom, arrasto e encaixe
  const zoom = { k: 1, x: 0, y: 0, base: { w: 0, h: 0, ox: 0, oy: 0 } };
  function medirBase() {
    const W = ctx.m?.W || ctx.a.matriz_info.largura;
    const H = ctx.m?.H || ctx.a.matriz_info.altura;
    const folga = parseFloat(token("e-4"));
    const vw = vista.clientWidth - 2 * folga, vh = vista.clientHeight - 2 * folga;
    if (vw <= 0 || vh <= 0) return;
    const s = Math.min(vw / W, vh / H);
    zoom.base = { w: W * s, h: H * s, ox: (vista.clientWidth - W * s) / 2, oy: (vista.clientHeight - H * s) / 2 };
    quadro.style.width = `${zoom.base.w}px`;
    quadro.style.height = `${zoom.base.h}px`;
    aplicarZoom();
  }
  function aplicarZoom() {
    const { ox, oy, w, h } = zoom.base;
    // não deixa a imagem sair inteira da vista
    const maxX = Math.max(0, (w * zoom.k - w) / 2 + w * 0.4), maxY = Math.max(0, (h * zoom.k - h) / 2 + h * 0.4);
    zoom.x = Math.min(maxX, Math.max(-maxX - (w * zoom.k - w), zoom.x));
    zoom.y = Math.min(maxY, Math.max(-maxY - (h * zoom.k - h), zoom.y));
    quadro.style.transform = `translate(${ox + zoom.x}px, ${oy + zoom.y}px) scale(${zoom.k})`;
    quadro.style.setProperty("--k", zoom.k);
    quadro.classList.toggle("pixelado", zoom.k >= 3);
    ferramenta("zoom").querySelector(".rotulo").textContent = A.zoom(Math.round(zoom.k * 100));
  }
  function zoomEm(fator, cx, cy) {
    const k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom.k * fator));
    const r = vista.getBoundingClientRect();
    const px = (cx ?? r.left + r.width / 2) - r.left - zoom.base.ox - zoom.x;
    const py = (cy ?? r.top + r.height / 2) - r.top - zoom.base.oy - zoom.y;
    zoom.x -= px * (k / zoom.k - 1);
    zoom.y -= py * (k / zoom.k - 1);
    zoom.k = k;
    aplicarZoom();
  }
  function encaixar() { zoom.k = 1; zoom.x = 0; zoom.y = 0; aplicarZoom(); }
  new ResizeObserver(medirBase).observe(vista);
  vista.addEventListener("wheel", (ev) => { ev.preventDefault(); zoomEm(ev.deltaY < 0 ? 1.2 : 1 / 1.2, ev.clientX, ev.clientY); }, { passive: false });

  // ---------------------------------------------------------------- ponteiro: mira, seleção, desenho, mover e redimensionar
  function naMatriz(ev) {
    const r = canvas.hidden ? fundo.getBoundingClientRect() : canvas.getBoundingClientRect();
    const W = ctx.m?.W || ctx.a.matriz_info.largura;
    const H = ctx.m?.H || ctx.a.matriz_info.altura;
    const x = ((ev.clientX - r.left) / r.width) * W;
    const y = ((ev.clientY - r.top) / r.height) * H;
    return { x, y, dentro: x >= 0 && y >= 0 && x < W && y < H, W, H };
  }
  const limitar = (v, max) => Math.min(max - 0.01, Math.max(0, v));

  function mostrarLeitura(ev) {
    const p = naMatriz(ev);
    const t = p.dentro ? ctx.temperatura(p.x, p.y) : null;
    if (t == null || ctx.foto) { leitura.hidden = true; marcador.hidden = true; return; }
    const rv = vista.getBoundingClientRect();
    leitura.hidden = false;
    leitura.textContent = temperatura(t);
    const x = ev.clientX - rv.left, y = ev.clientY - rv.top;
    const passo = parseFloat(token("e-3"));
    const direita = x > rv.width - parseFloat(token("col-num"));
    leitura.style.transform = `translate(${direita ? x - leitura.offsetWidth - passo : x + passo}px, ${y + passo}px)`;
    const [lo, hi] = ctx.faixaAtual();
    marcador.hidden = false;
    marcador.style.top = `${(1 - Math.min(1, Math.max(0, (t - lo) / Math.max(hi - lo, 1e-6)))) * 100}%`;
  }

  let gesto = null; // { tipo, inicio, ... }
  let espaco = false;
  vista.addEventListener("pointerdown", (ev) => {
    if (ev.button === 1 || espaco) { gesto = { tipo: "mover-vista", x: ev.clientX, y: ev.clientY, zx: zoom.x, zy: zoom.y }; vista.setPointerCapture(ev.pointerId); vista.classList.add("arrastando"); return; }
    if (ev.button !== 0) return;
    const p = naMatriz(ev);
    vista.focus({ preventScroll: true });
    if (ctx.ferramenta === "selecionar") {
      const alca = ev.target.closest(".alca");
      const alvo = ev.target.closest(".caixa[data-id]");
      if (alca && ctx.sel) {
        gesto = { tipo: "redimensionar", canto: alca.dataset.canto, caixa: [...ctx.regiao().caixa], p0: p };
      } else if (alvo) {
        if (alvo.dataset.id !== ctx.sel) ctx.selecionar(alvo.dataset.id);
        gesto = { tipo: "mover-caixa", caixa: [...ctx.regiao().caixa], p0: p, moveu: false };
      } else {
        if (ctx.sel) ctx.selecionar(null);
        return;
      }
    } else if (!p.dentro) {
      return;
    } else if (ctx.ferramenta === "regiao" || ctx.ferramenta === "linha") {
      gesto = { tipo: ctx.ferramenta, p0: p, p1: p };
    } else if (ctx.ferramenta === "ponto") {
      adicionarMedicao({ tipo: "ponto", x: p.x, y: p.y });
      return;
    }
    vista.setPointerCapture(ev.pointerId);
  });

  vista.addEventListener("pointermove", (ev) => {
    mostrarLeitura(ev);
    if (!gesto) return;
    if (gesto.tipo === "mover-vista") { zoom.x = gesto.zx + ev.clientX - gesto.x; zoom.y = gesto.zy + ev.clientY - gesto.y; aplicarZoom(); return; }
    const p = naMatriz(ev);
    const { W, H } = p;
    if (gesto.tipo === "regiao" || gesto.tipo === "linha") {
      gesto.p1 = { x: limitar(p.x, W), y: limitar(p.y, H) };
      desenharRascunho();
    } else if (gesto.tipo === "mover-caixa") {
      const dx = p.x - gesto.p0.x, dy = p.y - gesto.p0.y;
      if (!gesto.moveu && Math.hypot(dx, dy) < 0.8) return;
      gesto.moveu = true;
      const [x0, y0, x1, y1] = gesto.caixa;
      const mx = Math.min(W - x1, Math.max(-x0, dx)), my = Math.min(H - y1, Math.max(-y0, dy));
      ajustarCaixaVisivel([x0 + mx, y0 + my, x1 + mx, y1 + my]);
    } else if (gesto.tipo === "redimensionar") {
      const c = [...gesto.caixa];
      const x = limitar(p.x, W), y = limitar(p.y, H);
      if (gesto.canto.includes("o")) c[0] = Math.min(x, c[2] - 1); else c[2] = Math.max(x, c[0] + 1);
      if (gesto.canto.includes("n")) c[1] = Math.min(y, c[3] - 1); else c[3] = Math.max(y, c[1] + 1);
      gesto.nova = c;
      ajustarCaixaVisivel(c);
    }
  });

  vista.addEventListener("pointerleave", () => { leitura.hidden = true; marcador.hidden = true; });

  vista.addEventListener("pointerup", () => {
    const g = gesto;
    gesto = null;
    vista.classList.remove("arrastando");
    rascunho.hidden = true;
    linhas.querySelector(".rascunho")?.remove();
    if (!g) return;
    if (g.tipo === "regiao") {
      const x0 = Math.min(g.p0.x, g.p1.x), x1 = Math.max(g.p0.x, g.p1.x), y0 = Math.min(g.p0.y, g.p1.y), y1 = Math.max(g.p0.y, g.p1.y);
      if (x1 - x0 < 2 || y1 - y0 < 2) return;
      const n = ctx.a.regioes.filter((r) => r.origem === "manual").length + 1;
      const id = Math.random().toString(16).slice(2, 10);
      const nova = { id, nome: `${A.regiaoNova} ${n}`, classe: "componente", caixa: [x0, y0, x1, y1].map((v) => Math.round(v * 100) / 100), origem: "manual" };
      ctx.salvarRegioes([...ctx.a.regioes, nova]).then(() => { ctx.ferramenta = "selecionar"; vista.dataset.ferramenta = "selecionar"; ctx.selecionar(id); }).catch((e) => avisar(e.message, { erro: true }));
    } else if (g.tipo === "linha") {
      if (Math.hypot(g.p1.x - g.p0.x, g.p1.y - g.p0.y) < 2) return;
      adicionarMedicao({ tipo: "linha", x0: g.p0.x, y0: g.p0.y, x1: g.p1.x, y1: g.p1.y });
    } else if ((g.tipo === "mover-caixa" && g.moveu) || (g.tipo === "redimensionar" && g.nova)) {
      const atual = ctx.regiao();
      const caixa = (g.nova || caixaVisivel).map((v) => Math.round(v * 100) / 100);
      ctx.salvarRegioes(ctx.a.regioes.map((r) => (r.id === atual.id ? { ...r, caixa, origem: r.origem === "manual" ? "manual" : r.origem } : r))).catch((e) => avisar(e.message, { erro: true }));
    }
  });

  let caixaVisivel = null;
  function ajustarCaixaVisivel(c) {
    caixaVisivel = c;
    const n = caixas.querySelector(`.caixa[data-id="${ctx.sel}"]`);
    const W = ctx.m?.W || ctx.a.matriz_info.largura, H = ctx.m?.H || ctx.a.matriz_info.altura;
    if (n) Object.assign(n.style, { left: pct(c[0], W), top: pct(c[1], H), width: pct(c[2] - c[0], W), height: pct(c[3] - c[1], H) });
  }

  function desenharRascunho() {
    const { p0, p1 } = gesto;
    const W = ctx.m?.W || ctx.a.matriz_info.largura, H = ctx.m?.H || ctx.a.matriz_info.altura;
    if (gesto.tipo === "regiao") {
      rascunho.hidden = false;
      Object.assign(rascunho.style, { left: pct(Math.min(p0.x, p1.x), W), top: pct(Math.min(p0.y, p1.y), H), width: pct(Math.abs(p1.x - p0.x), W), height: pct(Math.abs(p1.y - p0.y), H) });
    } else {
      linhas.querySelector(".rascunho")?.remove();
      linhas.append(svg("line", { x1: p0.x, y1: p0.y, x2: p1.x, y2: p1.y, class: "linha-medicao rascunho" }));
    }
  }

  function adicionarMedicao(m) {
    ctx.salvarMedicoes([...(ctx.a.medicoes || []), { id: Math.random().toString(16).slice(2, 10), ...m }]).catch((e) => avisar(e.message, { erro: true }));
  }

  // ---------------------------------------------------------------- escala: limites editáveis, isoterma
  function trocarFaixa(modo) {
    if (modo === "manual" && !ctx.faixa.manual) ctx.faixa.manual = ctx.faixaAtual().map((v, i) => (i ? Math.ceil(v) : Math.floor(v)));
    ctx.faixa.modo = modo;
    ctx.salvarExibicao();
    ctx.mudou("exibicao");
  }
  function editarLimite(botao) {
    if (ctx.a.sem_temperatura) return;
    const alto = botao === btnMax;
    const [lo, hi] = ctx.faixaAtual();
    const campo = el("input", { type: "text", inputmode: "decimal", class: "limite-escala editando num", value: fmt(alto ? hi : lo, 1), "aria-label": alto ? A.escalaMax : A.escalaMin });
    botao.replaceWith(campo);
    campo.select();
    const terminar = (aplicar) => {
      if (!campo.isConnected) return;
      campo.replaceWith(botao);
      if (!aplicar) return;
      const v = Number(String(campo.value).replace(",", "."));
      const nova = alto ? [lo, v] : [v, hi];
      if (!Number.isFinite(v) || nova[1] - nova[0] < 0.1) { avisar(A.escalaInvalida, { erro: true }); return; }
      ctx.faixa = { modo: "manual", manual: nova };
      ctx.salvarExibicao();
      ctx.mudou("exibicao");
    };
    campo.addEventListener("keydown", (ev) => { if (ev.key === "Enter") terminar(true); if (ev.key === "Escape") { ev.stopPropagation(); terminar(false); } });
    campo.addEventListener("blur", () => terminar(true));
  }
  btnMax.addEventListener("click", () => editarLimite(btnMax));
  btnMin.addEventListener("click", () => editarLimite(btnMin));
  trilhoCores.addEventListener("click", (ev) => {
    if (ctx.a.sem_temperatura) return;
    const r = trilhoCores.getBoundingClientRect();
    const [lo, hi] = ctx.faixaAtual();
    ctx.isoterma = { ligada: true, valor: lo + (1 - (ev.clientY - r.top) / r.height) * (hi - lo) };
    ctx.mudou("exibicao");
  });
  function alternarIsoterma() {
    if (ctx.a.sem_temperatura) return;
    const [lo, hi] = ctx.faixaAtual();
    ctx.isoterma = ctx.isoterma.ligada ? { ligada: false, valor: ctx.isoterma.valor } : { ligada: true, valor: ctx.isoterma.valor ?? lo + 0.75 * (hi - lo) };
    ctx.mudou("exibicao");
  }
  function alternarFoto() {
    if (!ctx.a.tem_foto) return;
    ctx.foto = !ctx.foto;
    ctx.mudou("exibicao");
  }

  // ---------------------------------------------------------------- teclado (só com a Análise aberta e fora de campos)
  function teclado(ev) {
    if (ev.target.closest("input, textarea, select, [contenteditable='true']") || document.querySelector("dialog[open], .menu:popover-open")) return;
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    const tecla = ev.key.toLowerCase();
    const atalhos = { v: () => usar("selecionar"), r: () => usar("regiao"), p: () => usar("ponto"), l: () => usar("linha"), i: alternarIsoterma, f: alternarFoto, 0: encaixar, "+": () => zoomEm(1.25), "=": () => zoomEm(1.25), "-": () => zoomEm(0.8) };
    if (ev.key === " " && ev.target.closest(".vista")) { espaco = true; vista.classList.add("pode-arrastar"); ev.preventDefault(); return; }
    if (atalhos[tecla]) { atalhos[tecla](); ev.preventDefault(); return; }
    if (ev.key === "Escape") {
      if (gesto) { gesto = null; rascunho.hidden = true; linhas.querySelector(".rascunho")?.remove(); return; }
      if (ctx.ferramenta !== "selecionar") usar("selecionar"); else if (ctx.sel) ctx.selecionar(null);
    }
  }
  function soltarEspaco(ev) { if (ev.key === " ") { espaco = false; vista.classList.remove("pode-arrastar"); } }
  document.addEventListener("keydown", teclado);
  document.addEventListener("keyup", soltarEspaco);

  // ---------------------------------------------------------------- redesenho por evento
  const parar = ctx.ouvir((parte) => {
    if (["tudo", "dados", "exibicao"].includes(parte)) { desenharImagem(); desenharSobreposicao(); atualizarBarra(); }
    if (parte === "tudo") medirBase();
    if (parte === "selecao" || parte === "ferramenta") { desenharSobreposicao(); atualizarBarra(); }
  });
  desenharImagem();
  desenharSobreposicao();
  atualizarBarra();
  vista.dataset.ferramenta = ctx.ferramenta;

  const palco = el("div", { class: "palco" }, vista, escala);
  return {
    barra,
    palco,
    realcar: (id, ligar) => caixas.querySelector(`.caixa[data-id="${id}"]`)?.classList.toggle("realce", ligar),
    encerrar() {
      parar();
      document.removeEventListener("keydown", teclado);
      document.removeEventListener("keyup", soltarEspaco);
      [menuPaleta, menuEscala, menuCamadas].forEach((m) => m.remove());
    },
  };
}

