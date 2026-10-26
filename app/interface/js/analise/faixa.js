// Faixa de regiões abaixo do termograma: uma ficha por região, da mais grave para a mais fria.
// Passar o mouse realça a caixa na imagem; clicar seleciona; setas percorrem; Delete apaga com Desfazer.
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

export function montarFaixa(ctx, { realcar }) {
  const lista = el("div", { class: "lista-regioes", role: "listbox", "aria-label": A.regioes, "aria-orientation": "horizontal", tabindex: "-1" });
  const titulo = el("div", { class: "titulo-faixa estrutura-caixa" }, el("span", {}, A.regioes), el("span", { class: "qtd num" }));
  const faixa = el("div", { class: "faixa-regioes" }, titulo, lista);

  function desenhar() {
    const regioes = regioesOrdenadas(ctx.a.regioes);
    titulo.querySelector(".qtd").textContent = String(regioes.length);
    if (!regioes.length) { lista.replaceChildren(el("p", { class: "vazio-faixa" }, A.semRegioes)); return; }
    lista.replaceChildren(...regioes.map((r) => el("button", {
      type: "button", role: "option", class: `ficha sev-${r.severidade}`, "aria-selected": String(r.id === ctx.sel), tabindex: r.id === (ctx.sel || regioes[0].id) ? "0" : "-1",
      dataset: { id: r.id }, title: `${r.nome}: ${r.severidade_rotulo || T.niveis[r.severidade] || ""}`,
      onclick: () => ctx.selecionar(r.id === ctx.sel ? null : r.id),
      onmouseenter: () => realcar(r.id, true), onmouseleave: () => realcar(r.id, false),
      onfocus: () => realcar(r.id, true), onblur: () => realcar(r.id, false),
    }, el("span", { class: "traco", "aria-hidden": "true" }), el("span", { class: "nome" }, r.nome), el("b", { class: "num" }, temperatura(r.medida?.t_max)))));
    const sel = lista.querySelector('[aria-selected="true"]');
    sel?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  lista.addEventListener("keydown", (ev) => {
    const fichas = [...lista.querySelectorAll(".ficha")];
    const i = fichas.indexOf(document.activeElement);
    if (i < 0) return;
    if (ev.key === "Delete") { ev.preventDefault(); apagarRegiao(ctx, fichas[i].dataset.id); return; }
    const alvo = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: fichas.length - 1 }[ev.key];
    if (alvo == null) return;
    ev.preventDefault();
    const f = fichas[(alvo + fichas.length) % fichas.length];
    ctx.selecionar(f.dataset.id);
    lista.querySelector(`[data-id="${f.dataset.id}"]`)?.focus();
  });

  const parar = ctx.ouvir((parte) => { if (["tudo", "dados", "selecao"].includes(parte)) desenhar(); });
  desenhar();
  return { faixa, encerrar: parar };
}
