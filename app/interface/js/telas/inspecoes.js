// Inspeções (Etapa 5a): a lista de todas as inspeções. Filtro de severidade com a contagem no próprio
// filtro, busca tolerante a acentos, ordenação pelo cabeçalho, seleção múltipla com barra de ações e o
// progresso da importação num lugar fixo. Filtros ficam no endereço (#inspecoes?sev=criticas&q=tr-01).
import { TEXTOS as T } from "../../textos.js";
import { el, icone, api, json, dataHora, temperatura, normalizar, animarEntrada } from "../base.js";
import { botao, campo, segmentado, tabela, selo, estadoVazio, avisar, dialogo, confirmar, menu, ocupado } from "../componentes.js";
import { endereco } from "../rotas.js";
import { escolherArquivos, importarDemonstracao, importacao, estadoImportacao, mostrarProgressoNaTela } from "../importar.js";
import { abrirLaudo } from "../laudo.js";
import { FILTROS_SEVERIDADE, quando, severidade, pesoSeveridade, situacaoAtual, leituraDestaque, miniatura, SEM_EQUIPAMENTO } from "../situacao.js";

const N = T.inspecoes;
const POR_PAGINA = 100;
const ORDENS = {
  data: (a, b) => quando(a).localeCompare(quando(b)),
  local: (a, b) => local(a).localeCompare(local(b), "pt-BR") || quando(a).localeCompare(quando(b)),
  tmax: (a, b) => (a.resumo?.t_max_cena ?? -999) - (b.resumo?.t_max_cena ?? -999),
  sev: (a, b) => pesoSeveridade(severidade(b)) - pesoSeveridade(severidade(a)) || (a.destaque?.pct_mta ?? 0) - (b.destaque?.pct_mta ?? 0),
};
const SENTIDO_INICIAL = { data: "desc", local: "asc", tmax: "desc", sev: "desc" };
const local = (it) => [it.identificacao?.equipamento, it.identificacao?.instalacao].filter(Boolean).join(" ");

