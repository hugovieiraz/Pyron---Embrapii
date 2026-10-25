// Dados de demonstração dos esboços (fictícios; nenhuma imagem do dataset de estudo).
const DADOS = {
  painel: {
    indicadores: [
      { id: "criticas", rotulo: "Críticas", valor: 2, nota: "urgente ou imediato", severidade: "urgente" },
      { id: "pendencias", rotulo: "Pendências vencidas", valor: 3, nota: "de 9 abertas", severidade: "programar" },
      { id: "inspecoes", rotulo: "Inspeções vencidas", valor: 4, nota: "de 18 equipamentos", severidade: "atencao" },
      { id: "alertas", rotulo: "Alertas", valor: 1, nota: "não lido", severidade: null },
    ],
    atencao: [
      { equipamento: "TR-01 69/13,8 kV", instalacao: "SE Campina Grande II", regiao: "Conexão X1", tmax: 96.4, criterio: "108 % da MTA", severidade: "imediato", data: "12/10/2026", pendencia: "Aberta, prazo 13/10", vencida: true },
      { equipamento: "Chave seccionadora CS-12", instalacao: "SE Bodocongó", regiao: "Contato fase B", tmax: 81.2, criterio: "ΔT 31,0 °C", severidade: "urgente", data: "08/10/2026", pendencia: "Programada, OS 4471", vencida: false },
      { equipamento: "Disjuntor DJ-52", instalacao: "SE Campina Grande II", regiao: "Terminal superior", tmax: 67.5, criterio: "75 % da MTA", severidade: "programar", data: "02/10/2026", pendencia: "Aberta, prazo 01/11", vencida: false },
      { equipamento: "Pátio 69 kV, bay 02", instalacao: "SE Campina Grande II", regiao: "Grampo de linha", tmax: 58.9, criterio: "ΔT 14,2 °C", severidade: "programar", data: "28/09/2026", pendencia: "Aberta, prazo 28/10", vencida: false },
      { equipamento: "TP-03 69 kV", instalacao: "SE Bodocongó", regiao: "Bucha H1", tmax: 41.3, criterio: "ΔT 5,8 °C", severidade: "atencao", data: "25/09/2026", pendencia: "Aberta, prazo 24/12", vencida: false },
      { equipamento: "Banco de capacitores BC-1", instalacao: "SE Mirante", regiao: "Fusível fase C", tmax: 39.8, criterio: "ΔT 4,9 °C", severidade: "atencao", data: "19/09/2026", pendencia: "Aberta, prazo 18/12", vencida: false },
    ],
    proximas: [
      { equipamento: "Para-raios PR-07", instalacao: "SE Mirante", data: "12/09/2026", atraso: "vencida há 43 dias" },
      { equipamento: "TR-02 69/13,8 kV", instalacao: "SE Campina Grande II", data: "30/09/2026", atraso: "vencida há 25 dias" },
      { equipamento: "Religador RL-3", instalacao: "SE Bodocongó", data: "03/11/2026", atraso: "em 9 dias" },
      { equipamento: "Barramento 13,8 kV", instalacao: "SE Mirante", data: "15/11/2026", atraso: "em 21 dias" },
      { equipamento: "Chave CS-08", instalacao: "SE Bodocongó", data: "22/11/2026", atraso: "em 28 dias" },
    ],
    estados: [
      { severidade: "imediato", n: 1 }, { severidade: "urgente", n: 1 }, { severidade: "programar", n: 3 },
      { severidade: "atencao", n: 4 }, { severidade: "normal", n: 9 },
    ],
  },
  analise: {
    arquivo: "TR01_20261012_0931.jpg",
    equipamento: "TR-01 69/13,8 kV",
    instalacao: "SE Campina Grande II",
    data: "12/10/2026 09:31",
    camera: "FLIR T540",
    posicao: [3, 5],
    severidade: "imediato",
    tmaxCena: 96.4,
    ambiente: 31.0,
    carga: 74,
    regioes: [
      { id: "r1", nome: "Conexão X1", classe: "Conexão", fase: "A", caixa: [86, 30, 114, 58], tmax: 96.4, dt: 50.6, mta: 108, severidade: "imediato", acao: "Corrigir imediatamente; reinspecionar após o reparo.", criterio: "Tmáx projetada para plena carga acima da MTA (90 °C)" },
      { id: "r2", nome: "Conexão X2", classe: "Conexão", fase: "B", caixa: [146, 28, 174, 56], tmax: 45.8, dt: 0.4, mta: 51, severidade: "normal" },
      { id: "r3", nome: "Conexão X3", classe: "Conexão", fase: "C", caixa: [206, 30, 234, 58], tmax: 45.4, dt: 0.0, mta: 50, severidade: "normal" },
      { id: "r4", nome: "Bucha X1", classe: "Bucha", fase: "A", caixa: [88, 58, 112, 150], tmax: 52.1, dt: 13.2, mta: 49, severidade: "programar", dimensoes: { altura: 1.22, largura: 0.31, metodo: "distância da câmera", referencia: "6,4 m" } },
      { id: "r5", nome: "Bucha X2", classe: "Bucha", fase: "B", caixa: [148, 56, 172, 148], tmax: 38.9, dt: 0.0, mta: 37, severidade: "normal" },
      { id: "r6", nome: "Bucha X3", classe: "Bucha", fase: "C", caixa: [208, 58, 232, 150], tmax: 39.3, dt: 0.4, mta: 37, severidade: "normal" },
      { id: "r7", nome: "Tanque", classe: "Tanque", fase: null, caixa: [40, 150, 280, 236], tmax: 33.6, dt: null, mta: 32, severidade: "normal" },
    ],
  },
};

const NIVEIS = { normal: "Normal", atencao: "Atenção", programar: "Programar", urgente: "Urgente", imediato: "Imediato" };

const fmt = (v, casas = 1) => (v == null ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }));
