"use strict";

// Pyron · interface. Textos em textos.js (TEXTOS), valores visuais em tokens.css.

// ================================================================= utilidades

const $ = (s, raiz = document) => raiz.querySelector(s);
const $$ = (s, raiz = document) => [...raiz.querySelectorAll(s)];
const T = TEXTOS;
const VERSAO_INTERFACE = "0.7.0"; // igual a VERSAO em app/servidor.py

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
  v == null || !Number.isFinite(v) ? T.geral.semValor : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }) + sufixo;
/** "2023-07-23T17:23:00" ou "2023-07-23 17:23:00" vira "23/07/2023 17:23". */
const dataHora = (iso) => {
  const t = String(iso || "").replace("T", " ");
  const m = t.match(/^(\d{4})-(\d{2})-(\d{2})(?: (\d{2}:\d{2}))?/);
  return m ? `${m[3]}/${m[2]}/${m[1]}${m[4] ? ` ${m[4]}` : ""}` : t.slice(0, 16);
};
/** Caminho longo de pasta vira as duas últimas partes; o completo fica no title. */
function caminhoCurto(caminho) {
  const partes = (caminho || "").split(/[\\/]/).filter(Boolean);
  return partes.length > 2 ? `…\\${partes.slice(-2).join("\\")}` : caminho;
}
const hora = (iso) => (iso || "").slice(11, 19);

const NIVEIS = ["normal", "atencao", "programar", "urgente", "imediato"];
const CLASSES_PADRAO = ["componente", "ponto_quente", "para_raio", "terminal_superior", "parte_isoladora", "terminal_inferior", "isolador", "bucha", "conexao", "cabo", "radiador", "tanque"];

