// Acompanhamento de uma anomalia (situação, prazo, OS, responsável, nota e histórico). O mesmo formulário
// serve à aba Pendência da Análise e ao painel de Pendências; a nota entra no histórico ao salvar.
import { TEXTOS as T } from "../textos.js";
import { el, api, json, data, dataHora, relativa } from "./base.js";
import { botao, campo, secao, avisar, ocupado } from "./componentes.js";
import { endereco } from "./rotas.js";

const P = T.pendencia;

/** Seções do formulário; aoSalvar(pendênciaNova) roda depois do servidor aceitar. */
export function formularioPendencia(p, { primario = false, aoSalvar } = {}) {
  const situacao = campo({ rotulo: P.situacao, opcoes: Object.entries(P.status).map(([valor, texto]) => ({ valor, texto })), valor: p.status });
  const prazo = campo({ rotulo: P.prazo, tipo: "date", valor: p.prazo, ajuda: p.vencida ? P.vencida(relativa(p.prazo)) : ["aberta", "programada"].includes(p.status) ? P.vence(relativa(p.prazo)) : null });
  const os = campo({ rotulo: P.os, valor: p.ordem_servico || "", marcador: P.osExemplo, autocomplete: "off", maxlength: "40" });
  const resp = campo({ rotulo: P.responsavel, valor: p.responsavel || "", marcador: P.responsavelExemplo, autocomplete: "off", maxlength: "80" });
  const nota = campo({ rotulo: P.nota, area: true, marcador: P.notaExemplo, maxlength: "500", rows: "2" });
  const salvar = botao({ texto: P.salvar, variante: primario ? "primario" : "secundario", compacto: !primario, onclick: () => ocupado(salvar, async () => {
    try {
      const nova = await api(`/api/analises/${p.id}/acompanhamento`, json("PUT", {
        status: situacao.querySelector("select").value, prazo: prazo.querySelector("input").value || null,
        ordem_servico: os.querySelector("input").value, responsavel: resp.querySelector("input").value, nota: nota.querySelector("textarea").value,
      }));
      avisar(P.salva(P.status[nova.status]));
      await aoSalvar?.(nova);
    } catch (e) { avisar(e.message, { erro: true }); }
  }) });
  // reinspeção normal depois da detecção: sugere marcar como verificada
  const dica = p.reinspecao && !["verificada", "descartada"].includes(p.status)
    ? el("p", { class: "dica-reinspecao" }, P.reinspecaoTexto(data(p.reinspecao.data)), " ", el("a", { href: endereco("inspecoes", [p.reinspecao.id]) }, P.verReinspecao))
    : null;
  const hist = (p.historico || []).slice().reverse();
  return [
    secao({ titulo: P.acompanhamento, conteudo: [
      dica, el("div", { class: "grade-campos-2" }, situacao, prazo), el("div", { class: "grade-campos-2" }, os, resp), nota, el("div", { class: "grupo-btn" }, salvar),
    ] }),
    hist.length ? secao({ titulo: P.historico, qtd: hist.length, aberta: false, conteudo: [el("ol", { class: "lista-historico" }, hist.map((h) => el("li", {},
      el("span", { class: "nota" }, dataHora(h.quando)), el("b", {}, P.status[h.status] || h.status), h.nota ? el("span", {}, h.nota) : null)))] }) : null,
  ];
}
