// Modelos › Em uso: o modelo térmico (para-raios + pontos quentes) e, ao lado, o detalhe dele. Só aparecem os que
// o servidor marca como principais (`principal`): a regra sozinha, o SAM 2 e o modelo treinado sem os pontos
// quentes saíram da escolha em 31/10/2026. A versão rápida (INT8) é uma opção no detalhe do original.
import { TEXTOS as T } from "../../textos.js";
import { el, icone, api, json, fmt } from "../base.js";
import { endereco } from "../rotas.js";
import { botao, tabela, secao, avisar, ocupado, estadoVazio } from "../componentes.js";
import { nomeClasse } from "../situacao.js";

const M = T.modelos;

/** Original → versão rápida (e o mesmo para a combinação com os pontos quentes). */
function mapaRapidas(modelos) {
  const rapidas = new Map();
  for (const m of modelos) {
    const origem = m.cartao?.otimizacao?.origem;
    if (!origem) continue;
    rapidas.set(origem, m);
    const comb = modelos.find((x) => x.id === `${m.id}+pontos-quentes`);
    if (comb) rapidas.set(`${origem}+pontos-quentes`, { ...comb, cartao: { ...comb.cartao, otimizacao: m.cartao.otimizacao } });
  }
  return rapidas;
}

/** O recomendado: a IA treinada junto com a regra dos pontos quentes (diz a peça e liga o calor a ela). */
const recomendadoDe = (lista) => lista.find((m) => m.tipo === "combinado" && m.id.endsWith("+pontos-quentes") && m.disponivel !== false) || null;

