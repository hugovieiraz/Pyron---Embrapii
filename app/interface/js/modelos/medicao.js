// Modelos › Medição: os modelos de medir em foto comum (DA3, MoGe-2 e o SAM do contorno). À esquerda, o que
// está instalado e o erro nas fotos do Hugo; ao lado, o detalhe do escolhido, o erro no registro deste
// computador (medidas com valor real) e o que falta instalar. Testar abre Captura › Medir foto.
import { TEXTOS as T } from "../../textos.js";
import { el, icone, api, json } from "../base.js";
import { botao, tabela, secao, avisar, ocupado } from "../componentes.js";
import { endereco } from "../rotas.js";

const M = T.modelos.medicao;
const MODOS = { com_referencia: M.comPostit, sem_referencia: M.semRef };

export async function montar(no) {
  let [estado, registro] = await Promise.all([api("/api/medicao/estado"), api("/api/medicao/registro?limite=1").catch(() => ({ resumo: {} }))]);
  let escolhido = estado.modelo_padrao || "da3";
  const corpo = el("div", { class: "corpo-lista com-lado" });
  const area = el("div", { class: "area-lista" });
  const lado = el("aside", { class: "painel-lateral", "aria-label": T.modelos.detalhe });
  no.append(el("div", { class: "barra-lista" }, el("p", { class: "nota" }, M.nota), el("span", { class: "empurrar" }),
    el("a", { class: "btn", href: endereco("captura", ["medir"]) }, icone("regua"), M.testar)), corpo);
  corpo.append(area, lado);
  desenhar();

  function situacao(c) {
    if (!c.pacote) return el("span", { class: "fraco" }, M.semPacote);
    if (!c.pesos) return el("span", { class: "fraco" }, M.naoInstalado);
    return el("div", { class: "celula-sev" }, el("span", { class: "em-uso" }, icone("check", "ic p"), M.instalado),
      c.id === estado.modelo_padrao ? el("span", { class: "chip-recomendado" }, M.padrao) : null);
  }

  function desenhar() {
    const lista = estado.catalogo || [];
    area.replaceChildren(tabela({
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
    const baixar = (b) => ocupado(b, async () => {
      avisar(M.baixando);
      try {
        estado = await api("/api/medicao/baixar", json("POST", { modelo: c.id }));
        avisar(M.baixado(m.nome));
        desenhar();
      } catch (e) { avisar(e.message, { erro: true }); }
    });
    const acao = !c.pacote
      ? [el("p", {}, M.instalarPacote), el("pre", { class: "comando" }, m.comando)]
      : !c.pesos ? [el("div", { class: "grupo-btn" }, botao({ texto: M.baixar, icone: "importar", variante: "primario", onclick: (ev) => baixar(ev.currentTarget) }))]
        : [el("p", { class: "em-uso" }, icone("check", "ic p"), M.instalado), el("p", { class: "nota" }, M.dispositivo(estado.dispositivo))];
    lado.replaceChildren(...[
      el("div", { class: "cab-lado cab-modelo" },
        el("div", { class: "titulo-lado" }, el("h2", {}, m.nome), el("p", { class: "nota" }, `${M.funcoes[m.funcao]}, ${m.licenca}`),
          c.id === estado.modelo_padrao ? el("span", { class: "chip-recomendado" }, M.padrao) : null),
        el("p", {}, m.texto),
        ...acao),
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
  return null;
}