/** Cor de severidade vinda dos tokens (tokens.css), para o que é desenhado no canvas e nas caixas. */
function corNivel(nivel) {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${nivel}`).trim() || getComputedStyle(document.documentElement).getPropertyValue("--branco").trim();
}

const estado = {
  analise: null, matriz: null, paletas: null, paleta: "ferro", faixa: "equipamento", ferramenta: "selecionar",
  selecionada: null, rascunho: null, isoterma: { ligada: false, valor: null }, processando: null,
  modelos: [], ativo: null, config: null, inspecoes: [], filtro: "todas", busca: "", ordem: "recentes",
  exibir: lerPreferencia("exibir", "tabela"), abaConfig: "identidade", monitor: null, alertasPendentes: null, vista: null,
  selecao: new Set(), // inspeções marcadas para um relatório com várias imagens
  camada: "tudo", // tudo, pecas ou pontos: o que aparece no termograma e na lista de regiões
  rotulos: lerPreferencia("rotulos", "sim") !== "nao",
};

function lerPreferencia(chave, padrao) {
  try { return localStorage.getItem(`pyron.${chave}`) || padrao; } catch { return padrao; }
}
function guardarPreferencia(chave, valor) {
  try { localStorage.setItem(`pyron.${chave}`, valor); } catch { /* sem armazenamento: só não lembra */ }
}

function nomeClasse(c, modelo) {
  const nomes = (modelo || (estado.analise && estado.analise.modelo) || {}).nomes || {};
  return nomes[c] || T.classes[c] || c;
}

// ================================================================= servidor

async function api(caminho, opcoes = {}) {
  let r;
  try {
    r = await fetch(caminho, opcoes);
  } catch {
    mostrarOffline(true);
    throw new Error(T.geral.semResposta);
  }
  mostrarOffline(false);
  const tipo = r.headers.get("content-type") || "";
  const corpo = tipo.includes("application/json") ? await r.json() : null;
  // Servidor antigo na memória não conhece as rotas novas: explica o que fazer em vez de "Not Found".
  if (r.status === 404 && estado.versaoServidor && estado.versaoServidor !== VERSAO_INTERFACE) {
    throw new Error(T.geral.versaoDiferente(estado.versaoServidor, VERSAO_INTERFACE));
  }
  if (!r.ok) throw new Error((corpo && (corpo.erro || corpo.detail)) || T.geral.erroServidor(r.status));
  return corpo;
}
const json = (metodo, corpo) => ({ method: metodo, headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });

function mostrarOffline(ligar) {
  const faixa = $("#offline");
  const estava = !faixa.hidden;
  faixa.hidden = !ligar;
  const chip = $("#chip-servidor .ponto");
  chip.className = `ponto ${ligar ? "erro" : "ok"}`;
  // O servidor voltou (talvez numa versão nova, reaberto pelo Pyron.exe): recarrega a página inteira.
  if (estava && !ligar) location.reload();
}

// ================================================================= avisos, diálogos e estados

function avisar(texto, { erro = false, acao = null, duracao } = {}) {
  const a = el("div", { class: `aviso${erro ? " erro" : ""}`, role: erro ? "alert" : "status" }, icone(erro ? "alerta" : "check"), el("span", {}, texto));
  const sair = () => {
    a.classList.add("saindo");
    setTimeout(() => a.remove(), 160);
  };
  if (acao) a.append(el("button", { type: "button", onclick: () => { acao.executar(); sair(); } }, acao.rotulo));
  $("#toasts").append(a);
  setTimeout(sair, duracao || (erro ? 8000 : acao ? 7000 : 3500));
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
    acoes: [{ rotulo: T.geral.cancelar, valor: "nao" }, { rotulo, valor: "sim", classe: perigo ? "btn-perigo btn-primaria" : "btn-primaria" }],
  }).then((v) => v === "sim");
}

/** Esqueletos de carregamento: a forma do conteúdo que vem, sem girar nada no meio da tela. */
const esqueleto = {
  linhas: (n = 3) => el("div", { class: "pilha" }, Array.from({ length: n }, (_, i) => el("div", { class: "esqueleto esq-linha", style: { width: `${90 - i * 15}%` } }))),
  kpis: (n = 4) => el("div", { class: "kpis-grandes" }, Array.from({ length: n }, () => el("div", { class: "esqueleto esq-kpi" }))),
  bloco: () => el("div", { class: "esqueleto esq-bloco" }),
  tabela: (n = 5) => el("div", { class: "cartao pilha" }, el("div", { class: "esqueleto esq-titulo" }), Array.from({ length: n }, () => el("div", { class: "esqueleto esq-linha" }))),
};

function estadoErro(titulo, erro, tentar) {
  return el("div", { class: "estado-erro", role: "alert" },
    icone("alerta"), el("h2", {}, titulo), el("p", {}, erro.message || String(erro)),
    tentar ? el("div", { class: "acoes" }, el("button", { class: "btn", type: "button", onclick: tentar }, icone("refazer"), T.geral.tentarDeNovo)) : null);
}

function estadoVazio({ nomeIcone = "inspecoes", titulo, texto, acoes = [], compacto = false }) {
  return el("div", { class: `vazio${compacto ? " compacto" : ""}` }, icone(nomeIcone), el("h2", {}, titulo), el("p", {}, texto), acoes.length ? el("div", { class: "acoes" }, acoes) : null);
}

/** Entrada escalonada dos primeiros itens de uma lista (no máximo 6, 30 ms entre eles). */
function animarEntrada(nos) {
  nos.slice(0, 6).forEach((n, i) => {
    n.classList.add("entra");
    n.style.setProperty("--i", i);
  });
  return nos;
}

function ocupado(botao, ligar) {
  botao.classList.toggle("ocupado", ligar);
  botao.setAttribute("aria-busy", String(ligar));
}

// ================================================================= tema, navegação e barra de status

const midiaEscura = window.matchMedia("(prefers-color-scheme: dark)");
function aplicarTema(tema) {
  const escolhido = tema || "claro";
  const efetivo = escolhido === "sistema" ? (midiaEscura.matches ? "escuro" : "claro") : escolhido;
  document.documentElement.dataset.tema = efetivo;
  document.documentElement.dataset.temaEscolhido = escolhido;
  $$("#seg-tema button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.valor === escolhido)));
  if (estado.analise && estado.matriz) desenharCaixas();
}
midiaEscura.addEventListener("change", () => {
  if (document.documentElement.dataset.temaEscolhido === "sistema") aplicarTema("sistema");
});

const VISTAS = ["painel", "analise", "video", "inspecoes", "equipamentos", "pendencias", "monitoramento", "modelos", "avaliacao", "configuracoes", "sobre"];

function mostrarVista(vista) {
  const trocou = estado.vista !== vista;
  estado.vista = vista;
  $$(".vista").forEach((v) => {
    const ativa = v.dataset.vista === vista;
    v.hidden = !ativa;
    if (ativa && trocou) {
      v.classList.remove("entrando");
      void v.offsetWidth; // reinicia a animação de entrada
      v.classList.add("entrando");
    }
  });
  atualizarTrilha();
  // O botão global de nova análise some na própria tela de nova análise (um primário por área).
  $("#topo-nova").hidden = vista === "analise" && !estado.analise && !estado.processando;
  if (trocou) window.scrollTo({ top: 0 });
}

/** Trilha do topo e item ativo do menu. Uma inspeção aberta pertence a Inspeções, não a Nova análise. */
function atualizarTrilha() {
  const vista = estado.vista;
  const aberta = vista === "analise" && (estado.analise || estado.processando);
  const itemMenu = aberta && estado.analise ? "inspecoes" : vista;
  $$("[data-rota]").forEach((a) => {
    a.classList.toggle("ativo", a.dataset.rota === itemMenu);
    if (a.dataset.rota === itemMenu) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  let partes = [...T.rotas[vista]];
  let link = null; // o segundo nível vira link quando há um item aberto dentro dele
  if (aberta && estado.analise) {
    partes = [T.rotas.inspecoes[0], T.rotas.inspecoes[1], estado.analise.arquivo];
    link = "#inspecoes";
  } else if (aberta) {
    partes = [...T.rotas.analise, estado.processando.nome];
  } else if (vista === "equipamentos" && estado.equipamentoAberto && location.hash.includes("/")) {
    const d = estado.equipamentoAberto;
    partes = [...T.rotas.equipamentos, d.equipamento || T.equip.semEquipTitulo(d.inspecoes)];
    link = "#equipamentos";
  } else if (vista === "video" && vid.id && vid.dados) {
    partes = [...T.rotas.video, vid.dados.arquivo];
    link = "#video";
  }
  const trilha = $("#trilha");
  trilha.replaceChildren();
  partes.forEach((p, i) => {
    if (i) trilha.append(icone("seta"));
    const ultimo = i === partes.length - 1;
    if (!ultimo && i === 1 && link) trilha.append(el("a", { href: link }, p));
    else trilha.append(ultimo ? el("b", {}, p) : el("span", {}, p));
  });
  document.title = `${partes[partes.length - 1]} · Pyron`;
}

function rota() {
  const [pedida, sub] = (location.hash.replace("#", "") || "painel").split("/");
  const vista = VISTAS.includes(pedida) ? pedida : "painel";
  if (vista === "analise") {
    if (estado.processando) return mostrarVista(vista);
    if (sub) {
      if (!estado.analise || estado.analise.id !== sub) abrirInspecao(sub);
      else mostrarAnaliseAberta();
    } else {
      mostrarVazio();
    }
  }
  mostrarVista(vista);
  if (vista === "painel") carregarPainel();
  if (vista === "inspecoes") carregarInspecoes();
  if (vista === "monitoramento") carregarMonitoramento();
  if (vista === "modelos") {
    carregarModelos();
    if (sub === "treinar") setTimeout(() => $("#cartao-treinar").scrollIntoView({ behavior: "smooth", block: "start" }), 150);
  }
  if (vista === "avaliacao") carregarAvaliacoes();
  if (vista === "configuracoes") carregarConfiguracoes(sub);
  if (vista === "pendencias") carregarPendencias();
  if (vista === "equipamentos") {
    estado.equipamentoAberto = null;
    carregarEquipamentos(sub);
  }
  if (vista === "video") {
    if (sub) abrirVideo(sub);
    else mostrarInicioVideo();
  } else {
    pararVideo();
  }
}

function segmentado(seletor, aoMudar) {
  $$(`${seletor} button`).forEach((b) =>
    b.addEventListener("click", () => {
      if (b.disabled) return;
      $$(`${seletor} button`).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      aoMudar(b.dataset.valor);
    }),
  );
}
function marcarSegmentado(seletor, valor) {
  $$(`${seletor} button`).forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.valor === valor)));
}

async function atualizarStatus() {
  let s;
  try {
    s = await api("/api/status");
  } catch {
    return;
  }
  const m = s.monitoramento;
  const classe = m.erro && m.ativo ? "erro" : m.ativo ? "ativo" : "desligado";
  const texto = m.erro && m.ativo ? T.monitor.chipErro : m.ativo ? T.monitor.chipLigado : T.monitor.chipDesligado;
  $("#chip-monitor .ponto").className = `ponto ${classe}`;
  $("#chip-monitor span").textContent = texto;
  const ponto = $("#nav-monitor-ponto");
  ponto.hidden = !m.ativo;
  ponto.className = `ponto ${classe}`;
  const chipTreino = $("#chip-treino");
  chipTreino.hidden = !s.treino;
  if (s.treino) $("span", chipTreino).textContent = T.treino.chip(s.treino);
  if (s.treino && estado.vista === "modelos") carregarTreinos();
  const n = s.alertas_pendentes;
  $("#contador-alertas").textContent = String(n);
  $("#contador-alertas").hidden = !n;
  $("#alertas-n").textContent = String(n);
  $("#alertas-n").hidden = !n;
  $("#btn-alertas").setAttribute("aria-label", n ? `Alertas: ${T.monitor.alertasPendentes(n)}` : "Alertas do monitoramento");
  if (estado.alertasPendentes != null && n > estado.alertasPendentes && estado.vista !== "monitoramento") {
    avisar(T.monitor.novoAlerta(T.monitor.alertasPendentes(n)), { erro: true, acao: { rotulo: T.monitor.verAlerta, executar: () => (location.hash = "monitoramento") } });
  }
  estado.alertasPendentes = n;
  if (estado.vista === "monitoramento" && m.ativo) desenharEstadoMonitor(m, n);
}

// ================================================================= modelos (lista usada em várias telas)

async function carregarListaModelos() {
  const d = await api("/api/modelos");
  estado.modelos = d.modelos;
  estado.ativo = d.ativo;
  const ativo = d.modelos.find((m) => m.id === d.ativo) || d.modelos[0];
  $("#modelo-nome").textContent = ativo ? ativo.nome : T.geral.semValor;
  $("#modelo-tipo").textContent = ativo ? (ativo.tipo === "regra" ? T.modelos.regraSemIa : ativo.arquitetura) : "";
  $("#sel-modelo").replaceChildren(...d.modelos.map((m) => new Option(m.nome, m.id)));
  $("#sel-modelo").value = estado.analise ? estado.analise.modelo.id : d.ativo;
}

async function carregarModelos() {
  const grade = $("#grade-modelos");
  if (estado.config) $("#pasta-modelos").textContent = estado.config.pasta_modelos;
  if (!$("#treino-etapa").childElementCount) desenharEtapaTreino();
  verificarAmbiente();
  carregarTreinos();
  grade.replaceChildren(esqueleto.bloco(), esqueleto.bloco());
  try {
    await carregarListaModelos();
  } catch (e) {
    return grade.replaceChildren(estadoErro(T.modelos.erroTitulo, e, carregarModelos));
  }
  const cartoes = estado.modelos.map((m) => {
    const emUso = m.id === estado.ativo;
    const c = m.cartao || {};
    const detalhes = el("div", { class: "detalhes" });
    const linha = (rotulo, valor) => detalhes.append(el("div", {}, el("b", {}, `${rotulo}: `), valor));
    if (typeof c.treino === "string") linha(T.modelos.treino, c.treino);
    else if (c.treino) linha(T.modelos.treino, Object.values(c.treino).join(" · "));
    if (c.metricas) linha(T.modelos.desempenho, Object.entries(c.metricas).map(([k, v]) => `${k} ${v ?? T.geral.semValor}`).join(" · "));
    if (c.limitacoes && c.limitacoes.length) detalhes.append(el("b", {}, T.modelos.limitacoes), el("ul", {}, c.limitacoes.map((l) => el("li", {}, l))));
    const rodape = emUso
      ? el("span", { class: "em-uso" }, icone("check"), T.modelos.emUso)
      : el("button", {
          class: "btn btn-sm", type: "button",
          onclick: async (ev) => {
            ocupado(ev.currentTarget, true);
            try {
              await api("/api/modelos/ativo", json("PUT", { id: m.id }));
              avisar(T.modelos.passaASer(m.nome));
              carregarModelos();
            } catch (e) {
              ocupado(ev.currentTarget, false);
              falhou(e);
            }
          },
        }, T.modelos.usar);
    return el("div", { class: `cartao modelo${emUso ? " ativo" : ""}` },
      el("div", { class: "modelo-topo" },
        el("div", {}, el("h2", {}, m.nome), el("p", { class: "nota" }, T.modelos.versao(m.arquitetura, m.versao))),
        el("span", { class: `tipo ${m.tipo}` }, { regra: T.modelos.regra, combinado: T.modelos.combinado }[m.tipo] || T.modelos.ia)),
      el("p", {}, m.descricao),
      el("div", { class: "fichas" }, m.classes.map((cl) => el("span", { class: "ficha" }, nomeClasse(cl, m)))),
      detalhes,
      el("div", { class: "rodape-modelo" }, el("span", { class: "nota" }, { regra: T.modelos.embutido, combinado: T.modelos.combinadoNota }[m.tipo] || T.modelos.instaladoEm), rodape));
  });
  grade.replaceChildren(...animarEntrada(cartoes));
}

// ================================================================= treino de modelos

let relogioTreinos = null;

async function verificarAmbiente() {
  const chip = $("#ambiente-treino");
  if (estado.ambiente) return desenharAmbiente();
  chip.className = "etiqueta";
  chip.textContent = T.treino.ambienteVerificando;
  try {
    estado.ambiente = await api("/api/treinos/ambiente");
  } catch (e) {
    estado.ambiente = { ok: false, mensagem: e.message };
  }
  desenharAmbiente();
  desenharEtapaTreino();
}

function desenharAmbiente() {
  const a = estado.ambiente;
  const chip = $("#ambiente-treino");
  chip.className = `etiqueta ${a.ok ? "disponivel" : "estimada"}`;
  chip.textContent = a.ok ? a.mensagem : T.treino.ambienteBloqueado;
  $("#ambiente-aviso").replaceChildren(a.ok ? "" : el("ul", { class: "avisos" }, el("li", {}, icone("alerta"), el("span", {}, a.mensagem))));
}

function desenharEtapaTreino() {
  const alvo = $("#treino-etapa");
  const t = estado.treino;
  if (!t) {
    const entrada = el("input", { type: "file", accept: ".zip,.json", multiple: true, hidden: true, onchange: (ev) => { if (ev.target.files.length) enviarRotulos([...ev.target.files]); } });
    const zona = el("div", { class: "soltar compacto", tabindex: "0", role: "button", "aria-label": T.treino.soltar,
      onclick: () => entrada.click(), onkeydown: (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); entrada.click(); } } },
      el("div", { class: "soltar-icone" }, icone("upload")), el("h2", {}, T.treino.soltar), el("p", {}, T.treino.soltarNota),
      el("button", { class: "btn", type: "button", onclick: (ev) => { ev.stopPropagation(); entrada.click(); } }, T.treino.escolher), entrada);
    ["dragenter", "dragover"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); e.stopPropagation(); zona.classList.add("sobre"); }));
    ["dragleave", "drop"].forEach((ev) => zona.addEventListener(ev, () => zona.classList.remove("sobre")));
    zona.addEventListener("drop", (e) => { e.preventDefault(); e.stopPropagation(); if (e.dataTransfer.files.length) enviarRotulos([...e.dataTransfer.files]); });
    return alvo.replaceChildren(zona);
  }
  const r = t.relatorio;
  const s = t.sugestao;
  const kpi = (rotulo, valor, nota) => el("div", { class: "kpi-grande" }, el("span", {}, rotulo), el("b", {}, String(valor)), nota ? el("small", {}, nota) : null);
  const maior = Math.max(1, ...r.classes.map((c) => c.rotulos));
  const tabela = el("table", { class: "tabela" },
    el("thead", {}, el("tr", {}, T.treino.colunasClasses.map((c, i) => el("th", { class: i ? "direita" : null }, c)))),
    el("tbody", {}, r.classes.map((c) => el("tr", {},
      el("td", {}, el("div", { class: "principal-celula" }, el("b", {}, c.nome), el("div", { class: "barra-classe" }, el("i", { style: { width: `${(c.rotulos / maior) * 100}%` } })))),
      el("td", { class: "num direita" }, String(c.rotulos)),
      el("td", { class: "num direita" }, String(c.imagens))))));
  const avisos = r.avisos.length ? el("ul", { class: "avisos" }, r.avisos.map((a) => el("li", {}, icone("info"), el("span", {}, a)))) : null;

  const campoNome = el("input", { id: "t-nome", value: s.nome, oninput: (ev) => { $("#t-id").value = idDoNome(ev.target.value); } });
  const temCvat = Object.keys(r.subconjuntos).length > 0;
  const divisao = el("div", { class: "segmentado", role: "group", "aria-label": T.treino.divisao, id: "seg-divisao" },
    el("button", { type: "button", "data-valor": "sessao", "aria-pressed": "true" }, T.treino.porSessao),
    el("button", { type: "button", "data-valor": "cvat", "aria-pressed": "false", disabled: !temCvat || null }, T.treino.doCvat));
  $$("button", divisao).forEach((b) => b.addEventListener("click", () => { if (!b.disabled) $$("button", divisao).forEach((x) => x.setAttribute("aria-pressed", String(x === b))); }));
  const podeTreinar = r.pronto && estado.ambiente && estado.ambiente.ok;
  const botaoTreinar = el("button", { class: "btn btn-primaria", type: "submit", disabled: !podeTreinar || null,
    title: !r.pronto ? T.treino.naoPronto : estado.ambiente && !estado.ambiente.ok ? estado.ambiente.mensagem : null }, icone("modelos"), T.treino.comecar);
  const form = el("form", { class: "form", onsubmit: (ev) => { ev.preventDefault(); iniciarTreino(ev.submitter || botaoTreinar); } },
    el("div", { class: "campos-3" },
      el("label", {}, T.treino.nome, campoNome),
      el("label", {}, T.treino.id, el("input", { id: "t-id", value: s.id, spellcheck: "false", pattern: "[a-z0-9][a-z0-9-]{2,48}" }), el("span", { class: "ajuda" }, T.treino.idAjuda)),
      el("label", {}, T.treino.epocas, el("input", { id: "t-epocas", type: "number", min: "1", max: "500", value: String(s.epocas) }), el("span", { class: "ajuda" }, T.treino.epocasAjuda))),
    el("label", {}, T.treino.divisao, divisao, el("span", { class: "ajuda" }, T.treino.divisaoAjuda)),
    el("div", { class: "form-acoes" },
      el("button", { class: "btn btn-fantasma", type: "button", onclick: () => { estado.treino = null; desenharEtapaTreino(); } }, T.treino.trocar),
      el("button", { class: "btn", type: "button", title: T.treino.pacoteNota, onclick: (ev) => baixarPacote(ev.currentTarget) }, icone("externo"), T.treino.pacote),
      botaoTreinar));

  alvo.replaceChildren(el("div", { class: "pilha entra" },
    el("div", { class: "kpis-grandes" },
      kpi(T.treino.imagensProntas, r.imagens_utilizaveis, T.treino.deTotal(r.imagens_rotuladas)),
      kpi(T.treino.rotulos, r.rotulos, T.treino.tipos(r.tipos)),
      kpi(T.treino.classes, r.classes.length, r.arquivo),
      kpi(T.treino.sessoes, r.sessoes, temCvat ? T.treino.divisaoCvat(r.subconjuntos) : null)),
    el("div", { class: "cartao tabela-cartao" }, tabela),
    avisos, form));
}

const idDoNome = (nome) => {
  const base = nome.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 36) || "modelo";
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${base}-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
};

async function enviarRotulos(arquivos) {
  const alvo = $("#treino-etapa");
  alvo.replaceChildren(el("div", { class: "pilha" }, el("p", { class: "nota" }, T.treino.analisando), esqueleto.kpis(4), esqueleto.tabela(3)));
  const dados = new FormData();
  [].concat(arquivos).forEach((a) => dados.append("arquivos", a));
  try {
    estado.treino = await api("/api/treinos/rotulos", { method: "POST", body: dados });
    desenharEtapaTreino();
  } catch (e) {
    alvo.replaceChildren(estadoErro(T.treino.erroAnalise, e, () => { estado.treino = null; desenharEtapaTreino(); }));
  }
}

function pedidoDeTreino() {
  return {
    arquivo: estado.treino.arquivo,
    nome: $("#t-nome").value.trim(),
    id: $("#t-id").value.trim(),
    epocas: Number($("#t-epocas").value || 60),
    divisao: ($("#seg-divisao button[aria-pressed='true']") || {}).dataset?.valor || "sessao",
  };
}

async function iniciarTreino(botao) {
  const pedido = pedidoDeTreino();
  ocupado(botao, true);
  try {
    await api("/api/treinos", json("POST", pedido));
    avisar(T.treino.iniciado(pedido.nome));
    estado.treino = null;
    desenharEtapaTreino();
    carregarTreinos();
    atualizarStatus();
    $("#lista-treinos").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    falhou(e);
  } finally {
    ocupado(botao, false);
  }
}

async function baixarPacote(botao) {
  ocupado(botao, true);
  try {
    const r = await fetch("/api/treinos/pacote", json("POST", pedidoDeTreino()));
    if (!r.ok) {
      const corpo = await r.json().catch(() => null);
      throw new Error((corpo && corpo.erro) || T.geral.erroServidor(r.status));
    }
    const nome = (r.headers.get("content-disposition") || "").match(/filename="([^"]+)"/)?.[1] || "Pyron_pacote_treino.zip";
    const link = el("a", { href: URL.createObjectURL(await r.blob()), download: nome });
    document.body.append(link);
    link.click();
    link.remove();
    avisar(T.treino.pacoteBaixado);
  } catch (e) {
    falhou(e);
  } finally {
    ocupado(botao, false);
  }
}

async function carregarTreinos() {
  let lista;
  try {
    lista = (await api("/api/treinos")).treinos;
  } catch {
    return;
  }
  const alvo = $("#lista-treinos");
  alvo.replaceChildren(...lista.slice(0, 5).map(cartaoTreino));
  const andando = lista.some((t) => !["pronto", "erro", "cancelado", "interrompido"].includes(t.etapa));
  // Com treino andando, atualiza a cada 2 s enquanto a tela Modelos estiver aberta.
  clearTimeout(relogioTreinos);
  if (estado.vista === "modelos" && andando) relogioTreinos = setTimeout(carregarTreinos, 2000);
  // Treino que acabou de terminar: a lista de modelos ganha o novo.
  const prontos = lista.filter((t) => t.etapa === "pronto").map((t) => t.id).join();
  if (estado.treinosProntos !== undefined && prontos !== estado.treinosProntos) carregarModelos();
  estado.treinosProntos = prontos;
}

function cartaoTreino(t) {
  const final = ["pronto", "erro", "cancelado", "interrompido"].includes(t.etapa);
  const selo = el("span", { class: `etiqueta ${T.treino.classeEtapa[t.etapa] || "info"}` }, T.treino.etapas[t.etapa] || t.etapa);
  const perdas = t.perda || [];
  const linhaInfo = [
    t.mensagem,
    t.etapa === "treinando" && perdas.length ? T.treino.perda(fmt(perdas[perdas.length - 1], 3), fmt(perdas[0], 3)) : null,
    t.imagens_treino ? T.treino.divisaoUsada(t.divisao || "", t.imagens_treino, t.imagens_teste) : null,
  ].filter(Boolean).join(" · ") + (t.etapa === "treinando" ? T.treino.restante(t.restante) : "");
  const corpo = [
    el("div", { class: "cartao-cabeca", style: { marginBottom: 0 } },
      el("div", {}, el("h2", {}, t.nome), el("p", { class: "nota mono" }, `${t.id}${t.dispositivo ? " · " + t.dispositivo : ""}`)), selo),
  ];
  if (!final) {
    corpo.push(el("div", { class: "progresso", role: "progressbar", "aria-valuenow": String(t.percentual), "aria-valuemin": "0", "aria-valuemax": "100" },
      el("i", { style: { transform: `scaleX(${t.percentual / 100})` } })));
  }
  corpo.push(el("p", { class: t.etapa === "erro" || t.etapa === "interrompido" ? "nota texto-erro" : "nota" }, linhaInfo));
  if (t.etapa === "pronto" && t.metricas) corpo.push(metricasTreino(t));
  const acoes = [];
  if (!final) acoes.push(el("button", { class: "btn btn-sm btn-perigo", type: "button", onclick: () => cancelarTreino(t) }, icone("x"), T.treino.cancelar));
  if (t.etapa === "pronto" && estado.ativo !== t.id) acoes.push(el("button", { class: "btn btn-sm btn-primaria", type: "button", onclick: (ev) => usarModelo(t.id, t.nome, ev.currentTarget) }, T.treino.usar));
  if (final && t.etapa !== "pronto") acoes.push(el("button", { class: "btn btn-sm btn-fantasma", type: "button", onclick: (ev) => mostrarRegistro(t, ev.currentTarget) }, T.treino.verRegistro));
  if (acoes.length) corpo.push(el("div", { class: "acoes" }, acoes));
  return el("div", { class: "cartao treino pilha" }, corpo);
}

function metricasTreino(t) {
  const m = t.metricas;
  const M = T.treino.metricas;
  const item = (rotulo, valor) => el("div", {}, el("dt", {}, rotulo), el("dd", { class: "num" }, valor));
  const classes = Object.entries(m.por_classe || {});
  return el("div", { class: "resultado-treino" },
    el("div", { class: "pilha" },
      el("dl", { class: "metricas-treino" },
        item(M.mAP50, m.mAP50 != null ? fmt(m.mAP50 * 100, 0, "%") : T.geral.semValor),
        item(M.revocacao, m.revocacao != null ? fmt(m.revocacao * 100, 0, "%") : T.geral.semValor),
        item(M.erro, fmt(m.erro_tmax_mediano_c, 2, " °C")),
        item(M.erro90, fmt(m.erro_tmax_p90_c, 2, " °C"))),
      classes.length ? el("table", { class: "tabela" },
        el("thead", {}, el("tr", {}, T.treino.porClasse.map((c, i) => el("th", { class: i ? "direita" : null }, c)))),
        el("tbody", {}, classes.map(([nome, c]) => el("tr", {}, el("td", {}, nome),
          el("td", { class: "num direita" }, c.AP50 != null ? fmt(c.AP50 * 100, 0, "%") : T.geral.semValor),
          el("td", { class: "num direita" }, c.revocacao_no_limiar != null ? fmt(c.revocacao_no_limiar * 100, 0, "%") : T.geral.semValor))))) : null),
    el("figure", { class: "figura-treino" },
      el("a", { href: `/api/treinos/${t.id}/previsoes.png`, target: "_blank" }, el("img", { src: `/api/treinos/${t.id}/previsoes.png`, alt: T.treino.previsoes, loading: "lazy" })),
      el("figcaption", { class: "nota" }, T.treino.previsoes)));
}

async function usarModelo(id, nome, botao) {
  ocupado(botao, true);
  try {
    await api("/api/modelos/ativo", json("PUT", { id }));
    avisar(T.modelos.passaASer(nome));
    carregarModelos();
  } catch (e) {
    falhou(e);
  } finally {
    ocupado(botao, false);
  }
}

async function cancelarTreino(t) {
  if (!(await confirmar(T.treino.cancelarTitulo, T.treino.cancelarTexto, T.treino.cancelar, true))) return;
  try {
    await api(`/api/treinos/${t.id}/cancelar`, { method: "POST" });
    avisar(T.treino.cancelado);
    carregarTreinos();
    atualizarStatus();
  } catch (e) {
    falhou(e);
  }
}

async function mostrarRegistro(t, botao) {
  ocupado(botao, true);
  try {
    const d = await api(`/api/treinos/${t.id}`);
    await dialogo({ titulo: `${T.treino.verRegistro}: ${t.nome}`, conteudo: el("pre", { class: "registro" }, d.registro || T.geral.semValor), acoes: [{ rotulo: T.geral.fechar, valor: "fechar" }] });
  } catch (e) {
    falhou(e);
  } finally {
    ocupado(botao, false);
  }
}

async function instalarModelo(arquivo) {
  const dados = new FormData();
  dados.append("arquivo", arquivo);
  try {
    const r = await api("/api/modelos/instalar", { method: "POST", body: dados });
    avisar(T.modelos.instalado(r.id));
    carregarModelos();
  } catch (e) {
    falhou(e);
  }
}

// ================================================================= avaliação de modelos (resultados do Colab)

const SVG_NS = "http://www.w3.org/2000/svg";
const corSerie = (i) => `var(--serie-${(i % 4) + 1})`;
const num2 = (v) => fmt(v, 2);

function svgEl(tag, props = {}, ...filhos) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(props)) if (v != null) n.setAttribute(k, v);
  for (const f of filhos.flat()) if (f != null && f !== false) n.append(f instanceof Node ? f : document.createTextNode(String(f)));
  return n;
}

function legendaGrafico(itens) {
  return el("ul", { class: "legenda-grafico" }, itens.map(({ nome, indice, tracejado }) =>
    el("li", {}, amostraSerie(indice, tracejado), nome)));
}

/** Quadradinho (ou traço) da cor da série, para legendas e tabelas. */
function amostraSerie(indice, tracejado = false) {
  return el("span", { class: `amostra${tracejado ? " tracejada" : ""}`, style: tracejado ? { borderTopColor: corSerie(indice) } : { background: corSerie(indice) } });
}

/** Barras agrupadas: uma cor por série (modelo), um grupo por categoria (métrica). Valores de 0 a 1. */
function graficoBarras(categorias, series) {
  const L = 900, A = 250, m = { e: 40, d: 8, t: 20, b: 30 };
  const w = L - m.e - m.d, h = A - m.t - m.b;
  const grupo = w / categorias.length;
  const larg = Math.min(34, (grupo * 0.8) / series.length);
  const y = (v) => m.t + h - Math.max(0, Math.min(v ?? 0, 1)) * h;
  const svg = svgEl("svg", { viewBox: `0 0 ${L} ${A}`, class: "grafico-svg", role: "img", "aria-label": categorias.join(", ") });
  for (const t of [0, 0.25, 0.5, 0.75, 1]) {
    svg.append(svgEl("line", { x1: m.e, x2: L - m.d, y1: y(t), y2: y(t), class: "grade" }),
      svgEl("text", { x: m.e - 6, y: y(t) + 4, class: "eixo", "text-anchor": "end" }, fmt(t, 2)));
  }
  categorias.forEach((c, i) => {
    const x0 = m.e + i * grupo + (grupo - larg * series.length) / 2;
    series.forEach((s, j) => {
      const v = s.valores[i];
      const x = x0 + j * larg;
      svg.append(svgEl("rect", { x, y: y(v), width: larg - 4, height: m.t + h - y(v), rx: 3, style: `fill: ${corSerie(s.indice)}` },
        svgEl("title", {}, `${s.nome} · ${c}: ${num2(v)}`)));
      if (v != null) svg.append(svgEl("text", { x: x + (larg - 4) / 2, y: y(v) - 5, class: "valor", "text-anchor": "middle" }, num2(v)));
    });
    svg.append(svgEl("text", { x: m.e + i * grupo + grupo / 2, y: A - 8, class: "eixo rotulo", "text-anchor": "middle" }, c));
  });
  return el("figure", { class: "grafico" }, svg, legendaGrafico(series));
}

/** Linhas por época. series: [{nome, indice, pontos: [[x, y]], tracejado}]; marcas: [{x, indice}] (melhor época). */
function graficoLinhas(titulo, series, { yMax = null, marcas = [] } = {}) {
  const pontos = series.flatMap((s) => s.pontos).filter(([x, v]) => Number.isFinite(x) && Number.isFinite(v));
  if (!pontos.length) return null;
  const L = 380, A = 230, m = { e: 44, d: 10, t: 12, b: 32 };
  const xs = pontos.map((p) => p[0]);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const topo = yMax ?? Math.max(...pontos.map((p) => p[1])) * 1.08;
  const x = (v) => m.e + ((v - xMin) / Math.max(xMax - xMin, 1)) * (L - m.e - m.d);
  const y = (v) => m.t + (1 - v / (topo || 1)) * (A - m.t - m.b);
  const svg = svgEl("svg", { viewBox: `0 0 ${L} ${A}`, class: "grafico-svg", role: "img", "aria-label": titulo });
  for (const t of [0, 0.5, 1]) {
    svg.append(svgEl("line", { x1: m.e, x2: L - m.d, y1: y(t * topo), y2: y(t * topo), class: "grade" }),
      svgEl("text", { x: m.e - 6, y: y(t * topo) + 4, class: "eixo", "text-anchor": "end" }, fmt(t * topo, topo < 3 ? 2 : 1)));
  }
  for (const v of [...new Set([xMin, Math.round((xMin + xMax) / 2), xMax])]) {
    svg.append(svgEl("text", { x: x(v), y: A - 12, class: "eixo", "text-anchor": "middle" }, String(v)));
  }
  svg.append(svgEl("text", { x: L - m.d, y: A - 1, class: "eixo", "text-anchor": "end" }, T.avaliacao.epoca));
  for (const mc of marcas) {
    if (Number.isFinite(mc.x)) svg.append(svgEl("line", { x1: x(mc.x), x2: x(mc.x), y1: m.t, y2: A - m.b, class: "marca-epoca", style: `stroke: ${corSerie(mc.indice)}` }));
  }
  for (const s of series) {
    const validos = s.pontos.filter(([a, b]) => Number.isFinite(a) && Number.isFinite(b));
    if (!validos.length) continue;
    const d = validos.map(([a, b], i) => `${i ? "L" : "M"}${x(a).toFixed(1)} ${y(b).toFixed(1)}`).join(" ");
    svg.append(svgEl("path", { d, class: `linha${s.tracejado ? " tracejada" : ""}`, style: `stroke: ${corSerie(s.indice)}` }, svgEl("title", {}, s.nome)));
  }
  return el("figure", { class: "grafico" }, el("figcaption", {}, titulo), svg, legendaGrafico(series));
}

/** Cor da célula: AP50 e revocação são bons a partir de 0,90; o AP50-95 (caixa justa) é naturalmente mais baixo. */
const FAIXAS_METRICA = { AP50: [0.9, 0.75], revocacao: [0.9, 0.75], "AP50-95": [0.6, 0.4] };
function nivelValor(v, metrica = "AP50") {
  if (v == null) return "";
  const [bom, medio] = FAIXAS_METRICA[metrica] || FAIXAS_METRICA.AP50;
  return v >= bom ? "bom" : v >= medio ? "medio" : "fraco";
}

async function carregarAvaliacoes() {
  const alvo = $("#conteudo-avaliacao");
  const sel = $("#sel-avaliacao");
  alvo.replaceChildren(esqueleto.kpis(4), esqueleto.bloco(), esqueleto.tabela(4));
  let lista;
  try {
    lista = await api("/api/avaliacoes");
  } catch (e) {
    return alvo.replaceChildren(estadoErro(T.avaliacao.erroTitulo, e, carregarAvaliacoes));
  }
  sel.hidden = lista.length < 2;
  sel.replaceChildren(...lista.map((m) => new Option(T.avaliacao.opcao(m), m.id)));
  if (!lista.length) {
    estado.avaliacaoId = null;
    return alvo.replaceChildren(estadoVazio({
      nomeIcone: "grafico", titulo: T.avaliacao.vazioTitulo, texto: T.avaliacao.vazioTexto,
      acoes: [el("button", { class: "btn btn-primaria", type: "button", onclick: () => $("#arquivo-avaliacao").click() }, icone("upload"), T.avaliacao.importar)],
    }));
  }
  if (!lista.some((m) => m.id === estado.avaliacaoId)) estado.avaliacaoId = lista[0].id;
  sel.value = estado.avaliacaoId;
  await carregarAvaliacao(estado.avaliacaoId);
}

async function carregarAvaliacao(id) {
  estado.avaliacaoId = id;
  const alvo = $("#conteudo-avaliacao");
  alvo.replaceChildren(esqueleto.kpis(4), esqueleto.bloco());
  try {
    desenharAvaliacao(await api(`/api/avaliacoes/${id}`));
  } catch (e) {
    alvo.replaceChildren(estadoErro(T.avaliacao.erroTitulo, e, () => carregarAvaliacao(id)));
  }
}

async function importarAvaliacao(arquivo) {
  if (estado.vista !== "avaliacao") location.hash = "avaliacao";
  $("#conteudo-avaliacao").replaceChildren(el("p", { class: "nota" }, T.avaliacao.importando), esqueleto.kpis(4), esqueleto.bloco());
  const dados = new FormData();
  dados.append("arquivo", arquivo);
  try {
    const r = await api("/api/avaliacoes", { method: "POST", body: dados });
    const partes = [];
    if (r.avaliacao) partes.push(T.avaliacao.parteAvaliacao);
    if (r.modelo) partes.push(T.avaliacao.parteModelo(r.modelo));
    if (partes.length) avisar(T.avaliacao.importou(partes));
    for (const aviso of r.avisos || []) avisar(aviso, { erro: true });
    if (r.avaliacao) estado.avaliacaoId = r.avaliacao;
    if (r.modelo) carregarListaModelos().catch(() => {});
  } catch (e) {
    falhou(e);
  }
  carregarAvaliacoes();
}

function desenharAvaliacao(d) {
  const r = d.resumo;
  const modelos = Object.keys(r.teste);
  const cartoes = [
    resumoAvaliacao(r, modelos),
    cartaoComparacao(r, modelos),
    cartaoPorClasse(r, modelos),
    cartaoCurvas(r, modelos),
    cartaoPecasPerdidas(d.tabelas || {}),
    cartaoFiguras(d.meta),
    cartaoDadosAvaliacao(d),
  ].filter(Boolean);
  $("#conteudo-avaliacao").replaceChildren(...animarEntrada(cartoes));
}

function resumoAvaliacao(r, modelos) {
  const A = T.avaliacao;
  const t = r.teste;
  const melhor = modelos.reduce((a, b) => ((t[b].mAP50 ?? 0) > (t[a].mAP50 ?? 0) ? b : a));
  const menosPerdas = modelos.reduce((a, b) => ((t[b].perdidos ?? Infinity) < (t[a].perdidos ?? Infinity) ? b : a));
  const total = (m) => (t[m].acertos ?? 0) + (t[m].perdidos ?? 0);
  const f = r.fotos || {};
  const qtd = (v) => (Array.isArray(v) ? v.length : v);
  const kpi = (rotulo, valor, nota, titulo) => el("div", { class: "kpi-grande", title: titulo }, el("span", {}, rotulo), el("b", {}, valor), el("small", {}, nota));
  const tm = t[melhor];
  return el("div", { class: "kpis-grandes" },
    kpi(A.melhor, melhor, A.melhorNota(num2(tm.mAP50))),
    kpi(A.revocacao, tm.revocacao != null ? fmt(tm.revocacao * 100, 0, "%") : T.geral.semValor, A.revocacaoNota(tm.acertos ?? 0, total(melhor))),
    kpi(A.perdidas, String(t[menosPerdas].perdidos ?? T.geral.semValor), A.perdidasNota(menosPerdas)),
    tm.erro_Tmax_mediano_C != null ? kpi(A.tmax, fmt(tm.erro_Tmax_mediano_C, 2, " °C"), A.tmaxNota(fmt(tm.erro_Tmax_p90_C, 2), tm.pecas_medidas ?? "–"), A.tmaxExplica) : null,
    kpi(A.fotos, A.fotosTeste(qtd(f.teste) ?? T.geral.semValor), A.fotosNota(qtd(f.treino) ?? T.geral.semValor, qtd(f.validacao) ?? T.geral.semValor)));
}

/** Leitura automática: empate técnico ou vantagem entre os dois primeiros, e a peça mais difícil para todos. */
function conclusoesAvaliacao(r, modelos) {
  const A = T.avaliacao;
  const t = r.teste;
  const frases = [];
  const ordem = [...modelos].sort((a, b) => (t[b].acertos ?? 0) - (t[a].acertos ?? 0));
  if (ordem.length > 1) {
    const [a, b] = ordem;
    const dif = (t[a].acertos ?? 0) - (t[b].acertos ?? 0);
    const total = (t[a].acertos ?? 0) + (t[a].perdidos ?? 0);
    frases.push(dif <= Math.max(2, Math.round(total * 0.02)) ? A.empate(a, b, dif) : A.vantagem(a, b, dif));
  }
  const classes = [...new Set(modelos.flatMap((m) => Object.keys(t[m].por_classe || {})))];
  const medias = classes.map((c) => {
    const v = modelos.map((m) => t[m].por_classe?.[c]?.AP50).filter((x) => x != null);
    return [c, v.length ? v.reduce((s, x) => s + x, 0) / v.length : null];
  }).filter(([, v]) => v != null).sort((p, q) => p[1] - q[1]);
  if (medias.length && medias[0][1] < 0.85) frases.push(A.pontoFraco(medias[0][0], num2(medias[0][1])));
  return frases;
}

function cartaoComparacao(r, modelos) {
  const A = T.avaliacao;
  const t = r.teste;
  const chaves = ["mAP50", "mAP50-95", "precisao", "revocacao", "F1"];
  const grafico = graficoBarras(A.metricas, modelos.map((m, i) => ({ nome: m, indice: i, valores: chaves.map((k) => t[m][k]) })));
  const colunas = [
    ["mAP50", "maior", num2], ["mAP50-95", "maior", num2], ["precisao", "maior", num2], ["revocacao", "maior", num2], ["F1", "maior", num2],
    ["IoU_medio_acertos", "maior", num2], ["acertos", "maior", String], ["falsos", "menor", String], ["perdidos", "menor", String],
  ];
  const temTemperatura = modelos.some((m) => t[m].erro_Tmax_mediano_C != null);
  if (temTemperatura) colunas.push(["erro_Tmax_mediano_C", "menor", num2], ["erro_Tmax_p90_C", "menor", num2]);
  const cabecalhos = [...A.colunas.slice(0, 10), ...(temTemperatura ? A.colunasTemperatura : []), ...A.colunas.slice(10)];
  const extremo = (k, sentido) => {
    const v = modelos.map((m) => t[m][k]).filter((x) => x != null);
    return v.length ? (sentido === "maior" ? Math.max(...v) : Math.min(...v)) : null;
  };
  const melhores = Object.fromEntries(colunas.map(([k, s]) => [k, extremo(k, s)]));
  const limiar = (m) => r.limiares?.[m] ?? r.configuracao?.limiar ?? r.configuracao?.limiar_padrao;
  const tabela = el("div", { class: "tabela-rolagem" }, el("table", { class: "tabela tabela-avaliacao" },
    el("thead", {}, el("tr", {}, cabecalhos.map((c, i) => el("th", { class: i ? "direita" : null }, c)))),
    el("tbody", {}, modelos.map((m, i) => el("tr", {},
      el("td", {}, amostraSerie(i), m),
      colunas.map(([k, , f]) => el("td", { class: `num direita${t[m][k] != null && t[m][k] === melhores[k] ? " destaque" : ""}` }, t[m][k] != null ? f(t[m][k]) : T.geral.semValor)),
      el("td", { class: "num direita" }, limiar(m) != null ? num2(limiar(m)) : T.geral.semValor),
      el("td", { class: "num direita" }, r.ms_por_foto?.[m] != null ? fmt(r.ms_por_foto[m], 0) : T.geral.semValor))))));
  const frases = conclusoesAvaliacao(r, modelos);
  return el("section", { class: "cartao" },
    el("div", { class: "cartao-cabeca" }, el("div", {}, el("h2", {}, A.comparacao), el("p", { class: "nota" }, A.comparacaoNota))),
    frases.length ? el("div", { class: "conclusao" }, icone("info"), el("div", {}, frases.map((f) => el("p", {}, f)))) : null,
    grafico, tabela);
}

function cartaoPorClasse(r, modelos) {
  const A = T.avaliacao;
  const t = r.teste;
  const classes = [...new Set([...(r.classes || []), ...modelos.flatMap((m) => Object.keys(t[m].por_classe || {}))])]
    .filter((c) => modelos.some((m) => t[m].por_classe?.[c]));
  if (!classes.length) return null;
  const chaves = ["AP50", "AP50-95", "revocacao"];
  const celula = (v, k) => el("td", { class: `num direita mapa ${nivelValor(v, k)}` }, v != null ? num2(v) : T.geral.semValor);
  const grafico = graficoBarras(classes, modelos.map((m, i) => ({ nome: m, indice: i, valores: classes.map((c) => t[m].por_classe?.[c]?.AP50) })));
  return el("section", { class: "cartao" },
    el("div", { class: "cartao-cabeca" }, el("div", {}, el("h2", {}, A.porClasse), el("p", { class: "nota" }, A.porClasseNota))),
    grafico,
    el("div", { class: "tabela-rolagem" }, el("table", { class: "tabela tabela-avaliacao" },
      el("thead", {},
        el("tr", {}, el("th", { rowspan: 2 }, A.componente), modelos.map((m, i) => el("th", { colspan: 3, class: "centro" }, amostraSerie(i), m))),
        el("tr", {}, modelos.flatMap(() => A.colunasClasse.map((c) => el("th", { class: "direita" }, c))))),
      el("tbody", {}, classes.map((c) => el("tr", {}, el("td", {}, c), modelos.flatMap((m) => chaves.map((k) => celula(t[m].por_classe?.[c]?.[k], k)))))))));
}

function cartaoCurvas(r, modelos) {
  const A = T.avaliacao;
  const hist = r.historico || {};
  const comHistorico = modelos.filter((m) => hist[m] && (hist[m].perda_treino || []).length);
  const graficos = comHistorico.map((m) => {
    const h = hist[m];
    const i = modelos.indexOf(m);
    const ep = h.epocas_perda || h.perda_treino.map((_, k) => k + 1);
    return graficoLinhas(A.perda(m), [
      { nome: A.treino, indice: i, pontos: ep.map((e, k) => [e, h.perda_treino[k]]) },
      { nome: A.validacao, indice: i, tracejado: true, pontos: ep.map((e, k) => [e, (h.perda_validacao || [])[k]]) },
    ], { marcas: h.melhor_epoca ? [{ x: h.melhor_epoca, indice: i }] : [] });
  });
  const mapa = graficoLinhas(A.mapaValidacao,
    comHistorico.map((m) => ({ nome: m, indice: modelos.indexOf(m), pontos: (hist[m].epocas_map || []).map((e, k) => [e, hist[m].map50_validacao[k]]) })),
    { yMax: 1, marcas: comHistorico.filter((m) => hist[m].melhor_epoca).map((m) => ({ x: hist[m].melhor_epoca, indice: modelos.indexOf(m) })) });
  const todos = [...graficos, mapa].filter(Boolean);
  return el("section", { class: "cartao" },
    el("div", { class: "cartao-cabeca" }, el("div", {}, el("h2", {}, A.curvas), el("p", { class: "nota" }, A.curvasNota))),
    todos.length ? el("div", { class: "grade-graficos" }, todos) : el("p", { class: "nota" }, A.semCurvas));
}

function tabelaCsv(t) {
  const formatar = (v) => (typeof v === "number" ? (Number.isInteger(v) ? String(v) : num2(v)) : v);
  return el("div", { class: "tabela-rolagem" }, el("table", { class: "tabela" },
    el("thead", {}, el("tr", {}, t.colunas.map((c, i) => el("th", { class: i ? "direita" : null }, c)))),
    el("tbody", {}, t.linhas.map((l) => el("tr", {}, l.map((v, i) => el("td", { class: i ? "num direita" : null }, formatar(v))))))));
}

function cartaoPecasPerdidas(tabelas) {
  const A = T.avaliacao;
  const partes = ["pecas_perdidas_por_tipo.csv", "efeito_do_limiar.csv"].filter((n) => tabelas[n] && tabelas[n].linhas.length);
  if (!partes.length) return null;
  return el("section", { class: "cartao" },
    el("div", { class: "cartao-cabeca" }, el("div", {}, el("h2", {}, A.pecasPerdidas), el("p", { class: "nota" }, A.pecasPerdidasNota))),
    el("div", { class: "grade-tabelas" }, partes.map((n) => tabelaCsv(tabelas[n]))));
}

function cartaoFiguras(meta) {
  const A = T.avaliacao;
  const figuras = meta.figuras || [];
  if (!figuras.length) return null;
  const ordem = (n) => (n.startsWith("teste_") ? 0 : n === "piores_fotos.png" ? 1 : n === "pecas_perdidas.png" ? 2 : 3);
  const lista = [...figuras].sort((a, b) => ordem(a) - ordem(b) || a.localeCompare(b));
  return el("section", { class: "cartao" },
    el("div", { class: "cartao-cabeca" }, el("div", {}, el("h2", {}, A.figuras), el("p", { class: "nota" }, A.figurasNota))),
    el("div", { class: "galeria" }, lista.map((n) => {
      const src = `/api/avaliacoes/${meta.id}/arquivos/${encodeURIComponent(n)}`;
      const titulo = A.figura[n] || A.figuraTeste(n);
      return el("figure", { class: "figura-avaliacao" },
        el("a", { href: src, target: "_blank", rel: "noopener" }, el("img", { src, alt: titulo, loading: "lazy" })),
        el("figcaption", { class: "nota" }, titulo));
    })));
}

function cartaoDadosAvaliacao(d) {
  const A = T.avaliacao;
  const { meta, resumo: r } = d;
  const L = A.linhasDados;
  const linhas = [
    [L.importado, dataHora(meta.importado_em)],
    [L.arquivo, meta.arquivo],
    [L.gpu, r.gpu],
    [L.divisao, A.divisao(meta.fotos || {})],
    [L.classes, (r.classes || []).join(" · ")],
    [L.formato, r.formato_anotacoes],
    [L.limiares, r.limiares ? Object.entries(r.limiares).map(([m, v]) => `${m} ${num2(v)}`).join(" · ") : null],
  ].filter(([, v]) => v);
  const blocoModelo = meta.modelo_instalado && d.modelo_disponivel
    ? el("div", { class: "modelo-da-avaliacao" },
        el("div", {}, el("b", {}, A.modeloInstalado), el("p", { class: "nota" }, `${meta.modelo_instalado} · ${A.modeloInstaladoNota}`)),
        d.modelo_ativo === meta.modelo_instalado
          ? el("span", { class: "em-uso" }, icone("check"), A.emUso)
          : el("button", {
              class: "btn btn-primaria", type: "button",
              onclick: async (ev) => {
                ocupado(ev.currentTarget, true);
                try {
                  await api("/api/modelos/ativo", json("PUT", { id: meta.modelo_instalado }));
                  avisar(T.modelos.passaASer(meta.modelo_instalado));
                  await carregarListaModelos();
                  carregarAvaliacao(meta.id);
                } catch (e) {
                  ocupado(ev.currentTarget, false);
                  falhou(e);
                }
              },
            }, icone("check"), A.usarModelo))
    : null;
  const apagar = el("button", {
    class: "btn btn-fantasma btn-perigo", type: "button",
    onclick: async () => {
      if (!(await confirmar(A.apagarTitulo, A.apagarTexto, T.geral.apagar, true))) return;
      try {
        await api(`/api/avaliacoes/${meta.id}`, { method: "DELETE" });
        avisar(A.apagada);
        estado.avaliacaoId = null;
        carregarAvaliacoes();
      } catch (e) {
        falhou(e);
      }
    },
  }, icone("lixo"), A.apagar);
  return el("section", { class: "cartao" },
    el("div", { class: "cartao-cabeca" }, el("h2", {}, A.dados)),
    blocoModelo,
    el("dl", { class: "dados-avaliacao" }, linhas.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)])),
    el("div", { class: "cartao-rodape" }, apagar));
}

// ================================================================= busca rápida (Ctrl+K) e atalhos (?)

const normalizar = (t) => String(t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** Tudo o que dá para achar: telas, ações, equipamentos e inspeções. */
function itensDaBusca() {
  const B = T.busca;
  const telas = Object.entries(B.telas).map(([rota, [nome, icone_]]) => ({ tipo: B.grupoTelas, rotulo: nome, icone: icone_, executar: () => { location.hash = rota; } }));
  const acoes = [
    { rotulo: B.acaoAnalisar, icone: "upload", executar: abrirArquivos },
    { rotulo: B.acaoVideo, icone: "video", executar: () => { location.hash = "video"; } },
    { rotulo: B.acaoPlanilha, icone: "baixar", executar: () => { const a = el("a", { href: "/api/inspecoes.csv", download: "" }); document.body.append(a); a.click(); a.remove(); } },
    { rotulo: B.acaoTema, icone: "config", executar: () => { const novo = document.documentElement.dataset.tema === "escuro" ? "claro" : "escuro"; aplicarTema(novo); salvarConfig({ tema: novo }); } },
    { rotulo: B.acaoAtalhos, icone: "info", executar: mostrarAtalhos },
  ].map((a) => ({ ...a, tipo: B.grupoAcoes }));
  const equips = (estado.equipamentos || []).filter((e) => e.chave !== SEM_EQUIPAMENTO).map((e) => ({
    tipo: B.grupoEquipamentos, rotulo: e.equipamento, detalhe: e.instalacao, icone: "ativos", severidade: e.severidade,
    executar: () => { location.hash = `equipamentos/${encodeURIComponent(e.chave)}`; },
  }));
  const inspecoes = (estado.inspecoes || []).map((it) => ({
    tipo: B.grupoInspecoes, rotulo: it.arquivo, icone: "inspecoes", severidade: it.resumo.severidade,
    detalhe: [it.identificacao.equipamento, it.identificacao.instalacao, dataCurta(it.data_captura || it.criado_em)].filter(Boolean).join(" · "),
    executar: () => abrirInspecao(it.id),
  }));
  return [...telas, ...acoes, ...equips, ...inspecoes];
}

const busca = { itens: [], achados: [], atual: 0 };

function abrirBusca() {
  const d = $("#paleta");
  if (d.open) return;
  busca.itens = itensDaBusca();
  $("#paleta-texto").value = "";
  filtrarBusca();
  d.showModal();
  $("#paleta-texto").focus();
  // Inspeções e equipamentos podem não estar carregados ainda: chegam e entram na lista.
  if (!estado.inspecoes.length || !estado.equipamentos) {
    Promise.all([api("/api/analises"), api("/api/equipamentos")]).then(([l, e]) => {
      estado.inspecoes = l;
      estado.equipamentos = e;
      if (d.open) { busca.itens = itensDaBusca(); filtrarBusca(); }
    }).catch(() => {});
  }
}

function filtrarBusca() {
  const termos = normalizar($("#paleta-texto").value).split(/\s+/).filter(Boolean);
  busca.achados = busca.itens.filter((it) => {
    if (!termos.length) return it.tipo !== T.busca.grupoInspecoes; // sem texto: telas, ações e equipamentos
    const texto = normalizar(`${it.rotulo} ${it.detalhe || ""} ${it.tipo} ${it.severidade ? T.niveis[it.severidade] : ""}`);
    return termos.every((t) => texto.includes(t));
  }).slice(0, 40);
  busca.atual = 0;
  desenharBusca();
}

function desenharBusca() {
  const lista = $("#paleta-lista");
  if (!busca.achados.length) return lista.replaceChildren(el("li", { class: "paleta-vazio" }, T.busca.nada));
  let grupo = null;
  const nos = [];
  busca.achados.forEach((it, i) => {
    if (it.tipo !== grupo) {
      grupo = it.tipo;
      nos.push(el("li", { class: "paleta-grupo", role: "presentation" }, grupo));
    }
    nos.push(el("li", {
      class: `paleta-item${i === busca.atual ? " atual" : ""}`, role: "option", "aria-selected": String(i === busca.atual),
      onmousemove: () => { if (busca.atual !== i) { busca.atual = i; marcarAtualBusca(); } },
      onclick: () => executarBusca(i),
    }, icone(it.icone), el("span", { class: "paleta-texto" }, el("b", {}, it.rotulo), it.detalhe ? el("small", {}, it.detalhe) : null),
    it.severidade ? el("span", { class: `selo ${it.severidade}` }, T.niveis[it.severidade]) : null));
  });
  lista.replaceChildren(...nos);
}

function marcarAtualBusca() {
  $$("#paleta-lista .paleta-item").forEach((n, i) => {
    n.classList.toggle("atual", i === busca.atual);
    n.setAttribute("aria-selected", String(i === busca.atual));
  });
  const atual = $("#paleta-lista .paleta-item.atual");
  if (atual) atual.scrollIntoView({ block: "nearest" });
}

function executarBusca(i) {
  const it = busca.achados[i];
  $("#paleta").close();
  if (it) it.executar();
}

function teclaBusca(ev) {
  if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
    ev.preventDefault();
    const n = busca.achados.length;
    if (!n) return;
    busca.atual = (busca.atual + (ev.key === "ArrowDown" ? 1 : -1) + n) % n;
    marcarAtualBusca();
  } else if (ev.key === "Enter") {
    ev.preventDefault();
    executarBusca(busca.atual);
  }
}

function mostrarAtalhos() {
  const A = T.atalhos;
  const tecla = (t) => t.split("+").map((k, i) => [i ? "+" : null, el("kbd", {}, k)]).flat().filter(Boolean);
  const bloco = ([titulo, linhas]) => el("div", { class: "bloco-atalhos" }, el("h3", { class: "sobrerrotulo" }, titulo),
    el("dl", {}, linhas.map(([t, d]) => el("div", {}, el("dt", {}, tecla(t)), el("dd", {}, d)))));
  dialogo({ titulo: A.titulo, conteudo: el("div", { class: "atalhos" }, A.grupos.map(bloco)), acoes: [{ rotulo: T.geral.fechar, valor: "ok", classe: "btn-primaria" }] });
}

// ================================================================= pendências (acompanhamento das anomalias até a correção)

const FILTROS_PENDENCIA = {
  andamento: (p) => ["aberta", "programada", "corrigida"].includes(p.status),
  vencidas: (p) => p.vencida,
  reinspecao: (p) => p.status === "corrigida" || (p.reinspecao && p.status !== "verificada" && p.status !== "descartada"),
  concluidas: (p) => p.status === "verificada" || p.status === "descartada",
  todas: () => true,
};

function seloStatus(status) {
  return el("span", { class: `status-pendencia ${status}` }, T.pend.status[status] || status);
}

function textoPrazo(p) {
  const P = T.pend;
  if (p.status === "verificada" || p.status === "descartada") return el("span", { class: "nota" }, dataCurta(p.prazo));
  return el("span", { class: `prazo${p.vencida ? " vencido" : p.dias <= 7 ? " perto" : ""}` }, icone("calendario"),
    dataCurta(p.prazo), el("small", {}, p.vencida ? P.vencidaHa(-p.dias) : P.faltam(p.dias)));
}

async function carregarPendencias() {
  const alvo = $("#lista-pendencias");
  $("#kpis-pendencias").replaceChildren(...esqueleto.kpis(4).children);
  if (!estado.pendencias) alvo.replaceChildren(esqueleto.tabela(5));
  try {
    estado.pendencias = await api("/api/pendencias");
  } catch (e) {
    $("#kpis-pendencias").replaceChildren();
    return alvo.replaceChildren(estadoErro(T.pend.erroTitulo, e, carregarPendencias));
  }
  atualizarContadorPendencias();
  desenharPendencias();
}

function atualizarContadorPendencias() {
  const n = (estado.pendencias || []).filter((p) => p.vencida).length;
  const c = $("#contador-pendencias");
  c.hidden = !n;
  c.textContent = String(n);
}

function desenharPendencias() {
  const P = T.pend;
  const todas = estado.pendencias || [];
  const alvo = $("#lista-pendencias");
  const filtro = estado.filtroPendencia || "andamento";
  $("#filtros-pendencias").hidden = !todas.length;
  $("#kpis-pendencias").hidden = !todas.length;
  if (!todas.length) {
    $("#kpis-pendencias").replaceChildren();
    return alvo.replaceChildren(estadoVazio({ nomeIcone: "check", titulo: P.vazioTitulo, texto: P.vazioTexto }));
  }
  const kpi = (rotulo, chave, cor) => el("button", {
    class: "kpi-grande", type: "button", "aria-pressed": String(filtro === chave),
    onclick: () => { estado.filtroPendencia = chave; marcarSegmentado("#seg-pendencias", chave); desenharPendencias(); },
  }, el("span", {}, cor ? el("i", { class: "ponto", style: { background: `var(--${cor})`, boxShadow: "none" } }) : null, rotulo),
  el("b", {}, String(todas.filter(FILTROS_PENDENCIA[chave]).length)));
  $("#kpis-pendencias").replaceChildren(
    kpi(P.kAndamento, "andamento", "programar"),
    kpi(P.kVencidas, "vencidas", "imediato"),
    kpi(P.kReinspecao, "reinspecao", "info"),
    kpi(P.kConcluidas, "concluidas", "normal"));
  marcarSegmentado("#seg-pendencias", filtro);

  const termo = (estado.buscaPendencia || "").trim().toLowerCase();
  const itens = todas.filter(FILTROS_PENDENCIA[filtro]).filter((p) => !termo ||
    [p.equipamento, p.instalacao, p.regiao, p.arquivo, p.ordem_servico, p.responsavel].filter(Boolean).join(" ").toLowerCase().includes(termo));
  if (!itens.length) {
    return alvo.replaceChildren(estadoVazio({ nomeIcone: "busca", titulo: P.nadaTitulo, texto: P.nadaTexto, compacto: true }));
  }
  const linhas = itens.map((p) => el("tr", { class: `clicavel${p.vencida ? " linha-vencida" : ""}`, tabindex: "0", onclick: () => atualizarPendencia(p), onkeydown: (ev) => { if (ev.key === "Enter") atualizarPendencia(p); } },
    el("td", {}, el("span", { class: `selo ${p.severidade}` }, T.niveis[p.severidade])),
    el("td", {}, el("div", { class: "principal-celula" },
      el("b", {}, p.equipamento || p.arquivo),
      el("span", { class: "nota" }, [p.instalacao, p.regiao && `${p.regiao} · ${fmt(p.t_max, 1, " °C")}`].filter(Boolean).join(" · ")))),
    el("td", { class: "num" }, dataCurta(p.detectada_em)),
    el("td", {}, textoPrazo(p)),
    el("td", {}, seloStatus(p.status), p.reinspecao && !["verificada", "descartada"].includes(p.status)
      ? el("small", { class: "dica-reinspecao" }, icone("check"), P.reinspecaoNormal(dataCurta(p.reinspecao.data))) : null),
    el("td", {}, p.ordem_servico || el("span", { class: "nota" }, T.geral.semValor)),
    el("td", { class: "celula-acoes" },
      el("a", { class: "btn btn-sm btn-fantasma", href: `#analise/${p.id}`, onclick: (ev) => ev.stopPropagation(), title: P.abrirInspecao }, icone("analise"), P.ver),
      el("button", { class: "btn btn-sm", type: "button", onclick: (ev) => { ev.stopPropagation(); atualizarPendencia(p); } }, icone("editar"), P.atualizar))));
  alvo.replaceChildren(el("div", { class: "cartao cartao-tabela" }, el("div", { class: "tabela-rolagem" }, el("table", { class: "tabela" },
    el("thead", {}, el("tr", {}, [P.colSeveridade, P.colEquipamento, P.colDetectada, P.colPrazo, P.colSituacao, P.colOs, ""].map((t) => el("th", {}, t)))),
    el("tbody", {}, animarEntrada(linhas))))));
}

