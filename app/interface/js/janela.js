// Quem hospeda a janela própria do Pyron: o Pyron desktop (Tauri v2, desktop/), o Pyron.exe (WebView2, lancador/)
// ou ninguém (navegador, janela do Edge, tablet). Os dois hospedeiros recebem os mesmos pedidos (minimizar,
// maximizar, fechar) e devolvem o mesmo estado (maximizada ou não); casca.js desenha os botões.
// Sem DOM aqui: testes/js/janela.test.mjs roda este módulo no Node com hospedeiros falsos.

/** O hospedeiro desta página, ou null fora de uma janela própria. */
export function hospedeiroJanela(w = globalThis) {
  const tauri = w.__TAURI__;
  if (tauri && tauri.window && tauri.window.getCurrentWindow) return janelaTauri(tauri);
  const webview = w.chrome && w.chrome.webview;
  if (webview) return janelaWebView2(webview);
  return null;
}

// Pyron desktop: API de janela do Tauri. Só funciona para a origem do servidor configurado (capability criada pelo
// desktop/src-tauri ao abrir); fora dela, cada pedido é recusado pelo próprio Tauri.
function janelaTauri(tauri) {
  const janela = tauri.window.getCurrentWindow();
  return {
    nome: "tauri",
    pedir(acao) {
      if (acao === "minimizar") return janela.minimize();
      if (acao === "maximizar") return janela.toggleMaximize();
      if (acao === "fechar") return janela.close();
      return undefined;
    },
    /** fn(maximizada) agora e a cada mudança de tamanho. */
    aoMudar(fn) {
      const avisar = async () => { try { fn(await janela.isMaximized()); } catch { /* janela fechando */ } };
      janela.onResized(avisar);
      avisar();
    },
    // o WebView2 do Tauri não liga o app-region do CSS: o topo pede o arraste à janela
    arrastar: () => janela.startDragging(),
    notificar: (titulo, texto) => tauri.core.invoke("plugin:notification|notify", { options: { title: titulo, body: texto } }),
    ouvir: (evento, fn) => tauri.event.listen(evento, (ev) => fn(ev.payload)),
    contar: (evento, dado) => tauri.event.emit(evento, dado),
  };
}

// Pyron.exe: mensagens "janela:..." pelo WebView2 (lancador/Janela.cs), que já arrasta pelo app-region do CSS.
function janelaWebView2(webview) {
  return {
    nome: "webview2",
    pedir: (acao) => webview.postMessage(`janela:${acao}`),
    aoMudar(fn) {
      webview.addEventListener("message", (ev) => {
        if (ev.data === "janela:maximizada" || ev.data === "janela:normal") fn(ev.data === "janela:maximizada");
      });
      webview.postMessage("janela:estado");
    },
    arrastar: null,
    notificar: null,
    ouvir: null,
    contar: null,
  };
}

/** O clique no topo arrasta a janela? Não quando cai num controle, como no app-region: no-drag do CSS. */
export const arrastaJanela = (alvo) => !alvo.closest("a, button, input, select, textarea, label, [role], [tabindex]");

/** Alertas que chegaram desde a última contagem. Na primeira (antes = null) nada é novo: abrir o Pyron não avisa os antigos. */
export const alertasNovos = (antes, agora) => (antes == null ? 0 : Math.max(0, agora - antes));
