// Service worker do Pyron no modo servidor (tablet e notebook com o aplicativo instalado).
// Registrado só no modo servidor (js/casca.js, ligarAplicativo), como /sw.js?v=<versão>: o nome do cache leva a
// versão, e uma versão nova do servidor troca o cache inteiro.
// Rede primeiro: a casca guardada (index, CSS, módulos, textos e ícones) só aparece quando a rede falha, para a
// tela abrir e a faixa "sem conexão" avisar. NUNCA guarda /api/* (dados, imagens das inspeções, laudos) nem PDF.
// Sem edição offline nesta versão.

const VERSAO = new URL(self.location.href).searchParams.get("v") || "0";
const PREFIXO = "pyron-casca-";
const CACHE = `${PREFIXO}${VERSAO}`;

// A casca: testes/test_pwa.py confere que todo módulo de app/interface/js está aqui.
const CASCA = [
  "/",
  "/manifest.webmanifest",
  "/tokens.css", "/base.css", "/componentes.css", "/telas.css",
  "/textos.js",
  "/js/analise/cabecalho.js", "/js/analise/contexto.js", "/js/analise/faixa.js", "/js/analise/painel.js", "/js/analise/palco.js",
  "/js/aplicativo.js", "/js/base.js", "/js/busca.js",
  "/js/captura/alertas.js", "/js/captura/celular.js", "/js/captura/medir.js", "/js/captura/pasta.js", "/js/captura/video.js",
  "/js/casca.js", "/js/componentes.js", "/js/conferir.js",
  "/js/configuracoes/aparencia.js", "/js/configuracoes/componentes.js", "/js/configuracoes/criterio.js",
  "/js/configuracoes/dados.js", "/js/configuracoes/empresa.js", "/js/configuracoes/sobre.js",
  "/js/grafico.js", "/js/icones.js", "/js/ilustracoes.js", "/js/importar.js", "/js/janela.js", "/js/laudo.js",
  "/js/modelos/avaliacao.js", "/js/modelos/emuso.js", "/js/modelos/medicao.js", "/js/modelos/treino.js",
  "/js/pendencia.js", "/js/rotas.js", "/js/rotulos.js", "/js/situacao.js", "/js/telaAbas.js",
  "/js/telas/analise.js", "/js/telas/captura.js", "/js/telas/configuracoes.js", "/js/telas/entrar.js",
  "/js/telas/equipamento.js", "/js/telas/equipamentos.js", "/js/telas/inspecoes.js", "/js/telas/modelos.js",
  "/js/telas/painel.js", "/js/telas/pendencias.js",
  "/marca/logo-cor.svg", "/marca/logo-escuro.svg",
  "/marca/icone-janela-32.png", "/marca/icone-janela-64.png", "/marca/icone-janela-256.png",
  "/marca/icone-app-180.png", "/marca/icone-app-192.png", "/marca/icone-app-512.png", "/marca/icone-app-mascara-512.png",
];
const NA_CASCA = new Set(CASCA);

/** O que nunca passa pelo cache: dados, laudos e o que não é da casca nova. */
function nuncaGuardar(url) {
  return url.pathname.startsWith("/api/") || url.pathname.startsWith("/antiga") || url.pathname.startsWith("/c/")
    || url.pathname.toLowerCase().endsWith(".pdf");
}

self.addEventListener("install", (ev) => {
  ev.waitUntil(caches.open(CACHE).then((c) => c.addAll(CASCA.map((u) => new Request(u, { cache: "reload" })))).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil(caches.keys()
    .then((nomes) => Promise.all(nomes.filter((n) => n.startsWith(PREFIXO) && n !== CACHE).map((n) => caches.delete(n))))
    .then(() => self.clients.claim()));
});

/** Rede primeiro; se a rede responder, a cópia da casca é renovada; se falhar, vale a cópia guardada. */
async function redePrimeiro(pedido, chave) {
  try {
    const resposta = await fetch(pedido);
    if (resposta.ok) {
      const copia = resposta.clone();
      caches.open(CACHE).then((c) => c.put(chave, copia));
    }
    return resposta;
  } catch (erro) {
    const guardada = await caches.match(chave, { cacheName: CACHE });
    if (guardada) return guardada;
    throw erro;
  }
}

self.addEventListener("fetch", (ev) => {
  const pedido = ev.request;
  if (pedido.method !== "GET") return;
  const url = new URL(pedido.url);
  if (url.origin !== self.location.origin || nuncaGuardar(url)) return;
  if (pedido.mode === "navigate") {
    ev.respondWith(redePrimeiro(pedido, "/"));
    return;
  }
  if (NA_CASCA.has(url.pathname)) ev.respondWith(redePrimeiro(pedido, url.pathname));
});
