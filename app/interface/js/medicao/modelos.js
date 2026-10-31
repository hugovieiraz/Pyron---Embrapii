// Medição › Modelos: os modelos de medir em foto comum (DA3, MoGe-2 e o SAM do contorno). À esquerda, o que está
// instalado e o erro nas fotos do Hugo; ao lado, o detalhe do escolhido, a placa de vídeo e o que falta instalar.
// Testar abre Medição › Medir. A medida em si não é guardada: nada de histórico aqui.
import { TEXTOS as T } from "../../textos.js";
import { el, icone, api, json } from "../base.js";
import { botao, tabela, secao, avisar } from "../componentes.js";
import { endereco } from "../rotas.js";

const M = T.modelos.medicao;

export async function montar(no) {
  let estado = await api("/api/medicao/estado");
  let escolhido = estado.modelo_padrao || "da3";
  const corpo = el("div", { class: "corpo-lista com-lado" });
  const tabelaModelos = el("div");
  const area = el("div", { class: "area-lista area-medicao" }, tabelaModelos);
  const lado = el("aside", { class: "painel-lateral", "aria-label": T.modelos.detalhe });
  no.append(el("div", { class: "barra-lista" }, el("p", { class: "nota" }, M.nota), el("span", { class: "empurrar" }),
    el("a", { class: "btn", href: endereco("medicao") }, icone("regua"), M.testar)), corpo);
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

  function situacao(c) {
    if (!c.pacote) return el("span", { class: "fraco" }, M.semPacote);
    if (!c.pesos) return el("span", { class: "fraco" }, M.naoInstalado);
    return el("div", { class: "celula-sev" }, el("span", { class: "em-uso" }, icone("check", "ic p"), M.instalado),
      c.id === estado.modelo_padrao && c.pacote && c.pesos ? el("span", { class: "chip-recomendado" }, M.padrao) : null);
  }

  function desenhar() {
    const lista = estado.catalogo || [];
    tabelaModelos.replaceChildren(tabela({
      rotulo: T.telas.medicao,
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
      secao({ titulo: M.vantagens, aberta: false, conteudo: [el("ul", { class: "lista-avisos" }, m.vantagens.map((v) => el("li", {}, v)))] }),
    ].filter(Boolean));
  }
  return () => clearInterval(vigia);
}
