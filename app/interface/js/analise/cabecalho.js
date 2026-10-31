// Cabeçalho da Análise: equipamento e inspeção, navegação entre as inspeções do mesmo equipamento,
// estado "Salvo", as chaves do que aparece na imagem (Para-raios, Pontos quentes, Medição) e as ações (Mais opções,
// Gerar laudo). As chaves entraram no lugar de "Detectar de novo" em 31/10/2026: o modelo é sempre o mesmo
// (para-raios + pontos quentes), então reprocessar daria o mesmo resultado; o que muda é o que se quer ver.
import { TEXTOS as T } from "../../textos.js";
import { el, api, dataHora, data as dataCurta, pode } from "../base.js";
import { botao, chaves, selo, menu, confirmar, avisar } from "../componentes.js";
import { abrirLaudo as laudoDialogo } from "../laudo.js";
import { endereco } from "../rotas.js";

const A = T.analise;

function baixar(url) {
  const a = el("a", { href: url, download: "" });
  document.body.append(a);
  a.click();
  a.remove();
}

export function montarCabecalho(ctx) {
  const titulo = el("h1", { class: "titulo-analise" });
  const meta = el("div", { class: "meta" });
  const salvo = el("span", { class: "estado-salvo", role: "status" });
  const v = ctx.vizinhas || {};
  const irPara = (it) => () => { if (it) location.hash = endereco("inspecoes", [it.id]); };
  const anterior = botao({ texto: A.anterior, icone: "anterior", soIcone: true, variante: "fantasma", desabilitado: !v.anterior, onclick: irPara(v.anterior) });
  const seguinte = botao({ texto: A.seguinte, icone: "proxima", soIcone: true, variante: "fantasma", desabilitado: !v.seguinte, onclick: irPara(v.seguinte) });

  // ---------------------------------------------------------------- o que aparece na imagem (preferência guardada)
  const mostrar = chaves({
    rotulo: A.mostrarNaImagem,
    opcoes: [["regioes", A.mostrarParaRaios, A.mostrarParaRaiosDica], ["pontos", A.mostrarPontos, A.mostrarPontosDica], ["medicoes", A.mostrarMedicao, A.mostrarMedicaoDica]]
      .map(([chave, texto, dica]) => ({ chave, texto, dica, ligado: ctx.camadas[chave] })),
    aoMudar: (chave, ligado) => { ctx.camadas[chave] = ligado; ctx.guardarCamadas(); ctx.mudou("exibicao"); },
  });

  // ---------------------------------------------------------------- Mais opções
  const mais = botao({ texto: A.mais, icone: "mais-opcoes", soIcone: true });
  const menuMais = menu(mais, [
    { texto: A.exportarImagem, icone: "baixar", executar: () => baixar(`/api/analises/${ctx.a.id}/imagem.png?largura=1600`) },
    { texto: A.exportarCsv, icone: "baixar", executar: () => baixar(`/api/analises/${ctx.a.id}/temperaturas.csv`) },
    { texto: A.abrirOriginal, icone: "externo", executar: () => window.open(`/api/analises/${ctx.a.id}/original.jpg`, "_blank", "noopener") },
    ...(pode("revisao") ? [{ separador: true }, { texto: A.apagarInspecao, icone: "lixo", perigo: true, executar: async () => {
      if (!(await confirmar({ titulo: A.apagarTitulo, texto: A.apagarTexto(ctx.a.arquivo), confirmar: A.apagarInspecao, perigo: true }))) return;
      try { await api(`/api/analises/${ctx.a.id}`, { method: "DELETE" }); avisar(A.apagada); location.hash = endereco("inspecoes"); } catch (e) { avisar(e.message, { erro: true }); }
    } }] : []),
  ]);

  // ---------------------------------------------------------------- Gerar laudo
  const laudo = botao({ texto: A.laudo, icone: "laudo", variante: "primario", onclick: abrirLaudo });
  function abrirLaudo() {
    if (ctx.a.sem_temperatura) return;
    const id = ctx.a.identificacao || {};
    laudoDialogo({ ids: [ctx.a.id], config: ctx.config, responsavel: id.responsavel_id, art: id.art });
  }

  // ---------------------------------------------------------------- redesenho
  function desenhar() {
    const a = ctx.a;
    const id = a.identificacao || {};
    titulo.textContent = id.equipamento || a.arquivo;
    titulo.title = titulo.textContent;
    const quando = a.metadados?.data_hora || a.criado_em;
    meta.replaceChildren(...[
      selo(a.resumo?.severidade || "sem_medida"),
      a.sem_temperatura ? el("span", { class: "aviso-medida" }, A.semTemperaturaMeta) : !a.radiometrica && el("span", { class: "aviso-medida", title: a.origem }, A.estimadaMeta),
      id.instalacao && el("span", {}, id.instalacao),
      el("span", { class: "num" }, dataHora(quando)),
      id.equipamento && el("span", { title: a.arquivo, class: "arquivo" }, a.arquivo),
      a.metadados?.camera && a.metadados.camera !== "desconhecida" && el("span", {}, a.metadados.camera),
      v.total > 1 && el("span", { class: "num" }, A.posicao(v.posicao, v.total)),
      pendenciaNaMeta(a.pendencia),
    ].filter(Boolean));
    if (a.sem_temperatura) { laudo.setAttribute("aria-disabled", "true"); laudo.title = `${A.laudo}: ${A.laudoSemTemperatura}`; } else { laudo.removeAttribute("aria-disabled"); laudo.title = ""; }
    document.title = T.casca.titulo(id.equipamento ? `${id.equipamento} · ${a.arquivo}` : a.arquivo);
  }
  // pendência em aberto fica à vista no cabeçalho (o que falta fazer); clicar abre a aba Pendência
  function pendenciaNaMeta(p) {
    if (!p || !["aberta", "programada"].includes(p.status)) return null;
    const texto = p.vencida ? A.pendenciaVencida(dataCurta(p.prazo)) : A.pendenciaAberta(T.pendencia.status[p.status], dataCurta(p.prazo));
    return el("button", { type: "button", class: `link-pendencia${p.vencida ? " vencida" : ""}`, onclick: () => ctx.mudou("abrir-pendencia") }, texto);
  }
  function desenharSalvo() {
    const s = ctx.salvo;
    salvo.dataset.estado = s.estado;
    salvo.textContent = s.estado === "salvando" ? A.salvando : s.estado === "erro" ? A.erroSalvar : s.em ? A.salvoEm(s.em.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })) : "";
  }

  const marcarChaves = () => mostrar.querySelectorAll("button").forEach((b) => b.setAttribute("aria-checked", String(Boolean(ctx.camadas[b.dataset.chave]))));
  const parar = ctx.ouvir((parte) => {
    if (["tudo", "dados"].includes(parte)) desenhar();
    if (parte === "salvo") desenharSalvo();
    if (parte === "exibicao") marcarChaves();
  });
  desenhar();
  desenharSalvo();

  anterior.hidden = seguinte.hidden = !v.total;
  laudo.hidden = !pode("laudo");      // laudo: engenheiro que assina
  const cabecalho = el("header", { class: "cab-analise" },
    anterior,
    el("div", { class: "titulo" }, titulo, meta),
    seguinte,
    el("div", { class: "acoes" }, salvo, mostrar, mais, laudo));
  return { cabecalho, encerrar() { parar(); menuMais.remove(); } };
}
