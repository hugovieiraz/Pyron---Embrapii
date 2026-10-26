// Componentes da interface nova. Cada função devolve um nó pronto; o visual está em componentes.css.
import { TEXTOS as T } from "../textos.js";
import { el, icone, duracao, token, $ } from "./base.js";
import { ilustracao } from "./ilustracoes.js";

let sequencia = 0;
const novoId = (prefixo) => `${prefixo}-${++sequencia}`;

// ---------------------------------------------------------------- botão
/**
 * botao({ texto, icone, variante: "primario" | "secundario" | "fantasma" | "perigo", compacto, soIcone, atalho, onclick })
 * Com soIcone, o texto vira aria-label e dica: todo botão de ícone tem nome acessível.
 */
export function botao({ texto, icone: ic, variante = "secundario", compacto = false, soIcone = false, atalho, onclick, tipo = "button", desabilitado = false, contador, ...resto } = {}) {
  const classes = ["btn", variante !== "secundario" && variante, compacto && "compacto", soIcone && "icone"].filter(Boolean).join(" ");
  const dica = atalho ? `${texto} (${atalho})` : texto;
  const b = el("button", { type: tipo, class: classes, onclick, disabled: desabilitado, "aria-label": soIcone ? texto : null, title: soIcone || atalho ? dica : null, ...resto },
    ic ? icone(ic) : null, soIcone ? null : el("span", {}, texto), contador ? contadorNo(contador) : null);
  return b;
}

/** Mostra o indicador de carregamento no botão enquanto a ação roda; devolve o resultado da ação. */
export async function ocupado(b, acao) {
  b.setAttribute("aria-busy", "true");
  try {
    return await acao();
  } finally {
    b.removeAttribute("aria-busy");
  }
}

function contadorNo(n) {
  return el("span", { class: "contador", "aria-hidden": "true" }, n > 99 ? "99+" : String(n));
}
export const contador = contadorNo;

// ---------------------------------------------------------------- campos
/**
 * campo({ rotulo, tipo, valor, unidade, ajuda, erro, opcoes, area, marcador, ...atributos })
 * Rótulo sempre visível e ligado ao controle; ajuda e erro ficam em aria-describedby.
 */
export function campo({ rotulo, tipo = "text", valor, unidade, ajuda, erro, opcoes, area = false, marcador, id = novoId("campo"), classe, ...attrs } = {}) {
  const idAjuda = ajuda ? `${id}-ajuda` : null;
  const idErro = erro ? `${id}-erro` : null;
  const comuns = { id, "aria-describedby": [idAjuda, idErro].filter(Boolean).join(" ") || null, "aria-invalid": erro ? "true" : null, ...attrs };
  let controle;
  if (opcoes) {
    controle = el("select", comuns, opcoes.map((o) => (typeof o === "string" ? new Option(o, o) : new Option(o.texto, o.valor))));
    if (valor != null) controle.value = valor;
  } else if (area) {
    controle = el("textarea", { ...comuns, placeholder: marcador }, valor ?? "");
  } else if (tipo === "number") {
    // número aceita vírgula ou ponto (lerNumero): o campo nativo de número recusa "31,5"
    controle = el("input", { ...comuns, type: "text", inputmode: "decimal", autocomplete: "off", spellcheck: "false", class: "num", value: valor ?? "", placeholder: marcador });
  } else {
    controle = el("input", { ...comuns, type: tipo, value: valor ?? "", placeholder: marcador });
  }
  const corpo = unidade ? el("div", { class: "com-unidade" }, controle, el("span", { class: "unidade", "aria-hidden": "true" }, unidade)) : controle;
  if (unidade) controle.setAttribute("aria-label", `${rotulo} (${unidade})`);
  return el("div", { class: ["campo", classe].filter(Boolean).join(" ") },
    el("label", { for: id }, rotulo),
    corpo,
    ajuda ? el("span", { class: "ajuda", id: idAjuda }, ajuda) : null,
    erro ? el("span", { class: "erro-campo", id: idErro }, icone("alerta", "ic p"), erro) : null);
}

export function marcar({ rotulo, marcado = false, onchange, ...attrs } = {}) {
  return el("label", { class: "marcar" }, el("input", { type: "checkbox", checked: marcado, onchange, ...attrs }), el("span", {}, rotulo));
}

