// Casca da interface nova: navegação, roteamento, atalhos, busca, importação por arrastar, conexão e tema.
import { TEXTOS as T } from "../textos.js";
import { $, $$, el, api, json, conexao, definirVersaoServidor, VERSAO_INTERFACE } from "./base.js";
import { esqueleto, estadoVazio, estadoErro, estadoSemConexao, avisar, dialogo } from "./componentes.js";
import { instalarIcones } from "./icones.js";
import { ilustracao } from "./ilustracoes.js";
import { ROTAS, lerRota, endereco } from "./rotas.js";
import { abrirBusca } from "./busca.js";
import { importar, escolherArquivos, arquivosEscolhidos } from "./importar.js";

// ---------------------------------------------------------------- roteamento
const PARAMS = new URLSearchParams(location.search); // só para testes: ?conferir, ?tema=escuro, ?toque
let geracao = 0;         // descarta a montagem de uma tela se outra foi pedida no meio
let limpar = null;        // limpeza devolvida pela tela atual (intervalos, eventos)
let primeira = true;

async function mostrarRota() {
  const rota = lerRota();
  const minha = ++geracao;
  const conteudo = $("#conteudo");
  limpar?.();
  limpar = null;
  marcarNavegacao(rota.tela);

  if (!rota.tela) {
    document.title = T.casca.titulo(T.telas.painel);
    conteudo.replaceChildren(el("div", { class: "pagina entra" }, estadoVazio({
      icone: "alerta", titulo: `#${rota.nome}`, texto: null,
      acoes: [el("a", { class: "btn primario", href: endereco("painel") }, T.telas.painel)],
    })));
    return;
  }

  const def = ROTAS[rota.tela];
  const modulo = rota.partes.length && def.detalhe ? def.detalhe : def.modulo;
  document.title = T.casca.titulo(def.titulo);
  conteudo.replaceChildren(el("div", { class: "pagina" }, esqueleto[(!rota.partes.length && def.esqueleto) || "pagina"]()));
  try {
    const tela = await import(`./telas/${modulo}.js`);
    const pagina = el("div", { class: "pagina entra" });
    const resultado = await tela.montar(pagina, rota);
    if (minha !== geracao) { if (typeof resultado === "function") resultado(); return; }
    limpar = typeof resultado === "function" ? resultado : null;
    conteudo.replaceChildren(pagina);
  } catch (erro) {
    if (minha !== geracao) return;
    // sem servidor: a API não respondeu ou o módulo da tela não baixou; erro de código continua sendo erro
    const semServidor = erro.message === T.geral.semResposta || /dynamically imported module|Failed to fetch/i.test(erro.message);
    conteudo.replaceChildren(el("div", { class: "pagina entra" }, semServidor ? estadoSemConexao({ tentar: mostrarRota }) : estadoErro({ titulo: def.titulo, erro, tentar: mostrarRota })));
  }
  // Depois de navegar pelo teclado, o foco vai para o conteúdo (leitor de tela anuncia a tela nova).
  if (!primeira && document.activeElement && document.activeElement !== document.body && !conteudo.contains(document.activeElement)) conteudo.focus({ preventScroll: true });
  primeira = false;
  scrollTo({ top: 0 });
  // conferência automática da tela (testes visuais): ?conferir no endereço grava o resultado no <body>
  if (PARAMS.has("conferir")) setTimeout(() => import("./conferir.js").then((m) => { document.body.dataset.conferencia = JSON.stringify(m.conferir({ toque: PARAMS.has("toque") })); }), 500);
}

