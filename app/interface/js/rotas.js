// Mapa das telas da interface nova (Etapa 1: 6 itens + Configurações). Cada tela é um módulo em js/telas/
// que exporta montar(pagina, rota) e pode devolver uma função de limpeza.
import { TEXTOS as T } from "../textos.js";

export const ROTAS = {
  painel: { titulo: T.telas.painel, modulo: "painel", atalho: "1", icone: "painel" },
  inspecoes: { titulo: T.telas.inspecoes, modulo: "inspecoes", esqueleto: "lista", atalho: "2", icone: "inspecoes", detalhe: "analise" },
  equipamentos: { titulo: T.telas.equipamentos, modulo: "provisoria", atalho: "3", icone: "equipamentos", detalhe: "provisoria" },
  pendencias: { titulo: T.telas.pendencias, modulo: "provisoria", atalho: "4", icone: "pendencias" },
  captura: { titulo: T.telas.captura, modulo: "captura", detalhe: "captura", atalho: "5", icone: "captura" },
  modelos: { titulo: T.telas.modelos, modulo: "provisoria", atalho: "6", icone: "modelos" },
  configuracoes: { titulo: T.telas.configuracoes, modulo: "provisoria", atalho: "0", icone: "config" },
};

/** "#inspecoes/abc?sev=critico" vira { tela: "inspecoes", partes: ["abc"], params: URLSearchParams }. */
export function lerRota(hash = location.hash) {
  const [caminho, busca = ""] = hash.replace(/^#/, "").split("?");
  const [tela, ...partes] = caminho.split("/").filter(Boolean).map(decodeURIComponent);
  return { tela: ROTAS[tela] ? tela : tela ? null : "painel", nome: tela || "painel", partes, params: new URLSearchParams(busca) };
}

/** Monta o endereço de uma tela; usar sempre esta função para links internos. */
export function endereco(tela, partes = [], params = null) {
  const q = params && [...new URLSearchParams(params)].length ? `?${new URLSearchParams(params)}` : "";
  return `#${[tela, ...partes.map(encodeURIComponent)].join("/")}${q}`;
}
