// Importação de termogramas a partir de qualquer tela (Ctrl+O, botão ou arrastar e soltar) e dos dados
// de demonstração. Uma imagem abre direto na inspeção; várias entram na lista. O progresso fica num lugar
// fixo no topo de Inspeções; nas outras telas, num aviso que dura até o fim.
import { TEXTOS as T } from "../textos.js";
import { el, api, json } from "./base.js";
import { avisar, dialogo } from "./componentes.js";
import { endereco } from "./rotas.js";

const I = T.importar;
const ACEITOS = /\.(jpe?g|png|webp|bmp)$/i;

/** Avisa a cada passo: detail = { ativa, i, n, nome, feitas, falhas }. */
export const importacao = new EventTarget();
let atual = null;
let telasComProgresso = 0;
let aviso = null;

export const estadoImportacao = () => atual && { ativa: true, i: atual.i, n: atual.n, nome: atual.nome, feitas: atual.feitas.length, falhas: atual.falhas.length };

/** A tela que mostra o progresso no próprio lugar chama isto ao montar e a função devolvida ao sair. */
export function mostrarProgressoNaTela() {
  telasComProgresso++;
  aviso?.fechar();
  aviso = null;
  return () => { telasComProgresso--; if (atual) avisarProgresso(); };
}

function avisarProgresso() {
  const texto = I.enviando(atual.i, atual.n);
  if (telasComProgresso) return;
  if (aviso) aviso.atualizar(texto);
  else aviso = avisar(texto, { duracao: 3600000 });
}

function notificar() {
  importacao.dispatchEvent(new CustomEvent("progresso", { detail: estadoImportacao() || { ativa: false } }));
}

export function escolherArquivos() {
  document.getElementById("arquivos").click();
}

/** Envia os arquivos um a um (o servidor analisa em fila); destino = { instalacao, equipamento } opcional. */
export function importar(arquivos, destino = {}) {
  const lista = [...arquivos];
  const validos = lista.filter((a) => ACEITOS.test(a.name));
  const recusados = lista.filter((a) => !validos.includes(a)).map((a) => ({ nome: a.name, motivo: I.formato }));
  const tarefas = validos.map((arquivo) => ({
    nome: arquivo.name,
    enviar: () => {
      const dados = new FormData();
      dados.append("arquivo", arquivo);
      for (const [k, v] of Object.entries(destino)) if (v) dados.append(k, v);
      return api("/api/analises", { method: "POST", body: dados });
    },
  }));
  return executar(tarefas, { recusados, abrirUnica: true });
}

/** Analisa algumas imagens do dataset de estudo (Painel e Inspeções vazios). */
export async function importarDemonstracao(quantas = 6) {
  const { itens } = await api("/api/exemplos");
  const tarefas = itens.slice(0, quantas).map((it) => ({ nome: it.nome, enviar: () => api(`/api/exemplos/${encodeURIComponent(it.nome)}/analisar`, json("POST", {})) }));
  return executar(tarefas, { abrirUnica: false });
}

async function executar(tarefas, { recusados = [], abrirUnica }) {
  if (atual) { // importação em andamento: os novos entram no fim da mesma fila
    atual.fila.push(...tarefas);
    atual.n += tarefas.length;
    atual.falhas.push(...recusados);
    notificar();
    return [];
  }
  if (!tarefas.length) { if (recusados.length) resumirFalhas(recusados); return []; }
  atual = { fila: [...tarefas], n: tarefas.length, i: 0, nome: "", feitas: [], falhas: [...recusados] };
  while (atual.fila.length) {
    const t = atual.fila.shift();
    atual.i++;
    atual.nome = t.nome;
    avisarProgresso();
    notificar();
    try {
      atual.feitas.push(await t.enviar());
    } catch (erro) {
      atual.falhas.push({ nome: t.nome, motivo: erro.message });
    }
  }
  const { feitas, falhas, n } = atual;
  atual = null;
  aviso?.fechar();
  aviso = null;
  notificar();
  if (falhas.length) resumirFalhas(falhas);
  if (feitas.length === 1 && n === 1 && abrirUnica) {
    location.hash = endereco("inspecoes", [feitas[0].id]);
    avisar(I.pronto(1, 1));
  } else if (feitas.length) {
    const naLista = location.hash.replace(/\?.*/, "") === endereco("inspecoes");
    avisar(I.pronto(feitas.length, n), naLista ? {} : { acao: { rotulo: I.verInspecoes, executar: () => { location.hash = endereco("inspecoes"); } } });
  }
  if (feitas.length) document.dispatchEvent(new CustomEvent("pyron:importadas", { detail: feitas }));
  return feitas;
}

/** Um aviso só para todas as falhas; "Ver" abre a lista com o motivo de cada arquivo. */
function resumirFalhas(falhas) {
  const ver = () => dialogo({
    titulo: I.falhasTitulo(falhas.length),
    corpo: [el("ul", { class: "lista-falhas" }, falhas.map((f) => el("li", {}, el("b", { class: "mono", title: f.nome }, f.nome), el("span", {}, f.motivo))))],
  }).abrir();
  avisar(falhas.length === 1 ? `${falhas[0].nome}: ${falhas[0].motivo}` : I.falhas(falhas.length), { erro: true, acao: falhas.length > 1 ? { rotulo: I.ver, executar: ver } : null });
}
