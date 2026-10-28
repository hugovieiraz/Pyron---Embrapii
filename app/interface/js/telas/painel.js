// Painel (Etapa 5a): o que precisa de atenção hoje. À esquerda, "Atenção agora" (a última inspeção de
// cada equipamento fora do normal, da pior para a melhor); à direita, os quatro indicadores clicáveis,
// o que falta configurar, as próximas inspeções e a situação atual. Sem inspeção: primeira execução.
import { TEXTOS as T } from "../../textos.js";
import { el, icone, api, data, dataHora, relativa, temperatura } from "../base.js";
import { botao, selo, indicador, estadoVazio, avisar, ocupado } from "../componentes.js";
import { endereco } from "../rotas.js";
import { ilustracao } from "../ilustracoes.js";
import { escolherArquivos, importarDemonstracao } from "../importar.js";
import { CRITICAS, ORDEM_SEVERIDADE, SEM_EQUIPAMENTO, quando, severidade, pesoSeveridade, situacaoAtual, leituraDestaque, miniatura } from "../situacao.js";

const P = T.painel;
const FORA_DO_NORMAL = ["imediato", "urgente", "programar", "atencao"];

export async function montar(pagina) {
  let dados = await carregar();
  pagina.classList.add("tela-painel");
  desenhar();

  function desenhar() {
    const vazio = !dados.lista.length;
    const importar = botao({ texto: T.inspecoes.importar, icone: "importar", variante: "primario", atalho: "Ctrl O", onclick: escolherArquivos });
    const cab = el("header", { class: "cabecalho" }, el("div", { class: "titulo" }, el("h1", {}, T.telas.painel)), vazio ? null : el("div", { class: "acoes" }, importar));
    pagina.replaceChildren(cab, vazio ? primeiraExecucao(dados.exemplos) : el("div", { class: "painel-grade" }, el("div", { class: "coluna-principal" }, colunaAtencao(dados), recentes(dados)), colunaLado(dados)));
  }

  // atualiza sozinho: a captura automática e outras janelas também criam inspeções
  const atualizar = async () => {
    try { dados = await carregar(); } catch { return; } // a faixa de conexão já avisa
    desenhar();
  };
  const relogio = setInterval(atualizar, 60000);
  document.addEventListener("pyron:importadas", atualizar);
  return () => { clearInterval(relogio); document.removeEventListener("pyron:importadas", atualizar); };
}

async function carregar() {
  const [lista, pendencias, equipamentos, status, config] = await Promise.all([
    api("/api/analises"), api("/api/pendencias").catch(() => []), api("/api/equipamentos").catch(() => []),
    api("/api/status"), api("/api/configuracoes").catch(() => null),
  ]);
  const exemplos = lista.length ? [] : (await api("/api/exemplos").catch(() => ({ itens: [] }))).itens;
  return { lista, pendencias, equipamentos, status, config, exemplos };
}

// ---------------------------------------------------------------- Atenção agora
function colunaAtencao({ lista }) {
  const fora = situacaoAtual(lista)
    .filter((it) => FORA_DO_NORMAL.includes(severidade(it)))
    .sort((a, b) => pesoSeveridade(severidade(a)) - pesoSeveridade(severidade(b))
      || (b.destaque?.pct_mta ?? 0) - (a.destaque?.pct_mta ?? 0)
      || quando(b).localeCompare(quando(a)));
  const titulo = el("h2", { class: "titulo-coluna" }, P.atencao, fora.length ? el("span", { class: "qtd" }, String(fora.length)) : null);
  if (!fora.length) {
    return el("section", { class: "coluna-atencao", "aria-label": P.atencao }, titulo,
      estadoVazio({ ilustracao: "pendencias", titulo: P.tudoNormal, texto: P.tudoNormalTexto }));
  }
  return el("section", { class: "coluna-atencao", "aria-label": P.atencao }, titulo, el("ul", { class: "lista-atencao" }, fora.map(linhaAtencao)));
}

