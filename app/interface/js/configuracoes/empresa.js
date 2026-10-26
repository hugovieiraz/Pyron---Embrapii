// Configurações › Empresa e responsáveis: o cabeçalho do laudo (nome, subtítulo, logotipo) e o cadastro dos
// responsáveis técnicos (o laudo só sai com alguém daqui). Salva sozinho; responsável sem nome ou registro
// ainda não vai para o servidor, que o recusaria enquanto a pessoa digita.
import { TEXTOS as T } from "../../textos.js";
import { el, api, json } from "../base.js";
import { botao, campo, avisar, confirmar } from "../componentes.js";

const C = T.config;
const novoId = () => Math.random().toString(36).slice(2, 10);

export async function montar(no) {
  let cfg = await api("/api/configuracoes");
  const salvo = el("span", { class: "estado-salvo", role: "status" });
  const erro = el("p", { class: "erro-dialogo", role: "alert", hidden: true });

  const nome = campo({ rotulo: C.empresaNome, valor: cfg.empresa?.nome || "", autocomplete: "organization" });
  const sub = campo({ rotulo: C.empresaSub, valor: cfg.empresa?.subtitulo || "", marcador: C.empresaSubMarcador, autocomplete: "off" });

  // ---------------------------------------------------------------- logotipo
  const logo = el("div", { class: "bloco-logo" });
  const entradaLogo = el("input", { type: "file", accept: "image/png,image/jpeg", hidden: true, onchange: () => { enviarLogo(entradaLogo.files[0]); entradaLogo.value = ""; } });
  function desenharLogo() {
    logo.replaceChildren(
      cfg.tem_logo ? el("img", { class: "logo-empresa", src: `/api/configuracoes/logo.png?v=${Date.now()}`, alt: C.logoAlt }) : el("div", { class: "logo-vazio" }, C.semLogo),
      el("div", { class: "grupo-btn" },
        botao({ texto: cfg.tem_logo ? C.logoTrocar : C.logoEnviar, icone: "importar", compacto: true, onclick: () => entradaLogo.click() }),
        cfg.tem_logo ? botao({ texto: C.logoRemover, icone: "lixo", variante: "fantasma", compacto: true, onclick: removerLogo }) : null, entradaLogo),
      el("p", { class: "nota" }, C.logoNota));
  }
  async function enviarLogo(arquivo) {
    if (!arquivo) return;
    const envio = new FormData();
    envio.append("arquivo", arquivo);
    try { await api("/api/configuracoes/logo", { method: "POST", body: envio }); cfg = { ...cfg, tem_logo: true }; desenharLogo(); avisar(C.logoSalvo); } catch (e) { avisar(e.message, { erro: true }); }
  }
  async function removerLogo() {
    if (!(await confirmar({ titulo: C.logoRemoverTitulo, texto: C.logoRemoverTexto, confirmar: C.logoRemover, perigo: true }))) return;
    try { await api("/api/configuracoes/logo", { method: "DELETE" }); cfg = { ...cfg, tem_logo: false }; desenharLogo(); avisar(C.logoRemovido); } catch (e) { avisar(e.message, { erro: true }); }
  }
  desenharLogo();

  // ---------------------------------------------------------------- responsáveis técnicos
  const lista = el("div", { class: "lista-tecnicos" });
  function linha(r = { id: novoId(), nome: "", funcao: "", registro: "" }) {
    const padrao = el("label", { class: "alvo-marcar", title: C.respPadraoDica }, el("input", { type: "radio", name: "resp-padrao", value: r.id, checked: r.id === cfg.responsavel_padrao, "aria-label": C.respPadraoDe(r.nome || C.respNovo) }));
    padrao.querySelector("input").addEventListener("change", definirPadrao);
    const tirar = botao({ texto: C.respTirar(r.nome || C.respNovo), icone: "lixo", variante: "fantasma", soIcone: true, onclick: () => { l.remove(); salvarDepois(0); } });
    const l = el("div", { class: "linha-tecnico", dataset: { id: r.id } }, padrao,
      campo({ rotulo: C.respNome, valor: r.nome, autocomplete: "off" }),
      campo({ rotulo: C.respFuncao, valor: r.funcao || "", marcador: C.respFuncaoMarcador, autocomplete: "off" }),
      campo({ rotulo: C.respRegistro, valor: r.registro, marcador: C.respRegistroMarcador, autocomplete: "off" }), tirar);
    return l;
  }
  lista.append(...cfg.responsaveis.map((r) => linha(r)));
  const semNinguem = el("p", { class: "nota", hidden: cfg.responsaveis.length > 0 }, C.semResponsaveis);
  const adicionar = botao({ texto: C.respAdicionar, icone: "adicionar", compacto: true, onclick: () => { const l = linha(); lista.append(l); semNinguem.hidden = true; l.querySelectorAll("input")[1].focus(); } });

  const lerResponsaveis = () => [...lista.querySelectorAll(".linha-tecnico")].map((l) => {
    const [, n, f, reg] = l.querySelectorAll("input");
    return { id: l.dataset.id, nome: n.value.trim(), funcao: f.value.trim(), registro: reg.value.trim() };
  }).filter((r) => r.nome && r.registro);

  let relogio = null;
  function salvarDepois(espera = 700) {
    clearTimeout(relogio);
    salvo.dataset.estado = "salvando";
    salvo.textContent = T.analise.salvando;
    relogio = setTimeout(() => salvar({ empresa: { nome: nome.querySelector("input").value.trim(), subtitulo: sub.querySelector("input").value.trim() }, responsaveis: lerResponsaveis() }), espera);
  }
  async function salvar(corpo) {
    try {
      cfg = await api("/api/configuracoes", json("PUT", corpo));
      // o servidor pode ter trocado o id de um responsável novo: as linhas passam a usar o id guardado
      const guardados = cfg.responsaveis;
      [...lista.querySelectorAll(".linha-tecnico")].forEach((l) => {
        const nomeLinha = l.querySelectorAll("input")[1].value.trim();
        const r = guardados.find((x) => x.id === l.dataset.id) || guardados.find((x) => x.nome === nomeLinha);
        if (r) { l.dataset.id = r.id; l.querySelector("input[type=radio]").value = r.id; l.querySelector("input[type=radio]").checked = r.id === cfg.responsavel_padrao; }
      });
      erro.hidden = true;
      salvo.dataset.estado = "salvo";
      salvo.textContent = T.analise.salvoEm(new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }));
      return true;
    } catch (e) {
      erro.textContent = e.message;
      erro.hidden = false;
      salvo.dataset.estado = "erro";
      salvo.textContent = T.analise.erroSalvar;
      return false;
    }
  }
  async function definirPadrao(ev) {
    clearTimeout(relogio);
    if (await salvar({ responsaveis: lerResponsaveis() })) await salvar({ responsavel_padrao: ev.target.value });
  }
  no.addEventListener("input", (ev) => { if (ev.target.matches("input:not([type=radio]):not([type=file])")) salvarDepois(); });

  no.append(el("div", { class: "coluna-form coluna-config" },
    el("div", { class: "titulo-bloco" }, el("h2", {}, C.empresaTitulo), salvo),
    erro,
    el("div", { class: "grupo-campos" }, el("div", { class: "grade-campos-2" }, nome, sub), el("div", { class: "campo" }, el("span", { class: "rotulo" }, C.logo), logo)),
    el("div", { class: "titulo-bloco" }, el("h2", {}, C.responsaveisTitulo)),
    el("p", { class: "nota" }, C.responsaveisNota),
    semNinguem, lista, el("div", {}, adicionar)));
  return () => clearTimeout(relogio);
}
