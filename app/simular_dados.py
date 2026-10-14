"""Script de simulação: alimenta o banco de dados do Pyron com casos realistas.

Gera subestações, equipamentos (transformadores, disjuntores, para-raios), séries temporais
de inspeções com medições térmicas (regiões, delta T, % da MTA), alertas de monitoramento,
pendências de manutenção com ordens de serviço e catálogo de arquivos com hashes SHA-256.

Uso:
    python -m app.simular_dados
    python -m app.simular_dados --pasta app/dados_app --inspecoes 15
"""

from __future__ import annotations

import argparse
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from app.armazenamento import Armazenamento
from nucleo import analise, referencias

SUBESTACOES = [
    ("SE Campina Grande II", ["TR-01 (Transformador 230/69 kV)", "DJ-02 (Disjuntor 230 kV)", "PR-01 (Para-raios Fase A)"]),
    ("SE Santa Rita Norte", ["TR-02 (Transformador 69/13.8 kV)", "SEC-03 (Seccionadora)", "PR-02 (Para-raios Fase B)"]),
    ("SE Patos Oeste", ["BANCO-CAP-01 (Banco de Capacitores)", "TR-03 (Autotransformador 500 kV)"]),
]

CLASSES_COMPONENTE = [
    ("conexao", "Conexão", 90.0, "resistivo"),
    ("terminal_superior", "Terminal Superior", 90.0, "resistivo"),
    ("terminal_inferior", "Terminal Inferior", 90.0, "resistivo"),
    ("bucha", "Bucha Fase A", 95.0, "resistivo"),
    ("para_raio", "Corpo Para-raios", None, "dieletrico"),
    ("tanque", "Tanque Principal", 100.0, "oleo"),
]

SEVERIDADES = ["normal", "atencao", "programar", "urgente", "imediato"]


def gerar_matriz_termica(h: int = 120, w: int = 160, t_base: float = 30.0, ponto_quente: float | None = None) -> np.ndarray:
    """Gera matriz com ruído térmico realista e opcionalmente um ponto quente gaussiano."""
    matriz = np.random.normal(loc=t_base, scale=1.5, size=(h, w)).astype(np.float32)
    if ponto_quente:
        cx, cy = random.randint(30, w - 30), random.randint(20, h - 20)
        y, x = np.ogrid[:h, :w]
        dist2 = (x - cx) ** 2 + (y - cy) ** 2
        gauss = np.exp(-dist2 / (2 * 12.0 ** 2))
        matriz += (ponto_quente - t_base) * gauss
    return matriz


