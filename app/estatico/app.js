"use strict";

// ================================================================= utilidades

const $ = (s, raiz = document) => raiz.querySelector(s);
const $$ = (s, raiz = document) => [...raiz.querySelectorAll(s)];

function el(tag, props = {}, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null) continue;
    if (k === "class") n.className = v;
    else if (k === "style") Object.assign(n.style, v);
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(n.dataset, v);
    else if (k in n && typeof v !== "string") n[k] = v;
    else n.setAttribute(k, v);
  }
  for (const f of filhos.flat()) if (f != null && f !== false) n.append(f instanceof Node ? f : document.createTextNode(String(f)));
  return n;
}

function icone(nome) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "ic");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${nome}`);
  svg.append(use);
  return svg;
}

const fmt = (v, casas = 1, sufixo = "") =>
  v == null || !Number.isFinite(v) ? "–" : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }) + sufixo;

const NIVEIS = ["normal", "atencao", "programar", "urgente", "imediato"];
const COR_NIVEL = { normal: "#1E9B6A", atencao: "#D09E0C", programar: "#E2741B", urgente: "#D6452A", imediato: "#BE1A33" };
const ROTULO_CURTO = { normal: "Normal", atencao: "Atenção", programar: "Programar", urgente: "Urgente", imediato: "Imediato" };
const NOMES_CLASSES = {
  ponto_quente: "Ponto quente", componente: "Componente", para_raio: "Para-raio", terminal_superior: "Terminal superior",
  isolador: "Isolador", parte_isoladora: "Parte isoladora", terminal_inferior: "Terminal inferior", bucha: "Bucha",
  conexao: "Conexão", radiador: "Radiador", tanque: "Tanque", cabo: "Cabo isolado",
};
const CLASSES_PADRAO = ["componente", "ponto_quente", "para_raio", "terminal_superior", "parte_isoladora", "terminal_inferior", "isolador", "bucha", "conexao", "cabo", "radiador", "tanque"];
const AQUECIMENTO = { resistivo: "Resistivo (carga)", dieletrico: "Dielétrico (fuga)", oleo: "Óleo" };
const ETAPAS = ["Leitura da temperatura", "Detecção", "Medição e severidade", "Laudo"];

const estado = {
  analise: null, matriz: null, paletas: null, paleta: "ferro", faixa: "equipamento", ferramenta: "selecionar",
  selecionada: null, rascunho: null, faixaCompleta: null, isoterma: { ligada: false, valor: null },
  modelos: [], ativo: null, config: null, inspecoes: [], filtro: "todas", busca: "", ordem: "recentes",
};

function nomeClasse(c, modelo) {
  const nomes = (modelo || (estado.analise && estado.analise.modelo) || {}).nomes || {};
  return nomes[c] || NOMES_CLASSES[c] || c;
}

// ================================================================= servidor

async function api(caminho, opcoes = {}) {
  let r;
  try {
    r = await fetch(caminho, opcoes);
  } catch {
    throw new Error("O Pyron não está respondendo. Feche e abra o programa de novo.");
  }
  const tipo = r.headers.get("content-type") || "";
  const corpo = tipo.includes("application/json") ? await r.json() : null;
  if (!r.ok) throw new Error((corpo && (corpo.erro || corpo.detail)) || `O servidor respondeu com erro ${r.status}.`);
  return corpo;
}
const json = (metodo, corpo) => ({ method: metodo, headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });

// ================================================================= avisos, diálogos, carregamento

function avisar(texto, { erro = false, acao = null, duracao } = {}) {
  const a = el("div", { class: `aviso${erro ? " erro" : ""}`, role: erro ? "alert" : "status" }, icone(erro ? "alerta" : "check"), el("span", {}, texto));
  if (acao) a.append(el("button", { type: "button", onclick: () => { acao.executar(); a.remove(); } }, acao.rotulo));
  $("#toasts").append(a);
  setTimeout(() => a.remove(), duracao || (erro ? 8000 : acao ? 7000 : 3500));
}
const falhou = (e) => avisar(e.message, { erro: true });

function dialogo({ titulo, conteudo, acoes }) {
  const d = $("#dialogo");
  $("#dialogo-titulo").textContent = titulo;
  $("#dialogo-conteudo").replaceChildren(...[].concat(conteudo || []));
  $("#dialogo-acoes").replaceChildren(
    ...acoes.map((a) => el("button", { class: `btn ${a.classe || ""}`, value: a.valor, type: "submit", disabled: a.desativado || null }, a.rotulo)),
  );
  return new Promise((resolver) => {
    d.onclose = () => resolver(d.returnValue);
    d.returnValue = "";
    d.showModal();
  });
}

function confirmar(titulo, texto, rotulo, perigo = false) {
  return dialogo({
    titulo,
    conteudo: el("p", {}, texto),
    acoes: [{ rotulo: "Cancelar", valor: "nao" }, { rotulo, valor: "sim", classe: perigo ? "btn-perigo" : "btn-primaria" }],
  }).then((v) => v === "sim");
}

async function comCarregamento(titulo, tarefa, animarEtapas = true) {
  const textos = ["Lendo a temperatura", "Procurando componentes", "Medindo e classificando"];
  let k = 0;
  $("#carregando-titulo").textContent = titulo;
  $("#carregando-texto").textContent = textos[0];
  $("#carregando").hidden = false;
  if (animarEtapas) mostrarEtapas(null, 0);
  const giro = setInterval(() => {
    k = Math.min(k + 1, textos.length - 1);
    $("#carregando-texto").textContent = textos[k];
    if (animarEtapas) mostrarEtapas(null, k);
  }, 600);
  try {
    return await tarefa();
  } finally {
    clearInterval(giro);
    $("#carregando").hidden = true;
  }
}

// ================================================================= tema e navegação

function aplicarTema(tema) {
  if (tema === "claro" || tema === "escuro") document.documentElement.dataset.tema = tema;
  else delete document.documentElement.dataset.tema;
  $$("#seg-tema button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.valor === (tema || "sistema"))));
}

function rota() {
  const [pedida, idPedido] = (location.hash.replace("#", "") || "analise").split("/");
  const vista = ["analise", "inspecoes", "modelos", "configuracoes", "sobre"].includes(pedida) ? pedida : "analise";
  $$(".vista").forEach((v) => (v.hidden = v.dataset.vista !== vista));
  $$("[data-rota]").forEach((a) => a.classList.toggle("ativo", a.dataset.rota === vista));
  if (vista === "analise") {
    if (idPedido && (!estado.analise || estado.analise.id !== idPedido)) abrirInspecao(idPedido);
    else if (!idPedido && estado.analise) mostrarVazio();
    else if (!estado.analise) carregarInicio();
  }
  if (vista === "inspecoes") carregarInspecoes();
  if (vista === "modelos") carregarModelos();
  if (vista === "configuracoes") carregarConfiguracoes();
}

function segmentado(seletor, aoMudar) {
  $$(`${seletor} button`).forEach((b) =>
    b.addEventListener("click", () => {
      $$(`${seletor} button`).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      aoMudar(b.dataset.valor);
    }),
  );
}
function marcarSegmentado(seletor, valor) {
  $$(`${seletor} button`).forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.valor === valor)));
}

// ================================================================= modelos

async function carregarListaModelos() {
  const d = await api("/api/modelos");
  estado.modelos = d.modelos;
  estado.ativo = d.ativo;
  const ativo = d.modelos.find((m) => m.id === d.ativo) || d.modelos[0];
  $("#modelo-nome").textContent = ativo ? ativo.nome : "—";
  $("#modelo-tipo").textContent = ativo ? (ativo.tipo === "regra" ? "Regra, sem IA" : ativo.arquitetura) : "";
  $("#sel-modelo").replaceChildren(...d.modelos.map((m) => new Option(m.nome, m.id)));
  $("#sel-modelo").value = estado.analise ? estado.analise.modelo.id : d.ativo;
}

async function carregarModelos() {
  try {
    await carregarListaModelos();
  } catch (e) {
    return falhou(e);
  }
  const grade = $("#grade-modelos");
  grade.replaceChildren();
  for (const m of estado.modelos) {
    const emUso = m.id === estado.ativo;
    const c = m.cartao || {};
    const detalhes = el("div", { class: "detalhes" });
    const linha = (rotulo, valor) => detalhes.append(el("div", {}, el("b", {}, `${rotulo}: `), valor));
    if (typeof c.treino === "string") linha("Treino", c.treino);
    else if (c.treino) linha("Treino", Object.values(c.treino).join(" · "));
    if (c.metricas) linha("Desempenho", Object.entries(c.metricas).map(([k, v]) => `${k} ${v ?? "–"}`).join(" · "));
    if (c.limitacoes && c.limitacoes.length) detalhes.append(el("b", {}, "Limitações"), el("ul", {}, c.limitacoes.map((l) => el("li", {}, l))));
    const rodape = emUso
      ? el("span", { class: "em-uso" }, icone("check"), "Em uso")
      : el("button", {
          class: "btn btn-sm",
          type: "button",
          onclick: async () => {
            try {
              await api("/api/modelos/ativo", json("PUT", { id: m.id }));
              avisar(`${m.nome} passa a ser usado nas próximas análises.`);
              carregarModelos();
            } catch (e) {
              falhou(e);
            }
          },
        }, "Usar este modelo");
    grade.append(
      el("div", { class: `cartao modelo${emUso ? " ativo" : ""}` },
        el("div", { class: "modelo-topo" },
          el("div", {}, el("h2", {}, m.nome), el("p", { class: "nota" }, `${m.arquitetura} · versão ${m.versao}`)),
          el("span", { class: `tipo ${m.tipo}` }, m.tipo === "regra" ? "Regra" : "IA treinada")),
        el("p", {}, m.descricao),
        el("div", { class: "fichas" }, m.classes.map((cl) => el("span", { class: "ficha" }, nomeClasse(cl, m)))),
        detalhes,
        el("div", { class: "rodape-modelo" }, el("span", { class: "nota" }, m.tipo === "regra" ? "Embutido no programa" : "Instalado em modelos"), rodape)),
    );
  }
}

// ================================================================= tela inicial

async function carregarInicio() {
  try {
    const [ex, lista] = await Promise.all([api("/api/exemplos"), api("/api/analises")]);
    estado.inspecoes = lista;
    atualizarContador();
    const recentes = lista.slice(0, 4);
    $("#bloco-recentes").hidden = !recentes.length;
    $("#recentes").replaceChildren(...recentes.map((it) => cartaoMiniatura(`/api/analises/${it.id}/miniatura.png?v=${encodeURIComponent(it.resumo.severidade + it.resumo.regioes)}`, it.arquivo, dataCurta(it), it.resumo.severidade, () => abrirInspecao(it.id))));
    $("#bloco-exemplos").hidden = !ex.itens.length;
    $("#exemplos-fonte").textContent = ex.fonte;
    $("#exemplos").replaceChildren(...ex.itens.map((it) => cartaoMiniatura(`/api/exemplos/${encodeURIComponent(it.nome)}/miniatura.jpg`, it.classe, it.nome, null, () => analisarExemplo(it.nome))));
  } catch {
    /* sem exemplos: a tela inicial funciona sem eles */
  }
}

function cartaoMiniatura(src, titulo, subtitulo, severidade, acao) {
  const legenda = el("span", { class: "legenda" },
    el("span", { class: "linha" }, el("b", {}, titulo), severidade ? el("span", { class: `selo ${severidade}` }, ROTULO_CURTO[severidade]) : null),
    el("span", {}, subtitulo));
  return el("button", { class: "miniatura", type: "button", onclick: acao }, el("img", { src, alt: titulo, loading: "lazy" }), legenda);
}

const dataCurta = (it) => (it.data_captura || it.criado_em || "").replace("T", " ").slice(0, 16);

function atualizarContador() {
  const c = $("#contador-inspecoes");
  c.textContent = String(estado.inspecoes.length);
  c.hidden = !estado.inspecoes.length;
}

// ================================================================= envio de arquivos

function abrirArquivos() {
  $("#arquivos").click();
}

async function enviarArquivos(lista) {
  const arquivos = [...lista].filter((f) => /\.(jpe?g|png)$/i.test(f.name));
  if (!arquivos.length) return avisar("Envie imagens JPEG ou PNG.", { erro: true });
  if (arquivos.length === 1) return analisarArquivo(arquivos[0]);
  return analisarLote(arquivos);
}

async function analisarArquivo(arquivo) {
  const dados = new FormData();
  dados.append("arquivo", arquivo);
  dados.append("modelo", estado.ativo || "");
  try {
    abrirAnalise(await comCarregamento("Analisando…", () => api("/api/analises", { method: "POST", body: dados })));
  } catch (e) {
    falhou(e);
  }
}

async function analisarLote(arquivos) {
  const barra = el("i");
  const itens = arquivos.map((f) => el("li", {}, el("span", {}, f.name), el("span", { class: "nota" }, "na fila")));
  const texto = el("p", {}, `0 de ${arquivos.length} analisadas`);
  const d = $("#dialogo");
  $("#dialogo-titulo").textContent = `Analisando ${arquivos.length} imagens`;
  $("#dialogo-conteudo").replaceChildren(texto, el("div", { class: "progresso" }, barra), el("ul", { class: "lote" }, itens));
  $("#dialogo-acoes").replaceChildren();
  d.onclose = null;
  d.showModal();
  let ok = 0;
  for (let i = 0; i < arquivos.length; i++) {
    const status = itens[i].lastChild;
    status.textContent = "analisando…";
    const dados = new FormData();
    dados.append("arquivo", arquivos[i]);
    dados.append("modelo", estado.ativo || "");
    try {
      const a = await api("/api/analises", { method: "POST", body: dados });
      status.replaceChildren(el("span", { class: `selo ${a.resumo.severidade}` }, ROTULO_CURTO[a.resumo.severidade]));
      ok++;
    } catch (e) {
      status.textContent = e.message.slice(0, 60);
      status.style.color = "var(--imediato-texto)";
    }
    barra.style.width = `${((i + 1) / arquivos.length) * 100}%`;
    texto.textContent = `${i + 1} de ${arquivos.length} processadas`;
  }
  texto.textContent = `${ok} de ${arquivos.length} analisadas.`;
  $("#dialogo-acoes").replaceChildren(
    el("button", { class: "btn", value: "fechar", type: "submit" }, "Fechar"),
    el("button", { class: "btn btn-primaria", value: "ver", type: "submit" }, "Ver inspeções"),
  );
  const escolha = await new Promise((r) => (d.onclose = () => r(d.returnValue)));
  if (escolha === "ver") location.hash = "inspecoes";
  else carregarInicio();
}

async function analisarExemplo(nome) {
  try {
    abrirAnalise(await comCarregamento("Analisando…", () => api(`/api/exemplos/${encodeURIComponent(nome)}/analisar`, json("POST", { modelo: estado.ativo }))));
  } catch (e) {
    falhou(e);
  }
}

async function abrirInspecao(id) {
  try {
    abrirAnalise(await api(`/api/analises/${id}`));
  } catch (e) {
    falhou(e);
    if (!estado.analise) mostrarVazio();
  }
}

// ================================================================= análise aberta

function decodificar(m) {
  const bin = atob(m.dados);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const valores = new Float32Array(bytes.buffer);
  let lo = Infinity;
  let hi = -Infinity;
  let validos = 0;
  for (const v of valores) {
    if (Number.isFinite(v)) {
      validos++;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  return { largura: m.largura, altura: m.altura, valores, lo, hi, validos };
}

function mostrarVazio() {
  estado.analise = null;
  estado.selecionada = null;
  $("#analise-vazia").hidden = false;
  $("#analise-cheia").hidden = true;
  if (location.hash !== "#analise") history.replaceState(null, "", "#analise");
  carregarInicio();
}

function abrirAnalise(a) {
  const nova = !estado.analise || estado.analise.id !== a.id;
  estado.analise = a;
  if (a.matriz) estado.matriz = decodificar(a.matriz);
  if (nova) {
    estado.faixaCompleta = null;
    estado.selecionada = null;
    estado.isoterma = { ligada: false, valor: null };
    $("#btn-isoterma").setAttribute("aria-pressed", "false");
    $("#isoterma-controle").hidden = true;
    definirFerramenta("selecionar");
    $("#btn-foto").setAttribute("aria-pressed", "false");
    $("#quadro-foto").hidden = true;
    $("#palco-imagens").classList.remove("com-foto");
    trocarAba("resultado");
    $("#conteudo").scrollTop = 0;
    window.scrollTo({ top: 0 });
  }
  $("#analise-vazia").hidden = true;
  $("#analise-cheia").hidden = false;
  if (location.hash !== `#analise/${a.id}`) {
    const vindoDeOutraTela = !location.hash.startsWith("#analise");
    history.pushState(null, "", `#analise/${a.id}`);
    if (vindoDeOutraTela) rota();
  }
  preencherCabecalho();
  mostrarEtapas(a.etapas);
  desenharTermograma();
  desenharCaixas();
  preencherResultado();
  preencherCondicoes();
  preencherLaudo();
  const sel = $("#sel-modelo");
  if ([...sel.options].some((o) => o.value === a.modelo.id)) sel.value = a.modelo.id;
}

