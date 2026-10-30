// Configurações › Empresa e time: o cabeçalho do laudo (nome, subtítulo, logotipo) e o time operacional
// (engenheiros e técnicos; o laudo só sai com quem assina, a pendência aceita qualquer um). Salva sozinho;
// membro sem nome, ou que assina sem registro, ainda não vai para o servidor, que o recusaria enquanto a pessoa digita.
// Acesso ao servidor (0.9): usuário e administrador salvam sozinhos; a senha só vai pelo botão "Definir senha"
// (nunca no salvamento automático, que mandaria a senha pela metade) e nunca volta do servidor.
import { TEXTOS as T } from "../../textos.js";
import { el, api, json } from "../base.js";
import { botao, campo, marcar, avisar, confirmar } from "../componentes.js";

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

  // ---------------------------------------------------------------- time operacional
  const lista = el("div", { class: "lista-tecnicos" });
  const contagem = el("span", { class: "nota" });
  const valor = (l, k) => l.querySelector(`[data-campo=${k}]`);
  function linha(r = { id: novoId(), nome: "", perfil: "tecnico", funcao: "", registro: "", email: "", telefone: "", assina: false, alertas: null, usuario: "", administrador: false, tem_senha: false }) {
    const comCampo = (k, n) => { n.querySelector("input, select").dataset.campo = k; return n; };
    const padrao = el("label", { class: "padrao-tecnico", title: C.respPadraoDica },
      el("input", { type: "radio", name: "resp-padrao", value: r.id, checked: r.id === cfg.responsavel_padrao, disabled: !r.assina, "aria-label": C.respPadraoDe(r.nome || C.respNovo) }), C.respPadrao);
    padrao.querySelector("input").addEventListener("change", definirPadrao);
    const assina = marcar({ rotulo: C.respAssina, marcado: r.assina !== false, onchange: () => { padrao.querySelector("input").disabled = !assina.querySelector("input").checked; salvarDepois(0); } });
    assina.querySelector("input").dataset.campo = "assina";
    const tirar = botao({ texto: C.respTirar(r.nome || C.respNovo), icone: "lixo", variante: "fantasma", soIcone: true, onclick: () => { l.remove(); contar(); salvarDepois(0); } });
    const admin = marcar({ rotulo: C.respAdmin, marcado: Boolean(r.administrador), onchange: () => salvarDepois(0) });
    admin.querySelector("input").dataset.campo = "administrador";
    const senha = campo({ rotulo: C.respSenha, tipo: "password", autocomplete: "new-password", maxlength: "200", classe: "campo-senha" });
    const estadoSenha = el("p", { class: "nota estado-senha" }, r.tem_senha ? C.respSenhaComSenha : C.respSenhaSemSenha);
    const definir = botao({ texto: C.respDefinir, icone: "chave", compacto: true, "aria-label": C.respDefinirSenha(r.nome || C.respNovo), onclick: () => definirSenha(l, senha) });
    const l = el("div", { class: "linha-tecnico", dataset: { id: r.id } },
      comCampo("nome", campo({ rotulo: C.respNome, valor: r.nome, autocomplete: "off" })),
      comCampo("perfil", campo({ rotulo: C.respPerfil, opcoes: Object.entries(C.perfis).map(([valor, texto]) => ({ valor, texto })), valor: r.perfil || "tecnico" })),
      comCampo("funcao", campo({ rotulo: C.respFuncao, valor: r.funcao || "", marcador: C.respFuncaoMarcador, autocomplete: "off" })),
      tirar,
      comCampo("registro", campo({ rotulo: C.respRegistro, valor: r.registro, marcador: C.respRegistroMarcador, autocomplete: "off" })),
      comCampo("email", campo({ rotulo: C.respEmail, tipo: "email", valor: r.email || "", marcador: C.respEmailMarcador, autocomplete: "off" })),
      comCampo("telefone", campo({ rotulo: C.respTelefone, tipo: "tel", valor: r.telefone || "", marcador: C.respTelefoneMarcador, autocomplete: "off" })),
      el("div", { class: "marcas-tecnico" }, assina, padrao,
        comCampo("alertas", campo({ rotulo: C.respAlertas, opcoes: Object.entries(C.alertaOpcoes).map(([valor, texto]) => ({ valor, texto })), valor: r.alertas || "", classe: "campo-alertas" }))),
      el("div", { class: "marcas-tecnico acesso-tecnico" },
        comCampo("usuario", campo({ rotulo: C.respUsuario, valor: r.usuario || "", marcador: C.respUsuarioMarcador, autocomplete: "off", autocapitalize: "none", spellcheck: "false", maxlength: "32" })),
        senha, definir, admin),
      estadoSenha);
    return l;
  }
  function contar() {
    const perfis = [...lista.querySelectorAll("[data-campo=perfil]")].map((s) => s.value);
    contagem.textContent = C.respContagem(perfis.filter((p) => p === "engenheiro").length, perfis.filter((p) => p === "tecnico").length);
    semNinguem.hidden = perfis.length > 0;
    const cheio = perfis.length >= (cfg.limite_time || 20);
    adicionar.disabled = cheio;
    adicionar.title = cheio ? C.respLimite(cfg.limite_time || 20) : "";
  }
  lista.append(...cfg.responsaveis.map((r) => linha(r)));
  const semNinguem = el("p", { class: "nota" }, C.semResponsaveis);
  const adicionar = botao({ texto: C.respAdicionar, icone: "adicionar", compacto: true, onclick: () => { const l = linha(); lista.append(l); contar(); valor(l, "nome").focus(); } });
  contar();

  async function definirSenha(l, campoSenha) {
    const entrada = campoSenha.querySelector("input");
    const mostrar = (texto, foco) => { erro.textContent = texto; erro.hidden = false; foco.focus(); };
    if (!valor(l, "usuario").value.trim()) return mostrar(C.respSenhaUsuario, valor(l, "usuario"));
    if (entrada.value.length < 10) return mostrar(C.respSenhaFalta, entrada);
    clearTimeout(relogio);
    const corpo = lerResponsaveis().map((r) => (r.id === l.dataset.id ? { ...r, senha: entrada.value } : r));
    if (await salvar({ responsaveis: corpo })) {
      entrada.value = "";
      avisar(C.respSenhaDefinida(valor(l, "nome").value.trim()));
    }
  }

  // usuário pela metade (menos de 3 letras, caractere inválido) não vai: segue o já guardado até ficar válido
  const usuarioDe = (l) => {
    const u = valor(l, "usuario").value.trim().toLowerCase();
    return !u || /^[a-z0-9][a-z0-9._-]{2,31}$/.test(u) ? u : cfg.responsaveis.find((x) => x.id === l.dataset.id)?.usuario || "";
  };
  // só vai quem o servidor aceita: com nome, com registro se assina e com e-mail válido (ou vazio)
  const lerResponsaveis = () => [...lista.querySelectorAll(".linha-tecnico")]
    .filter((l) => valor(l, "email").checkValidity())
    .map((l) => ({ id: l.dataset.id, assina: valor(l, "assina").checked,
      ...Object.fromEntries(["nome", "perfil", "funcao", "registro", "email", "telefone"].map((k) => [k, valor(l, k).value.trim()])),
      alertas: valor(l, "alertas").value || null,
      usuario: usuarioDe(l), administrador: valor(l, "administrador").checked }))
    .filter((r) => r.nome && (!r.assina || r.registro));

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
        const nomeLinha = valor(l, "nome").value.trim();
        const r = guardados.find((x) => x.id === l.dataset.id) || guardados.find((x) => x.nome === nomeLinha);
        if (r) {
          l.dataset.id = r.id; l.querySelector("input[type=radio]").value = r.id; l.querySelector("input[type=radio]").checked = r.id === cfg.responsavel_padrao;
          l.querySelector(".estado-senha").textContent = r.tem_senha ? C.respSenhaComSenha : C.respSenhaSemSenha;
        }
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
  no.addEventListener("input", (ev) => { if (ev.target.matches("input:not([type=radio]):not([type=file]):not([type=checkbox]):not([type=password])")) salvarDepois(); });
  no.addEventListener("change", (ev) => { if (ev.target.matches("select")) { contar(); salvarDepois(0); } });

  no.append(el("div", { class: "coluna-form coluna-config" },
    el("div", { class: "titulo-bloco" }, el("h2", {}, C.empresaTitulo), salvo),
    erro,
    el("div", { class: "grupo-campos" }, el("div", { class: "grade-campos-2" }, nome, sub), el("div", { class: "campo" }, el("span", { class: "rotulo" }, C.logo), logo)),
    el("div", { class: "titulo-bloco" }, el("h2", {}, C.responsaveisTitulo), contagem),
    el("p", { class: "nota" }, C.responsaveisNota),
    el("p", { class: "nota" }, C.acessoNota),
    semNinguem, lista, el("div", {}, adicionar)));
  return () => clearTimeout(relogio);
}
