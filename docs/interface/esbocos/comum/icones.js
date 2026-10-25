// Ícones de traço (24 × 24) usados pelos esboços.
const ICONES = {
  painel: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="4" rx="1.5"/><rect x="13.5" y="10.5" width="7" height="10" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/>',
  inspecoes: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
  equipamentos: '<path d="M4 20V9l5 3V9l5 3V5h6v15z"/><path d="M8 16h2M13 16h2"/>',
  pendencias: '<path d="M14.5 5.5a4 4 0 0 0 4 5.5l-7.5 7.5a2.1 2.1 0 0 1-3-3L15.5 8a4 4 0 0 0-1-2.5z"/>',
  captura: '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
  modelos: '<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/>',
  config: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
  busca: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>',
  sino: '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  importar: '<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5"/><path d="M4 15v4h16v-4"/>',
  laudo: '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h7M9 17h5"/>',
  anterior: '<path d="m14.5 6-6 6 6 6"/>',
  proxima: '<path d="m9.5 6 6 6-6 6"/>',
  selecionar: '<path d="m6 4 12 7-5.5 1.5L10 18z"/>',
  regiao: '<rect x="4.5" y="4.5" width="15" height="15" rx="1" stroke-dasharray="3 2.5"/>',
  ponto: '<circle cx="12" cy="12" r="3"/><path d="M12 3v4M12 17v4M3 12h4M17 12h4"/>',
  linha: '<path d="m5 19 14-14"/><circle cx="5" cy="19" r="1.5"/><circle cx="19" cy="5" r="1.5"/>',
  camadas: '<path d="m12 4 8.5 4.5L12 13 3.5 8.5z"/><path d="m3.5 12.5 8.5 4.5 8.5-4.5"/>',
  detectar: '<path d="M4 9V5h4M16 5h4v4M20 15v4h-4M8 19H4v-4"/><circle cx="12" cy="12" r="3"/>',
  mais: '<circle cx="6" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="18" cy="12" r="1.3"/>',
  foto: '<rect x="3.5" y="5.5" width="17" height="13" rx="2"/><circle cx="9" cy="10" r="1.8"/><path d="m20.5 15-4.5-4.5-8 8"/>',
  regua: '<rect x="3" y="8" width="18" height="8" rx="1" transform="rotate(-30 12 12)"/><path d="m8.5 13.5 1-1.7M11.5 11.8l1-1.7M14.5 10l1-1.7"/>',
};

document.addEventListener("DOMContentLoaded", () => {
  const sprite = Object.entries(ICONES).map(([id, d]) => `<symbol id="i-${id}" viewBox="0 0 24 24">${d}</symbol>`).join("");
  document.body.insertAdjacentHTML("afterbegin", `<svg width="0" height="0" style="position:absolute" aria-hidden="true">${sprite}</svg>`);
});

const ic = (id) => `<svg class="ic" aria-hidden="true"><use href="#i-${id}"/></svg>`;