/** Busca das telas de lista: lupa dentro do campo, rótulo acessível, aoMudar a cada letra. */
export function campoBusca({ rotulo, valor = "", aoMudar }) {
  const entrada = el("input", { type: "search", class: "entrada", value: valor, placeholder: rotulo, "aria-label": rotulo, autocomplete: "off", spellcheck: "false", oninput: () => aoMudar(entrada.value) });
  const no = el("div", { class: "busca-lista" }, icone("busca"), entrada);
  no.entrada = entrada;
  return no;
}

// ---------------------------------------------------------------- segmentado e abas
/** Grupo de opções exclusivas (filtro, modo): botões com aria-pressed. */
export function segmentado({ rotulo, opcoes, valor, aoMudar }) {
  const g = el("div", { class: "segmentado", role: "group", "aria-label": rotulo });
  const marcarValor = (v) => [...g.children].forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.valor === v)));
  for (const o of opcoes) {
    g.append(el("button", { type: "button", dataset: { valor: o.valor }, "aria-pressed": String(o.valor === valor), onclick: () => { marcarValor(o.valor); aoMudar?.(o.valor); } },
      o.texto, o.qtd != null ? el("span", { class: "qtd" }, String(o.qtd)) : null));
  }
  g.definir = marcarValor;
  return g;
}

/**
 * Abas com teclado: setas mudam de aba, Home e End vão às pontas (padrão WAI-ARIA).
 * vertical: true vira o trilho de ícones do painel de detalhe (cada item com icone; o texto vai para o nome acessível).
 */
export function abas({ rotulo, itens, ativa, aoMudar, vertical = false }) {
  const lista = el("div", { class: vertical ? "trilho" : "abas", role: "tablist", "aria-label": rotulo, "aria-orientation": vertical ? "vertical" : null });
  const botoes = itens.map((a) => el("button", {
    type: "button", role: "tab", id: `aba-${a.id}`, "aria-controls": `painel-${a.id}`, "aria-selected": String(a.id === ativa), tabindex: a.id === ativa ? "0" : "-1",
    dataset: { aba: a.id }, onclick: () => escolher(a.id, true),
    "aria-label": vertical ? a.texto : null, title: vertical ? a.texto : null,
  }, vertical ? icone(a.icone) : a.texto, a.qtd != null ? (vertical ? (a.qtd ? contadorNo(a.qtd) : null) : el("span", { class: "qtd" }, String(a.qtd))) : null));
  function escolher(id, avisarMudanca) {
    for (const b of botoes) {
      const sim = b.dataset.aba === id;
      b.setAttribute("aria-selected", String(sim));
      b.tabIndex = sim ? 0 : -1;
    }
    if (avisarMudanca) aoMudar?.(id);
  }
  lista.addEventListener("keydown", (ev) => {
    const i = botoes.indexOf(document.activeElement);
    if (i < 0) return;
    const teclas = vertical ? { ArrowDown: i + 1, ArrowUp: i - 1 } : { ArrowRight: i + 1, ArrowLeft: i - 1 };
    const alvo = { ...teclas, Home: 0, End: botoes.length - 1 }[ev.key];
    if (alvo == null) return;
    ev.preventDefault();
    const b = botoes[(alvo + botoes.length) % botoes.length];
    b.focus();
    escolher(b.dataset.aba, true);
  });
  lista.append(...botoes);
  lista.escolher = (id) => escolher(id, false);
  return lista;
}

/** Painel de conteúdo ligado a uma aba de abas(). */
export const painelAba = (id, ...filhos) => el("div", { role: "tabpanel", id: `painel-${id}`, "aria-labelledby": `aba-${id}`, tabindex: "0" }, ...filhos);

// ---------------------------------------------------------------- cabeçalho de página
export function cabecalho({ titulo, meta = [], acoes = [], antes = [] }) {
  return el("header", { class: "cabecalho" }, antes,
    el("div", { class: "titulo" }, el("h1", {}, titulo), meta.length ? el("div", { class: "meta" }, meta) : null),
    acoes.length ? el("div", { class: "acoes" }, acoes) : null);
}

// ---------------------------------------------------------------- severidade e indicador
/** Selo de severidade: cor + nome do nível (a cor nunca é o único sinal). */
export function selo(nivel, { indicativa = false } = {}) {
  return el("span", { class: `selo ${nivel}${indicativa ? " indicativa" : ""}`, title: indicativa ? T.indicativa : null }, T.niveis[nivel] || nivel);
}

