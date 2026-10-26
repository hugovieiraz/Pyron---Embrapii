// Captura › Alertas: o que o monitoramento achou acima do nível escolhido. Enviar abre o WhatsApp com a
// mensagem pronta (o responsável manda; o Pyron não envia sozinho) e marca como enviado; Resolver tem Desfazer.
import { TEXTOS as T } from "../../textos.js";
import { el, api, json, dataHora, relativa, animarEntrada } from "../base.js";
import { botao, segmentado, tabela, selo, estadoVazio, avisar, menu } from "../componentes.js";
import { endereco } from "../rotas.js";

const A = T.alertas;
const FILTROS = { pendente: (a) => a.status === "pendente", enviado: (a) => a.status === "enviado", resolvido: (a) => a.status === "resolvido", todos: () => true };

export async function montar(no, { contarAlertas }) {
  let { alertas } = await api("/api/alertas");
  let filtro = alertas.some(FILTROS.pendente) ? "pendente" : "todos";
  let animada = false;
  let seg = el("div");
  const corpo = el("div", { class: "corpo-alertas" });
  no.append(el("div", { class: "barra-lista" }, seg), corpo);
  desenhar();

  function desenhar() {
    contarAlertas?.(alertas.filter(FILTROS.pendente).length);
    if (!alertas.length) {
      seg.hidden = true;
      corpo.replaceChildren(estadoVazio({ ilustracao: "pendencias", titulo: A.vazioTitulo, texto: A.vazioTexto }));
      return;
    }
    seg.replaceWith(seg = segmentado({ rotulo: A.filtro, valor: filtro, opcoes: Object.keys(FILTROS).map((k) => ({ valor: k, texto: A.filtros[k], qtd: alertas.filter(FILTROS[k]).length })),
      aoMudar: (v) => { filtro = v; desenharTabela(); } }));
    desenharTabela();
  }

  function desenharTabela() {
    const itens = alertas.filter(FILTROS[filtro]);
    if (!itens.length) {
      corpo.replaceChildren(estadoVazio({ ilustracao: "pendencias", titulo: A.nadaTitulo[filtro], compacto: true }));
      return;
    }
    const t = tabela({
      rotulo: A.titulo,
      colunas: [
        { chave: "sev", titulo: A.colSeveridade, celula: (a) => selo(a.severidade) },
        { chave: "quando", titulo: A.colQuando, celula: (a) => [el("span", {}, dataHora(a.criado_em)), el("span", { class: "sub" }, relativa(a.criado_em))] },
        { chave: "inspecao", titulo: A.colInspecao, link: true, celula: (a) => [el("span", { class: "corta", title: a.arquivo }, a.arquivo),
          el("span", { class: "sub corta" }, [a.equipamento, a.instalacao].filter(Boolean).join(", ") || A.semEquipamento)] },
        { chave: "resumo", titulo: A.colResumo, celula: (a) => el("span", { class: "corta resumo-alerta", title: a.resumo }, a.resumo) },
        { chave: "situacao", titulo: A.colSituacao, celula: (a) => A.status[a.status] },
        { chave: "acoes", titulo: el("span", { class: "so-leitor" }, A.colAcoes), classe: "dir", celula: acoes },
      ],
      linhas: itens,
      severidade: (a) => a.severidade,
      href: (a) => endereco("inspecoes", [a.analise_id]),
    });
    if (!animada) { animarEntrada([...t.querySelectorAll("tbody tr")]); animada = true; }
    corpo.replaceChildren(t);
  }

  function acoes(a) {
    const enviar = botao({ texto: A.enviar, icone: "externo", compacto: true, onclick: () => enviarWhatsapp(a, enviar) });
    const resolver = botao({ texto: A.resolver, icone: "check", variante: "fantasma", compacto: true, onclick: () => mudar(a, "resolvido", true) });
    return el("div", { class: "acoes-linha" }, a.status === "resolvido" ? null : enviar, a.status === "resolvido" ? null : resolver);
  }

  async function enviarWhatsapp(a, gatilho) {
    let r;
    try { r = await api(`/api/alertas/${a.id}/whatsapp`); } catch (e) { avisar(e.message, { erro: true }); return; }
    if (!r.links.length) { avisar(A.semResponsavel, { erro: true }); return; }
    const abrir = (l) => { window.open(l.url, "_blank", "noopener"); if (a.status === "pendente") mudar(a, "enviado"); };
    if (r.links.length === 1) { abrir(r.links[0]); return; }
    const b = gatilho.getBoundingClientRect();
    menu(gatilho, [{ grupo: A.para }, ...r.links.map((l) => ({ texto: `${l.nome} (${l.telefone})`, executar: () => abrir(l) }))], { em: { x: b.left, y: b.bottom }, descartar: true });
  }

  async function mudar(a, status, comDesfazer = false) {
    const antes = a.status;
    try {
      await api(`/api/alertas/${a.id}`, json("PUT", { status }));
      alertas = alertas.map((x) => (x.id === a.id ? { ...x, status } : x));
      desenhar();
      if (comDesfazer) avisar(A.mudou(A.status[status]), { acao: { rotulo: T.geral.desfazer, executar: () => mudar({ ...a, status }, antes) } });
    } catch (e) { avisar(e.message, { erro: true }); }
  }
  return null;
}
