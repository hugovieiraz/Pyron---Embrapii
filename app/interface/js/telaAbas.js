// Tela com abas (Captura, Modelos, Configurações): cabeçalho, abas e a área da aba ativa. Cada aba é um
// módulo com montar(no, ctx) que pode devolver a limpeza. Trocar de aba não recarrega a tela; o endereço
// acompanha (#tela/aba) com history.replaceState. Erro e falta de conexão aparecem dentro da aba.
import { TEXTOS as T } from "../textos.js";
import { el } from "./base.js";
import { abas, esqueleto, estadoErro, estadoSemConexao } from "./componentes.js";
import { endereco } from "./rotas.js";

/**
 * telaComAbas(pagina, rota, { tela, titulo, rotulo, abas: [{ id, texto, qtd }], carregar(id), meta, ctx })
 * carregar(id) devolve o import() do módulo da aba (o caminho fica em quem chama). A primeira aba é a padrão.
 * Devolve { limpar(), contar(id, n) }.
 */
export async function telaComAbas(pagina, rota, { tela, titulo, rotulo, abas: itens, carregar, meta = null, ctx = {} }) {
  const ids = itens.map((a) => a.id);
  const padrao = ids[0];
  let ativa = ids.includes(rota.partes[0]) ? rota.partes[0] : padrao;
  let limpar = null;
  let geracao = 0;

  const lista = abas({ rotulo, ativa, itens, aoMudar: (id) => mostrar(id, []) });
  const area = el("div", { class: "area-abas", role: "tabpanel", id: `painel-${ativa}`, "aria-labelledby": `aba-${ativa}`, tabindex: "-1" });
  pagina.classList.add("tela-abas");
  pagina.append(el("header", { class: "cabecalho" }, el("div", { class: "titulo" }, el("h1", {}, titulo), meta)), lista, area);

  async function mostrar(id, partes) {
    const minha = ++geracao;
    limpar?.();
    limpar = null;
    ativa = id;
    lista.escolher(id);
    area.id = `painel-${id}`;
    area.setAttribute("aria-labelledby", `aba-${id}`);
    if (!partes.length) history.replaceState(null, "", endereco(tela, id === padrao ? [] : [id]));
    area.replaceChildren(esqueleto.linhas(4));
    try {
      const modulo = await carregar(id);
      const no = el("div", { class: "conteudo-aba entra" });
      const r = await modulo.montar(no, { ...ctx, partes });
      if (minha !== geracao) { if (typeof r === "function") r(); return; }
      limpar = typeof r === "function" ? r : null;
      area.replaceChildren(no);
    } catch (erro) {
      if (minha !== geracao) return;
      const semServidor = erro.message === T.geral.semResposta || /dynamically imported module|Failed to fetch/i.test(erro.message);
      area.replaceChildren(semServidor ? estadoSemConexao({ tentar: () => mostrar(id, partes) }) : estadoErro({ titulo: itens.find((a) => a.id === id).texto, erro, tentar: () => mostrar(id, partes) }));
    }
  }

  /** Contagem ao lado do nome da aba (alertas pendentes, por exemplo); 0 tira. */
  function contar(id, n) {
    const aba = lista.querySelector(`#aba-${id}`);
    aba.querySelector(".qtd")?.remove();
    if (n) aba.append(el("span", { class: "qtd" }, String(n)));
  }

  await mostrar(ativa, rota.partes.slice(1));
  return { limpar: () => { geracao++; limpar?.(); }, contar };
}
