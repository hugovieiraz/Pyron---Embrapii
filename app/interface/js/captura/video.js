// Captura › Vídeo: a gravação da tela da câmera analisada quadro a quadro, como se fosse ao vivo. Lista com o
// envio (primário: Enviar vídeo) e o vídeo aberto (#captura/video/<id>): quadro com as regiões, reprodução,
// máxima no tempo, momentos com anomalia e o que há no quadro. Primário do vídeo aberto: Salvar quadro.
import { TEXTOS as T } from "../../textos.js";
import { el, icone, api, fmt, temperatura, dataHora, lerNumero, animarEntrada } from "../base.js";
import { botao, campo, segmentado, secao, tabela, selo, estadoVazio, avisar, confirmar, ocupado, menu } from "../componentes.js";
import { endereco } from "../rotas.js";
import { graficoSerie } from "../grafico.js";
import { pesoSeveridade } from "../situacao.js";

const V = T.video;
const ATIVOS = ["na_fila", "processando"];
const EXTENSOES = /\.(mp4|avi|mov|mkv|m4v|wmv|webm)$/i;

/** 83,4 s vira "1:23,4". */
export function tempoVideo(s) {
  if (s == null || !Number.isFinite(s)) return T.geral.semValor;
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(1).padStart(4, "0").replace(".", ",")}`;
}

export async function montar(no, { partes }) {
  return partes[0] ? montarAberto(no, partes[0]) : montarLista(no);
}

// ================================================================ lista e envio
async function montarLista(no) {
  const [videos, modelos] = await Promise.all([api("/api/videos"), api("/api/modelos").catch(() => ({ modelos: [], ativo: null }))]);
  let lista = videos;
  let relogio = null;
  const opcoes = { modo: "ao_vivo" };
  const disponiveis = (modelos.modelos || []).filter((m) => m.disponivel !== false);

  // ---------------------------------------------------------------- opções do envio
  const velocidade = campo({ rotulo: V.velocidade, opcoes: ["0.5", "1", "2", "4"].map((v) => ({ valor: v, texto: `${fmt(Number(v), v.includes(".") ? 1 : 0)}×` })), valor: "1" });
  const intervalo = campo({ rotulo: V.intervalo, tipo: "number", valor: "0,5", unidade: "s" });
  intervalo.hidden = true;
  const notaModo = el("p", { class: "nota" }, V.modoAoVivo);
  const modo = segmentado({ rotulo: V.modo, valor: "ao_vivo", opcoes: [{ valor: "ao_vivo", texto: V.aoVivoOpcao }, { valor: "intervalo", texto: V.intervaloOpcao }],
    aoMudar: (v) => { opcoes.modo = v; velocidade.hidden = v !== "ao_vivo"; intervalo.hidden = v !== "intervalo"; notaModo.textContent = v === "ao_vivo" ? V.modoAoVivo : V.modoIntervalo; } });
  const modelo = campo({ rotulo: V.modelo, opcoes: disponiveis.map((m) => ({ valor: m.id, texto: m.nome })), valor: modelos.ativo });
  const tmin = campo({ rotulo: V.escalaMin, tipo: "number", unidade: "°C", marcador: V.lerDaImagem });
  const tmax = campo({ rotulo: V.escalaMax, tipo: "number", unidade: "°C", marcador: V.lerDaImagem });
  const entrada = el("input", { type: "file", accept: "video/*,.mkv,.wmv", hidden: true, onchange: () => { enviar(entrada.files[0]); entrada.value = ""; } });
  const enviarBtn = botao({ texto: V.enviar, icone: "importar", variante: "primario", onclick: () => entrada.click() });
  const progresso = el("div", { class: "faixa-importacao", role: "status", hidden: true }, icone("importar"),
    el("div", { class: "texto-importacao" }, el("b", {})), el("div", { class: "barra", role: "progressbar", "aria-label": V.envioRotulo, "aria-valuemin": "0", "aria-valuemax": "100" }, el("i", {})));
  const corpo = el("div", { class: "corpo-videos" });

  no.append(el("section", { class: "envio-video", "aria-label": V.enviarTitulo },
    el("div", { class: "titulo-bloco" }, el("h2", {}, V.enviarTitulo), enviarBtn, entrada),
    el("div", { class: "linha-opcoes" }, el("div", { class: "campo" }, el("span", { class: "rotulo" }, V.modo), modo), velocidade, intervalo, modelo),
    notaModo,
    secao({ titulo: V.escalaFixa, aberta: false, conteudo: [el("p", {}, V.escalaFixaTexto), el("div", { class: "grade-campos-2" }, tmin, tmax)] })),
  progresso, corpo);
  desenhar();

  function desenhar() {
    clearTimeout(relogio);
    if (!lista.length) {
      corpo.replaceChildren(estadoVazio({ ilustracao: "analise", titulo: V.vazioTitulo, texto: V.vazioTexto, compacto: true }));
      return;
    }
    const t = tabela({
      rotulo: V.lista,
      colunas: [
        { chave: "mini", titulo: el("span", { class: "so-leitor" }, V.colImagem), classe: "celula-mini", celula: (v) => (v.miniatura ? el("img", { class: "miniatura", src: v.miniatura, alt: "", loading: "lazy", width: 64, height: 48 }) : el("span", { class: "miniatura vazia" })) },
        { chave: "arquivo", titulo: V.colVideo, link: true, celula: (v) => [el("span", { class: "corta", title: v.arquivo }, v.arquivo), el("span", { class: "sub" }, dataHora(v.criado_em))] },
        { chave: "duracao", titulo: V.colDuracao, classe: "num", celula: (v) => tempoVideo(v.info?.duracao_s) },
        { chave: "modo", titulo: V.colModo, celula: (v) => (v.opcoes.modo === "ao_vivo" ? V.modoVivo(fmt(v.opcoes.velocidade, v.opcoes.velocidade % 1 ? 1 : 0)) : V.modoIntervaloCurto(fmt(v.opcoes.intervalo_s, 2))) },
        { chave: "quadros", titulo: V.colQuadros, classe: "num", celula: (v) => String(v.resumo?.analisados || 0) },
        { chave: "tmax", titulo: V.colMaxima, classe: "num", celula: (v) => temperatura(v.resumo?.t_max) },
        { chave: "status", titulo: V.colSituacao, celula: celulaStatus },
        { chave: "acoes", titulo: el("span", { class: "so-leitor" }, V.colAcoes), classe: "dir", celula: (v) => botao({ texto: V.apagarRotulo(v.arquivo), icone: "lixo", variante: "fantasma", soIcone: true, compacto: true, onclick: () => apagar(v) }) },
      ],
      linhas: lista,
      severidade: (v) => v.resumo?.severidade_max || "sem_medida",
      href: (v) => endereco("captura", ["video", v.id]),
      aoMenu: (v, ev) => menu(ev.currentTarget, [{ texto: V.abrirVideo, icone: "video", executar: () => { location.hash = endereco("captura", ["video", v.id]); } }, { separador: true }, { texto: V.apagar, icone: "lixo", perigo: true, executar: () => apagar(v) }], { em: { x: ev.clientX, y: ev.clientY }, descartar: true }),
    });
    animarEntrada([...t.querySelectorAll("tbody tr")]);
    corpo.replaceChildren(t);
    if (lista.some((v) => ATIVOS.includes(v.status))) relogio = setTimeout(recarregar, 2000);
  }

  function celulaStatus(v) {
    const ativo = ATIVOS.includes(v.status);
    return el("div", { class: "celula-sev" }, el("span", { class: ativo ? "status-vivo" : null }, V.status[v.status] || v.status),
      ativo ? el("div", { class: "barra barra-linha", role: "progressbar", "aria-label": V.analiseRotulo, "aria-valuenow": String(Math.round((v.progresso || 0) * 100)), "aria-valuemin": "0", "aria-valuemax": "100" }, el("i", { style: { transform: `scaleX(${v.progresso || 0})` } }))
        : v.resumo?.severidade_max ? selo(v.resumo.severidade_max) : null);
  }

  async function recarregar() {
    try { lista = await api("/api/videos"); } catch { relogio = setTimeout(recarregar, 4000); return; }
    desenhar();
  }

  async function apagar(v) {
    if (!(await confirmar({ titulo: V.apagarTitulo, texto: V.apagarTexto(v.arquivo), confirmar: V.apagar, perigo: true }))) return;
    try { await api(`/api/videos/${v.id}`, { method: "DELETE" }); avisar(V.apagado); await recarregar(); } catch (e) { avisar(e.message, { erro: true }); }
  }

  /** Envio com XMLHttpRequest para mostrar o andamento (um vídeo pode ter centenas de MB). */
  function enviar(arquivo) {
    if (!arquivo) return;
    if (!EXTENSOES.test(arquivo.name)) { avisar(V.soVideos, { erro: true }); return; }
    const dados = new FormData();
    dados.append("arquivo", arquivo);
    dados.append("modo", opcoes.modo);
    dados.append("velocidade", velocidade.querySelector("select").value);
    dados.append("intervalo_s", String(lerNumero(intervalo.querySelector("input").value) ?? 0.5));
    dados.append("modelo", modelo.querySelector("select").value || "");
    dados.append("t_min", String(lerNumero(tmin.querySelector("input").value) ?? ""));
    dados.append("t_max", String(lerNumero(tmax.querySelector("input").value) ?? ""));
    const texto = progresso.querySelector("b");
    const barra = progresso.querySelector(".barra");
    progresso.hidden = false;
    enviarBtn.setAttribute("aria-busy", "true");
    const mostrar = (p) => { texto.textContent = V.enviando(Math.round(p * 100)); barra.setAttribute("aria-valuenow", String(Math.round(p * 100))); barra.firstChild.style.transform = `scaleX(${p})`; };
    mostrar(0);
    const fim = () => { progresso.hidden = true; enviarBtn.removeAttribute("aria-busy"); };
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/videos");
    xhr.upload.onprogress = (ev) => { if (ev.lengthComputable) mostrar(ev.loaded / ev.total); };
    xhr.onload = () => {
      fim();
      let r = null;
      try { r = JSON.parse(xhr.responseText); } catch { /* resposta sem JSON */ }
      if (xhr.status >= 200 && xhr.status < 300 && r) { avisar(V.enviado); location.hash = endereco("captura", ["video", r.id]); }
      else avisar((r && (r.erro || r.detail)) || T.geral.erroServidor(xhr.status), { erro: true });
    };
    xhr.onerror = () => { fim(); avisar(T.geral.semResposta, { erro: true }); };
    xhr.send(dados);
  }

  return () => clearTimeout(relogio);
}

// ================================================================ vídeo aberto
async function montarAberto(no, id) {
  let d;
  try {
    d = await api(`/api/videos/${encodeURIComponent(id)}?desde=0`);
  } catch (erro) {
    if (erro.status !== 404) throw erro;
    no.append(estadoVazio({ ilustracao: "busca", titulo: V.naoEncontrado, acoes: [el("a", { class: "btn primario", href: endereco("captura", ["video"]) }, V.verVideos)] }));
    return null;
  }
  let quadros = d.quadros || [];
  let atual = -1;
  let seguindo = true;   // acompanha o último quadro enquanto a análise anda
  let tocando = false;
  let relogioSonda = null;
  let relogioTocar = null;
  const cache = new Map();
  const ativo = () => ATIVOS.includes(d.status);

  // ---------------------------------------------------------------- cabeçalho do vídeo
  const etiquetas = el("div", { class: "meta" });
  const parar = botao({ texto: V.pararAnalise, icone: "x", onclick: () => ocupado(parar, async () => {
    try { await api(`/api/videos/${d.id}/cancelar`, { method: "POST" }); avisar(V.parando); } catch (e) { avisar(e.message, { erro: true }); }
  }) });
  const salvar = botao({ texto: V.salvarQuadro, icone: "inspecoes", variante: "primario", onclick: () => ocupado(salvar, async () => {
    const q = quadros[atual];
    if (!q) return;
    pausar();
    seguindo = false;
    try {
      const a = await api(`/api/videos/${d.id}/quadros/${q.n}/inspecao`, { method: "POST" });
      avisar(V.salvo(a.arquivo), { acao: { rotulo: V.abrir, executar: () => { location.hash = endereco("inspecoes", [a.id]); } } });
      document.dispatchEvent(new CustomEvent("pyron:importadas", { detail: [a] }));
    } catch (e) { avisar(e.message, { erro: true }); }
  }) });
  const cab = el("div", { class: "cab-video" },
    el("a", { class: "btn fantasma icone", href: endereco("captura", ["video"]), "aria-label": V.verVideos, title: V.verVideos }, icone("anterior")),
    el("div", { class: "titulo" }, el("h2", { class: "corta", title: d.arquivo }, d.arquivo), etiquetas),
    el("div", { class: "acoes" }, parar, salvar));

  // ---------------------------------------------------------------- palco: quadro, regiões e leitura
  const imagem = el("img", { class: "quadro-imagem", alt: "" });
  const sobre = el("div", { class: "quadro-regioes" });
  const hud = el("div", { class: "hud-video", role: "status" });
  const quadro = el("div", { class: "quadro-video" }, imagem, sobre);
  const palco = el("div", { class: "palco-video", tabindex: "0", "aria-label": V.palco }, quadro, hud);

  const tocarBtn = botao({ texto: V.tocar, icone: "tocar", soIcone: true, atalho: V.espaco, onclick: () => alternarTocar() });
  const linha = el("input", { type: "range", min: "0", max: "0", value: "0", step: "1", class: "linha-tempo", "aria-label": V.posicao, oninput: () => irParaQuadro(Number(linha.value)) });
  const tempo = el("span", { class: "num tempo-video" });
  const ritmo = campo({ rotulo: V.ritmo, opcoes: ["0.5", "1", "2"].map((v) => ({ valor: v, texto: `${fmt(Number(v), v.includes(".") ? 1 : 0)}×` })), valor: "1", classe: "campo-ritmo" });
  ritmo.querySelector("select").addEventListener("change", () => { if (tocando) agendarProximo(); });
  const aoVivo = botao({ texto: V.voltarAoVivo, compacto: true, onclick: () => { pausar(); seguindo = true; mostrarQuadro(quadros.length - 1); } });
  const controles = el("div", { class: "controles-video" }, tocarBtn, linha, tempo, ritmo, aoVivo);

  // ---------------------------------------------------------------- painel: números, gráfico, momentos, quadro
  const indicadores = el("div", { class: "indicadores" });
  const caixaGrafico = el("div", { class: "caixa-grafico-video" });
  const momentos = el("div", { class: "lista-momentos" });
  const nesteQuadro = el("div");
  const lado = el("aside", { class: "painel-video", "aria-label": V.painel },
    indicadores,
    el("section", {}, el("div", { class: "titulo-bloco" }, el("h2", {}, V.graficoTitulo)), caixaGrafico, el("p", { class: "nota" }, V.graficoDica)),
    secao({ titulo: V.momentos, conteudo: [momentos] }),
    secao({ titulo: V.neste, conteudo: [nesteQuadro] }));

  no.append(cab, el("div", { class: "video-grade" }, el("div", { class: "coluna-video" }, palco, controles), lado));
  let grafico = null;
  let pontosNoGrafico = -1;

  function receber(novo, inicial = false) {
    const estavaAtivo = ativo();
    if (!inicial) for (const q of novo.quadros || []) if (q.n === quadros.length) quadros.push(q);
    d = { ...novo, quadros: undefined };
    desenharCabecalho();
    desenharIndicadores();
    desenharGrafico();
    desenharMomentos();
    linha.max = String(Math.max(quadros.length - 1, 0));
    if (quadros.length) {
      if (ativo() && seguindo) mostrarQuadro(quadros.length - 1);
      else if (atual < 0) mostrarQuadro(0);
    } else {
      hud.replaceChildren(el("span", {}, d.status === "na_fila" ? V.naFila : ativo() ? V.preparando : V.semRegioes));
    }
    aoVivo.hidden = !(ativo() && !seguindo);
    if (ativo()) agendarSonda();
    else if (estavaAtivo) {
      if (d.status === "concluido") avisar(V.concluido);
      else if (d.status === "erro") avisar(d.erro || V.status.erro, { erro: true });
      else avisar(V.parado);
    }
  }

  function agendarSonda() {
    clearTimeout(relogioSonda);
    relogioSonda = setTimeout(async () => {
      try { receber(await api(`/api/videos/${d.id}?desde=${quadros.length}`)); } catch { agendarSonda(); }
    }, 400);
  }

  function desenharCabecalho() {
    const op = d.opcoes;
    etiquetas.replaceChildren(
      el("span", { class: ativo() ? "status-vivo" : d.status === "erro" ? "vencida" : null, title: d.erro || "" }, V.status[d.status] || d.status),
      el("span", {}, op.modo === "ao_vivo" ? V.modoVivo(fmt(op.velocidade, op.velocidade % 1 ? 1 : 0)) : V.modoIntervaloCurto(fmt(op.intervalo_s, 2))),
      d.modelo ? el("span", { class: "corta", title: d.modelo.nome }, d.modelo.nome) : null,
      el("span", {}, op.limites ? V.escalaFixaInfo(fmt(op.limites[0], 1), fmt(op.limites[1], 1)) : V.escalaLida),
      el("span", { class: "num" }, V.duracao(tempoVideo(d.info.duracao_s), fmt(d.info.fps, 0))));
    parar.hidden = !ativo();
    salvar.disabled = !quadros.length;
    quadro.style.aspectRatio = `${d.info.largura} / ${d.info.altura}`;
    quadro.style.setProperty("--proporcao", String(d.info.largura / d.info.altura));
  }

  function desenharIndicadores() {
    const r = d.resumo || {};
    const bloco = (rotulo, valor, nota) => el("div", { class: "indicador" }, el("span", { class: "rotulo" }, rotulo), el("span", { class: "valor" }, valor), nota ? el("span", { class: "nota" }, nota) : null);
    indicadores.replaceChildren(
      bloco(V.kQuadros, String(r.analisados || 0), V.kQuadrosDe(d.info.quadros)),
      bloco(V.kRitmo, r.quadros_por_segundo != null ? fmt(r.quadros_por_segundo, 1) : T.geral.semValor, V.kRitmoNota(fmt(d.info.fps, 0))),
      bloco(V.kLatencia, r.latencia_media_ms != null ? `${r.latencia_media_ms} ms` : T.geral.semValor, r.latencia_p95_ms != null ? V.kLatenciaNota(r.latencia_p95_ms) : null),
      bloco(V.kMaxima, temperatura(r.t_max), r.severidade_max ? T.niveis[r.severidade_max] : null));
  }

  function desenharGrafico() {
    const com = quadros.filter((q) => q.t_max != null);
    if (com.length === pontosNoGrafico) return; // nada novo: não redesenha a cada sonda
    pontosNoGrafico = com.length;
    grafico?.encerrar();
    if (!com.length) {
      grafico = null;
      caixaGrafico.replaceChildren(el("p", { class: "nota" }, quadros.length ? V.graficoVazio : V.graficoEspera));
      return;
    }
    grafico = graficoSerie({
      titulo: V.graficoTitulo,
      pontos: com.map((q) => ({ ...q, valor: q.t_max, rotulo: tempoVideo(q.tempo_s) })),
      eixo: { de: (q) => q.tempo_s, rotulo: tempoVideo, folga: 1 },
      comPonto: (q) => q.severidade && q.severidade !== "normal",
      aoEscolher: (q) => irParaQuadro(q.n),
      aoClicar: (t) => irParaTempo(t),
    });
    caixaGrafico.replaceChildren(grafico.no);
    if (quadros[atual]) grafico.cursor(quadros[atual].tempo_s);
  }

  /** Trechos seguidos de quadros fora do normal, com o pior nível e o quadro mais quente de cada um. */
  function desenharMomentos() {
    const grupos = [];
    let g = null;
    for (const q of quadros) {
      if (!q.severidade || q.severidade === "normal") { g = null; continue; }
      if (!g) grupos.push((g = { ini: q.tempo_s, fim: q.tempo_s, pior: q.severidade, quente: q, n: 0 }));
      g.fim = q.tempo_s;
      g.n += 1;
      if (pesoSeveridade(q.severidade) < pesoSeveridade(g.pior)) g.pior = q.severidade;
      if ((q.t_max ?? -Infinity) > (g.quente.t_max ?? -Infinity)) g.quente = q;
    }
    momentos.replaceChildren(grupos.length
      ? el("ul", { class: "lista-momentos-video" }, grupos.slice(0, 40).map((x) => el("li", {}, el("button", { type: "button", onclick: () => irParaQuadro(x.quente.n) },
        selo(x.pior), el("span", { class: "num" }, x.ini === x.fim ? tempoVideo(x.ini) : V.trecho(tempoVideo(x.ini), tempoVideo(x.fim))),
        el("span", { class: "nota" }, V.eventoResumo(x.n, temperatura(x.quente.t_max)))))))
      : el("p", { class: "nota" }, quadros.length ? V.semEventos : V.graficoEspera));
  }

  function carregar(n) {
    let im = cache.get(n);
    if (!im) {
      im = new Image();
      im.src = `/api/videos/${d.id}/quadros/${n}.jpg`;
      cache.set(n, im);
      if (cache.size > 80) cache.delete(cache.keys().next().value);
    }
    return im.decode ? im.decode().catch(() => {}) : Promise.resolve();
  }

  function mostrarQuadro(i) {
    const q = quadros[i];
    if (!q) return;
    atual = i;
    // a imagem só troca depois de decodificada: sem piscar entre um quadro e outro
    carregar(q.n).then(() => { if (atual !== i) return; imagem.src = `/api/videos/${d.id}/quadros/${q.n}.jpg`; desenharRegioes(q); });
    for (let k = 1; k <= 3; k++) if (quadros[i + k]) carregar(quadros[i + k].n);
    linha.value = String(i);
    tempo.textContent = `${tempoVideo(q.tempo_s)} / ${tempoVideo(d.info.duracao_s)}`;
    salvar.disabled = false;
    aoVivo.hidden = !(ativo() && !seguindo);
    desenharHud(q);
    desenharNeste(q);
    grafico?.cursor(q.tempo_s);
  }

  function desenharRegioes(q) {
    const [W, H] = q.matriz || d.matriz || [320, 240];
    const pct = (v, total) => `${(v / total) * 100}%`;
    sobre.replaceChildren(...q.regioes.map((r) => {
      const [x0, y0, x1, y1] = r.caixa;
      const fora = r.severidade && r.severidade !== "normal";
      return el("div", { class: `caixa-video${fora ? " fora" : ""}`, title: [r.nome, r.t_max != null ? temperatura(r.t_max) : null].filter(Boolean).join(", "),
        style: { "--sev": `var(--${r.severidade || "sem_medida"})`, left: pct(x0, W), top: pct(y0, H), width: pct(x1 - x0, W), height: pct(y1 - y0, H) } },
      fora ? el("span", { class: "etq" }, `${r.nome} · ${temperatura(r.t_max)}`) : null); // rótulo só fora do normal, como na Análise
    }), ...(q.ponto_mais_quente ? [el("span", { class: "alvo-quente", style: { left: pct(q.ponto_mais_quente.x + 0.5, W), top: pct(q.ponto_mais_quente.y + 0.5, H) } })] : []));
  }

  function desenharHud(q) {
    const vivo = ativo() && seguindo;
    hud.replaceChildren(el("b", { class: vivo ? "status-vivo" : null }, vivo ? V.aoVivo : tocando ? V.reproducao : V.pausado),
      el("span", { class: "num" }, tempoVideo(q.tempo_s)), el("span", { class: "num" }, `${q.ms} ms`),
      el("span", { class: "num" }, q.escala ? V.escalaCurta(fmt(q.escala[0], 1), fmt(q.escala[1], 1)) : V.semEscalaCurta));
  }

  function desenharNeste(q) {
    const regioes = [...q.regioes].sort((a, b) => pesoSeveridade(a.severidade || "sem_medida") - pesoSeveridade(b.severidade || "sem_medida") || (b.t_max ?? -999) - (a.t_max ?? -999));
    const pares = [[V.instante, `${tempoVideo(q.tempo_s)}, ${V.quadroN(q.indice)}`],
      [V.escala, q.escala ? `${V.escalaCurta(fmt(q.escala[0], 1), fmt(q.escala[1], 1))} (${V.fontes[q.fonte_escala] || q.fonte_escala})` : V.fontes.sem_escala],
      [V.tempo, q.preparo ? V.preparo(q.ms) : `${q.ms} ms`]];
    if (q.pulados) pares.push([V.perdidos, V.pulados(q.pulados)]);
    nesteQuadro.replaceChildren(
      el("dl", { class: "pares" }, pares.flatMap(([t, v]) => [el("dt", {}, t), el("dd", {}, v)])),
      q.erro ? el("p", { class: "erro-dialogo" }, V.erroQuadro) : null,
      regioes.length ? el("ul", { class: "lista-regioes-video" }, regioes.map((r) => el("li", {}, el("i", { class: "traco", style: { "--sev": `var(--${r.severidade || "sem_medida"})` } }),
        el("span", { class: "corta" }, r.nome), el("b", { class: "num" }, temperatura(r.t_max)), r.severidade ? selo(r.severidade) : el("span"))))
        : el("p", { class: "nota" }, V.semRegioes));
  }

  // ---------------------------------------------------------------- reprodução no ritmo em que os quadros foram analisados
  function agendarProximo() {
    clearTimeout(relogioTocar);
    if (!tocando) return;
    const q = quadros[atual], prox = quadros[atual + 1];
    if (!prox) { tocando = false; if (ativo()) seguindo = true; marcarTocar(); if (q) mostrarQuadro(atual); return; }
    const espera = Math.max(30, ((prox.tempo_s - q.tempo_s) / (Number(ritmo.querySelector("select").value) || 1)) * 1000);
    relogioTocar = setTimeout(() => { mostrarQuadro(atual + 1); agendarProximo(); }, espera);
  }
  function marcarTocar() {
    tocarBtn.querySelector("use").setAttribute("href", tocando ? "#i-pausar" : "#i-tocar");
    tocarBtn.setAttribute("aria-label", tocando ? V.pausar : V.tocar);
    tocarBtn.title = `${tocando ? V.pausar : V.tocar} (${V.espaco})`;
  }
  function alternarTocar() {
    if (!quadros.length) return;
    if (tocando) { pausar(); return; }
    seguindo = false;
    if (atual >= quadros.length - 1 && !ativo()) mostrarQuadro(0);
    tocando = true;
    marcarTocar();
    desenharHud(quadros[atual]);
    agendarProximo();
  }
  function pausar() {
    tocando = false;
    clearTimeout(relogioTocar);
    marcarTocar();
    if (quadros[atual]) desenharHud(quadros[atual]);
  }
  function irParaQuadro(n) {
    pausar();
    seguindo = false;
    mostrarQuadro(Math.max(0, Math.min(n, quadros.length - 1)));
  }
  function irParaTempo(t) {
    if (!quadros.length) return;
    let melhor = 0;
    quadros.forEach((q, i) => { if (Math.abs(q.tempo_s - t) < Math.abs(quadros[melhor].tempo_s - t)) melhor = i; });
    irParaQuadro(melhor);
  }

  // espaço reproduz ou pausa; ← → andam um quadro (fora de campos)
  const teclado = (ev) => {
    const alvo = ev.target instanceof Element ? ev.target : document.body;
    if (alvo.closest("input:not([type=range]), textarea, select, [role=tablist]") || document.querySelector("dialog[open]")) return;
    if (ev.key === " " && ev.target.tagName === "BUTTON") return;
    if (ev.key === " ") alternarTocar();
    else if (ev.key === "ArrowRight" && ev.target !== linha) irParaQuadro(atual + 1);
    else if (ev.key === "ArrowLeft" && ev.target !== linha) irParaQuadro(atual - 1);
    else return;
    ev.preventDefault();
  };
  document.addEventListener("keydown", teclado);

  receber(d, true);
  return () => { clearTimeout(relogioSonda); clearTimeout(relogioTocar); grafico?.encerrar(); document.removeEventListener("keydown", teclado); };
}