function linhaAtencao(it) {
  const id = it.identificacao || {};
  const d = it.destaque || {};
  const sev = severidade(it);
  const detalhe = [id.instalacao, d.nome, leituraDestaque(d), relativa(quando(it))].filter(Boolean).join(", ");
  return el("li", {}, el("a", { class: "linha-atencao", href: endereco("inspecoes", [it.id]), style: { "--sev": `var(--${sev})` } },
    el("i", { class: "traco", "aria-hidden": "true" }),
    el("span", { class: "eq" }, el("b", { class: "corta", title: id.equipamento || it.arquivo }, id.equipamento || it.arquivo), el("span", { class: "corta", title: detalhe }, detalhe)),
    el("span", { class: "leitura" }, el("b", { class: "num" }, temperatura(d.t_max ?? it.resumo?.t_max_cena)), selo(sev, { indicativa: Boolean(it.resumo?.conferir) }))));
}

/** As três últimas importadas: o caminho de volta para o que acabou de entrar (o resto da altura fica para "Atenção agora"). */
function recentes({ lista }) {
  const ultimas = [...lista].sort((a, b) => String(b.criado_em).localeCompare(String(a.criado_em))).slice(0, 3);
  return el("section", { class: "bloco-recentes", "aria-label": P.recentes },
    el("div", { class: "titulo-bloco" }, el("h2", {}, P.recentes), el("a", { href: endereco("inspecoes") }, P.verInspecoes(lista.length))),
    el("ul", { class: "lista-recentes" }, ultimas.map((it) => {
      const id = it.identificacao || {};
      return el("li", {}, el("a", { href: endereco("inspecoes", [it.id]) },
        el("img", { class: "miniatura", src: miniatura(it), alt: "", loading: "lazy", decoding: "async", width: 64, height: 48 }),
        el("span", { class: "eq" }, el("b", { class: "corta", title: id.equipamento || it.arquivo }, id.equipamento || it.arquivo),
          el("span", { class: "corta" }, [id.equipamento ? it.arquivo : null, id.instalacao].filter(Boolean).join(", ") || T.inspecoes.semEquipamento)),
        el("span", { class: "quando", title: dataHora(it.criado_em) }, P.importada(relativa(it.criado_em))),
        selo(severidade(it), { indicativa: Boolean(it.resumo?.conferir) })));
    })));
}

// ---------------------------------------------------------------- coluna da direita
function colunaLado({ lista, pendencias, equipamentos, status, config }) {
  const atual = situacaoAtual(lista);
  const criticas = atual.filter((it) => CRITICAS.includes(severidade(it))).length;
  const abertas = pendencias.filter((p) => ["aberta", "programada"].includes(p.status));
  const vencidas = abertas.filter((p) => p.vencida).length;
  const reais = equipamentos.filter((e) => e.chave !== SEM_EQUIPAMENTO);
  const comAgenda = reais.filter((e) => e.proxima_inspecao);
  const atrasadas = comAgenda.filter((e) => e.proxima_inspecao.vencida).length;
  const alertas = status.alertas_pendentes || 0;

  const indicadores = el("div", { class: "indicadores" },
    indicador({ rotulo: P.criticas, valor: criticas, nota: P.criticasNota, severidade: criticas ? "imediato" : null, href: endereco("inspecoes", [], { sev: "criticas", atual: "1" }) }),
    indicador({ rotulo: P.pendenciasVencidas, valor: vencidas, nota: P.pendenciasNota(abertas.length), severidade: vencidas ? "urgente" : null, href: endereco("pendencias", [], { situacao: "vencidas" }) }),
    indicador({ rotulo: P.inspecoesVencidas, valor: atrasadas, nota: P.inspecoesNota(reais.length), severidade: atrasadas ? "programar" : null, href: endereco("equipamentos", [], { filtro: "vencidas" }) }),
    indicador({ rotulo: P.alertas, valor: alertas, nota: P.alertasNota, severidade: alertas ? "urgente" : null, href: endereco("captura", ["alertas"]) }));

  return el("div", { class: "coluna-lado" }, indicadores, avisoConfiguracao(config), proximas(comAgenda), situacao(atual));
}

