// Medição: medir objetos em foto comum, à parte da parte térmica. Abas Medir (uma medida por vez, nada guardado;
// docs/07_roteiro_medicao_geral.md) e Modelos (o que está instalado, a placa de vídeo e o Instalar); cada aba é um
// módulo em js/medicao/ (js/telaAbas.js). Os endereços antigos #captura/medir e #modelos/medicao caem aqui (js/rotas.js).
import { TEXTOS as T } from "../../textos.js";
import { telaComAbas } from "../telaAbas.js";

const K = T.medicao;
const ABAS = ["medir", "modelos"];

export async function montar(pagina, rota) {
  const tela = await telaComAbas(pagina, rota, {
    tela: "medicao", titulo: T.telas.medicao, rotulo: K.abas,
    abas: ABAS.map((id) => ({ id, texto: K.aba[id] })),
    carregar: (id) => import(`../medicao/${id}.js`),
  });
  return tela.limpar;
}
