// Catálogo dos componentes da interface nova: cada um em todos os estados, nos dois temas.
// Endereço: /nova/catalogo.html (?tema=escuro, ?toque simula tela de toque, ?conferir grava o resultado no <body>).
import { TEXTOS as T } from "../textos.js";
import { $, el, icone, temperatura, token } from "./base.js";
import {
  botao, campo, marcar, segmentado, abas, painelAba, cabecalho, selo, indicador, tabela,
  esqueleto, estadoVazio, estadoErro, avisar, dialogo, confirmar, menu, contador,
  barraFerramentas, secao as secaoRecolhivel, painelDetalhe,
} from "./componentes.js";
import { instalarIcones, NOMES_ICONES } from "./icones.js";
import { ilustracao, NOMES_ILUSTRACOES } from "./ilustracoes.js";
import { conferir, razao } from "./conferir.js";

const C = T.catalogo;
const params = new URLSearchParams(location.search);
if (params.get("tema") === "escuro") document.documentElement.dataset.tema = "escuro";
if (params.has("toque")) document.documentElement.style.setProperty("--alvo-compacto", "var(--alvo)");

// dados de demonstração do catálogo (fictícios)
const AMOSTRA = [
  { id: "a1", equipamento: "TR-01 69/13,8 kV", instalacao: "SE Campina Grande II", regiao: "Conexão X1", tmax: 96.4, criterio: "108 % da MTA", sev: "imediato", prazo: "13/10/2026", vencida: true },
  { id: "a2", equipamento: "Chave seccionadora CS-12", instalacao: "SE Bodocongó", regiao: "Contato fase B", tmax: 81.2, criterio: "ΔT 31,0 °C", sev: "urgente", prazo: "07/11/2026", vencida: false },
  { id: "a3", equipamento: "Disjuntor DJ-52", instalacao: "SE Campina Grande II", regiao: "Terminal superior", tmax: 67.5, criterio: "75 % da MTA", sev: "programar", prazo: "01/12/2026", vencida: false },
  { id: "a4", equipamento: "TP-03 69 kV", instalacao: "SE Bodocongó", regiao: "Bucha H1", tmax: 41.3, criterio: "ΔT 5,8 °C", sev: "atencao", prazo: "24/12/2026", vencida: false },
  { id: "a5", equipamento: "Para-raios PR-07", instalacao: "SE Mirante", regiao: "Corpo", tmax: 33.0, criterio: "ΔT 0,4 °C", sev: "normal", prazo: "—", vencida: false },
];

const secoes = [];
const secao = (id, titulo, ...filhos) => { secoes.push([id, titulo]); return el("section", { id, "aria-labelledby": `t-${id}` }, el("h2", { id: `t-${id}` }, titulo), ...filhos); };
const exemplo = (titulo, ...filhos) => el("div", { class: "exemplo" }, el("h3", {}, titulo), ...filhos);
const linha = (...filhos) => el("div", { class: "linha-ex" }, ...filhos);

function amostraCor(nome, sobreNome = null) {
  const valor = token(nome);
  const info = [el("code", {}, `--${nome}`), el("span", {}, valor)];
  if (sobreNome) {
    const cor = document.createElement("span");
    cor.style.color = `var(--${nome})`;
    cor.style.background = `var(--${sobreNome})`;
    document.body.append(cor);
    const [frente, fundo] = [getComputedStyle(cor).color, getComputedStyle(cor).backgroundColor].map((s) => s.match(/\d+(\.\d+)?/g).slice(0, 3).map(Number));
    cor.remove();
    info.push(el("span", {}, C.contraste(razao(frente, fundo).toFixed(1).replace(".", ","), sobreNome)));
  }
  return el("div", { class: "amostra" }, el("div", { class: "cor", style: { background: `var(--${nome})` } }), el("div", { class: "info" }, info));
}

