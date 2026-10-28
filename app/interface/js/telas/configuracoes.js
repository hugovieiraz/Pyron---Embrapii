// Configurações (Etapa 5d): o que muda o laudo e o sistema. Abas Empresa e time, Critério, Componentes,
// Aparência, Dados e backup e Sobre (decisão da Etapa 1); cada aba é um módulo em js/configuracoes/.
import { TEXTOS as T } from "../../textos.js";
import { telaComAbas } from "../telaAbas.js";

const C = T.config;
const ABAS = ["empresa", "criterio", "componentes", "aparencia", "dados", "sobre"];

export async function montar(pagina, rota) {
  const tela = await telaComAbas(pagina, rota, {
    tela: "configuracoes", titulo: T.telas.configuracoes, rotulo: C.abas,
    abas: ABAS.map((id) => ({ id, texto: C.aba[id] })),
    carregar: (id) => import(`../configuracoes/${id}.js`),
  });
  return tela.limpar;
}
