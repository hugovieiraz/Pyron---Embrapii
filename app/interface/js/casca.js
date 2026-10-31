// Casca da interface nova: navegação, roteamento, atalhos, busca, importação por arrastar, conexão e tema.
import { TEXTOS as T } from "../textos.js";
import { $, $$, el, icone, api, json, conexao, definirVersaoServidor, VERSAO_INTERFACE, acesso, definirAcesso, pode, modoServidor, sessao, lerPreferencia, guardarPreferencia } from "./base.js";
import { versaoMudou } from "./aplicativo.js";
import { esqueleto, estadoVazio, estadoErro, estadoSemConexao, avisar, dialogo, podeSair, botao, campo, menu, ocupado } from "./componentes.js";
import { instalarIcones } from "./icones.js";
import { ilustracao } from "./ilustracoes.js";
import { ROTAS, lerRota, endereco } from "./rotas.js";
import { abrirBusca } from "./busca.js";
import { hospedeiroJanela, arrastaJanela, alertasNovos } from "./janela.js";
import { importar, escolherArquivos, arquivosEscolhidos } from "./importar.js";

// ---------------------------------------------------------------- roteamento
const PARAMS = new URLSearchParams(location.search); // só para testes: ?conferir, ?tema=escuro, ?toque
let geracao = 0;         // descarta a montagem de uma tela se outra foi pedida no meio
let limpar = null;        // limpeza devolvida pela tela atual (intervalos, eventos)
let primeira = true;

