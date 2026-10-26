// Pendências (Etapa 5b): cada anomalia até a correção verificada. Filtro por situação com a contagem
// dentro, busca, tabela e, ao escolher uma linha, o acompanhamento no painel ao lado (sem diálogo).
// Filtro, busca e a pendência aberta ficam no endereço (#pendencias?situacao=vencidas&id=<inspeção>).
import { TEXTOS as T } from "../../textos.js";
import { el, api, data, relativa, temperatura, normalizar, animarEntrada } from "../base.js";
import { botao, segmentado, campoBusca, tabela, selo, estadoVazio } from "../componentes.js";
import { endereco } from "../rotas.js";
import { formularioPendencia } from "../pendencia.js";

const P = T.pendencias;
const S = T.pendencia;
const FILTROS = {
  andamento: (p) => ["aberta", "programada", "corrigida"].includes(p.status),
  vencidas: (p) => p.vencida,
  reinspecao: (p) => p.status === "corrigida" || Boolean(p.reinspecao && !["verificada", "descartada"].includes(p.status)),
  concluidas: (p) => ["verificada", "descartada"].includes(p.status),
  todas: () => true,
};

export async function montar(pagina, rota) {
  let lista = await api("/api/pendencias");
  const params = rota.params;
  const estado = { filtro: FILTROS[params.get("situacao")] ? params.get("situacao") : "andamento", q: params.get("q") || "", id: params.get("id") || null };

  const meta = el("span", {});
  const cab = el("header", { class: "cabecalho" }, el("div", { class: "titulo" }, el("h1", {}, T.telas.pendencias), el("div", { class: "meta" }, meta)));
  pagina.classList.add("tela-lista");
  if (!lista.length) {
    pagina.append(cab, el("div", { class: "corpo-lista" }, estadoVazio({ ilustracao: "pendencias", titulo: P.vazioTitulo, texto: P.vazioTexto,
      acoes: [el("a", { class: "btn", href: endereco("inspecoes") }, P.verInspecoes)] })));
    return null;
  }

  let seg = el("div");
  const busca = campoBusca({ rotulo: P.buscar, valor: estado.q, aoMudar: (v) => { estado.q = v; guardar(); desenharTabela(); } });
  const filtros = el("div", { class: "barra-lista" }, seg, el("span", { class: "empurrar" }), busca);
  const areaTabela = el("div", { class: "area-lista" });
  const lado = el("aside", { class: "painel-lateral", "aria-label": P.painel });
  pagina.append(cab, filtros, el("div", { class: "corpo-lista com-lado" }, areaTabela, lado));
  let animada = false;
  desenhar();

  function desenhar() {
    meta.textContent = P.total(lista.length);
    const opcoes = Object.keys(FILTROS).map((k) => ({ valor: k, texto: P.filtros[k], qtd: lista.filter(FILTROS[k]).length }));
    seg.replaceWith(seg = segmentado({ rotulo: P.filtroSituacao, opcoes, valor: estado.filtro, aoMudar: (v) => { estado.filtro = v; guardar(); desenharTabela(); } }));
    desenharTabela();
    desenharLado();
  }

  function visiveis() {
    const termo = normalizar(estado.q);
    return lista.filter(FILTROS[estado.filtro]).filter((p) => !termo
      || normalizar([p.equipamento, p.instalacao, p.regiao, p.arquivo, p.ordem_servico, p.responsavel].filter(Boolean).join(" ")).includes(termo));
  }

  function desenharTabela() {
    const itens = visiveis();
    if (!itens.length) {
      areaTabela.replaceChildren(estadoVazio({ ilustracao: "busca", titulo: P.nadaTitulo, acoes: [botao({ texto: P.limparFiltros, onclick: limpar })] }));
      return;
    }
    const t = tabela({
      rotulo: T.telas.pendencias,
      colunas: [
        { chave: "sev", titulo: P.colSeveridade, celula: (p) => selo(p.severidade) },
        { chave: "equip", titulo: P.colEquipamento, link: true, celula: (p) => [
          el("span", { class: "corta", title: p.equipamento || p.arquivo }, p.equipamento || p.arquivo),
          el("span", { class: "sub corta" }, [p.instalacao || (p.equipamento ? null : P.semEquipamento), p.regiao, temperatura(p.t_max)].filter(Boolean).join(", ")),
        ] },
        { chave: "detectada", titulo: P.colDetectada, celula: (p) => data(p.detectada_em) },
        { chave: "prazo", titulo: P.colPrazo, celula: celulaPrazo },
        { chave: "situacao", titulo: P.colSituacao, celula: (p) => [el("span", {}, S.status[p.status]), p.reinspecao && !["verificada", "descartada"].includes(p.status) ? el("span", { class: "sub" }, P.normalEm(data(p.reinspecao.data))) : null] },
        { chave: "os", titulo: P.colOs, celula: (p) => p.ordem_servico || el("span", { class: "fraco" }, T.geral.semValor) },
        { chave: "resp", titulo: P.colResponsavel, celula: (p) => (p.responsavel ? el("span", { class: "corta", title: p.responsavel }, p.responsavel) : el("span", { class: "fraco" }, T.geral.semValor)) },
      ],
      linhas: itens,
      severidade: (p) => p.severidade,
      selecionada: (p) => p.id === estado.id,
      aoEscolher: (p) => escolher(p.id),
    });
    if (!animada) { animarEntrada([...t.querySelectorAll("tbody tr")]); animada = true; }
    areaTabela.replaceChildren(t);
  }

  function celulaPrazo(p) {
    const andando = ["aberta", "programada"].includes(p.status);
    return [el("span", {}, data(p.prazo)), andando ? el("span", { class: p.vencida ? "vencida" : "sub" }, p.vencida ? P.vencidaHa(relativa(p.prazo)) : P.vence(relativa(p.prazo))) : null];
  }

  // ---------------------------------------------------------------- painel ao lado
  function desenharLado() {
    const p = lista.find((x) => x.id === estado.id);
    if (!p) {
      lado.replaceChildren(estadoVazio({ icone: "pendencias", titulo: P.escolha, texto: P.escolhaTexto, compacto: true }));
      return;
    }
    const cabLado = el("div", { class: "cab-lado" },
      el("img", { class: "miniatura-lado", src: `/api/analises/${p.id}/miniatura.png?v=${p.severidade}`, alt: "", decoding: "async" }),
      el("div", { class: "titulo-lado" }, el("h2", { class: "corta", title: p.equipamento || p.arquivo }, p.equipamento || p.arquivo),
        el("p", { class: "nota" }, [p.instalacao, p.regiao, temperatura(p.t_max)].filter(Boolean).join(", ")),
        el("p", { class: "nota" }, P.detectadaEm(data(p.detectada_em)))),
      el("a", { class: "btn compacto", href: endereco("inspecoes", [p.id]) }, P.abrirInspecao));
    lado.replaceChildren(cabLado, ...formularioPendencia(p, { primario: true, aoSalvar: async () => { lista = await api("/api/pendencias"); desenhar(); } }).filter(Boolean));
  }

  function escolher(id) {
    estado.id = id;
    guardar();
    desenharTabela();
    desenharLado();
    areaTabela.querySelector('tr[aria-selected="true"] button.escolher')?.focus({ preventScroll: true });
  }

  // ↑ ↓ percorrem as pendências da lista com o foco nela
  areaTabela.addEventListener("keydown", (ev) => {
    if (!["ArrowDown", "ArrowUp"].includes(ev.key)) return;
    const itens = visiveis();
    const i = itens.findIndex((p) => p.id === estado.id);
    const alvo = itens[Math.min(itens.length - 1, Math.max(0, i + (ev.key === "ArrowDown" ? 1 : -1)))];
    if (alvo) { ev.preventDefault(); escolher(alvo.id); }
  });

  function guardar() {
    const q = {};
    if (estado.filtro !== "andamento") q.situacao = estado.filtro;
    if (estado.q.trim()) q.q = estado.q.trim();
    if (estado.id) q.id = estado.id;
    history.replaceState(null, "", endereco("pendencias", [], q));
  }
  function limpar() {
    estado.filtro = "todas";
    estado.q = "";
    busca.entrada.value = "";
    guardar();
    desenhar();
  }
  return null;
}
