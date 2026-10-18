"""Testes para o exportador / ETL de SQLite para PostgreSQL."""

from pathlib import Path
import numpy as np

from app.armazenamento import Armazenamento
from app.exportar_postgres import ExportadorPostgres, uuid_estavel


def _analise(id_="exp1", sev="urgente", instalacao="SE Sul", equipamento="DJ-01"):
    return {
        "id": id_,
        "criado_em": "2026-10-01T10:00:00",
        "arquivo": f"{id_}.jpg",
        "fonte": "manual",
        "radiometrica": True,
        "metadados": {"camera": "FLIR C5", "data_hora": "2026-09-30 14:05:00", "emissividade": 0.95,
                      "distancia_m": 3.0, "temp_refletida_c": 20.0},
        "modelo": {"nome": "pontos-quentes"},
        "condicoes": {"ambiente_c": 25.0, "carga_pct": 80.0},
        "identificacao": {"instalacao": instalacao, "equipamento": equipamento},
        "regioes": [
            {"id": "r1", "nome": "Conexão A", "classe": "conexao", "caixa": [1, 2, 10, 12], "origem": "modelo",
             "confianca": 0.95, "medida": {"t_max": 85.0, "t_med": 55.0, "t_min": 35.0, "x_max": 5, "y_max": 6, "pixels": 50},
             "dt_corrigido": 20.0, "pct_mta": 94.4, "severidade": sev},
        ],
        "resumo": {"severidade": sev, "t_max_cena": 85.0, "t_min_cena": 20.0, "maior_pct_mta": 94.4, "mensagem": "Alerta térmico"},
    }


def test_uuid_estavel_deterministico():
    u1 = uuid_estavel("teste:123")
    u2 = uuid_estavel("teste:123")
    u3 = uuid_estavel("teste:456")
    assert u1 == u2
    assert u1 != u3


def test_exportador_gera_sql_valido(tmp_path):
    pasta = tmp_path / "dados"
    arm = Armazenamento(pasta)
    arm.salvar(_analise(), original=b"x", matriz=np.zeros((2, 2)))
    arm.salvar_alerta({"id": "al1", "criado_em": "2026-10-01T10:00:00", "status": "pendente",
                       "analise_id": "exp1", "severidade": "urgente", "mensagem": "Ponto quente"})

    exp = ExportadorPostgres(arm, empresa_padrao="Concessionária Alpha")
    sql = exp.gerar_script_sql()

    assert "BEGIN;" in sql and "COMMIT;" in sql
    assert "INSERT INTO empresas" in sql and "Concessionária Alpha" in sql
    assert "INSERT INTO catalogo_tipos_componente" in sql
    assert "INSERT INTO normas_tecnicas" in sql
    assert "INSERT INTO instalacoes" in sql and "SE Sul" in sql
    assert "INSERT INTO equipamentos" in sql and "DJ-01" in sql
    assert "INSERT INTO inspecoes_termograficas" in sql and "exp1" in sql
    assert "INSERT INTO deteccoes_regioes" in sql and "Conexão A" in sql
    assert "INSERT INTO pendencias_manutencao" in sql
    assert "INSERT INTO alertas" in sql and "al1" in sql

    saida = tmp_path / "dump.sql"
    bytes_gerados = exp.exportar_para_arquivo(saida)
    assert saida.exists() and bytes_gerados == len(sql)

