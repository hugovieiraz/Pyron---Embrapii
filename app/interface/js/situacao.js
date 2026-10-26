// Regras de leitura da lista de inspeções usadas pelo Painel e por Inspeções: ordem de severidade,
// data de referência de cada inspeção e a situação atual de cada equipamento.
import { TEXTOS as T } from "../textos.js";
import { fmt, temperatura } from "./base.js";

export { ORDEM_SEVERIDADE } from "./analise/faixa.js";
import { ORDEM_SEVERIDADE } from "./analise/faixa.js";

export const SEM_EQUIPAMENTO = "sem-equipamento";
export const CRITICAS = ["urgente", "imediato"];

/** Filtros de severidade das listas: valor do endereço (?sev=) → níveis que entram. */
export const FILTROS_SEVERIDADE = {
  todas: null,
  criticas: CRITICAS,
  programar: ["programar"],
  atencao: ["atencao"],
  normais: ["normal"],
  sem: ["sem_medida", "nao_avaliado"],
};

/** Data da captura (a da câmera) ou, sem ela, a da importação. */
export const quando = (it) => String(it.data_captura || it.criado_em || "").replace(" ", "T");

export const severidade = (it) => it.resumo?.severidade || "sem_medida";
export const pesoSeveridade = (nivel) => {
  const i = ORDEM_SEVERIDADE.indexOf(nivel);
  return i < 0 ? ORDEM_SEVERIDADE.length : i;
};

/**
 * Situação atual: de cada equipamento, só a inspeção mais recente (uma normal depois de uma grave quer
 * dizer que o equipamento está normal agora; a anomalia antiga segue em Pendências até a correção ser
 * verificada). Inspeções sem equipamento valem cada uma por si.
 */
export function situacaoAtual(lista) {
  const ultimas = new Map();
  const soltas = [];
  for (const it of lista) {
    const chave = it.equipamento_chave;
    if (!chave || chave === SEM_EQUIPAMENTO) { soltas.push(it); continue; }
    const antes = ultimas.get(chave);
    if (!antes || quando(it) > quando(antes)) ultimas.set(chave, it);
  }
  return [...ultimas.values(), ...soltas];
}

/** A leitura que decide a severidade da inspeção: % da MTA, ΔT ou Tmáx, nessa ordem. */
export function leituraDestaque(d) {
  if (!d) return null;
  if (d.pct_mta != null) return T.inspecoes.pctMta(fmt(d.pct_mta, 0));
  if (d.dt != null) return T.inspecoes.dt(fmt(d.dt, 1));
  return d.t_max != null ? temperatura(d.t_max) : null;
}

/** Miniatura com a severidade e o número de regiões no endereço: muda quando a análise muda. */
export const miniatura = (it) => `/api/analises/${it.id}/miniatura.png?v=${encodeURIComponent(`${severidade(it)}-${it.resumo?.regioes ?? 0}`)}`;