export async function montar(no) {
  let dados = await api("/api/modelos");
  let escolhido = null;
  const corpo = el("div", { class: "corpo-lista com-lado" });
  const area = el("div", { class: "area-lista" });
  const lado = el("aside", { class: "painel-lateral", "aria-label": M.detalhe });
  const instalar = el("input", { type: "file", accept: ".zip", hidden: true, onchange: () => { instalarModelo(instalar.files[0]); instalar.value = ""; } });
  // onde o modelo em uso roda: na placa, preparando a placa (TensorRT monta o motor uma vez) ou no processador
  const onde = el("p", { class: "nota", role: "status" });
  const desenharOnde = () => {
    const p = dados.placa;
    onde.textContent = !p ? "" : p.onde === "placa" ? M.ondePlaca(p.placa) : p.onde === "carregando" ? M.preparandoPlaca(p.acelerador) : M.ondeCpu;
  };
  desenharOnde();
  const relogio = setInterval(async () => {
    if (dados.placa?.onde !== "carregando") return;
    try { dados = await api("/api/modelos"); desenharOnde(); } catch { /* a faixa de conexão avisa */ }
  }, 5000);
  no.append(el("div", { class: "barra-lista" }, el("div", {}, el("p", { class: "nota" }, M.notaLista), onde,
    el("p", { class: "nota" }, M.notaMedicao, " ", el("a", { href: endereco("medicao", ["modelos"]) }, M.irMedicao))), el("span", { class: "empurrar" }),
    botao({ texto: M.instalar, icone: "importar", title: M.instalarDica, onclick: () => instalar.click() }), instalar), corpo);
  corpo.append(area, lado);
  desenhar();

  function desenhar() {
    const rapidas = mapaRapidas(dados.modelos);
    // a rápida some da lista quando o original dela está na lista (vira opção no detalhe dele)
    const ehRapida = (m) => [...rapidas.entries()].some(([origem, r]) => r.id === m.id && dados.modelos.some((x) => x.id === origem && x.principal));
    const lista = dados.modelos.filter((m) => m.principal && !ehRapida(m));
    const recomendado = recomendadoDe(lista);
    // o em uso conta para o original quando a versão rápida está ativa
    const emUso = (m) => m.id === dados.ativo || rapidas.get(m.id)?.id === dados.ativo;
    if (!escolhido || !lista.some((m) => m.id === escolhido)) escolhido = (lista.find(emUso) || recomendado || lista[0])?.id;
    if (!lista.length) { area.replaceChildren(estadoVazio({ ilustracao: "modelos", titulo: M.vazioTitulo, texto: M.vazioTexto })); lado.replaceChildren(); return; }
    area.replaceChildren(tabela({
      rotulo: M.aba.emuso,
      colunas: [
        { chave: "nome", titulo: M.colModelo, link: true, celula: (m) => [el("span", { class: "corta", title: m.nome }, m.nome), el("span", { class: "sub corta", title: m.arquitetura }, m.arquitetura)] },
        { chave: "tipo", titulo: M.colTipo, celula: (m) => M.tipos[m.tipo] || M.tipos.aprendizado },
        { chave: "pecas", titulo: M.colPecas, classe: "num", celula: (m) => String(m.classes.length) },
        { chave: "situacao", titulo: M.colSituacao, celula: (m) => situacao(m, emUso(m), m.id === recomendado?.id) },
      ],
      linhas: lista,
      selecionada: (m) => m.id === escolhido,
      aoEscolher: (m) => { escolhido = m.id; desenhar(); },
    }));
    desenharLado(lista.find((m) => m.id === escolhido), rapidas.get(escolhido), emUso, recomendado);
  }

  function situacao(m, usado, recomendado) {
    if (m.disponivel === false) return el("span", { class: "fraco" }, M.naoInstalado);
    return el("div", { class: "celula-sev" }, usado ? el("span", { class: "em-uso" }, icone("check", "ic p"), M.emUso) : null,
      recomendado ? el("span", { class: "chip-recomendado", title: M.recomendadoDica }, M.recomendado) : null);
  }

  function desenharLado(m, rapida, emUso, recomendado) {
    if (!m) { lado.replaceChildren(); return; }
    const c = m.cartao || {};
    const usar = (alvo, b) => ocupado(b, async () => {
      try {
        dados = await api("/api/modelos/ativo", json("PUT", { id: alvo.id }));
        avisar(M.passaASer(alvo.nome));
        desenhar();
      } catch (e) { avisar(e.message, { erro: true }); }
    });
    const treino = typeof c.treino === "string" ? c.treino : c.treino ? Object.values(c.treino).join(", ") : null;
    const metricas = c.metricas ? Object.entries(c.metricas).map(([k, v]) => [k, typeof v === "number" ? fmt(v, v < 1 && v > 0 ? 3 : 2) : v ?? T.geral.semValor]) : [];
    const o = rapida?.cartao?.otimizacao;
    const acao = m.disponivel === false
      ? el("p", { class: "fraco" }, M.naoInstaladoTexto)
      : emUso(m) && dados.ativo === m.id ? el("p", { class: "em-uso" }, icone("check", "ic p"), M.emUsoTexto)
        : botao({ texto: rapida && dados.ativo === rapida.id ? M.usarNormal : M.usar, variante: "primario", onclick: (ev) => usar(m, ev.currentTarget) });
    const blocoRapida = o ? secao({ titulo: M.rapida, conteudo: [
      el("p", {}, M.rapidaInfo(o.tempo_ms, o.tempo_original_ms, fmt(o.tamanho_mb, 1), fmt(o.tamanho_original_mb, 1))),
      o.teste && o.teste_original ? el("p", { class: "nota" }, M.rapidaAcerto(fmt(o.teste_original.mAP50, 3), fmt(o.teste.mAP50, 3))) : null,
      el("div", { class: "grupo-btn" }, dados.ativo === rapida.id ? el("span", { class: "em-uso" }, icone("check", "ic p"), M.emUso)
        : botao({ texto: M.usarRapida, compacto: true, onclick: (ev) => usar(rapida, ev.currentTarget) })),
    ] }) : null;
    lado.replaceChildren(...[
      el("div", { class: "cab-lado cab-modelo" },
        el("div", { class: "titulo-lado" }, el("h2", {}, m.nome), el("p", { class: "nota" }, `${M.tipos[m.tipo] || M.tipos.aprendizado}, ${M.versao(m.versao)}`),
          m.id === recomendado?.id ? el("span", { class: "chip-recomendado" }, M.recomendado) : null),
        el("p", {}, m.descricao),
        el("div", { class: "fichas-classes" }, m.classes.map((cl) => el("span", { class: "ficha-classe" }, m.nomes?.[cl] || nomeClasse(cl)))),
        el("div", { class: "grupo-btn" }, acao)),
      treino || metricas.length ? secao({ titulo: M.desempenho, conteudo: [
        treino ? el("p", {}, treino) : null,
        metricas.length ? el("dl", { class: "pares" }, metricas.flatMap(([k, v]) => [el("dt", {}, k), el("dd", { class: "num" }, String(v))])) : null,
      ] }) : null,
      blocoRapida,
      c.vantagens?.length ? secao({ titulo: M.vantagens, aberta: false, conteudo: [el("ul", { class: "lista-avisos" }, c.vantagens.map((v) => el("li", {}, v)))] }) : null,
      c.limitacoes?.length ? secao({ titulo: M.limitacoes, aberta: false, conteudo: [el("ul", { class: "lista-avisos" }, c.limitacoes.map((v) => el("li", {}, v)))] }) : null,
    ].filter(Boolean));
  }

  async function instalarModelo(arquivo) {
    if (!arquivo) return;
    const envio = new FormData();
    envio.append("arquivo", arquivo);
    try {
      const r = await api("/api/modelos/instalar", { method: "POST", body: envio });
      dados = { ...dados, ativo: r.ativo, modelos: r.modelos };
      escolhido = r.id;
      avisar(M.instalado(r.id));
      desenhar();
    } catch (e) { avisar(e.message, { erro: true }); }
  }
  return () => clearInterval(relogio);
}