function mostrarEtapas(tempos, andando = -1) {
  $("#etapas").replaceChildren(
    ...ETAPAS.map((nome, i) => {
      const feita = tempos ? true : i < andando;
      const classe = feita ? "feita" : i === andando ? "andando" : "";
      const marcador = el("span", { class: "marcador" }, feita ? icone("check") : String(i + 1));
      const tempo = el("span", { class: "tempo" }, tempos ? (tempos[i] ? `${tempos[i].ms} ms` : "pronto") : "");
      return el("li", { class: classe }, marcador, el("span", { class: "nome" }, nome), tempo);
    }),
  );
}

function preencherCabecalho() {
  const a = estado.analise;
  $("#a-arquivo").textContent = a.arquivo;
  $("#a-arquivo").title = a.arquivo;
  const e = [el("span", { class: `etiqueta ${a.radiometrica ? "medida" : "estimada"}` }, a.radiometrica ? "Temperatura medida" : "Temperatura estimada pelas cores")];
  if (a.metadados.camera) e.push(el("span", { class: "etiqueta" }, a.metadados.camera));
  if (a.metadados.data_hora) e.push(el("span", { class: "etiqueta" }, a.metadados.data_hora));
  e.push(el("span", { class: "etiqueta" }, a.modelo.nome));
  $("#a-etiquetas").replaceChildren(...e);
  $("#btn-foto").hidden = !a.tem_foto;
}

