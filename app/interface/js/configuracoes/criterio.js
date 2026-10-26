// Configurações › Critério: os limites que decidem a severidade (% da MTA, ΔT entre semelhantes, ΔT sobre o
// ambiente). Salvar é explícito porque recalcula todas as inspeções; dá para partir de um modelo (Brasil ou
// NETA) e voltar ao padrão. Campo vazio = aquele nível não é usado no grupo.
import { TEXTOS as T } from "../../textos.js";
import { el, api, json, fmt, lerNumero } from "../base.js";
import { botao, campo, marcar, selo, avisar, confirmar, ocupado } from "../componentes.js";

const C = T.config;
const GRUPOS = { mta_faixas: "%", similares: "°C", dieletrico: "°C", ambiente: "°C" };
const NIVEIS = ["atencao", "programar", "urgente", "imediato"];

export async function montar(no) {
  let cfg = await api("/api/configuracoes");
  const inspecoes = (await api("/api/sistema").catch(() => ({ inspecoes: null }))).inspecoes;
  const estado = el("span", { class: "nota" });
  const erro = el("p", { class: "erro-dialogo", role: "alert", hidden: true });
  const grupos = el("div", { class: "grade-criterio" });
  const nome = campo({ rotulo: C.critNome, valor: "", autocomplete: "off" });
  const expoente = campo({ rotulo: C.critExpoente, tipo: "number", valor: "", ajuda: C.critExpoenteAjuda });
  const carga = campo({ rotulo: C.critCarga, tipo: "number", valor: "", unidade: "%", ajuda: C.critCargaAjuda });
  const usarAmbiente = marcar({ rotulo: C.critUsarAmbiente });
  usarAmbiente.querySelector("input").addEventListener("change", () => grupos.querySelector('[data-grupo="ambiente"]').classList.toggle("desligado", !usarAmbiente.querySelector("input").checked));

  function preencher(crit) {
    grupos.replaceChildren(...Object.entries(GRUPOS).map(([g, unidade]) => el("section", { class: `grupo-criterio${g === "ambiente" && !crit.usar_ambiente ? " desligado" : ""}`, dataset: { grupo: g } },
      el("h3", {}, C.grupos[g]),
      el("p", { class: "nota" }, C.cadaNivel),
      g === "ambiente" ? usarAmbiente : null,
      ...NIVEIS.map((n) => {
        const achado = (crit[g] || []).find(([, x]) => x === n);
        const c = campo({ rotulo: C.aPartirDe(T.niveis[n]), tipo: "number", valor: achado ? fmt(achado[0], achado[0] % 1 ? 1 : 0) : "", unidade, marcador: C.naoUsar, "data-grupo": g, "data-nivel": n });
        return el("div", { class: "linha-criterio" }, selo(n), c);
      }))));
    usarAmbiente.querySelector("input").checked = Boolean(crit.usar_ambiente);
    nome.querySelector("input").value = crit.nome || "";
    expoente.querySelector("input").value = fmt(crit.expoente_carga, 1);
    carga.querySelector("input").value = fmt(crit.carga_minima_pct, 0);
    estado.textContent = cfg.criterio_personalizado ? C.critPersonalizado : C.critPadrao;
  }

  function ler() {
    const grupo = (g) => [...grupos.querySelectorAll(`input[data-grupo="${g}"]`)].map((i) => [lerNumero(i.value), i.dataset.nivel]).filter(([v]) => v != null);
    return { nome: nome.querySelector("input").value.trim(), mta_faixas: grupo("mta_faixas"), similares: grupo("similares"), dieletrico: grupo("dieletrico"), ambiente: grupo("ambiente"),
      usar_ambiente: usarAmbiente.querySelector("input").checked, expoente_carga: lerNumero(expoente.querySelector("input").value) ?? 2, carga_minima_pct: lerNumero(carga.querySelector("input").value) ?? 40 };
  }

  async function salvar(criterio, b, mensagem) {
    await ocupado(b, async () => {
      try {
        cfg = await api("/api/configuracoes", json("PUT", { criterio }));
        erro.hidden = true;
        preencher(cfg.criterio);
        avisar(mensagem);
      } catch (e) { erro.textContent = e.message; erro.hidden = false; }
    });
  }

  const salvarBtn = botao({ texto: C.critSalvar, variante: "primario", onclick: () => salvar(ler(), salvarBtn, C.critSalvo(inspecoes)) });
  const padraoBtn = botao({ texto: C.restaurarPadrao, variante: "fantasma", onclick: async () => {
    if (!(await confirmar({ titulo: C.critPadraoTitulo, texto: C.critPadraoTexto(cfg.criterio_padrao.nome), confirmar: C.restaurarPadrao }))) return;
    await salvar(null, padraoBtn, C.critRestaurado);
  } });
  const modelo = (chave) => botao({ texto: C.modelosCriterio[chave], compacto: true, onclick: () => { preencher(cfg.modelos_criterio[chave]); avisar(C.modeloAplicado); } });

  preencher(cfg.criterio);
  no.append(el("div", { class: "coluna-config larga" },
    el("div", { class: "titulo-bloco" }, el("h2", {}, C.critTitulo), estado),
    el("p", { class: "nota" }, C.critNota),
    el("div", { class: "barra-lista" }, el("span", { class: "nota" }, C.partirDe), modelo("brasil"), modelo("neta")),
    erro, grupos,
    el("div", { class: "grade-campos-3" }, nome, expoente, carga),
    el("div", { class: "rodape-form" }, padraoBtn, salvarBtn)));
  return null;
}
