// Painel de detalhe da Análise: Resumo ou Região selecionada, Condições, Identificação e Pendência.
// Edições salvam sozinhas (indicador "Salvo" no cabeçalho); ações que recalculam têm botão próprio.
import { TEXTOS as T } from "../../textos.js";
import { el, api, json, fmt, temperatura, data, dataHora, lerNumero } from "../base.js";
import { botao, campo, secao, selo, painelDetalhe, estadoVazio, avisar, ocupado } from "../componentes.js";
import { apagarRegiao } from "./faixa.js";

const A = T.analise;
const pct = (v) => fmt(v, 0, " %");
const dl = (pares) => el("dl", { class: "pares" }, pares.filter(Boolean).flatMap(([t, d]) => [el("dt", {}, t), el("dd", {}, d)]));

export function montarPainel(ctx, { equipamentos }) {
  const sam2 = ctx.modelos.find((m) => m.id === "sam2-dinov2")?.disponivel === true;

  // ---------------------------------------------------------------- resumo da inspeção (nenhuma região selecionada)
  function resumo() {
    const a = ctx.a;
    const r = a.resumo || {};
    const partes = [];
    if (ctx.ocupado === "detectar") partes.push(estadoVazio({ ilustracao: "analise", procurando: true, titulo: A.detectando, compacto: true }));
    else if (!a.regioes.length) partes.push(estadoVazio({ ilustracao: "analise", titulo: A.regioes, texto: A.semRegioes, compacto: true }));
    partes.push(secao({ titulo: A.situacao, conteudo: [
      el("div", { class: "linha-selo" }, selo(r.severidade || "sem_medida")),
      r.mensagem ? el("p", {}, r.mensagem) : null,
      dl([[A.tmaxCena, temperatura(r.t_max_cena)], r.maior_pct_mta != null && [A.maiorMta, pct(r.maior_pct_mta)], [A.regioesN, String(a.regioes.length)]]),
    ] }));
    const avisos = r.avisos || [];
    if (avisos.length) partes.push(secao({ titulo: A.avisos, qtd: avisos.length, aberta: false, conteudo: [el("ul", { class: "lista-avisos" }, avisos.map((t) => el("li", {}, t)))] }));
    const grupos = (r.comparacao_componentes || []).filter((g) => g.itens.length > 1);
    if (grupos.length) {
      partes.push(secao({ titulo: A.comparacao, conteudo: grupos.map((g) => el("div", { class: "grupo-fases" }, el("b", {}, g.nome),
        dl(g.itens.map((i) => [i.nome, `${temperatura(i.t_max)}${i.dt != null ? ` · ΔT ${fmt(i.dt, 1, " °C")}` : ""}`])))) }));
    }
    const meds = a.medicoes || [];
    partes.push(secao({ titulo: A.medicoes, qtd: meds.length, conteudo: meds.length ? [el("ul", { class: "lista-medicoes" }, meds.map((m, i) => {
      const v = m.valor || {};
      const nome = m.nome || (m.tipo === "ponto" ? A.pontoN(i + 1) : A.linhaN(i + 1));
      const valor = m.tipo === "ponto" ? temperatura(v.t) : A.linhaValor(fmt(v.t_max, 1), fmt(v.t_min, 1), fmt(v.t_med, 1));
      return el("li", {}, el("span", {}, nome), el("span", { class: "num" }, valor),
        botao({ texto: A.removerMedicao(nome), icone: "lixo", soIcone: true, compacto: true, variante: "fantasma", onclick: () => ctx.salvarMedicoes(meds.filter((x) => x.id !== m.id)).catch((e) => avisar(e.message, { erro: true })) }));
    }))] : [el("p", { class: "nota" }, A.semMedicoes)] }));
    return partes;
  }

  // ---------------------------------------------------------------- região selecionada
  function regiao(r) {
    const nomes = { ...(ctx.a.modelo?.nomes || {}) };
    const classes = [...new Set([...(ctx.a.modelo?.classes || []), r.classe, "componente"])];
    const salvarCampo = (mudanca) => ctx.salvarRegioes(ctx.a.regioes.map((x) => (x.id === r.id ? { ...x, ...mudanca } : x))).catch((e) => avisar(e.message, { erro: true }));
    const nome = campo({ rotulo: A.nome, valor: r.nome, autocomplete: "off", maxlength: "60" });
    nome.querySelector("input").addEventListener("change", (ev) => { const v = ev.target.value.trim(); if (v && v !== r.nome) salvarCampo({ nome: v }); });
    const classe = campo({ rotulo: A.classe, opcoes: classes.map((c) => ({ valor: c, texto: nomes[c] || c.replace(/_/g, " ").replace(/^./, (l) => l.toUpperCase()) })), valor: r.classe });
    classe.querySelector("select").addEventListener("change", (ev) => salvarCampo({ classe: ev.target.value }));

    const m = r.medida || {};
    const dt = r.dt_ref ?? r.dt_entorno;
    const rotuloDt = r.ref_tipo === "fase" || r.ref_tipo === "semelhante" ? A.dtFase : r.ref_tipo === "ambiente" ? A.dtAmbiente : A.dtEntorno;
    const leituras = el("div", { class: "leituras" },
      el("div", { class: "leitura-principal" }, el("span", { class: "rotulo" }, A.tmax), el("b", { class: "num" }, temperatura(m.t_max))),
      el("div", { class: "leituras-secundarias" },
        el("div", {}, el("span", { class: "rotulo" }, rotuloDt), el("b", { class: "num" }, fmt(dt, 1, " °C"))),
        el("div", {}, el("span", { class: "rotulo" }, A.pctMta), el("b", { class: "num" }, r.pct_mta != null ? pct(r.pct_mta) : T.geral.semValor))));

    const geo = r.segmentacao?.geometria;
    const dimensoes = geo?.height_meters != null
      ? dl([[A.dimensoes, A.dimAlturaLargura(fmt(geo.height_meters, 2), fmt(geo.mean_width_meters, 2))], [A.metodo, A.dimMetodo[geo.metodo_metrologia] || geo.metodo_metrologia],
          r.segmentacao.termica_isolada?.t_max != null && [A.tmaxPeca, temperatura(r.segmentacao.termica_isolada.t_max)]])
      : null;
    const medir = sam2 ? botao({ texto: A.medir, icone: "regua", compacto: true, title: A.medirDica, onclick: (ev) => ocupado(ev.currentTarget, async () => {
      try {
        const resp = await api(`/api/analises/${ctx.a.id}/segmentar`, json("POST", { regiao_id: r.id }));
        ctx.aplicar(resp.analise);
      } catch (e) { avisar(e.message, { erro: true }); }
    }) }) : null;

    return [
      el("div", { class: "cab-regiao" }, botao({ texto: A.voltarResumo, icone: "anterior", soIcone: true, compacto: true, variante: "fantasma", onclick: () => ctx.selecionar(null) }),
        selo(r.severidade, { indicativa: r.indicativa }), r.confianca != null && r.origem !== "manual" ? el("span", { class: "nota" }, A.confianca(Math.round(r.confianca * 100))) : el("span", { class: "nota" }, A.origemManual)),
      el("div", { class: "campos-regiao" }, nome, classe),
      secao({ titulo: A.leituras, conteudo: [leituras] }),
      secao({ titulo: A.diagnostico, conteudo: [
        el("p", { class: "rotulo-severidade" }, r.severidade_rotulo || T.niveis[r.severidade] || ""),
        r.criterio_disparo?.length ? dl([[A.criterio, r.criterio_disparo.join(" e ")]]) : null,
        r.acao ? el("p", {}, r.acao) : null,
        r.indicativa ? el("p", { class: "nota" }, T.indicativa) : null,
      ] }),
      r.referencia ? secao({ titulo: A.referencia, aberta: false, conteudo: [dl([[r.referencia.nome, r.referencia.mta_c != null ? `${A.mta} ${temperatura(r.referencia.mta_c, 0)}` : T.geral.semValor]]), r.referencia.fonte ? el("p", { class: "nota" }, r.referencia.fonte) : null] }) : null,
      dimensoes || medir ? secao({ titulo: A.dimensoes, conteudo: [dimensoes, medir ? el("div", { class: "grupo-btn" }, medir) : null] }) : null,
      el("div", { class: "rodape-painel" }, botao({ texto: A.apagarRegiao, icone: "lixo", variante: "perigo", compacto: true, onclick: () => apagarRegiao(ctx, r.id) })),
    ];
  }

  // ---------------------------------------------------------------- condições e parâmetros
  function condicoes() {
    const a = ctx.a;
    const c = a.condicoes || {};
    const amb = campo({ rotulo: A.ambiente, tipo: "number", unidade: "°C", valor: c.ambiente_c != null ? fmt(c.ambiente_c, 1) : "" });
    const carga = campo({ rotulo: A.carga, tipo: "number", unidade: "%", valor: c.carga_pct != null ? fmt(c.carga_pct, 0) : "" });
    const ler = () => ({ condicoes: { ambiente_c: lerNumero(amb.querySelector("input").value), carga_pct: lerNumero(carga.querySelector("input").value) } });
    [amb, carga].forEach((f) => f.querySelector("input").addEventListener("input", () => ctx.salvarDepois("condicoes", ler, 900)));
    const partes = [secao({ titulo: A.ambienteCarga, conteudo: [el("div", { class: "grade-campos-2" }, amb, carga), el("p", { class: "nota" }, A.cargaAjuda)] })];

    if (a.radiometrica) {
      const md = a.metadados || {};
      const p = {
        emissividade: campo({ rotulo: A.emissividade, tipo: "number", valor: md.emissividade != null ? fmt(md.emissividade, 2) : "" }),
        temp_refletida_c: campo({ rotulo: A.refletida, tipo: "number", unidade: "°C", valor: md.temp_refletida_c != null ? fmt(md.temp_refletida_c, 1) : "" }),
        distancia_m: campo({ rotulo: A.distancia, tipo: "number", unidade: "m", valor: md.distancia_m != null ? fmt(md.distancia_m, 1) : "" }),
        umidade_relativa: campo({ rotulo: A.umidade, tipo: "number", unidade: "%", valor: md.umidade_relativa != null ? fmt(md.umidade_relativa * 100, 0) : "" }),
        temp_atmosfera_c: campo({ rotulo: A.ar, tipo: "number", unidade: "°C", valor: md.temp_atmosfera_c != null ? fmt(md.temp_atmosfera_c, 1) : "" }),
      };
      const aplicar = (corpo, b, msg) => ocupado(b, async () => {
        try { ctx.aplicar(await api(`/api/analises/${a.id}/parametros`, json("POST", corpo))); avisar(msg); } catch (e) { avisar(e.message, { erro: true }); }
      });
      const ajustados = a.parametros_ajustados?.length;
      partes.push(secao({ titulo: A.camera, aberta: Boolean(ajustados), conteudo: [
        el("div", { class: "grade-campos-2" }, ...Object.values(p)),
        el("div", { class: "grupo-btn" },
          botao({ texto: A.aplicar, compacto: true, onclick: (ev) => aplicar(Object.fromEntries(Object.entries(p).map(([k, f]) => [k, lerNumero(f.querySelector("input").value)])), ev.currentTarget, A.parametrosAplicados) }),
          ajustados ? botao({ texto: A.restaurarCamera, variante: "fantasma", compacto: true, onclick: (ev) => aplicar({ restaurar: true }, ev.currentTarget, A.parametrosRestaurados) }) : null),
      ] }));
    } else {
      const [lo, hi] = a.matriz_info?.faixa_exibicao || [];
      const tmin = campo({ rotulo: A.escalaMin, tipo: "number", unidade: "°C", valor: a.sem_temperatura ? "" : fmt(lo, 1) });
      const tmax = campo({ rotulo: A.escalaMax, tipo: "number", unidade: "°C", valor: a.sem_temperatura ? "" : fmt(hi, 1) });
      partes.push(secao({ titulo: A.escalaImagem, conteudo: [el("p", { class: "nota" }, A.escalaImagemAjuda), el("div", { class: "grade-campos-2" }, tmin, tmax),
        el("div", { class: "grupo-btn" }, botao({ texto: A.aplicarEscala, compacto: true, variante: a.sem_temperatura ? "primario" : "secundario", onclick: (ev) => ocupado(ev.currentTarget, async () => {
          try { ctx.aplicar(await api(`/api/analises/${a.id}/escala`, json("POST", { t_min: lerNumero(tmin.querySelector("input").value), t_max: lerNumero(tmax.querySelector("input").value) }))); } catch (e) { avisar(e.message, { erro: true }); }
        }) }))] }));
    }
    return partes;
  }

  // ---------------------------------------------------------------- identificação
  function identificacao() {
    const id = ctx.a.identificacao || {};
    const lista = (nome, valores) => el("datalist", { id: nome }, [...new Set(valores.filter(Boolean))].map((v) => el("option", { value: v })));
    const inst = campo({ rotulo: A.instalacao, valor: id.instalacao || "", list: "dl-instalacoes", autocomplete: "off" });
    const equip = campo({ rotulo: A.equipamento, valor: id.equipamento || "", list: "dl-equipamentos", autocomplete: "off" });
    const resps = ctx.config.responsaveis || [];
    const resp = campo({ rotulo: T.laudo.responsavel, opcoes: [{ valor: "", texto: A.semResponsavelOpcao }, ...resps.map((r) => ({ valor: r.id, texto: [r.nome, r.registro].filter(Boolean).join(", ") }))], valor: id.responsavel_id || "" });
    const art = campo({ rotulo: T.laudo.art, valor: id.art || "", marcador: T.laudo.artMarcador, autocomplete: "off" });
    const obs = campo({ rotulo: A.observacoes, area: true, valor: id.observacoes || "", marcador: A.observacoesMarcador });
    const ler = () => ({ identificacao: { ...id, instalacao: inst.querySelector("input").value.trim(), equipamento: equip.querySelector("input").value.trim(),
      responsavel_id: resp.querySelector("select").value, art: art.querySelector("input").value.trim(), observacoes: obs.querySelector("textarea").value.trim() } });
    for (const n of [inst, equip, art, obs]) n.querySelector("input, textarea").addEventListener("input", () => ctx.salvarDepois("identificacao", ler, 900));
    resp.querySelector("select").addEventListener("change", () => ctx.salvarDepois("identificacao", ler, 0));
    return [el("div", { class: "campos-regiao" }, inst, equip, resp, art, obs,
      lista("dl-instalacoes", equipamentos.map((e) => e.instalacao)), lista("dl-equipamentos", equipamentos.map((e) => e.equipamento)))];
  }

  // ---------------------------------------------------------------- pendência (acompanhamento da anomalia)
  function pendencia() {
    const p = ctx.a.pendencia;
    if (!p) return [estadoVazio({ ilustracao: "pendencias", titulo: A.semPendencia, compacto: true })];
    const situacao = campo({ rotulo: A.situacaoPend, opcoes: Object.entries(A.status).map(([valor, texto]) => ({ valor, texto })), valor: p.status });
    const prazo = campo({ rotulo: A.prazo, tipo: "date", valor: p.prazo, ajuda: p.vencida ? A.vencida(Math.abs(p.dias)) : p.dias != null ? A.faltam(p.dias) : null });
    const os = campo({ rotulo: A.os, valor: p.ordem_servico || "", autocomplete: "off", maxlength: "40" });
    const resp = campo({ rotulo: A.responsavelPend, valor: p.responsavel || "", autocomplete: "off", maxlength: "80" });
    const nota = campo({ rotulo: A.nota, area: true, marcador: A.notaMarcador, maxlength: "500" });
    const registrar = botao({ texto: A.registrar, variante: "secundario", compacto: true, onclick: (ev) => ocupado(ev.currentTarget, async () => {
      try {
        await api(`/api/analises/${ctx.a.id}/acompanhamento`, json("PUT", { status: situacao.querySelector("select").value, prazo: prazo.querySelector("input").value || null, ordem_servico: os.querySelector("input").value, responsavel: resp.querySelector("input").value, nota: nota.querySelector("textarea").value }));
        ctx.aplicar(await api(`/api/analises/${ctx.a.id}`));
        avisar(A.pendenciaAtualizada);
      } catch (e) { avisar(e.message, { erro: true }); }
    }) });
    const hist = (p.historico || []).slice().reverse();
    return [
      secao({ titulo: A.acompanhamento, conteudo: [el("div", { class: "linha-selo" }, selo(p.severidade), el("span", { class: p.vencida ? "vencida" : "nota" }, `${A.prazo} ${data(p.prazo)}`)), situacao, prazo, os, resp, nota, el("div", { class: "grupo-btn" }, registrar)] }),
      hist.length ? secao({ titulo: A.historico, qtd: hist.length, aberta: false, conteudo: [el("ul", { class: "lista-avisos" }, hist.map((h) => el("li", {}, `${dataHora(h.quando)} · ${A.status[h.status] || h.status}${h.nota ? `: ${h.nota}` : ""}`)))] }) : null,
    ];
  }

  // ---------------------------------------------------------------- montagem e redesenho
  const painel = painelDetalhe({
    rotulo: A.painel,
    itens: [
      { id: "resumo", icone: "info", texto: A.resumo, titulo: () => (ctx.regiao() ? null : A.resumo), montar: () => (ctx.regiao() ? regiao(ctx.regiao()) : resumo()) },
      { id: "condicoes", icone: "termometro", texto: A.condicoes, montar: condicoes },
      { id: "identificacao", icone: "etiqueta", texto: A.identificacao, montar: identificacao },
      { id: "pendencia", icone: "pendencias", texto: A.pendencia, montar: pendencia },
    ],
  });
  const formularios = new Set(["condicoes", "identificacao", "pendencia"]);
  const parar = ctx.ouvir((parte) => {
    if (parte === "selecao") { if (painel.ativa() !== "resumo") painel.mostrar("resumo"); else painel.atualizar(); return; }
    if (parte === "abrir-pendencia") { painel.mostrar("pendencia"); return; }
    if (parte === "tudo" || parte === "ocupado") painel.atualizar();
    if (parte === "dados" && !formularios.has(painel.ativa())) painel.atualizar();
  });
  return { painel, encerrar: parar };
}
