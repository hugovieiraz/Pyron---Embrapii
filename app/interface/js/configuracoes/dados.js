// Configurações › Dados e backup: onde ficam os dados, quanto ocupam, o backup (.zip) e a restauração.
// Restaurar troca tudo: pede confirmação (o estado atual fica guardado antes, numa pasta de backups).
import { TEXTOS as T } from "../../textos.js";
import { el, icone, api, json, fmt, nesteComputador } from "../base.js";
import { botao, avisar, confirmar, ocupado } from "../componentes.js";

const C = T.config;
const tamanho = (b) => (b >= 1024 ** 3 ? `${fmt(b / 1024 ** 3, 1)} GB` : `${fmt(b / 1024 ** 2, b < 10 * 1024 ** 2 ? 1 : 0)} MB`);

export async function montar(no) {
  const s = await api("/api/sistema");
  const abrir = botao({ texto: C.abrirPasta, icone: "pasta", compacto: true, variante: "fantasma", onclick: () => ocupado(abrir, async () => {
    try { await api("/api/sistema/abrir-pasta", json("POST", { qual: "dados" })); } catch (e) { avisar(e.message, { erro: true }); }
  }) });
  const entrada = el("input", { type: "file", accept: ".zip", hidden: true, onchange: () => { restaurar(entrada.files[0]); entrada.value = ""; } });
  const restaurarBtn = botao({ texto: C.restaurar, icone: "refazer", onclick: () => entrada.click() });

  async function restaurar(arquivo) {
    if (!arquivo) return;
    if (!(await confirmar({ titulo: C.restaurarTitulo, texto: C.restaurarTexto(arquivo.name), confirmar: C.restaurar, perigo: true }))) return;
    const envio = new FormData();
    envio.append("arquivo", arquivo);
    await ocupado(restaurarBtn, async () => {
      try {
        const r = await api("/api/backup/restaurar", { method: "POST", body: envio });
        avisar(C.restaurado(r.inspecoes ?? 0));
        setTimeout(() => location.reload(), 1500);
      } catch (e) { avisar(e.message, { erro: true }); }
    });
  }

  no.append(el("div", { class: "coluna-config" },
    el("div", { class: "titulo-bloco" }, el("h2", {}, C.dadosTitulo)),
    el("dl", { class: "pares" },
      el("dt", {}, C.pastaDados), el("dd", { class: "mono corta", title: s.pasta_dados }, s.pasta_dados),
      el("dt", {}, C.inspecoes), el("dd", { class: "num" }, String(s.inspecoes)),
      el("dt", {}, C.ocupa), el("dd", { class: "num" }, s.bytes_videos ? C.ocupaComVideos(tamanho(s.bytes), tamanho(s.bytes_videos)) : tamanho(s.bytes))),
    nesteComputador() ? el("div", { class: "grupo-btn" }, abrir) : null, // pelo navegador de outro aparelho, não há pasta para abrir
    el("div", { class: "titulo-bloco" }, el("h2", {}, C.backupTitulo)),
    el("p", { class: "nota" }, C.backupNota),
    el("div", { class: "grupo-btn" }, el("a", { class: "btn primario", href: "/api/backup.zip", download: "" }, icone("baixar"), el("span", {}, C.baixarBackup)), nesteComputador() ? [restaurarBtn, entrada] : null))); // restaurar: só no computador do servidor
  return null;
}