/** Diálogo único de atualização: situação, prazo, OS, responsável, nota e o histórico. */
async function atualizarPendencia(p, aoSalvar) {
  const P = T.pend;
  const status = el("select", {}, Object.entries(P.status).map(([v, t]) => new Option(t, v)));
  status.value = p.status;
  const prazo = el("input", { type: "date", value: p.prazo });
  const os = el("input", { value: p.ordem_servico || "", placeholder: P.osExemplo, autocomplete: "off" });
  const resp = el("input", { value: p.responsavel || "", placeholder: P.responsavelExemplo, autocomplete: "off" });
  const nota = el("textarea", { rows: 2, placeholder: P.notaExemplo });
  const historico = (p.historico || []).slice().reverse();
  const escolha = await dialogo({
    titulo: P.dialogoTitulo(p.equipamento || p.arquivo),
    conteudo: el("div", { class: "form" },
      el("div", { class: "resumo-pendencia" }, el("span", { class: `selo ${p.severidade}` }, T.niveis[p.severidade]),
        el("span", {}, [p.regiao, p.t_max != null && fmt(p.t_max, 1, " °C"), P.detectadaEm(dataCurta(p.detectada_em))].filter(Boolean).join(" · "))),
      p.reinspecao ? el("p", { class: "nota dica-reinspecao" }, icone("check"), P.reinspecaoTexto(dataCurta(p.reinspecao.data))) : null,
      el("div", { class: "campos-2" },
        el("label", {}, P.situacao, status), el("label", {}, P.prazo, prazo),
        el("label", {}, P.os, os), el("label", {}, P.responsavel, resp)),
      el("label", {}, P.nota, nota),
      historico.length ? el("details", { class: "historico-pendencia" }, el("summary", {}, P.historico(historico.length)),
        el("ol", {}, historico.map((h) => el("li", {}, el("b", {}, `${dataCurta(h.quando)} ${hora(h.quando).slice(0, 5)}`), " ", P.status[h.status] || h.status, h.nota ? el("span", { class: "nota" }, ` · ${h.nota}`) : null)))) : null),
    acoes: [{ rotulo: T.geral.cancelar, valor: "nao" }, { rotulo: P.salvar, valor: "sim", classe: "btn-primaria" }],
  });
  if (escolha !== "sim") return;
  try {
    const nova = await api(`/api/analises/${p.id}/acompanhamento`, json("PUT", {
      status: status.value, prazo: prazo.value, ordem_servico: os.value, responsavel: resp.value, nota: nota.value,
    }));
    avisar(P.salva(P.status[nova.status]));
    if (aoSalvar) aoSalvar(nova);
    else carregarPendencias();
  } catch (e) {
    falhou(e);
  }
}

/** Cartão da anomalia na análise aberta: situação, prazo e o botão de atualizar. */
function desenharAcompanhamento() {
  const alvo = $("#acompanhamento");
  const p = estado.analise.pendencia;
  alvo.hidden = !p;
  if (!p) return;
  const P = T.pend;
  alvo.replaceChildren(
    el("div", { class: "corpo" },
      el("span", { class: "rotulo" }, icone("chave"), P.cartaoTitulo),
      el("div", { class: "linha-acompanhamento" }, seloStatus(p.status), textoPrazo(p), p.ordem_servico ? el("span", { class: "nota" }, P.osCurta(p.ordem_servico)) : null)),
    el("button", { class: "btn btn-sm", type: "button", onclick: () => atualizarPendencia(p, (nova) => { estado.analise.pendencia = nova; desenharAcompanhamento(); estado.pendencias = null; }) }, icone("editar"), P.atualizar));
}

// ================================================================= equipamentos (histórico, tendência e próxima inspeção)

const SEM_EQUIPAMENTO = "sem-equipamento";
const LIMIAR_ESQUENTANDO = 0.5; // °C por mês

/** "2023-07-23T17:23:00" vira "23/07/2023". */
function dataCurta(iso) {
  if (!iso) return T.geral.semValor;
  const [a, m, d] = String(iso).slice(0, 10).split("-");
  return d && m && a ? `${d}/${m}/${a}` : T.geral.semValor;
}

/** Sobe, desce ou estável, com o valor em °C por mês e a explicação no balão. */
function selotendencia(t) {
  const E = T.equip;
  if (!t) return el("span", { class: "tendencia sem", title: E.semTendenciaDica }, icone("estavel"), E.semTendencia);
  const v = t.por_mes;
  const tipo = v > LIMIAR_ESQUENTANDO ? "sobe" : v < -LIMIAR_ESQUENTANDO ? "desce" : "estavel";
  const titulo = E.tendenciaTitulo(fmt(t.r2, 2), t.n) + (t.r2 < 0.3 ? E.tendenciaInstavel : "");
  return el("span", { class: `tendencia ${tipo}`, title: titulo }, icone(tipo), E.tendencia(`${v > 0 ? "+" : ""}${fmt(v, 1)}`));
}

function seloProxima(p) {
  if (!p) return null;
  const E = T.equip;
  return el("span", { class: `proxima${p.vencida ? " vencida" : ""}` }, icone("calendario"),
    p.vencida ? E.vencidaHa(-p.dias) : E.proxima(`${dataCurta(p.data)} (${E.emDias(p.dias)})`));
}

/** Linha pequena da máxima ao longo das inspeções, com a última bolinha na cor da severidade. */
function sparkline(serie) {
  const pts = serie.filter((p) => p.t_max != null);
  const L = 160, A = 36, m = 4;
  const svg = svgEl("svg", { viewBox: `0 0 ${L} ${A}`, class: "sparkline", preserveAspectRatio: "xMinYMid meet", "aria-hidden": "true" });
  if (!pts.length) return svg;
  const ts = pts.map((p) => Date.parse(p.data));
  const vs = pts.map((p) => p.t_max);
  const [t0, t1] = [Math.min(...ts), Math.max(...ts)];
  const [v0, v1] = [Math.min(...vs), Math.max(...vs)];
  const x = (t) => (t1 > t0 ? m + ((t - t0) / (t1 - t0)) * (L - 2 * m) : L / 2);
  const y = (v) => (v1 > v0 ? A - m - ((v - v0) / (v1 - v0)) * (A - 2 * m) : A / 2);
  if (pts.length > 1) svg.append(svgEl("path", { d: pts.map((p, i) => `${i ? "L" : "M"}${x(ts[i]).toFixed(1)} ${y(p.t_max).toFixed(1)}`).join(" "), class: "linha" }));
  pts.forEach((p, i) => {
    const ultimo = i === pts.length - 1;
    if (ultimo || p.severidade !== "normal") svg.append(svgEl("circle", { cx: x(ts[i]).toFixed(1), cy: y(p.t_max).toFixed(1), r: ultimo ? 3.5 : 2.5, style: `fill: var(--${p.severidade})` }));
  });
  return svg;
}

/** Séries no tempo (eixo x em datas). series: [{nome, indice, pontos: [{data, valor, severidade, id}]}]. */
function graficoDatas(titulo, series, { aoClicar = null, unidade = " °C", tendencia = false } = {}) {
  const todos = series.flatMap((s) => s.pontos).filter((p) => p.valor != null);
  if (!todos.length) return null;
  const L = 1080, A = 280, m = { e: 44, d: 14, t: 12, b: 30 };
  const ts = todos.map((p) => Date.parse(p.data));
  let [t0, t1] = [Math.min(...ts), Math.max(...ts)];
  if (t1 - t0 < 864e5) { t0 -= 864e5; t1 += 864e5; } // uma data só: abre um dia para cada lado
  const vs = todos.map((p) => p.valor);
  const folga = Math.max(1, (Math.max(...vs) - Math.min(...vs)) * 0.15);
  const lo = Math.floor(Math.min(...vs) - folga), hi = Math.ceil(Math.max(...vs) + folga);
  const x = (t) => m.e + ((t - t0) / (t1 - t0)) * (L - m.e - m.d);
  const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (A - m.t - m.b);
  const svg = svgEl("svg", { viewBox: `0 0 ${L} ${A}`, class: "grafico-svg", role: "img", "aria-label": titulo });
  for (const v of [lo, (lo + hi) / 2, hi]) {
    svg.append(svgEl("line", { x1: m.e, x2: L - m.d, y1: y(v), y2: y(v), class: "grade" }),
      svgEl("text", { x: m.e - 6, y: y(v) + 4, class: "eixo", "text-anchor": "end" }, fmt(v, 0)));
  }
  [[t0, "start"], [(t0 + t1) / 2, "middle"], [t1, "end"]].forEach(([t, ancora]) =>
    svg.append(svgEl("text", { x: x(t), y: A - 8, class: "eixo", "text-anchor": ancora }, dataCurta(new Date(t).toISOString()))));
  for (const s of series) {
    const pts = s.pontos.filter((p) => p.valor != null).sort((a, b) => Date.parse(a.data) - Date.parse(b.data));
    if (tendencia && pts.length >= 3) {
      // Reta de mínimos quadrados, tracejada: a mesma conta do servidor, só para desenhar.
      const xs = pts.map((p) => Date.parse(p.data)), ys = pts.map((p) => p.valor);
      const mx = xs.reduce((a, b) => a + b) / xs.length, my = ys.reduce((a, b) => a + b) / ys.length;
      const sxx = xs.reduce((a, x) => a + (x - mx) ** 2, 0);
      if (sxx > 0) {
        const k = xs.reduce((a, x, i) => a + (x - mx) * (ys[i] - my), 0) / sxx;
        const f = (t) => my + k * (t - mx);
        svg.append(svgEl("line", { x1: x(xs[0]), y1: y(f(xs[0])), x2: x(xs[xs.length - 1]), y2: y(f(xs[xs.length - 1])), class: "reta-tendencia" }));
      }
    }
    if (pts.length > 1) {
      svg.append(svgEl("path", { d: pts.map((p, i) => `${i ? "L" : "M"}${x(Date.parse(p.data)).toFixed(1)} ${y(p.valor).toFixed(1)}`).join(" "), class: "linha", style: `stroke: ${corSerie(s.indice)}` }));
    }
    for (const p of pts) {
      const c = svgEl("circle", {
        cx: x(Date.parse(p.data)).toFixed(1), cy: y(p.valor).toFixed(1), r: 4.5, class: aoClicar && p.id ? "ponto-clicavel" : null,
        style: `fill: ${p.severidade ? `var(--${p.severidade})` : corSerie(s.indice)}; stroke: var(--superficie); stroke-width: 1.5`,
      }, svgEl("title", {}, `${s.nome} · ${dataCurta(p.data)} · ${fmt(p.valor, 1, unidade)}${p.severidade ? ` · ${T.niveis[p.severidade]}` : ""}`));
      if (aoClicar && p.id) c.addEventListener("click", () => aoClicar(p));
      svg.append(c);
    }
  }
  return el("figure", { class: "grafico" }, el("figcaption", {}, titulo), svg, series.length > 1 ? legendaGrafico(series) : null);
}

function preencherSugestoes(equips) {
  const inst = [...new Set(equips.map((e) => e.instalacao).filter(Boolean))].sort();
  const eqs = [...new Set(equips.map((e) => e.equipamento).filter(Boolean))].sort();
  $("#dl-instalacoes").replaceChildren(...inst.map((v) => el("option", { value: v })));
  $("#dl-equipamentos").replaceChildren(...eqs.map((v) => el("option", { value: v })));
  const vencidas = equips.filter((e) => e.proxima_inspecao && e.proxima_inspecao.vencida).length;
  const c = $("#contador-vencidas");
  c.hidden = !vencidas;
  c.textContent = String(vencidas);
}

async function carregarEquipamentos(sub) {
  $("#equip-inicio").hidden = !!sub;
  $("#equip-detalhe").hidden = !sub;
  if (sub) return abrirEquipamento(decodeURIComponent(sub));
  const alvo = $("#lista-equip");
  $("#kpis-equip").replaceChildren(...esqueleto.kpis(4).children);
  if (!estado.equipamentos) alvo.replaceChildren(esqueleto.tabela(4));
  try {
    estado.equipamentos = await api("/api/equipamentos");
  } catch (e) {
    $("#kpis-equip").replaceChildren();
    return alvo.replaceChildren(estadoErro(T.equip.erroTitulo, e, () => carregarEquipamentos()));
  }
  preencherSugestoes(estado.equipamentos);
  desenharEquipamentos();
}

function desenharEquipamentos() {
  const E = T.equip;
  const todos = estado.equipamentos || [];
  const reais = todos.filter((e) => e.chave !== SEM_EQUIPAMENTO);
  const sem = todos.find((e) => e.chave === SEM_EQUIPAMENTO);
  const alvo = $("#lista-equip");
  $("#filtros-equip").hidden = !reais.length;
  $("#kpis-equip").hidden = !reais.length;
  if (!reais.length) {
    $("#kpis-equip").replaceChildren();
    return alvo.replaceChildren(estadoVazio({
      nomeIcone: "ativos", titulo: E.vazioTitulo, texto: E.vazioTexto,
      acoes: [el("a", { class: "btn btn-primaria", href: "#inspecoes" }, icone("editar"), E.vazioAcao)],
    }));
  }
  const filtros = {
    todos: () => true,
    anomalia: (e) => e.severidade !== "normal",
    vencida: (e) => e.proxima_inspecao && e.proxima_inspecao.vencida,
    esquentando: (e) => e.tendencia && e.tendencia.por_mes > LIMIAR_ESQUENTANDO,
  };
  const filtro = estado.filtroEquip || "todos";
  const kpi = (rotulo, chave, nota, cor) => el("button", {
    class: "kpi-grande", type: "button", "aria-pressed": String(filtro === chave),
    onclick: () => { estado.filtroEquip = filtro === chave ? "todos" : chave; desenharEquipamentos(); },
  }, el("span", {}, cor ? el("i", { class: "ponto", style: { background: `var(--${cor})`, boxShadow: "none" } }) : null, rotulo),
  el("b", {}, String(reais.filter(filtros[chave]).length)), nota ? el("small", {}, nota) : null);
  $("#kpis-equip").replaceChildren(
    kpi(E.kTotal, "todos"),
    kpi(E.kAnomalia, "anomalia", null, "programar"),
    kpi(E.kVencida, "vencida", null, "imediato"),
    kpi(E.kEsquentando, "esquentando", E.kEsquentandoNota, "urgente"));

  const termo = (estado.buscaEquip || "").trim().toLowerCase();
  const visiveis = reais.filter(filtros[filtro]).filter((e) => !termo || `${e.instalacao} ${e.equipamento}`.toLowerCase().includes(termo));
  if (!visiveis.length) {
    alvo.replaceChildren(estadoVazio({ nomeIcone: "busca", titulo: E.nadaTitulo, texto: E.nadaTexto, compacto: true }));
  } else {
    const grupos = new Map();
    for (const e of visiveis) {
      const nome = e.instalacao || E.semInstalacao;
      if (!grupos.has(nome)) grupos.set(nome, []);
      grupos.get(nome).push(e);
    }
    alvo.replaceChildren(...[...grupos].map(([nome, lista]) => el("section", { class: "grupo-equip" },
      el("h2", { class: "grupo-titulo" }, icone("ativos"), nome, el("span", { class: "nota" }, String(lista.length))),
      el("div", { class: "grade-equip" }, animarEntrada(lista.map(cartaoEquipamento))))));
  }
  if (sem && filtro === "todos" && !termo) {
    alvo.append(el("div", { class: "aviso-sem-equip" }, icone("info"),
      el("div", {}, el("b", {}, E.semEquipTitulo(sem.inspecoes)), el("p", { class: "nota" }, E.semEquipTexto)),
      el("a", { class: "btn btn-sm", href: "#inspecoes" }, icone("editar"), E.vazioAcao)));
  }
}

function cartaoEquipamento(e) {
  const E = T.equip;
  const abrir = () => { location.hash = `equipamentos/${encodeURIComponent(e.chave)}`; };
  return el("article", { class: "cartao-equip", tabindex: "0", onclick: abrir, onkeydown: (ev) => { if (ev.key === "Enter") abrir(); } },
    el("img", { class: "cartao-equip-img", src: `/api/analises/${e.ultima_id}/miniatura.png`, alt: "", loading: "lazy" }),
    el("div", { class: "cartao-equip-corpo" },
      el("div", { class: "cartao-equip-topo" },
        el("b", { class: "cartao-equip-nome", title: e.equipamento }, e.equipamento),
        el("span", { class: `selo ${e.severidade}` }, T.niveis[e.severidade])),
      el("span", { class: "nota" }, `${E.inspecoes(e.inspecoes)} · ${E.ultima(dataCurta(e.ultima))}`),
      el("div", { class: "cartao-equip-serie" }, sparkline(e.serie), el("b", { class: "num" }, fmt(e.t_max, 1, " °C"))),
      el("div", { class: "cartao-equip-rodape" }, selotendencia(e.tendencia), seloProxima(e.proxima_inspecao))));
}