/** Número de destaque da tela; com href ou onclick vira atalho para a lista filtrada. */
export function indicador({ rotulo, valor, nota, severidade, href, onclick }) {
  const tag = href ? "a" : onclick ? "button" : "div";
  return el(tag, { class: `indicador${severidade ? ` sev-${severidade}` : ""}`, href, onclick, type: tag === "button" ? "button" : null },
    el("span", { class: "valor" }, String(valor)), el("span", { class: "rotulo" }, rotulo), nota ? el("span", { class: "nota" }, nota) : null);
}

// ---------------------------------------------------------------- tabela
/**
 * tabela({ rotulo, colunas: [{ chave, titulo, classe, ordenavel, link, celula(linha) }], linhas, severidade(linha), href(linha), ordem, aoOrdenar,
 *          marcar: { rotulo(linha), marcada(linha), aoMudar(linhas, sim, todas), todas }, aoMenu(linha, evento), aoEscolher(linha), grupo(linha) })
 * A linha inteira é clicável, mas o alvo de teclado é o link da coluna com link: true (ou da primeira), sem div clicável.
 * Com marcar, a primeira coluna tem a caixa de seleção e o cabeçalho marca ou desmarca todas as linhas visíveis.
 * Com aoEscolher (lista com painel de detalhe), a linha seleciona em vez de navegar: o alvo de teclado vira botão.
 * Com grupo, uma linha de título separa as linhas a cada valor novo (ex.: instalação).
 */
