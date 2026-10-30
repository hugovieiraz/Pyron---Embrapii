// Conferência automática da página aberta: contraste de cada texto visível (WCAG 1.4.3) e tamanho de
// cada alvo clicável (≥ 44 px; 36 px só nos compactos com mouse). Usada pelo catálogo e pelos testes visuais.

const rgba = (s) => {
  const m = s.match(/rgba?\(([^)]+)\)/);
  if (!m) return [255, 255, 255, 1];
  const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
  return [p[0], p[1], p[2], p[3] ?? 1];
};
const sobre = ([r, g, b, a], [R, G, B]) => [r * a + R * (1 - a), g * a + G * (1 - a), b * a + B * (1 - a)];
const luz = (c) => {
  const [r, g, b] = c.map((v) => v / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
export const razao = (a, b) => { const [x, y] = [luz(a), luz(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

/** Cor de fundo efetiva: compõe os fundos semitransparentes dos ancestrais até achar um opaco. */
function fundoDe(no) {
  const camadas = [];
  for (let n = no; n && n.nodeType === 1; n = n.parentElement) {
    const c = rgba(getComputedStyle(n).backgroundColor);
    if (c[3] > 0) camadas.push(c);
    if (c[3] >= 1) break;
  }
  let base = rgba(getComputedStyle(document.body).backgroundColor);
  if (base[3] < 1) base = [255, 255, 255, 1];
  let cor = base.slice(0, 3);
  for (const c of camadas.reverse()) cor = sobre(c, cor);
  return cor;
}

const visivel = (n) => {
  const r = n.getBoundingClientRect();
  if (!r.width || !r.height) return false;
  const s = getComputedStyle(n);
  return s.visibility !== "hidden" && s.opacity !== "0";
};
const caminho = (n) => {
  const partes = [];
  for (let x = n; x && x !== document.body && partes.length < 3; x = x.parentElement) partes.unshift(x.tagName.toLowerCase() + (x.id ? `#${x.id}` : x.classList.length ? `.${[...x.classList].join(".")}` : ""));
  return partes.join(" > ");
};

export function conferir({ toque = false, raiz = document.body } = {}) {
  const contraste = [];
  let textos = 0;
  for (const n of raiz.querySelectorAll("*")) {
    // texto de controle inativo (e o rótulo dele) fica fora da regra de contraste (WCAG 1.4.3)
    if (n.closest("[aria-hidden='true'], .esq, svg, script, style, [disabled], [aria-disabled='true'], label:has(:disabled), .ignorar-conferencia")) continue;
    if (![...n.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim())) continue;
    if (!visivel(n)) continue;
    const s = getComputedStyle(n);
    if (s.color === "rgba(0, 0, 0, 0)" || s.color === "transparent") continue;
    textos++;
    const fundo = fundoDe(n);
    const frente = sobre(rgba(s.color), fundo);
    const tam = parseFloat(s.fontSize);
    const grande = tam >= 24 || (tam >= 18.66 && Number(s.fontWeight) >= 700);
    const minimo = grande ? 3 : 4.5;
    const r = razao(frente, fundo);
    if (r < minimo) contraste.push({ onde: caminho(n), texto: n.textContent.trim().slice(0, 40), razao: +r.toFixed(2), minimo });
  }

  const alvos = [];
  let clicaveis = 0;
  const seletor = "a[href], button, input:not([type='hidden']), select, textarea, summary, [role='tab'], [role='option'], [role^='menuitem'], [tabindex='0']";
  for (const n of raiz.querySelectorAll(seletor)) {
    if (!visivel(n) || n.closest("[hidden], .ignorar-conferencia")) continue;
    if (n.matches("a") && n.closest("p, dd, li.texto")) continue; // link dentro de frase: exceção da WCAG 2.5.8
    const alvo = n.matches("input[type='checkbox'], input[type='radio']") ? n.closest("label") || n : n;
    if (n.matches("[role='tabpanel']")) continue;
    clicaveis++;
    const r = alvo.getBoundingClientRect();
    const compacto = !toque && (alvo.matches(".compacto, .menu [role^='menuitem'], .segmentado button, .tabela th button, .secao > summary") || alvo.closest(".compacto"));
    const minimo = compacto ? 36 : 44;
    const menor = Math.min(Math.round(r.width), Math.round(r.height));
    if (menor < minimo) alvos.push({ onde: caminho(alvo), tamanho: `${Math.round(r.width)}×${Math.round(r.height)}`, minimo });
  }
  return { textos, contraste, clicaveis, alvos };
}