function marcarNavegacao(tela) {
  for (const a of $$("[data-rota]")) {
    if (a.dataset.rota === tela) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

// ---------------------------------------------------------------- atalhos
const emCampo = (alvo) => alvo.closest("input, textarea, select, [contenteditable='true']");

function abrirAtalhos() {
  dialogo({
    titulo: T.atalhos.titulo,
    corpo: [el("dl", { class: "pares legenda" }, T.atalhos.lista.flatMap(([tecla, o]) => [el("dt", {}, el("kbd", {}, tecla)), el("dd", {}, o)]))],
  }).abrir();
}

async function alternarTema() {
  const novo = document.documentElement.dataset.tema === "escuro" ? "claro" : "escuro";
  aplicarTema(novo);
  try { await api("/api/configuracoes", json("PUT", { tema: novo })); } catch (erro) { avisar(erro.message, { erro: true }); }
}

const acoesBusca = () => [
  { texto: T.busca.acaoImportar, icone: "importar", sub: "Ctrl O", executar: escolherArquivos },
  { texto: T.busca.acaoAtalhos, icone: "teclado", sub: "?", executar: abrirAtalhos },
  { texto: T.busca.acaoTema, icone: "tema", executar: alternarTema },
];

function ligarAtalhos() {
  document.addEventListener("keydown", (ev) => {
    if (document.querySelector("dialog[open]") && ev.key !== "Escape") {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") ev.preventDefault();
      return;
    }
    const tecla = ev.key.toLowerCase();
    if ((ev.ctrlKey || ev.metaKey) && tecla === "k") { ev.preventDefault(); abrirBusca(acoesBusca()); return; }
    if ((ev.ctrlKey || ev.metaKey) && tecla === "o") { ev.preventDefault(); escolherArquivos(); return; }
    if (ev.altKey && !ev.ctrlKey && /^[0-6]$/.test(ev.key)) {
      const alvo = Object.entries(ROTAS).find(([, r]) => r.atalho === ev.key);
      if (alvo) { ev.preventDefault(); location.hash = endereco(alvo[0]); }
      return;
    }
    const interrogacao = ev.key === "?" || (ev.shiftKey && (ev.key === "/" || ev.code === "IntlRo")); // ABNT2 tem o "?" em outra tecla
    if (interrogacao && !emCampo(ev.target)) { ev.preventDefault(); abrirAtalhos(); }
  });
  $("#btn-busca").addEventListener("click", () => abrirBusca(acoesBusca()));
  $("#pular").addEventListener("click", () => $("#conteudo").focus());
}

// ---------------------------------------------------------------- arrastar e soltar em qualquer tela
function ligarSoltar() {
  let camada = null;
  let profundidade = 0;
  const temArquivo = (ev) => [...(ev.dataTransfer?.types || [])].includes("Files");
  const esconder = () => { profundidade = 0; camada?.remove(); camada = null; };
  document.addEventListener("dragenter", (ev) => {
    if (!temArquivo(ev)) return;
    ev.preventDefault();
    profundidade++;
    if (!camada) {
      camada = el("div", { class: "soltar-tela", "aria-hidden": "true" },
        el("div", { class: "alvo-soltar" }, ilustracao("inspecoes", { rotulo: T.casca.soltarTitulo }), el("h2", {}, T.casca.soltarTitulo), el("p", {}, T.casca.soltarDica)));
      document.body.append(camada);
    }
  });
  document.addEventListener("dragover", (ev) => { if (temArquivo(ev)) ev.preventDefault(); });
  document.addEventListener("dragleave", (ev) => { if (temArquivo(ev) && --profundidade <= 0) esconder(); });
  document.addEventListener("drop", (ev) => {
    if (!temArquivo(ev)) return;
    ev.preventDefault();
    esconder();
    importar(ev.dataTransfer.files);
  });
  $("#arquivos").addEventListener("change", (ev) => { arquivosEscolhidos(ev.target.files); ev.target.value = ""; });
}

// ---------------------------------------------------------------- conexão com o servidor
function ligarConexao() {
  const faixa = $("#faixa-conexao");
  let relogio = null;
  const testar = async () => {
    try {
      const r = await fetch("/api/saude");
      if (r.ok) conexao.dispatchEvent(new Event("voltou"));
    } catch { /* continua sem conexão */ }
  };
  conexao.addEventListener("caiu", () => {
    if (!faixa.hidden) return;
    faixa.hidden = false;
    relogio = setInterval(testar, 3000);
  });
  conexao.addEventListener("voltou", async () => {
    if (faixa.hidden) return;
    faixa.hidden = true;
    clearInterval(relogio);
    // O servidor pode ter voltado em outra versão (reaberto pelo Pyron.exe): aí recarrega tudo.
    try {
      const s = await api("/api/status");
      if (s.versao !== VERSAO_INTERFACE) { location.reload(); return; }
    } catch { return; }
    avisar(T.casca.voltou);
    mostrarRota();
  });
  $("#btn-reconectar").addEventListener("click", (ev) => {
    ev.currentTarget.setAttribute("aria-busy", "true");
    testar().finally(() => $("#btn-reconectar").removeAttribute("aria-busy"));
  });
}

/** Cada janela avisa o servidor que está aberta (o lançador encerra o servidor quando não sobra nenhuma). */
function ligarSinal() {
  const cliente = `nova-${Math.random().toString(36).slice(2, 8)}`;
  const enviar = () => fetch(`/api/sinal?cliente=${cliente}`, { method: "POST" }).catch(() => {});
  enviar();
  setInterval(enviar, 20000);
  addEventListener("pagehide", () => navigator.sendBeacon(`/api/sinal?cliente=${cliente}&saindo=true`));
  addEventListener("pageshow", (ev) => ev.persisted && enviar());
}

// ---------------------------------------------------------------- contadores da navegação
/** Contador visível só quando há algo a fazer; o leitor de tela ouve "Pendências, 3 pendências vencidas". */
function mostrarContador(no, n, rotulo) {
  no.hidden = !n;
  no.textContent = n > 99 ? "99+" : String(n || "");
  no.setAttribute("aria-hidden", "true");
  const dono = no.closest("a");
  if (n) dono.setAttribute("aria-label", `${dono.dataset.nome}, ${rotulo}`);
  else dono.removeAttribute("aria-label");
}

async function atualizarContadores() {
  try {
    const [status, pendencias] = await Promise.all([api("/api/status"), api("/api/pendencias")]);
    definirVersaoServidor(status.versao);
    const alertas = status.alertas_pendentes || 0;
    const vencidas = pendencias.filter((p) => p.vencida).length;
    mostrarContador($("#contador-pendencias"), vencidas, T.casca.vencidas(vencidas));
    const sino = $("#btn-alertas");
    $("#contador-alertas").hidden = !alertas;
    $("#contador-alertas").textContent = alertas > 99 ? "99+" : String(alertas);
    sino.setAttribute("aria-label", T.casca.alertas(alertas));
    sino.title = T.casca.alertas(alertas);
  } catch { /* a faixa de conexão já avisa */ }
}

// ---------------------------------------------------------------- tema (Configurações › Aparência; padrão claro)
const escuroDoSistema = matchMedia("(prefers-color-scheme: dark)");
function aplicarTema(tema = "claro") {
  const efetivo = tema === "sistema" ? (escuroDoSistema.matches ? "escuro" : "claro") : tema;
  document.documentElement.dataset.tema = efetivo;
  document.documentElement.dataset.temaEscolhido = tema;
}
escuroDoSistema.addEventListener("change", () => { if (document.documentElement.dataset.temaEscolhido === "sistema") aplicarTema("sistema"); });

// ---------------------------------------------------------------- início
async function iniciar() {
  instalarIcones();
  for (const a of $$("#nav a")) a.dataset.nome = a.textContent.trim();
  ligarAtalhos();
  ligarSoltar();
  ligarConexao();
  ligarSinal();
  addEventListener("hashchange", mostrarRota);
  if (PARAMS.get("tema")) aplicarTema(PARAMS.get("tema"));
  else api("/api/configuracoes").then((c) => aplicarTema(c.tema)).catch(() => {});
  if (PARAMS.has("toque")) document.documentElement.style.setProperty("--alvo-compacto", "var(--alvo)");
  mostrarRota();
  atualizarContadores();
  setInterval(atualizarContadores, 30000);
  document.addEventListener("pyron:importadas", atualizarContadores);
  document.addEventListener("pyron:alertas", atualizarContadores);
}

iniciar();

