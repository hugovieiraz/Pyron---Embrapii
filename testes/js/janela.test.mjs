// Adaptador da janela própria (app/interface/js/janela.js) com hospedeiros falsos. Roda por testes/test_janela.py
// (node --test); sem dependências.
import { test } from "node:test";
import assert from "node:assert/strict";
import { hospedeiroJanela, arrastaJanela, alertasNovos } from "../../app/interface/js/janela.js";

function tauriFalso({ maximizada = false } = {}) {
  const chamadas = [];
  let aoRedimensionar = null;
  const janela = {
    minimize: async () => chamadas.push("minimize"),
    toggleMaximize: async () => { maximizada = !maximizada; chamadas.push("toggleMaximize"); aoRedimensionar?.(); },
    close: async () => chamadas.push("close"),
    isMaximized: async () => maximizada,
    onResized: (fn) => { aoRedimensionar = fn; },
    startDragging: async () => chamadas.push("startDragging"),
  };
  const ouvintes = {};
  const tauri = {
    window: { getCurrentWindow: () => janela },
    core: { invoke: async (cmd, args) => chamadas.push([cmd, args]) },
    event: {
      listen: async (nome, fn) => { ouvintes[nome] = fn; },
      emit: async (nome, dado) => chamadas.push(["emit", nome, dado]),
    },
  };
  return { w: { __TAURI__: tauri }, chamadas, ouvintes };
}

function webview2Falso({ maximizada = false } = {}) {
  const enviadas = [];
  let ouvinte = null;
  const webview = {
    postMessage: (m) => {
      enviadas.push(m);
      if (m === "janela:estado") ouvinte?.({ data: maximizada ? "janela:maximizada" : "janela:normal" });
    },
    addEventListener: (_tipo, fn) => { ouvinte = fn; },
  };
  return { w: { chrome: { webview } }, enviadas, receber: (data) => ouvinte?.({ data }) };
}

const esperar = () => new Promise((r) => setTimeout(r, 0));

test("navegador comum: sem hospedeiro, nada muda", () => {
  assert.equal(hospedeiroJanela({}), null);
  assert.equal(hospedeiroJanela({ chrome: {} }), null);
  assert.equal(hospedeiroJanela({ __TAURI__: {} }), null); // Tauri sem a API de janela (global desligado)
});

test("Tauri: os três botões viram a API de janela", async () => {
  const { w, chamadas } = tauriFalso();
  const h = hospedeiroJanela(w);
  assert.equal(h.nome, "tauri");
  await h.pedir("minimizar");
  await h.pedir("maximizar");
  await h.pedir("fechar");
  assert.equal(h.pedir("outra"), undefined);
  assert.deepEqual(chamadas, ["minimize", "toggleMaximize", "close"]);
});

test("Tauri: estado maximizado agora e a cada mudança de tamanho", async () => {
  const { w } = tauriFalso({ maximizada: true });
  const h = hospedeiroJanela(w);
  const estados = [];
  h.aoMudar((max) => estados.push(max));
  await esperar();
  await h.pedir("maximizar");
  await esperar();
  assert.deepEqual(estados, [true, false]);
});

test("Tauri: arraste, aviso do Windows e eventos da bandeja", async () => {
  const { w, chamadas, ouvintes } = tauriFalso();
  const h = hospedeiroJanela(w);
  await h.arrastar();
  await h.notificar("2 alertas novos", "Abra o Pyron");
  await h.contar("pyron:monitoramento", true);
  const recebidos = [];
  await h.ouvir("bandeja:monitoramento", (dado) => recebidos.push(dado));
  ouvintes["bandeja:monitoramento"]({ payload: null });
  assert.deepEqual(chamadas, [
    "startDragging",
    ["plugin:notification|notify", { options: { title: "2 alertas novos", body: "Abra o Pyron" } }],
    ["emit", "pyron:monitoramento", true],
  ]);
  assert.deepEqual(recebidos, [null]);
});

test("Pyron.exe (WebView2): as mesmas mensagens janela:... de antes", () => {
  const { w, enviadas, receber } = webview2Falso({ maximizada: true });
  const h = hospedeiroJanela(w);
  assert.equal(h.nome, "webview2");
  const estados = [];
  h.aoMudar((max) => estados.push(max));
  h.pedir("minimizar");
  h.pedir("maximizar");
  h.pedir("fechar");
  receber("janela:normal");
  receber("outra coisa");
  assert.deepEqual(enviadas, ["janela:estado", "janela:minimizar", "janela:maximizar", "janela:fechar"]);
  assert.deepEqual(estados, [true, false]);
  // o Pyron.exe arrasta pelo app-region do CSS e não tem bandeja nem aviso
  assert.equal(h.arrastar, null);
  assert.equal(h.notificar, null);
  assert.equal(h.ouvir, null);
});

test("Tauri tem prioridade quando os dois aparecem", () => {
  const { w } = tauriFalso();
  w.chrome = webview2Falso().w.chrome; // o WebView2 do Tauri também expõe chrome.webview
  assert.equal(hospedeiroJanela(w).nome, "tauri");
});

test("arraste só fora dos controles", () => {
  const alvo = (controle) => ({ closest: (seletor) => (controle && seletor.includes(controle) ? {} : null) });
  assert.equal(arrastaJanela(alvo(null)), true);
  for (const c of ["a", "button", "input", "select", "[tabindex]", "[role]"]) assert.equal(arrastaJanela(alvo(c)), false, c);
});

test("alertas novos: a primeira contagem não avisa, depois só o que subiu", () => {
  assert.equal(alertasNovos(null, 5), 0);
  assert.equal(alertasNovos(5, 7), 2);
  assert.equal(alertasNovos(7, 3), 0);
  assert.equal(alertasNovos(0, 1), 1);
});
