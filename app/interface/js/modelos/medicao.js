// Modelos › Medição: os modelos de medir em foto comum (DA3, MoGe-2 e o SAM do contorno). À esquerda, o que
// está instalado e o erro nas fotos do Hugo; ao lado, o detalhe do escolhido, o erro no registro deste
// computador (medidas com valor real) e o que falta instalar. Testar abre Captura › Medir foto.
import { TEXTOS as T } from "../../textos.js";
import { el, icone, api, json, fmt } from "../base.js";
import { botao, tabela, secao, avisar } from "../componentes.js";
import { endereco } from "../rotas.js";

const M = T.modelos.medicao;
const MODOS = { com_referencia: M.comPostit, sem_referencia: M.semRef };

export async function montar(no) {
  let [estado, registro] = await Promise.all([api("/api/medicao/estado"), api("/api/medicao/registro?limite=500").catch(() => ({ resumo: {}, entradas: [] }))]);
  let escolhido = estado.modelo_padrao || "da3";
  const corpo = el("div", { class: "corpo-lista com-lado" });
  const tabelaModelos = el("div");
  const guardadas = el("section", { class: "medicoes-guardadas", "aria-label": M.guardadas });
  const area = el("div", { class: "area-lista area-medicao" }, tabelaModelos, guardadas);
  const lado = el("aside", { class: "painel-lateral", "aria-label": T.modelos.detalhe });
  no.append(el("div", { class: "barra-lista" }, el("p", { class: "nota" }, M.nota), el("span", { class: "empurrar" }),
    el("a", { class: "btn", href: endereco("captura", ["medir"]) }, icone("regua"), M.testar)), corpo);
  corpo.append(area, lado);
  let instalacao = await api("/api/medicao/instalar").catch(() => ({ ativa: false }));
  let vigia = null;
  desenhar();
  if (instalacao.ativa) acompanhar();

  async function instalar(id) {
    try {
      instalacao = await api("/api/medicao/instalar", json("POST", { modelo: id }));
      desenhar();
      acompanhar();
    } catch (e) { avisar(e.message, { erro: true }); }
  }

  // a instalação leva minutos (pip e pesos): pergunta a cada 2 s e redesenha só o lado
  function acompanhar() {
    clearInterval(vigia);
    vigia = setInterval(async () => {
      instalacao = await api("/api/medicao/instalar").catch(() => instalacao);
      if (!instalacao.ativa) {
        clearInterval(vigia);
        estado = await api("/api/medicao/estado").catch(() => estado);
        if (instalacao.erro) avisar(M.falhou, { erro: true });
        else avisar(M.pronto(M.modelos[instalacao.modelo].nome));
      }
      desenhar();
    }, 2000);
  }

  /** Todas as medições, agrupadas pelo nome do objeto: uma linha por medição, a medida principal em cada modelo e modo. */
  function desenharGuardadas() {
    // agrupadas pelo nome (as sem nome no fim), a mais nova primeiro dentro de cada grupo
    const entradas = [...(registro.entradas || [])].sort((a, b) => Number(!a.nome) - Number(!b.nome)
      || (a.nome || "").localeCompare(b.nome || "", "pt-BR") || b.quando - a.quando);
    const cab = el("div", { class: "titulo-bloco" }, el("h2", {}, M.guardadas),
      entradas.length ? el("a", { href: "/api/medicao/registro.csv", download: "medicoes_pyron.csv" }, M.exportar) : null);
    if (!entradas.length) { guardadas.replaceChildren(cab, el("p", { class: "nota" }, M.guardadasVazio)); return; }
    const ORDEM = ["comprimento", "altura", "largura", "distancia", "espessura"];
    const principal = (e) => ORDEM.find((q) => Object.values(e.resultados || {}).some((r) => r?.sem_referencia?.[`${q}_cm`] != null || r?.com_referencia?.[`${q}_cm`] != null));
    const valor = (e, modelo, modo) => {
      const q = principal(e), v = e.resultados?.[modelo]?.[modo]?.[`${q}_cm`];
      if (v == null) return el("span", { class: "fraco" }, T.geral.semValor);
      const erro = e.erros?.[modelo]?.[modo]?.[q];
      return [el("span", { class: "num" }, fmt(v, 1)), erro != null ? el("span", { class: `sub num erro-medida ${Math.abs(erro) < 0.1 ? "bom" : ""}` }, M.erroPct(Math.round(erro * 100))) : null];
    };
    const data = (t) => new Date(t * 1000).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    const colunasModelo = [["da3", "sem_referencia", "da3"], ["da3", "com_referencia", "da3_ref"], ["moge", "sem_referencia", "moge"], ["moge", "com_referencia", "moge_ref"]];
    guardadas.replaceChildren(cab, el("p", { class: "nota" }, M.guardadasNota), tabela({
      rotulo: M.guardadas,
      grupo: (e) => e.nome || M.semNome,
      href: (e) => endereco("captura", ["medir", e.foto]),
      colunas: [
        { chave: "foto", titulo: M.colFoto, celula: (e) => el("img", { class: "mini-medicao", src: `/api/medicao/fotos/${e.foto}/miniatura`, alt: "", loading: "lazy", decoding: "async" }) },
        { chave: "objeto", titulo: M.colObjeto, link: true, celula: (e) => [el("span", { class: "corta", title: M.abrirFoto }, e.nome || M.semNome),
          el("span", { class: "sub corta" }, M.quando(data(e.quando), M.origem[e.origem] || e.origem))] },
        { chave: "medida", titulo: M.colMedida, celula: (e) => T.medir.nomes[principal(e)] || T.geral.semValor },
        ...colunasModelo.map(([modelo, modo, id]) => ({ chave: id, titulo: M.colunas[id], classe: "num", celula: (e) => valor(e, modelo, modo) })),
        { chave: "real", titulo: M.colReal, classe: "num", celula: (e) => e.real?.[principal(e)] != null ? fmt(e.real[principal(e)], 1) : el("span", { class: "fraco" }, T.geral.semValor) },
      ],
      linhas: entradas,
    }));
  }

  function situacao(c) {
    if (!c.pacote) return el("span", { class: "fraco" }, M.semPacote);
    if (!c.pesos) return el("span", { class: "fraco" }, M.naoInstalado);
    return el("div", { class: "celula-sev" }, el("span", { class: "em-uso" }, icone("check", "ic p"), M.instalado),
      c.id === estado.modelo_padrao && c.pacote && c.pesos ? el("span", { class: "chip-recomendado" }, M.padrao) : null);
  }

  function desenhar() {
    const lista = estado.catalogo || [];
    desenharGuardadas();
    tabelaModelos.replaceChildren(tabela({
      rotulo: T.modelos.aba.medicao,
      colunas: [
        { chave: "nome", titulo: T.modelos.colModelo, link: true, celula: (c) => [el("span", { class: "corta" }, M.modelos[c.id].nome), el("span", { class: "sub corta" }, M.modelos[c.id].sub)] },
        { chave: "funcao", titulo: M.colFuncao, celula: (c) => M.funcoes[M.modelos[c.id].funcao] },
        { chave: "licenca", titulo: M.colLicenca, celula: (c) => M.modelos[c.id].licenca },
        { chave: "fotos", titulo: M.colFotos, classe: "num", celula: (c) => M.modelos[c.id].comPostit },
        { chave: "situacao", titulo: T.modelos.colSituacao, celula: situacao },
      ],
      linhas: lista,
      selecionada: (c) => c.id === escolhido,
      aoEscolher: (c) => { escolhido = c.id; desenhar(); },
    }));
    desenharLado(lista.find((c) => c.id === escolhido));
  }

  function desenharLado(c) {
    if (!c) { lado.replaceChildren(); return; }
    const m = M.modelos[c.id];
    const resumo = registro.resumo?.[c.id] || {};
    const linhasRegistro = Object.entries(MODOS).filter(([modo]) => resumo[modo]);
    const acao = !c.pacote || !c.pesos ? [
      el("p", { class: "nota" }, M.instalarTexto),
      instalacao.ativa
        ? el("p", { class: "nota", role: "status" }, M.instalando(instalacao.modelo === c.id ? instalacao.etapa : M.modelos[instalacao.modelo].nome))
        : el("div", { class: "grupo-btn" }, botao({ texto: M.instalar, icone: "importar", variante: "primario", onclick: () => instalar(c.id) })),
      instalacao.erro && instalacao.modelo === c.id ? el("pre", { class: "comando erro-instalar" }, `${M.falhou}: ${instalacao.erro}`) : null,
      el("p", { class: "nota" }, M.terminal), el("pre", { class: "comando" }, M.comando(c.id)),
    ] : [el("p", { class: "em-uso" }, icone("check", "ic p"), M.instalado), el("p", { class: "nota" }, M.dispositivo(estado.dispositivo))];
    const p = estado.placa || {};
    // a placa de vídeo: em uso, ou por que não e o que fazer (a troca do PyTorch é com o Pyron fechado, pelo terminal)
    const secaoPlaca = secao({ titulo: M.placaTitulo, conteudo: p.usada ? [el("p", { class: "em-uso" }, icone("check", "ic p"), M.placaUsada(p.nome))] : [
      el("p", {}, M.placaMotivo[p.motivo] || M.placaMotivo.falhou),
      p.motivo === "torch_cpu" ? el("pre", { class: "comando" }, M.placaComando) : null,
      p.motivo === "torch_cpu" ? el("p", { class: "nota" }, M.placaComandoNota) : null,
      p.torch ? el("p", { class: "nota" }, M.placaVersao(p.torch, p.cuda)) : null,
    ].filter(Boolean) });
    lado.replaceChildren(...[
      el("div", { class: "cab-lado cab-modelo" },
        el("div", { class: "titulo-lado" }, el("h2", {}, m.nome), el("p", { class: "nota" }, `${M.funcoes[m.funcao]}, ${m.licenca}`),
          c.id === estado.modelo_padrao && c.pacote && c.pesos ? el("span", { class: "chip-recomendado" }, M.padrao) : null),
        el("p", {}, m.texto),
        ...acao),
      secaoPlaca,
      m.funcao === "profundidade" ? secao({ titulo: M.fotosTitulo, conteudo: [
        el("dl", { class: "pares" }, [[M.comPostit, m.comPostit], [M.semRef, m.semRef], [M.porFoto, m.tempo]].flatMap(([k, v]) => [el("dt", {}, k), el("dd", { class: "num" }, v)])),
      ] }) : null,
      m.funcao === "profundidade" ? secao({ titulo: M.registroTitulo, conteudo: linhasRegistro.length ? [
        el("p", { class: "nota" }, M.registroNota),
        el("dl", { class: "pares" }, linhasRegistro.flatMap(([modo, nome]) => [el("dt", {}, `${nome} (${M.medidas(resumo[modo].n)})`),
          el("dd", { class: "num" }, `${String(resumo[modo].erro_mediano_pct).replace(".", ",")} %`)])),
      ] : [el("p", { class: "nota" }, M.registroVazio)] }) : null,
      secao({ titulo: M.vantagens, aberta: false, conteudo: [el("ul", { class: "lista-avisos" }, m.vantagens.map((v) => el("li", {}, v)))] }),
    ].filter(Boolean));
  }
  return () => clearInterval(vigia);
}