function montar() {
  const raiz = $("#catalogo");
  const tema = segmentado({
    rotulo: C.tema, valor: document.documentElement.dataset.tema,
    opcoes: [{ valor: "claro", texto: C.claro }, { valor: "escuro", texto: C.escuro }],
    aoMudar: (v) => { document.documentElement.dataset.tema = v; },
  });
  const btnConferir = botao({ texto: C.conferir, icone: "check", variante: "primario", onclick: () => mostrarConferencia() });
  $("#controles").append(tema, btnConferir);

  raiz.append(
    cabecalho({ titulo: T.telas.catalogo, meta: [el("span", {}, C.sub)] }),

    secao("cores", C.cores,
      exemplo(C.acao, el("div", { class: "amostras" }, ["cobalto-50", "cobalto-100", "cobalto-200", "cobalto-300", "cobalto-400", "cobalto-500", "cobalto-600", "cobalto-700", "cobalto-800", "cobalto-900"].map((n) => amostraCor(n)))),
      exemplo(C.neutros, el("div", { class: "amostras" }, ["branco", "n-100", "n-200", "n-300", "n-400", "n-500", "n-600", "n-700", "n-800", "n-900"].map((n) => amostraCor(n)))),
      exemplo(C.papeis, el("div", { class: "amostras" }, [["texto", "superficie"], ["texto-2", "superficie"], ["texto-3", "superficie"], ["texto-3", "superficie-2"], ["acao", "superficie"], ["acao-texto", "acao"], ["foco", "superficie"], ["borda-campo", "superficie"]].map(([n, s]) => amostraCor(n, s)))),
      exemplo(C.severidade, el("div", { class: "amostras" }, ["normal", "atencao", "programar", "urgente", "imediato"].flatMap((n) => [amostraCor(n, "superficie"), amostraCor(`${n}-texto`, `${n}-fundo`)]))),
      exemplo(C.palco, el("div", { class: "palco-ex" }, el("span", {}, C.palcoTexto), el("span", { class: "apagado" }, C.palcoTexto2), el("span", { class: "etiqueta-imagem" }, `Conexão X1 ${temperatura(96.4)}`)),
        el("div", { class: "amostras" }, [["palco-texto", "palco"], ["palco-texto-2", "palco"]].map(([n, s]) => amostraCor(n, s))))),

    secao("tipografia", C.tipografia,
      el("div", { class: "tipos" }, [6, 5, 4, 3, 2, 1].map((i) => el("div", { class: "tipo" },
        el("code", {}, `--t-${i}: ${token(`t-${i}`)} / ${token(`a-${i}`)}`),
        el("span", { style: { fontSize: `var(--t-${i})`, lineHeight: `var(--a-${i})`, fontWeight: i >= 4 ? "var(--p-forte)" : "var(--p-normal)" } }, C.usoTipo[i])))),
      exemplo(C.numeros, linha(el("span", { class: "num", style: { fontSize: "var(--t-5)", fontWeight: "var(--p-forte)" } }, temperatura(96.4)), el("span", { class: "mono" }, "C:\\Termografia\\Entrada")))),

    secao("medidas", C.medidas,
      exemplo(C.espacamento, el("div", { class: "escala-esp" }, ["1", "2", "3", "4", "5", "6", "8", "10", "12", "16"].map((n) => el("div", {}, el("i", { style: { width: `var(--e-${n})`, height: `var(--e-${n})` } }), `e-${n}`)))),
      exemplo(C.raios, linha(["r-p", "r-m", "r-g", "r-pilula"].map((r) => el("div", { class: "caixa-sombra", style: { borderRadius: `var(--${r})`, border: "1px solid var(--borda-forte)" } }, r)))),
      exemplo(C.sombras, linha(["sombra-1", "sombra-2", "sombra-3"].map((s) => el("div", { class: "caixa-sombra", style: { boxShadow: `var(--${s})` } }, s))))),

    secao("botoes", C.botoes,
      exemplo(C.variantes, linha(
        botao({ texto: C.gerarLaudo, icone: "laudo", variante: "primario" }),
        botao({ texto: C.detectarDeNovo, icone: "detectar" }),
        botao({ texto: C.cancelar, variante: "fantasma" }),
        botao({ texto: C.apagar, icone: "lixo", variante: "perigo" }),
        botao({ texto: C.mais, icone: "mais-opcoes", soIcone: true }),
        botao({ texto: C.importar, icone: "importar", atalho: "Ctrl O" }))),
      exemplo(C.estadosBotao, linha(
        botao({ texto: C.gerarLaudo, icone: "laudo", variante: "primario", "aria-busy": "true" }),
        botao({ texto: C.salvar, variante: "primario", desabilitado: true }),
        botao({ texto: C.detectarDeNovo, desabilitado: true }),
        botao({ texto: C.alertas, icone: "sino", variante: "fantasma", soIcone: true, contador: 3 }))),
      exemplo(C.compactos, linha(
        botao({ texto: C.editar, icone: "editar", compacto: true }),
        botao({ texto: C.editar, icone: "editar", compacto: true, soIcone: true }),
        botao({ texto: C.apagar, icone: "lixo", compacto: true, soIcone: true, variante: "fantasma" })))),

    secao("campos", C.campos,
      el("div", { class: "grade-campos" },
        campo({ rotulo: C.instalacao, marcador: "SE Campina Grande II", autocomplete: "off" }),
        campo({ rotulo: C.ambiente, tipo: "number", unidade: "°C", valor: "31,0" }),
        campo({ rotulo: C.emissividade, tipo: "number", valor: "0,95", ajuda: C.emissividadeAjuda }),
        campo({ rotulo: C.carga, tipo: "number", unidade: "%", valor: "250", erro: C.cargaErro }),
        campo({ rotulo: C.material, opcoes: C.materiais }),
        campo({ rotulo: C.responsavel, opcoes: C.responsaveis, disabled: true }),
        campo({ rotulo: C.observacoes, area: true, marcador: C.observacoesMarcador }),
        el("div", { class: "campo" }, el("span", { class: "rotulo" }, C.opcoes), marcar({ rotulo: C.incluirFoto, marcado: true }), marcar({ rotulo: C.incluirOriginal })))),

    secao("selecao", C.selecao,
      exemplo(C.segmentadoT, segmentado({ rotulo: C.filtro, valor: "todas", opcoes: [{ valor: "todas", texto: C.todas, qtd: 42 }, { valor: "criticas", texto: C.criticas, qtd: 2 }, { valor: "programar", texto: C.programar, qtd: 4 }, { valor: "atencao", texto: C.atencao, qtd: 7 }] })),
      (() => {
        const corpo = el("div", {});
        const nomes = { regioes: C.regioes, condicoes: C.condicoes, identificacao: C.identificacao };
        const mostrar = (id) => corpo.replaceChildren(painelAba(id, el("p", { style: { paddingTop: "var(--e-4)" } }, C.conteudoAba(nomes[id]))));
        const a = abas({ rotulo: C.abasT, ativa: "regioes", itens: [{ id: "regioes", texto: C.regioes, qtd: 7 }, { id: "condicoes", texto: C.condicoes }, { id: "identificacao", texto: C.identificacao }], aoMudar: mostrar });
        mostrar("regioes");
        return exemplo(C.abasT, a, corpo);
      })(),
      exemplo(C.menuT, linha(
        (() => { const b = botao({ texto: C.detectarDeNovo, icone: "detectar" }); menu(b, [{ grupo: C.modelo }, { texto: "Para-raios (RF-DETR)", marcado: true, executar: () => avisar(C.escolhido) }, { texto: C.pontosQuentes, marcado: false, executar: () => avisar(C.escolhido) }, { separador: true }, { texto: C.identificarComponentes, icone: "detectar", executar: () => avisar(C.escolhido) }]); return b; })(),
        (() => { const b = botao({ texto: C.mais, icone: "mais-opcoes", soIcone: true }); menu(b, [{ texto: C.exportarImagem, icone: "baixar", executar: () => avisar(C.escolhido) }, { texto: C.exportarCsv, icone: "baixar", executar: () => avisar(C.escolhido) }, { separador: true }, { texto: C.apagar, icone: "lixo", perigo: true, executar: () => avisar(C.escolhido) }, { texto: C.indisponivel, desabilitado: true }]); return b; })()),
        el("div", { class: "menu menu-estatico ignorar-conferencia", role: "presentation" },
          el("div", { class: "grupo-menu" }, C.modelo),
          el("button", { type: "button", role: "menuitemradio", "aria-checked": "true", tabindex: "-1" }, el("span", {}, "Para-raios (RF-DETR)"), icone("check", "ic p marca")),
          el("button", { type: "button", role: "menuitemradio", "aria-checked": "false", tabindex: "-1" }, el("span", {}, C.pontosQuentes), icone("check", "ic p marca"))))),

    secao("estrutura", C.estrutura,
      exemplo(C.cabecalhoT, el("div", { class: "cartao" }, el("div", { class: "corpo" },
        cabecalho({ titulo: "TR-01 69/13,8 kV", meta: [selo("imediato"), el("span", {}, "SE Campina Grande II"), el("span", {}, "12/10/2026 09:31"), el("span", {}, "3 de 5")],
          acoes: [botao({ texto: C.detectarDeNovo, icone: "detectar" }), botao({ texto: C.mais, icone: "mais-opcoes", soIcone: true }), botao({ texto: C.gerarLaudo, icone: "laudo", variante: "primario" })] })))),
      exemplo(C.cartaoT, el("div", { class: "grade-ex" },
        el("div", { class: "cartao" }, el("div", { class: "corpo" }, el("h3", {}, C.condicoes), el("dl", { class: "pares" }, el("dt", {}, C.ambiente), el("dd", {}, temperatura(31)), el("dt", {}, C.carga), el("dd", {}, "74 %")))),
        el("div", { class: "cartao recuado" }, el("div", { class: "corpo" }, el("h3", {}, C.recuado), el("p", {}, C.recuadoTexto)))))),

    secao("severidade", C.severidade,
      exemplo(C.selos, linha(["normal", "atencao", "programar", "urgente", "imediato", "sem_medida", "nao_avaliado"].map((n) => selo(n)), selo("programar", { indicativa: true }))),
      exemplo(C.barras, el("div", { style: { display: "grid", gap: "var(--e-2)", maxWidth: "var(--col-g)" } },
        [["imediato", 108], ["programar", 75], ["atencao", 49], ["normal", 32]].map(([n, v]) => el("div", { class: `barra sev-${n}`, role: "img", "aria-label": `${T.niveis[n]}: ${v} % da MTA` }, el("i", { style: { width: `${Math.min(v, 100)}%` } }))))),
      exemplo(C.indicadores, el("div", { class: "grade-ex" },
        indicador({ rotulo: C.criticas, valor: 2, nota: C.criticasNota, severidade: "urgente", href: "#severidade" }),
        indicador({ rotulo: C.pendenciasVencidas, valor: 3, nota: C.pendenciasNota, severidade: "programar", href: "#severidade" }),
        indicador({ rotulo: C.inspecoesVencidas, valor: 4, nota: C.inspecoesNota, severidade: "atencao", href: "#severidade" }),
        indicador({ rotulo: C.alertas, valor: 0, nota: C.alertasNota })))),

    secao("tabela", C.tabelaT,
      tabela({
        rotulo: C.tabelaT,
        ordem: { chave: "tmax", sentido: "desc" },
        aoOrdenar: () => avisar(C.ordenar),
        severidade: (l) => l.sev,
        href: () => "#tabela",
        selecionada: (l) => l.id === "a2",
        colunas: [
          { chave: "equipamento", titulo: C.equipamento, ordenavel: true, celula: (l) => [l.equipamento, el("span", { class: "sub" }, l.instalacao)] },
          { chave: "regiao", titulo: C.regiao },
          { chave: "tmax", titulo: C.tmax, classe: "num", ordenavel: true, celula: (l) => el("b", {}, temperatura(l.tmax)) },
          { chave: "criterio", titulo: C.criterio },
          { chave: "sev", titulo: C.severidadeCol, celula: (l) => selo(l.sev) },
          { chave: "prazo", titulo: C.prazo, classe: "num", celula: (l) => el("span", { class: l.vencida ? "vencida" : null }, l.prazo) },
          { chave: "acoes", titulo: el("span", { class: "so-leitor" }, C.acoes), classe: "dir", celula: (l) => el("div", { class: "acoes-linha" }, botao({ texto: C.editarItem(l.equipamento), icone: "editar", compacto: true, soIcone: true, variante: "fantasma" })) },
        ],
        linhas: AMOSTRA,
      })),

    secao("estados", C.estados,
      exemplo(C.esqueletoT, el("div", { class: "grade-ex" }, esqueleto.linhas(4), esqueleto.tabela(3)), esqueleto.indicadores(4)),
      exemplo(C.vazioT, estadoVazio({ icone: "inspecoes", titulo: C.vazioTitulo, texto: C.vazioTexto, acoes: [botao({ texto: C.importar, icone: "importar", variante: "primario" })] })),
      exemplo(C.erroT, estadoErro({ titulo: C.erroTitulo, erro: new Error(C.erroDetalhe), tentar: () => avisar(C.tentando) })),
      exemplo(C.semConexao, el("div", { class: "faixa-conexao faixa-estatica", role: "presentation" }, icone("offline"), el("span", {}, el("b", {}, T.casca.offline), " ", T.casca.offlineDica), botao({ texto: T.geral.tentarDeNovo, icone: "refazer", compacto: true })))),

    secao("retorno", C.retorno,
      exemplo(C.avisosT, linha(
        botao({ texto: C.avisoSimples, onclick: () => avisar(C.laudoGerado) }),
        botao({ texto: C.avisoDesfazer, onclick: () => avisar(C.regiaoApagada, { acao: { rotulo: T.geral.desfazer, executar: () => avisar(C.desfeito) } }) }),
        botao({ texto: C.avisoErro, onclick: () => avisar(C.erroDetalhe, { erro: true }) })),
        el("div", { class: "aviso aviso-estatico", role: "presentation", style: { maxWidth: "var(--aviso-max)" } }, icone("check"), el("span", { class: "texto" }, C.regiaoApagada), el("button", { type: "button", class: "btn compacto acao" }, T.geral.desfazer), el("button", { type: "button", class: "btn compacto icone", "aria-label": T.geral.fechar }, icone("x", "ic p")))),
      exemplo(C.dialogosT, linha(
        botao({ texto: C.abrirDialogo, onclick: () => dialogo({ titulo: C.dialogoTitulo, corpo: [campo({ rotulo: C.ordemServico, marcador: "OS 4471" }), campo({ rotulo: C.responsavel, opcoes: C.responsaveis })], acoes: [botao({ texto: C.cancelar, onclick: (ev) => ev.target.closest("dialog").close() }), botao({ texto: C.salvar, variante: "primario", onclick: (ev) => { ev.target.closest("dialog").close(); avisar(C.salvo); } })] }).abrir() }),
        botao({ texto: C.abrirConfirmar, variante: "perigo", icone: "lixo", onclick: async () => { if (await confirmar({ titulo: C.confirmarTitulo, texto: C.confirmarTexto, confirmar: C.apagar, perigo: true })) avisar(C.apagado); } })))),

    secao("acabamento", C.acabamento,
      exemplo(C.vozEstrutura, el("div", { class: "tipos" },
        el("div", { class: "tipo" }, el("code", {}, "--fonte-estrutura"), el("span", { class: "estrutura-caixa", style: { fontSize: "var(--t-1)", fontWeight: "var(--p-medio)" } }, C.amostraEstrutura)),
        el("div", { class: "tipo" }, el("code", {}, "--fonte"), el("span", { style: { fontSize: "var(--t-1)", fontWeight: "var(--p-medio)", textTransform: "uppercase", letterSpacing: "var(--espaco-estrutura)" } }, C.amostraEstrutura)))),
      exemplo(C.barraT, barraFerramentas({
        rotulo: C.barraT,
        grupos: [
          [{ texto: C.selecionar, icone: "selecionar", pressionado: true }, { texto: C.novaRegiao, icone: "regiao", pressionado: false }, { texto: C.ponto, icone: "ponto", pressionado: false }, { texto: C.linhaT, icone: "linha", pressionado: false }],
          [{ texto: C.camadas, icone: "camadas" }, { texto: C.foto, icone: "foto", indisponivel: C.semFoto }],
        ],
        direita: [{ texto: C.mais, icone: "mais-opcoes", soIcone: true }],
      })),
      exemplo(C.painelT, el("div", { class: "cartao", style: { display: "flex", justifyContent: "flex-end", overflow: "hidden", height: "var(--e-24)", minHeight: "calc(var(--e-24) * 4)" } },
        painelDetalhe({
          rotulo: C.painelT,
          itens: [
            { id: "c-regiao", icone: "info", texto: C.regiaoT, montar: () => [secaoRecolhivel({ titulo: C.leituras, conteudo: [el("dl", { class: "pares" }, el("dt", {}, C.tmax), el("dd", {}, temperatura(96.4)), el("dt", {}, C.criterio), el("dd", {}, "108 % da MTA"))] }), secaoRecolhivel({ titulo: C.dimensoes, aberta: false, conteudo: [el("p", {}, "1,22 × 0,31 m")] })] },
            { id: "c-alertas", icone: "sino", texto: C.alertas, qtd: 2, montar: () => [secaoRecolhivel({ titulo: C.pendentesT, qtd: 2, conteudo: [el("p", {}, C.doisAlertas)] })] },
          ],
        }))),
      exemplo(C.ilustracoesT, el("div", { class: "grade-ilustracoes" }, NOMES_ILUSTRACOES.map((n) => el("figure", {}, ilustracao(n, { rotulo: C.ilu[n] }), el("figcaption", {}, C.ilu[n]))))),
      exemplo(C.vazioIlustrado, estadoVazio({ ilustracao: "inspecoes", titulo: C.vazioTitulo, texto: C.vazioTexto, acoes: [botao({ texto: C.importar, icone: "importar", variante: "primario" })] })),
      exemplo(C.procurandoT, estadoVazio({ ilustracao: "captura", procurando: true, titulo: C.procurando, texto: C.procurandoTexto }))),

    secao("icones", C.iconesT, el("div", { class: "icones" }, NOMES_ICONES.map((n) => el("div", {}, icone(n), n)))),

    secao("conferencia", C.conferenciaT, el("div", { class: "resultado-conferencia", id: "resultado" }, el("p", {}, C.conferenciaDica))),
  );
  $("#indice").append(...secoes.filter(([id]) => ["cores", "tipografia", "botoes", "campos", "tabela", "estados", "acabamento", "conferencia"].includes(id)).map(([id, t]) => el("a", { href: `#${id}` }, t)));
  // o índice usa âncoras da própria página; nada de roteamento aqui
  document.querySelectorAll('a[href="#severidade"], a[href="#tabela"]').forEach((a) => a.addEventListener("click", (ev) => ev.preventDefault()));
}

