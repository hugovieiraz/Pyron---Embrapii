// Modelos (Etapa 5d): os detectores, o treino e a avaliação. Abas Em uso, Treino e Avaliação (decisão da
// Etapa 1: avaliar é parte de escolher o modelo); cada aba é um módulo em js/modelos/ (js/telaAbas.js).
// Os modelos de medir em foto comum saíram daqui: ficam na tela Medição (js/telas/medicao.js).
import { TEXTOS as T } from "../../textos.js";
import { telaComAbas } from "../telaAbas.js";

const M = T.modelos;
const ABAS = ["emuso", "treino", "avaliacao"];

export async function montar(pagina, rota) {
  const tela = await telaComAbas(pagina, rota, {
    tela: "modelos", titulo: T.telas.modelos, rotulo: M.abas,
    abas: ABAS.map((id) => ({ id, texto: M.aba[id] })),
    carregar: (id) => import(`../modelos/${id}.js`),
  });
  return tela.limpar;
}
