// Captura (Etapa 5c): as fontes de imagem que chegam sozinhas e o resultado delas. Abas Pasta monitorada,
// Vídeo, Celular e Alertas (decisão da Etapa 1); cada aba é um módulo em js/captura/ com montar(area, ctx)
// que devolve a limpeza. Trocar de aba não recarrega a tela; o endereço acompanha (#captura/video).
import { TEXTOS as T } from "../../textos.js";
import { el, api } from "../base.js";
import { abas, esqueleto, estadoErro, estadoSemConexao } from "../componentes.js";
import { endereco } from "../rotas.js";

const K = T.captura;
const ABAS = ["pasta", "video", "celular", "alertas"];

export async function montar(pagina, rota) {
  const status = await api("/api/status");
  let ativa = ABAS.includes(rota.partes[0]) ? rota.partes[0] : "pasta";
  let limpar = null;
  let geracao = 0;

  const meta = el("div", { class: "meta" });
  const lista = abas({ rotulo: K.abas, ativa, itens: ABAS.map((id) => ({ id, texto: K.aba[id], qtd: id === "alertas" && status.alertas_pendentes ? status.alertas_pendentes : null })),
    aoMudar: (id) => mostrar(id, []) });
  const area = el("div", { class: "area-captura", role: "tabpanel", id: `painel-${ativa}`, "aria-labelledby": `aba-${ativa}`, tabindex: "-1" });
  pagina.classList.add("tela-captura");
  pagina.append(el("header", { class: "cabecalho" }, el("div", { class: "titulo" }, el("h1", {}, T.telas.captura), meta)), lista, area);

  // linha de estado no cabeçalho: o que está ligado agora (pasta vigiada, celular)
  function desenharMeta(s) {
    const m = s.monitoramento || {};
    meta.replaceChildren(el("span", { class: `estado-fonte${m.ativo && !m.erro ? " ligada" : m.erro && m.ativo ? " erro" : ""}` },
      m.ativo ? (m.erro ? K.metaErro : K.metaVigiando) : K.metaDesligado));
  }
  desenharMeta(status);

  async function mostrar(id, partes) {
    const minha = ++geracao;
    limpar?.();
    limpar = null;
    ativa = id;
    lista.escolher(id);
    area.id = `painel-${id}`;
    area.setAttribute("aria-labelledby", `aba-${id}`);
    if (!partes.length) history.replaceState(null, "", endereco("captura", id === "pasta" ? [] : [id]));
    area.replaceChildren(esqueleto.linhas(4));
    try {
      const modulo = await import(`../captura/${id}.js`);
      const no = el("div", { class: "conteudo-aba entra" });
      const r = await modulo.montar(no, { partes, aoMudarEstado: desenharMeta, contarAlertas: (n) => contar(n) });
      if (minha !== geracao) { if (typeof r === "function") r(); return; }
      limpar = typeof r === "function" ? r : null;
      area.replaceChildren(no);
    } catch (erro) {
      if (minha !== geracao) return;
      const semServidor = erro.message === T.geral.semResposta || /dynamically imported module|Failed to fetch/i.test(erro.message);
      area.replaceChildren(semServidor ? estadoSemConexao({ tentar: () => mostrar(id, partes) }) : estadoErro({ titulo: K.aba[id], erro, tentar: () => mostrar(id, partes) }));
    }
  }

  /** Contador da aba Alertas (pendentes) e o do sino, na casca. */
  function contar(n) {
    const aba = lista.querySelector("#aba-alertas");
    aba.querySelector(".qtd")?.remove();
    if (n) aba.append(el("span", { class: "qtd" }, String(n)));
    document.dispatchEvent(new CustomEvent("pyron:alertas"));
  }

  await mostrar(ativa, rota.partes.slice(1));
  return () => { geracao++; limpar?.(); };
}
