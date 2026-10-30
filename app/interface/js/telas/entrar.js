// Entrada no modo servidor (app/acesso.py): usuário e senha. Não está no mapa de rotas: a casca mostra esta
// tela antes de qualquer outra quando o servidor pede login, e de novo quando a sessão termina no meio do uso.
// Estados: pronto, entrando (botão ocupado), erro do servidor (senha, bloqueio) e sem conexão.
import { TEXTOS as T } from "../../textos.js";
import { el, api, json } from "../base.js";
import { botao, campo } from "../componentes.js";

const E = T.entrar;

/** montar(pagina, { aviso, aoEntrar(eu) }): ``aviso`` aparece no lugar do erro (ex.: sessão terminou). */
export function montar(pagina, { aviso = null, aoEntrar }) {
  const usuario = campo({ rotulo: E.usuario, autocomplete: "username", autocapitalize: "none", spellcheck: "false", maxlength: "32", required: true });
  const senha = campo({ rotulo: E.senha, tipo: "password", autocomplete: "current-password", maxlength: "200", required: true });
  const mensagem = el("p", { class: aviso ? "nota-entrar" : "erro-dialogo", role: aviso ? "status" : "alert", hidden: !aviso }, aviso || "");
  const enviar = botao({ texto: E.entrar, variante: "primario", tipo: "submit" });
  const campoUsuario = usuario.querySelector("input");
  const campoSenha = senha.querySelector("input");

  function mostrarErro(texto) {
    mensagem.className = "erro-dialogo";
    mensagem.setAttribute("role", "alert");
    mensagem.textContent = texto;
    mensagem.hidden = false;
  }

  async function entrar(ev) {
    ev.preventDefault();
    if (enviar.getAttribute("aria-busy") === "true") return;
    const corpo = { usuario: campoUsuario.value.trim(), senha: campoSenha.value };
    if (!corpo.usuario || !corpo.senha) { mostrarErro(E.preencha); (corpo.usuario ? campoSenha : campoUsuario).focus(); return; }
    enviar.setAttribute("aria-busy", "true");
    enviar.disabled = true;
    enviar.querySelector("span").textContent = E.entrando;
    try {
      const eu = await api("/api/acesso/entrar", json("POST", corpo));
      aoEntrar(eu);
    } catch (erro) {
      mostrarErro(erro.message === T.geral.semResposta ? E.semConexao : erro.message);
      campoSenha.value = "";
      campoSenha.focus();
    } finally {
      enviar.removeAttribute("aria-busy");
      enviar.disabled = false;
      enviar.querySelector("span").textContent = E.entrar;
    }
  }

  const form = el("form", { class: "form-entrar", novalidate: true, onsubmit: entrar }, usuario, senha, mensagem, enviar);
  pagina.append(el("section", { class: "tela-entrar", "aria-labelledby": "titulo-entrar" },
    el("div", { class: "cartao-entrar" },
      el("div", { class: "marca-entrar" },
        el("img", { class: "logo-claro", src: "/marca/logo-cor.svg", alt: "", width: "120", height: "40" }),
        el("img", { class: "logo-escuro", src: "/marca/logo-escuro.svg", alt: "", width: "120", height: "40" })),
      el("h1", { id: "titulo-entrar" }, E.titulo),
      el("p", { class: "nota" }, E.servidor),
      form,
      el("p", { class: "nota" }, E.esqueceu))));
  setTimeout(() => campoUsuario.focus());
}
