// Tela provisória: ocupa a rota até a tela nova correspondente ser construída (Etapas 4 e 5).
import { TEXTOS as T } from "../../textos.js";
import { el } from "../base.js";
import { cabecalho, estadoVazio } from "../componentes.js";
import { ROTAS } from "../rotas.js";

const NA_ATUAL = { painel: "painel", inspecoes: "inspecoes", equipamentos: "equipamentos", pendencias: "pendencias", captura: "monitoramento", modelos: "modelos", configuracoes: "configuracoes" };

export function montar(pagina, rota) {
  const titulo = ROTAS[rota.tela].titulo;
  pagina.append(
    cabecalho({ titulo }),
    estadoVazio({
      icone: ROTAS[rota.tela].icone,
      titulo: T.provisoria.titulo,
      texto: T.provisoria.texto(titulo),
      acoes: [el("a", { class: "btn", href: `/#${NA_ATUAL[rota.tela]}` }, T.provisoria.abrirAtual)],
    }),
  );
}