/** O que falta para o laudo sair completo (empresa e responsável técnico). */
function avisoConfiguracao(config) {
  if (!config) return null;
  const falta = [];
  if (!(config.empresa?.nome || "").trim()) falta.push(P.faltaEmpresa);
  if (!(config.responsaveis || []).some((r) => r.assina !== false)) falta.push(P.faltaResponsavel);
  if (!falta.length) return null;
  return el("div", { class: "aviso-config" }, icone("info"),
    el("p", {}, P.falta(falta)),
    el("a", { class: "btn compacto", href: endereco("configuracoes") }, P.configurar));
}

function proximas(comAgenda) {
  const lista = [...comAgenda].sort((a, b) => a.proxima_inspecao.data.localeCompare(b.proxima_inspecao.data)).slice(0, 5);
  const cab = el("div", { class: "titulo-bloco" }, el("h2", {}, P.proximas), el("a", { href: endereco("equipamentos") }, P.verEquipamentos));
  if (!lista.length) return el("section", { class: "bloco-lado" }, cab, el("p", { class: "nota" }, P.semAgenda));
  return el("section", { class: "bloco-lado" }, cab, el("ul", { class: "lista-proximas" }, lista.map((e) => {
    const p = e.proxima_inspecao;
    return el("li", {}, el("a", { href: endereco("equipamentos", [e.chave]) },
      el("span", { class: "eq" }, el("b", { class: "corta", title: e.equipamento }, e.equipamento), e.instalacao ? el("span", { class: "corta" }, e.instalacao) : null),
      el("span", { class: "quando" }, el("b", { class: "num" }, data(p.data)), el("span", { class: p.vencida ? "vencida" : null }, p.vencida ? P.vencidaHa(relativa(p.data)) : relativa(p.data)))));
  })));
}

/** Barra empilhada da última inspeção de cada equipamento, com a legenda e a contagem por nível. */
function situacao(atual) {
  const niveis = [...ORDEM_SEVERIDADE].filter((n) => atual.some((it) => severidade(it) === n));
  const conta = (n) => atual.filter((it) => severidade(it) === n).length;
  const resumo = niveis.map((n) => `${T.niveis[n]}: ${conta(n)}`).join(", ");
  return el("section", { class: "bloco-lado" },
    el("div", { class: "titulo-bloco" }, el("h2", {}, P.situacao), el("span", { class: "nota" }, P.situacaoNota(atual.filter((it) => it.equipamento_chave && it.equipamento_chave !== SEM_EQUIPAMENTO).length, atual.filter((it) => !it.equipamento_chave || it.equipamento_chave === SEM_EQUIPAMENTO).length))),
    el("div", { class: "barra-empilhada", role: "img", "aria-label": resumo }, niveis.map((n) => el("i", { style: { flexGrow: conta(n), background: `var(--${n})` }, title: `${T.niveis[n]}: ${conta(n)}` }))),
    el("ul", { class: "legenda-niveis" }, niveis.map((n) => el("li", {}, el("i", { style: { background: `var(--${n})` }, "aria-hidden": "true" }), el("span", {}, T.niveis[n]), el("b", { class: "num" }, String(conta(n)))))));
}

// ---------------------------------------------------------------- primeira execução (nenhuma inspeção)
function primeiraExecucao(exemplos) {
  const passo = (n, ilu, titulo, texto) => el("li", {}, ilustracao(ilu, { rotulo: titulo }), el("h3", {}, el("span", { class: "num-passo" }, String(n)), titulo), el("p", {}, texto));
  const demo = exemplos.length ? botao({ texto: P.usarDemonstracao, onclick: () => ocupado(demo, async () => {
    location.hash = endereco("inspecoes");
    try { await importarDemonstracao(); } catch (e) { avisar(e.message, { erro: true }); }
  }) }) : null;
  return el("section", { class: "primeira-execucao", "aria-label": P.inicio },
    el("h2", {}, P.inicio),
    el("ol", { class: "passos" },
      passo(1, "inspecoes", P.passo1, P.passo1Texto),
      passo(2, "analise", P.passo2, P.passo2Texto),
      passo(3, "laudo", P.passo3, P.passo3Texto)),
    el("div", { class: "grupo-btn" }, botao({ texto: T.inspecoes.importar, icone: "importar", variante: "primario", atalho: "Ctrl O", onclick: escolherArquivos }), demo),
    demo ? el("p", { class: "nota" }, P.demonstracaoFonte) : null);
}
