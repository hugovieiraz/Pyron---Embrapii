// Estado da Análise: a inspeção aberta, a matriz de temperatura e as escolhas de exibição.
// As partes da tela (palco, faixa, painel, cabeçalho) assinam com ctx.ouvir() e redesenham o que mudou.
import { TEXTOS as T } from "../../textos.js";
import { api, json, lerPreferencia, guardarPreferencia, pode } from "../base.js";
import { avisar } from "../componentes.js";

const CAMPOS_REGIAO = ["id", "nome", "classe", "caixa", "confianca", "origem", "segmentacao", "classificacao_dinov2"];

/** Matriz em base64 (float32 little-endian) para Float32Array, com mínimo e máximo dos valores válidos. */
function lerMatriz(m) {
  if (!m) return null;
  const bytes = Uint8Array.from(atob(m.dados), (c) => c.charCodeAt(0));
  const valores = new Float32Array(bytes.buffer);
  let lo = Infinity, hi = -Infinity, validos = 0;
  for (const v of valores) if (Number.isFinite(v)) { validos++; if (v < lo) lo = v; if (v > hi) hi = v; }
  return { W: m.largura, H: m.altura, valores, lo, hi, validos };
}

export function criarContexto({ analise, paletas, config, vizinhas }) {
  const ouvintes = new Set();
  const ctx = {
    a: null, m: null, paletas, config, vizinhas,
    sel: null,                       // região selecionada
    ferramenta: "selecionar",
    paleta: "ferro",
    faixa: { modo: "equipamento", manual: null },
    camadas: { regioes: true, rotulos: true, pontos: true, contornos: true, medicoes: true, ...lerPreferencia("camadas", {}) },
    isoterma: { ligada: false, valor: null },
    foto: false,
    salvo: { estado: "salvo", em: null },
    podeEditar: pode("revisao"),     // técnico (modo servidor) vê, comenta e acompanha; quem edita é o engenheiro

    ouvir(fn) { ouvintes.add(fn); return () => ouvintes.delete(fn); },
    mudou(parte = "tudo") { for (const fn of ouvintes) fn(parte); },

    regiao(id = ctx.sel) { return ctx.a?.regioes.find((r) => r.id === id) || null; },
    selecionar(id) { ctx.sel = id && ctx.regiao(id) ? id : null; ctx.mudou("selecao"); },
    faixaAtual() {
      if (ctx.faixa.modo === "manual" && ctx.faixa.manual) return ctx.faixa.manual;
      if (ctx.faixa.modo === "cena" && ctx.m) return [ctx.m.lo, ctx.m.hi];
      return ctx.a.matriz_info?.faixa_exibicao || [ctx.m?.lo ?? 0, ctx.m?.hi ?? 1];
    },
    temperatura(x, y) {
      if (!ctx.m || ctx.a.sem_temperatura) return null;
      const i = Math.floor(y) * ctx.m.W + Math.floor(x);
      const v = ctx.m.valores[i];
      return Number.isFinite(v) ? v : null;
    },
    guardarCamadas() { guardarPreferencia("camadas", ctx.camadas); },
  };

  /** Troca a inspeção aberta (resposta da API) mantendo seleção e exibição quando fazem sentido. */
  ctx.aplicar = (a, { manterExibicao = true, parte = "tudo" } = {}) => {
    const outra = !ctx.a || ctx.a.id !== a.id;
    const { matriz, ...resto } = a;
    ctx.a = resto;
    if (matriz) ctx.m = lerMatriz(matriz);
    if (outra || !manterExibicao) {
      const ex = a.exibicao || {};
      ctx.paleta = ex.paleta && paletas[ex.paleta] ? ex.paleta : "ferro";
      ctx.faixa = ex.faixa ? { modo: "manual", manual: ex.faixa } : { modo: "equipamento", manual: null };
      ctx.isoterma = { ligada: false, valor: null };
      ctx.foto = false;
    }
    if (ctx.sel && !ctx.regiao(ctx.sel)) ctx.sel = null;
    ctx.mudou(parte);
  };

  // ---------------------------------------------------------------- salvar (com o estado "Salvo" no cabeçalho)
  // parte "dados": o formulário em edição não é reconstruído (o foco fica onde o usuário está digitando)
  async function salvar(acao, parte = "tudo") {
    ctx.salvo = { estado: "salvando", em: ctx.salvo.em };
    ctx.mudou("salvo");
    try {
      const a = await acao();
      ctx.salvo = { estado: "salvo", em: new Date() };
      if (a) ctx.aplicar(a, { parte });
      ctx.mudou("salvo");
      return a;
    } catch (erro) {
      ctx.salvo = { estado: "erro", em: ctx.salvo.em };
      ctx.mudou("salvo");
      throw erro;
    }
  }
  // Uma gravação por vez, cada uma com a revisão que a tela conhece: se outra pessoa gravou antes, o servidor
  // responde 409 em vez de apagar a edição dela (modo servidor, vários engenheiros na mesma inspeção).
  let fila = Promise.resolve();
  const put = (corpo, parte) => {
    if (!ctx.podeEditar) return Promise.reject(new Error(T.analise.soEngenheiroEdita));
    const vez = fila.then(() => salvar(() => api(`/api/analises/${ctx.a.id}`, json("PUT", { ...corpo, revisao: ctx.a.revisao ?? 0 })), parte));
    fila = vez.catch(() => {});
    return vez;
  };
  const avisarConflito = (erro) => {
    if (erro?.status === 409) avisar(T.analise.conflito, { erro: true, acao: { rotulo: T.analise.recarregar, executar: () => location.reload() } });
  };
  ctx.salvar = salvar;
  ctx.salvarRegioes = (regioes) => put({ regioes: regioes.map((r) => Object.fromEntries(CAMPOS_REGIAO.filter((k) => r[k] !== undefined).map((k) => [k, r[k]]))) });
  ctx.salvarMedicoes = (lista) => put({ medicoes: lista.map(({ id, tipo, x, y, x0, y0, x1, y1 }) => ({ id, tipo, x, y, x0, y0, x1, y1 })) });

  // edições que acontecem em sequência (escala, condições, identificação) esperam o usuário parar
  const adiados = {};
  ctx.salvarDepois = (chave, corpo, espera = 700) => {
    if (!ctx.podeEditar) return; // exibição (paleta, escala) muda só nesta tela
    clearTimeout(adiados[chave]);
    ctx.salvo = { estado: "salvando", em: ctx.salvo.em };
    ctx.mudou("salvo");
    adiados[chave] = setTimeout(() => put(typeof corpo === "function" ? corpo() : corpo, "dados").catch(avisarConflito), espera);
  };
  ctx.salvarExibicao = () => ctx.salvarDepois("exibicao", () => ({ exibicao: { paleta: ctx.paleta, faixa: ctx.faixa.modo === "manual" ? ctx.faixa.manual : null } }));
  ctx.encerrar = () => Object.values(adiados).forEach(clearTimeout);

  ctx.aplicar(analise);
  return ctx;
}
