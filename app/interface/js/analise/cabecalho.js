// Cabeçalho da Análise: equipamento e inspeção, navegação entre as inspeções do mesmo equipamento,
// estado "Salvo" e as ações (Detectar de novo, Mais opções, Gerar laudo).
import { TEXTOS as T } from "../../textos.js";
import { el, api, json, dataHora, data as dataCurta, pode } from "../base.js";
import { botao, selo, menu, confirmar, avisar } from "../componentes.js";
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

  // ---------------------------------------------------------------- Detectar de novo
  const detectar = botao({ texto: A.detectar, icone: "detectar" });
  const sam2 = ctx.modelos.find((m) => m.id === "sam2-dinov2");
  const rodar = (acao) => async () => {
    ctx.ocupado = "detectar";
    ctx.mudou("ocupado");
    detectar.setAttribute("aria-busy", "true");
    try { ctx.aplicar(await acao()); } catch (e) { avisar(e.message, { erro: true }); } finally {
      ctx.ocupado = null;
      detectar.removeAttribute("aria-busy");
      ctx.mudou("ocupado");
    }
  };
  const menuDetectar = menu(detectar, [
    { grupo: A.modeloAtual },
    ...ctx.modelos.map((m) => ({
      texto: m.nome, marcado: m.id === ctx.a.modelo?.id, desabilitado: m.disponivel === false,
      executar: rodar(() => api(`/api/analises/${ctx.a.id}/detectar`, json("POST", { modelo: m.id }))),
    })),
    { separador: true },
    { texto: sam2?.disponivel ? A.identificar : `${A.identificar}: ${A.indisponivel}`, icone: "detectar", desabilitado: !sam2?.disponivel,
      executar: rodar(() => api(`/api/analises/${ctx.a.id}/auto_identificar`, json("POST", {}))) },
  ]);

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
    [...menuDetectar.querySelectorAll('[role="menuitemradio"]')].forEach((b, i) => b.setAttribute("aria-checked", String(ctx.modelos[i]?.id === a.modelo?.id)));
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

  const parar = ctx.ouvir((parte) => { if (["tudo", "dados"].includes(parte)) desenhar(); if (parte === "salvo") desenharSalvo(); });
  desenhar();
  desenharSalvo();

  anterior.hidden = seguinte.hidden = !v.total;
  detectar.hidden = !pode("revisao"); // reprocessar é revisão (engenheiro)
  laudo.hidden = !pode("laudo");      // laudo: engenheiro que assina
  const cabecalho = el("header", { class: "cab-analise" },
    anterior,
    el("div", { class: "titulo" }, titulo, meta),
    seguinte,
    el("div", { class: "acoes" }, salvo, detectar, mais, laudo));
  return { cabecalho, encerrar() { parar(); menuDetectar.remove(); menuMais.remove(); } };
}
