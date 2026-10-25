// Captura (Etapa 3b: só o estado sem fonte de imagens, com dados reais). A tela completa, com pasta
// monitorada, vídeo, celular e alertas, entra na Etapa 5c; enquanto isso a configuração abre na interface atual.
import { TEXTOS as T } from "../../textos.js";
import { el, api } from "../base.js";
import { barraFerramentas, estadoVazio, painelDetalhe, secao } from "../componentes.js";

const K = T.captura;
const NA_ATUAL = { pasta: "/#monitoramento", celular: "/#celular", alertas: "/#monitoramento" };

export async function montar(pagina, rota) {
  const [status, celular, alertas] = await Promise.all([api("/api/status"), api("/api/celular").catch(() => ({ ligado: false })), api("/api/alertas").catch(() => ({ pendentes: 0 }))]);
  const m = status.monitoramento || {};
  const pasta = (m.pasta || "").trim();
  const temFonte = Boolean(pasta || m.ativo || celular.ligado);
  const pendentes = alertas.pendentes || 0;

  pagina.classList.add("cheia");
  const barra = barraFerramentas({
    rotulo: K.ferramentas,
    grupos: [
      [
        { texto: K.pasta, icone: "pasta", href: NA_ATUAL.pasta },
        { texto: K.celular, icone: "celular", href: NA_ATUAL.celular },
      ],
      [{ texto: K.verificar, icone: "refazer", indisponivel: m.ativo ? null : K.semFonte, onclick: () => api("/api/monitoramento/verificar", { method: "POST" }) }],
    ],
  });

  const centro = el("div", { class: "centro" }, temFonte
    ? estadoVazio({ icone: "captura", titulo: K.ligadaTitulo, texto: K.ligadaTexto, acoes: [el("a", { class: "btn", href: NA_ATUAL.pasta }, T.provisoria.abrirAtual)] })
    : estadoVazio({ ilustracao: "captura", titulo: K.vazioTitulo, texto: K.vazioTexto, acoes: [el("a", { class: "btn primario", href: NA_ATUAL.pasta }, K.definirPasta)] }));

  const painel = painelDetalhe({
    rotulo: K.painel,
    ativa: rota.partes[0] === "alertas" ? "alertas" : "fonte",
    itens: [
      {
        id: "fonte", icone: "info", texto: K.fonte,
        montar: () => [
          secao({ titulo: K.pasta, conteudo: [el("p", { class: pasta ? "mono" : null }, pasta || K.pastaNaoDefinida), el("div", { class: "grupo-btn" }, el("a", { class: "btn compacto", href: NA_ATUAL.pasta }, pasta ? K.alterar : K.definir))] }),
          secao({ titulo: K.celular, conteudo: [el("p", {}, celular.ligado ? K.celularLigado : K.celularDesligado), el("div", { class: "grupo-btn" }, el("a", { class: "btn compacto", href: NA_ATUAL.celular }, celular.ligado ? K.abrir : K.ligar))] }),
        ],
      },
      {
        id: "alertas", icone: "sino", texto: K.alertas, qtd: pendentes,
        montar: () => [secao({ titulo: K.pendentes, qtd: pendentes, conteudo: [el("p", {}, pendentes ? K.alertasPendentes(pendentes) : K.nenhumAlerta), pendentes ? el("div", { class: "grupo-btn" }, el("a", { class: "btn compacto", href: NA_ATUAL.alertas }, T.provisoria.abrirAtual)) : null] })],
      },
    ],
  });

  pagina.append(el("div", { class: "tela-trabalho" }, barra, el("div", { class: "area-trabalho" }, centro, painel)));
}
