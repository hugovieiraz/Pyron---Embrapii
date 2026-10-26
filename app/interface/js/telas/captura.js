// Captura (Etapa 5c): as fontes de imagem que chegam sozinhas e o resultado delas. Abas Pasta monitorada,
// Vídeo, Celular e Alertas (decisão da Etapa 1); cada aba é um módulo em js/captura/ (js/telaAbas.js).
import { TEXTOS as T } from "../../textos.js";
import { el, api } from "../base.js";
import { telaComAbas } from "../telaAbas.js";

const K = T.captura;
const ABAS = ["pasta", "video", "celular", "alertas"];

export async function montar(pagina, rota) {
  const status = await api("/api/status");
  const meta = el("div", { class: "meta" });

  // linha de estado no cabeçalho: a pasta monitorada ligada, com erro ou desligada
  function desenharMeta(s) {
    const m = s.monitoramento || {};
    meta.replaceChildren(el("span", { class: `estado-fonte${m.ativo && !m.erro ? " ligada" : m.erro && m.ativo ? " erro" : ""}` },
      m.ativo ? (m.erro ? K.metaErro : K.metaVigiando) : K.metaDesligado));
  }
  desenharMeta(status);

  let tela = null;
  const contarAlertas = (n) => { tela?.contar("alertas", n); document.dispatchEvent(new CustomEvent("pyron:alertas")); };
  tela = await telaComAbas(pagina, rota, {
    tela: "captura", titulo: T.telas.captura, rotulo: K.abas, meta,
    abas: ABAS.map((id) => ({ id, texto: K.aba[id], qtd: id === "alertas" && status.alertas_pendentes ? status.alertas_pendentes : null })),
    carregar: (id) => import(`../captura/${id}.js`),
    ctx: { aoMudarEstado: desenharMeta, contarAlertas },
  });
  return tela.limpar;
}
