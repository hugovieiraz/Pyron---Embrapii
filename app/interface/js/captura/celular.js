// Captura › Celular: o celular como câmera ao vivo (só identificação das peças; a temperatura sai da barra
// de cores quando ela está no quadro). Desligado: uma linha e Ligar. Ligado: QR e endereço à esquerda e,
// à direita, o que o celular está vendo, com as peças marcadas. O vídeo chega por WebSocket, quadro a quadro.
import { TEXTOS as T } from "../../textos.js";
import { el, api, fmt, token } from "../base.js";
import { botao, avisar, ocupado, estadoVazio } from "../componentes.js";
import { ilustracao } from "../ilustracoes.js";
import { endereco } from "../rotas.js";
import { posicionarRotulos, chavesDasDeteccoes, corDaClasse } from "../rotulos.js";

const C = T.celular;
const INTERVALO_MS = 800;       // estado da conexão; o vídeo vem pelo WebSocket
const CABECALHO = 16;           // antes do JPEG: número do quadro, trecho do rastro e posição da câmera (x, y)
const DESLOCAMENTO_MAXIMO = 0.5; // a câmera andou mais que meia tela desde o quadro analisado: esconde as caixas

export async function montar(no) {
  let c = await api("/api/celular");
  let relogio = null;
  let esp = null;
  let classes = [];
  let capturas = 0;

  function desenhar() {
    fecharEspelho();
    clearInterval(relogio);
    if (!c.ligado) { desenharDesligado(); return; }
    desenharLigado();
    relogio = setInterval(atualizar, INTERVALO_MS);
  }

  function desenharDesligado() {
    const semModelo = c.modelo?.erro;
    const ligar = botao({ texto: C.ligar, icone: "celular", variante: "primario", desabilitado: Boolean(semModelo), onclick: () => ocupado(ligar, async () => {
      try { c = await api("/api/celular/ligar", { method: "POST" }); desenhar(); } catch (e) { avisar(e.message, { erro: true }); }
    }) });
    no.replaceChildren(el("div", { class: "celular-desligado" },
      ilustracao("celular", { rotulo: C.comoTitulo }),
      el("h2", {}, C.comoTitulo),
      el("p", {}, C.umaLinha),
      semModelo ? el("p", { class: "erro-dialogo" }, c.modelo.erro) : el("p", { class: "nota" }, C.modeloUsado(c.modelo?.nome || T.geral.semValor)),
      el("div", { class: "grupo-btn" }, ligar),
      el("p", { class: "nota" }, C.notaRede)));
  }

  function desenharLigado() {
    classes = c.modelo?.classes || [];
    capturas = c.capturas;
    const desligar = botao({ texto: C.desligar, icone: "x", onclick: () => ocupado(desligar, async () => {
      try { c = await api("/api/celular/desligar", { method: "POST" }); avisar(C.desligado); desenhar(); } catch (e) { avisar(e.message, { erro: true }); }
    }) });
    const copiar = botao({ texto: C.copiar, compacto: true, variante: "fantasma", onclick: async () => {
      try { await navigator.clipboard.writeText(c.url); avisar(C.copiado); } catch { avisar(C.copiarFalhou, { erro: true }); }
    } });
    no.replaceChildren(el("div", { class: "celular-grade" },
      el("section", { class: "celular-conectar", "aria-label": C.abraTitulo },
        el("h2", {}, C.abraTitulo),
        el("img", { class: "celular-qr", src: `/api/celular/qr.png?v=${encodeURIComponent(c.url)}`, alt: C.qrAlt, width: 240, height: 240 }),
        el("div", { class: "celular-link" }, el("code", { class: "mono corta", title: c.url }, c.url), copiar),
        el("p", { class: "nota" }, C.avisoCertificado),
        el("p", { class: "linha-estado-fonte", id: "celular-status", role: "status" }),
        el("div", { class: "grupo-btn" }, desligar)),
      el("section", { class: "celular-espelho", "aria-label": C.espelhoTitulo },
        el("div", { class: "titulo-bloco" }, el("h2", {}, C.espelhoTitulo), el("span", { class: "nota", id: "celular-ritmo" })),
        el("div", { class: "palco-espelho", id: "celular-palco" }, estadoVazio({ ilustracao: "celular", procurando: true, titulo: C.esperandoTitulo, texto: C.esperandoTexto, compacto: true })),
        el("div", { class: "celular-achados", id: "celular-achados" }))));
    abrirEspelho();
    atualizarEstado();
  }

  async function atualizar() {
    try {
      c = await api("/api/celular");
      if (!c.ligado) { desenhar(); return; }
      atualizarEstado();
    } catch { /* a faixa de conexão já avisa */ }
  }

  function atualizarEstado() {
    const u = c.ultimo;
    const status = no.querySelector("#celular-status");
    if (!status) return;
    status.className = `linha-estado-fonte${c.conectado ? " ligada" : ""}`;
    status.replaceChildren(el("i", { class: "ponto-estado", "aria-hidden": "true" }), el("b", {}, c.conectado ? C.conectado : u ? C.desconectado(fmt(u.ha_s, 0)) : C.esperando));
    const lugar = c.modelo?.onde || {};
    const barrado = lugar.onde === "cpu" && /4551|Controle de Aplicativo/.test(lugar.motivo || ""); // o SAC barrou a DLL da placa
    const onde = barrado ? C.ondeBarrado : { placa: C.ondePlaca, carregando: C.ondeCarregando, cpu: C.ondeCpu }[lugar.onde];
    const ritmo = [];
    if (u && c.conectado && u.quadros_por_s != null) ritmo.push(C.videoPc(fmt(u.quadros_por_s, 0)));
    if (u && c.conectado && u.analises_por_s != null) ritmo.push(C.ritmoPc(fmt(u.analises_por_s, 1), u.ms, onde));
    no.querySelector("#celular-ritmo").textContent = ritmo.join(", ");
    if (capturas !== c.capturas) { capturas = c.capturas; desenharAchados(); }
  }

  // ---------------------------------------------------------------- espelho (WebSocket com o próprio servidor)
  // Binário: um quadro (cabeçalho + JPEG); texto: o resultado de uma análise. Quadro que chega enquanto o
  // anterior decodifica substitui o que esperava: sempre o mais novo, sem fila.
  function abrirEspelho() {
    fecharEspelho();
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/celular/ws`);
    ws.binaryType = "arraybuffer";
    const meu = { ws, pendente: null, decodificando: false, posicao: null, resultado: null, lugares: new Map(), largura: 0, altura: 0 };
    esp = meu;
    ws.addEventListener("message", (ev) => {
      if (esp !== meu) return;
      if (typeof ev.data === "string") { meu.resultado = JSON.parse(ev.data); desenharResultado(); desenharAchados(); return; }
      meu.pendente = ev.data;
      if (!meu.decodificando) mostrarQuadros(meu);
    });
    ws.addEventListener("close", () => { if (esp === meu) setTimeout(() => { if (esp === meu) abrirEspelho(); }, INTERVALO_MS * 2); });
  }
  function fecharEspelho() {
    const antigo = esp;
    esp = null;
    antigo?.ws.close();
  }

  async function mostrarQuadros(meu) {
    meu.decodificando = true;
    try {
      while (meu.pendente && esp === meu) {
        const dados = meu.pendente;
        meu.pendente = null;
        if (dados.byteLength <= CABECALHO) continue;
        const cab = new DataView(dados, 0, CABECALHO);
        const x = cab.getFloat32(8, true), y = cab.getFloat32(12, true);
        let imagem;
        try { imagem = await createImageBitmap(new Blob([new Uint8Array(dados, CABECALHO)], { type: "image/jpeg" })); } catch { continue; }
        meu.posicao = Number.isFinite(x) && Number.isFinite(y) ? { x, y, trecho: cab.getUint32(4, true) } : null;
        desenharQuadro(imagem);
      }
    } finally {
      meu.decodificando = false;
    }
  }

  function desenharQuadro(imagem) {
    const palco = no.querySelector("#celular-palco");
    if (!palco) { imagem.close(); return; }
    let quadro = palco.querySelector(".celular-quadro");
    if (!quadro) {
      quadro = el("div", { class: "celular-quadro" }, el("canvas", { role: "img", "aria-label": C.espelhoAlt }), el("div", { class: "celular-caixas" }));
      palco.replaceChildren(quadro);
    }
    const tela = quadro.querySelector("canvas");
    const mudou = tela.width !== imagem.width || tela.height !== imagem.height;
    if (mudou) { tela.width = imagem.width; tela.height = imagem.height; }
    tela.getContext("2d").drawImage(imagem, 0, 0);
    imagem.close();
    if (mudou || esp.largura !== tela.clientWidth) desenharResultado(); else moverCaixas();
  }

  /** Quanto a câmera andou do quadro analisado ao quadro na tela (fração); null quando não dá para saber. */
  function deslocamento() {
    const r = esp?.resultado;
    if (!r || !r.posicao || !esp.posicao) return { x: 0, y: 0 };
    if (r.posicao.trecho !== esp.posicao.trecho) return null;
    const d = { x: esp.posicao.x - r.posicao.x, y: esp.posicao.y - r.posicao.y };
    return Math.hypot(d.x, d.y) > DESLOCAMENTO_MAXIMO ? null : d;
  }
  function moverCaixas() {
    const camada = no.querySelector(".celular-caixas");
    if (!camada) return;
    const d = deslocamento();
    camada.classList.toggle("sumido", !d);
    if (d) camada.style.transform = `translate3d(${(d.x * esp.largura).toFixed(1)}px, ${(d.y * esp.altura).toFixed(1)}px, 0)`;
  }

  const temperaturaPeca = (d) => C.temperatura(fmt(d.tmax, 1), d.tmax_acima);
  const textoPeca = (d) => (d.tmax != null ? C.comTemperatura(d.nome, temperaturaPeca(d)) : d.nome);

  function desenharResultado() {
    const quadro = no.querySelector(".celular-quadro");
    const r = esp?.resultado;
    if (!quadro || !r) return;
    const pct = (v) => `${v * 100}%`;
    const caixaEm = (b) => ({ left: pct(b[0]), top: pct(b[1]), width: pct(b[2] - b[0]), height: pct(b[3] - b[1]) });
    const rotulos = r.deteccoes.map((d) => el("span", { class: "celular-rotulo" }, el("i", { style: { background: corDaClasse(d.classe, classes) } }), textoPeca(d)));
    const barra = r.escala?.barra;
    quadro.querySelector(".celular-caixas").replaceChildren(
      ...(r.area ? [el("div", { class: "celular-area", style: caixaEm(r.area) })] : []),
      ...(barra ? [el("div", { class: "celular-barra", style: caixaEm(barra) })] : []),
      ...r.deteccoes.map((d) => el("div", { class: "celular-caixa", style: { ...caixaEm(d.caixa), "--cor": corDaClasse(d.classe, classes) } })),
      ...rotulos);
    const W = quadro.clientWidth, H = quadro.clientHeight;
    esp.largura = W;
    esp.altura = H;
    const m = parseFloat(token("e-1")) || 0;
    const chaves = chavesDasDeteccoes(r.deteccoes);
    const itens = r.deteccoes.map((d, i) => ({ chave: chaves[i], largura: rotulos[i].offsetWidth, altura: rotulos[i].offsetHeight,
      caixa: { x: d.caixa[0] * W, y: d.caixa[1] * H, w: (d.caixa[2] - d.caixa[0]) * W, h: (d.caixa[3] - d.caixa[1]) * H } }));
    posicionarRotulos(itens, { x0: m, y0: m, x1: W - m, y1: H - m }, esp.lugares, m)
      .forEach((p, i) => { rotulos[i].style.transform = `translate(${Math.round(p.x)}px, ${Math.round(p.y)}px)`; });
    moverCaixas();
  }

  /** Embaixo do vídeo: as peças do último quadro analisado, a barra lida e as capturas salvas. */
  function desenharAchados() {
    const lista = no.querySelector("#celular-achados");
    if (!lista) return;
    const r = esp?.resultado;
    const itens = [];
    if (r) {
      const ordenadas = [...r.deteccoes].sort((a, b) => a.caixa[1] - b.caixa[1]);
      if (ordenadas.length) itens.push(...ordenadas.map((d) => el("span", { class: "etiqueta-peca" }, el("i", { style: { background: corDaClasse(d.classe, classes) }, "aria-hidden": "true" }),
        d.tmax != null ? C.comTemperatura(C.rotulo(d.nome, Math.round(d.confianca * 100)), temperaturaPeca(d)) : C.rotulo(d.nome, Math.round(d.confianca * 100)))));
      else itens.push(el("span", { class: "nota" }, r.area ? C.nenhumNoQuadro : C.semTermograma));
      if (r.escala) itens.push(el("span", { class: "nota" }, r.escala.estado === "lida" ? C.escalaLida(fmt(r.escala.min, 1), fmt(r.escala.max, 1)) : C.escalaLendo));
    }
    if (capturas) itens.push(el("span", { class: "nota" }, C.capturas(capturas)), el("a", { class: "btn compacto", href: endereco("inspecoes") }, C.verInspecoes));
    lista.replaceChildren(...itens);
  }

  desenhar();
  return () => { clearInterval(relogio); fecharEspelho(); };
}
