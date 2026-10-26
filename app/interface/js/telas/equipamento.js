// Equipamento (Etapa 5b): histórico e tendência de um ativo. Migalhas, quatro indicadores (estado,
// máxima na última, tendência, próxima inspeção), gráfico da máxima por inspeção, peças e a lista de
// inspeções. Primário: Relatório do equipamento. Rota: #equipamentos/<chave>.
import { TEXTOS as T } from "../../textos.js";
import { el, api, data, relativa, temperatura } from "../base.js";
import { botao, selo, segmentado, estadoVazio, avisar } from "../componentes.js";
import { endereco } from "../rotas.js";
import { escolherArquivos } from "../importar.js";
import { abrirLaudo } from "../laudo.js";
import { graficoSerie, seloTendencia } from "../grafico.js";
import { SEM_EQUIPAMENTO, severidade, quando, leituraDestaque, miniatura, nomeClasse } from "../situacao.js";

const E = T.equipamentos;

export async function montar(pagina, rota) {
  const chave = rota.partes[0];
  if (chave === SEM_EQUIPAMENTO) { location.replace(endereco("inspecoes", [], { equipamento: "sem" })); return null; }
  let d;
  try {
    d = await api(`/api/equipamentos/${encodeURIComponent(chave)}`);
  } catch (erro) {
    if (erro.status !== 404) throw erro;
    pagina.append(estadoVazio({ ilustracao: "busca", titulo: E.naoEncontrado, texto: E.naoEncontradoTexto, acoes: [el("a", { class: "btn primario", href: endereco("equipamentos") }, E.verEquipamentos)] }));
    return null;
  }
  const config = await api("/api/configuracoes").catch(() => null);
  document.title = T.casca.titulo(d.equipamento);
  pagina.classList.add("tela-equipamento");

  // ---------------------------------------------------------------- cabeçalho com migalhas
  const migalhas = el("nav", { class: "migalhas", "aria-label": E.caminho }, el("ol", {},
    el("li", {}, el("a", { href: endereco("equipamentos") }, T.telas.equipamentos)),
    el("li", {}, d.instalacao ? el("a", { href: endereco("equipamentos", [], { q: d.instalacao }) }, d.instalacao) : E.semInstalacao),
    el("li", { "aria-current": "page" }, d.equipamento)));
  const adicionar = botao({ texto: E.adicionar, icone: "importar", title: E.adicionarDica, onclick: () => escolherArquivos({ instalacao: d.instalacao, equipamento: d.equipamento }) });
  const relatorio = botao({ texto: E.relatorio, icone: "laudo", variante: "primario", onclick: async () => {
    const ids = [...d.lista].reverse().map((it) => it.id).slice(-60); // da mais antiga para a mais nova
    try { abrirLaudo({ ids, config: config || await api("/api/configuracoes") }); } catch (e) { avisar(e.message, { erro: true }); }
  } });
  const cab = el("header", { class: "cabecalho" },
    el("div", { class: "titulo" }, migalhas, el("h1", {}, d.equipamento),
      el("div", { class: "meta" }, selo(d.severidade), el("span", {}, `${E.inspecoes(d.inspecoes)}, ${E.desde(data(d.primeira))}`))),
    el("div", { class: "acoes" }, adicionar, relatorio));

  // ---------------------------------------------------------------- indicadores
  const ultimo = d.serie[d.serie.length - 1] || {};
  const prox = d.proxima_inspecao;
  const temPlena = d.serie.filter((p) => p.elevacao_plena != null).length >= 2;
  let modo = temPlena && d.tendencia_plena ? "plena" : "medida";
  const bloco = (rotulo, valor, nota) => el("div", { class: "indicador" }, el("span", { class: "rotulo" }, rotulo), el("span", { class: "valor-bloco" }, valor), nota ? el("span", { class: "nota" }, nota) : null);
  const indicadores = el("div", { class: "indicadores-linha" },
    bloco(E.estado, selo(d.severidade), E.ultimaEm(data(d.ultima))),
    bloco(E.tmaxUltima, el("b", { class: "num" }, temperatura(d.t_max)), ultimo.regiao || null),
    el("div"), // tendência: preenchida por atualizarTendencia() (muda com a série do gráfico)
    prox ? bloco(E.proxima, el("b", { class: "num" }, data(prox.data)), prox.vencida ? el("span", { class: "vencida" }, E.vencidaHa(relativa(prox.data))) : E.prazoDias(prox.prazo_dias)) : null);
  // ---------------------------------------------------------------- gráfico (medida ou a plena carga)
  const caixaGrafico = el("div", { class: "caixa-grafico" });
  let grafico = null;
  function desenharGrafico() {
    grafico?.encerrar();
    const plena = modo === "plena";
    grafico = graficoSerie({
      titulo: plena ? E.graficoPlena : E.grafico,
      pontos: d.serie.map((p) => ({ ...p, valor: plena ? p.elevacao_plena : p.t_max, rotulo: p.regiao })),
      tendencia: Boolean(plena ? d.tendencia_plena : d.tendencia),
      href: (p) => endereco("inspecoes", [p.id]),
    });
    caixaGrafico.replaceChildren(grafico.no);
  }
  const troca = temPlena ? segmentado({ rotulo: E.serie, valor: modo, opcoes: [{ valor: "medida", texto: E.serieMedida }, { valor: "plena", texto: E.seriePlena }],
    aoMudar: (v) => { modo = v; desenharGrafico(); atualizarTendencia(); } }) : null;
  if (troca) troca.title = E.plenaDica;
  const tituloGrafico = el("h2", {}, modo === "plena" ? E.graficoPlena : E.grafico);
  const secaoGrafico = el("section", { class: "bloco-grafico", "aria-label": E.grafico },
    el("div", { class: "titulo-bloco" }, tituloGrafico, troca), caixaGrafico, el("p", { class: "nota" }, E.graficoDica));
  function atualizarTendencia() {
    tituloGrafico.textContent = modo === "plena" ? E.graficoPlena : E.grafico;
    const antigo = indicadores.children[2];
    const t = modo === "plena" ? d.tendencia_plena : d.tendencia;
    const pm = d.projecao_mta;
    antigo.replaceWith(bloco(modo === "plena" ? E.tendenciaPlena : E.tendencia, seloTendencia(t), pm ? E.chegaMta(data(pm.data)) + (pm.confiavel ? "" : E.estimativaFraca) : null));
  }

  // ---------------------------------------------------------------- peças e inspeções
  const pecas = d.componentes.filter((c) => c.pontos.length);
  const secaoPecas = pecas.length > 1 || (pecas.length === 1 && pecas[0].classe !== "ponto_quente")
    ? el("section", { class: "bloco-pecas", "aria-label": E.pecas },
      el("div", { class: "titulo-bloco" }, el("h2", {}, E.pecas)),
      el("table", { class: "tabela tabela-simples", "aria-label": E.pecas },
        el("thead", {}, el("tr", {}, [E.colPeca, E.colMax, E.colTend, E.colSev].map((t, i) => el("th", { scope: "col", class: i === 1 ? "num" : null }, t)))),
        el("tbody", {}, pecas.map((c) => el("tr", {},
          el("td", {}, nomeClasse(c.classe, config)), el("td", { class: "num" }, temperatura(c.t_max)), el("td", {}, seloTendencia(c.tendencia)), el("td", {}, selo(c.severidade)))))))
    : null;

  const lista = el("section", { class: "coluna-inspecoes", "aria-label": E.historico },
    el("div", { class: "titulo-bloco" }, el("h2", {}, E.historico), el("span", { class: "nota" }, String(d.lista.length))),
    el("ul", { class: "lista-recentes" }, d.lista.map((it) => el("li", {}, el("a", { href: endereco("inspecoes", [it.id]) },
      el("img", { class: "miniatura", src: miniatura(it), alt: "", loading: "lazy", decoding: "async", width: 64, height: 48 }),
      el("span", { class: "eq" }, el("b", {}, data(quando(it))), el("span", { class: "corta" }, [it.destaque?.nome, leituraDestaque(it.destaque)].filter(Boolean).join(", ") || it.arquivo)),
      el("span", { class: "quando num" }, temperatura(it.destaque?.t_max ?? it.resumo?.t_max_cena)),
      selo(severidade(it), { indicativa: Boolean(it.resumo?.conferir) }))))));

  pagina.append(cab, indicadores, el("div", { class: "equipamento-grade" }, el("div", { class: "coluna-grafico" }, secaoGrafico, secaoPecas), lista));
  atualizarTendencia();
  desenharGrafico();

  // imagens novas deste equipamento: recarrega a tela para entrar no histórico
  const aoImportar = () => { if (location.hash.startsWith(endereco("equipamentos", [chave]))) dispatchEvent(new HashChangeEvent("hashchange")); };
  document.addEventListener("pyron:importadas", aoImportar);
  return () => { grafico?.encerrar(); document.removeEventListener("pyron:importadas", aoImportar); };
}