export function tabela({ rotulo, colunas, linhas, severidade, href, ordem, aoOrdenar, selecionada, marcar: sel, aoMenu, aoEscolher, grupo }) {
  const comTraco = Boolean(severidade);
  const iLink = Math.max(0, colunas.findIndex((c) => c.link));
  let todas = null;
  if (sel) {
    todas = el("input", { type: "checkbox", "aria-label": sel.todas, onchange: (ev) => sel.aoMudar(linhas, ev.target.checked, true) });
  }
  const sincronizarTodas = () => {
    if (!todas) return;
    const n = linhas.filter((l) => sel.marcada(l)).length;
    todas.checked = n > 0 && n === linhas.length;
    todas.indeterminate = n > 0 && n < linhas.length;
  };
  const cab = el("tr", {}, sel ? el("th", { class: "celula-marcar" }, el("label", { class: "alvo-marcar" }, todas)) : null, comTraco ? el("th", { class: "celula-traco", "aria-hidden": "true" }) : null, colunas.map((c) => {
    const sentido = ordem && ordem.chave === c.chave ? (ordem.sentido === "asc" ? "ascending" : "descending") : null;
    return el("th", { scope: "col", class: c.classe, "aria-sort": sentido },
      c.ordenavel ? el("button", { type: "button", onclick: () => aoOrdenar?.(c.chave) }, c.titulo, sentido ? icone("ordenar", "ic p") : null) : c.titulo);
  }));
  const nColunas = colunas.length + (sel ? 1 : 0) + (comTraco ? 1 : 0);
  let grupoAtual;
  const corpo = el("tbody", {}, linhas.flatMap((l) => {
    const titulo = grupo?.(l);
    const cabGrupo = grupo && titulo !== grupoAtual ? el("tr", { class: "linha-grupo" }, el("th", { scope: "colgroup", colspan: String(nColunas) }, titulo)) : null;
    grupoAtual = titulo;
    const destino = href?.(l);
    const marcada = sel ? sel.marcada(l) : false;
    const tr = el("tr", { class: [destino && "clicavel", marcada && "marcada"].filter(Boolean).join(" ") || null, "aria-selected": selecionada ? String(selecionada(l)) : null },
      sel ? el("td", { class: "celula-marcar" }, el("label", { class: "alvo-marcar" }, el("input", { type: "checkbox", checked: marcada, "aria-label": sel.rotulo(l),
        onchange: (ev) => { tr.classList.toggle("marcada", ev.target.checked); sel.aoMudar([l], ev.target.checked); sincronizarTodas(); } }))) : null,
      comTraco ? el("td", { class: `traco-celula sev-${severidade(l)}` }) : null,
      colunas.map((c, i) => {
        let conteudo = c.celula ? c.celula(l) : l[c.chave];
        if (i === iLink && destino) conteudo = el("a", { href: destino, class: "forte" }, conteudo);
        else if (i === iLink && aoEscolher) conteudo = el("button", { type: "button", class: "forte escolher", onclick: () => aoEscolher(l) }, conteudo);
        return el("td", { class: c.classe }, conteudo);
      }));
    if (aoEscolher) {
      tr.classList.add("clicavel");
      tr.addEventListener("click", (ev) => { if (!ev.target.closest("a, button, input, label")) aoEscolher(l); });
    }
    if (destino) tr.addEventListener("click", (ev) => { if (!ev.target.closest("a, button, input, label")) location.hash = destino.replace(/^#/, ""); });
    if (aoMenu) tr.addEventListener("contextmenu", (ev) => { ev.preventDefault(); aoMenu(l, ev); });
    return cabGrupo ? [cabGrupo, tr] : [tr];
  }));
  sincronizarTodas();
  return el("div", { class: "tabela-caixa" }, el("table", { class: "tabela", "aria-label": rotulo }, el("thead", {}, cab), corpo));
}

// ---------------------------------------------------------------- estados de carregamento, vazio e erro
const esq = (classe, estilo) => el("span", { class: `esq ${classe}`, style: estilo, "aria-hidden": "true" });
export const esqueleto = {
  linhas: (n = 3) => el("div", { class: "esqueleto", role: "status", "aria-busy": "true", "aria-label": T.geral.carregando }, Array.from({ length: n }, (_, i) => esq("linha", { width: `${[92, 76, 84, 60][i % 4]}%` }))),
  indicadores: (n = 4) => el("div", { class: "esqueleto" }, el("div", { class: "grade" }, Array.from({ length: n }, () => esq("bloco")))),
  tabela: (n = 6) => el("div", { class: "esqueleto tabela-caixa", role: "status", "aria-busy": "true", "aria-label": T.geral.carregando },
    Array.from({ length: n }, () => el("div", { class: "linha-tabela" }, esq("linha"), esq("linha"), esq("linha"), esq("linha")))),
  lista: () => el("div", { class: "esqueleto", role: "status", "aria-busy": "true", "aria-label": T.geral.carregando, style: { paddingTop: "var(--e-6)" } },
    esq("titulo"), esq("linha", { width: "40%" }), el("div", { class: "tabela-caixa" }, Array.from({ length: 8 }, () => el("div", { class: "linha-tabela" }, esq("linha"), esq("linha"), esq("linha"), esq("linha"))))),
  pagina: () => el("div", { class: "esqueleto", role: "status", "aria-busy": "true", "aria-label": T.geral.carregando, style: { paddingTop: "var(--e-6)" } },
    esq("titulo"), el("div", { class: "grade" }, Array.from({ length: 4 }, () => esq("bloco"))), esq("cheio")),
};

/**
 * Vazio: uma frase útil e a ação que resolve. Com ilustracao (nome de js/ilustracoes.js), o desenho
 * da tela entra no lugar do ícone e a moldura tracejada sai (estado de tela inteira).
 */
export function estadoVazio({ icone: ic = "inspecoes", ilustracao: ilu, procurando = false, titulo, texto, acoes = [], compacto = false, nivel = 2 }) {
  const figura = ilu ? ilustracao(ilu, { rotulo: titulo, procurando }) : icone(ic);
  return el("div", { class: ["vazio", compacto && "compacto", ilu && "com-ilustracao"].filter(Boolean).join(" ") }, figura, el(`h${nivel}`, {}, titulo), texto ? el("p", {}, texto) : null,
    acoes.length ? el("div", { class: "grupo-btn" }, acoes) : null);
}

/** Sem conexão com o servidor, em tela inteira (a faixa do topo continua avisando). */
export function estadoSemConexao({ tentar }) {
  return estadoVazio({ ilustracao: "sem-conexao", titulo: T.casca.offline, texto: T.casca.offlineDica,
    acoes: [botao({ texto: T.geral.tentarDeNovo, icone: "refazer", variante: "primario", onclick: tentar })] });
}

// ---------------------------------------------------------------- barra de ferramentas, seção e painel de detalhe
/**
 * barraFerramentas({ rotulo, grupos: [[{ texto, icone, onclick, href, pressionado, indisponivel, soIcone }], ...], direita: [...] })
 * Ícone + rótulo, divisor entre grupos, indisponível em cinza (continua no Tab, com o motivo na dica).
 * Setas percorrem as ferramentas (padrão WAI-ARIA de toolbar).
 */
export function barraFerramentas({ rotulo, grupos = [], direita = [] }) {
  const ferramenta = (f) => {
    const tag = f.href && !f.indisponivel ? "a" : "button";
    const dica = f.indisponivel ? `${f.texto}: ${f.indisponivel}` : f.atalho ? `${f.texto} (${f.atalho})` : f.soIcone ? f.texto : f.dica || null;
    return el(tag, {
      class: `ferramenta${f.soIcone ? " so-icone" : ""}`, type: tag === "button" ? "button" : null, href: tag === "a" ? f.href : null,
      "aria-pressed": f.pressionado == null ? null : String(f.pressionado), "aria-disabled": f.indisponivel ? "true" : null,
      "aria-label": f.soIcone ? f.texto : null, title: dica, tabindex: "-1", dataset: f.chave ? { chave: f.chave } : null,
      onclick: (ev) => { if (ev.currentTarget.getAttribute("aria-disabled") === "true") { ev.preventDefault(); return; } f.onclick?.(ev); },
    }, f.icone ? icone(f.icone) : null, f.soIcone ? null : el("span", { class: "rotulo" }, f.texto));
  };
  const partes = [];
  grupos.forEach((g, i) => { if (i) partes.push(el("span", { class: "divisor", role: "separator", "aria-orientation": "vertical" })); partes.push(...g.map(ferramenta)); });
  if (direita.length) partes.push(el("span", { class: "empurrar" }), ...direita.map(ferramenta));
  const barra = el("div", { class: "barra-ferramentas", role: "toolbar", "aria-label": rotulo }, partes);
  const itens = () => [...barra.querySelectorAll(".ferramenta")];
  const primeiro = itens()[0];
  if (primeiro) primeiro.tabIndex = 0;
  barra.addEventListener("keydown", (ev) => {
    const lista = itens();
    const i = lista.indexOf(document.activeElement);
    const alvo = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: lista.length - 1 }[ev.key];
    if (i < 0 || alvo == null) return;
    ev.preventDefault();
    lista.forEach((n) => { n.tabIndex = -1; });
    const n = lista[(alvo + lista.length) % lista.length];
    n.tabIndex = 0;
    n.focus();
  });
  return barra;
}

/** Seção recolhível com faixa de título (<details> nativo: teclado e leitor de tela sem código extra). */
export function secao({ titulo, aberta = true, qtd, conteudo = [] }) {
  return el("details", { class: "secao", open: aberta },
    el("summary", {}, el("span", {}, titulo), qtd != null ? el("span", { class: "qtd" }, String(qtd)) : null, icone("baixo", "ic p")),
    el("div", { class: "corpo-secao" }, conteudo));
}

/**
 * painelDetalhe({ rotulo, itens: [{ id, icone, texto, qtd, montar: () => nós }], ativa })
 * Inspetor à direita: trilho de ícones (abas verticais) e o conteúdo da aba com título e seções.
 */
export function painelDetalhe({ rotulo, itens, ativa = itens[0].id }) {
  const conteudo = el("div", { class: "painel-conteudo" });
  let atual = ativa;
  const mostrar = (id) => {
    atual = id;
    const item = itens.find((i) => i.id === id);
    const titulo = typeof item.titulo === "function" ? item.titulo() : item.texto;
    conteudo.replaceChildren(el("div", { role: "tabpanel", id: `painel-${id}`, "aria-labelledby": `aba-${id}` }, titulo ? el("h2", {}, titulo) : null, item.montar()));
  };
  const trilho = abas({ rotulo, itens, ativa, vertical: true, aoMudar: mostrar });
  mostrar(ativa);
  const painel = el("aside", { class: "painel-detalhe", "aria-label": rotulo }, trilho, conteudo);
  painel.ativa = () => atual;
  painel.atualizar = () => mostrar(atual);                       // redesenha a aba aberta (dados novos)
  painel.mostrar = (id) => { trilho.escolher(id); mostrar(id); }; // troca de aba por código
  return painel;
}

/** Erro: o que aconteceu, a mensagem do servidor e "Tentar de novo". */
export function estadoErro({ titulo, erro, tentar }) {
  return el("div", { class: "erro-estado", role: "alert" }, icone("alerta"), el("h2", {}, titulo),
    erro ? el("p", { class: "detalhe" }, erro.message || String(erro)) : null,
    tentar ? el("div", { class: "grupo-btn" }, botao({ texto: T.geral.tentarDeNovo, icone: "refazer", onclick: tentar })) : null);
}

// ---------------------------------------------------------------- aviso
function caixaAvisos() {
  let c = $(".avisos");
  if (!c) {
    c = el("div", { class: "avisos", "aria-live": "polite" });
    document.body.append(c);
  }
  return c;
}

/**
 * avisar(texto, { erro, acao: { rotulo, executar }, duracao })
 * Fica parado enquanto o mouse ou o foco estão nele; com ação (Desfazer), dura mais.
 */
export function avisar(texto, { erro = false, acao = null, duracao: tempo } = {}) {
  const total = tempo || (erro ? 8000 : acao ? 7000 : 4000);
  const fechar = () => {
    clearTimeout(relogio);
    a.classList.add("saindo");
    setTimeout(() => a.remove(), duracao("rapida"));
  };
  const a = el("div", { class: `aviso${erro ? " erro" : ""}`, role: erro ? "alert" : "status" },
    icone(erro ? "alerta" : "check"), el("span", { class: "texto" }, texto),
    acao ? el("button", { type: "button", class: "btn compacto acao", onclick: () => { fechar(); acao.executar(); } }, acao.rotulo) : null,
    el("button", { type: "button", class: "btn compacto icone", "aria-label": T.geral.fechar, title: T.geral.fechar, onclick: () => fechar() }, icone("x", "ic p")));
  let restante = total;
  let inicio = performance.now();
  let relogio = setTimeout(fechar, restante);
  const pausar = () => { clearTimeout(relogio); restante -= performance.now() - inicio; };
  const seguir = () => { inicio = performance.now(); relogio = setTimeout(fechar, Math.max(restante, 1500)); };
  a.addEventListener("mouseenter", pausar);
  a.addEventListener("mouseleave", seguir);
  a.addEventListener("focusin", pausar);
  a.addEventListener("focusout", seguir);
  caixaAvisos().append(a);
  return { fechar, atualizar: (novo) => { a.querySelector(".texto").textContent = novo; } };
}

// ---------------------------------------------------------------- diálogo
/** dialogo({ titulo, corpo, acoes }): <dialog> nativo (foco preso, Esc fecha). Devolve { no, abrir, fechar }. */
export function dialogo({ titulo, corpo = [], acoes = [], aoFechar, classe = "" }) {
  const idTitulo = novoId("dialogo");
  const d = el("dialog", { class: `dialogo ${classe}`, "aria-labelledby": idTitulo },
    el("div", { class: "cab-dialogo" }, el("h2", { id: idTitulo }, titulo),
      botao({ texto: T.geral.fechar, icone: "x", variante: "fantasma", soIcone: true, compacto: true, onclick: () => d.close() })),
    el("div", { class: "corpo-dialogo" }, corpo),
    acoes.length ? el("div", { class: "rodape-dialogo" }, acoes) : null);
  d.addEventListener("close", () => { aoFechar?.(d.returnValue); d.remove(); });
  d.addEventListener("click", (ev) => { if (ev.target === d) d.close(); }); // clique no véu fecha
  return {
    no: d,
    abrir() { document.body.append(d); d.showModal(); return this; },
    fechar(valor = "") { d.close(valor); },
  };
}

/** Pergunta com duas saídas; resolve true se confirmar. Para ação irreversível, prefira avisar() com Desfazer. */
export function confirmar({ titulo, texto, confirmar: rotulo, perigo = false }) {
  return new Promise((resolver) => {
    let ok = false;
    const dlg = dialogo({
      titulo,
      corpo: [el("p", {}, texto)],
      acoes: [
        botao({ texto: T.geral.cancelar, onclick: () => dlg.fechar() }),
        botao({ texto: rotulo, variante: perigo ? "perigo" : "primario", onclick: () => { ok = true; dlg.fechar("ok"); } }),
      ],
      aoFechar: () => resolver(ok),
    }).abrir();
  });
}

// ---------------------------------------------------------------- alterações não salvas
// Só os formulários de Salvar explícito (critério, componentes) usam: o resto salva sozinho.
let pendente = null;
addEventListener("beforeunload", (ev) => { if (pendente?.()) ev.preventDefault(); });

/** vigiarAlteracoes(raiz): digitar em raiz marca a tela como alterada. Devolve { marcar(), salvo() }. */
export function vigiarAlteracoes(raiz) {
  let alterada = false;
  raiz.addEventListener("input", () => { alterada = true; });
  pendente = () => alterada && raiz.isConnected;
  return { marcar() { alterada = true; }, salvo() { alterada = false; } };
}

/** Antes de trocar de tela ou de aba: com alteração sem salvar, pergunta. Resolve true para seguir. */
export async function podeSair() {
  if (!pendente?.()) return true;
  const ok = await confirmar({ titulo: T.geral.sairTitulo, texto: T.geral.sairTexto, confirmar: T.geral.sairConfirmar, perigo: true });
  if (ok) pendente = null;
  return ok;
}

// ---------------------------------------------------------------- menu
/**
 * menu(gatilho, itens, { em, descartar }): itens = [{ texto, icone, executar, marcado, perigo, desabilitado } | { separador: true } | { grupo: "..." }]
 * Usa popover nativo (fecha com Esc e clique fora); setas, Home e End percorrem os itens.
 * Com em = { x, y } (menu de contexto, botão direito), abre já no ponteiro; o foco volta ao gatilho ao fechar.
 */
export function menu(gatilho, itens, { em = null, descartar = false } = {}) {
  const m = el("div", { class: "menu", popover: "auto", role: "menu", id: novoId("menu") });
  const comMarca = itens.some((i) => "marcado" in i);
  for (const i of itens) {
    if (i.separador) { m.append(el("div", { class: "separador", role: "separator" })); continue; }
    if (i.grupo) { m.append(el("div", { class: "grupo-menu", role: "presentation" }, i.grupo)); continue; }
    const papel = "marcado" in i ? "menuitemradio" : "menuitem";
    m.append(el("button", {
      type: "button", role: papel, class: i.perigo ? "perigo" : null, tabindex: "-1",
      "aria-checked": "marcado" in i ? String(Boolean(i.marcado)) : null, "aria-disabled": i.desabilitado ? "true" : null,
      onclick: () => { if (i.desabilitado) return; m.hidePopover(); i.executar?.(); },
    }, i.icone ? icone(i.icone) : null, el("span", {}, i.texto), comMarca ? icone("check", "ic p marca") : null));
  }
  const itensFoco = () => [...m.querySelectorAll('[role^="menuitem"]:not([aria-disabled="true"])')];
  m.addEventListener("keydown", (ev) => {
    const lista = itensFoco();
    const i = lista.indexOf(document.activeElement);
    const alvo = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: lista.length - 1 }[ev.key];
    if (alvo == null) return;
    ev.preventDefault();
    lista[(alvo + lista.length) % lista.length].focus();
  });
  m.addEventListener("toggle", (ev) => {
    gatilho.setAttribute("aria-expanded", String(ev.newState === "open"));
    if (ev.newState === "open") {
      const r = em ? { left: em.x, right: em.x, bottom: em.y } : gatilho.getBoundingClientRect();
      const largura = m.offsetWidth;
      const folga = parseFloat(token("e-1"));
      const margem = parseFloat(token("e-2"));
      m.style.top = `${Math.min(r.bottom + folga, innerHeight - m.offsetHeight - margem)}px`;
      // alinha pela esquerda do botão; perto da borda direita da janela, pela direita
      const esquerda = r.left + largura <= innerWidth - margem ? r.left : r.right - largura;
      m.style.left = `${Math.max(margem, esquerda)}px`;
      itensFoco()[0]?.focus();
    } else {
      if (m.contains(document.activeElement) || document.activeElement === document.body) gatilho.focus();
      if (descartar) setTimeout(() => m.remove(), duracao("rapida"));
    }
  });
  if (em) {
    document.body.append(m);
    m.showPopover();
    return m;
  }
  gatilho.setAttribute("aria-haspopup", "menu");
  gatilho.setAttribute("aria-expanded", "false");
  gatilho.setAttribute("aria-controls", m.id);
  document.body.append(m);
  gatilho.popoverTargetElement = m; // o botão abre e fecha o popover sem brigar com o clique fora
  return m;
}