async function abrirEquipamento(chave) {
  const alvo = $("#equip-detalhe");
  alvo.replaceChildren(esqueleto.kpis(4), esqueleto.bloco(), esqueleto.tabela(4));
  let d;
  try {
    d = await api(`/api/equipamentos/${encodeURIComponent(chave)}`);
  } catch (e) {
    return alvo.replaceChildren(estadoErro(T.equip.erroTitulo, e, () => abrirEquipamento(chave)));
  }
  estado.equipamentoAberto = d;
  atualizarTrilha();
  desenharEquipamento(d);
}

function desenharEquipamento(d) {
  const E = T.equip;
  const sem = d.chave === SEM_EQUIPAMENTO;
  const ids = d.lista.map((it) => it.id);
  const adicionar = () => {
    estado.destinoEquipamento = { instalacao: d.instalacao, equipamento: d.equipamento, chave: d.chave };
    abrirArquivos();
  };
  const cabecalho = el("header", { class: "cabecalho cabecalho-analise" },
    el("div", { class: "titulo-analise" },
      el("a", { class: "btn btn-fantasma btn-icone", href: "#equipamentos", "aria-label": E.voltar, title: E.voltar }, icone("voltar")),
      el("div", {},
        el("h1", { class: "nome-arquivo" }, sem ? E.semEquipTitulo(d.inspecoes) : d.equipamento),
        el("div", { class: "etiquetas" },
          d.instalacao ? el("span", { class: "etiqueta" }, icone("ativos"), d.instalacao) : null,
          el("span", { class: `selo ${d.severidade}` }, T.niveis[d.severidade]),
          el("span", { class: "etiqueta" }, `${E.inspecoes(d.inspecoes)} · ${E.desde(dataCurta(d.primeira))}`)))),
    el("div", { class: "acoes" },
      sem ? null : el("button", { class: "btn", type: "button", title: E.adicionarTitulo, onclick: adicionar }, icone("upload"), E.adicionar),
      el("button", { class: "btn btn-primaria", type: "button", onclick: () => emitirRelatorio(d.lista.slice().reverse().map((it) => it.id)) }, icone("laudo"), E.relatorio)));

  const kpi = (rotulo, valor, nota) => el("div", { class: "kpi-grande" }, el("span", {}, rotulo), valor, nota ? el("small", {}, nota) : null);
  const prox = d.proxima_inspecao;
  // Com ambiente e carga em ao menos 2 inspeções, dá para comparar a elevação projetada para plena carga.
  const temPlena = d.serie.filter((p) => p.elevacao_plena != null).length >= 2;
  const modo = temPlena ? (estado.modoSerieEquip || (d.tendencia_plena ? "plena" : "medida")) : "medida";
  const tend = modo === "plena" ? d.tendencia_plena : d.tendencia;
  const kpis = el("div", { class: "kpis-grandes" },
    kpi(E.estadoAtual, el("b", {}, el("span", { class: `selo selo-grande ${d.severidade}` }, T.niveis[d.severidade])), E.ultima(dataCurta(d.ultima))),
    kpi(E.tmaxUltima, el("b", { class: "num" }, fmt(d.t_max, 1, " °C")), d.serie[d.serie.length - 1].regiao || null),
    kpi(modo === "plena" ? E.tendenciaPlenaRotulo : E.tendenciaRotulo, el("b", {}, selotendencia(tend)),
      d.projecao_mta ? E.estimativaMta(dataCurta(d.projecao_mta.data)) + (d.projecao_mta.confiavel ? "" : E.estimativaFraca) : modo === "plena" ? E.plenaNota : null),
    prox ? kpi(E.proximaRotulo, el("b", { class: prox.vencida ? "texto-erro" : "" }, dataCurta(prox.data)), prox.vencida ? E.vencidaHa(-prox.dias) : E.prazo(prox.prazo_dias)) : null);

  const abrirPonto = (p) => { location.hash = `analise/${p.id}`; };
  const grafico = graficoDatas(modo === "plena" ? E.graficoPlenaTitulo : E.graficoTitulo,
    [{ nome: d.equipamento || E.semInstalacao, indice: 0, pontos: d.serie.map((p) => ({ ...p, valor: modo === "plena" ? p.elevacao_plena : p.t_max })) }],
    { aoClicar: abrirPonto, tendencia: !!tend });
  const trocaModo = temPlena ? el("div", { class: "segmentado", role: "group", "aria-label": E.serieRotulo },
    ["medida", "plena"].map((m) => el("button", { type: "button", "aria-pressed": String(m === modo), title: m === "plena" ? E.plenaNota : null,
      onclick: () => { estado.modoSerieEquip = m; desenharEquipamento(d); } }, m === "plena" ? E.serieplena : E.serieMedida))) : null;
  const pecas = d.componentes.filter((c) => c.classe !== "ponto_quente");
  const graficoPecas = pecas.length > 1
    ? graficoDatas(E.graficoPecasTitulo, pecas.slice(0, 4).map((c, i) => ({ nome: nomeClasse(c.classe), indice: i, pontos: c.pontos.map((p) => ({ ...p, valor: p.t_max, severidade: null })) })), { aoClicar: abrirPonto })
    : null;

  const tabelaPecas = d.componentes.length
    ? el("div", { class: "cartao" },
      el("h2", { class: "cartao-titulo" }, E.componentes),
      el("table", { class: "tabela tabela-compacta" },
        el("thead", {}, el("tr", {}, [E.colPeca, E.colUltima, E.colDt, E.colTendencia, E.colEstado].map((t) => el("th", {}, t)))),
        el("tbody", {}, d.componentes.map((c) => el("tr", {},
          el("td", {}, nomeClasse(c.classe)),
          el("td", { class: "num" }, fmt(c.t_max, 1, " °C")),
          el("td", { class: "num" }, c.pontos[c.pontos.length - 1].dt != null ? fmt(c.pontos[c.pontos.length - 1].dt, 1, " °C") : T.geral.semValor),
          el("td", {}, selotendencia(c.tendencia)),
          el("td", {}, el("span", { class: `selo ${c.severidade}` }, T.niveis[c.severidade])))))))
    : null;

  const historico = el("div", { class: "cartao" },
    el("h2", { class: "cartao-titulo" }, E.historico),
    el("ol", { class: "linha-inspecoes" }, d.lista.map((it) => {
      const p = it.destaque;
      return el("li", {}, el("a", { href: `#analise/${it.id}` },
        el("img", { src: miniaturaSrc(it), alt: "", loading: "lazy" }),
        el("div", { class: "linha-inspecoes-texto" },
          el("b", {}, dataCurta(it.data_captura || it.criado_em)),
          el("span", { class: "nota" }, p ? `${p.nome} · ${fmt(p.t_max, 1, " °C")}` : it.arquivo)),
        el("span", { class: `selo ${it.resumo.severidade}` }, T.niveis[it.resumo.severidade])));
    })));

  $("#equip-detalhe").replaceChildren(...[
    cabecalho, kpis,
    el("div", { class: "cartao" }, trocaModo ? el("div", { class: "barra-grafico" }, trocaModo) : null, grafico, el("p", { class: "nota" }, E.graficoDica)),
    graficoPecas ? el("div", { class: "cartao" }, graficoPecas) : null,
    el("div", { class: "grade-equip-detalhe" }, tabelaPecas, historico),
  ].filter(Boolean));
}

/** Instalação e equipamento de várias inspeções de uma vez (Inspeções › seleção). */
async function definirEquipamento(ids) {
  const E = T.equip;
  const primeira = estado.inspecoes.find((it) => it.id === ids[0]);
  const ident = (primeira && primeira.identificacao) || {};
  const inst = el("input", { value: ident.instalacao || "", list: "dl-instalacoes", autocomplete: "off", placeholder: "SE Campina Grande II" });
  const equip = el("input", { value: ident.equipamento || "", list: "dl-equipamentos", autocomplete: "off", placeholder: "TR-01 69/13,8 kV" });
  if (!estado.equipamentos) api("/api/equipamentos").then((l) => { estado.equipamentos = l; preencherSugestoes(l); }).catch(() => {});
  const escolha = await dialogo({
    titulo: E.definirTitulo(ids.length),
    conteudo: el("div", { class: "form" }, el("p", { class: "nota" }, E.definirTexto),
      el("label", {}, E.instalacao, inst), el("label", {}, E.equipamento, equip)),
    acoes: [{ rotulo: T.geral.cancelar, valor: "nao" }, { rotulo: E.salvar, valor: "sim", classe: "btn-primaria" }],
  });
  if (escolha !== "sim") return;
  if (!equip.value.trim()) return avisar(E.obrigatorio, { erro: true });
  try {
    const r = await api("/api/analises/identificacao", json("POST", { ids, instalacao: inst.value, equipamento: equip.value }));
    estado.selecao.clear();
    estado.equipamentos = null;
    avisar(E.definido(r.atualizadas, equip.value.trim()), { acao: { rotulo: E.verEquipamento, executar: () => { location.hash = `equipamentos/${encodeURIComponent(r.chave)}`; } } });
    carregarInspecoes();
  } catch (e) {
    falhou(e);
  }
}

// ================================================================= vídeo ao vivo (simulação da câmera)

const EXT_VIDEO = /\.(mp4|avi|mov|mkv|m4v|wmv|webm)$/i;
const ATIVOS_VIDEO = ["na_fila", "processando"];
// id e dados do vídeo aberto, quadros recebidos, quadro na tela, reprodução, sondagem do servidor.
const vid = { id: null, dados: null, quadros: [], atual: -1, tocando: false, seguindo: true, timer: null, sonda: null, sondaLista: null, camada: "tudo", modo: "ao_vivo", cache: new Map(), grafico: null };

/** 83,4 s vira "1:23,4". */
function tempoVideo(s) {
  if (s == null || !Number.isFinite(s)) return T.geral.semValor;
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(1).padStart(4, "0").replace(".", ",")}`;
}

const ativoVideo = () => !!vid.dados && ATIVOS_VIDEO.includes(vid.dados.status);

function pararVideo() {
  clearTimeout(vid.sonda);
  clearTimeout(vid.timer);
  clearTimeout(vid.sondaLista);
  vid.tocando = false;
}

// ---------------------------------------------------------------- lista e envio

function mostrarInicioVideo() {
  pararVideo();
  vid.id = null;
  vid.dados = null;
  $("#video-inicio").hidden = false;
  $("#video-aberto").hidden = true;
  atualizarTrilha();
  carregarVideos();
}

async function carregarVideos() {
  const alvo = $("#lista-videos");
  if (!alvo.childElementCount) alvo.replaceChildren(esqueleto.linhas(3));
  prepararFormVideo();
  let lista;
  try {
    lista = await api("/api/videos");
  } catch (e) {
    return alvo.replaceChildren(estadoErro(T.video.erroTitulo, e, carregarVideos));
  }
  if (estado.vista !== "video" || vid.id) return;
  $("#videos-total").textContent = lista.length ? T.video.total(lista.length) : "";
  const algumAtivo = lista.some((v) => ATIVOS_VIDEO.includes(v.status));
  $("#nav-video-ponto").hidden = !algumAtivo;
  if (!lista.length) {
    return alvo.replaceChildren(estadoVazio({ nomeIcone: "video", titulo: T.video.vazioTitulo, texto: T.video.vazioTexto, compacto: true }));
  }
  const primeiraVez = !$(".grade-videos", alvo);
  const cartoes = lista.map(cartaoVideo);
  alvo.replaceChildren(el("div", { class: "grade-videos" }, primeiraVez ? animarEntrada(cartoes) : cartoes));
  clearTimeout(vid.sondaLista);
  if (algumAtivo) vid.sondaLista = setTimeout(carregarVideos, 2000);
}

function cartaoVideo(v) {
  const r = v.resumo || {};
  const ativo = ATIVOS_VIDEO.includes(v.status);
  const abrir = () => { location.hash = `video/${v.id}`; };
  const apagar = el("button", {
    class: "btn btn-sm btn-fantasma btn-icone", type: "button", title: T.geral.apagar, "aria-label": T.video.apagarRotulo(v.arquivo),
    onclick: (ev) => { ev.stopPropagation(); apagarVideo(v); },
  }, icone("lixo"));
  return el("article", { class: "cartao-video", tabindex: "0", onclick: abrir, onkeydown: (ev) => { if (ev.key === "Enter") abrir(); } },
    el("div", { class: "cartao-video-imagem" },
      v.miniatura ? el("img", { src: v.miniatura, alt: "", loading: "lazy" }) : icone("video"),
      el("span", { class: `status-video ${v.status}` }, ativo ? el("i", { class: "ponto-vivo" }) : null, T.video.status[v.status] || v.status),
      ativo ? el("div", { class: "progresso" }, el("i", { style: { transform: `scaleX(${v.progresso || 0})` } })) : null),
    el("div", { class: "cartao-video-corpo" },
      el("div", { class: "cartao-video-titulo" }, el("b", { title: v.arquivo }, v.arquivo), apagar),
      el("span", { class: "nota" }, `${dataHora(v.criado_em)} · ${tempoVideo(v.info.duracao_s)}${v.modelo ? ` · ${v.modelo.nome}` : ""}`),
      el("div", { class: "cartao-video-numeros" },
        r.analisados ? el("span", { class: "num" }, T.video.nQuadros(r.analisados)) : null,
        r.quadros_por_segundo != null ? el("span", { class: "num" }, `${fmt(r.quadros_por_segundo, 1)} q/s`) : null,
        r.t_max != null ? el("span", { class: "num" }, `máx. ${fmt(r.t_max, 1, " °C")}`) : null,
        r.severidade_max ? el("span", { class: `selo ${r.severidade_max}` }, T.niveis[r.severidade_max]) : null)));
}

function prepararFormVideo() {
  const sel = $("#v-modelo");
  const preencher = () => {
    const antes = sel.value;
    sel.replaceChildren(...estado.modelos.map((m) => new Option(m.nome, m.id)));
    sel.value = estado.modelos.some((m) => m.id === antes) ? antes : estado.ativo;
  };
  if (estado.modelos.length) preencher();
  else carregarListaModelos().then(preencher).catch(() => {});
  marcarModoVideo(vid.modo);
}

function marcarModoVideo(modo) {
  vid.modo = modo;
  marcarSegmentado("#seg-video-modo", modo);
  $("#campo-velocidade").hidden = modo !== "ao_vivo";
  $("#campo-intervalo").hidden = modo !== "intervalo";
  $("#video-modo-nota").textContent = modo === "ao_vivo" ? T.video.modoAoVivo : T.video.modoIntervalo;
}

/** Envia com XMLHttpRequest para mostrar o andamento (um vídeo pode ter centenas de MB). */
function enviarVideo(arquivo) {
  if (!arquivo) return;
  if (!EXT_VIDEO.test(arquivo.name)) return avisar(T.video.soVideos, { erro: true });
  if (location.hash !== "#video") location.hash = "video";
  const dados = new FormData();
  dados.append("arquivo", arquivo);
  dados.append("modo", vid.modo);
  dados.append("velocidade", $("#v-velocidade").value);
  dados.append("intervalo_s", $("#v-intervalo").value || "0.5");
  dados.append("modelo", $("#v-modelo").value || "");
  dados.append("t_min", $("#v-tmin").value);
  dados.append("t_max", $("#v-tmax").value);
  const caixa = $("#envio-video");
  const barra = $("#envio-video .progresso i");
  const texto = $("#envio-video-texto");
  const botao = $("#btn-video");
  caixa.hidden = false;
  botao.disabled = true;
  texto.textContent = T.video.enviando(0);
  const fim = () => {
    caixa.hidden = true;
    botao.disabled = false;
    barra.style.transform = "scaleX(0)";
  };
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/videos");
  xhr.upload.onprogress = (ev) => {
    if (!ev.lengthComputable) return;
    const p = ev.loaded / ev.total;
    barra.style.transform = `scaleX(${p})`;
    texto.textContent = T.video.enviando(Math.round(p * 100));
  };
  xhr.onload = () => {
    fim();
    let corpo = null;
    try { corpo = JSON.parse(xhr.responseText); } catch { /* resposta sem JSON */ }
    if (xhr.status >= 200 && xhr.status < 300 && corpo) {
      avisar(T.video.enviado);
      location.hash = `video/${corpo.id}`;
    } else {
      avisar((corpo && (corpo.erro || corpo.detail)) || T.geral.erroServidor(xhr.status), { erro: true });
    }
  };
  xhr.onerror = () => { fim(); avisar(T.geral.semResposta, { erro: true }); };
  xhr.send(dados);
}

async function apagarVideo(v) {
  if (!(await confirmar(T.video.apagarTitulo, T.video.apagarTexto(v.arquivo), T.geral.apagar, true))) return;
  try {
    await api(`/api/videos/${v.id}`, { method: "DELETE" });
    avisar(T.video.apagado);
    if (vid.id === v.id) location.hash = "video";
    else carregarVideos();
  } catch (e) {
    falhou(e);
  }
}

// ---------------------------------------------------------------- vídeo aberto

async function abrirVideo(id) {
  pararVideo();
  $("#video-inicio").hidden = true;
  $("#video-aberto").hidden = false;
  if (vid.id !== id) {
    Object.assign(vid, { id, dados: null, quadros: [], atual: -1, seguindo: true, camada: "tudo", grafico: null });
    vid.cache.clear();
    $("#v-arquivo").textContent = "…";
    $("#v-etiquetas").replaceChildren();
    $("#v-imagem").removeAttribute("src");
    $("#v-sobreposicao").replaceChildren();
    $("#v-hud").replaceChildren();
    $("#v-kpis").replaceChildren(...Array.from({ length: 4 }, () => el("div", { class: "kpi" }, el("div", { class: "esqueleto esq-linha" }))));
    $("#v-grafico").replaceChildren(esqueleto.bloco());
    $("#v-quadro").replaceChildren();
    $("#v-eventos").replaceChildren();
  }
  try {
    const d = await api(`/api/videos/${id}?desde=0`);
    if (vid.id === id) receberVideo(d, true);
  } catch (e) {
    falhou(e);
    location.hash = "video";
  }
}

function receberVideo(d, inicial = false) {
  const estavaAtivo = ativoVideo();
  if (inicial) vid.quadros = d.quadros || [];
  else for (const q of d.quadros || []) if (q.n === vid.quadros.length) vid.quadros.push(q);
  vid.dados = { ...d, quadros: undefined };
  const ativo = ativoVideo();
  $("#nav-video-ponto").hidden = !ativo;
  desenharCabecalhoVideo();
  prepararCamadasVideo();
  desenharKpisVideo();
  desenharGraficoVideo();
  desenharEventosVideo();
  $("#v-linha").max = String(Math.max(vid.quadros.length - 1, 0));
  if (vid.quadros.length) {
    if (ativo && vid.seguindo) mostrarQuadroVideo(vid.quadros.length - 1);
    else if (vid.atual < 0) mostrarQuadroVideo(0);
  } else {
    $("#v-hud").replaceChildren(el("span", {}, d.status === "na_fila" ? T.video.naFila : ativo ? T.video.preparando : T.video.semRegioes));
    $("#v-quadro").replaceChildren();
  }
  $("#btn-video-aovivo").hidden = !(ativo && !vid.seguindo);
  if (ativo) agendarSonda();
  else if (estavaAtivo) {
    if (d.status === "concluido") avisar(T.video.concluido);
    else if (d.status === "erro") avisar(d.erro || T.video.status.erro, { erro: true });
    else avisar(T.video.parado);
    if (vid.atual >= 0) desenharHud(vid.quadros[vid.atual]);
  }
}

function agendarSonda() {
  clearTimeout(vid.sonda);
  vid.sonda = setTimeout(async () => {
    const id = vid.id;
    if (estado.vista !== "video" || !id) return;
    try {
      const d = await api(`/api/videos/${id}?desde=${vid.quadros.length}`);
      if (vid.id === id) receberVideo(d);
    } catch {
      if (vid.id === id) agendarSonda();
    }
  }, 400);
}

function desenharCabecalhoVideo() {
  const d = vid.dados;
  const V = T.video;
  const op = d.opcoes;
  const ativo = ativoVideo();
  $("#v-arquivo").textContent = d.arquivo;
  $("#v-arquivo").title = d.arquivo;
  $("#v-etiquetas").replaceChildren(...[
    el("span", { class: `etiqueta${ativo ? " info" : d.status === "erro" ? " erro" : ""}`, title: d.erro || "" }, ativo ? el("i", { class: "ponto-vivo" }) : null, V.status[d.status] || d.status),
    el("span", { class: "etiqueta" }, op.modo === "ao_vivo" ? V.modoVivo(fmt(op.velocidade, op.velocidade % 1 ? 1 : 0)) : V.modoIntervalo(fmt(op.intervalo_s, 2))),
    d.modelo ? el("span", { class: "etiqueta" }, d.modelo.nome) : null,
    el("span", { class: `etiqueta${op.limites ? "" : " estimada"}` }, op.limites ? V.escalaFixa(fmt(op.limites[0], 1), fmt(op.limites[1], 1)) : V.escalaLida),
    el("span", { class: "etiqueta" }, V.duracao(tempoVideo(d.info.duracao_s), fmt(d.info.fps, 0)))].filter(Boolean));
  $("#btn-video-parar").hidden = !ativo;
  const barra = $("#v-progresso");
  barra.hidden = !ativo;
  $("i", barra).style.transform = `scaleX(${d.progresso || 0})`;
  $("#btn-video-salvar").disabled = !vid.quadros.length;
  $("#quadro-video").style.aspectRatio = `${d.info.largura} / ${d.info.altura}`;
  atualizarTrilha();
}

function prepararCamadasVideo() {
  const regioes = vid.quadros.flatMap((q) => q.regioes);
  const ambos = regioes.some((r) => r.classe === "ponto_quente") && regioes.some((r) => r.classe !== "ponto_quente");
  $("#seg-video-camada").hidden = !ambos;
  if (!ambos) vid.camada = "tudo";
  marcarSegmentado("#seg-video-camada", vid.camada);
  $("#btn-video-rotulos").setAttribute("aria-pressed", String(estado.rotulos));
}

function desenharKpisVideo() {
  const r = vid.dados.resumo || {};
  const V = T.video;
  const info = vid.dados.info;
  const kpi = (rotulo, valor, nota) => el("div", { class: "kpi" }, el("span", {}, rotulo), el("b", { class: "num" }, valor), nota ? el("small", {}, nota) : null);
  $("#v-kpis").replaceChildren(
    kpi(V.kQuadros, String(r.analisados || 0), V.kQuadrosDe(info.quadros)),
    kpi(V.kRitmo, r.quadros_por_segundo != null ? fmt(r.quadros_por_segundo, 1) : T.geral.semValor, V.kRitmoNota(fmt(info.fps, 0))),
    kpi(V.kLatencia, r.latencia_media_ms != null ? `${r.latencia_media_ms} ms` : T.geral.semValor, r.latencia_p95_ms != null ? V.kLatenciaNota(r.latencia_p95_ms) : null),
    kpi(V.kMaxima, fmt(r.t_max, 1, " °C"), r.severidade_max ? T.niveis[r.severidade_max] : null));
}

/** Máxima da cena em cada quadro analisado; bolinhas onde houve anomalia; clique leva ao instante. */
function desenharGraficoVideo() {
  const alvo = $("#v-grafico");
  const V = T.video;
  const qs = vid.quadros.filter((q) => q.t_max != null);
  const titulo = el("h3", { class: "sobrerrotulo" }, V.graficoTitulo);
  if (!qs.length) {
    vid.grafico = null;
    return alvo.replaceChildren(titulo, el("p", { class: "nota" }, vid.quadros.length ? V.graficoVazio : V.graficoEspera));
  }
  const dur = Math.max(vid.dados.info.duracao_s || 0, qs[qs.length - 1].tempo_s, 0.1);
  const L = 360, A = 150, m = { e: 34, d: 8, t: 8, b: 22 };
  const temps = qs.map((q) => q.t_max);
  const lo = Math.floor(Math.min(...temps) - 1), hi = Math.ceil(Math.max(...temps) + 1);
  const x = (t) => m.e + (t / dur) * (L - m.e - m.d);
  const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (A - m.t - m.b);
  const svg = svgEl("svg", { viewBox: `0 0 ${L} ${A}`, class: "grafico-svg grafico-tempo", role: "img", "aria-label": V.graficoTitulo });
  for (const v of [lo, (lo + hi) / 2, hi]) {
    svg.append(svgEl("line", { x1: m.e, x2: L - m.d, y1: y(v), y2: y(v), class: "grade" }),
      svgEl("text", { x: m.e - 5, y: y(v) + 4, class: "eixo", "text-anchor": "end" }, fmt(v, 0)));
  }
  [[0, "start"], [dur / 2, "middle"], [dur, "end"]].forEach(([t, ancora]) =>
    svg.append(svgEl("text", { x: x(t), y: A - 5, class: "eixo", "text-anchor": ancora }, tempoVideo(t))));
  svg.append(svgEl("path", { d: qs.map((q, i) => `${i ? "L" : "M"}${x(q.tempo_s).toFixed(1)} ${y(q.t_max).toFixed(1)}`).join(" "), class: "linha", style: "stroke: var(--serie-1)" }));
  for (const q of qs) {
    if (!q.severidade || q.severidade === "normal") continue;
    svg.append(svgEl("circle", { cx: x(q.tempo_s).toFixed(1), cy: y(q.t_max).toFixed(1), r: 3.2, style: `fill: var(--${q.severidade})` },
      svgEl("title", {}, `${tempoVideo(q.tempo_s)} · ${fmt(q.t_max, 1, " °C")} · ${T.niveis[q.severidade]}`)));
  }
  const cursor = svgEl("line", { y1: m.t, y2: A - m.b, class: "cursor-tempo" });
  svg.append(cursor);
  svg.addEventListener("click", (ev) => {
    const b = svg.getBoundingClientRect();
    const px = ((ev.clientX - b.left) / b.width) * L;
    irParaTempo(((px - m.e) / (L - m.e - m.d)) * dur);
  });
  vid.grafico = { cursor, x };
  alvo.replaceChildren(titulo, svg, el("p", { class: "nota" }, V.graficoDica));
  if (vid.atual >= 0) moverCursorGrafico(vid.quadros[vid.atual].tempo_s);
}

function moverCursorGrafico(t) {
  if (!vid.grafico) return;
  const px = vid.grafico.x(t).toFixed(1);
  vid.grafico.cursor.setAttribute("x1", px);
  vid.grafico.cursor.setAttribute("x2", px);
}

/** Trechos seguidos de quadros fora do normal, com o pior nível e o quadro mais quente de cada um. */
function eventosVideo() {
  const grupos = [];
  let g = null;
  for (const q of vid.quadros) {
    if (!q.severidade || q.severidade === "normal") {
      g = null;
      continue;
    }
    if (!g) grupos.push((g = { ini: q.tempo_s, fim: q.tempo_s, pior: q.severidade, quente: q, n: 0 }));
    g.fim = q.tempo_s;
    g.n += 1;
    if (NIVEIS.indexOf(q.severidade) > NIVEIS.indexOf(g.pior)) g.pior = q.severidade;
    if ((q.t_max ?? -Infinity) > (g.quente.t_max ?? -Infinity)) g.quente = q;
  }
  return grupos;
}

function desenharEventosVideo() {
  const V = T.video;
  const grupos = eventosVideo();
  const itens = grupos.slice(0, 40).map((g) => el("li", {},
    el("button", { type: "button", onclick: () => irParaQuadro(g.quente.n) },
      el("span", { class: `selo ${g.pior}` }, T.niveis[g.pior]),
      el("span", { class: "num" }, g.ini === g.fim ? tempoVideo(g.ini) : `${tempoVideo(g.ini)} a ${tempoVideo(g.fim)}`),
      el("span", { class: "nota" }, V.eventoResumo(g.n, fmt(g.quente.t_max, 1, " °C"))))));
  $("#v-eventos").replaceChildren(
    el("h3", { class: "sobrerrotulo" }, V.eventos(grupos.length)),
    itens.length ? el("ul", { class: "eventos-video" }, itens) : el("p", { class: "nota" }, vid.quadros.length ? V.semEventos : ""));
}

function carregarQuadro(n) {
  let im = vid.cache.get(n);
  if (!im) {
    im = new Image();
    im.src = `/api/videos/${vid.id}/quadros/${n}.jpg`;
    vid.cache.set(n, im);
    if (vid.cache.size > 80) vid.cache.delete(vid.cache.keys().next().value);
  }
  return im.decode ? im.decode().catch(() => {}) : Promise.resolve();
}

function mostrarQuadroVideo(i) {
  const q = vid.quadros[i];
  if (!q) return;
  vid.atual = i;
  const url = `/api/videos/${vid.id}/quadros/${q.n}.jpg`;
  // A imagem só troca depois de decodificada: sem piscar entre um quadro e outro.
  carregarQuadro(q.n).then(() => {
    if (vid.atual !== i) return;
    $("#v-imagem").src = url;
    desenharCaixasVideo(q);
  });
  for (let k = 1; k <= 3; k++) if (vid.quadros[i + k]) carregarQuadro(vid.quadros[i + k].n);
  $("#v-linha").value = String(i);
  $("#v-tempo").textContent = tempoVideo(q.tempo_s);
  $("#btn-video-salvar").disabled = false;
  $("#btn-video-aovivo").hidden = !(ativoVideo() && !vid.seguindo);
  desenharHud(q);
  desenharQuadroInfo(q);
  moverCursorGrafico(q.tempo_s);
}

function desenharCaixasVideo(q) {
  const s = $("#v-sobreposicao");
  s.replaceChildren();
  const [W, H] = q.matriz || vid.dados.matriz || [320, 240];
  const pct = (v, total) => `${(v / total) * 100}%`;
  for (const r of q.regioes.filter((x) => naCamadaDe(vid.camada, x))) {
    const [x0, y0, x1, y1] = r.caixa;
    const cor = r.severidade ? corNivel(r.severidade) : "var(--branco)";
    const temperatura = r.t_max != null ? fmt(r.t_max, 1, " °C") : null;
    const completo = temperatura ? `${r.nome} · ${temperatura}` : r.nome;
    const confianca = r.confianca != null ? ` · ${T.analise.confianca(fmt(r.confianca * 100, 0))}` : "";
    const caixa = el("div", {
      class: "caixa",
      dataset: { severidade: r.severidade || "normal", area: String((x1 - x0) * (y1 - y0)) },
      title: completo + confianca,
      style: { borderColor: cor, left: pct(x0, W), top: pct(y0, H), width: pct(x1 - x0, W), height: pct(y1 - y0, H) },
    }, el("span", { class: "etq", dataset: { completo, curto: temperatura || r.nome } }, el("i", { style: { background: cor } }), completo));
    if (r.x_max != null) {
      caixa.append(el("span", { class: "pico", style: { left: pct(r.x_max + 0.5 - x0, x1 - x0), top: pct(r.y_max + 0.5 - y0, y1 - y0) } }));
    }
    s.append(caixa);
  }
  const pq = q.ponto_mais_quente;
  if (pq && vid.camada !== "pecas") {
    s.append(el("span", { class: "alvo-maximo", title: T.analise.pqImagem(fmt(pq.t_max, 1, " °C"), pq.componente), style: { left: pct(pq.x + 0.5, W), top: pct(pq.y + 0.5, H) } }));
  }
  evitarColisaoDeEtiquetas(s);
}

function desenharHud(q) {
  const V = T.video;
  const aoVivo = ativoVideo() && vid.seguindo;
  $("#v-hud").replaceChildren(
    aoVivo ? el("b", { class: "hud-vivo" }, el("i", { class: "ponto-vivo" }), V.aoVivo) : el("b", {}, vid.tocando ? V.reproducao : V.pausado),
    el("span", { class: "num" }, tempoVideo(q.tempo_s)),
    el("span", { class: "num" }, `${q.ms} ms`),
    el("span", { class: "num" }, q.escala ? `${fmt(q.escala[0], 1)} a ${fmt(q.escala[1], 1)} °C` : V.semEscalaCurta));
}

function desenharQuadroInfo(q) {
  const V = T.video;
  const linhas = [
    [V.instante, `${tempoVideo(q.tempo_s)} · ${V.quadroN(q.indice)}`],
    [V.escala, q.escala ? `${fmt(q.escala[0], 1)} a ${fmt(q.escala[1], 1)} °C (${V.fontes[q.fonte_escala] || q.fonte_escala})` : V.fontes.sem_escala],
    [V.tempo, q.preparo ? V.preparo(q.ms) : q.etapas_ms ? `${q.ms} ms (${V.etapas(q.etapas_ms.temperatura, q.etapas_ms.deteccao, q.etapas_ms.medicao)})` : `${q.ms} ms`],
  ];
  if (q.pulados) linhas.push([V.perdidos, V.pulados(q.pulados)]);
  const regioes = q.regioes.filter((r) => naCamadaDe(vid.camada, r)).sort((a, b) => (b.t_max ?? -Infinity) - (a.t_max ?? -Infinity));
  const aviso = vid.dados.erro || vid.dados.aviso;
  $("#v-quadro").replaceChildren(...[
    el("h3", { class: "sobrerrotulo" }, V.neste),
    aviso ? el("p", { class: "nota" }, aviso) : null,
    el("dl", { class: "meta meta-larga" }, linhas.map(([k, v]) => el("div", {}, el("dt", {}, k), el("dd", {}, v)))),
    q.erro ? el("p", { class: "nota" }, V.erroQuadro) : null,
    regioes.length
      ? el("ul", { class: "lista-quadro" }, regioes.map((r) => el("li", {},
        el("span", { class: "faixa", style: { background: r.severidade ? corNivel(r.severidade) : "var(--borda-forte)" } }),
        el("span", { class: "nome" }, r.nome, r.componente ? el("small", {}, ` · ${T.analise.naPeca(r.componente)}`) : null),
        el("b", { class: "num" }, fmt(r.t_max, 1, " °C")),
        r.severidade ? el("span", { class: `selo ${r.severidade}` }, T.niveis[r.severidade]) : el("span"))))
      : el("p", { class: "nota" }, V.semRegioes)].filter(Boolean));
}

/** Naturalmente no ritmo em que os quadros foram analisados: a reprodução mostra o que a tela ao vivo mostrou. */
function agendarProximoQuadro() {
  clearTimeout(vid.timer);
  if (!vid.tocando) return;
  const i = vid.atual;
  const q = vid.quadros[i];
  const prox = vid.quadros[i + 1];
  if (!prox) {
    vid.tocando = false;
    if (ativoVideo()) vid.seguindo = true; // alcançou a análise em andamento: volta a acompanhar ao vivo
    atualizarBotaoTocar();
    if (q) mostrarQuadroVideo(i);
    return;
  }
  const ritmo = Number($("#v-ritmo").value) || 1;
  const espera = Math.max(30, ((prox.tempo_s - q.tempo_s) / ritmo) * 1000);
  vid.timer = setTimeout(() => {
    mostrarQuadroVideo(i + 1);
    agendarProximoQuadro();
  }, espera);
}

function atualizarBotaoTocar() {
  const b = $("#btn-video-tocar");
  $("use", b).setAttribute("href", vid.tocando ? "#i-pausa" : "#i-play");
  b.setAttribute("aria-label", vid.tocando ? T.video.pausar : T.video.tocar);
  b.title = `${vid.tocando ? T.video.pausar : T.video.tocar} (espaço)`;
}

function alternarTocarVideo() {
  if (!vid.quadros.length) return;
  if (vid.tocando) return pausarVideo();
  vid.seguindo = false;
  if (vid.atual >= vid.quadros.length - 1 && !ativoVideo()) mostrarQuadroVideo(0);
  vid.tocando = true;
  atualizarBotaoTocar();
  desenharHud(vid.quadros[vid.atual]);
  agendarProximoQuadro();
}

function pausarVideo() {
  vid.tocando = false;
  clearTimeout(vid.timer);
  atualizarBotaoTocar();
  if (vid.quadros[vid.atual]) desenharHud(vid.quadros[vid.atual]);
}

function irParaQuadro(n) {
  pausarVideo();
  vid.seguindo = false;
  mostrarQuadroVideo(Math.max(0, Math.min(n, vid.quadros.length - 1)));
}

function irParaTempo(t) {
  if (!vid.quadros.length) return;
  let melhor = 0;
  vid.quadros.forEach((q, i) => { if (Math.abs(q.tempo_s - t) < Math.abs(vid.quadros[melhor].tempo_s - t)) melhor = i; });
  irParaQuadro(melhor);
}

function voltarAoVivo() {
  pausarVideo();
  vid.seguindo = true;
  mostrarQuadroVideo(vid.quadros.length - 1);
}

function alternarRotulosVideo() {
  estado.rotulos = !estado.rotulos;
  guardarPreferencia("rotulos", estado.rotulos ? "sim" : "nao");
  $("#btn-video-rotulos").setAttribute("aria-pressed", String(estado.rotulos));
  $("#btn-rotulos").setAttribute("aria-pressed", String(estado.rotulos));
  if (vid.quadros[vid.atual]) desenharCaixasVideo(vid.quadros[vid.atual]);
}

function trocarCamadaVideo(camada) {
  vid.camada = camada;
  const q = vid.quadros[vid.atual];
  if (q) {
    desenharCaixasVideo(q);
    desenharQuadroInfo(q);
  }
}

async function pararAnaliseVideo(botao) {
  ocupado(botao, true);
  try {
    await api(`/api/videos/${vid.id}/cancelar`, { method: "POST" });
    avisar(T.video.parando);
  } catch (e) {
    falhou(e);
  } finally {
    ocupado(botao, false);
  }
}

async function salvarQuadroVideo(botao) {
  const q = vid.quadros[vid.atual];
  if (!q) return;
  pausarVideo();
  vid.seguindo = false;
  ocupado(botao, true);
  try {
    const a = await api(`/api/videos/${vid.id}/quadros/${q.n}/inspecao`, { method: "POST" });
    avisar(T.video.salvo(a.arquivo), { acao: { rotulo: T.video.abrir, executar: () => { location.hash = `analise/${a.id}`; } } });
    atualizarStatus();
  } catch (e) {
    falhou(e);
  } finally {
    ocupado(botao, false);
  }
}

function ligarVideo() {
  const zona = $("#soltar-video");
  const entrada = $("#arquivo-video");
  const escolher = () => entrada.click();
  $("#btn-video").addEventListener("click", (ev) => { ev.stopPropagation(); escolher(); });
  zona.addEventListener("click", escolher);
  zona.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); escolher(); } });
  entrada.addEventListener("change", () => { enviarVideo(entrada.files[0]); entrada.value = ""; });
  ["dragenter", "dragover"].forEach((t) => zona.addEventListener(t, (ev) => { ev.preventDefault(); zona.classList.add("sobre"); }));
  ["dragleave", "drop"].forEach((t) => zona.addEventListener(t, () => zona.classList.remove("sobre")));
  zona.addEventListener("drop", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    if (ev.dataTransfer.files.length) enviarVideo(ev.dataTransfer.files[0]);
  });
  segmentado("#seg-video-modo", marcarModoVideo);
  segmentado("#seg-video-camada", trocarCamadaVideo);
  $("#btn-video-rotulos").addEventListener("click", alternarRotulosVideo);
  $("#btn-video-voltar").addEventListener("click", () => { location.hash = "video"; });
  $("#btn-video-parar").addEventListener("click", (ev) => pararAnaliseVideo(ev.currentTarget));
  $("#btn-video-salvar").addEventListener("click", (ev) => salvarQuadroVideo(ev.currentTarget));
  $("#btn-video-tocar").addEventListener("click", alternarTocarVideo);
  $("#btn-video-aovivo").addEventListener("click", voltarAoVivo);
  $("#v-linha").addEventListener("input", (ev) => irParaQuadro(Number(ev.target.value)));
  $("#v-ritmo").addEventListener("change", () => { if (vid.tocando) agendarProximoQuadro(); });
}

/** Atalhos do vídeo aberto. Devolve true quando tratou a tecla. */
function teclaVideo(ev) {
  if (estado.vista !== "video" || !vid.id || $("#video-aberto").hidden) return false;
  if (ev.key === " " && document.activeElement.tagName === "BUTTON") return false; // o próprio botão já responde ao espaço
  if (ev.key === " ") alternarTocarVideo();
  else if (ev.key === "ArrowRight") irParaQuadro(vid.atual + 1);
  else if (ev.key === "ArrowLeft") irParaQuadro(vid.atual - 1);
  else if (ev.key === "r" || ev.key === "R") alternarRotulosVideo();
  else return false;
  ev.preventDefault();
  return true;
}

// ================================================================= painel

async function carregarPainel() {
  const corpo = $("#painel-corpo");
  corpo.replaceChildren(esqueleto.kpis(), el("div", { class: "painel-grade" }, esqueleto.tabela(6), esqueleto.bloco()));
  let lista, status, alertas, pendencias, equips;
  try {
    [lista, status, alertas, pendencias, equips] = await Promise.all([
      api("/api/analises"), api("/api/status"), api("/api/alertas"), api("/api/pendencias"), api("/api/equipamentos")]);
  } catch (e) {
    return corpo.replaceChildren(estadoErro(T.painel.erroTitulo, e, carregarPainel));
  }
  estado.inspecoes = lista;
  estado.pendencias = pendencias;
  estado.equipamentos = equips;
  atualizarContador();
  atualizarContadorPendencias();
  preencherSugestoes(equips);
  if (estado.vista !== "painel") return;

  const conta = (niveis) => lista.filter((it) => niveis.includes(it.resumo.severidade)).length;
  const criticas = conta(["urgente", "imediato"]);
  const kpi = (rotulo, valor, nota, destino, classe = "") =>
    el("button", { class: `kpi-grande ${classe}`, type: "button", onclick: destino }, el("span", {}, rotulo), el("b", {}, String(valor)), el("small", {}, nota));
  const irInspecoes = (filtro) => () => { estado.filtro = filtro; location.hash = "inspecoes"; };
  const kpis = el("div", { class: "kpis-grandes" }, animarEntrada([
    kpi(T.painel.kpiInspecoes, lista.length, T.painel.kpiInspecoesNota(lista.filter((it) => it.fonte === "monitoramento").length), irInspecoes("todas")),
    kpi(T.painel.kpiCriticas, criticas, T.painel.kpiCriticasNota, irInspecoes("grave"), criticas ? "critico" : ""),
    kpi(T.painel.kpiPendencias, pendencias.filter((p) => p.vencida).length, T.painel.kpiPendenciasNota(pendencias.filter((p) => ["aberta", "programada", "corrigida"].includes(p.status)).length),
      () => { estado.filtroPendencia = "vencidas"; location.hash = "pendencias"; }, pendencias.some((p) => p.vencida) ? "critico" : ""),
    kpi(T.painel.kpiVencidas, equips.filter((e) => e.proxima_inspecao && e.proxima_inspecao.vencida).length, T.painel.kpiVencidasNota(equips.filter((e) => e.chave !== SEM_EQUIPAMENTO).length),
      () => { estado.filtroEquip = "vencida"; location.hash = "equipamentos"; }),
    kpi(T.painel.kpiAlertas, status.alertas_pendentes, T.painel.kpiAlertasNota, () => (location.hash = "monitoramento"), status.alertas_pendentes ? "critico" : ""),
  ]));

  if (!lista.length) {
    return corpo.replaceChildren(boasVindas(), el("div", { class: "painel-grade" }, el("div"), cartaoMonitor(status, alertas)));
  }

  corpo.replaceChildren(kpis, el("div", { class: "painel-grade" },
    cartaoAtencao(lista),
    el("div", { class: "pilha" }, cartaoDistribuicao(lista), cartaoProximas(equips), cartaoMonitor(status, alertas))));
}

/** Equipamentos pela data da próxima inspeção: os vencidos primeiro. */
function cartaoProximas(equips) {
  const P = T.painel;
  const lista = equips.filter((e) => e.proxima_inspecao).sort((a, b) => a.proxima_inspecao.data.localeCompare(b.proxima_inspecao.data)).slice(0, 5);
  const corpo = lista.length
    ? el("ul", { class: "lista-proximas" }, lista.map((e) => el("li", {}, el("a", { href: `#equipamentos/${encodeURIComponent(e.chave)}` },
      el("span", { class: `ponto-sev`, style: { background: `var(--${e.severidade})` } }),
      el("span", { class: "nome" }, el("b", {}, e.equipamento), el("small", {}, e.instalacao || "")),
      el("span", { class: `quando${e.proxima_inspecao.vencida ? " vencida" : ""}` }, dataCurta(e.proxima_inspecao.data),
        el("small", {}, e.proxima_inspecao.vencida ? P.proximasVencida(-e.proxima_inspecao.dias) : T.equip.emDias(e.proxima_inspecao.dias)))))))
    : el("p", { class: "nota" }, P.proximasVazio);
  return el("div", { class: "cartao" },
    el("div", { class: "cartao-cabeca" }, el("h2", {}, P.proximasTitulo), el("a", { class: "link", href: "#equipamentos" }, P.verEquipamentos)),
    corpo);
}

