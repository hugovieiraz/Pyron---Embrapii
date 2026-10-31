// Regiões da Análise: a ordem (da mais grave para a mais fria), a lista da lateral e apagar com Desfazer.
// A lista ficava numa faixa horizontal abaixo do termograma; voltou para a lateral (31/10/2026, pedido do Hugo:
// com muitas regiões, a faixa obrigava a rolar de lado).
import { TEXTOS as T } from "../../textos.js";
import { el, temperatura } from "../base.js";
import { avisar } from "../componentes.js";

const A = T.analise;
export const ORDEM_SEVERIDADE = ["imediato", "urgente", "programar", "atencao", "normal", "nao_avaliado", "sem_medida"];

export function regioesOrdenadas(regioes) {
  return [...regioes].sort((a, b) => ORDEM_SEVERIDADE.indexOf(a.severidade) - ORDEM_SEVERIDADE.indexOf(b.severidade) || (b.medida?.t_max ?? -999) - (a.medida?.t_max ?? -999));
}

/** Apaga a região e oferece Desfazer (a região volta no mesmo lugar da lista). */
export function apagarRegiao(ctx, id) {
  if (!ctx.podeEditar) return;
  const lista = ctx.a.regioes;
  const i = lista.findIndex((r) => r.id === id);
  if (i < 0) return;
  const removida = lista[i];
  if (ctx.sel === id) ctx.sel = null;
  ctx.salvarRegioes(lista.filter((r) => r.id !== id)).then(() => {
    avisar(A.regiaoApagada(removida.nome), {
      acao: { rotulo: T.geral.desfazer, executar: () => {
        const atual = [...ctx.a.regioes];
        atual.splice(Math.min(i, atual.length), 0, removida);
        ctx.salvarRegioes(atual).then(() => { ctx.selecionar(removida.id); avisar(A.regiaoRestaurada(removida.nome)); }).catch((e) => avisar(e.message, { erro: true }));
      } },
    });
  }).catch((e) => avisar(e.message, { erro: true }));
}

/** Lista das regiões na lateral (Resumo), uma linha por região, da mais grave para a mais fria. Passar o mouse
 * realça a caixa na imagem; clicar abre a região no painel; setas para cima e para baixo percorrem; Delete apaga. */
export function listaRegioes(ctx, realcar) {
  const regioes = regioesOrdenadas(ctx.a.regioes);
  const lista = el("div", { class: "lista-regioes", role: "listbox", "aria-label": A.regioes, tabindex: "-1" });
  lista.append(...regioes.map((r, i) => el("button", {
    type: "button", role: "option", class: `linha-regiao sev-${r.severidade}`, "aria-selected": "false", tabindex: i === 0 ? "0" : "-1",
    dataset: { id: r.id }, title: `${r.nome}: ${r.severidade_rotulo || T.niveis[r.severidade] || ""}`,
    onclick: () => ctx.selecionar(r.id),
    onmouseenter: () => realcar(r.id, true), onmouseleave: () => realcar(r.id, false),
    onfocus: () => realcar(r.id, true), onblur: () => realcar(r.id, false),
  }, el("span", { class: "traco", "aria-hidden": "true" }), el("span", { class: "nome" }, r.nome), el("b", { class: "num" }, temperatura(r.medida?.t_max)))));

  lista.addEventListener("keydown", (ev) => {
    const linhas = [...lista.querySelectorAll(".linha-regiao")];
    const i = linhas.indexOf(document.activeElement);
    if (i < 0) return;
    if (ev.key === "Delete") { ev.preventDefault(); apagarRegiao(ctx, linhas[i].dataset.id); return; }
    const alvo = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: linhas.length - 1 }[ev.key];
    if (alvo == null) return;
    ev.preventDefault();
    linhas.forEach((l) => { l.tabIndex = -1; });
    const l = linhas[(alvo + linhas.length) % linhas.length];
    l.tabIndex = 0;
    l.focus();
  });
  return lista;
}
