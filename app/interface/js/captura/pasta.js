// Captura › Pasta monitorada: a pasta onde a câmera grava, a regra do alerta e quem recebe (vem do time
// operacional, em Configurações › Empresa e time; aqui só se mostra). Cada mudança
// salva sozinha ("Salvo às …"); Ligar é o primário da aba. Com a pasta vigiada, o estado se atualiza a cada 5 s.
// Só a fonte que funciona aparece (pasta); RTSP, SDK e envio automático continuam fora até existirem.
import { TEXTOS as T } from "../../textos.js";
import { el, api, json, lerNumero, dataHora, relativa } from "../base.js";
import { botao, campo, marcar, segmentado, secao, avisar, ocupado } from "../componentes.js";
import { ilustracao } from "../ilustracoes.js";
import { endereco } from "../rotas.js";

const P = T.pasta;
const NIVEIS = ["atencao", "programar", "urgente", "imediato"];

export async function montar(no, { aoMudarEstado }) {
  const [dados, previa, equipamentos] = await Promise.all([
    api("/api/monitoramento"), api("/api/monitoramento/previa").catch(() => ({ mensagem: null })), api("/api/equipamentos").catch(() => []),
  ]);
  let cfg = dados.config;
  let estado = dados.estado;

  // ---------------------------------------------------------------- formulário (salva sozinho)
  const pasta = campo({ rotulo: P.pasta, valor: cfg.pasta, marcador: P.pastaMarcador, autocomplete: "off", spellcheck: "false", classe: "campo-caminho" });
  const intervalo = campo({ rotulo: P.intervalo, tipo: "number", valor: String(cfg.intervalo_s), unidade: "s" });
  const subpastas = marcar({ rotulo: P.subpastas, marcado: cfg.subpastas });
  const listaInst = el("datalist", { id: "pasta-instalacoes" }, [...new Set(equipamentos.map((e) => e.instalacao).filter(Boolean))].map((v) => el("option", { value: v })));
  const listaEquip = el("datalist", { id: "pasta-equipamentos" }, [...new Set(equipamentos.map((e) => e.equipamento).filter(Boolean))].map((v) => el("option", { value: v })));
  const instalacao = campo({ rotulo: P.instalacao, valor: cfg.instalacao, list: "pasta-instalacoes", autocomplete: "off" });
  const equipamento = campo({ rotulo: P.equipamento, valor: cfg.equipamento, list: "pasta-equipamentos", autocomplete: "off", ajuda: P.equipamentoAjuda });
  let minima = cfg.severidade_minima;
  const nivel = segmentado({ rotulo: P.minima, valor: minima, opcoes: NIVEIS.map((n) => ({ valor: n, texto: T.niveis[n] })), aoMudar: (v) => { minima = v; salvarDepois(); } });
  const repetir = campo({ rotulo: P.repetir, tipo: "number", valor: String(cfg.repetir_min), unidade: "min", ajuda: P.repetirAjuda });
  const responsaveis = el("ul", { class: "lista-recebe" });
  const erro = el("p", { class: "erro-dialogo", role: "alert", hidden: true });
  const salvo = el("span", { class: "estado-salvo", role: "status" });

  // quem recebe: nome, WhatsApp e a partir de que nível; quem pede menos que o monitor só recebe a partir do monitor
  function desenharResponsaveis() {
    const quem = cfg.destinatarios || [];
    const abaixo = (d) => NIVEIS.indexOf(d.minima) < NIVEIS.indexOf(minima);
    responsaveis.replaceChildren(...quem.map((d) => el("li", {}, el("b", {}, d.nome), el("span", { class: "mono" }, d.telefone),
      el("span", { class: "nota" }, abaixo(d) ? `${P.aPartirDe(T.niveis[d.minima])} (${P.abaixoDoMonitor})` : P.aPartirDe(T.niveis[d.minima])))));
    semResponsaveis.hidden = quem.length > 0;
  }
  const semResponsaveis = el("p", { class: "nota" }, P.semResponsaveis);
  const editarTime = el("a", { class: "btn compacto", href: endereco("configuracoes", ["empresa"]) }, P.editarTime);

  function lerFormulario() {
    return {
      pasta: pasta.querySelector("input").value.trim(),
      intervalo_s: Math.round(lerNumero(intervalo.querySelector("input").value) ?? cfg.intervalo_s),
      subpastas: subpastas.querySelector("input").checked,
      instalacao: instalacao.querySelector("input").value.trim(),
      equipamento: equipamento.querySelector("input").value.trim(),
      severidade_minima: minima,
      repetir_min: Math.round(lerNumero(repetir.querySelector("input").value) ?? cfg.repetir_min),
    };
  }

  let relogioSalvar = null;
  function salvarDepois(espera = 700) {
    clearTimeout(relogioSalvar);
    salvo.dataset.estado = "salvando";
    salvo.textContent = T.analise.salvando;
    relogioSalvar = setTimeout(() => salvar(lerFormulario()), espera);
  }
  async function salvar(corpo) {
    try {
      const r = await api("/api/monitoramento", json("PUT", corpo));
      cfg = r.config;
      estado = r.estado;
      erro.hidden = true;
      salvo.dataset.estado = "salvo";
      salvo.textContent = T.analise.salvoEm(new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }));
      desenharEstado();
      desenharResponsaveis();
      return true;
    } catch (e) {
      erro.textContent = e.message;
      erro.hidden = false;
      salvo.dataset.estado = "erro";
      salvo.textContent = T.analise.erroSalvar;
      return false;
    }
  }
  // salva ao sair do campo (texto) e na hora (caixa de marcar); digitando, espera parar
  no.addEventListener("input", (ev) => { if (ev.target.matches("input:not([type=checkbox]), textarea")) salvarDepois(); });
  no.addEventListener("change", (ev) => { if (ev.target.matches("input[type=checkbox]")) salvarDepois(0); });

  // ---------------------------------------------------------------- estado e ação principal
  const blocoEstado = el("section", { class: "bloco-estado", "aria-label": P.estado });
  function desenharEstado() {
    const ligado = cfg.ativo;
    const comErro = ligado && estado.erro;
    const pares = [
      [P.ultimaVerificacao, estado.ultima_verificacao ? `${dataHora(estado.ultima_verificacao)} (${relativa(estado.ultima_verificacao)})` : T.geral.semValor],
      [P.ultimaImagem, estado.ultima_imagem?.arquivo || T.geral.semValor],
      [P.analisadas, String(estado.analisadas || 0)],
      [P.alertasGerados, String(estado.alertas || 0)],
    ];
    const ligar = botao({ texto: P.ligar, icone: "captura", variante: "primario", onclick: () => ocupado(ligar, async () => {
      clearTimeout(relogioSalvar);
      if (await salvar({ ...lerFormulario(), ativo: true })) {
        estado = { ...estado, erro: null }; // o servidor acabou de aceitar a pasta: o erro guardado é de antes de ligar
        desenharEstado();
        avisar(P.ligado);
      }
      else pasta.querySelector("input").focus();
    }) });
    const desligar = botao({ texto: P.desligar, onclick: () => ocupado(desligar, async () => { if (await salvar({ ...lerFormulario(), ativo: false })) avisar(P.desligado); }) });
    const verificar = botao({ texto: P.verificar, icone: "refazer", onclick: () => ocupado(verificar, async () => {
      try {
        const r = await api("/api/monitoramento/verificar", { method: "POST" });
        estado = r.estado;
        desenharEstado();
        avisar(P.verificado(r.novas));
      } catch (e) { avisar(e.message, { erro: true }); }
    }) });
    blocoEstado.replaceChildren(...[
      // sem pasta definida: o desenho da câmera e a frase do que falta (estado vazio da aba)
      !ligado && !cfg.pasta ? el("div", { class: "vazio-fonte" }, ilustracao("captura", { rotulo: P.vazioTitulo }), el("p", {}, P.vazioTexto)) : null,
      el("div", { class: `linha-estado-fonte${ligado && !comErro ? " ligada" : comErro ? " erro" : ""}` }, el("i", { class: "ponto-estado", "aria-hidden": "true" }),
        el("b", {}, ligado ? (comErro ? P.comErro : P.vigiando) : P.desligadoEstado)),
      comErro ? el("p", { class: "erro-dialogo" }, estado.erro) : null,
      ligado ? el("p", { class: "mono corta", title: cfg.pasta }, cfg.pasta) : el("p", { class: "nota" }, P.desligadoTexto),
      el("dl", { class: "pares" }, pares.flatMap(([t, d]) => [el("dt", {}, t), el("dd", {}, d)])),
      el("div", { class: "grupo-btn" }, ...(ligado ? [verificar, desligar] : [ligar])),
    ].filter(Boolean));
    aoMudarEstado?.({ monitoramento: { ...estado, ativo: cfg.ativo } });
  }

  const blocoPrevia = previa.mensagem
    ? secao({ titulo: P.previa, aberta: false, conteudo: [el("p", { class: "nota" }, P.previaNota(previa.arquivo)), el("pre", { class: "previa-mensagem" }, previa.mensagem)] })
    : null;

  no.append(el("div", { class: "captura-grade" },
    el("div", { class: "coluna-form" },
      el("div", { class: "titulo-bloco" }, el("h2", {}, P.pastaTitulo), salvo),
      erro,
      el("div", { class: "grupo-campos" }, pasta, el("div", { class: "grade-campos-2" }, intervalo, el("div", { class: "campo-marcar" }, subpastas)),
        el("div", { class: "grade-campos-2" }, instalacao, equipamento), listaInst, listaEquip),
      el("div", { class: "titulo-bloco" }, el("h2", {}, P.alertaTitulo)),
      el("div", { class: "grupo-campos" },
        el("div", { class: "campo" }, el("span", { class: "rotulo", id: "rotulo-minima" }, P.minima), nivel),
        repetir,
        el("div", { class: "campo" }, el("span", { class: "rotulo" }, P.responsaveis), el("p", { class: "nota" }, P.responsaveisNota), semResponsaveis, responsaveis, el("div", {}, editarTime)))),
    el("div", { class: "coluna-lado" }, blocoEstado, blocoPrevia)));
  desenharEstado();
  desenharResponsaveis();

  // com a pasta vigiada, o estado anda sozinho (última verificação, analisadas, alertas)
  const relogio = setInterval(async () => {
    if (!cfg.ativo) return;
    try {
      const r = await api("/api/monitoramento");
      estado = r.estado;
      desenharEstado();
    } catch { /* a faixa de conexão já avisa */ }
  }, 5000);
  return () => { clearInterval(relogio); clearTimeout(relogioSalvar); };
}