function faixaAtual() {
  if (estado.faixa === "equipamento") return estado.analise.matriz_info.faixa_exibicao;
  return [estado.matriz.lo, estado.matriz.hi];
}

const fora = document.createElement("canvas");
function desenharTermograma() {
  const { largura: W, altura: H, valores } = estado.matriz;
  const [lo, hi] = faixaAtual();
  const lut = estado.paletas[estado.paleta];
  const iso = estado.isoterma.ligada ? estado.isoterma.valor : null;
  fora.width = W;
  fora.height = H;
  const ctx = fora.getContext("2d");
  const img = ctx.createImageData(W, H);
  const d = img.data;
  const escala = 255 / Math.max(hi - lo, 1e-6);
  let acima = 0;
  for (let i = 0; i < valores.length; i++) {
    const v = valores[i];
    const j = i * 4;
    if (!Number.isFinite(v)) {
      d[j] = 30; d[j + 1] = 34; d[j + 2] = 42;
    } else {
      let k = ((v - lo) * escala) | 0;
      k = k < 0 ? 0 : k > 255 ? 255 : k;
      const c = lut[k];
      if (iso != null && v < iso) {
        const cinza = (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) * 0.55;
        d[j] = d[j + 1] = d[j + 2] = cinza;
      } else {
        d[j] = c[0]; d[j + 1] = c[1]; d[j + 2] = c[2];
        if (iso != null) acima++;
      }
    }
    d[j + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  const tela = $("#tela");
  tela.width = Math.max(1024, W * 4);
  tela.height = Math.round((tela.width * H) / W);
  const c2 = tela.getContext("2d");
  c2.imageSmoothingEnabled = true;
  c2.imageSmoothingQuality = "high";
  c2.drawImage(fora, 0, 0, tela.width, tela.height);
  if (iso != null) $("#isoterma-area").textContent = `${fmt((acima / Math.max(estado.matriz.validos, 1)) * 100, 1)}% da imagem`;

  const barra = $("#barra-cores");
  const cb = barra.getContext("2d");
  const faixa = cb.createImageData(256, 1);
  for (let x = 0; x < 256; x++) {
    const v = lo + (x / 255) * (hi - lo);
    const c = lut[x];
    const apagar = iso != null && v < iso;
    const cinza = (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) * 0.55;
    faixa.data.set(apagar ? [cinza, cinza, cinza, 255] : [c[0], c[1], c[2], 255], x * 4);
  }
  cb.putImageData(faixa, 0, 0);
  $("#escala-ticks").replaceChildren(...[0, 0.25, 0.5, 0.75, 1].map((f) => el("span", { style: { left: `${f * 100}%` } }, fmt(lo + f * (hi - lo), 1, f === 1 ? " °C" : ""))));
}

function corDaRegiao(r) {
  return COR_NIVEL[r.severidade] || "#FFFFFF";
}

function desenharCaixas() {
  const s = $("#sobreposicao");
  s.replaceChildren();
  const { largura: W, altura: H } = estado.matriz;
  const pos = (n, x0, y0, x1, y1) =>
    Object.assign(n.style, { left: `${(x0 / W) * 100}%`, top: `${(y0 / H) * 100}%`, width: `${((x1 - x0) / W) * 100}%`, height: `${((y1 - y0) / H) * 100}%` });
  for (const r of estado.analise.regioes) {
    const [x0, y0, x1, y1] = r.caixa;
    const cor = corDaRegiao(r);
    const etq = el("span", { class: "etq" }, el("i", { style: { background: cor } }), `${r.nome} · ${fmt(r.medida && r.medida.t_max, 1, " °C")}`);
    if (y0 / H < 0.08) Object.assign(etq.style, { bottom: "auto", top: "100%", marginTop: "4px", marginBottom: "0" });
    const caixa = el("div", {
      class: `caixa${r.id === estado.selecionada ? " selecionada" : ""}`,
      dataset: { id: r.id },
      style: { borderColor: cor },
      onmousedown: (ev) => { if (estado.ferramenta !== "desenhar") ev.stopPropagation(); },
      onclick: (ev) => { if (estado.ferramenta === "desenhar") return; ev.stopPropagation(); selecionar(r.id); },
    }, etq);
    pos(caixa, x0, y0, x1, y1);
    if (r.medida) {
      const p = el("span", { class: "pico" });
      p.style.left = `${((r.medida.x_max + 0.5 - x0) / (x1 - x0)) * 100}%`;
      p.style.top = `${((r.medida.y_max + 0.5 - y0) / (y1 - y0)) * 100}%`;
      caixa.append(p);
    }
    s.append(caixa);
  }
  if (estado.rascunho) {
    const { x0, y0, x1, y1 } = estado.rascunho;
    const r = el("div", { class: "caixa rascunho" });
    pos(r, Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1));
    s.append(r);
  }
  evitarColisaoDeEtiquetas(s);
}

function evitarColisaoDeEtiquetas(s) {
  // Uma etiqueta não cobre outra nem o ponto de máxima de outra região. Tenta, nesta ordem: no lado de
  // costume, no lado oposto da caixa e, por fim, só com a temperatura.
  const colide = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
  const ocupadas = $$(".caixa .pico", s).map((p) => p.getBoundingClientRect());
  const acima = { bottom: "", top: "", marginTop: "", marginBottom: "" };
  const abaixo = { bottom: "auto", top: "100%", marginTop: "4px", marginBottom: "0" };
  const etiquetas = $$(".caixa .etq", s).sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
  for (const etq of etiquetas) {
    const completo = etq.lastChild.textContent;
    const curto = completo.split(" · ").pop();
    const [lado, oposto] = etq.style.top === "100%" ? [abaixo, acima] : [acima, abaixo];
    let livre = null;
    for (const [posicao, texto] of [[lado, completo], [oposto, completo], [lado, curto], [oposto, curto]]) {
      Object.assign(etq.style, posicao);
      etq.lastChild.textContent = texto;
      const r = etq.getBoundingClientRect();
      if (!ocupadas.some((o) => colide(r, o))) {
        livre = r;
        break;
      }
    }
    if (!livre) {
      Object.assign(etq.style, lado);
      livre = etq.getBoundingClientRect();
    }
    ocupadas.push(livre);
  }
}

function selecionar(id, rolar = true) {
  estado.selecionada = estado.selecionada === id ? null : id;
  desenharCaixas();
  $$(".regiao").forEach((n) => n.classList.toggle("selecionada", n.dataset.id === estado.selecionada));
  if (rolar && estado.selecionada) {
    trocarAba("resultado");
    const n = $(`.regiao[data-id="${estado.selecionada}"]`);
    if (n) n.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function realcar(id, ligar) {
  const c = $(`.caixa[data-id="${id}"]`);
  if (c) c.classList.toggle("realce", ligar);
}

function preencherResultado() {
  const a = estado.analise;
  const r = a.resumo;
  const v = $("#veredito");
  v.className = `veredito ${r.severidade}`;
  $("use", v).setAttribute("href", r.severidade === "normal" ? "#i-check" : "#i-alerta");
  const indicativa = a.regioes.some((x) => x.indicativa && x.severidade === r.severidade);
  $("#veredito-titulo").textContent = r.severidade_rotulo + (indicativa && r.severidade !== "normal" ? " (indicativa)" : "");
  $("#veredito-texto").textContent = r.mensagem;
  $("#k-max").textContent = fmt(r.t_max_cena, 1, " °C");
  if (r.maior_pct_mta != null) {
    $("#k-dt-rotulo").textContent = "Mais perto da MTA";
    $("#k-dt").textContent = `${fmt(r.maior_pct_mta, 0)}%`;
  } else {
    const dts = a.regioes.filter((x) => x.ref_tipo === "semelhantes").map((x) => x.dt_corrigido);
    $("#k-dt-rotulo").textContent = "Maior ΔT entre fases";
    $("#k-dt").textContent = dts.length ? fmt(Math.max(...dts), 1, " °C") : "–";
  }
  $("#k-regioes").textContent = String(r.regioes);
  $("#avisos").replaceChildren(...(r.avisos || []).map((t) => el("li", {}, icone("info"), el("span", {}, t))));
  $("#criterio-nome").textContent = r.criterio;

  const lista = $("#regioes");
  if (!a.regioes.length) {
    lista.replaceChildren(el("div", { class: "regioes-vazio" }, "Nenhuma região. Use Desenhar (D) e arraste sobre a imagem."));
    return;
  }
  const [lo, hi] = faixaAtual();
  const classes = [...new Set([...(a.modelo.classes || []), ...CLASSES_PADRAO, ...a.regioes.map((x) => x.classe)])];
  lista.replaceChildren(
    ...a.regioes.map((x) => {
      const cor = corDaRegiao(x);
      const m = x.medida || {};
      const ref = x.referencia || {};
      const nome = el("input", { class: "nome", value: x.nome, "aria-label": "Nome da região", onchange: (ev) => atualizarRegiao(x.id, { nome: ev.target.value }) });
      const sel = el("select", { "aria-label": "Classe", onchange: (ev) => atualizarRegiao(x.id, { classe: ev.target.value }) }, classes.map((c) => new Option(nomeClasse(c), c)));
      sel.value = x.classe;
      const partes = [];
      if (x.pct_mta != null) {
        const mta = `MTA ${fmt(ref.mta_c, 0)} °C`;
        if (x.avaliacao_absoluta === "completa") partes.push(`≈ ${fmt(x.t_projetada, 1)} °C a plena carga (${mta})`);
        else if (x.avaliacao_absoluta === "sem_carga") partes.push(`${mta}, sem carga informada`);
        else partes.push(`${mta}, sem projeção`);
      }
      if (x.ref_tipo === "semelhantes") partes.push(`ΔT fases ${fmt(x.dt_corrigido, 1, " °C")}`);
      if (x.carga_limite) partes.push(x.carga_limite.pct_nominal != null ? `atinge a MTA com ${fmt(x.carga_limite.pct_nominal, 0)}% da carga` : `atinge a MTA com ${fmt(x.carga_limite.vezes_corrente_atual, 1)}× a corrente atual`);
      if (ref.aquecimento === "dieletrico" && x.ref_tipo !== "semelhantes") partes.push("compare com as outras fases");
      if (x.confianca != null) partes.push(`confiança ${fmt(x.confianca * 100, 0)}%`);
      const medidaSecundaria = x.pct_mta != null ? `${fmt(x.pct_mta, 0)}% da MTA` : x.ref_tipo === "semelhantes" ? `ΔT ${fmt(x.dt_corrigido, 1, " °C")}` : x.dt_entorno != null ? `+${fmt(x.dt_entorno, 1)} °C no entorno` : "";
      // A barra vai até a MTA (o limite do componente); sem MTA, até o topo da escala da imagem.
      const largura = x.pct_mta != null ? Math.min(100, Math.max(3, x.pct_mta)) : m.t_max != null ? Math.min(100, Math.max(3, ((m.t_max - lo) / Math.max(hi - lo, 1e-6)) * 100)) : 0;
      const tituloBarra = x.pct_mta != null ? `${fmt(x.t_projetada, 1)} °C de ${fmt(ref.mta_c, 0)} °C admissíveis (${ref.fonte || ""})` : "Temperatura máxima na escala da imagem";
      const remover = el("button", { class: "btn btn-sm btn-fantasma btn-icone remover", type: "button", title: "Remover (Delete)", "aria-label": `Remover ${x.nome}`, onclick: (ev) => { ev.stopPropagation(); removerRegiao(x.id); } }, icone("lixo"));
      const porque = x.criterio_disparo ? ` Critério: ${x.criterio_disparo.join(" e ")}.` : "";
      const selo = el("span", { class: `selo ${x.severidade}${x.indicativa ? " indicativa" : ""}`, title: `${x.severidade_rotulo}.${porque} ${x.acao}${x.indicativa ? " Classificação indicativa: informe ambiente e carga ou compare fases." : ""}` }, ROTULO_CURTO[x.severidade]);
      return el("div", {
        class: `regiao${x.id === estado.selecionada ? " selecionada" : ""}`,
        dataset: { id: x.id },
        onclick: (ev) => { if (!["INPUT", "SELECT", "BUTTON", "OPTION"].includes(ev.target.tagName)) selecionar(x.id, false); },
        onmouseenter: () => realcar(x.id, true),
        onmouseleave: () => realcar(x.id, false),
      },
        el("span", { class: "faixa", style: { background: cor } }),
        el("div", { class: "corpo" },
          el("div", { class: "linha1" }, nome, remover),
          el("div", { class: "linha2" }, sel, el("span", { class: "ref" }, partes.join(" · "))),
          el("div", { class: `termometro${x.pct_mta != null ? " limite" : ""}`, title: tituloBarra }, el("i", { style: { width: `${largura}%`, background: cor } }))),
        el("div", { class: "medidas" }, el("span", { class: "tmax" }, fmt(m.t_max, 1, " °C")), el("span", { class: "dt" }, medidaSecundaria), selo));
    }),
  );
}

function preencherCondicoes() {
  const a = estado.analise;
  $("#c-ambiente").value = a.condicoes.ambiente_c ?? "";
  $("#c-carga").value = a.condicoes.carga_pct ?? "";
  const m = a.metadados;
  const pares = [
    ["Origem", a.radiometrica ? "medida" : "estimada"],
    ["Câmera", m.camera],
    ["Emissividade", m.emissividade != null ? fmt(m.emissividade, 2) : null],
    ["Distância", m.distancia_m != null ? fmt(m.distancia_m, 1, " m") : null],
    ["T. refletida", m.temp_refletida_c != null ? fmt(m.temp_refletida_c, 1, " °C") : null],
    ["Umidade", m.umidade_relativa != null ? fmt(m.umidade_relativa * 100, 0, " %") : null],
    ["Sensor", m.resolucao_sensor],
    ["Escala lida", m.escala_lida_c ? `${fmt(m.escala_lida_c[0])} a ${fmt(m.escala_lida_c[1], 1, " °C")}` : null],
  ].filter(([, v]) => v);
  $("#meta").replaceChildren(...pares.map(([k, v]) => el("div", {}, el("dt", {}, k), el("dd", {}, v))));
}

function preencherLaudo() {
  const i = estado.analise.identificacao || {};
  $("#i-instalacao").value = i.instalacao || "";
  $("#i-equipamento").value = i.equipamento || "";
  $("#i-responsavel").value = i.responsavel || "";
  $("#i-art").value = i.art || "";
  $("#i-observacoes").value = i.observacoes || "";
}

function trocarAba(nome) {
  $$(".abas [role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.aba === nome)));
  $$(".painel-aba").forEach((p) => (p.hidden = p.dataset.painel !== nome));
}

function definirFerramenta(nome) {
  estado.ferramenta = nome;
  marcarSegmentado("#seg-ferramenta", nome);
  $("#sobreposicao").classList.toggle("desenhando", nome === "desenhar");
  $("#dica-desenho").hidden = nome !== "desenhar";
  if (nome !== "desenhar") estado.rascunho = null;
}

// ================================================================= edição de regiões

const paraEnvio = (r) => ({ id: r.id, nome: r.nome, classe: r.classe, caixa: r.caixa, confianca: r.confianca ?? null, origem: r.origem });

async function salvarRegioes(regioes) {
  try {
    abrirAnalise(await api(`/api/analises/${estado.analise.id}`, json("PUT", { regioes: regioes.map(paraEnvio) })));
  } catch (e) {
    falhou(e);
  }
}

function atualizarRegiao(id, mudancas) {
  salvarRegioes(estado.analise.regioes.map((r) => (r.id === id ? { ...r, ...mudancas } : r)));
}

async function removerRegiao(id) {
  const antes = estado.analise.regioes.slice();
  const alvo = antes.find((r) => r.id === id);
  if (estado.selecionada === id) estado.selecionada = null;
  await salvarRegioes(antes.filter((r) => r.id !== id));
  avisar(`${alvo ? alvo.nome : "Região"} removida.`, { acao: { rotulo: "Desfazer", executar: () => salvarRegioes(antes) } });
}

function coordenadas(ev) {
  const s = $("#sobreposicao").getBoundingClientRect();
  const { largura: W, altura: H } = estado.matriz;
  const fx = Math.min(1, Math.max(0, (ev.clientX - s.left) / s.width));
  const fy = Math.min(1, Math.max(0, (ev.clientY - s.top) / s.height));
  return { x: fx * W, y: fy * H, px: ev.clientX - s.left, py: ev.clientY - s.top, fx };
}

function ligarImagem() {
  const s = $("#sobreposicao");
  const leitura = $("#leitura");
  const marca = $("#escala-marca");
  s.addEventListener("mousemove", (ev) => {
    if (!estado.matriz) return;
    const { x, y, px, py } = coordenadas(ev);
    const { largura: W, altura: H, valores } = estado.matriz;
    const v = valores[Math.min(H - 1, Math.floor(y)) * W + Math.min(W - 1, Math.floor(x))];
    leitura.textContent = Number.isFinite(v) ? fmt(v, 1, " °C") : "sem medida";
    const larguraQuadro = s.clientWidth;
    leitura.style.left = `${px > larguraQuadro - 110 ? px - 110 : px}px`;
    leitura.style.top = `${py}px`;
    leitura.hidden = false;
    if (Number.isFinite(v)) {
      const [lo, hi] = faixaAtual();
      marca.style.left = `${Math.min(100, Math.max(0, ((v - lo) / Math.max(hi - lo, 1e-6)) * 100))}%`;
      marca.hidden = false;
    }
    if (estado.rascunho) {
      estado.rascunho.x1 = x;
      estado.rascunho.y1 = y;
      desenharCaixas();
    }
  });
  s.addEventListener("mouseleave", () => {
    leitura.hidden = true;
    marca.hidden = true;
  });
  s.addEventListener("mousedown", (ev) => {
    if (estado.ferramenta !== "desenhar" || ev.button !== 0) return;
    ev.preventDefault();
    const { x, y } = coordenadas(ev);
    estado.rascunho = { x0: x, y0: y, x1: x, y1: y };
  });
  s.addEventListener("click", () => {
    if (estado.ferramenta === "selecionar" && estado.selecionada) selecionar(estado.selecionada, false);
  });
  window.addEventListener("mouseup", () => {
    const r = estado.rascunho;
    if (!r) return;
    estado.rascunho = null;
    const caixa = [Math.min(r.x0, r.x1), Math.min(r.y0, r.y1), Math.max(r.x0, r.x1), Math.max(r.y0, r.y1)].map((v) => Math.round(v * 100) / 100);
    if (caixa[2] - caixa[0] < 1.5 || caixa[3] - caixa[1] < 1.5) return desenharCaixas();
    const n = estado.analise.regioes.filter((x) => x.origem === "manual").length + 1;
    salvarRegioes([...estado.analise.regioes, { id: null, nome: `Região ${n}`, classe: "componente", caixa, origem: "manual" }]);
  });
}

// ================================================================= inspeções

async function carregarInspecoes() {
  try {
    estado.inspecoes = await api("/api/analises");
  } catch (e) {
    return falhou(e);
  }
  atualizarContador();
  const total = estado.inspecoes.length;
  const conta = (niveis) => estado.inspecoes.filter((it) => niveis.includes(it.resumo.severidade)).length;
  const kpi = (rotulo, valor, cor) => el("div", { class: "kpi-grande" }, el("span", {}, cor ? el("i", { style: { background: cor } }) : null, rotulo), el("b", {}, String(valor)));
  $("#kpis-inspecoes").replaceChildren(
    kpi("Inspeções", total),
    kpi("Graves", conta(["urgente", "imediato"]), COR_NIVEL.imediato),
    kpi("Programar reparo", conta(["programar"]), COR_NIVEL.programar),
    kpi("Atenção", conta(["atencao"]), COR_NIVEL.atencao),
    kpi("Normais", conta(["normal"]), COR_NIVEL.normal),
  );
  $("#kpis-inspecoes").hidden = !total;
  $$(".filtros").forEach((f) => (f.hidden = !total));
  desenharInspecoes();
}

function desenharInspecoes() {
  const termo = estado.busca.trim().toLowerCase();
  const passa = {
    todas: () => true,
    grave: (s) => s === "urgente" || s === "imediato",
    programar: (s) => s === "programar",
    atencao: (s) => s === "atencao",
    normal: (s) => s === "normal",
  }[estado.filtro];
  let itens = estado.inspecoes.filter((it) => {
    if (!passa(it.resumo.severidade)) return false;
    if (!termo) return true;
    const texto = [it.arquivo, it.identificacao.instalacao, it.identificacao.equipamento].filter(Boolean).join(" ").toLowerCase();
    return texto.includes(termo);
  });
  if (estado.ordem === "graves") itens = itens.slice().sort((a, b) => NIVEIS.indexOf(b.resumo.severidade) - NIVEIS.indexOf(a.resumo.severidade));
  if (estado.ordem === "nome") itens = itens.slice().sort((a, b) => a.arquivo.localeCompare(b.arquivo));
  const grade = $("#grade-inspecoes");
  grade.replaceChildren(
    ...itens.map((it) => {
      const local = [it.identificacao.instalacao, it.identificacao.equipamento].filter(Boolean).join(" · ");
      const imagem = el("img", {
        src: `/api/analises/${it.id}/miniatura.png?v=${encodeURIComponent(it.resumo.severidade + it.resumo.regioes)}`,
        alt: it.arquivo, loading: "lazy", style: { cursor: "pointer" }, onclick: () => abrirInspecao(it.id),
      });
      const legenda = el("span", { class: "legenda" },
        el("span", { class: "linha" }, el("b", {}, it.arquivo), el("span", { class: `selo ${it.resumo.severidade}` }, ROTULO_CURTO[it.resumo.severidade])),
        el("span", {}, [dataCurta(it), local || `${it.resumo.regioes} regiões`].filter(Boolean).join(" · ")));
      const acoes = el("div", { class: "acoes-cartao" },
        el("button", { class: "btn btn-sm", type: "button", onclick: () => abrirInspecao(it.id) }, "Abrir"),
        el("button", { class: "btn btn-sm", type: "button", title: "Laudo em PDF", onclick: () => window.open(`/api/analises/${it.id}/laudo.pdf`, "_blank") }, icone("laudo"), "Laudo"),
        el("button", {
          class: "btn btn-sm btn-fantasma btn-icone", type: "button", title: "Apagar", "aria-label": `Apagar ${it.arquivo}`,
          onclick: async () => {
            if (!(await confirmar("Apagar inspeção?", `${it.arquivo} e suas regiões serão apagadas deste computador. Não dá para desfazer.`, "Apagar", true))) return;
            try {
              await api(`/api/analises/${it.id}`, { method: "DELETE" });
              if (estado.analise && estado.analise.id === it.id) estado.analise = null;
              avisar("Inspeção apagada.");
              carregarInspecoes();
            } catch (e) {
              falhou(e);
            }
          },
        }, icone("lixo")));
      return el("div", { class: "inspecao miniatura", style: { cursor: "default" } }, imagem, legenda, acoes);
    }),
  );
  const vazio = $("#inspecoes-vazio");
  vazio.hidden = itens.length > 0;
  if (!itens.length && estado.inspecoes.length) {
    $("h2", vazio).textContent = "Nada encontrado";
    $("p", vazio).textContent = "Nenhuma inspeção com esse filtro ou busca.";
  } else {
    $("h2", vazio).textContent = "Nenhuma inspeção por aqui";
    $("p", vazio).textContent = "Analise um termograma e ele aparece nesta lista.";
  }
}

// ================================================================= configurações

async function carregarConfiguracoes() {
  let c;
  try {
    c = await api("/api/configuracoes");
  } catch (e) {
    return falhou(e);
  }
  estado.config = c;
  $("#cfg-empresa-nome").value = c.empresa.nome || "";
  $("#cfg-empresa-sub").value = c.empresa.subtitulo || "";
  $("#cfg-resp-nome").value = c.responsavel.nome || "";
  $("#cfg-resp-registro").value = c.responsavel.registro || "";
  aplicarTema(c.tema);
  $("#pasta-dados").textContent = c.pasta_dados;
  $("#pasta-modelos").textContent = c.pasta_modelos;
  $("#versao-2").textContent = c.versao;
  preencherCriterio(c.criterio, c.criterio_personalizado);
  preencherComponentes(c.componentes, c.componentes_padrao);
}

const GRUPOS_CRITERIO = { mta_faixas: "%", similares: "°C", dieletrico: "°C", ambiente: "°C" };
const NIVEIS_EDITAVEIS = ["atencao", "programar", "urgente", "imediato"];

function preencherCriterio(crit, personalizado) {
  for (const [grupo, unidade] of Object.entries(GRUPOS_CRITERIO)) {
    $(`#crit-${grupo}`).replaceChildren(
      ...NIVEIS_EDITAVEIS.map((nivel) => {
        const achado = (crit[grupo] || []).find(([, n]) => n === nivel);
        return el("div", { class: "crit-linha" },
          el("span", {}, el("span", { class: `selo ${nivel}` }, ROTULO_CURTO[nivel]), " a partir de"),
          el("div", { class: "campo-unidade" },
            el("input", { type: "number", step: "0.1", min: "0", value: achado ? achado[0] : "", placeholder: "não usar", dataset: { grupo, nivel }, "aria-label": `${ROTULO_CURTO[nivel]}, limite em ${unidade}` }),
            el("span", {}, unidade)));
      }),
    );
  }
  $("#crit-usar-ambiente").checked = !!crit.usar_ambiente;
  $("#crit-ambiente").closest(".crit-grupo").classList.toggle("desligado", !crit.usar_ambiente);
  $("#crit-nome").value = crit.nome;
  $("#crit-expoente").value = crit.expoente_carga;
  $("#crit-carga").value = crit.carga_minima_pct;
  if (personalizado !== undefined) {
    $("#criterio-estado").textContent = personalizado
      ? "Critério personalizado em uso. As inspeções salvas são recalculadas quando ele muda."
      : "Em uso: modelo brasileiro (NBR 15866). Confira os limites com o seu termografista responsável.";
  }
}

function lerCriterio() {
  const grupo = (g) => $$(`input[data-grupo="${g}"]`).filter((i) => i.value !== "").map((i) => [Number(i.value), i.dataset.nivel]);
  return {
    nome: $("#crit-nome").value,
    similares: grupo("similares"),
    dieletrico: grupo("dieletrico"),
    mta_faixas: grupo("mta_faixas"),
    ambiente: grupo("ambiente"),
    usar_ambiente: $("#crit-usar-ambiente").checked,
    expoente_carga: Number($("#crit-expoente").value),
    carga_minima_pct: Number($("#crit-carga").value),
  };
}

function preencherComponentes(lista, padrao) {
  $("#lista-componentes").replaceChildren(
    ...Object.entries(lista).map(([classe, c]) => {
      const dieletrico = c.aquecimento === "dieletrico";
      const alterado = padrao[classe] && padrao[classe].mta_c !== c.mta_c;
      const campo = dieletrico
        ? el("span", { class: "nota" }, "não se aplica")
        : el("div", { class: "campo-unidade" }, el("input", { type: "number", step: "1", min: "20", max: "400", value: c.mta_c ?? "", dataset: { classe }, "aria-label": `MTA de ${c.nome}` }), el("span", {}, "°C"));
      return el("tr", { class: alterado ? "alterado" : "" },
        el("td", {}, el("b", {}, c.nome), el("div", { class: "nota" }, classe)),
        el("td", {}, el("span", { class: "aquecimento" }, AQUECIMENTO[c.aquecimento] || c.aquecimento)),
        el("td", {}, campo),
        el("td", {}, c.fonte));
    }),
  );
}

async function salvarConfig(parcial, mensagem) {
  try {
    const c = await api("/api/configuracoes", json("PUT", parcial));
    estado.config = c;
    if (mensagem) avisar(mensagem);
    return c;
  } catch (e) {
    falhou(e);
    return null;
  }
}

// ================================================================= sinal de vida (fecha o servidor junto com a janela)

function sinalDeVida() {
  // Cada janela tem sua identidade: fechar uma não derruba o servidor enquanto houver outra aberta.
  const cliente = Math.random().toString(36).slice(2, 10);
  const enviar = () => fetch(`/api/sinal?cliente=${cliente}`, { method: "POST" }).catch(() => {});
  enviar();
  setInterval(enviar, 20000);
  window.addEventListener("pagehide", () => navigator.sendBeacon(`/api/sinal?cliente=${cliente}&saindo=true`));
  window.addEventListener("pageshow", (e) => e.persisted && enviar());
}

// ================================================================= eventos

function ligarEventos() {
  const entrada = $("#arquivos");
  const soltar = $("#soltar");
  $("#btn-arquivos").addEventListener("click", (ev) => { ev.stopPropagation(); abrirArquivos(); });
  $$("[data-abrir-arquivos]").forEach((b) => b.addEventListener("click", abrirArquivos));
  soltar.addEventListener("click", abrirArquivos);
  soltar.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); abrirArquivos(); } });
  entrada.addEventListener("change", () => { enviarArquivos(entrada.files); entrada.value = ""; });
  ["dragenter", "dragover"].forEach((t) => soltar.addEventListener(t, (ev) => { ev.preventDefault(); soltar.classList.add("sobre"); }));
  ["dragleave", "drop"].forEach((t) => soltar.addEventListener(t, () => soltar.classList.remove("sobre")));
  soltar.addEventListener("drop", (ev) => { ev.preventDefault(); enviarArquivos(ev.dataTransfer.files); });
  window.addEventListener("dragover", (ev) => ev.preventDefault());
  window.addEventListener("drop", (ev) => {
    ev.preventDefault();
    if (ev.dataTransfer && ev.dataTransfer.files.length && !soltar.contains(ev.target)) enviarArquivos(ev.dataTransfer.files);
  });

  $("#btn-voltar").addEventListener("click", mostrarVazio);
  // "Análise" no menu volta para a análise aberta; o logotipo e o botão de voltar começam uma nova.
  $('.nav a[data-rota="analise"]').addEventListener("click", (ev) => {
    if (estado.analise) {
      ev.preventDefault();
      location.hash = `analise/${estado.analise.id}`;
    }
  });
  const gerarLaudo = () => window.open(`/api/analises/${estado.analise.id}/laudo.pdf`, "_blank");
  $("#btn-laudo").addEventListener("click", gerarLaudo);
  $("#btn-laudo-2").addEventListener("click", gerarLaudo);
  $("#btn-detectar").addEventListener("click", async () => {
    try {
      const a = await comCarregamento("Detectando…", () => api(`/api/analises/${estado.analise.id}/detectar`, json("POST", { modelo: $("#sel-modelo").value })), false);
      abrirAnalise(a);
      avisar(`Detecção refeita com ${a.modelo.nome}.`);
    } catch (e) {
      falhou(e);
    }
  });

  segmentado("#seg-paleta", (v) => { estado.paleta = v; desenharTermograma(); });
  segmentado("#seg-faixa", (v) => { estado.faixa = v; desenharTermograma(); preencherResultado(); });
  segmentado("#seg-ferramenta", definirFerramenta);
  $("#btn-nova-regiao").addEventListener("click", () => definirFerramenta("desenhar"));
  $("#btn-isoterma").addEventListener("click", (ev) => {
    const ligar = ev.currentTarget.getAttribute("aria-pressed") !== "true";
    ev.currentTarget.setAttribute("aria-pressed", String(ligar));
    const { lo, hi } = estado.matriz;
    const faixa = $("#isoterma-valor");
    faixa.min = String(Math.floor(lo));
    faixa.max = String(Math.ceil(hi));
    if (estado.isoterma.valor == null) estado.isoterma.valor = Math.round((hi - 0.15 * (hi - lo)) * 10) / 10;
    faixa.value = String(estado.isoterma.valor);
    $("#isoterma-saida").textContent = fmt(estado.isoterma.valor, 1, " °C");
    estado.isoterma.ligada = ligar;
    $("#isoterma-controle").hidden = !ligar;
    desenharTermograma();
  });
  $("#isoterma-valor").addEventListener("input", (ev) => {
    estado.isoterma.valor = Number(ev.target.value);
    $("#isoterma-saida").textContent = fmt(estado.isoterma.valor, 1, " °C");
    desenharTermograma();
  });
  $("#btn-foto").addEventListener("click", (ev) => {
    const ligar = ev.currentTarget.getAttribute("aria-pressed") !== "true";
    ev.currentTarget.setAttribute("aria-pressed", String(ligar));
    $("#quadro-foto").hidden = !ligar;
    $("#palco-imagens").classList.toggle("com-foto", ligar);
    if (ligar) $("#img-foto").src = `/api/analises/${estado.analise.id}/foto.jpg`;
  });
  $$(".abas [role=tab]").forEach((b) => b.addEventListener("click", () => trocarAba(b.dataset.aba)));

  $("#form-condicoes").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      abrirAnalise(await api(`/api/analises/${estado.analise.id}`, json("PUT", { condicoes: { ambiente_c: $("#c-ambiente").value, carga_pct: $("#c-carga").value } })));
      trocarAba("resultado");
      avisar("Severidade recalculada com as condições informadas.");
    } catch (e) {
      falhou(e);
    }
  });
  $("#form-laudo").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const identificacao = {
      instalacao: $("#i-instalacao").value, equipamento: $("#i-equipamento").value, responsavel: $("#i-responsavel").value,
      art: $("#i-art").value, observacoes: $("#i-observacoes").value,
    };
    try {
      abrirAnalise(await api(`/api/analises/${estado.analise.id}`, json("PUT", { identificacao })));
      avisar("Dados do laudo salvos.");
    } catch (e) {
      falhou(e);
    }
  });

  $("#busca").addEventListener("input", (ev) => { estado.busca = ev.target.value; desenharInspecoes(); });
  segmentado("#seg-filtro", (v) => { estado.filtro = v; desenharInspecoes(); });
  $("#ordem").addEventListener("change", (ev) => { estado.ordem = ev.target.value; desenharInspecoes(); });

  $("#form-empresa").addEventListener("submit", (ev) => {
    ev.preventDefault();
    salvarConfig({ empresa: { nome: $("#cfg-empresa-nome").value, subtitulo: $("#cfg-empresa-sub").value } }, "Empresa salva. Os próximos laudos saem com esse cabeçalho.");
  });
  $("#form-responsavel").addEventListener("submit", (ev) => {
    ev.preventDefault();
    salvarConfig({ responsavel: { nome: $("#cfg-resp-nome").value, registro: $("#cfg-resp-registro").value } }, "Responsável padrão salvo.");
  });
  segmentado("#seg-tema", (v) => { aplicarTema(v); salvarConfig({ tema: v }); });
  $("#form-criterio").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const c = await salvarConfig({ criterio: lerCriterio() }, "Critério salvo. As inspeções foram recalculadas.");
    if (c) preencherCriterio(c.criterio, c.criterio_personalizado);
  });
  $$("[data-modelo-criterio]").forEach((b) =>
    b.addEventListener("click", () => {
      const modelo = estado.config && estado.config.modelos_criterio[b.dataset.modeloCriterio];
      if (!modelo) return;
      preencherCriterio(modelo);
      avisar(`Modelo ${b.textContent} carregado no formulário. Salve para aplicar.`);
    }),
  );
  $("#crit-usar-ambiente").addEventListener("change", (ev) => $("#crit-ambiente").closest(".crit-grupo").classList.toggle("desligado", !ev.target.checked));
  $("#form-componentes").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const padrao = estado.config.componentes_padrao;
    const trocas = {};
    for (const i of $$("#lista-componentes input[data-classe]")) {
      const valor = i.value === "" ? null : Number(i.value);
      const base = padrao[i.dataset.classe];
      if (!base || base.mta_c !== valor) trocas[i.dataset.classe] = { mta_c: valor, fonte: valor == null ? "Sem MTA definida." : "Valor informado pelo usuário (fabricante ou critério próprio)." };
    }
    const c = await salvarConfig({ componentes: trocas }, "Biblioteca salva. As inspeções foram recalculadas.");
    if (c) preencherComponentes(c.componentes, c.componentes_padrao);
  });
  $("#btn-comp-padrao").addEventListener("click", async () => {
    if (!(await confirmar("Restaurar a biblioteca padrão?", "As MTAs voltam aos valores das normas e da prática brasileira, e as inspeções são recalculadas.", "Restaurar"))) return;
    const c = await salvarConfig({ componentes: null }, "Biblioteca padrão restaurada.");
    if (c) preencherComponentes(c.componentes, c.componentes_padrao);
  });
  $("#btn-crit-padrao").addEventListener("click", async () => {
    if (!(await confirmar("Restaurar o critério padrão?", "Os limites voltam ao modelo brasileiro (NBR 15866) e as inspeções são recalculadas.", "Restaurar"))) return;
    const c = await salvarConfig({ criterio: null }, "Critério padrão restaurado.");
    if (c) preencherCriterio(c.criterio, c.criterio_personalizado);
  });
  $("#btn-copiar-comando").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("#comando-treino").textContent);
      avisar("Comando copiado.");
    } catch {
      avisar("Não consegui copiar. Selecione o texto e use Ctrl + C.", { erro: true });
    }
  });

  document.addEventListener("keydown", (ev) => {
    const digitando = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "o") {
      ev.preventDefault();
      abrirArquivos();
      return;
    }
    if (digitando || $("#dialogo").open || !estado.analise || $("#analise-cheia").hidden) return;
    if (ev.key === "d" || ev.key === "D") definirFerramenta("desenhar");
    else if (ev.key === "s" || ev.key === "S" || ev.key === "v" || ev.key === "V") definirFerramenta("selecionar");
    else if (ev.key === "Escape") {
      definirFerramenta("selecionar");
      if (estado.selecionada) selecionar(estado.selecionada, false);
      desenharCaixas();
    } else if ((ev.key === "Delete" || ev.key === "Backspace") && estado.selecionada) {
      ev.preventDefault();
      removerRegiao(estado.selecionada);
    }
  });

  ligarImagem();
  window.addEventListener("hashchange", rota);
  window.addEventListener("popstate", rota);
}

async function iniciar() {
  ligarEventos();
  try {
    estado.paletas = await api("/api/paletas");
    const c = await api("/api/configuracoes");
    estado.config = c;
    aplicarTema(c.tema);
    $("#versao").textContent = c.versao;
    await carregarListaModelos();
  } catch (e) {
    falhou(e);
  }
  sinalDeVida();
  rota();
}

iniciar();
