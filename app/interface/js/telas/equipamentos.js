// Equipamentos (Etapa 5b): os ativos agrupados por instalação, com estado, última inspeção, tendência da
// máxima e próxima inspeção. Filtro com a contagem dentro (com anomalia, inspeção vencida, esquentando)
// e busca; filtros no endereço (#equipamentos?filtro=vencidas&q=bay). O detalhe é js/telas/equipamento.js.
import { TEXTOS as T } from "../../textos.js";
import { el, api, data, relativa, temperatura, normalizar, animarEntrada } from "../base.js";
import { botao, segmentado, tabela, selo, estadoVazio, campoBusca } from "../componentes.js";
import { endereco } from "../rotas.js";
import { SEM_EQUIPAMENTO, ESQUENTANDO } from "../situacao.js";
import { seloTendencia, miniSerie } from "../grafico.js";

const E = T.equipamentos;
const FILTROS = {
  todos: () => true,
  anomalia: (e) => ["atencao", "programar", "urgente", "imediato"].includes(e.severidade),
  vencidas: (e) => Boolean(e.proxima_inspecao?.vencida),
  esquentando: (e) => (e.tendencia?.por_mes ?? 0) > ESQUENTANDO,
};

export async function montar(pagina, rota) {
  const todos = await api("/api/equipamentos");
  const reais = todos.filter((e) => e.chave !== SEM_EQUIPAMENTO);
  const sem = todos.find((e) => e.chave === SEM_EQUIPAMENTO);
  const estado = { filtro: FILTROS[rota.params.get("filtro")] ? rota.params.get("filtro") : "todos", q: rota.params.get("q") || "" };
  const instalacoes = new Set(reais.map((e) => e.instalacao || E.semInstalacao));
  const destinoDefinir = endereco("inspecoes", [], sem ? { equipamento: "sem" } : null);

  const cab = el("header", { class: "cabecalho" }, el("div", { class: "titulo" }, el("h1", {}, T.telas.equipamentos),
    reais.length ? el("div", { class: "meta" }, el("span", {}, E.total(reais.length, instalacoes.size))) : null));
  pagina.classList.add("tela-lista");
  if (!reais.length) {
    pagina.append(cab, el("div", { class: "corpo-lista" }, estadoVazio({ ilustracao: "equipamentos", titulo: E.vazioTitulo, texto: E.vazioTexto,
      acoes: [el("a", { class: "btn primario", href: destinoDefinir }, E.definirEmInspecoes)] })));
    return null;
  }

  const busca = campoBusca({ rotulo: E.buscar, valor: estado.q, aoMudar: (v) => { estado.q = v; guardar(); desenhar(); } });
  const opcoes = Object.keys(FILTROS).map((k) => ({ valor: k, texto: E.filtros[k], qtd: reais.filter(FILTROS[k]).length }));
  const seg = segmentado({ rotulo: E.filtro, opcoes, valor: estado.filtro, aoMudar: (v) => { estado.filtro = v; guardar(); desenhar(); } });
  seg.querySelector('[data-valor="esquentando"]').title = E.esquentandoDica;
  const filtros = el("div", { class: "barra-lista" }, seg, el("span", { class: "empurrar" }), busca);
  const corpo = el("div", { class: "corpo-lista" });
  const rodape = sem ? el("p", { class: "nota-lista" }, E.semEquipTexto(sem.inspecoes), " ", el("a", { href: destinoDefinir }, E.definirEmInspecoes)) : null;
  pagina.append(cab, filtros, corpo);
  let animada = false;
  desenhar();

  function desenhar() {
    const termo = normalizar(estado.q);
    const itens = reais.filter(FILTROS[estado.filtro]).filter((e) => !termo || normalizar(`${e.instalacao} ${e.equipamento}`).includes(termo));
    if (!itens.length) {
      corpo.replaceChildren(estadoVazio({ ilustracao: "busca", titulo: E.nadaTitulo, acoes: [botao({ texto: E.limparFiltros, onclick: limpar })] }));
      return;
    }
    // instalação com o pior equipamento primeiro; dentro dela, a ordem do servidor (pior estado primeiro)
    const ordemInst = [...new Set(itens.map((e) => e.instalacao || E.semInstalacao))];
    const ordenados = ordemInst.flatMap((inst) => itens.filter((e) => (e.instalacao || E.semInstalacao) === inst));
    const t = tabela({
      rotulo: T.telas.equipamentos,
      grupo: (e) => e.instalacao || E.semInstalacao,
      colunas: [
        { chave: "mini", titulo: el("span", { class: "so-leitor" }, E.colImagem), classe: "celula-mini", celula: (e) => el("img", { class: "miniatura", src: `/api/analises/${e.ultima_id}/miniatura.png?v=${e.severidade}-${e.inspecoes}`, alt: "", loading: "lazy", decoding: "async", width: 64, height: 48 }) },
        { chave: "equipamento", titulo: E.colEquipamento, link: true, celula: (e) => [el("span", { class: "corta", title: e.equipamento }, e.equipamento), el("span", { class: "sub" }, `${E.inspecoes(e.inspecoes)}, ${E.desde(data(e.primeira))}`)] },
        { chave: "estado", titulo: E.colEstado, celula: (e) => selo(e.severidade) },
        { chave: "ultima", titulo: E.colUltima, celula: (e) => [el("span", {}, data(e.ultima)), el("span", { class: "sub" }, relativa(e.ultima))] },
        { chave: "tmax", titulo: E.colTmax, classe: "num", celula: (e) => temperatura(e.t_max) },
        { chave: "tendencia", titulo: E.colTendencia, celula: (e) => el("div", { class: "celula-tendencia" }, miniSerie(e.serie), seloTendencia(e.tendencia)) },
        { chave: "proxima", titulo: E.colProxima, celula: celulaProxima },
      ],
      linhas: ordenados,
      severidade: (e) => e.severidade,
      href: (e) => endereco("equipamentos", [e.chave]),
    });
    if (!animada) { animarEntrada([...t.querySelectorAll("tbody tr:not(.linha-grupo)")]); animada = true; }
    corpo.replaceChildren(t);
    if (rodape && estado.filtro === "todos" && !termo) corpo.append(rodape);
  }

  function celulaProxima(e) {
    const p = e.proxima_inspecao;
    if (!p) return el("span", { class: "fraco" }, T.geral.semValor);
    return [el("span", {}, data(p.data)), el("span", { class: p.vencida ? "vencida" : "sub" }, p.vencida ? E.vencidaHa(relativa(p.data)) : relativa(p.data))];
  }
  function guardar() {
    const params = {};
    if (estado.filtro !== "todos") params.filtro = estado.filtro;
    if (estado.q.trim()) params.q = estado.q.trim();
    history.replaceState(null, "", endereco("equipamentos", [], params));
  }
  function limpar() {
    estado.filtro = "todos";
    estado.q = "";
    busca.entrada.value = "";
    seg.definir("todos");
    guardar();
    desenhar();
  }
  return null;
}
