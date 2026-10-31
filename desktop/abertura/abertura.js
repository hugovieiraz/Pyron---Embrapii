// Abertura do Pyron desktop: "Abrindo o Pyron…" enquanto o servidor sobe, ou o erro com "Reiniciar".
// O main.rs traz o erro na URL (?erro=código&detalhe=…&registro=…); o texto vem de textos.js (T.desktop).
import { TEXTOS as T } from "./gerado/textos.js";
import { instalarIcones } from "./gerado/icones.js";

const D = T.desktop;
const J = T.casca.janela;
const params = new URLSearchParams(location.search);
const erro = params.get("erro");
const tauri = window.__TAURI__;
const janela = tauri.window.getCurrentWindow();
const $ = (id) => document.getElementById(id);

instalarIcones();

// sem a barra do Windows: o topo arrasta e os botões minimizam e fecham, como na interface
const botao = (ic, rotulo, acao, classe = "") => {
  const b = document.createElement("button");
  b.type = "button";
  b.className = classe;
  b.title = rotulo;
  b.setAttribute("aria-label", rotulo);
  b.innerHTML = `<svg class="ic p" aria-hidden="true"><use href="#i-${ic}"/></svg>`;
  b.addEventListener("click", acao);
  return b;
};
$("controles").setAttribute("aria-label", J.grupo);
$("controles").append(botao("minimizar", J.minimizar, () => janela.minimize()), botao("x", J.fechar, () => janela.close(), "fechar"));
$("topo").addEventListener("mousedown", (ev) => { if (ev.button === 0 && !ev.target.closest("button")) janela.startDragging(); });

if (!erro) {
  $("texto").textContent = D.abrindo;
} else {
  $("giro").hidden = true;
  $("texto").textContent = D.erros[erro] || D.erros.iniciar;
  const detalhe = params.get("detalhe");
  if (detalhe) { $("detalhe").textContent = detalhe; $("detalhe").hidden = false; }
  const registro = params.get("registro");
  if (registro && ["parou", "demorou", "iniciar"].includes(erro)) { $("registro").textContent = D.registro(registro); $("registro").hidden = false; }
  const reiniciar = $("reiniciar");
  reiniciar.textContent = erro === "endereco" ? D.tentarDeNovo : D.reiniciar;
  reiniciar.hidden = false;
  reiniciar.addEventListener("click", () => {
    reiniciar.setAttribute("aria-busy", "true");
    tauri.core.invoke("reiniciar");
  });
  reiniciar.focus();
}