export async function montar(pagina, rota) {
  const p = rota.params;
  const estado = {
    sev: FILTROS_SEVERIDADE[p.get("sev")] !== undefined ? p.get("sev") : "todas",
    q: p.get("q") || "",
    atual: p.get("atual") === "1",
    ordem: lerOrdem(p.get("ordem")),
    mostrar: POR_PAGINA,
    marcadas: new Set(),
  };
  let lista = [];
  let pendencias = new Map();
  let animada = false;

  async function carregar() {
    const [analises, pend] = await Promise.all([api("/api/analises"), api("/api/pendencias").catch(() => [])]);
    lista = analises;
    pendencias = new Map(pend.filter((x) => ["aberta", "programada"].includes(x.status)).map((x) => [x.id, x]));
    for (const id of [...estado.marcadas]) if (!lista.some((it) => it.id === id)) estado.marcadas.delete(id);
  }
  await carregar();

  // ---------------------------------------------------------------- estrutura fixa
  const importarBtn = botao({ texto: N.importar, icone: "importar", variante: "primario", atalho: "Ctrl O", onclick: escolherArquivos });
  const exportar = el("a", { class: "btn", href: "/api/inspecoes.csv", download: "" }, icone("baixar"), el("span", {}, N.exportar));
  const meta = el("span", { class: "num" });
  const cab = el("header", { class: "cabecalho" }, el("div", { class: "titulo" }, el("h1", {}, T.telas.inspecoes), el("div", { class: "meta" }, meta)), el("div", { class: "acoes" }, exportar, importarBtn));

  const faixa = faixaImportacao();
  const filtros = el("div", { class: "barra-lista" });
  const busca = el("input", { type: "search", class: "entrada", value: estado.q, placeholder: N.buscar, "aria-label": N.buscar, autocomplete: "off", spellcheck: "false",
    oninput: () => { estado.q = busca.value; estado.mostrar = POR_PAGINA; guardar(); desenharCorpo(); } });
  const caixaBusca = el("div", { class: "busca-lista" }, icone("busca"), busca);
  const corpo = el("div", { class: "corpo-lista" });
  const barraSelecao = el("div", { class: "barra-selecao", role: "toolbar", "aria-label": N.selecao, hidden: true });

  pagina.classList.add("tela-lista");
  pagina.append(cab, faixa.no, filtros, corpo);
  document.body.append(barraSelecao); // fora da página: a animação de entrada da página prenderia o position: fixed
  desenhar();

  // ---------------------------------------------------------------- desenho
  function visiveis() {
    const base = estado.atual ? situacaoAtual(lista) : lista;
    const niveis = FILTROS_SEVERIDADE[estado.sev];
    const termo = normalizar(estado.q);
    const passa = (it) => (!niveis || niveis.includes(severidade(it)))
      && (!termo || normalizar([it.arquivo, it.identificacao?.instalacao, it.identificacao?.equipamento, it.destaque?.nome].filter(Boolean).join(" ")).includes(termo));
    const f = ORDENS[estado.ordem.chave];
    const sinal = estado.ordem.sentido === "asc" ? 1 : -1;
    return { base, itens: base.filter(passa).sort((a, b) => sinal * f(a, b)) };
  }

  function desenhar() {
    const vazio = !lista.length;
    meta.textContent = vazio ? "" : N.total(lista.length);
    cab.querySelector(".acoes").hidden = vazio; // vazio: o primário é o do próprio estado vazio
    filtros.hidden = vazio;
    if (!vazio) desenharFiltros();
    desenharCorpo();
  }

  function desenharFiltros() {
    const base = estado.atual ? situacaoAtual(lista) : lista;
    const conta = (chave) => (FILTROS_SEVERIDADE[chave] ? base.filter((it) => FILTROS_SEVERIDADE[chave].includes(severidade(it))).length : base.length);
    const opcoes = Object.keys(FILTROS_SEVERIDADE)
      .filter((k) => k !== "sem" || conta("sem") || estado.sev === "sem")
      .map((k) => ({ valor: k, texto: N.filtros[k], qtd: conta(k) }));
    const seg = segmentado({ rotulo: N.filtroSeveridade, opcoes, valor: estado.sev, aoMudar: (v) => { estado.sev = v; estado.mostrar = POR_PAGINA; guardar(); desenharCorpo(); } });
    const chipAtual = estado.atual
      ? el("button", { type: "button", class: "chip compacto", title: N.atualDica, onclick: () => { estado.atual = false; guardar(); desenhar(); } }, el("span", {}, N.atual), icone("x", "ic p"))
      : null;
    filtros.replaceChildren(...[seg, chipAtual, el("span", { class: "empurrar" }), caixaBusca].filter(Boolean));
  }

  function desenharCorpo() {
    if (!lista.length) {
      corpo.replaceChildren(vazioInicial());
      desenharSelecao();
      return;
    }
    const { itens } = visiveis();
    if (!itens.length) {
      corpo.replaceChildren(estadoVazio({ ilustracao: "busca", titulo: N.nadaTitulo, texto: N.nadaTexto(estado.q.trim(), estado.sev === "todas" ? null : N.filtros[estado.sev]),
        acoes: [botao({ texto: N.limparFiltros, onclick: limparFiltros })] }));
      desenharSelecao();
      return;
    }
    const mostradas = itens.slice(0, estado.mostrar);
    const t = tabela({
      rotulo: T.telas.inspecoes,
      colunas: [
        { chave: "mini", titulo: el("span", { class: "so-leitor" }, N.colImagem), classe: "celula-mini", celula: (it) => el("img", { class: "miniatura", src: miniatura(it), alt: "", loading: "lazy", decoding: "async", width: 64, height: 48 }) },
        { chave: "data", titulo: N.colInspecao, ordenavel: true, link: true, classe: "celula-inspecao", celula: (it) => [el("span", { class: "corta", title: it.arquivo }, it.arquivo), el("span", { class: "sub" }, dataHora(quando(it)))] },
        { chave: "local", titulo: N.colEquipamento, ordenavel: true, classe: "celula-local", celula: celulaLocal },
        { chave: "regiao", titulo: N.colRegiao, classe: "celula-regiao", celula: celulaRegiao },
        { chave: "tmax", titulo: N.colTmax, ordenavel: true, classe: "num", celula: (it) => temperatura(it.resumo?.t_max_cena) },
        { chave: "sev", titulo: N.colSeveridade, ordenavel: true, celula: celulaSeveridade },
      ],
      linhas: mostradas,
      severidade,
      href: (it) => endereco("inspecoes", [it.id]),
      ordem: estado.ordem,
      aoOrdenar: (chave) => {
        estado.ordem = estado.ordem.chave === chave ? { chave, sentido: estado.ordem.sentido === "asc" ? "desc" : "asc" } : { chave, sentido: SENTIDO_INICIAL[chave] };
        guardar();
        desenharCorpo();
        corpo.querySelector(`th[aria-sort] button`)?.focus();
      },
      marcar: {
        todas: N.marcarTodas,
        rotulo: (it) => N.marcar(it.arquivo),
        marcada: (it) => estado.marcadas.has(it.id),
        aoMudar: (linhas, sim, todas) => {
          for (const it of linhas) (sim ? estado.marcadas.add(it.id) : estado.marcadas.delete(it.id));
          if (todas) desenharCorpo();
          else desenharSelecao();
        },
      },
      aoMenu: (it, ev) => menuLinha(it, ev),
    });
    if (!animada) { animarEntrada([...t.querySelectorAll("tbody tr")]); animada = true; } // só na chegada, não a cada letra da busca
    const restantes = itens.length - mostradas.length;
    corpo.replaceChildren(t);
    if (restantes > 0) corpo.append(el("div", { class: "mais-linhas" }, botao({ texto: N.mostrarMais(Math.min(POR_PAGINA, restantes), restantes), onclick: () => { estado.mostrar += POR_PAGINA; desenharCorpo(); } })));
    desenharSelecao();
  }

  function celulaLocal(it) {
    const id = it.identificacao || {};
    if (!id.equipamento) return el("span", { class: "fraco" }, N.semEquipamento);
    return [el("span", { class: "corta", title: id.equipamento }, id.equipamento), id.instalacao ? el("span", { class: "sub corta", title: id.instalacao }, id.instalacao) : null];
  }
  function celulaRegiao(it) {
    const d = it.destaque;
    if (!d) return el("span", { class: "fraco" }, T.geral.semValor);
    return [el("span", { class: "corta", title: d.nome }, d.nome), el("span", { class: "sub" }, leituraDestaque(d))];
  }
  function celulaSeveridade(it) {
    const p = pendencias.get(it.id);
    return el("div", { class: "celula-sev" }, selo(severidade(it), { indicativa: Boolean(it.resumo?.conferir) }),
      p ? el("span", { class: p.vencida ? "vencida" : "sub" }, p.vencida ? N.pendenciaVencida : N.pendenciaAberta) : null);
  }

  // ---------------------------------------------------------------- estado vazio (primeira inspeção)
  function vazioInicial() {
    const demo = botao({ texto: N.usarDemonstracao, onclick: () => usarDemonstracao(demo) });
    return estadoVazio({ ilustracao: "inspecoes", titulo: N.vazioTitulo, texto: N.vazioTexto,
      acoes: [botao({ texto: N.importar, icone: "importar", variante: "primario", atalho: "Ctrl O", onclick: escolherArquivos }), demo] });
  }

  // ---------------------------------------------------------------- seleção múltipla
  function marcadasEmOrdem() {
    const { itens } = visiveis();
    const ordem = itens.filter((it) => estado.marcadas.has(it.id));
    const fora = lista.filter((it) => estado.marcadas.has(it.id) && !ordem.includes(it));
    return [...ordem, ...fora];
  }

  function desenharSelecao() {
    const n = estado.marcadas.size;
    barraSelecao.hidden = !n;
    document.body.classList.toggle("com-selecao", n > 0);
    if (!n) return;
    const itens = marcadasEmOrdem();
    const semTemperatura = itens.filter((it) => severidade(it) === "sem_medida").length;
    const laudo = botao({ texto: N.gerarLaudo, icone: "laudo", onclick: () => gerarLaudo(itens.map((it) => it.id)) });
    if (semTemperatura) { laudo.setAttribute("aria-disabled", "true"); laudo.title = N.laudoSemTemperatura(semTemperatura); }
    barraSelecao.replaceChildren(
      el("span", { class: "qtd-selecao", role: "status" }, N.selecionadas(n)),
      laudo,
      botao({ texto: N.definirEquipamento, icone: "equipamentos", onclick: () => definirEquipamento(itens) }),
      botao({ texto: N.apagar, icone: "lixo", variante: "fantasma", onclick: () => apagar(itens) }),
      el("span", { class: "divisor", role: "separator", "aria-orientation": "vertical" }),
      botao({ texto: N.limparSelecao, icone: "x", variante: "fantasma", soIcone: true, atalho: "Esc", onclick: limparSelecao }),
    );
  }
  function limparSelecao() {
    estado.marcadas.clear();
    desenharCorpo();
  }

  async function gerarLaudo(ids) {
    if (ids.some((id) => severidade(lista.find((it) => it.id === id)) === "sem_medida")) return;
    try {
      abrirLaudo({ ids, config: await api("/api/configuracoes") });
    } catch (e) { avisar(e.message, { erro: true }); }
  }

  async function definirEquipamento(itens) {
    const equipamentos = await api("/api/equipamentos").catch(() => []);
    const comuns = (k) => { const v = new Set(itens.map((it) => it.identificacao?.[k] || "")); return v.size === 1 ? [...v][0] : ""; };
    const lista1 = el("datalist", { id: "lista-instalacoes" }, [...new Set(equipamentos.map((e) => e.instalacao).filter(Boolean))].map((v) => el("option", { value: v })));
    const lista2 = el("datalist", { id: "lista-equipamentos" }, [...new Set(equipamentos.map((e) => e.equipamento).filter(Boolean))].map((v) => el("option", { value: v })));
    const inst = campo({ rotulo: N.instalacao, valor: comuns("instalacao"), list: "lista-instalacoes", autocomplete: "off" });
    const equip = campo({ rotulo: N.equipamento, valor: comuns("equipamento"), list: "lista-equipamentos", autocomplete: "off", required: true });
    const erro = el("p", { class: "erro-dialogo", role: "alert", hidden: true });
    const salvar = botao({ texto: N.definir, variante: "primario", onclick: () => ocupado(salvar, async () => {
      const corpo = { ids: itens.map((it) => it.id), instalacao: inst.querySelector("input").value.trim(), equipamento: equip.querySelector("input").value.trim() };
      if (!corpo.equipamento) { erro.textContent = N.informeEquipamento; erro.hidden = false; equip.querySelector("input").focus(); return; }
      try {
        await api("/api/analises/identificacao", json("POST", corpo));
      } catch (e) { erro.textContent = e.message; erro.hidden = false; return; }
      dlg.fechar();
      avisar(N.equipamentoDefinido(itens.length, corpo.equipamento));
      await recarregar();
    }) });
    const dlg = dialogo({
      titulo: N.definirTitulo(itens.length),
      corpo: [el("p", { class: "nota" }, N.definirTexto), inst, equip, lista1, lista2, erro],
      acoes: [botao({ texto: T.geral.cancelar, onclick: () => dlg.fechar() }), salvar],
    }).abrir();
    equip.querySelector("input").focus();
  }

  async function apagar(itens) {
    const ok = await confirmar({ titulo: N.apagarTitulo(itens.length), texto: itens.length === 1 ? N.apagarTextoUma(itens[0].arquivo) : N.apagarTexto(itens.length), confirmar: N.apagar, perigo: true });
    if (!ok) return;
    let feitas = 0;
    for (const it of itens) {
      try {
        await api(`/api/analises/${it.id}`, { method: "DELETE" });
        feitas++;
        estado.marcadas.delete(it.id);
      } catch (e) { avisar(`${it.arquivo}: ${e.message}`, { erro: true }); }
    }
    if (feitas) avisar(N.apagadas(feitas));
    await recarregar();
  }

  function menuLinha(it, ev) {
    const sem = severidade(it) === "sem_medida";
    menu(ev.currentTarget.querySelector("a.forte") || corpo, [
      { texto: N.abrir, icone: "inspecoes", executar: () => { location.hash = endereco("inspecoes", [it.id]); } },
      { texto: sem ? `${N.gerarLaudo}: ${T.analise.laudoSemTemperatura}` : N.gerarLaudo, icone: "laudo", desabilitado: sem, executar: () => gerarLaudo([it.id]) },
      { texto: N.definirEquipamento, icone: "equipamentos", executar: () => definirEquipamento([it]) },
      it.equipamento_chave && it.equipamento_chave !== SEM_EQUIPAMENTO ? { texto: N.verEquipamento, icone: "equipamentos", executar: () => { location.hash = endereco("equipamentos", [it.equipamento_chave]); } } : null,
      { separador: true },
      { texto: N.apagar, icone: "lixo", perigo: true, executar: () => apagar([it]) },
    ].filter(Boolean), { em: { x: ev.clientX, y: ev.clientY }, descartar: true });
  }

  // ---------------------------------------------------------------- filtros no endereço
  function guardar() {
    const params = {};
    if (estado.sev !== "todas") params.sev = estado.sev;
    if (estado.q.trim()) params.q = estado.q.trim();
    if (estado.atual) params.atual = "1";
    if (estado.ordem.chave !== "data" || estado.ordem.sentido !== "desc") params.ordem = `${estado.ordem.chave}-${estado.ordem.sentido}`;
    history.replaceState(null, "", endereco("inspecoes", [], params));
  }
  function limparFiltros() {
    estado.sev = "todas";
    estado.q = "";
    estado.atual = false;
    busca.value = "";
    guardar();
    desenhar();
  }

  async function recarregar() {
    try { await carregar(); } catch (e) { avisar(e.message, { erro: true }); return; }
    desenhar();
  }

  async function usarDemonstracao(b) {
    await ocupado(b, async () => {
      try { await importarDemonstracao(); } catch (e) { avisar(e.message, { erro: true }); }
    });
  }

  // ---------------------------------------------------------------- importação: a lista enche enquanto importa
  let feitasAntes = estadoImportacao()?.feitas ?? 0;
  let relogio = null;
  const aoProgresso = (ev) => {
    faixa.mostrar(ev.detail);
    const feitas = ev.detail.ativa ? ev.detail.feitas : 0;
    if (ev.detail.ativa && feitas !== feitasAntes) { clearTimeout(relogio); relogio = setTimeout(recarregar, 600); }
    feitasAntes = feitas;
  };
  const aoImportar = () => { clearTimeout(relogio); recarregar(); };
  const soltarProgresso = mostrarProgressoNaTela();
  importacao.addEventListener("progresso", aoProgresso);
  document.addEventListener("pyron:importadas", aoImportar);
  faixa.mostrar(estadoImportacao() || { ativa: false });

  const teclado = (ev) => {
    if (ev.key === "Escape" && estado.marcadas.size && !document.querySelector("dialog[open], .menu:popover-open")) { limparSelecao(); ev.preventDefault(); }
    if (ev.key === "/" && !ev.target.closest("input, textarea, select") && lista.length) { busca.focus(); ev.preventDefault(); }
  };
  document.addEventListener("keydown", teclado);

  return () => {
    barraSelecao.remove();
    document.body.classList.remove("com-selecao");
    clearTimeout(relogio);
    soltarProgresso();
    importacao.removeEventListener("progresso", aoProgresso);
    document.removeEventListener("pyron:importadas", aoImportar);
    document.removeEventListener("keydown", teclado);
  };
}

function lerOrdem(texto) {
  const [chave, sentido] = String(texto || "").split("-");
  return ORDENS[chave] && ["asc", "desc"].includes(sentido) ? { chave, sentido } : { chave: "data", sentido: "desc" };
}

/** Faixa fixa no topo da lista: "Importando 3 de 12", o arquivo da vez e a barra determinada. */
function faixaImportacao() {
  const texto = el("b", {});
  const nome = el("span", { class: "mono corta" });
  const barra = el("div", { class: "barra", role: "progressbar", "aria-label": N.progresso, "aria-valuemin": "0" }, el("i", {}));
  const no = el("div", { class: "faixa-importacao", role: "status", hidden: true }, icone("importar"), el("div", { class: "texto-importacao" }, texto, nome), barra);
  return {
    no,
    mostrar(e) {
      no.hidden = !e.ativa;
      if (!e.ativa) return;
      texto.textContent = T.importar.enviando(e.i, e.n);
      nome.textContent = e.nome;
      nome.title = e.nome;
      barra.setAttribute("aria-valuemax", String(e.n));
      barra.setAttribute("aria-valuenow", String(e.i - 1));
      barra.firstChild.style.transform = `scaleX(${(e.i - 1) / e.n})`;
    },
  };
}