function mostrarConferencia() {
  const r = conferir({ toque: params.has("toque") });
  const caixa = $("#resultado");
  const lista = (itens, f) => el("ul", {}, itens.slice(0, 30).map((i) => el("li", { class: "mono" }, f(i))));
  caixa.replaceChildren(
    el("p", { class: r.contraste.length ? "falha" : "ok" }, C.resultadoContraste(r.textos, r.contraste.length)),
    r.contraste.length ? lista(r.contraste, (i) => `${i.razao}:1 < ${i.minimo}  "${i.texto}"  ${i.onde}`) : null,
    el("p", { class: r.alvos.length ? "falha" : "ok" }, C.resultadoAlvos(r.clicaveis, r.alvos.length, params.has("toque"))),
    r.alvos.length ? lista(r.alvos, (i) => `${i.tamanho} < ${i.minimo}  ${i.onde}`) : null,
  );
  document.body.dataset.conferencia = JSON.stringify({ tema: document.documentElement.dataset.tema, toque: params.has("toque"), ...r });
  return r;
}

instalarIcones();
montar();
// a página nasce vazia e é montada aqui: só agora a âncora do endereço existe
if (location.hash) document.querySelector(location.hash)?.scrollIntoView();
// ?secao=<id>: só aquela seção (captura de tela de uma parte do catálogo)
if (params.get("secao")) document.querySelectorAll("#catalogo > section").forEach((s) => { s.hidden = s.id !== params.get("secao"); });
if (params.has("conferir")) requestAnimationFrame(() => setTimeout(mostrarConferencia, 300));