function boasVindas() {
  const passo = ([titulo, texto]) => el("li", {}, el("div", {}, el("b", {}, titulo), texto));
  return el("div", { class: "boas-vindas entra" },
    el("div", {},
      el("h2", {}, T.painel.boasVindas),
      el("p", { class: "sub" }, T.painel.boasVindasTexto),
      el("ol", { class: "passos-inicio" }, passo(T.painel.passo1), passo(T.painel.passo2), passo(T.painel.passo3)),
      el("div", { class: "acoes" },
        el("button", { class: "btn btn-primaria", type: "button", onclick: abrirArquivos }, icone("upload"), T.painel.analisar),
        el("a", { class: "btn", href: "#analise" }, T.painel.verExemplos),
        el("a", { class: "btn btn-fantasma", href: "#configuracoes/identidade" }, T.painel.configurarEmpresa))),
    el("img", { src: "marca/logo.png", alt: "" }));
}

function valorDestaque(d) {
  if (!d) return "";
  if (d.pct_mta != null) return `${d.nome} · ${T.analise.pctMta(fmt(d.pct_mta, 0))}`;
  if (d.dt != null) return `${d.nome} · ΔT ${fmt(d.dt, 1, " °C")}`;
  return `${d.nome} · ${fmt(d.t_max, 1, " °C")}`;
}

function miniaturaSrc(it) {
  return `/api/analises/${it.id}/miniatura.png?v=${encodeURIComponent(it.resumo.severidade + it.resumo.regioes)}`;
}

function cartaoAtencao(lista) {
  const graves = lista
    .filter((it) => it.resumo.severidade !== "normal")
    .sort((a, b) =>
      NIVEIS.indexOf(b.resumo.severidade) - NIVEIS.indexOf(a.resumo.severidade) ||
      ((b.destaque && b.destaque.pct_mta) || 0) - ((a.destaque && a.destaque.pct_mta) || 0) ||
      b.criado_em.localeCompare(a.criado_em))
    .slice(0, 8);
  const cabeca = el("div", { class: "cartao-cabeca", style: { padding: "var(--e-5) var(--e-5) 0" } },
    el("div", {}, el("h2", {}, T.painel.atencaoTitulo), el("p", { class: "nota" }, T.painel.atencaoNota)));
  if (!graves.length) {
    return el("div", { class: "cartao" }, estadoVazio({ nomeIcone: "check", titulo: T.painel.tudoCerto, texto: T.painel.tudoCertoTexto, compacto: true }));
  }
  const linhas = graves.map((it) => {
    // O equipamento identifica a linha; instalação, arquivo e data vêm embaixo.
    const ident = it.identificacao;
    const titulo = ident.equipamento || it.arquivo;
    const detalhe = [ident.instalacao, ident.equipamento ? it.arquivo : null, dataHora(it.data_captura || it.criado_em)].filter(Boolean).join(" · ");
    return el("tr", { class: "clicavel", onclick: () => abrirInspecao(it.id) },
      el("td", {}, el("img", { class: "miniatura-tabela", src: miniaturaSrc(it), alt: "", loading: "lazy" })),
      el("td", {}, el("div", { class: "principal-celula" }, el("b", { title: titulo }, titulo), el("span", {}, detalhe))),
      el("td", { class: "num" }, valorDestaque(it.destaque)),
      el("td", {}, el("span", { class: `selo ${it.resumo.severidade}` }, T.niveis[it.resumo.severidade])),
      el("td", { class: "direita" }, el("button", { class: "btn btn-sm", type: "button", onclick: (ev) => { ev.stopPropagation(); abrirInspecao(it.id); } }, T.geral.abrir)));
  });
  return el("div", { class: "cartao tabela-cartao" }, cabeca,
    el("div", { class: "tabela-rolagem", style: { marginTop: "var(--e-4)" } },
      el("table", { class: "tabela" },
        el("thead", {}, el("tr", {}, T.painel.colunas.map((c) => el("th", {}, c)))),
        el("tbody", {}, animarEntrada(linhas)))));
}

function cartaoDistribuicao(lista) {
  const total = lista.length;
  const barra = el("div", { class: "barra-empilhada", role: "img", "aria-label": T.painel.distribuicao });
  const legenda = el("ul", { class: "legenda-severidade" });
  for (const n of [...NIVEIS].reverse()) {
    const q = lista.filter((it) => it.resumo.severidade === n).length;
    if (q) barra.append(el("i", { style: { width: `${(q / total) * 100}%`, background: `var(--${n})` }, title: `${T.niveis[n]}: ${q}` }));
    legenda.append(el("li", {}, el("span", { class: "ponto", style: { background: `var(--${n})` } }), T.niveis[n], el("b", {}, String(q))));
  }
  return el("div", { class: "cartao distribuicao" },
    el("div", {}, el("h2", {}, T.painel.distribuicao), el("p", { class: "nota" }, T.painel.distribuicaoNota(total))), barra, legenda);
}

function cartaoMonitor(status, alertas) {
  const m = status.monitoramento;
  const classe = m.erro && m.ativo ? "erro" : m.ativo ? "ativo" : "desligado";
  const rotulo = m.erro && m.ativo ? T.painel.monitorErro : m.ativo ? T.painel.monitorLigado : T.painel.monitorDesligado;
  const pares = el("dl", { class: "pares" },
    el("div", {}, el("dt", {}, T.painel.pasta), el("dd", { class: "mono", title: m.pasta || "" }, m.pasta ? caminhoCurto(m.pasta) : T.monitor.semPasta)),
    el("div", {}, el("dt", {}, T.painel.ultimaVerificacao), el("dd", {}, m.ultima_verificacao ? hora(m.ultima_verificacao) : T.geral.semValor)),
    m.ultima_imagem ? el("div", {}, el("dt", {}, T.painel.ultimaImagem), el("dd", {}, m.ultima_imagem.arquivo)) : null);
  const recentes = alertas.alertas.slice(0, 3).map((a) =>
    el("div", { class: "linha-estado" }, el("span", { class: `selo ${a.severidade}` }, T.niveis[a.severidade]), el("span", { class: "nota" }, `${dataHora(a.criado_em)} · ${a.arquivo}`)));
  return el("div", { class: "cartao resumo-monitor" },
    el("div", { class: "cartao-cabeca", style: { marginBottom: 0 } }, el("h2", {}, T.painel.monitorTitulo), el("a", { class: "btn btn-sm", href: "#monitoramento" }, m.ativo ? T.painel.verAlertas : T.painel.configurar)),
    el("div", { class: "linha-estado" }, el("i", { class: `ponto ${classe}` }), rotulo),
    m.erro && m.ativo ? el("p", { class: "nota" }, m.erro) : null,
    pares, recentes);
}

// ================================================================= nova análise

async function carregarInicio() {
  try {
    const [ex, lista] = await Promise.all([api("/api/exemplos"), api("/api/analises")]);
    estado.inspecoes = lista;
    atualizarContador();
    const recentes = lista.slice(0, 4);
    $("#bloco-recentes").hidden = !recentes.length;
    $("#recentes").replaceChildren(...animarEntrada(recentes.map((it) => cartaoMiniatura(miniaturaSrc(it), it.arquivo, dataHora(it.data_captura || it.criado_em), it.resumo.severidade, () => abrirInspecao(it.id)))));
    $("#bloco-exemplos").hidden = !ex.itens.length;
    $("#exemplos-fonte").textContent = ex.fonte;
    $("#exemplos").replaceChildren(...animarEntrada(ex.itens.map((it) => cartaoMiniatura(`/api/exemplos/${encodeURIComponent(it.nome)}/miniatura.jpg`, it.classe, it.nome, null, () => analisarExemplo(it.nome)))));
  } catch {
    /* sem exemplos e recentes a tela de nova análise continua funcionando */
  }
}

function cartaoMiniatura(src, titulo, subtitulo, severidade, acao) {
  const legenda = el("span", { class: "legenda" },
    el("span", { class: "linha" }, el("b", {}, titulo), severidade ? el("span", { class: `selo ${severidade}` }, T.niveis[severidade]) : null),
    el("span", {}, subtitulo));
  return el("button", { class: "miniatura", type: "button", onclick: acao }, el("img", { src, alt: titulo, loading: "lazy" }), legenda);
}

function atualizarContador() {
  const c = $("#contador-inspecoes");
  c.textContent = String(estado.inspecoes.length);
  c.hidden = !estado.inspecoes.length;
}

function abrirArquivos() {
  $("#arquivos").click();
}

/** Na página de um equipamento, "Adicionar imagens" já manda instalação e equipamento junto. */
function anexarDestino(dados, destino) {
  if (!destino) return;
  dados.append("instalacao", destino.instalacao || "");
  dados.append("equipamento", destino.equipamento || "");
}

async function enviarArquivos(lista) {
  const arquivos = [...lista].filter((f) => /\.(jpe?g|png)$/i.test(f.name));
  if (!arquivos.length) return avisar(T.geral.soImagens, { erro: true });
  let destino = estado.vista === "equipamentos" && location.hash.includes("/") ? estado.destinoEquipamento : null;
  const [inst, equip] = [$("#envio-instalacao").value.trim(), $("#envio-equipamento").value.trim()];
  if (!destino && estado.vista === "analise" && !estado.analise && (inst || equip)) destino = { instalacao: inst, equipamento: equip, chave: null };
  if (arquivos.length === 1) return analisarArquivo(arquivos[0], destino);
  return analisarLote(arquivos, destino);
}

function analisarArquivo(arquivo, destino = null) {
  const tarefa = () => {
    const dados = new FormData();
    dados.append("arquivo", arquivo);
    dados.append("modelo", estado.ativo || "");
    anexarDestino(dados, destino);
    return api("/api/analises", { method: "POST", body: dados });
  };
  return processarAnalise(arquivo.name, tarefa);
}

function analisarExemplo(nome) {
  return processarAnalise(nome, () => api(`/api/exemplos/${encodeURIComponent(nome)}/analisar`, json("POST", { modelo: estado.ativo })));
}

/** Mostra a análise tomando forma: esqueleto do resultado e etapas andando; no fim, o resultado; se falhar, o motivo e como tentar de novo. */
async function processarAnalise(nome, tarefa) {
  estado.processando = { nome };
  estado.analise = null;
  if (location.hash !== "#analise") history.pushState(null, "", "#analise");
  mostrarVista("analise");
  $("#analise-vazia").hidden = true;
  $("#analise-cheia").hidden = false;
  $("#a-arquivo").textContent = nome;
  $("#a-etiquetas").replaceChildren(el("span", { class: "etiqueta info" }, T.analise.analisandoEtiqueta));
  $("#a-acoes").hidden = true;
  $("#area-analise").hidden = true;
  $("#analise-estado").replaceChildren(
    el("div", { class: "area-analise" },
      el("div", { class: "palco" }, el("div", { class: "palco-barra" }, el("div", { class: "esqueleto esq-titulo" })), el("div", { class: "poco" }, el("div", { class: "esqueleto esq-palco" }))),
      el("div", { class: "inspetor" }, el("div", { class: "painel-aba" }, el("div", { class: "esqueleto esq-kpi" }), esqueleto.linhas(4), esqueleto.linhas(3)))));
  let passo = 0;
  mostrarEtapas(null, passo);
  const relogio = setInterval(() => mostrarEtapas(null, (passo = Math.min(passo + 1, 2))), 600);
  try {
    const a = await tarefa();
    clearInterval(relogio);
    estado.processando = null;
    abrirAnalise(a, true);
    api("/api/analises").then((lista) => { estado.inspecoes = lista; atualizarContador(); }).catch(() => {});
  } catch (e) {
    clearInterval(relogio);
    estado.processando = null;
    mostrarEtapas(null, passo);
    $("#a-etiquetas").replaceChildren(el("span", { class: "etiqueta estimada" }, T.geral.semValor));
    $("#analise-estado").replaceChildren(el("div", { class: "analise-erro" },
      estadoErro(T.analise.erroTitulo(nome), e, () => processarAnalise(nome, tarefa))));
    $(".estado-erro .acoes", $("#analise-estado")).append(el("button", { class: "btn btn-fantasma", type: "button", onclick: abrirArquivos }, T.analise.outroArquivo));
  }
}

