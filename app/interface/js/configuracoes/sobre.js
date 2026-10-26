// Configurações › Sobre: versão, o detector em uso, onde ficam os dados e os modelos, e os créditos
// (dataset de estudo, fonte da marca). Sem texto de apresentação: isso fica no README.
import { TEXTOS as T } from "../../textos.js";
import { el, api } from "../base.js";

const C = T.config;

export async function montar(no) {
  const [s, modelos] = await Promise.all([api("/api/sistema"), api("/api/modelos").catch(() => ({ ativo: null, modelos: [] }))]);
  const ativo = modelos.modelos.find((m) => m.id === modelos.ativo);
  no.append(el("div", { class: "coluna-config sobre" },
    el("div", { class: "marca-sobre" },
      el("img", { class: "logo-claro", src: "/marca/logo-cor.svg", alt: "Pyron", width: 192, height: 64 }),
      el("img", { class: "logo-escuro", src: "/marca/logo-escuro.svg", alt: "Pyron", width: 192, height: 64 }),
      el("p", { class: "num" }, C.versao(s.versao))),
    el("dl", { class: "pares" },
      el("dt", {}, C.detector), el("dd", {}, ativo ? ativo.nome : T.geral.semValor),
      el("dt", {}, C.pastaDados), el("dd", { class: "mono corta", title: s.pasta_dados }, s.pasta_dados),
      el("dt", {}, C.pastaModelos), el("dd", { class: "mono corta", title: s.pasta_modelos }, s.pasta_modelos)),
    el("div", { class: "titulo-bloco" }, el("h2", {}, C.antigaTitulo)),
    el("p", { class: "nota" }, C.antigaTexto),
    el("div", { class: "grupo-btn" }, el("a", { class: "btn compacto", href: "/antiga/" }, C.antigaAbrir)),
    el("div", { class: "titulo-bloco" }, el("h2", {}, C.creditos)),
    el("ul", { class: "lista-avisos" }, C.listaCreditos.map((c) => el("li", {}, c)))));
  return null;
}
