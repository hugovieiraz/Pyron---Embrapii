// Importação de termogramas a partir de qualquer tela (Ctrl+O, botão ou arrastar e soltar).
// Uma imagem abre direto na inspeção; várias entram na lista. A tela de Inspeções (Etapa 5a) refina o progresso.
import { TEXTOS as T } from "../textos.js";
import { api } from "./base.js";
import { avisar } from "./componentes.js";
import { endereco } from "./rotas.js";

const ACEITOS = /\.(jpe?g|png|webp|bmp)$/i;

export function escolherArquivos() {
  document.getElementById("arquivos").click();
}

/** Envia os arquivos um a um (o servidor analisa em fila); destino = { instalacao, equipamento } opcional. */
export async function importar(arquivos, destino = {}) {
  const lista = [...arquivos];
  const validos = lista.filter((a) => ACEITOS.test(a.name));
  for (const a of lista.filter((x) => !validos.includes(x))) avisar(T.importar.formato(a.name), { erro: true });
  if (!validos.length) return [];
  const progresso = avisar(T.importar.enviando(1, validos.length), { duracao: 3600000 });
  const feitas = [];
  for (const [i, arquivo] of validos.entries()) {
    progresso.atualizar(T.importar.enviando(i + 1, validos.length));
    const dados = new FormData();
    dados.append("arquivo", arquivo);
    for (const [k, v] of Object.entries(destino)) if (v) dados.append(k, v);
    try {
      feitas.push(await api("/api/analises", { method: "POST", body: dados }));
    } catch (erro) {
      avisar(T.importar.falhou(arquivo.name, erro.message), { erro: true });
    }
  }
  progresso.fechar();
  if (!feitas.length) return feitas;
  if (feitas.length === 1 && validos.length === 1) {
    location.hash = endereco("inspecoes", [feitas[0].id]);
    avisar(T.importar.pronto(1, 1));
  } else {
    avisar(T.importar.pronto(feitas.length, validos.length), { acao: { rotulo: T.importar.verInspecoes, executar: () => { location.hash = endereco("inspecoes"); } } });
  }
  document.dispatchEvent(new CustomEvent("pyron:importadas", { detail: feitas }));
  return feitas;
}
