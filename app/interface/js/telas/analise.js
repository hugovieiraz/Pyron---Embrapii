// Análise (Etapa 4, tela de referência): uma inspeção aberta. Cabeçalho, barra de ferramentas, termograma
// com escala, faixa de regiões e painel de detalhe. Rota: #inspecoes/<id>.
import { TEXTOS as T } from "../../textos.js";
import { el, api } from "../base.js";
import { estadoVazio } from "../componentes.js";
import { endereco } from "../rotas.js";
import { criarContexto } from "../analise/contexto.js";
import { montarPalco } from "../analise/palco.js";
import { montarFaixa, regioesOrdenadas, apagarRegiao } from "../analise/faixa.js";
import { montarPainel } from "../analise/painel.js";
import { montarCabecalho } from "../analise/cabecalho.js";

const A = T.analise;

export async function montar(pagina, rota) {
  const id = rota.partes[0];
  let analise;
  try {
    analise = await api(`/api/analises/${encodeURIComponent(id)}`);
  } catch (erro) {
    if (erro.status !== 404) throw erro;
    pagina.append(estadoVazio({ ilustracao: "busca", titulo: A.naoEncontrada, texto: A.naoEncontradaTexto, acoes: [el("a", { class: "btn primario", href: endereco("inspecoes") }, A.verInspecoes)] }));
    return null;
  }
  const [paletas, modelos, config, vizinhas, equipamentos] = await Promise.all([
    api("/api/paletas"),
    api("/api/modelos").then((r) => r.modelos),
    api("/api/configuracoes"),
    api(`/api/analises/${analise.id}/vizinhas`).catch(() => ({})),
    api("/api/equipamentos").catch(() => []),
  ]);

  const ctx = criarContexto({ analise, paletas, modelos, config, vizinhas });
  const palco = montarPalco(ctx);
  const faixa = montarFaixa(ctx, { realcar: palco.realcar });
  const painel = montarPainel(ctx, { equipamentos });
  const cab = montarCabecalho(ctx);

  pagina.classList.add("cheia");
  pagina.append(el("div", { class: "tela-analise" },
    cab.cabecalho,
    el("div", { class: "corpo-analise" },
      el("div", { class: "coluna-imagem" }, palco.barra, palco.palco, faixa.faixa),
      painel.painel)));

  // setas percorrem as regiões e Delete apaga a selecionada (fora de campos e da faixa, que cuida do próprio teclado)
  function teclado(ev) {
    if (ev.target.closest("input, textarea, select, .lista-regioes, [role='tablist'], [role='toolbar']") || document.querySelector("dialog[open]")) return;
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
    const ordem = regioesOrdenadas(ctx.a.regioes);
    if (!ordem.length) return;
    if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
      const i = ordem.findIndex((r) => r.id === ctx.sel);
      const passo = ev.key === "ArrowRight" ? 1 : -1;
      ctx.selecionar(ordem[(i < 0 ? (passo > 0 ? 0 : ordem.length - 1) : (i + passo + ordem.length) % ordem.length)].id);
      ev.preventDefault();
    } else if (ev.key === "Delete" && ctx.sel) {
      apagarRegiao(ctx, ctx.sel);
      ev.preventDefault();
    }
  }
  document.addEventListener("keydown", teclado);

  return () => {
    document.removeEventListener("keydown", teclado);
    palco.encerrar();
    faixa.encerrar();
    painel.encerrar();
    cab.encerrar();
    ctx.encerrar();
  };
}
