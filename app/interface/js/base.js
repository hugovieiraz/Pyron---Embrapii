// Utilitários da interface nova: DOM, API, formatação e preferências. Sem dependência externa.
import { TEXTOS as T } from "../textos.js";

export const VERSAO_INTERFACE = "0.7.7"; // igual a VERSAO em app/servidor.py

export const $ = (s, raiz = document) => raiz.querySelector(s);
export const $$ = (s, raiz = document) => [...raiz.querySelectorAll(s)];

/** Cria um elemento: el("button", { class: "btn", onclick }, filhos...). */
export function el(tag, props = {}, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "style") Object.assign(n.style, v);
    else if (k === "dataset") Object.assign(n.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (k in n && typeof v !== "string") n[k] = v;
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const f of filhos.flat(Infinity)) if (f != null && f !== false) n.append(f instanceof Node ? f : document.createTextNode(String(f)));
  return n;
}

export function icone(nome, classe = "ic") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", classe);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${nome}`);
  svg.append(use);
  return svg;
}

// ---------------------------------------------------------------- formatação (pt-BR, Intl)
const numeros = new Map();
export function fmt(v, casas = 1, sufixo = "") {
  if (v == null || !Number.isFinite(Number(v))) return T.geral.semValor;
  if (!numeros.has(casas)) numeros.set(casas, new Intl.NumberFormat("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }));
  return numeros.get(casas).format(Number(v)) + sufixo;
}
export const temperatura = (v, casas = 1) => fmt(v, casas, " °C");

const dataCurta = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
const dataHoraCurta = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
const paraData = (iso) => {
  if (!iso) return null;
  const d = new Date(String(iso).length === 10 ? `${iso}T12:00:00` : String(iso).replace(" ", "T"));
  return Number.isNaN(d.getTime()) ? null : d;
};
export const data = (iso) => { const d = paraData(iso); return d ? dataCurta.format(d) : T.geral.semValor; };
export const dataHora = (iso) => { const d = paraData(iso); return d ? dataHoraCurta.format(d).replace(",", "") : T.geral.semValor; };

/** Lê número digitado com vírgula ou ponto ("31,5", "31.5", "1.234,5"); devolve null se não for número. */
export function lerNumero(texto) {
  let s = String(texto ?? "").trim().replace(/\s/g, "");
  if (!s) return null;
  if (s.includes(",") && s.includes(".")) s = s.replace(/\./g, "");
  const v = Number(s.replace(",", "."));
  return Number.isFinite(v) ? v : null;
}

/** Texto comparável: sem acento, minúsculo, espaços simples (busca tolerante). */
export const normalizar = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();

// ---------------------------------------------------------------- tokens lidos pelo JS (canvas, durações)
export const token = (nome) => getComputedStyle(document.documentElement).getPropertyValue(`--${nome}`).trim();
export const corNivel = (nivel) => token(nivel) || token("sem_medida");
export const duracao = (nome) => (matchMedia("(prefers-reduced-motion: reduce)").matches ? 1 : parseFloat(token(`dur-${nome}`)) || 0);

// ---------------------------------------------------------------- preferências deste computador (só conveniência)
const PREFIXO = "pyron.nova.";
export function lerPreferencia(chave, padrao) {
  try {
    const v = localStorage.getItem(PREFIXO + chave);
    return v == null ? padrao : JSON.parse(v);
  } catch {
    return padrao;
  }
}
export function guardarPreferencia(chave, valor) {
  try { localStorage.setItem(PREFIXO + chave, JSON.stringify(valor)); } catch { /* armazenamento bloqueado: segue sem lembrar */ }
}

// ---------------------------------------------------------------- API
// A casca escuta estes eventos para mostrar e esconder a faixa "sem conexão".
export const conexao = new EventTarget();
let versaoServidor = null;
export const definirVersaoServidor = (v) => { versaoServidor = v; };

export async function api(caminho, opcoes = {}) {
  let r;
  try {
    r = await fetch(caminho, opcoes);
  } catch {
    conexao.dispatchEvent(new Event("caiu"));
    throw new Error(T.geral.semResposta);
  }
  conexao.dispatchEvent(new Event("voltou"));
  const tipo = r.headers.get("content-type") || "";
  const corpo = tipo.includes("application/json") ? await r.json() : null;
  if (r.status === 404 && versaoServidor && versaoServidor !== VERSAO_INTERFACE) throw new Error(T.geral.versaoDiferente(versaoServidor, VERSAO_INTERFACE));
  if (!r.ok) throw new Error((corpo && (corpo.erro || corpo.detail)) || T.geral.erroServidor(r.status));
  return corpo;
}
export const json = (metodo, corpo) => ({ method: metodo, headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });

/** Entrada escalonada dos primeiros itens de uma lista (no máximo 6). */
export function animarEntrada(nos) {
  nos.slice(0, 6).forEach((n, i) => { n.classList.add("entra-item"); n.style.setProperty("--i", i); });
  return nos;
}
