// Modelos › Avaliação: a comparação dos detectores treinados no Colab, nas fotos que nenhum deles viu.
// Importar resultados é o primário; a leitura vem em números e tabelas (valores exatos, poucos modelos), com
// o melhor de cada coluna em negrito, as figuras do caderno recolhidas e "Usar este modelo" quando ele veio junto.
import { TEXTOS as T } from "../../textos.js";
import { el, api, json, fmt, dataHora } from "../base.js";
import { botao, campo, secao, estadoVazio, avisar, confirmar, ocupado } from "../componentes.js";

const V = T.avaliacao;
const num2 = (v) => (v == null ? T.geral.semValor : fmt(v, 2));
const pct = (v) => (v == null ? T.geral.semValor : fmt(v * 100, 0, " %"));

export async function montar(no) {
  let lista = await api("/api/avaliacoes");
  let atual = lista[0]?.id || null;
  const entrada = el("input", { type: "file", accept: ".zip", hidden: true, onchange: () => { importar(entrada.files[0]); entrada.value = ""; } });
  const importarBtn = botao({ texto: V.importar, icone: "importar", variante: "primario", onclick: () => entrada.click() });
  const barra = el("div", { class: "barra-lista" });
  const corpo = el("div", { class: "corpo-avaliacao" });
  no.append(barra, corpo);
  await desenhar();

  async function desenhar() {
    if (!lista.length) {
      barra.replaceChildren();
      corpo.replaceChildren(estadoVazio({ ilustracao: "modelos", titulo: V.vazioTitulo, texto: V.vazioTexto, acoes: [importarBtn, entrada] }));
      return;
    }
    const escolha = lista.length > 1 ? campo({ rotulo: V.escolher, opcoes: lista.map((m) => ({ valor: m.id, texto: V.opcao(dataHora(m.importado_em), m.modelos.length, m.melhor) })), valor: atual }) : null;
    escolha?.querySelector("select").addEventListener("change", (ev) => { atual = ev.target.value; desenharAvaliacao(); });
    const apagar = botao({ texto: V.apagar, icone: "lixo", variante: "fantasma", onclick: async () => {
      if (!(await confirmar({ titulo: V.apagarTitulo, texto: V.apagarTexto, confirmar: V.apagarCurto, perigo: true }))) return;
      try { await api(`/api/avaliacoes/${atual}`, { method: "DELETE" }); avisar(V.apagada); lista = await api("/api/avaliacoes"); atual = lista[0]?.id || null; await desenhar(); } catch (e) { avisar(e.message, { erro: true }); }
    } });
    barra.replaceChildren(...[escolha, el("span", { class: "empurrar" }), apagar, importarBtn, entrada].filter(Boolean));
    await desenharAvaliacao();
  }

  async function desenharAvaliacao() {
    corpo.replaceChildren(el("p", { class: "nota", role: "status" }, T.geral.carregando));
    const d = await api(`/api/avaliacoes/${atual}`);
    const r = d.resumo;
    const t = r.teste;
    const modelos = Object.keys(t);
    const melhor = modelos.reduce((a, b) => ((t[b].mAP50 ?? 0) > (t[a].mAP50 ?? 0) ? b : a));
    const menosPerdas = modelos.reduce((a, b) => ((t[b].perdidos ?? Infinity) < (t[a].perdidos ?? Infinity) ? b : a));
    const total = (m) => (t[m].acertos ?? 0) + (t[m].perdidos ?? 0);
    const qtd = (v) => (Array.isArray(v) ? v.length : v);
    const f = r.fotos || {};
    const bloco = (rotulo, valor, nota) => el("div", { class: "indicador" }, el("span", { class: "rotulo" }, rotulo), el("span", { class: "valor corta", title: valor }, valor), nota ? el("span", { class: "nota" }, nota) : null);

    // melhor de cada coluna em negrito (sentido: maior ou menor é melhor)
    const colunas = [["mAP50", "maior", num2], ["mAP50-95", "maior", num2], ["precisao", "maior", num2], ["revocacao", "maior", num2], ["F1", "maior", num2],
      ["acertos", "maior", String], ["falsos", "menor", String], ["perdidos", "menor", String]];
    if (modelos.some((m) => t[m].erro_Tmax_mediano_C != null)) colunas.push(["erro_Tmax_mediano_C", "menor", num2]);
    const extremo = (k, s) => { const v = modelos.map((m) => t[m][k]).filter((x) => x != null); return v.length ? (s === "maior" ? Math.max(...v) : Math.min(...v)) : null; };
    const melhores = Object.fromEntries(colunas.map(([k, s]) => [k, extremo(k, s)]));
    const comparacao = el("div", { class: "tabela-caixa" }, el("table", { class: "tabela", "aria-label": V.comparacao },
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, V.colModelo), colunas.map(([k]) => el("th", { scope: "col", class: "num metrica" }, V.colunas[k] || k)), el("th", { scope: "col", class: "num" }, V.msFoto))),
      el("tbody", {}, modelos.map((m) => el("tr", {}, el("th", { scope: "row", class: "forte" }, m),
        colunas.map(([k, , fn]) => { const v = t[m][k]; const top = v != null && v === melhores[k] && modelos.length > 1; return el("td", { class: `num${top ? " melhor" : ""}`, title: top ? V.melhorDaColuna : null }, v != null ? fn(v) : T.geral.semValor); }),
        el("td", { class: "num" }, r.ms_por_foto?.[m] != null ? fmt(r.ms_por_foto[m], 0) : T.geral.semValor))))));

    const classes = [...new Set(modelos.flatMap((m) => Object.keys(t[m].por_classe || {})))];
    const porClasse = classes.length ? el("div", { class: "tabela-caixa" }, el("table", { class: "tabela", "aria-label": V.porClasse },
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, V.componente), modelos.map((m) => el("th", { scope: "col", class: "num" }, m)))),
      el("tbody", {}, classes.map((c) => {
        const vs = modelos.map((m) => t[m].por_classe?.[c]?.AP50);
        const max = Math.max(...vs.filter((v) => v != null));
        return el("tr", {}, el("th", { scope: "row" }, c), vs.map((v) => el("td", { class: `num${v != null && v === max && modelos.length > 1 ? " melhor" : ""}` }, num2(v))));
      })))) : null;

    const frases = conclusoes(t, modelos);
    const instalado = d.meta.modelo_instalado && d.modelo_disponivel;
    const usar = instalado && d.modelo_ativo !== d.meta.modelo_instalado
      ? botao({ texto: V.usarModelo, compacto: true, onclick: (ev) => ocupado(ev.currentTarget, async () => {
        try { await api("/api/modelos/ativo", json("PUT", { id: d.meta.modelo_instalado })); avisar(T.modelos.passaASer(d.meta.modelo_instalado)); await desenharAvaliacao(); } catch (e) { avisar(e.message, { erro: true }); }
      }) }) : null;
    const figuras = (d.meta.figuras || []).slice().sort((a, b) => (a.startsWith("teste_") ? 1 : 0) - (b.startsWith("teste_") ? 1 : 0) || a.localeCompare(b));

    corpo.replaceChildren(...[
      el("div", { class: "indicadores indicadores-4" },
        bloco(V.melhor, melhor, V.melhorNota(num2(t[melhor].mAP50))),
        bloco(V.revocacao, pct(t[melhor].revocacao), V.revocacaoNota(t[melhor].acertos ?? 0, total(melhor))),
        bloco(V.perdidas, String(t[menosPerdas].perdidos ?? T.geral.semValor), V.perdidasNota(menosPerdas)),
        bloco(V.fotos, V.fotosTeste(qtd(f.teste) ?? T.geral.semValor), V.fotosNota(qtd(f.treino) ?? T.geral.semValor, qtd(f.validacao) ?? T.geral.semValor))),
      frases.length ? el("div", { class: "conclusao" }, frases.map((x) => el("p", {}, x))) : null,
      instalado ? el("div", { class: "faixa-modelo" }, el("p", {}, V.modeloVeio(d.meta.modelo_instalado)), usar || el("p", { class: "em-uso" }, T.modelos.emUso)) : null,
      el("section", {}, el("div", { class: "titulo-bloco" }, el("h2", {}, V.comparacao), el("span", { class: "nota" }, V.comparacaoNota)), comparacao),
      porClasse ? el("section", {}, el("div", { class: "titulo-bloco" }, el("h2", {}, V.porClasse), el("span", { class: "nota" }, V.porClasseNota)), porClasse) : null,
      figuras.length ? secao({ titulo: V.figuras, aberta: false, qtd: figuras.length, conteudo: [el("div", { class: "galeria-figuras" }, figuras.map((n) => {
        const src = `/api/avaliacoes/${d.meta.id}/arquivos/${encodeURIComponent(n)}`;
        return el("figure", {}, el("a", { href: src, target: "_blank", rel: "noopener" }, el("img", { src, alt: V.figura[n] || n, loading: "lazy" })), el("figcaption", { class: "nota" }, V.figura[n] || n));
      }))] }) : null,
      el("dl", { class: "pares dados-avaliacao" }, [[V.importadoEm, dataHora(d.meta.importado_em)], [V.arquivo, d.meta.arquivo], [V.gpu, r.gpu], [V.classes, (r.classes || []).join(", ")]]
        .filter(([, v]) => v).flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)])),
    ].filter(Boolean));
  }

  /** Leitura automática: empate ou vantagem entre os dois primeiros e a peça mais difícil para todos. */
  function conclusoes(t, modelos) {
    const frases = [];
    const ordem = [...modelos].sort((a, b) => (t[b].acertos ?? 0) - (t[a].acertos ?? 0));
    if (ordem.length > 1) {
      const [a, b] = ordem;
      const dif = (t[a].acertos ?? 0) - (t[b].acertos ?? 0);
      const tot = (t[a].acertos ?? 0) + (t[a].perdidos ?? 0);
      frases.push(dif <= Math.max(2, Math.round(tot * 0.02)) ? V.empate(a, b, dif) : V.vantagem(a, b, dif));
    }
    const classes = [...new Set(modelos.flatMap((m) => Object.keys(t[m].por_classe || {})))];
    const medias = classes.map((c) => { const v = modelos.map((m) => t[m].por_classe?.[c]?.AP50).filter((x) => x != null); return [c, v.length ? v.reduce((s, x) => s + x, 0) / v.length : null]; })
      .filter(([, v]) => v != null).sort((p, q) => p[1] - q[1]);
    if (medias.length && medias[0][1] < 0.85) frases.push(V.pontoFraco(medias[0][0], num2(medias[0][1])));
    return frases;
  }

  async function importar(arquivo) {
    if (!arquivo) return;
    const envio = new FormData();
    envio.append("arquivo", arquivo);
    corpo.replaceChildren(el("p", { class: "nota", role: "status" }, V.importando));
    try {
      const r = await api("/api/avaliacoes", { method: "POST", body: envio });
      const partes = [r.avaliacao ? V.parteAvaliacao : null, r.modelo ? V.parteModelo(r.modelo) : null].filter(Boolean);
      if (partes.length) avisar(V.importou(partes));
      for (const aviso of r.avisos || []) avisar(aviso, { erro: true });
      lista = await api("/api/avaliacoes");
      atual = r.avaliacao || lista[0]?.id || null;
    } catch (e) { avisar(e.message, { erro: true }); }
    await desenhar();
  }
  return null;
}