async function analisarLote(arquivos, destino = null) {
  const barra = el("i");
  const itens = arquivos.map((f) => el("li", {}, el("span", {}, f.name), el("span", { class: "nota" }, T.analise.loteFila)));
  const texto = el("p", {}, T.analise.loteProgresso(0, arquivos.length));
  const d = $("#dialogo");
  $("#dialogo-titulo").textContent = T.analise.loteTitulo(arquivos.length);
  $("#dialogo-conteudo").replaceChildren(el("div", { class: "pilha" }, texto, el("div", { class: "progresso" }, barra), el("ul", { class: "lote" }, itens)));
  $("#dialogo-acoes").replaceChildren();
  d.onclose = null;
  d.showModal();
  let ok = 0;
  for (let i = 0; i < arquivos.length; i++) {
    const status = itens[i].lastChild;
    status.textContent = T.analise.loteAndando;
    const dados = new FormData();
    dados.append("arquivo", arquivos[i]);
    dados.append("modelo", estado.ativo || "");
    anexarDestino(dados, destino);
    try {
      const a = await api("/api/analises", { method: "POST", body: dados });
      status.replaceChildren(el("span", { class: `selo ${a.resumo.severidade}` }, T.niveis[a.resumo.severidade]));
      ok++;
    } catch (e) {
      status.textContent = e.message.slice(0, 60);
      status.style.color = "var(--erro-texto)";
    }
    barra.style.transform = `scaleX(${(i + 1) / arquivos.length})`;
    texto.textContent = T.analise.loteProgresso(i + 1, arquivos.length);
  }
  texto.textContent = T.analise.loteFim(ok, arquivos.length);
  $("#dialogo-acoes").replaceChildren(
    el("button", { class: "btn", value: "fechar", type: "submit" }, T.geral.fechar),
    el("button", { class: "btn btn-primaria", value: "ver", type: "submit" }, destino && destino.chave ? T.equip.verEquipamento : T.analise.verInspecoes),
  );
  const escolha = await new Promise((r) => (d.onclose = () => r(d.returnValue)));
  estado.equipamentos = null;
  if (escolha === "ver") location.hash = destino && destino.chave ? `equipamentos/${encodeURIComponent(destino.chave)}` : "inspecoes";
  else rota();
}

async function abrirInspecao(id) {
  if (location.hash !== `#analise/${id}`) history.pushState(null, "", `#analise/${id}`);
  mostrarVista("analise");
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
  if (location.hash !== "#analise" && location.hash.startsWith("#analise")) history.replaceState(null, "", "#analise");
  $("#topo-nova").hidden = true;
  carregarInicio();
}

function mostrarAnaliseAberta() {
  $("#analise-vazia").hidden = true;
  $("#analise-cheia").hidden = false;
  $("#area-analise").hidden = false;
  $("#a-acoes").hidden = false;
  $("#analise-estado").replaceChildren();
  $("#topo-nova").hidden = false;
}

function abrirAnalise(a, recemCriada = false) {
  const nova = !estado.analise || estado.analise.id !== a.id;
  estado.analise = a;
  if (a.matriz) estado.matriz = decodificar(a.matriz);
  if (nova) {
    estado.selecionada = null;
    estado.isoterma = { ligada: false, valor: null };
    $("#btn-isoterma").setAttribute("aria-pressed", "false");
    $("#isoterma-controle").hidden = true;
    definirFerramenta("selecionar");
    $("#btn-foto").setAttribute("aria-pressed", "false");
    $("#quadro-foto").hidden = true;
    $("#palco-imagens").classList.remove("com-foto");
    trocarAba("resultado", false);
    estado.rascunhoLinha = null;
    restaurarExibicao(a);
  }
  const destino = `#analise/${a.id}`;
  if (location.hash !== destino) {
    if (recemCriada || location.hash === "#analise") history.replaceState(null, "", destino);
    else history.pushState(null, "", destino);
  }
  mostrarVista("analise");
  mostrarAnaliseAberta();
  atualizarTrilha();
  if (nova) {
    const area = $("#area-analise");
    area.classList.remove("entra");
    void area.offsetWidth;
    area.classList.add("entra");
  }
  preencherCabecalho();
  mostrarEtapas(a.etapas);
  prepararCamadas();
  desenharTermograma();
  desenharCaixas();
  preencherResultado();
  desenharAcompanhamento();
  preencherMedicoes();
  preencherCondicoes();
  preencherParametros();
  preencherLaudo();
  const sel = $("#sel-modelo");
  if ([...sel.options].some((o) => o.value === a.modelo.id)) sel.value = a.modelo.id;
}

