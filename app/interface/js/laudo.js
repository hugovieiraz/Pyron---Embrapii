// Gerar laudo (uma inspeção na Análise, várias em Inspeções). O servidor só gera com responsável do
// cadastro. O PDF é pedido com o diálogo aberto e o fim mostra "Laudo pronto" com Abrir e Salvar:
// abrir depende de um clique (o navegador bloqueia janela aberta depois de esperar o servidor).
import { TEXTOS as T } from "../textos.js";
import { el, icone, json, conexao } from "./base.js";
import { botao, campo, dialogo, ocupado } from "./componentes.js";
import { ilustracao } from "./ilustracoes.js";

const L = T.laudo;

async function pedirPdf(ids, responsavel, art) {
  let r;
  try {
    r = ids.length === 1
      ? await fetch(`/api/analises/${encodeURIComponent(ids[0])}/laudo.pdf?${new URLSearchParams({ responsavel, art })}`)
      : await fetch("/api/laudos", json("POST", { ids, responsavel, art }));
  } catch {
    conexao.dispatchEvent(new Event("caiu"));
    throw new Error(T.geral.semResposta);
  }
  if (!r.ok) {
    const corpo = await r.json().catch(() => ({}));
    throw new Error(corpo.erro || corpo.detail || T.geral.erroServidor(r.status));
  }
  const nome = /filename="([^"]+)"/.exec(r.headers.get("content-disposition") || "")?.[1] || "laudo.pdf";
  return { url: URL.createObjectURL(await r.blob()), nome };
}

/**
 * abrirLaudo({ ids, config, responsavel, art }): diálogo com responsável e ART; ao gerar, o mesmo
 * diálogo vira o fim da tarefa (ilustração do laudo, Abrir laudo e Salvar PDF).
 */
export function abrirLaudo({ ids, config, responsavel = null, art = "" }) {
  const resps = config?.responsaveis || [];
  if (!resps.length) {
    dialogo({ titulo: L.titulo(ids.length), corpo: [el("p", {}, L.semResponsavel)], acoes: [el("a", { class: "btn primario", href: "/#configuracoes/identidade" }, L.cadastrar)] }).abrir();
    return;
  }
  const escolhido = [responsavel, config.responsavel_padrao, resps[0].id].find((id) => id && resps.some((r) => r.id === id));
  const resp = campo({ rotulo: L.responsavel, opcoes: resps.map((r) => ({ valor: r.id, texto: [r.nome, r.registro].filter(Boolean).join(", ") })), valor: escolhido });
  const campoArt = campo({ rotulo: L.art, valor: art || "", marcador: L.artMarcador, autocomplete: "off" });
  const erro = el("p", { class: "erro-dialogo", role: "alert", hidden: true });
  let pdf = null;

  const gerar = botao({ texto: L.gerar, icone: "laudo", variante: "primario", onclick: () => ocupado(gerar, async () => {
    erro.hidden = true;
    try {
      pdf = await pedirPdf(ids, resp.querySelector("select").value, campoArt.querySelector("input").value.trim());
    } catch (e) {
      erro.textContent = e.message;
      erro.hidden = false;
      return;
    }
    mostrarPronto(resp.querySelector("select").selectedOptions[0].textContent);
  }) });

  const dlg = dialogo({
    titulo: L.titulo(ids.length),
    corpo: [ids.length > 1 ? el("p", { class: "nota" }, L.ordem(ids.length)) : null, resp, campoArt, erro],
    acoes: [botao({ texto: T.geral.cancelar, onclick: () => dlg.fechar() }), gerar],
    aoFechar: () => { if (pdf) setTimeout(() => URL.revokeObjectURL(pdf.url), 60000); },
  }).abrir();

  // fim da tarefa (Peak-End): o resultado, quem assina e as duas saídas
  function mostrarPronto(quem) {
    const abrir = () => window.open(pdf.url, "_blank"); // PDF do próprio Pyron; com noopener o endereço blob: pode não abrir
    const salvar = el("a", { class: "btn", href: pdf.url, download: pdf.nome }, icone("baixar"), el("span", {}, L.salvar));
    const abrirBtn = botao({ texto: L.abrir, icone: "externo", variante: "primario", onclick: abrir });
    dlg.no.querySelector(".cab-dialogo h2").textContent = L.pronto;
    dlg.no.querySelector(".corpo-dialogo").replaceChildren(el("div", { class: "laudo-pronto", role: "status" },
      ilustracao("laudo", { rotulo: L.pronto }), el("p", {}, L.prontoTexto(ids.length, quem)), el("p", { class: "nota mono", title: pdf.nome }, pdf.nome)));
    dlg.no.querySelector(".rodape-dialogo").replaceChildren(salvar, abrirBtn);
    abrirBtn.focus();
  }
}
