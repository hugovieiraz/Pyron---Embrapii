// Aplicativo instalado (PWA) no modo servidor: manifest, ícone do iPad e service worker (/sw.js).
// No modo local nada disto entra: o Pyron.exe e a janela do Edge seguem como antes.
import { TEXTOS as T } from "../textos.js";
import { el, VERSAO_INTERFACE, modoServidor } from "./base.js";
import { avisar } from "./componentes.js";

/** Manifest e metas do iPad no <head> e o service worker com a versão no endereço (o cache leva a versão). */
export function ligarAplicativo() {
  if (document.querySelector('link[rel="manifest"]')) return;
  document.head.append(
    el("link", { rel: "manifest", href: "/manifest.webmanifest" }),
    el("link", { rel: "apple-touch-icon", href: "/marca/icone-app-180.png" }),
    el("meta", { name: "apple-mobile-web-app-capable", content: "yes" }),
    el("meta", { name: "mobile-web-app-capable", content: "yes" }),
    el("meta", { name: "apple-mobile-web-app-title", content: "Pyron" }),
    el("meta", { name: "apple-mobile-web-app-status-bar-style", content: "default" }));
  // service worker só em conexão segura (HTTPS ou o próprio computador); sem ele o Pyron funciona igual
  if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
  navigator.serviceWorker.register(`/sw.js?v=${encodeURIComponent(VERSAO_INTERFACE)}`, { scope: "/" }).catch(() => {});
}

let avisado = false;
/** O servidor está em outra versão que esta tela (atualizado com o tablet aberto): avisa e recarrega. */
export function versaoMudou(versaoServidor) {
  if (!modoServidor() || !versaoServidor || versaoServidor === VERSAO_INTERFACE || avisado) return;
  avisado = true;
  avisar(T.casca.versaoNova(versaoServidor));
  setTimeout(async () => {
    try { await (await navigator.serviceWorker?.getRegistration())?.update(); } catch { /* recarrega assim mesmo */ }
    location.reload();
  }, 4000);
}