function mostrarEtapas(tempos, andando = -1) {
  $("#etapas").replaceChildren(
    ...T.etapas.map((nome, i) => {
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
  const e = [el("span", { class: `etiqueta ${a.radiometrica ? "medida" : "estimada"}` }, a.radiometrica ? T.analise.medida : T.analise.estimada)];
  if (a.fonte === "monitoramento") e.push(el("span", { class: "etiqueta info" }, icone("camera"), T.analise.monitor));
  if (a.metadados.camera) e.push(el("span", { class: "etiqueta" }, a.metadados.camera));
  if (a.metadados.data_hora) e.push(el("span", { class: "etiqueta" }, icone("calendario"), dataHora(a.metadados.data_hora)));
  e.push(el("span", { class: "etiqueta" }, a.modelo.nome));
  if (a.parametros_ajustados && a.parametros_ajustados.length) {
    e.push(el("span", { class: "etiqueta info", title: T.analise.ajustadosTitulo }, T.analise.ajustados(fmt(a.metadados.emissividade, 2))));
  }
  const ident = a.identificacao || {};
  if (ident.equipamento && a.equipamento_chave) {
    e.unshift(el("a", { class: "etiqueta etiqueta-link", href: `#equipamentos/${encodeURIComponent(a.equipamento_chave)}`, title: T.equip.chipTitulo }, icone("ativos"), T.equip.chip(ident.equipamento)));
  }
  $("#a-etiquetas").replaceChildren(...e);
  $("#btn-foto").hidden = !a.tem_foto;
}

function faixaAtual() {
  if (estado.faixa === "manual" && estado.faixaManual) return estado.faixaManual;
  if (estado.faixa === "equipamento" || estado.faixa === "manual") return estado.analise.matriz_info.faixa_exibicao;
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
  if (iso != null) $("#isoterma-area").textContent = `${fmt((acima / Math.max(estado.matriz.validos, 1)) * 100, 1)}% ${T.analise.daImagem}`;

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

/** Lugares que uma etiqueta pode ocupar em volta da caixa, na ordem de preferência. */
const POSICOES_ETIQUETA = [
  { bottom: "100%", top: "auto", left: "-2px", right: "auto", marginBottom: "var(--e-1)", marginTop: "0" }, // acima, à esquerda
  { bottom: "100%", top: "auto", left: "auto", right: "-2px", marginBottom: "var(--e-1)", marginTop: "0" }, // acima, à direita
  { bottom: "auto", top: "100%", left: "-2px", right: "auto", marginBottom: "0", marginTop: "var(--e-1)" }, // abaixo, à esquerda
  { bottom: "auto", top: "100%", left: "auto", right: "-2px", marginBottom: "0", marginTop: "var(--e-1)" }, // abaixo, à direita
  { bottom: "auto", top: "2px", left: "2px", right: "auto", marginBottom: "0", marginTop: "0" },            // dentro, em cima
  { bottom: "2px", top: "auto", left: "2px", right: "auto", marginBottom: "0", marginTop: "0" },            // dentro, embaixo
];

/** Lugares do rótulo de um ponto ou linha: à direita, à esquerda, acima e abaixo da mira. */
const POSICOES_MEDICAO = [
  { left: "calc(100% + var(--e-1))", right: "auto", top: "50%", bottom: "auto", transform: "translateY(-50%)" },
  { left: "auto", right: "calc(100% + var(--e-1))", top: "50%", bottom: "auto", transform: "translateY(-50%)" },
  { left: "50%", right: "auto", top: "auto", bottom: "calc(100% + var(--e-1))", transform: "translateX(-50%)" },
  { left: "50%", right: "auto", top: "calc(100% + var(--e-1))", bottom: "auto", transform: "translateX(-50%)" },
];

/** Camada à vista no termograma e na lista: tudo, só as peças ou só os pontos quentes. */
function naCamada(r) {
  return naCamadaDe(estado.camada, r);
}
function naCamadaDe(camada, r) {
  if (camada === "pecas") return r.classe !== "ponto_quente";
  if (camada === "pontos") return r.classe === "ponto_quente";
  return true;
}

function desenharCaixas() {
  const s = $("#sobreposicao");
  s.replaceChildren();
  const { largura: W, altura: H } = estado.matriz;
  const pos = (n, x0, y0, x1, y1) =>
    Object.assign(n.style, { left: `${(x0 / W) * 100}%`, top: `${(y0 / H) * 100}%`, width: `${((x1 - x0) / W) * 100}%`, height: `${((y1 - y0) / H) * 100}%` });
  for (const r of estado.analise.regioes.filter(naCamada)) {
    const [x0, y0, x1, y1] = r.caixa;
    const cor = corNivel(r.severidade);
    const temperatura = fmt(r.medida && r.medida.t_max, 1, " °C");
    const completo = `${r.nome} · ${temperatura}`;
    const etq = el("span", { class: "etq", dataset: { completo, curto: temperatura } }, el("i", { style: { background: cor } }), completo);
    const caixa = el("div", {
      class: `caixa${r.id === estado.selecionada ? " selecionada" : ""}`,
      dataset: { id: r.id, severidade: r.severidade, area: String((x1 - x0) * (y1 - y0)) },
      title: completo,
      style: { borderColor: cor },
      onmousedown: (ev) => { if (estado.ferramenta === "selecionar") ev.stopPropagation(); },
      onclick: (ev) => { if (estado.ferramenta !== "selecionar") return; ev.stopPropagation(); selecionar(r.id); },
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
  const pq = estado.analise.resumo && estado.analise.resumo.ponto_mais_quente;
  if (pq) {
    // O ponto mais quente da cena ganha um alvo próprio, maior que o ponto de máxima de cada caixa.
    const alvo = el("span", { class: "alvo-maximo", title: T.analise.pqImagem(fmt(pq.t_max, 1, " °C"), pq.componente && pq.componente.nome) });
    Object.assign(alvo.style, { left: `${((pq.x + 0.5) / W) * 100}%`, top: `${((pq.y + 0.5) / H) * 100}%` });
    s.append(alvo);
  }
  desenharMedicoes(s);
  evitarColisaoDeEtiquetas(s);
}

function evitarColisaoDeEtiquetas(s) {
  // Nenhuma etiqueta cobre outra, um ponto de máxima ou o alvo do ponto mais quente, nem sai da imagem.
  // Cada uma tenta os seis lugares com o texto completo e depois só com a temperatura; sem lugar livre,
  // some (o nome continua na lista e no balão da caixa). A da região selecionada aparece sempre, primeiro.
  const area = s.getBoundingClientRect();
  const cabe = (r) => r.left >= area.left - 1 && r.right <= area.right + 1 && r.top >= area.top - 1 && r.bottom <= area.bottom + 1;
  const colide = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
  const ocupadas = $$(".caixa .pico, .alvo-maximo, .mira, .marca-linha", s).map((p) => p.getBoundingClientRect());
  // Pontos e linhas foram pedidos pelo usuário: os rótulos deles escolhem lugar primeiro.
  for (const etq of $$(".etq-med", s)) {
    etq.hidden = false;
    let livre = null;
    for (const posicao of POSICOES_MEDICAO) {
      Object.assign(etq.style, posicao);
      const r = etq.getBoundingClientRect();
      if (cabe(r) && !ocupadas.some((o) => colide(r, o))) {
        livre = r;
        break;
      }
    }
    etq.hidden = !livre;
    if (livre) ocupadas.push(livre);
  }
  const ordem = (etq) => {
    const c = etq.parentElement;
    return [c.classList.contains("selecionada") ? 0 : 1, -NIVEIS.indexOf(c.dataset.severidade), Number(c.dataset.area)];
  };
  const etiquetas = $$(".caixa .etq", s).sort((a, b) => {
    const [x, y] = [ordem(a), ordem(b)];
    return x[0] - y[0] || x[1] - y[1] || x[2] - y[2];
  });
  for (const etq of etiquetas) {
    const selecionada = etq.parentElement.classList.contains("selecionada");
    if (!estado.rotulos && !selecionada) {
      etq.hidden = true;
      continue;
    }
    etq.hidden = false;
    let livre = null;
    for (const texto of [etq.dataset.completo, etq.dataset.curto]) {
      etq.lastChild.textContent = texto;
      for (const posicao of POSICOES_ETIQUETA) {
        Object.assign(etq.style, posicao);
        const r = etq.getBoundingClientRect();
        if (cabe(r) && !ocupadas.some((o) => colide(r, o))) {
          livre = r;
          break;
        }
      }
      if (livre) break;
    }
    if (!livre && selecionada) {
      etq.lastChild.textContent = etq.dataset.completo;
      Object.assign(etq.style, POSICOES_ETIQUETA[0]);
      livre = etq.getBoundingClientRect();
    }
    etq.hidden = !livre;
    if (livre) ocupadas.push(livre);
  }
}

/** Mostra o seletor de camadas só quando a análise tem peças e pontos quentes juntos. */
function prepararCamadas() {
  const regioes = (estado.analise && estado.analise.regioes) || [];
  const pontos = regioes.some((r) => r.classe === "ponto_quente");
  const pecas = regioes.some((r) => r.classe !== "ponto_quente");
  const ambos = pontos && pecas;
  $("#seg-camada").hidden = !ambos;
  $("#divisor-camada").hidden = !ambos;
  if (!ambos) estado.camada = "tudo";
  marcarSegmentado("#seg-camada", estado.camada);
  $("#btn-rotulos").setAttribute("aria-pressed", String(estado.rotulos));
}

function trocarCamada(camada) {
  estado.camada = camada;
  marcarSegmentado("#seg-camada", camada);
  if (estado.selecionada && !estado.analise.regioes.some((r) => r.id === estado.selecionada && naCamada(r))) estado.selecionada = null;
  desenharCaixas();
  preencherResultado();
}

function alternarRotulos() {
  estado.rotulos = !estado.rotulos;
  guardarPreferencia("rotulos", estado.rotulos ? "sim" : "nao");
  $("#btn-rotulos").setAttribute("aria-pressed", String(estado.rotulos));
  desenharCaixas();
}

function selecionar(id, rolar = true) {
  const r = estado.analise.regioes.find((x) => x.id === id);
  if (r && !naCamada(r)) {
    // Quem pede para ver uma região escondida pela camada quer vê-la: volta a mostrar tudo.
    estado.camada = "tudo";
    marcarSegmentado("#seg-camada", "tudo");
    preencherResultado();
  }
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
  $("#veredito-titulo").textContent = r.severidade_rotulo + (indicativa && r.severidade !== "normal" ? T.analise.indicativa : "");
  $("#veredito-texto").textContent = r.mensagem;
  $("#k-max").textContent = fmt(r.t_max_cena, 1, " °C");
  if (r.maior_pct_mta != null) {
    $("#k-dt-rotulo").textContent = T.analise.maisPertoMta;
    $("#k-dt").textContent = `${fmt(r.maior_pct_mta, 0)}%`;
  } else {
    const dts = a.regioes.filter((x) => x.ref_tipo === "semelhantes").map((x) => x.dt_corrigido);
    $("#k-dt-rotulo").textContent = T.analise.maiorDt;
    $("#k-dt").textContent = dts.length ? fmt(Math.max(...dts), 1, " °C") : T.geral.semValor;
  }
  $("#k-regioes").textContent = String(r.regioes);
  $("#avisos").replaceChildren(...(r.avisos || []).map((t) => el("li", {}, icone("info"), el("span", {}, t))));
  $("#criterio-nome").textContent = r.criterio;
  desenharPontoMaisQuente(a);
  desenharComparacaoComponentes(a);

  const lista = $("#regioes");
  if (!a.regioes.length) {
    lista.replaceChildren(el("div", { class: "regioes-vazio" }, T.analise.semRegioes));
    return;
  }
  const [lo, hi] = faixaAtual();
  const classes = [...new Set([...(a.modelo.classes || []), ...CLASSES_PADRAO, ...a.regioes.map((x) => x.classe)])];
  const visiveis = a.regioes.filter(naCamada);
  const filtro = visiveis.length < a.regioes.length
    ? el("div", { class: "regioes-filtro" },
      el("span", {}, T.analise.mostrandoCamada(visiveis.length, a.regioes.length, T.analise.camadas[estado.camada])),
      el("button", { class: "btn btn-sm btn-fantasma", type: "button", onclick: () => trocarCamada("tudo") }, T.analise.mostrarTudo))
    : null;
  lista.replaceChildren(
    ...(filtro ? [filtro] : []),
    ...visiveis.map((x) => {
      const cor = corNivel(x.severidade);
      const m = x.medida || {};
      const ref = x.referencia || {};
      const nome = el("input", { class: "nome", value: x.nome, "aria-label": T.analise.nomeRegiao, onchange: (ev) => atualizarRegiao(x.id, { nome: ev.target.value }) });
      const sel = el("select", { "aria-label": T.analise.classe, onchange: (ev) => atualizarRegiao(x.id, { classe: ev.target.value }) }, classes.map((c) => new Option(nomeClasse(c), c)));
      sel.value = x.classe;
      const partes = [];
      if (x.pct_mta != null) {
        const mta = `MTA ${fmt(ref.mta_c, 0)} °C`;
        if (x.avaliacao_absoluta === "completa") partes.push(T.analise.plenaCarga(fmt(x.t_projetada, 1), mta));
        else if (x.avaliacao_absoluta === "sem_carga") partes.push(T.analise.semCarga(mta));
        else partes.push(T.analise.semProjecao(mta));
      }
      if (x.ref_tipo === "semelhantes") partes.push(T.analise.dtFases(fmt(x.dt_corrigido, 1, " °C")));
      if (x.carga_limite) partes.push(x.carga_limite.pct_nominal != null ? T.analise.atingeMtaCarga(fmt(x.carga_limite.pct_nominal, 0)) : T.analise.atingeMtaCorrente(fmt(x.carga_limite.vezes_corrente_atual, 1)));
      if (ref.aquecimento === "dieletrico" && x.ref_tipo !== "semelhantes") partes.push(T.analise.compararFases);
      if (x.classe === "ponto_quente" && "componente" in x) partes.unshift(x.componente ? T.analise.naPeca(x.componente.nome) : T.analise.foraDePeca);
      if (x.confianca != null) partes.push(T.analise.confianca(fmt(x.confianca * 100, 0)));
      const medidaSecundaria = x.pct_mta != null ? T.analise.pctMta(fmt(x.pct_mta, 0)) : x.ref_tipo === "semelhantes" ? `ΔT ${fmt(x.dt_corrigido, 1, " °C")}` : x.dt_entorno != null ? T.analise.noEntorno(fmt(x.dt_entorno, 1)) : "";
      // A barra vai até a MTA (o limite do componente); sem MTA, até o topo da escala da imagem.
      const largura = x.pct_mta != null ? Math.min(100, Math.max(3, x.pct_mta)) : m.t_max != null ? Math.min(100, Math.max(3, ((m.t_max - lo) / Math.max(hi - lo, 1e-6)) * 100)) : 0;
      const tituloBarra = x.pct_mta != null ? T.analise.tituloBarraMta(fmt(x.t_projetada, 1), fmt(ref.mta_c, 0), ref.fonte || "") : T.analise.tituloBarraEscala;
      const remover = el("button", { class: "btn btn-sm btn-fantasma btn-icone remover", type: "button", title: T.analise.removerTitulo, "aria-label": T.analise.remover(x.nome), onclick: (ev) => { ev.stopPropagation(); removerRegiao(x.id); } }, icone("lixo"));
      const porque = x.criterio_disparo ? T.analise.criterio(x.criterio_disparo.join(" e ")) : "";
      const selo = el("span", { class: `selo ${x.severidade}${x.indicativa ? " indicativa" : ""}`, title: `${x.severidade_rotulo}.${porque} ${x.acao}${x.indicativa ? T.analise.indicativaDica : ""}` }, T.niveis[x.severidade]);
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

/** Onde está o ponto mais quente da cena e em qual peça. */
function desenharPontoMaisQuente(a) {
  const alvo = $("#ponto-maximo");
  const p = a.resumo.ponto_mais_quente;
  alvo.hidden = !p;
  if (!p) return;
  const A = T.analise;
  const temPecas = a.regioes.some((x) => x.classe !== "ponto_quente");
  const onde = p.componente ? A.pqEm(p.componente.nome) : temPecas ? A.pqForaDePeca : "";
  const dentro = p.dentro_de && p.dentro_de.length ? A.pqDentroDe(p.dentro_de.map((c) => c.nome).join(", ")) : "";
  const fora = p.mais_quente_fora;
  alvo.replaceChildren(
    el("span", { class: "faixa", style: { background: corNivel(p.severidade) } }),
    el("div", { class: "corpo" },
      el("span", { class: "rotulo" }, temPecas ? A.pqTituloPecas : A.pqTitulo),
      el("b", { class: "num" }, fmt(p.t_max, 1, " °C")),
      onde ? el("p", {}, onde, dentro ? el("span", { class: "nota" }, ` ${dentro}`) : null) : null,
      fora ? el("button", { class: "link-fora", type: "button", onclick: () => selecionar(fora.regiao.id) }, A.pqFora(fora.regiao.nome, fmt(fora.t_max, 1, " °C"))) : null),
    p.regiao && p.regiao.id ? el("button", { class: "btn btn-sm", type: "button", onclick: () => selecionar(p.regiao.id) }, icone("busca"), A.pqVer) : null);
}

/** Peças do mesmo tipo lado a lado: Tmáx de cada uma e a diferença para a referência dos semelhantes. */
function desenharComparacaoComponentes(a) {
  const alvo = $("#comparacao-componentes");
  const grupos = a.resumo.comparacao_componentes || [];
  alvo.hidden = !grupos.length;
  if (!grupos.length) return;
  const A = T.analise;
  const [lo, hi] = faixaAtual();
  alvo.replaceChildren(
    el("h3", {}, A.compTitulo),
    el("p", { class: "nota" }, A.compNota),
    ...grupos.map((g) => el("div", { class: "comp-grupo" },
      el("div", { class: "comp-cabeca" }, el("b", {}, nomeClasse(g.classe, a.modelo)),
        el("span", { class: "nota" }, g.amplitude_c != null ? A.compAmplitude(fmt(g.amplitude_c, 1)) : A.compSozinho)),
      el("table", { class: "tabela tabela-comp" },
        el("tbody", {}, g.itens.map((i) => el("tr", { class: "clicavel", onclick: () => selecionar(i.id) },
          el("td", {}, i.nome),
          el("td", { class: "barra-celula" }, el("span", { class: "barra-classe" },
            el("i", { style: { width: `${Math.min(100, Math.max(3, ((i.t_max - lo) / Math.max(hi - lo, 1e-6)) * 100))}%`, background: corNivel(i.severidade) } }))),
          el("td", { class: "num direita" }, fmt(i.t_max, 1, " °C")),
          el("td", { class: `num direita${i.dt != null && i.dt > 0 ? " acima" : ""}` },
            i.dt != null ? `${i.dt > 0 ? "+" : ""}${fmt(i.dt, 1, " °C")}` : T.geral.semValor))))))));
}

function preencherCondicoes() {
  const a = estado.analise;
  $("#c-ambiente").value = a.condicoes.ambiente_c ?? "";
  $("#c-carga").value = a.condicoes.carga_pct ?? "";
  const m = a.metadados;
  const M = T.analise.meta;
  const pares = [
    [M.origem, a.radiometrica ? M.medida : M.estimada],
    [M.camera, m.camera],
    [M.emissividade, m.emissividade != null ? fmt(m.emissividade, 2) : null],
    [M.distancia, m.distancia_m != null ? fmt(m.distancia_m, 1, " m") : null],
    [M.refletida, m.temp_refletida_c != null ? fmt(m.temp_refletida_c, 1, " °C") : null],
    [M.umidade, m.umidade_relativa != null ? fmt(m.umidade_relativa * 100, 0, " %") : null],
    [M.sensor, m.resolucao_sensor],
    [M.escala, m.escala_lida_c ? `${fmt(m.escala_lida_c[0])} a ${fmt(m.escala_lida_c[1], 1, " °C")}` : null],
  ].filter(([, v]) => v);
  $("#meta").replaceChildren(...pares.map(([k, v]) => el("div", {}, el("dt", {}, k), el("dd", {}, v))));
}

function preencherLaudo() {
  const i = estado.analise.identificacao || {};
  $("#i-instalacao").value = i.instalacao || "";
  $("#i-equipamento").value = i.equipamento || "";
  $("#i-art").value = i.art || "";
  $("#i-observacoes").value = i.observacoes || "";
  const sel = $("#i-responsavel");
  obterConfig().then((cfg) => {
    const lista = cfg.responsaveis || [];
    sel.replaceChildren(...(lista.length ? lista.map((r) => new Option(`${r.nome} · ${r.registro}`, r.id)) : [new Option(T.laudo.semResponsavelTitulo, "")]));
    sel.disabled = !lista.length;
    const atual = lista.some((r) => r.id === i.responsavel_id) ? i.responsavel_id : cfg.responsavel_padrao;
    if (atual) sel.value = atual;
  }).catch(() => {});
}

function trocarAba(nome, animar = true) {
  $$(".inspetor .abas [role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.aba === nome)));
  $$(".painel-aba").forEach((p) => {
    const ativa = p.dataset.painel === nome;
    const mudou = p.hidden === ativa;
    p.hidden = !ativa;
    if (ativa && mudou && animar) {
      p.classList.remove("entrando");
      void p.offsetWidth;
      p.classList.add("entrando");
    }
  });
}

function definirFerramenta(nome) {
  estado.ferramenta = nome;
  marcarSegmentado("#seg-ferramenta", nome);
  $("#sobreposicao").classList.toggle("desenhando", nome === "desenhar");
  $("#sobreposicao").classList.toggle("medindo", nome === "ponto" || nome === "linha");
  const dica = { desenhar: T.analise.dicaRegiao, ponto: T.analise.dicaPonto, linha: T.analise.dicaLinha }[nome];
  $("#dica-desenho").hidden = !dica;
  if (dica) $("#dica-desenho").textContent = dica;
  if (nome !== "desenhar") estado.rascunho = null;
  if (nome !== "linha" && estado.rascunhoLinha) {
    estado.rascunhoLinha = null;
    if (estado.analise && estado.matriz) desenharCaixas();
  }
}

// ================================================================= pontos, linhas, escala manual, parâmetros e exportação

/** Paleta e escala manual ficam guardadas na inspeção: o laudo e a imagem exportada saem como a tela. */
let temporizadorExibicao = null;
function salvarExibicao() {
  const a = estado.analise;
  if (!a) return;
  const exibicao = { paleta: estado.paleta, faixa: estado.faixa === "manual" ? estado.faixaManual : null };
  a.exibicao = exibicao;
  clearTimeout(temporizadorExibicao);
  const id = a.id;
  temporizadorExibicao = setTimeout(() => api(`/api/analises/${id}`, json("PUT", { exibicao })).catch(falhou), 700);
}

function restaurarExibicao(a) {
  const ex = a.exibicao || {};
  if (ex.paleta && estado.paletas && estado.paletas[ex.paleta]) estado.paleta = ex.paleta;
  marcarSegmentado("#seg-paleta", estado.paleta);
  estado.faixaManual = ex.faixa || null;
  if (ex.faixa) estado.faixa = "manual";
  else if (estado.faixa === "manual") estado.faixa = "equipamento";
  marcarSegmentado("#seg-faixa", estado.faixa);
  preencherEscalaManual();
}

function preencherEscalaManual() {
  $("#escala-controle").hidden = estado.faixa !== "manual";
  if (estado.faixa !== "manual" || !estado.analise) return;
  const [lo, hi] = faixaAtual();
  $("#escala-min").value = Math.round(lo * 10) / 10;
  $("#escala-max").value = Math.round(hi * 10) / 10;
}

function trocarFaixa(v) {
  if (v === "manual" && !estado.faixaManual) {
    const [lo, hi] = estado.analise.matriz_info.faixa_exibicao;
    estado.faixaManual = [Math.floor(lo), Math.ceil(hi)];
  }
  estado.faixa = v;
  marcarSegmentado("#seg-faixa", v);
  preencherEscalaManual();
  desenharTermograma();
  preencherResultado();
  salvarExibicao();
}

function lerEscalaManual() {
  const lo = Number($("#escala-min").value), hi = Number($("#escala-max").value);
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi - lo < 0.1) return avisar(T.analise.escalaInvalida, { erro: true });
  estado.faixaManual = [lo, hi];
  desenharTermograma();
  preencherResultado();
  salvarExibicao();
}

// ---------------------------------------------------------------- pontos e linhas

function salvarMedicoes(lista) {
  const envio = lista.map(({ id, tipo, x, y, x0, y0, x1, y1 }) => ({ id, tipo, x, y, x0, y0, x1, y1 }));
  return api(`/api/analises/${estado.analise.id}`, json("PUT", { medicoes: envio })).then((a) => abrirAnalise(a)).catch(falhou);
}

function adicionarMedicao(m) {
  salvarMedicoes([...(estado.analise.medicoes || []), m]);
}

function removerMedicao(id) {
  salvarMedicoes((estado.analise.medicoes || []).filter((m) => m.id !== id));
}

/** Miras dos pontos e linhas sobre o termograma; a linha em SVG estica junto com a imagem. */
function desenharMedicoes(s) {
  const { largura: W, altura: H } = estado.matriz;
  const svg = $("#camada-linhas");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.replaceChildren();
  const pct = (v, total) => `${((v + 0.5) / total) * 100}%`;
  const rotulo = (texto) => el("span", { class: "etq-med" }, texto);
  for (const m of estado.analise.medicoes || []) {
    const v = m.valor || {};
    if (m.tipo === "ponto") {
      const texto = v.t != null ? `${m.nome} · ${fmt(v.t, 1, " °C")}` : m.nome;
      s.append(el("div", { class: "mira", title: texto, style: { left: pct(m.x, W), top: pct(m.y, H) }, onclick: (ev) => { ev.stopPropagation(); focarMedicao(m.id); } }, rotulo(texto)));
    } else {
      svg.append(svgEl("line", { x1: m.x0 + 0.5, y1: m.y0 + 0.5, x2: m.x1 + 0.5, y2: m.y1 + 0.5, class: "linha-medicao" }));
      for (const [x, y] of [[m.x0, m.y0], [m.x1, m.y1]]) s.append(el("span", { class: "ponta-linha", style: { left: pct(x, W), top: pct(y, H) } }));
      const texto = v.t_max != null ? `${m.nome} · máx ${fmt(v.t_max, 1, " °C")}` : m.nome;
      const mx = v.x_max ?? (m.x0 + m.x1) / 2, my = v.y_max ?? (m.y0 + m.y1) / 2;
      s.append(el("div", { class: "marca-linha", title: texto, style: { left: pct(mx, W), top: pct(my, H) }, onclick: (ev) => { ev.stopPropagation(); focarMedicao(m.id); } }, rotulo(texto)));
    }
  }
  const r = estado.rascunhoLinha;
  if (r) svg.append(svgEl("line", { x1: r.x0, y1: r.y0, x2: r.x1, y2: r.y1, class: "linha-medicao rascunho" }));
}

function focarMedicao(id) {
  trocarAba("resultado");
  const n = $(`.medicao[data-id="${id}"]`);
  if (!n) return;
  n.scrollIntoView({ block: "nearest", behavior: "smooth" });
  n.classList.remove("piscar");
  void n.offsetWidth;
  n.classList.add("piscar");
}

/** Perfil da linha: temperatura em cada pixel percorrido, com a máxima marcada. */
function graficoPerfil(valores) {
  const pts = (valores || []).map((v, i) => [i, v]).filter(([, v]) => v != null);
  if (pts.length < 2) return null;
  const L = 320, A = 84, m = { e: 30, d: 6, t: 8, b: 14 };
  const vs = pts.map((p) => p[1]);
  const lo = Math.min(...vs), hi = Math.max(...vs) + 1e-6;
  const n = valores.length - 1;
  const x = (i) => m.e + (i / n) * (L - m.e - m.d);
  const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (A - m.t - m.b);
  const imax = pts.reduce((a, p) => (p[1] > a[1] ? p : a))[0];
  return svgEl("svg", { viewBox: `0 0 ${L} ${A}`, class: "grafico-svg perfil", role: "img", "aria-label": T.analise.perfilTitulo },
    svgEl("line", { x1: m.e, x2: L - m.d, y1: y(hi), y2: y(hi), class: "grade" }),
    svgEl("line", { x1: m.e, x2: L - m.d, y1: y(lo), y2: y(lo), class: "grade" }),
    svgEl("text", { x: m.e - 4, y: y(hi) + 4, class: "eixo", "text-anchor": "end" }, fmt(hi, 0)),
    svgEl("text", { x: m.e - 4, y: y(lo) + 4, class: "eixo", "text-anchor": "end" }, fmt(lo, 0)),
    svgEl("path", { d: pts.map(([i, v], k) => `${k ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" "), class: "linha", style: "stroke: var(--serie-1)" }),
    svgEl("circle", { cx: x(imax), cy: y(hi), r: 3.5, style: "fill: var(--imediato)" }));
}

function preencherMedicoes() {
  const lista = estado.analise.medicoes || [];
  const A = T.analise;
  const alvo = $("#medicoes");
  if (!lista.length) return alvo.replaceChildren(el("p", { class: "nota" }, A.medVazio));
  alvo.replaceChildren(...lista.map((m) => {
    const v = m.valor || {};
    const remover = el("button", { class: "btn btn-sm btn-fantasma btn-icone", type: "button", title: A.medRemover, "aria-label": `${A.medRemover} ${m.nome}`, onclick: () => removerMedicao(m.id) }, icone("lixo"));
    if (m.tipo === "ponto") {
      return el("div", { class: "medicao", dataset: { id: m.id } }, icone("mira"), el("b", {}, m.nome),
        el("span", { class: "num" }, fmt(v.t, 1, " °C")), remover);
    }
    return el("div", { class: "medicao medicao-linha", dataset: { id: m.id } }, icone("linha"), el("b", {}, m.nome),
      el("span", { class: "num" }, A.medLinha(fmt(v.t_max, 1), fmt(v.t_min, 1), fmt(v.t_med, 1))), remover,
      graficoPerfil(v.valores));
  }));
}

// ---------------------------------------------------------------- parâmetros de medição (radiométrica)

function preencherParametros() {
  const a = estado.analise;
  const f = $("#form-parametros");
  f.hidden = !a.radiometrica;
  if (!a.radiometrica) return;
  const m = a.metadados || {};
  $("#p-emissividade").value = m.emissividade ?? "";
  $("#p-refletida").value = m.temp_refletida_c ?? "";
  $("#p-distancia").value = m.distancia_m ?? "";
  $("#p-umidade").value = m.umidade_relativa != null ? Math.round(m.umidade_relativa * 100) : "";
  $("#p-ar").value = m.temp_atmosfera_c ?? "";
  $("#p-material").value = "";
  $("#btn-parametros-camera").hidden = !(a.parametros_ajustados && a.parametros_ajustados.length);
}

async function aplicarParametros(corpo, botao, mensagem) {
  ocupado(botao, true);
  try {
    abrirAnalise(await api(`/api/analises/${estado.analise.id}/parametros`, json("POST", corpo)));
    avisar(mensagem);
  } catch (e) {
    falhou(e);
  } finally {
    ocupado(botao, false);
  }
}

// ---------------------------------------------------------------- menu suspenso (exportar)

function fecharMenu() {
  const m = $(".menu-suspenso");
  if (m) m.remove();
  document.removeEventListener("click", fecharMenuFora, true);
}
function fecharMenuFora(ev) {
  if (!ev.target.closest(".menu-suspenso")) fecharMenu();
}

/** Menu de ações curto, ancorado num botão. itens: [{rotulo, icone, href?, acao?}] */
function abrirMenu(botao, itens) {
  if ($(".menu-suspenso")) return fecharMenu();
  const menu = el("div", { class: "menu-suspenso", role: "menu" }, itens.map((it) => el(it.href ? "a" : "button", {
    class: "item-menu", role: "menuitem", href: it.href || null, download: it.href ? "" : null, type: it.href ? null : "button",
    onclick: () => { setTimeout(fecharMenu); if (it.acao) it.acao(); },
  }, icone(it.icone), el("span", {}, it.rotulo, it.nota ? el("small", {}, it.nota) : null))));
  document.body.append(menu);
  const r = botao.getBoundingClientRect();
  menu.style.top = `${r.bottom + 6}px`;
  menu.style.left = `${Math.max(8, Math.min(r.right - menu.offsetWidth, window.innerWidth - menu.offsetWidth - 8))}px`;
  setTimeout(() => document.addEventListener("click", fecharMenuFora, true));
  $(".item-menu", menu).focus();
}

function menuExportar(botao) {
  const a = estado.analise;
  const A = T.analise;
  abrirMenu(botao, [
    { rotulo: A.exportarImagem, nota: A.exportarImagemNota, icone: "foto", href: `/api/analises/${a.id}/imagem.png` },
    { rotulo: A.exportarCsv, nota: A.exportarCsvNota, icone: "tabela", href: `/api/analises/${a.id}/temperaturas.csv` },
    { rotulo: A.exportarLaudo, nota: A.exportarLaudoNota, icone: "laudo", acao: () => $("#btn-laudo").click() },
  ]);
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
  avisar(T.analise.removida(alvo && alvo.nome), { acao: { rotulo: T.geral.desfazer, executar: () => salvarRegioes(antes) } });
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
    if (!estado.matriz || !estado.analise) return;
    const { x, y, px, py } = coordenadas(ev);
    const { largura: W, altura: H, valores } = estado.matriz;
    const v = valores[Math.min(H - 1, Math.floor(y)) * W + Math.min(W - 1, Math.floor(x))];
    leitura.textContent = Number.isFinite(v) ? fmt(v, 1, " °C") : T.analise.semMedida;
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
    if (estado.rascunhoLinha) {
      estado.rascunhoLinha.x1 = x;
      estado.rascunhoLinha.y1 = y;
      desenharMedicoes(s);
    }
  });
  s.addEventListener("mouseleave", () => {
    leitura.hidden = true;
    marca.hidden = true;
  });
  s.addEventListener("mousedown", (ev) => {
    if (ev.button !== 0 || !["desenhar", "linha"].includes(estado.ferramenta)) return;
    ev.preventDefault();
    const { x, y } = coordenadas(ev);
    if (estado.ferramenta === "linha") estado.rascunhoLinha = { x0: x, y0: y, x1: x, y1: y };
    else estado.rascunho = { x0: x, y0: y, x1: x, y1: y };
  });
  s.addEventListener("click", (ev) => {
    if (estado.ferramenta === "ponto" && estado.matriz) {
      const { x, y } = coordenadas(ev);
      return adicionarMedicao({ tipo: "ponto", x: Math.round(x * 100) / 100, y: Math.round(y * 100) / 100 });
    }
    if (estado.ferramenta === "selecionar" && estado.selecionada) selecionar(estado.selecionada, false);
  });
  window.addEventListener("mouseup", () => {
    const l = estado.rascunhoLinha;
    if (l) {
      estado.rascunhoLinha = null;
      const arred = (v) => Math.round(v * 100) / 100;
      if (Math.hypot(l.x1 - l.x0, l.y1 - l.y0) < 2) return desenharMedicoes(s);
      return adicionarMedicao({ tipo: "linha", x0: arred(l.x0), y0: arred(l.y0), x1: arred(l.x1), y1: arred(l.y1) });
    }
    const r = estado.rascunho;
    if (!r) return;
    estado.rascunho = null;
    const caixa = [Math.min(r.x0, r.x1), Math.min(r.y0, r.y1), Math.max(r.x0, r.x1), Math.max(r.y0, r.y1)].map((v) => Math.round(v * 100) / 100);
    if (caixa[2] - caixa[0] < 1.5 || caixa[3] - caixa[1] < 1.5) return desenharCaixas();
    const n = estado.analise.regioes.filter((x) => x.origem === "manual").length + 1;
    salvarRegioes([...estado.analise.regioes, { id: null, nome: T.analise.regiaoNova(n), classe: "componente", caixa, origem: "manual" }]);
  });
}

// ================================================================= inspeções

async function carregarInspecoes() {
  const alvo = $("#lista-inspecoes");
  marcarSegmentado("#seg-filtro", estado.filtro);
  marcarSegmentado("#seg-exibir", estado.exibir);
  $("#kpis-inspecoes").replaceChildren(...esqueleto.kpis(5).children);
  alvo.replaceChildren(esqueleto.tabela(6));
  try {
    estado.inspecoes = await api("/api/analises");
  } catch (e) {
    $("#kpis-inspecoes").replaceChildren();
    return alvo.replaceChildren(estadoErro(T.inspecoes.erroTitulo, e, carregarInspecoes));
  }
  atualizarContador();
  desenharInspecoes();
}

function desenharKpisInspecoes() {
  const conta = (niveis) => estado.inspecoes.filter((it) => niveis.includes(it.resumo.severidade)).length;
  const kpi = (rotulo, valor, filtro, cor) =>
    el("button", {
      class: "kpi-grande", type: "button", "aria-pressed": String(estado.filtro === filtro),
      onclick: () => { estado.filtro = filtro; marcarSegmentado("#seg-filtro", filtro); desenharInspecoes(); },
    }, el("span", {}, cor ? el("i", { class: "ponto", style: { background: `var(--${cor})`, boxShadow: "none" } }) : null, rotulo), el("b", {}, String(valor)));
  $("#kpis-inspecoes").replaceChildren(
    kpi(T.inspecoes.total, estado.inspecoes.length, "todas"),
    kpi(T.inspecoes.criticas, conta(["urgente", "imediato"]), "grave", "imediato"),
    kpi(T.inspecoes.programar, conta(["programar"]), "programar", "programar"),
    kpi(T.inspecoes.atencao, conta(["atencao"]), "atencao", "atencao"),
    kpi(T.inspecoes.normais, conta(["normal"]), "normal", "normal"),
  );
}

function desenharInspecoes() {
  const total = estado.inspecoes.length;
  $("#kpis-inspecoes").hidden = !total;
  $("#filtros-inspecoes").hidden = !total;
  const alvo = $("#lista-inspecoes");
  if (!total) {
    return alvo.replaceChildren(estadoVazio({
      titulo: T.inspecoes.vazioTitulo, texto: T.inspecoes.vazioTexto,
      acoes: [el("button", { class: "btn btn-primaria", type: "button", onclick: abrirArquivos }, icone("upload"), T.painel.analisar)],
    }));
  }
  desenharKpisInspecoes();
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
  const quando = (it) => it.data_captura || it.criado_em;
  if (estado.ordem === "recentes") itens = itens.slice().sort((a, b) => quando(b).localeCompare(quando(a)));
  if (estado.ordem === "graves") itens = itens.slice().sort((a, b) => NIVEIS.indexOf(b.resumo.severidade) - NIVEIS.indexOf(a.resumo.severidade));
  if (estado.ordem === "nome") itens = itens.slice().sort((a, b) => a.arquivo.localeCompare(b.arquivo));
  if (!itens.length) {
    return alvo.replaceChildren(estadoVazio({
      nomeIcone: "busca", titulo: T.inspecoes.nadaTitulo, texto: T.inspecoes.nadaTexto,
      acoes: [el("button", { class: "btn", type: "button", onclick: limparFiltros }, T.inspecoes.limpar)],
    }));
  }
  alvo.replaceChildren(estado.exibir === "grade" ? gradeInspecoes(itens) : tabelaInspecoes(itens));
  desenharBarraSelecao();
}

function limparFiltros() {
  estado.filtro = "todas";
  estado.busca = "";
  $("#busca").value = "";
  marcarSegmentado("#seg-filtro", "todas");
  desenharInspecoes();
}

async function apagarInspecao(it) {
  if (!(await confirmar(T.inspecoes.apagarTitulo, T.inspecoes.apagarTexto(it.arquivo), T.geral.apagar, true))) return;
  try {
    await api(`/api/analises/${it.id}`, { method: "DELETE" });
    if (estado.analise && estado.analise.id === it.id) estado.analise = null;
    avisar(T.inspecoes.apagada);
    carregarInspecoes();
  } catch (e) {
    falhou(e);
  }
}

// ================================================================= laudo (uma ou várias imagens)

async function obterConfig() {
  if (!estado.config) estado.config = await api("/api/configuracoes");
  return estado.config;
}

/** Relatório em PDF. Sem responsável válido informado, pergunta (só aceita quem está no cadastro). */
async function emitirRelatorio(ids, { responsavel = null, art = null } = {}) {
  let cfg;
  try {
    cfg = await obterConfig();
  } catch (e) {
    return falhou(e);
  }
  const lista = cfg.responsaveis || [];
  let escolhido = responsavel && lista.some((r) => r.id === responsavel) ? responsavel : null;
  let numeroArt = art || "";
  if (!escolhido) {
    if (!lista.length) {
      const r = await dialogo({ titulo: T.laudo.semResponsavelTitulo, conteudo: el("p", {}, T.laudo.semResponsavelTexto),
        acoes: [{ rotulo: T.geral.cancelar, valor: "" }, { rotulo: T.laudo.cadastrar, valor: "cadastrar", classe: "btn-primaria" }] });
      if (r === "cadastrar") location.hash = "configuracoes/identidade";
      return;
    }
    const sel = el("select", {}, lista.map((r) => new Option(`${r.nome} · ${r.registro}`, r.id)));
    sel.value = lista.some((r) => r.id === cfg.responsavel_padrao) ? cfg.responsavel_padrao : lista[0].id;
    const campoArt = el("input", { placeholder: T.laudo.artOpcional, autocomplete: "off", value: numeroArt });
    const r = await dialogo({
      titulo: ids.length > 1 ? T.laudo.tituloVarios(ids.length) : T.laudo.titulo,
      conteudo: el("div", { class: "form" }, ids.length > 1 ? el("p", { class: "nota" }, T.laudo.ordem) : null,
        el("label", {}, T.laudo.responsavel, sel), el("label", {}, T.laudo.art, campoArt)),
      acoes: [{ rotulo: T.geral.cancelar, valor: "" }, { rotulo: T.laudo.gerar, valor: "gerar", classe: "btn-primaria" }],
    });
    if (r !== "gerar") return;
    escolhido = sel.value;
    numeroArt = campoArt.value.trim();
  }
  // A janela abre já no clique: depois de esperar o servidor, o navegador a trataria como pop-up.
  const janela = window.open("", "_blank");
  if (janela) janela.document.title = T.laudo.gerando;
  try {
    const resp = await fetch("/api/laudos", json("POST", { ids, responsavel: escolhido, art: numeroArt }));
    if (!resp.ok) {
      const c = await resp.json().catch(() => ({}));
      throw new Error(c.erro || T.geral.erroServidor(resp.status));
    }
    const url = URL.createObjectURL(await resp.blob());
    if (janela) janela.location.href = url;
    else {
      const a = el("a", { href: url, download: "relatorio_termografico.pdf" });
      document.body.append(a);
      a.click();
      a.remove();
    }
    avisar(ids.length > 1 ? T.laudo.prontoVarios(ids.length) : T.laudo.pronto);
  } catch (e) {
    if (janela) janela.close();
    falhou(e);
  }
}

function alternarSelecao(id, marcado) {
  if (marcado) estado.selecao.add(id);
  else estado.selecao.delete(id);
  desenharBarraSelecao();
}

function desenharBarraSelecao() {
  const barra = $("#barra-selecao");
  const existentes = new Set(estado.inspecoes.map((it) => it.id));
  for (const id of [...estado.selecao]) if (!existentes.has(id)) estado.selecao.delete(id);
  const n = estado.selecao.size;
  barra.hidden = !n;
  if (!n) return;
  const ids = estado.inspecoes.filter((it) => estado.selecao.has(it.id)).map((it) => it.id);
  barra.replaceChildren(
    el("span", { class: "contagem" }, icone("check"), T.inspecoes.selecionadas(n)),
    el("div", { class: "acoes" },
      el("button", { class: "btn btn-fantasma btn-sm", type: "button", onclick: () => { estado.selecao.clear(); desenharInspecoes(); } }, T.inspecoes.limparSelecao),
      el("button", { class: "btn btn-sm", type: "button", onclick: () => definirEquipamento(ids) }, icone("ativos"), T.equip.definir),
      el("button", { class: "btn btn-primaria btn-sm", type: "button", onclick: () => emitirRelatorio(ids) }, icone("laudo"), T.inspecoes.gerarRelatorio(n))));
}

function caixaSelecao(it) {
  return el("input", {
    type: "checkbox", class: "marcar", checked: estado.selecao.has(it.id), "aria-label": T.inspecoes.marcar(it.arquivo),
    onclick: (ev) => ev.stopPropagation(),
    onchange: (ev) => { alternarSelecao(it.id, ev.target.checked); ev.target.closest(".inspecao, tr")?.classList.toggle("marcada", ev.target.checked); },
  });
}

function acoesInspecao(it) {
  const parar = (f) => (ev) => { ev.stopPropagation(); f(); };
  const ident = it.identificacao || {};
  return [
    el("button", { class: "btn btn-sm", type: "button", title: T.inspecoes.laudoTitulo, onclick: parar(() => emitirRelatorio([it.id], { responsavel: ident.responsavel_id, art: ident.art })) }, icone("laudo"), T.geral.laudo),
    el("button", { class: "btn btn-sm btn-fantasma btn-icone", type: "button", title: T.geral.apagar, "aria-label": T.inspecoes.rotuloApagar(it.arquivo), onclick: parar(() => apagarInspecao(it)) }, icone("lixo")),
  ];
}

function tabelaInspecoes(itens) {
  const linhas = itens.map((it) => {
    const ident = it.identificacao;
    const local = ident.equipamento
      ? el("div", { class: "principal-celula" },
        el("a", { class: "link-equip", href: `#equipamentos/${encodeURIComponent(it.equipamento_chave)}`, title: T.equip.chipTitulo, onclick: (ev) => ev.stopPropagation() }, icone("ativos"), ident.equipamento),
        el("span", {}, ident.instalacao || ""))
      : el("span", { class: "nota" }, T.inspecoes.semEquipamento);
    return el("tr", { class: `clicavel${estado.selecao.has(it.id) ? " marcada" : ""}`, tabindex: "0", onclick: () => abrirInspecao(it.id), onkeydown: (ev) => { if (ev.key === "Enter" && ev.target.tagName !== "INPUT") abrirInspecao(it.id); } },
      el("td", { class: "celula-marcar" }, caixaSelecao(it)),
      el("td", {}, el("img", { class: "miniatura-tabela", src: miniaturaSrc(it), alt: "", loading: "lazy" })),
      el("td", {}, el("div", { class: "principal-celula" },
        el("b", {}, it.arquivo),
        el("span", {}, [dataHora(it.data_captura || it.criado_em), it.fonte === "monitoramento" ? T.inspecoes.monitor : null, T.geral.regioes(it.resumo.regioes)].filter(Boolean).join(" · ")))),
      el("td", {}, local),
      el("td", { class: "num" }, valorDestaque(it.destaque) || T.geral.semValor),
      el("td", { class: "num direita" }, fmt(it.resumo.t_max_cena, 1, " °C")),
      el("td", {}, el("span", { class: `selo ${it.resumo.severidade}` }, T.niveis[it.resumo.severidade])),
      el("td", {}, el("div", { class: "acoes-linha" }, acoesInspecao(it))));
  });
  const todas = el("input", {
    type: "checkbox", class: "marcar", "aria-label": T.inspecoes.marcarTodas,
    checked: itens.length > 0 && itens.every((it) => estado.selecao.has(it.id)),
    onchange: (ev) => { for (const it of itens) (ev.target.checked ? estado.selecao.add(it.id) : estado.selecao.delete(it.id)); desenharInspecoes(); },
  });
  return el("div", { class: "cartao tabela-cartao" }, el("div", { class: "tabela-rolagem" },
    el("table", { class: "tabela" },
      el("thead", {}, el("tr", {}, el("th", { class: "celula-marcar" }, todas), T.inspecoes.colunas.map((c, i) => el("th", { class: i === 4 ? "direita" : null }, c)))),
      el("tbody", {}, animarEntrada(linhas)))));
}

function gradeInspecoes(itens) {
  const cartoes = itens.map((it) => {
    const local = [it.identificacao.instalacao, it.identificacao.equipamento].filter(Boolean).join(" · ");
    const imagem = el("img", { src: miniaturaSrc(it), alt: it.arquivo, loading: "lazy", style: { cursor: "pointer" }, onclick: () => abrirInspecao(it.id) });
    const legenda = el("span", { class: "legenda" },
      el("span", { class: "linha" }, el("b", {}, it.arquivo), el("span", { class: `selo ${it.resumo.severidade}` }, T.niveis[it.resumo.severidade])),
      el("span", {}, [dataHora(it.data_captura || it.criado_em), local || T.geral.regioes(it.resumo.regioes)].filter(Boolean).join(" · ")));
    const acoes = el("div", { class: "acoes-cartao" }, el("button", { class: "btn btn-sm", type: "button", onclick: () => abrirInspecao(it.id) }, T.geral.abrir), acoesInspecao(it));
    return el("div", { class: `inspecao miniatura${estado.selecao.has(it.id) ? " marcada" : ""}`, style: { cursor: "default" } },
      el("label", { class: "marcar-cartao" }, caixaSelecao(it)), imagem, legenda, acoes);
  });
  return el("div", { class: "grade-inspecoes" }, animarEntrada(cartoes));
}

// ================================================================= monitoramento

async function carregarMonitoramento() {
  $("#monitor-estado").replaceChildren(...Array.from({ length: 4 }, () => el("div", {}, el("div", { class: "esqueleto esq-linha" }), el("div", { class: "esqueleto esq-titulo" }))));
  $("#lista-alertas").replaceChildren(el("div", { style: { padding: "var(--e-5)" } }, esqueleto.linhas(3)));
  let dados, alertas, previa;
  try {
    [dados, alertas, previa] = await Promise.all([api("/api/monitoramento"), api("/api/alertas"), api("/api/monitoramento/previa")]);
  } catch (e) {
    $("#monitor-estado").replaceChildren(el("div", { style: { gridColumn: "1 / -1" } }, estadoErro(T.monitor.erroTitulo, e, carregarMonitoramento)));
    return;
  }
  estado.monitor = dados;
  const c = dados.config;
  $("#m-pasta").value = c.pasta || "";
  $("#m-intervalo").value = c.intervalo_s;
  $("#m-instalacao").value = c.instalacao || "";
  $("#m-equipamento").value = c.equipamento || "";
  $("#m-subpastas").checked = !!c.subpastas;
  $("#m-repetir").value = c.repetir_min;
  marcarSegmentado("#seg-minima", c.severidade_minima);
  $$('input[name="fonte"]').forEach((i) => (i.checked = i.value === c.fonte));
  $$('input[name="envio"]').forEach((i) => (i.checked = i.value === c.envio));
  desenharDestinatarios(c.destinatarios);
  desenharPrevia(previa);
  desenharEstadoMonitor(dados.estado, alertas.pendentes);
  desenharAlertas(alertas.alertas);
}

function desenharEstadoMonitor(m, pendentes) {
  const classe = m.erro && m.ativo ? "erro" : m.ativo ? "ativo" : "desligado";
  const rotulo = m.erro && m.ativo ? T.monitor.comErro : m.ativo ? T.monitor.vigiando : T.monitor.desligado;
  $("#monitor-estado").replaceChildren(
    el("div", {}, el("span", { class: "sobrerrotulo" }, T.monitor.estado), el("b", { class: "linha-estado" }, el("i", { class: `ponto ${classe}` }), rotulo), m.erro ? el("span", { class: "nota" }, m.erro) : null),
    el("div", {}, el("span", { class: "sobrerrotulo" }, T.monitor.pasta), el("b", { class: "caminho", title: m.pasta || "" }, m.pasta ? caminhoCurto(m.pasta) : T.monitor.semPasta)),
    el("div", {}, el("span", { class: "sobrerrotulo" }, T.monitor.ultimaVerificacao), el("b", { class: "num" }, m.ultima_verificacao ? hora(m.ultima_verificacao) : T.geral.semValor),
      m.ultima_imagem ? el("span", { class: "nota" }, T.monitor.ultimaImagem(m.ultima_imagem.arquivo)) : null),
    el("div", {}, el("span", { class: "sobrerrotulo" }, T.monitor.analisadas), el("b", { class: "num" }, String(m.analisadas || 0)), el("span", { class: "nota" }, T.monitor.alertasPendentes(pendentes || 0))));
  const botao = $("#btn-ligar-monitor");
  botao.classList.toggle("btn-primaria", !m.ativo);
  $("span", botao).textContent = m.ativo ? T.monitor.desligar : T.monitor.ligar;
}

function desenharDestinatarios(lista) {
  const alvo = $("#destinatarios");
  const linhas = (lista.length ? lista : []).map((d) => linhaDestinatario(d));
  alvo.replaceChildren(...linhas);
  if (!linhas.length) alvo.append(el("p", { class: "nota", id: "sem-destinatarios" }, T.monitor.semDestinatarios));
}

function linhaDestinatario(d = { nome: "", telefone: "" }) {
  const linha = el("div", { class: "destinatario" },
    el("label", {}, T.monitor.nome, el("input", { value: d.nome, "data-campo": "nome", autocomplete: "off" })),
    el("label", {}, T.monitor.telefone, el("input", { value: d.telefone, "data-campo": "telefone", inputmode: "tel", placeholder: T.monitor.telefoneExemplo, autocomplete: "off" })),
    el("button", { class: "btn btn-fantasma btn-icone", type: "button", "aria-label": T.monitor.removerDestinatario(d.nome), onclick: () => { linha.remove(); if (!$$(".destinatario").length) desenharDestinatarios([]); } }, icone("lixo")));
  return linha;
}

function lerMonitorDoFormulario() {
  return {
    fonte: ($('input[name="fonte"]:checked') || {}).value || "pasta",
    pasta: $("#m-pasta").value.trim(),
    intervalo_s: Number($("#m-intervalo").value || 10),
    instalacao: $("#m-instalacao").value,
    equipamento: $("#m-equipamento").value,
    subpastas: $("#m-subpastas").checked,
    severidade_minima: ($("#seg-minima button[aria-pressed='true']") || {}).dataset.valor || "urgente",
    repetir_min: Number($("#m-repetir").value || 0),
    destinatarios: $$(".destinatario").map((l) => ({ nome: $('[data-campo="nome"]', l).value, telefone: $('[data-campo="telefone"]', l).value })),
    envio: ($('input[name="envio"]:checked') || {}).value || "manual",
  };
}

function desenharPrevia(previa) {
  const alvo = $("#previa-mensagem");
  if (!previa || !previa.mensagem) return alvo.replaceChildren(el("p", { class: "nota" }, T.monitor.previaVazia));
  alvo.replaceChildren(el("div", { class: "bolha" }, previa.mensagem, el("span", { class: "bolha-rodape" }, T.monitor.previaRodape(previa.arquivo))));
}

async function salvarMonitor(parcial, mensagem, botao) {
  if (botao) ocupado(botao, true);
  try {
    const d = await api("/api/monitoramento", json("PUT", { ...lerMonitorDoFormulario(), ...parcial }));
    estado.monitor = d;
    desenharEstadoMonitor(d.estado, estado.alertasPendentes || 0);
    desenharDestinatarios(d.config.destinatarios);
    avisar(mensagem);
    atualizarStatus();
    return d;
  } catch (e) {
    falhou(e);
    return null;
  } finally {
    if (botao) ocupado(botao, false);
  }
}

function desenharAlertas(alertas) {
  const alvo = $("#lista-alertas");
  if (!alertas.length) {
    return alvo.replaceChildren(el("div", { style: { padding: "var(--e-5)" } },
      estadoVazio({ nomeIcone: "sino", titulo: T.monitor.alertasVazioTitulo, texto: T.monitor.alertasVazioTexto, compacto: true })));
  }
  const linhas = alertas.map((a) => {
    const local = [a.instalacao, a.equipamento].filter(Boolean).join(" · ");
    return el("tr", {},
      el("td", { class: "num" }, dataHora(a.criado_em)),
      el("td", {}, el("div", { class: "principal-celula" }, el("b", {}, a.arquivo), el("span", {}, local || T.geral.semValor))),
      el("td", {}, el("span", { class: `selo ${a.severidade}` }, T.niveis[a.severidade])),
      el("td", { style: { maxWidth: "var(--medida)" } }, el("span", { class: "nota" }, a.resumo)),
      el("td", {}, el("span", { class: `status-alerta ${a.status}` }, T.monitor.status[a.status])),
      el("td", {}, el("div", { class: "acoes-linha" },
        el("button", { class: "btn btn-sm", type: "button", onclick: () => enviarWhatsapp(a) }, icone("mensagem"), T.monitor.whatsapp),
        el("button", { class: "btn btn-sm", type: "button", onclick: () => abrirInspecao(a.analise_id) }, T.geral.abrir),
        a.status !== "resolvido" ? el("button", { class: "btn btn-sm btn-fantasma", type: "button", onclick: () => mudarStatusAlerta(a, "resolvido", T.monitor.resolvido) }, icone("check"), T.monitor.resolver) : null)));
  });
  alvo.replaceChildren(el("div", { class: "tabela-rolagem", style: { marginTop: "var(--e-4)" } },
    el("table", { class: "tabela" }, el("thead", {}, el("tr", {}, T.monitor.colunas.map((c) => el("th", {}, c)))), el("tbody", {}, animarEntrada(linhas)))));
}

async function mudarStatusAlerta(a, status, mensagem) {
  try {
    await api(`/api/alertas/${a.id}`, json("PUT", { status }));
    if (mensagem) avisar(mensagem);
    const alertas = await api("/api/alertas");
    desenharAlertas(alertas.alertas);
    atualizarStatus();
  } catch (e) {
    falhou(e);
  }
}

async function enviarWhatsapp(a) {
  let dados;
  try {
    dados = await api(`/api/alertas/${a.id}/whatsapp`);
  } catch (e) {
    return falhou(e);
  }
  const copiar = el("button", { class: "btn btn-sm", type: "button", onclick: async () => {
    try { await navigator.clipboard.writeText(dados.mensagem); avisar(T.geral.copiado); } catch { avisar(T.geral.naoCopiou, { erro: true }); }
  } }, icone("copiar"), T.monitor.copiarMensagem);
  const lista = dados.links.length
    ? el("ul", { class: "lista-links" }, dados.links.map((l) => el("li", {},
        el("div", { class: "principal-celula" }, el("b", {}, l.nome), el("span", { class: "num" }, l.telefone)),
        el("a", { class: "btn btn-sm btn-primaria", href: l.url, target: "_blank", rel: "noopener", onclick: () => mudarStatusAlerta(a, "enviado") }, icone("externo"), T.monitor.abrirWhatsapp))))
    : el("p", { class: "nota" }, T.monitor.dialogoSemDestinatarios);
  await dialogo({
    titulo: T.monitor.dialogoTitulo,
    conteudo: el("div", { class: "pilha" }, el("p", {}, T.monitor.dialogoTexto), el("div", { class: "bolha" }, dados.mensagem), lista, el("div", {}, copiar)),
    acoes: [{ rotulo: T.geral.fechar, valor: "fechar" }],
  });
}

// ================================================================= configurações

function desenharLogo(tem) {
  const previa = $("#logo-previa");
  previa.replaceChildren(tem ? el("img", { src: `/api/configuracoes/logo.png?t=${Date.now()}`, alt: T.config.logoAlt }) : icone("foto"));
  previa.classList.toggle("vazia", !tem);
  $("#btn-logo-remover").hidden = !tem;
  $("#btn-logo").lastChild.textContent = tem ? T.config.logoTrocar : T.config.logoEnviar;
}

async function carregarConfiguracoes(aba) {
  if (aba) estado.abaConfig = aba;
  mostrarAbaConfig(estado.abaConfig);
  let c;
  try {
    c = await api("/api/configuracoes");
  } catch (e) {
    return avisar(`${T.config.erroTitulo}: ${e.message}`, { erro: true });
  }
  estado.config = c;
  $("#cfg-empresa-nome").value = c.empresa.nome || "";
  $("#cfg-empresa-sub").value = c.empresa.subtitulo || "";
  desenharLogo(c.tem_logo);
  desenharResponsaveis(c.responsaveis || [], c.responsavel_padrao);
  aplicarTema(c.tema);
  $("#pasta-dados").textContent = c.pasta_dados;
  $("#pasta-modelos").textContent = c.pasta_modelos;
  $("#pasta-modelos-2").textContent = c.pasta_modelos;
  $("#versao-2").textContent = c.versao;
  preencherCriterio(c.criterio, c.criterio_personalizado);
  preencherComponentes(c.componentes, c.componentes_padrao);
}

function mostrarAbaConfig(aba) {
  const valida = $$("[data-secao-config]").some((s) => s.dataset.secaoConfig === aba) ? aba : "identidade";
  estado.abaConfig = valida;
  $$("[data-aba-config]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.abaConfig === valida)));
  $$("[data-secao-config]").forEach((s) => {
    const ativa = s.dataset.secaoConfig === valida;
    if (ativa && s.hidden) {
      s.classList.remove("entrando");
      void s.offsetWidth;
      s.classList.add("entrando");
    }
    s.hidden = !ativa;
  });
}

const GRUPOS_CRITERIO = { mta_faixas: "%", similares: "°C", dieletrico: "°C", ambiente: "°C" };
const NIVEIS_EDITAVEIS = ["atencao", "programar", "urgente", "imediato"];

function preencherCriterio(crit, personalizado) {
  for (const [grupo, unidade] of Object.entries(GRUPOS_CRITERIO)) {
    $(`#crit-${grupo}`).replaceChildren(
      ...NIVEIS_EDITAVEIS.map((nivel) => {
        const achado = (crit[grupo] || []).find(([, n]) => n === nivel);
        return el("div", { class: "crit-linha" },
          el("span", {}, el("span", { class: `selo ${nivel}` }, T.niveis[nivel]), T.config.aPartirDe),
          el("div", { class: "campo-unidade" },
            el("input", { type: "number", step: "0.1", min: "0", value: achado ? achado[0] : "", placeholder: T.config.naoUsar, dataset: { grupo, nivel }, "aria-label": T.config.limiteRotulo(T.niveis[nivel], unidade) }),
            el("span", {}, unidade)));
      }),
    );
  }
  $("#crit-usar-ambiente").checked = !!crit.usar_ambiente;
  $("#crit-ambiente").closest(".crit-grupo").classList.toggle("desligado", !crit.usar_ambiente);
  $("#crit-nome").value = crit.nome;
  $("#crit-expoente").value = crit.expoente_carga;
  $("#crit-carga").value = crit.carga_minima_pct;
  if (personalizado !== undefined) $("#criterio-estado").textContent = personalizado ? T.config.criterioPersonalizado : T.config.criterioPadrao;
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
        ? el("span", { class: "nota" }, T.config.naoSeAplica)
        : el("div", { class: "campo-unidade" }, el("input", { type: "number", step: "1", min: "20", max: "400", value: c.mta_c ?? "", dataset: { classe }, "aria-label": T.config.mtaRotulo(c.nome) }), el("span", {}, "°C"));
      return el("tr", { class: alterado ? "alterado" : "" },
        el("td", {}, el("div", { class: "principal-celula" }, el("b", {}, c.nome), el("span", {}, classe))),
        el("td", {}, el("span", { class: "aquecimento" }, T.aquecimento[c.aquecimento] || c.aquecimento)),
        el("td", {}, campo),
        el("td", {}, c.fonte));
    }),
  );
}

// Cadastro de responsáveis técnicos: o laudo só aceita quem está aqui.
const novoIdResponsavel = () => Math.random().toString(36).slice(2, 10);

function linhaResponsavel(r = { id: novoIdResponsavel(), nome: "", funcao: "", registro: "" }, padrao = false) {
  const C = T.config;
  const linha = el("div", { class: "responsavel-linha", dataset: { id: r.id } },
    el("label", { class: "padrao", title: C.respPadraoTitulo }, el("input", { type: "radio", name: "resp-padrao", value: r.id, checked: padrao }), C.respPadrao),
    el("label", {}, C.respNome, el("input", { value: r.nome, "data-campo": "nome", autocomplete: "off" })),
    el("label", {}, C.respFuncao, el("input", { value: r.funcao || "", "data-campo": "funcao", placeholder: C.respFuncaoExemplo, autocomplete: "off" })),
    el("label", {}, C.respRegistro, el("input", { value: r.registro, "data-campo": "registro", placeholder: C.respRegistroExemplo, autocomplete: "off" })),
    el("button", { class: "btn btn-fantasma btn-icone", type: "button", "aria-label": C.respRemover(r.nome), title: C.respRemover(r.nome), onclick: () => linha.remove() }, icone("lixo")));
  return linha;
}

function desenharResponsaveis(lista, padrao) {
  $("#lista-responsaveis").replaceChildren(...(lista.length ? lista.map((r) => linhaResponsavel(r, r.id === padrao)) : [linhaResponsavel(undefined, true)]));
}

function lerResponsaveis() {
  return $$("#lista-responsaveis .responsavel-linha").map((l) => ({
    id: l.dataset.id,
    nome: $("[data-campo=nome]", l).value.trim(),
    funcao: $("[data-campo=funcao]", l).value.trim(),
    registro: $("[data-campo=registro]", l).value.trim(),
  })).filter((r) => r.nome || r.registro);
}

async function salvarConfig(parcial, mensagem, botao) {
  if (botao) ocupado(botao, true);
  try {
    const c = await api("/api/configuracoes", json("PUT", parcial));
    estado.config = c;
    if (mensagem) avisar(mensagem);
    return c;
  } catch (e) {
    falhou(e);
    return null;
  } finally {
    if (botao) ocupado(botao, false);
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
    const arquivos = ev.dataTransfer ? [...ev.dataTransfer.files] : [];
    if (!arquivos.length || soltar.contains(ev.target)) return;
    // Um .zip solto na tela Modelos são rótulos do CVAT; na Avaliação, os resultados do Colab; imagens vão para análise.
    if (/\.(zip|json)$/i.test(arquivos[0].name) && estado.vista === "modelos") return enviarRotulos(arquivos);
    if (/\.zip$/i.test(arquivos[0].name) && estado.vista === "avaliacao") return importarAvaliacao(arquivos[0]);
    if (EXT_VIDEO.test(arquivos[0].name)) return enviarVideo(arquivos[0]);
    enviarArquivos(arquivos);
  });

  $("#btn-voltar").addEventListener("click", () => { location.hash = "analise"; });
  $("#btn-reconectar").addEventListener("click", () => { rota(); atualizarStatus(); });
  $("#btn-laudo").addEventListener("click", () => {
    const i = estado.analise.identificacao || {};
    emitirRelatorio([estado.analise.id], { responsavel: i.responsavel_id, art: i.art });
  });
  $("#btn-laudo-2").addEventListener("click", () => emitirRelatorio([estado.analise.id], { responsavel: $("#i-responsavel").value, art: $("#i-art").value.trim() }));
  $("#btn-detectar").addEventListener("click", async (ev) => {
    const botao = ev.currentTarget;
    ocupado(botao, true);
    try {
      const a = await api(`/api/analises/${estado.analise.id}/detectar`, json("POST", { modelo: $("#sel-modelo").value }));
      abrirAnalise(a);
      avisar(T.analise.detectado(a.modelo.nome));
    } catch (e) {
      falhou(e);
    } finally {
      ocupado(botao, false);
    }
  });

  segmentado("#seg-paleta", (v) => { estado.paleta = v; desenharTermograma(); salvarExibicao(); });
  segmentado("#seg-faixa", trocarFaixa);
  ["#escala-min", "#escala-max"].forEach((id) => $(id).addEventListener("change", lerEscalaManual));
  $("#btn-escala-auto").addEventListener("click", () => trocarFaixa("equipamento"));
  $("#btn-novo-ponto").addEventListener("click", () => definirFerramenta("ponto"));
  $("#btn-nova-linha").addEventListener("click", () => definirFerramenta("linha"));
  $("#btn-exportar").addEventListener("click", (ev) => menuExportar(ev.currentTarget));
  $("#p-material").addEventListener("change", (ev) => { if (ev.target.value) $("#p-emissividade").value = ev.target.value; });
  $("#form-parametros").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const umidade = $("#p-umidade").value;
    aplicarParametros({
      emissividade: $("#p-emissividade").value, temp_refletida_c: $("#p-refletida").value, distancia_m: $("#p-distancia").value,
      umidade_relativa: umidade === "" ? "" : Number(umidade) / 100, temp_atmosfera_c: $("#p-ar").value,
    }, $("button[type=submit]", ev.currentTarget), T.analise.parametrosAplicados(fmt(Number($("#p-emissividade").value), 2)));
  });
  $("#btn-parametros-camera").addEventListener("click", (ev) => aplicarParametros({ restaurar: true }, ev.currentTarget, T.analise.parametrosRestaurados));
  segmentado("#seg-ferramenta", definirFerramenta);
  segmentado("#seg-camada", trocarCamada);
  $("#btn-rotulos").addEventListener("click", alternarRotulos);
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
  $$(".inspetor .abas [role=tab]").forEach((b) => b.addEventListener("click", () => trocarAba(b.dataset.aba)));

  $("#form-condicoes").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const botao = $("button[type=submit]", ev.currentTarget);
    ocupado(botao, true);
    try {
      abrirAnalise(await api(`/api/analises/${estado.analise.id}`, json("PUT", { condicoes: { ambiente_c: $("#c-ambiente").value, carga_pct: $("#c-carga").value } })));
      trocarAba("resultado");
      avisar(T.analise.recalculado);
    } catch (e) {
      falhou(e);
    } finally {
      ocupado(botao, false);
    }
  });
  $("#form-laudo").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const identificacao = {
      instalacao: $("#i-instalacao").value, equipamento: $("#i-equipamento").value, responsavel_id: $("#i-responsavel").value,
      art: $("#i-art").value.trim(), observacoes: $("#i-observacoes").value,
    };
    try {
      abrirAnalise(await api(`/api/analises/${estado.analise.id}`, json("PUT", { identificacao })));
      estado.equipamentos = null;
      avisar(T.analise.laudoSalvo);
    } catch (e) {
      falhou(e);
    }
  });

  $("#busca").addEventListener("input", (ev) => { estado.busca = ev.target.value; desenharInspecoes(); });
  $("#busca-equip").addEventListener("input", (ev) => { estado.buscaEquip = ev.target.value; desenharEquipamentos(); });
  $("#busca-pendencias").addEventListener("input", (ev) => { estado.buscaPendencia = ev.target.value; desenharPendencias(); });
  segmentado("#seg-pendencias", (v) => { estado.filtroPendencia = v; desenharPendencias(); });
  segmentado("#seg-filtro", (v) => { estado.filtro = v; desenharInspecoes(); });
  segmentado("#seg-exibir", (v) => { estado.exibir = v; guardarPreferencia("exibir", v); desenharInspecoes(); });
  $("#ordem").addEventListener("change", (ev) => { estado.ordem = ev.target.value; desenharInspecoes(); });

  // monitoramento
  segmentado("#seg-minima", () => {});
  $("#btn-add-destinatario").addEventListener("click", () => {
    const vazio = $("#sem-destinatarios");
    if (vazio) vazio.remove();
    const linha = linhaDestinatario();
    $("#destinatarios").append(linha);
    $("input", linha).focus();
  });
  $("#form-monitor").addEventListener("submit", (ev) => {
    ev.preventDefault();
    salvarMonitor({}, T.monitor.salvo, $("button[type=submit]", ev.currentTarget));
  });
  $("#btn-ligar-monitor").addEventListener("click", (ev) => {
    const ligar = !(estado.monitor && estado.monitor.config.ativo);
    salvarMonitor({ ativo: ligar }, ligar ? T.monitor.ligado : T.monitor.desligadoAviso, ev.currentTarget);
  });
  $("#btn-verificar").addEventListener("click", async (ev) => {
    const botao = ev.currentTarget;
    ocupado(botao, true);
    try {
      await api("/api/monitoramento", json("PUT", lerMonitorDoFormulario()));
      const r = await api("/api/monitoramento/verificar", { method: "POST" });
      avisar(T.monitor.verificado(r.novas));
      carregarMonitoramento();
      atualizarStatus();
    } catch (e) {
      falhou(e);
    } finally {
      ocupado(botao, false);
    }
  });

  // configurações
  $$("[data-aba-config]").forEach((b) => b.addEventListener("click", () => {
    mostrarAbaConfig(b.dataset.abaConfig);
    history.replaceState(null, "", `#configuracoes/${b.dataset.abaConfig}`);
  }));
  $("#btn-logo").addEventListener("click", () => $("#arquivo-logo").click());
  $("#arquivo-logo").addEventListener("change", async (ev) => {
    const arquivo = ev.target.files[0];
    ev.target.value = "";
    if (!arquivo) return;
    const dados = new FormData();
    dados.append("arquivo", arquivo);
    try {
      await api("/api/configuracoes/logo", { method: "POST", body: dados });
      desenharLogo(true);
      avisar(T.config.logoSalvo);
    } catch (e) {
      falhou(e);
    }
  });
  $("#btn-logo-remover").addEventListener("click", async () => {
    try {
      await api("/api/configuracoes/logo", { method: "DELETE" });
      desenharLogo(false);
      avisar(T.config.logoRemovido);
    } catch (e) {
      falhou(e);
    }
  });
  $("#form-identidade").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const responsaveis = lerResponsaveis();
    const marcado = $("#lista-responsaveis input[name=resp-padrao]:checked");
    const padrao = marcado && responsaveis.some((r) => r.id === marcado.value) ? marcado.value : responsaveis[0] && responsaveis[0].id;
    const c = await salvarConfig({
      empresa: { nome: $("#cfg-empresa-nome").value, subtitulo: $("#cfg-empresa-sub").value },
      responsaveis, ...(padrao ? { responsavel_padrao: padrao } : {}),
    }, T.config.empresaSalva, $("button[type=submit]", ev.currentTarget));
    if (c) desenharResponsaveis(c.responsaveis, c.responsavel_padrao);
  });
  $("#btn-novo-responsavel").addEventListener("click", () => {
    const linha = linhaResponsavel(undefined, !$$("#lista-responsaveis .responsavel-linha").length);
    $("#lista-responsaveis").append(linha);
    $("input[data-campo=nome]", linha).focus();
  });
  segmentado("#seg-tema", (v) => { aplicarTema(v); salvarConfig({ tema: v }); });
  $("#form-criterio").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const c = await salvarConfig({ criterio: lerCriterio() }, T.config.criterioSalvo, $("button[type=submit]", ev.currentTarget));
    if (c) preencherCriterio(c.criterio, c.criterio_personalizado);
  });
  $$("[data-modelo-criterio]").forEach((b) =>
    b.addEventListener("click", () => {
      const modelo = estado.config && estado.config.modelos_criterio[b.dataset.modeloCriterio];
      if (!modelo) return;
      preencherCriterio(modelo);
      avisar(T.config.criterioModelo(b.textContent));
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
      if (!base || base.mta_c !== valor) trocas[i.dataset.classe] = { mta_c: valor, fonte: valor == null ? T.config.semMta : T.config.fonteUsuario };
    }
    const c = await salvarConfig({ componentes: trocas }, T.config.bibliotecaSalva, $("button[type=submit]", ev.currentTarget));
    if (c) preencherComponentes(c.componentes, c.componentes_padrao);
  });
  $("#btn-comp-padrao").addEventListener("click", async () => {
    if (!(await confirmar(T.config.restaurarBibliotecaTitulo, T.config.restaurarBibliotecaTexto, T.geral.restaurar))) return;
    const c = await salvarConfig({ componentes: null }, T.config.bibliotecaRestaurada);
    if (c) preencherComponentes(c.componentes, c.componentes_padrao);
  });
  $("#btn-crit-padrao").addEventListener("click", async () => {
    if (!(await confirmar(T.config.restaurarCriterioTitulo, T.config.restaurarCriterioTexto, T.geral.restaurar))) return;
    const c = await salvarConfig({ criterio: null }, T.config.criterioRestaurado);
    if (c) preencherCriterio(c.criterio, c.criterio_personalizado);
  });
  $("#btn-ir-treinar").addEventListener("click", () => $("#cartao-treinar").scrollIntoView({ behavior: "smooth", block: "start" }));
  $("#btn-instalar-modelo").addEventListener("click", () => $("#arquivo-modelo").click());
  $("#arquivo-modelo").addEventListener("change", (ev) => { if (ev.target.files[0]) instalarModelo(ev.target.files[0]); ev.target.value = ""; });
  $("#btn-importar-avaliacao").addEventListener("click", () => $("#arquivo-avaliacao").click());
  $("#arquivo-avaliacao").addEventListener("change", (ev) => { if (ev.target.files[0]) importarAvaliacao(ev.target.files[0]); ev.target.value = ""; });
  $("#sel-avaliacao").addEventListener("change", (ev) => carregarAvaliacao(ev.target.value));
  $("#btn-copiar-comando").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("#comando-treino").textContent);
      avisar(T.config.comandoCopiado);
    } catch {
      avisar(T.geral.naoCopiou, { erro: true });
    }
  });

  document.addEventListener("keydown", (ev) => {
    const digitando = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "o") {
      ev.preventDefault();
      abrirArquivos();
      return;
    }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") {
      ev.preventDefault();
      abrirBusca();
      return;
    }
    if (ev.key === "?" && !digitando && !$("#dialogo").open && !$("#paleta").open) {
      ev.preventDefault();
      mostrarAtalhos();
      return;
    }
    if (ev.key === "Escape" && $(".menu-suspenso")) return fecharMenu();
    if (digitando || $("#dialogo").open) return;
    if (teclaVideo(ev)) return;
    if (!estado.analise || estado.vista !== "analise" || $("#analise-cheia").hidden) return;
    if (ev.key === "d" || ev.key === "D") definirFerramenta("desenhar");
    else if (ev.key === "p" || ev.key === "P") definirFerramenta("ponto");
    else if (ev.key === "l" || ev.key === "L") definirFerramenta("linha");
    else if (ev.key === "r" || ev.key === "R") alternarRotulos();
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
  ligarVideo();
  $("#btn-busca").addEventListener("click", abrirBusca);
  $("#paleta-texto").addEventListener("input", filtrarBusca);
  $("#paleta-texto").addEventListener("keydown", teclaBusca);
  $("#paleta").addEventListener("click", (ev) => { if (ev.target === ev.currentTarget) ev.currentTarget.close(); });
  window.addEventListener("hashchange", rota);
}

async function iniciar() {
  ligarEventos();
  aplicarTema("claro");
  try {
    estado.paletas = await api("/api/paletas");
    const c = await api("/api/configuracoes");
    estado.config = c;
    aplicarTema(c.tema);
    $("#versao").textContent = c.versao;
    estado.versaoServidor = c.versao;
    // Servidor antigo ainda aberto com a interface nova: pede para reabrir em vez de quebrar.
    if (c.versao !== VERSAO_INTERFACE) {
      $("#atualizar-texto").textContent = T.geral.versaoDiferente(c.versao, VERSAO_INTERFACE);
      $("#atualizar").hidden = false;
    }
    await carregarListaModelos();
  } catch (e) {
    falhou(e);
  }
  sinalDeVida();
  rota();
  api("/api/equipamentos").then((l) => { estado.equipamentos = estado.equipamentos || l; preencherSugestoes(l); }).catch(() => {});
  api("/api/pendencias").then((l) => { estado.pendencias = estado.pendencias || l; atualizarContadorPendencias(); }).catch(() => {});
  atualizarStatus();
  setInterval(atualizarStatus, 15000);
}

iniciar();
