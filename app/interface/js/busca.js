// Busca rápida (Ctrl+K): telas, ações, inspeções e equipamentos num só campo, sem acento e sem ordem de palavras.
import { TEXTOS as T } from "../textos.js";
import { el, icone, api, normalizar, data } from "./base.js";
import { ROTAS, endereco } from "./rotas.js";

const MAX_POR_GRUPO = 6;
let aberta = null;

/** acoes = [{ texto, icone, executar }] vindas da casca (importar, atalhos, tema). */
export async function abrirBusca(acoes = []) {
  if (aberta) return;
  const idLista = "busca-resultados";
  const entrada = el("input", {
    type: "text", role: "combobox", "aria-expanded": "true", "aria-controls": idLista, "aria-autocomplete": "list",
    "aria-label": T.busca.rotulo, placeholder: T.busca.marcador, autocomplete: "off", spellcheck: "false",
  });
  const lista = el("ul", { role: "listbox", id: idLista, "aria-label": T.busca.rotulo });
  const d = el("dialog", { class: "busca-rapida", "aria-label": T.busca.rotulo },
    el("div", { class: "campo-busca" }, icone("busca"), entrada, el("kbd", {}, "Esc")),
    lista,
    el("div", { class: "dicas", "aria-hidden": "true" }, el("span", {}, T.busca.dicaNavegar), el("span", {}, T.busca.dicaAbrir), el("span", {}, T.busca.dicaFechar)));
  aberta = d;
  document.body.append(d);
  d.showModal();
  d.addEventListener("close", () => { d.remove(); aberta = null; });
  d.addEventListener("click", (ev) => { if (ev.target === d) d.close(); });

  const fixos = [
    ...Object.entries(ROTAS).map(([id, r]) => ({ grupo: T.busca.grupoTelas, texto: r.titulo, sub: `Alt ${r.atalho}`, icone: r.icone, ir: endereco(id) })),
    ...acoes.map((a) => ({ grupo: T.busca.grupoAcoes, ...a })),
  ];
  let dados = [];
  let carregando = true;
  Promise.all([api("/api/analises").catch(() => []), api("/api/equipamentos").catch(() => [])]).then(([insp, equips]) => {
    dados = [
      ...equips.filter((e) => e.equipamento).map((e) => ({ grupo: T.busca.grupoEquipamentos, texto: e.equipamento, sub: e.instalacao, icone: "equipamentos", ir: endereco("equipamentos", [e.chave]) })),
      ...insp.map((a) => ({ grupo: T.busca.grupoInspecoes, texto: a.arquivo, sub: [a.identificacao?.equipamento, data(a.criado_em)].filter(Boolean).join(", "), icone: "inspecoes", ir: endereco("inspecoes", [a.id]) })),
    ];
    carregando = false;
    desenhar();
  });

  let itens = [];
  let atual = 0;
  function desenhar() {
    const termos = normalizar(entrada.value).split(" ").filter(Boolean);
    const casa = (i) => { const alvo = normalizar(`${i.texto} ${i.sub || ""}`); return termos.every((t) => alvo.includes(t)); };
    const grupos = new Map();
    for (const i of [...fixos, ...dados]) {
      if (!casa(i)) continue;
      if (!grupos.has(i.grupo)) grupos.set(i.grupo, []);
      if (grupos.get(i.grupo).length < MAX_POR_GRUPO) grupos.get(i.grupo).push(i);
    }
    itens = [...grupos.values()].flat();
    atual = Math.min(atual, Math.max(0, itens.length - 1));
    lista.replaceChildren();
    let n = 0;
    for (const [grupo, membros] of grupos) {
      lista.append(el("li", { class: "grupo-res", role: "presentation" }, grupo));
      for (const i of membros) {
        const indice = n++;
        lista.append(el("li", {
          role: "option", id: `res-${indice}`, "aria-selected": String(indice === atual),
          onclick: () => executar(i), onmousemove: () => { if (atual !== indice) { atual = indice; marcar(); } },
        }, icone(i.icone || "proxima"), el("span", {}, i.texto), i.sub ? el("span", { class: "sub" }, i.sub) : null));
      }
    }
    if (!itens.length) lista.append(el("li", { class: "nada", role: "presentation" }, carregando ? T.busca.carregando : T.busca.nada(entrada.value.trim())));
    marcar();
  }
  function marcar() {
    lista.querySelectorAll('[role="option"]').forEach((o, i) => o.setAttribute("aria-selected", String(i === atual)));
    const sel = lista.querySelector(`#res-${atual}`);
    entrada.setAttribute("aria-activedescendant", sel ? sel.id : "");
    sel?.scrollIntoView({ block: "nearest" });
  }
  function executar(i) {
    d.close();
    if (i.ir) location.hash = i.ir.replace(/^#/, "");
    else i.executar?.();
  }
  entrada.addEventListener("input", () => { atual = 0; desenhar(); });
  entrada.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      if (itens.length) { atual = (atual + (ev.key === "ArrowDown" ? 1 : -1) + itens.length) % itens.length; marcar(); }
    } else if (ev.key === "Enter" && itens[atual]) {
      ev.preventDefault();
      executar(itens[atual]);
    }
  });
  desenhar();
  entrada.focus();
}
