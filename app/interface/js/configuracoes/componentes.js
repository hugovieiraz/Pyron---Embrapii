// Configurações › Componentes: quanto cada componente aguenta (MTA). Valor do fabricante quando houver; sem ele,
// a prática brasileira. Dielétricos (para-raios, isoladores) não usam MTA: são avaliados pelo ΔT entre fases.
// Salvar é explícito porque recalcula todas as inspeções.
import { TEXTOS as T } from "../../textos.js";
import { el, api, json, fmt, lerNumero } from "../base.js";
import { botao, campo, avisar, confirmar, ocupado } from "../componentes.js";

const C = T.config;

export async function montar(no) {
  let cfg = await api("/api/configuracoes");
  const erro = el("p", { class: "erro-dialogo", role: "alert", hidden: true });
  const corpo = el("tbody");

  function preencher() {
    corpo.replaceChildren(...Object.entries(cfg.componentes).map(([classe, c]) => {
      const dieletrico = c.aquecimento === "dieletrico";
      const alterado = cfg.componentes_padrao[classe] && cfg.componentes_padrao[classe].mta_c !== c.mta_c;
      const mta = dieletrico ? el("span", { class: "fraco" }, C.naoSeAplica)
        : campo({ rotulo: C.mtaDe(c.nome), tipo: "number", valor: c.mta_c != null ? fmt(c.mta_c, 0) : "", unidade: "°C", classe: "campo-tabela", "data-classe": classe });
      return el("tr", { class: alterado ? "alterado" : null },
        el("th", { scope: "row" }, el("span", { class: "forte" }, c.nome), el("span", { class: "sub mono" }, classe)),
        el("td", {}, C.aquecimento[c.aquecimento] || c.aquecimento),
        el("td", {}, mta, alterado ? el("span", { class: "sub" }, C.padraoEra(fmt(cfg.componentes_padrao[classe].mta_c, 0))) : null),
        el("td", { class: "celula-fonte" }, el("span", { class: "corta", title: c.fonte }, c.fonte)));
    }));
  }

  const ler = () => Object.fromEntries([...corpo.querySelectorAll("input[data-classe]")].map((i) => [i.dataset.classe, { mta_c: lerNumero(i.value), fonte: cfg.componentes[i.dataset.classe]?.fonte }]));
  async function salvar(valor, b, mensagem) {
    await ocupado(b, async () => {
      try { cfg = await api("/api/configuracoes", json("PUT", { componentes: valor })); erro.hidden = true; preencher(); avisar(mensagem); } catch (e) { erro.textContent = e.message; erro.hidden = false; }
    });
  }
  const salvarBtn = botao({ texto: C.compSalvar, variante: "primario", onclick: () => salvar(ler(), salvarBtn, C.compSalvo) });
  const padraoBtn = botao({ texto: C.restaurarPadrao, variante: "fantasma", onclick: async () => {
    if (!(await confirmar({ titulo: C.compPadraoTitulo, texto: C.compPadraoTexto, confirmar: C.restaurarPadrao }))) return;
    await salvar(null, padraoBtn, C.compRestaurado);
  } });

  preencher();
  no.append(el("div", { class: "coluna-config larga" },
    el("div", { class: "titulo-bloco" }, el("h2", {}, C.compTitulo)),
    el("p", { class: "nota" }, C.compNota),
    erro,
    el("div", { class: "tabela-caixa" }, el("table", { class: "tabela tabela-componentes", "aria-label": C.compTitulo },
      el("thead", {}, el("tr", {}, [C.colComponente, C.colAquecimento, C.colMta, C.colFonte].map((t) => el("th", { scope: "col" }, t)))), corpo)),
    el("div", { class: "rodape-form" }, padraoBtn, salvarBtn)));
  return null;
}
