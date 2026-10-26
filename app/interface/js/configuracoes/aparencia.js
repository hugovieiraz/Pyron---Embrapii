// Configurações › Aparência: tema claro (padrão), escuro ou o do Windows. Vale na hora e fica guardado.
import { TEXTOS as T } from "../../textos.js";
import { el, api, json } from "../base.js";
import { segmentado, avisar } from "../componentes.js";

const C = T.config;

export async function montar(no) {
  const cfg = await api("/api/configuracoes");
  const tema = segmentado({ rotulo: C.tema, valor: cfg.tema, opcoes: ["claro", "escuro", "sistema"].map((v) => ({ valor: v, texto: C.temas[v] })),
    aoMudar: async (v) => {
      document.dispatchEvent(new CustomEvent("pyron:tema", { detail: v })); // a casca aplica
      try { await api("/api/configuracoes", json("PUT", { tema: v })); } catch (e) { avisar(e.message, { erro: true }); }
    } });
  no.append(el("div", { class: "coluna-config" },
    el("div", { class: "titulo-bloco" }, el("h2", {}, C.aparenciaTitulo)),
    el("div", { class: "campo" }, el("span", { class: "rotulo" }, C.tema), tema),
    el("p", { class: "nota" }, C.temaNota)));
  return null;
}