def simular_banco(pasta_dados: Path, quantidade_inspecoes: int = 12):
    pasta_dados = Path(pasta_dados)
    arm = Armazenamento(pasta_dados)
    agora = datetime.now()

    print(f"Iniciando simulação em: {pasta_dados.resolve()}")
    print(f"Gerando {quantidade_inspecoes} inspeções sintéticas com telemetria física...")

    inspecoes_geradas = 0
    alertas_gerados = 0

    for i in range(quantidade_inspecoes):
        subestacao, equipamentos_lista = random.choice(SUBESTACOES)
        equipamento = random.choice(equipamentos_lista)

        # Espalhar inspeções ao longo dos últimos 90 dias para criar série temporal
        dias_atras = random.randint(1, 90)
        data_captura = agora - timedelta(days=dias_atras, hours=random.randint(8, 17), minutes=random.randint(0, 59))
        data_str = data_captura.strftime("%Y-%m-%d %H:%M:%S")

        ambiente_c = round(random.uniform(22.0, 32.0), 1)
        carga_pct = round(random.uniform(50.0, 95.0), 1)

        # Escolher cenário de aquecimento
        prob_anomalia = random.random()
        if prob_anomalia < 0.35:
            # Ponto crítico / urgente
            t_max_alvo = random.uniform(85.0, 135.0)
            classe_alvo, nome_alvo, mta, aquec = random.choice(CLASSES_COMPONENTE[:3])
        elif prob_anomalia < 0.65:
            # Atenção / Programar
            t_max_alvo = random.uniform(55.0, 78.0)
            classe_alvo, nome_alvo, mta, aquec = random.choice(CLASSES_COMPONENTE)
        else:
            # Normal
            t_max_alvo = ambiente_c + random.uniform(5.0, 18.0)
            classe_alvo, nome_alvo, mta, aquec = CLASSES_COMPONENTE[0]

        matriz = gerar_matriz_termica(120, 160, t_base=ambiente_c + 8.0, ponto_quente=t_max_alvo)

        # Montar regiões de detecção
        regioes_base = [
            {
                "id": uuid.uuid4().hex[:8],
                "nome": nome_alvo,
                "classe": classe_alvo,
                "caixa": [20.0, 15.0, 80.0, 75.0],
                "confianca": round(random.uniform(0.85, 0.98), 2),
                "origem": "modelo",
            },
            {
                "id": uuid.uuid4().hex[:8],
                "nome": "Terminal Adjacente (Fase B)",
                "classe": classe_alvo,
                "caixa": [85.0, 15.0, 145.0, 75.0],
                "confianca": round(random.uniform(0.85, 0.98), 2),
                "origem": "modelo",
            },
        ]

        # Executar cálculo termográfico com as regras da norma
        regioes_calculadas, resumo = analise.analisar_regioes(
            matriz, regioes_base, ambiente_c=ambiente_c, carga_pct=carga_pct
        )

        id_analise = uuid.uuid4().hex
        analise_payload = {
            "id": id_analise,
            "criado_em": data_captura.isoformat(timespec="seconds"),
            "arquivo": f"TERM_{subestacao[:4].upper()}_{i+1:03d}.jpg",
            "fonte": random.choice(["manual", "celular", "monitoramento"]),
            "radiometrica": True,
            "metadados": {
                "camera": random.choice(["FLIR C5", "FLIR T540", "FLIR E8-XT"]),
                "data_hora": data_str,
                "emissividade": 0.95,
                "distancia_m": round(random.uniform(2.5, 8.0), 1),
                "temp_refletida_c": 22.0,
                "temp_atmosfera_c": ambiente_c,
                "umidade_relativa": round(random.uniform(0.40, 0.75), 2),
                "resolucao_sensor": "160×120",
            },
            "modelo": {"nome": "pontos-quentes"},
            "condicoes": {"ambiente_c": ambiente_c, "carga_pct": carga_pct},
            "identificacao": {"instalacao": subestacao, "equipamento": equipamento},
            "regioes": regioes_calculadas,
            "resumo": resumo,
            "matriz_info": {"largura": 160, "altura": 120, "faixa_exibicao": [float(matriz.min()), float(matriz.max())]},
        }

        # Simular acompanhamento se tiver anomalia
        if resumo["severidade"] not in ("normal", "sem_medida", "nao_avaliado"):
            status_escolhido = random.choice(["aberta", "programada", "corrigida"])
            dias_prazo = 7 if resumo["severidade"] in ("urgente", "imediato") else 30
            prazo_dt = (data_captura + timedelta(days=dias_prazo)).date()
            analise_payload["acompanhamento"] = {
                "status": status_escolhido,
                "prazo": prazo_dt.isoformat(),
                "ordem_servico": f"OS-2026-{random.randint(1000, 9999)}",
                "responsavel": random.choice(["Carlos Silva (Eng. Eletricista)", "Mariana Costa", "Equipe Manutenção Sul"]),
                "nota": f"Inspeção periódica. Identificado aquecimento em {nome_alvo}.",
                "historico": [
                    {
                        "quando": data_captura.isoformat(timespec="seconds"),
                        "status": "aberta",
                        "nota": "Anomalia detectada pelo Pyron.",
                    }
                ],
            }

            # Gerar alerta para severidades altas
            if resumo["severidade"] in ("urgente", "imediato"):
                arm.salvar_alerta({
                    "id": uuid.uuid4().hex[:12],
                    "criado_em": data_captura.isoformat(timespec="seconds"),
                    "analise_id": id_analise,
                    "arquivo": analise_payload["arquivo"],
                    "severidade": resumo["severidade"],
                    "severidade_rotulo": resumo["severidade_rotulo"],
                    "resumo": resumo["mensagem"],
                    "mensagem": f"Ponto quente detectado em {equipamento} ({subestacao}): Tmáx {resumo['t_max_cena']:.1f} °C",
                    "instalacao": subestacao,
                    "equipamento": equipamento,
                    "status": random.choice(["pendente", "enviado", "resolvido"]),
                })
                alertas_gerados += 1

        # Salva gerando arquivos binários fictícios (original JPEG e matriz .npy)
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 2048 + b"\xff\xd9"
        arm.salvar(analise_payload, original=fake_jpeg, matriz=matriz)
        inspecoes_geradas += 1

    print("\nSimulação concluída com sucesso!")
    print(f"-> {inspecoes_geradas} novas análises inseridas e normalizadas.")
    print(f"-> {alertas_gerados} alertas registrados.")


def imprimir_resumo_banco(pasta_dados: Path):
    import sqlite3
    banco = Path(pasta_dados) / "inspecoes.sqlite"
    c = sqlite3.connect(banco)
    print("\n" + "=" * 60)
    print(f"ESTADO ATUAL DO BANCO ({banco})")
    print("=" * 60)

    tabelas = [
        "instalacoes",
        "equipamentos",
        "analises",
        "regioes",
        "parametros_medicao",
        "pendencias",
        "alertas",
        "arquivos",
    ]
    for t in tabelas:
        qtd = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  • Tabela {t:<22}: {qtd:>4} registros")

    print("\n--- EQUIPAMENTOS CADASTRADOS (View vw_equipamentos) ---")
    eqs = c.execute("SELECT instalacao, equipamento, inspecoes, maior_t_max_cena, maior_pct_mta FROM vw_equipamentos").fetchall()
    for inst, eq, total, tmax, pct in eqs:
        tmax_str = f"{tmax:.1f} °C" if tmax is not None else "-"
        pct_str = f"{pct:.0f}%" if pct is not None else "-"
        print(f"  [{inst}] {eq} -> {total} inspeções | Pico: {tmax_str} ({pct_str} MTA)")

    print("\n--- PENDÊNCIAS EM ABERTO / PROGRAMADAS ---")
    pends = c.execute("SELECT severidade, status, prazo, responsavel FROM pendencias LIMIT 5").fetchall()
    for sev, st, dt, resp in pends:
        print(f"  Severidade: {sev:<10} | Status: {st:<11} | Limite: {dt} | Responsável: {resp or 'Não atribuído'}")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Alimenta o banco de dados do Pyron com simulações.")
    parser.add_argument("--pasta", default="app/dados_app", help="Diretório dos dados do app.")
    parser.add_argument("--inspecoes", type=int, default=12, help="Quantidade de inspeções a simular.")
    args = parser.parse_args()

    simular_banco(Path(args.pasta), quantidade_inspecoes=args.inspecoes)
    imprimir_resumo_banco(Path(args.pasta))


if __name__ == "__main__":
    main()
