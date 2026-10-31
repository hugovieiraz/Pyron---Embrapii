// Mapa das telas da interface nova (Etapa 1: 6 itens + Configurações). Cada tela é um módulo em js/telas/
// que exporta montar(pagina, rota) e pode devolver uma função de limpeza.
import { TEXTOS as T } from "../textos.js";

export const ROTAS = {
  painel: { titulo: T.telas.painel, modulo: "painel", atalho: "1", icone: "painel" },
  inspecoes: { titulo: T.telas.inspecoes, modulo: "inspecoes", esqueleto: "lista", atalho: "2", icone: "inspecoes", detalhe: "analise" },
  equipamentos: { titulo: T.telas.equipamentos, modulo: "equipamentos", atalho: "3", icone: "equipamentos", detalhe: "equipamento", esqueleto: "lista" },
  pendencias: { titulo: T.telas.pendencias, modulo: "pendencias", atalho: "4", icone: "pendencias", esqueleto: "lista" },
  captura: { titulo: T.telas.captura, modulo: "captura", detalhe: "captura", atalho: "5", icone: "captura" },
  medicao: { titulo: T.telas.medicao, modulo: "medicao", atalho: "6", icone: "regua" },
  modelos: { titulo: T.telas.modelos, modulo: "modelos", atalho: "7", icone: "modelos" },
  configuracoes: { titulo: T.telas.configuracoes, modulo: "configuracoes", atalho: "0", icone: "config", exige: "administracao" },
};

// Endereços de antes da Medição virar tela de topo: #captura/medir[/código] e #modelos/medicao viram #medicao/...
const ANTIGOS = { captura: { medir: ["medicao", "medir"] }, modelos: { medicao: ["medicao", "modelos"] } };

/** "#inspecoes/abc?sev=critico" vira { tela: "inspecoes", partes: ["abc"], params: URLSearchParams }. */
export function lerRota(hash = location.hash) {
  const [caminho, busca = ""] = hash.replace(/^#/, "").split("?");
  let [tela, ...partes] = caminho.split("/").filter(Boolean).map(decodeURIComponent);
  const novo = ANTIGOS[tela]?.[partes[0]];
  if (novo) [tela, ...partes] = [novo[0], novo[1], ...partes.slice(1)];
  return { tela: ROTAS[tela] ? tela : tela ? null : "painel", nome: tela || "painel", partes, params: new URLSearchParams(busca) };
}

/** Monta o endereço de uma tela; usar sempre esta função para links internos. */
export function endereco(tela, partes = [], params = null) {
  const q = params && [...new URLSearchParams(params)].length ? `?${new URLSearchParams(params)}` : "";
  return `#${[tela, ...partes.map(encodeURIComponent)].join("/")}${q}`;
}
