// Modelos › Treino: das anotações do CVAT ao modelo instalado. Envia os rótulos (o Pyron confere cada imagem),
// mostra o que há para treinar e começa o treino aqui ou gera o pacote para treinar fora (Colab). Os treinos
// em andamento se atualizam a cada 2 s; o pronto vira "Usar este modelo".
import { TEXTOS as T } from "../../textos.js";
import { el, api, json, fmt } from "../base.js";
import { botao, campo, segmentado, secao, tabela, avisar, confirmar, dialogo, ocupado } from "../componentes.js";
import { ilustracao } from "../ilustracoes.js";

const R = T.treino;
const FINAIS = ["pronto", "erro", "cancelado", "interrompido"];

/** "Para-raios 2" vira "para-raios-2-20261026-0130" (pasta do modelo). */
function idDoNome(nome) {
  const base = nome.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 36) || "modelo";
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${base}-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}

export async function montar(no) {
  const [ambiente, inicial] = await Promise.all([api("/api/treinos/ambiente").catch((e) => ({ ok: false, mensagem: e.message })), api("/api/treinos")]);
  let treinos = inicial.treinos;
  let rotulos = null; // relatório dos rótulos enviados
  let relogio = null;

  const etapa = el("section", { class: "etapa-treino", "aria-label": R.novo });
  const lista = el("section", { class: "lista-treinos", "aria-label": R.treinos });
  const chipAmbiente = el("p", { class: `linha-estado-fonte${ambiente.ok ? " ligada" : " erro"}` }, el("i", { class: "ponto-estado", "aria-hidden": "true" }),
    el("span", {}, ambiente.ok ? ambiente.mensagem : R.ambienteBloqueado));
  no.append(...[el("div", { class: "barra-lista" }, chipAmbiente), ambiente.ok ? null : el("p", { class: "erro-dialogo" }, ambiente.mensagem), etapa, lista].filter(Boolean));
  desenharEtapa();
  desenharTreinos();

  // ---------------------------------------------------------------- 1. rótulos do CVAT
  function desenharEtapa() {
    if (!rotulos) {
      const entrada = el("input", { type: "file", accept: ".zip,.json", multiple: true, hidden: true, onchange: () => { if (entrada.files.length) enviarRotulos([...entrada.files]); entrada.value = ""; } });
      etapa.replaceChildren(el("div", { class: "vazio-treino" }, ilustracao("modelos", { rotulo: R.enviarTitulo }),
        el("div", {}, el("h2", {}, R.enviarTitulo), el("p", {}, R.enviarTexto),
          el("div", { class: "grupo-btn" }, botao({ texto: R.enviar, icone: "importar", variante: "primario", onclick: () => entrada.click() }), entrada))));
      return;
    }
    const r = rotulos.relatorio;
    const s = rotulos.sugestao;
    const nome = campo({ rotulo: R.nome, valor: s.nome, autocomplete: "off" });
    const id = campo({ rotulo: R.id, valor: s.id, ajuda: R.idAjuda, autocomplete: "off", spellcheck: "false", classe: "campo-caminho" });
    nome.querySelector("input").addEventListener("input", (ev) => { id.querySelector("input").value = idDoNome(ev.target.value); });
    const epocas = campo({ rotulo: R.epocas, tipo: "number", valor: String(s.epocas), ajuda: R.epocasAjuda });
    const temCvat = Object.keys(r.subconjuntos || {}).length > 0;
    let divisao = "sessao";
    const opcoesDivisao = [{ valor: "sessao", texto: R.porSessao }].concat(temCvat ? [{ valor: "cvat", texto: R.doCvat }] : []);
    const seg = segmentado({ rotulo: R.divisao, valor: divisao, opcoes: opcoesDivisao, aoMudar: (v) => { divisao = v; } });
    const pedido = () => ({ arquivo: rotulos.arquivo, nome: nome.querySelector("input").value.trim(), id: id.querySelector("input").value.trim(),
      epocas: Number(epocas.querySelector("input").value || 60), divisao });
    const podeTreinar = r.pronto && ambiente.ok;
    const comecar = botao({ texto: R.comecar, icone: "modelos", variante: "primario", desabilitado: !podeTreinar, title: !r.pronto ? R.naoPronto : !ambiente.ok ? ambiente.mensagem : null,
      onclick: () => ocupado(comecar, async () => {
        try {
          await api("/api/treinos", json("POST", pedido()));
          avisar(R.iniciado(pedido().nome));
          rotulos = null;
          desenharEtapa();
          await recarregar();
        } catch (e) { avisar(e.message, { erro: true }); }
      }) });
    const pacote = botao({ texto: R.pacote, icone: "baixar", title: R.pacoteNota, onclick: () => ocupado(pacote, () => baixarPacote(pedido())) });
    const maior = Math.max(1, ...r.classes.map((c) => c.rotulos));
    const blocos = [
      [R.imagensProntas, r.imagens_utilizaveis, R.deTotal(r.imagens_rotuladas)],
      [R.rotulos, r.rotulos, R.tipos(r.tipos)],
      [R.classes, r.classes.length, r.arquivo],
      [R.sessoes, r.sessoes, temCvat ? R.divisaoCvat(r.subconjuntos) : null],
    ];
    etapa.replaceChildren(...[
      el("div", { class: "titulo-bloco" }, el("h2", {}, R.rotulosTitulo), botao({ texto: R.trocar, variante: "fantasma", compacto: true, onclick: () => { rotulos = null; desenharEtapa(); } })),
      el("div", { class: "indicadores indicadores-4" }, blocos.map(([rot, v, nota]) => el("div", { class: "indicador" }, el("span", { class: "rotulo" }, rot), el("span", { class: "valor" }, String(v)), nota ? el("span", { class: "nota corta", title: nota }, nota) : null))),
      tabela({ rotulo: R.classes, colunas: [
        { chave: "nome", titulo: R.colClasse, celula: (c) => [el("span", {}, c.nome), el("span", { class: "barra barra-classe" }, el("i", { style: { transform: `scaleX(${c.rotulos / maior})` } }))] },
        { chave: "rotulos", titulo: R.colRotulos, classe: "num", celula: (c) => String(c.rotulos) },
        { chave: "imagens", titulo: R.colImagens, classe: "num", celula: (c) => String(c.imagens) },
      ], linhas: r.classes }),
      r.avisos?.length ? el("ul", { class: "lista-avisos" }, r.avisos.map((a) => el("li", {}, a))) : null,
      el("div", { class: "form-treino" },
        el("div", { class: "grade-campos-3" }, nome, id, epocas),
        el("div", { class: "campo" }, el("span", { class: "rotulo" }, R.divisao), seg, el("span", { class: "ajuda" }, R.divisaoAjuda)),
        el("div", { class: "grupo-btn" }, pacote, comecar)),
    ].filter(Boolean));
  }

  async function enviarRotulos(arquivos) {
    etapa.replaceChildren(el("p", { class: "nota", role: "status" }, R.analisando));
    const envio = new FormData();
    arquivos.forEach((a) => envio.append("arquivos", a));
    try {
      rotulos = await api("/api/treinos/rotulos", { method: "POST", body: envio });
    } catch (e) {
      avisar(e.message, { erro: true });
      rotulos = null;
    }
    desenharEtapa();
  }

  async function baixarPacote(corpo) {
    try {
      const r = await fetch("/api/treinos/pacote", json("POST", corpo));
      if (!r.ok) { const c = await r.json().catch(() => null); throw new Error((c && (c.erro || c.detail)) || T.geral.erroServidor(r.status)); }
      const nomeArq = (r.headers.get("content-disposition") || "").match(/filename="([^"]+)"/)?.[1] || "Pyron_pacote_treino.zip";
      const a = el("a", { href: URL.createObjectURL(await r.blob()), download: nomeArq });
      document.body.append(a);
      a.click();
      a.remove();
      avisar(R.pacoteBaixado);
    } catch (e) { avisar(e.message, { erro: true }); }
  }

  // ---------------------------------------------------------------- 2. treinos
  function desenharTreinos() {
    clearTimeout(relogio);
    if (!treinos.length) { lista.replaceChildren(); return; }
    lista.replaceChildren(el("div", { class: "titulo-bloco" }, el("h2", {}, R.treinos)), ...treinos.slice(0, 8).map(cartao));
    if (treinos.some((t) => !FINAIS.includes(t.etapa))) relogio = setTimeout(recarregar, 2000);
  }

  function cartao(t) {
    const final = FINAIS.includes(t.etapa);
    const perdas = t.perda || [];
    const info = [t.mensagem, t.etapa === "treinando" && perdas.length ? R.perda(fmt(perdas[perdas.length - 1], 3), fmt(perdas[0], 3)) : null,
      t.imagens_treino ? R.divisaoUsada(t.divisao || "", t.imagens_treino, t.imagens_teste) : null, t.etapa === "treinando" && t.restante ? R.restante(t.restante) : null].filter(Boolean).join(", ");
    const acoes = [];
    if (!final) acoes.push(botao({ texto: R.cancelar, icone: "x", variante: "perigo", compacto: true, onclick: () => cancelar(t) }));
    if (t.etapa === "pronto") acoes.push(botao({ texto: R.usar, compacto: true, onclick: (ev) => ocupado(ev.currentTarget, async () => {
      try { await api("/api/modelos/ativo", json("PUT", { id: t.id })); avisar(T.modelos.passaASer(t.nome)); } catch (e) { avisar(e.message, { erro: true }); }
    }) }));
    if (final && t.etapa !== "pronto") acoes.push(botao({ texto: R.verRegistro, variante: "fantasma", compacto: true, onclick: (ev) => ocupado(ev.currentTarget, () => registro(t)) }));
    const m = t.metricas;
    return el("article", { class: "cartao-treino" },
      el("div", { class: "titulo-bloco" }, el("div", {}, el("h3", {}, t.nome), el("p", { class: "nota mono" }, [t.id, t.dispositivo].filter(Boolean).join(", "))),
        el("span", { class: t.etapa === "erro" || t.etapa === "interrompido" ? "vencida" : !final ? "status-vivo" : null }, R.etapas[t.etapa] || t.etapa)),
      !final ? el("div", { class: "barra", role: "progressbar", "aria-label": R.andamento, "aria-valuenow": String(t.percentual), "aria-valuemin": "0", "aria-valuemax": "100" }, el("i", { style: { transform: `scaleX(${t.percentual / 100})` } })) : null,
      info ? el("p", { class: t.etapa === "erro" ? "erro-dialogo" : "nota" }, info) : null,
      t.etapa === "pronto" && m ? el("dl", { class: "pares pares-4" },
        [[R.metricas.mAP50, m.mAP50 != null ? fmt(m.mAP50 * 100, 0, " %") : T.geral.semValor], [R.metricas.revocacao, m.revocacao != null ? fmt(m.revocacao * 100, 0, " %") : T.geral.semValor],
          [R.metricas.erro, fmt(m.erro_tmax_mediano_c, 2, " °C")], [R.metricas.erro90, fmt(m.erro_tmax_p90_c, 2, " °C")]].flatMap(([k, v]) => [el("dt", {}, k), el("dd", { class: "num" }, v)])) : null,
      t.etapa === "pronto" ? secao({ titulo: R.previsoesTitulo, aberta: false, conteudo: [el("a", { href: `/api/treinos/${t.id}/previsoes.png`, target: "_blank", rel: "noopener" },
        el("img", { class: "figura-treino", src: `/api/treinos/${t.id}/previsoes.png`, alt: R.previsoes, loading: "lazy" })), el("p", { class: "nota" }, R.previsoes)] }) : null,
      acoes.length ? el("div", { class: "grupo-btn" }, acoes) : null);
  }

  async function cancelar(t) {
    if (!(await confirmar({ titulo: R.cancelarTitulo, texto: R.cancelarTexto, confirmar: R.cancelar, perigo: true }))) return;
    try { await api(`/api/treinos/${t.id}/cancelar`, { method: "POST" }); avisar(R.cancelado); await recarregar(); } catch (e) { avisar(e.message, { erro: true }); }
  }

  async function registro(t) {
    try {
      const d = await api(`/api/treinos/${t.id}`);
      dialogo({ titulo: R.registroDe(t.nome), corpo: [el("pre", { class: "registro-treino" }, d.registro || T.geral.semValor)] }).abrir();
    } catch (e) { avisar(e.message, { erro: true }); }
  }

  async function recarregar() {
    try { treinos = (await api("/api/treinos")).treinos; } catch { relogio = setTimeout(recarregar, 4000); return; }
    desenharTreinos();
  }

  return () => clearTimeout(relogio);
}