async function mostrarRota() {
  if (document.documentElement.classList.contains("sem-sessao")) return; // a tela de entrada fica até entrar
  const rota = lerRota();
  const minha = ++geracao;
  const conteudo = $("#conteudo");
  limpar?.();
  limpar = null;
  marcarNavegacao(rota.tela);

  if (!rota.tela) {
    document.title = T.casca.titulo(T.telas.painel);
    conteudo.replaceChildren(el("div", { class: "pagina entra" }, estadoVazio({
      icone: "alerta", titulo: T.casca.rotaInexistente, texto: T.casca.rotaInexistenteTexto(rota.nome), nivel: 1, // a tela não tem outro título
      acoes: [el("a", { class: "btn primario", href: endereco("painel") }, T.telas.painel)],
    })));
    return;
  }

  const def = ROTAS[rota.tela];
  const modulo = rota.partes.length && def.detalhe ? def.detalhe : def.modulo;
  document.title = T.casca.titulo(def.titulo);
  if (def.exige && !pode(def.exige)) { // o servidor recusaria tudo da tela: diz logo por quê
    conteudo.replaceChildren(el("div", { class: "pagina entra" }, estadoVazio({
      icone: "config", titulo: T.conta.soAdministrador, texto: T.conta.soAdministradorTexto, nivel: 1,
      acoes: [el("a", { class: "btn primario", href: endereco("painel") }, T.telas.painel)],
    })));
    return;
  }
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
  if (!pode("administracao")) return; // no servidor, o tema guardado é da equipe: quem não administra troca só nesta tela
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
    if (!acessoConhecido) { location.reload(); return; } // abriu sem servidor: agora sim, entrada e perfil de verdade
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

// ---------------------------------------------------------------- acesso (modo servidor; app/acesso.py)
let acessoConhecido = false; // /api/acesso/eu respondeu nesta abertura da tela
let telaEntrada = null; // a promessa da entrada em andamento (não abre duas)

/** Mostra a tela de entrada no lugar do conteúdo e espera entrar. ``aviso``: por que pediu de novo. */
function pedirEntrada(aviso = null) {
  if (telaEntrada) return telaEntrada;
  document.documentElement.classList.add("sem-sessao");
  limpar?.();
  limpar = null;
  geracao++;
  for (const m of $$(".menu:popover-open")) m.hidePopover();
  telaEntrada = import("./telas/entrar.js").then((tela) => new Promise((resolver) => {
    const pagina = el("div", { class: "pagina entra" });
    tela.montar(pagina, { aviso, aoEntrar: (eu) => {
      document.documentElement.classList.remove("sem-sessao");
      definirAcesso(eu);
      aplicarPerfil();
      telaEntrada = null;
      resolver(eu);
    } });
    document.title = T.casca.titulo(T.entrar.titulo);
    $("#conteudo").replaceChildren(pagina);
  }));
  return telaEntrada;
}

let menuConta = null;
/** Topo conforme o perfil: Configurações só para quem administra; no servidor, nome, perfil e o menu da conta. */
function aplicarPerfil() {
  $('.topo-dir [data-rota="configuracoes"]').hidden = !pode("administracao");
  $("#btn-conta")?.remove();
  menuConta?.remove();
  menuConta = null;
  const u = acesso.usuario;
  if (!modoServidor() || !u) return;
  const C = T.conta;
  const papel = [C.perfis[u.perfil] || u.perfil, u.administrador ? C.administrador : null].filter(Boolean).join(" · ");
  const conta = el("button", { type: "button", class: "btn fantasma conta", id: "btn-conta", title: `${u.nome} · ${papel}` },
    icone("usuario"), el("span", { class: "conta-texto" }, el("span", { class: "conta-nome" }, u.nome), el("span", { class: "conta-papel" }, papel)));
  $(".topo-dir").append(conta);
  menuConta = menu(conta, [
    { texto: C.trocarSenha, icone: "chave", executar: trocarSenha },
    { separador: true },
    { texto: C.sair, icone: "sair", executar: sair },
  ]);
}

async function sair() {
  try { await api("/api/acesso/sair", json("POST", {})); } catch { /* sem servidor: a sessão vence sozinha */ }
  location.reload();
}

function trocarSenha() {
  const C = T.conta;
  const atual = campo({ rotulo: C.senhaAtual, tipo: "password", autocomplete: "current-password", maxlength: "200" });
  const nova = campo({ rotulo: C.senhaNova, tipo: "password", autocomplete: "new-password", maxlength: "200", ajuda: C.senhaAjuda });
  const repetir = campo({ rotulo: C.senhaRepetir, tipo: "password", autocomplete: "new-password", maxlength: "200" });
  const erro = el("p", { class: "erro-dialogo", role: "alert", hidden: true });
  const valor = (c) => c.querySelector("input").value;
  const salvar = botao({ texto: T.geral.salvar, variante: "primario", onclick: () => ocupado(salvar, async () => {
    erro.hidden = true;
    if (valor(nova) !== valor(repetir)) { erro.textContent = C.senhasDiferentes; erro.hidden = false; return; }
    try {
      await api("/api/acesso/senha", json("POST", { atual: valor(atual), nova: valor(nova) }));
    } catch (e) { erro.textContent = e.message; erro.hidden = false; return; }
    dlg.fechar();
    avisar(C.senhaTrocada);
  }) });
  const dlg = dialogo({ titulo: C.trocarSenha, corpo: [atual, nova, repetir, erro], acoes: [botao({ texto: T.geral.cancelar, onclick: () => dlg.fechar() }), salvar] }).abrir();
  atual.querySelector("input").focus();
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
/** Contador visível só quando há algo a fazer; o leitor de tela ouve "Pendências, 3 pendências vencidas" de um
 * texto escondido dentro do link (sem aria-label, o nome continua sendo o texto visível, para quem usa comando de voz). */
function mostrarContador(no, n, rotulo) {
  no.hidden = !n;
  no.textContent = n > 99 ? "99+" : String(n || "");
  no.setAttribute("aria-hidden", "true");
  const dono = no.closest("a");
  let leitura = dono.querySelector(".leitura-contador");
  if (!leitura) dono.append(leitura = el("span", { class: "so-leitor leitura-contador" }));
  leitura.textContent = n ? `, ${rotulo}` : "";
}

async function atualizarContadores() {
  try {
    const [status, pendencias] = await Promise.all([api("/api/status"), api("/api/pendencias")]);
    definirVersaoServidor(status.versao);
    versaoMudou(status.versao);
    const alertas = status.alertas_pendentes || 0;
    const vencidas = pendencias.filter((p) => p.vencida).length;
    mostrarContador($("#contador-pendencias"), vencidas, T.casca.vencidas(vencidas));
    const sino = $("#btn-alertas");
    $("#contador-alertas").hidden = !alertas;
    $("#contador-alertas").textContent = alertas > 99 ? "99+" : String(alertas);
    sino.setAttribute("aria-label", T.casca.alertas(alertas));
    sino.title = T.casca.alertas(alertas);
    avisarHospedeiro(status, alertas);
  } catch { /* a faixa de conexão já avisa */ }
}

// ---------------------------------------------------------------- Pyron desktop: aviso do Windows e bandeja
const hospedeiro = hospedeiroJanela();
let alertasAntes = null;

/** Alerta novo vira aviso do Windows (a janela pode estar minimizada) e a bandeja acompanha o monitoramento. */
function avisarHospedeiro(status, alertas) {
  if (!hospedeiro?.notificar) return;
  const novos = alertasNovos(alertasAntes, alertas);
  alertasAntes = alertas;
  if (novos) hospedeiro.notificar(T.desktop.alertas(novos), T.desktop.alertasTexto).catch(() => {});
  hospedeiro.contar("pyron:monitoramento", Boolean(status.monitoramento?.ativo)).catch(() => {});
}

/** "Monitoramento" da bandeja: liga ou desliga pela API, com a sessão e as permissões de quem está na janela. */
function ligarBandeja() {
  hospedeiro.ouvir("bandeja:monitoramento", async () => {
    try {
      const atual = await api("/api/monitoramento");
      const r = await api("/api/monitoramento", json("PUT", { ativo: !atual.config.ativo }));
      avisar(r.config.ativo ? T.desktop.monitorLigado : T.desktop.monitorDesligado);
      hospedeiro.contar("pyron:monitoramento", Boolean(r.config.ativo)).catch(() => {});
    } catch (e) {
      // sem pasta escolhida ou sem permissão: o motivo aparece e a tela da pasta monitorada abre
      avisar(`${T.desktop.monitorFalhou} ${e.message}`, { erro: true });
      if (pode("administracao")) location.hash = endereco("captura", ["pasta"]);
      atualizarContadores();
    }
  });
}

// ---------------------------------------------------------------- janela própria (Pyron desktop ou Pyron.exe)
// Sem a barra de título do Windows: o topo arrasta a janela e estes botões pedem ao hospedeiro (js/janela.js)
// minimizar, maximizar ou fechar. Fora dela (navegador, janela do Edge, tablet) nada muda.
function ligarJanela() {
  if (!hospedeiro) return;
  document.documentElement.classList.add("janela-propria");
  const J = T.casca.janela;
  const botao = (acao, ic, rotulo, classe = null) => el("button", { type: "button", class: classe, "aria-label": rotulo, title: rotulo,
    onclick: () => hospedeiro.pedir(acao) }, icone(ic));
  const maximizar = botao("maximizar", "restaurar", J.restaurar);
  $(".topo").append(el("div", { class: "controles-janela", role: "group", "aria-label": J.grupo },
    botao("minimizar", "minimizar", J.minimizar), maximizar, botao("fechar", "x", J.fechar, "fechar")));
  hospedeiro.aoMudar((max) => {
    maximizar.replaceChildren(icone(max ? "restaurar" : "maximizar"));
    maximizar.setAttribute("aria-label", max ? J.restaurar : J.maximizar);
    maximizar.title = max ? J.restaurar : J.maximizar;
  });
  if (hospedeiro.arrastar) {
    // dois cliques no topo maximizam ou restauram, como na barra de título do Windows
    $(".topo").addEventListener("mousedown", (ev) => {
      if (ev.button !== 0 || !arrastaJanela(ev.target)) return;
      if (ev.detail === 2) hospedeiro.pedir("maximizar");
      else hospedeiro.arrastar();
    });
  }
  if (hospedeiro.ouvir) ligarBandeja();
  // Ao abrir, a janela entrega o foco à página como se fosse pelo teclado, e o link "Pular para o conteúdo"
  // aparecia sobre a logo. Ele só fica quando o foco chega por uma tecla de verdade.
  let teclou = false;
  addEventListener("keydown", () => { teclou = true; }, { capture: true, once: true });
  $("#pular").addEventListener("focus", (ev) => { if (!teclou) ev.target.blur(); });
}

// ---------------------------------------------------------------- tema (Configurações › Aparência; padrão claro)
const escuroDoSistema = matchMedia("(prefers-color-scheme: dark)");
function aplicarTema(tema = "claro") {
  const efetivo = tema === "sistema" ? (escuroDoSistema.matches ? "escuro" : "claro") : tema;
  document.documentElement.dataset.tema = efetivo;
  document.documentElement.dataset.temaEscolhido = tema;
  // barra de título da janela do Edge (modo aplicativo) na cor do topo
  let meta = $('meta[name="theme-color"]');
  if (!meta) document.head.append(meta = el("meta", { name: "theme-color" }));
  meta.content = getComputedStyle(document.documentElement).getPropertyValue("--superficie").trim();
}
escuroDoSistema.addEventListener("change", () => { if (document.documentElement.dataset.temaEscolhido === "sistema") aplicarTema("sistema"); });

// ---------------------------------------------------------------- início
async function iniciar() {
  instalarIcones();
  ligarJanela();
  for (const a of $$("#nav a")) {
    a.dataset.nome = a.textContent.trim();
    // tablet em retrato: só o ícone da seção aparece (o nome fica para o leitor de tela e para a dica)
    const nome = [...a.childNodes].find((n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
    if (nome) nome.replaceWith(el("span", { class: "nome-nav" }, nome.textContent));
    a.prepend(icone(ROTAS[a.dataset.rota]?.icone || "painel", "ic ic-nav"));
  }
  ligarAtalhos();
  ligarSoltar();
  ligarConexao();
  // Quem está usando: no modo local não há login; no servidor, a tela de entrada vem antes de tudo.
  let eu = null;
  try {
    eu = await api("/api/acesso/eu");
    acessoConhecido = true;
    guardarPreferencia("modo", eu.modo);
  } catch { /* sem servidor: a faixa de conexão avisa; o tablet abre a casca guardada */ }
  // Sem resposta, vale o último modo visto neste aparelho só para os textos (nenhuma permissão no servidor);
  // quando a conexão voltar, a tela recarrega e pede a entrada se precisar.
  definirAcesso(eu || (lerPreferencia("modo", "local") === "servidor" ? { modo: "servidor", usuario: null, permissoes: [] } : null));
  if (modoServidor()) $("#faixa-conexao span").replaceChildren(el("b", {}, T.casca.offline), " ", T.casca.offlineDicaServidor);
  if (modoServidor()) import("./aplicativo.js").then((m) => m.ligarAplicativo()); // instalável no tablet (PWA)
  if (modoServidor() && !acesso.usuario && acessoConhecido) await pedirEntrada();
  aplicarPerfil();
  sessao.addEventListener("expirou", async () => { await pedirEntrada(T.entrar.expirou); mostrarRota(); atualizarContadores(); });
  if (!modoServidor()) ligarSinal(); // o servidor da equipe não se desliga quando uma janela fecha
  // alteração sem salvar (critério, componentes): ficar devolve o endereço anterior sem remontar a tela
  addEventListener("hashchange", async (ev) => { if (await podeSair()) mostrarRota(); else history.replaceState(null, "", ev.oldURL); });
  if (PARAMS.get("tema")) aplicarTema(PARAMS.get("tema"));
  else api("/api/configuracoes").then((c) => aplicarTema(c.tema)).catch(() => {});
  if (PARAMS.has("toque")) document.documentElement.style.setProperty("--alvo-compacto", "var(--alvo)");
  mostrarRota();
  atualizarContadores();
  setInterval(atualizarContadores, 30000);
  document.addEventListener("pyron:importadas", atualizarContadores);
  document.addEventListener("pyron:alertas", atualizarContadores);
  document.addEventListener("pyron:tema", (ev) => aplicarTema(ev.detail)); // Configurações › Aparência
}

iniciar();

