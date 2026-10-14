"""Exportador / ETL: extrai dados do SQLite local (esquema v2) para PostgreSQL ou script SQL.

Gera comandos SQL (INSERT ... ON CONFLICT) ou executa diretamente em conexão PostgreSQL
(via psycopg ou asyncpg se disponíveis).

Uso via linha de comando:
    python -m app.exportar_postgres                      # Gera dump exportacao_pyron.sql
    python -m app.exportar_postgres --saida dump.sql     # Especifica arquivo de saída
    python -m app.exportar_postgres --url postgresql://usuario:senha@host:5432/pyron  # Aplica direto no Postgres
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

from app.armazenamento import Armazenamento
from nucleo import analise, referencias

NAMESPACE_PYRON = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # Namespace estável para UUID v5


def uuid_estavel(chave: str) -> str:
    """Gera UUID determinístico baseado no namespace e chave legada."""
    return str(uuid.uuid5(NAMESPACE_PYRON, str(chave)))


def escape_sql(valor) -> str:
    """Formata valor para literal SQL seguro."""
    if valor is None:
        return "NULL"
    if isinstance(valor, bool):
        return "TRUE" if valor else "FALSE"
    if isinstance(valor, (int, float)):
        return str(valor)
    if isinstance(valor, dict) or isinstance(valor, list):
        txt = json.dumps(valor, ensure_ascii=False)
        return "'" + txt.replace("'", "''") + "'::jsonb"
    txt = str(valor)
    return "'" + txt.replace("'", "''") + "'"


class ExportadorPostgres:
    def __init__(self, armazenamento: Armazenamento, empresa_padrao: str = "Empresa Padrão"):
        self.arm = armazenamento
        self.empresa_padrao = empresa_padrao
        self.empresa_id = uuid_estavel(f"empresa:{empresa_padrao}")

    def gerar_script_sql(self) -> str:
        """Produz os comandos SQL para preenchimento de todas as tabelas normalizadas."""
        linhas = [
            "-- =============================================================================",
            f"-- Dump gerado automaticamente pelo Pyron em {datetime.now().isoformat()}",
            "-- Compatível com PostgreSQL 16+ conforme arquitetura_banco_dados_pyron_cloud.md",
            "-- =============================================================================",
            "BEGIN;",
            "",
        ]

        # 1. Empresa padrão
        linhas.append("-- 1. Empresa")
        linhas.append(
            f"INSERT INTO empresas (id, nome) VALUES ({escape_sql(self.empresa_id)}, {escape_sql(self.empresa_padrao)}) "
            f"ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome;"
        )
        linhas.append("")

        # 2. Catálogo de tipos de componente (da biblioteca canônica)
        linhas.append("-- 2. Catálogo canônico de componentes")
        for codigo, info in referencias.COMPONENTES_PADRAO.items():
            linhas.append(
                f"INSERT INTO catalogo_tipos_componente (codigo_classe, nome_exibicao, tipo_aquecimento, mta_padrao_c, fonte) "
                f"VALUES ({escape_sql(codigo)}, {escape_sql(info['nome'])}, {escape_sql(info['aquecimento'])}, "
                f"{escape_sql(info.get('mta_c'))}, {escape_sql(info.get('fonte'))}) "
                f"ON CONFLICT (codigo_classe) DO UPDATE SET nome_exibicao = EXCLUDED.nome_exibicao, "
                f"tipo_aquecimento = EXCLUDED.tipo_aquecimento, mta_padrao_c = EXCLUDED.mta_padrao_c, fonte = EXCLUDED.fonte;"
            )
        linhas.append("")

        # 3. Norma padrão (NBR 15866)
        linhas.append("-- 3. Norma padrão")
        norma_id = uuid_estavel("norma:nbr15866")
        criterios_json = analise.CRITERIOS_PADRAO
        linhas.append(
            f"INSERT INTO normas_tecnicas (id, codigo_norma, descricao, criterios_padrao) "
            f"VALUES ({escape_sql(norma_id)}, 'NBR 15866', 'MTA e delta T entre semelhantes conforme ABNT NBR 15866', "
            f"{escape_sql(criterios_json)}) "
            f"ON CONFLICT (codigo_norma) DO UPDATE SET criterios_padrao = EXCLUDED.criterios_padrao;"
        )
        linhas.append("")

        # Conectar no SQLite para extrair instalações, equipamentos, análises e tabelas derivadas
        with self.arm._conexao() as c:
            # 4. Instalações
            linhas.append("-- 4. Instalações")
            insts = c.execute("SELECT id, chave, nome FROM instalacoes").fetchall()
            inst_uuid_map = {}
            for i_id, i_chave, i_nome in insts:
                u_id = uuid_estavel(f"instalacao:{i_chave}")
                inst_uuid_map[i_id] = u_id
                linhas.append(
                    f"INSERT INTO instalacoes (id, empresa_id, codigo_instalacao, nome) "
                    f"VALUES ({escape_sql(u_id)}, {escape_sql(self.empresa_id)}, {escape_sql(i_chave)}, {escape_sql(i_nome)}) "
                    f"ON CONFLICT (empresa_id, codigo_instalacao) DO UPDATE SET nome = EXCLUDED.nome;"
                )
            linhas.append("")

            # 5. Equipamentos
            linhas.append("-- 5. Equipamentos")
            eqs = c.execute("SELECT id, chave, instalacao_id, nome FROM equipamentos").fetchall()
            eq_uuid_map = {}
            for e_id, e_chave, e_inst_id, e_nome in eqs:
                u_id = uuid_estavel(f"equipamento:{e_chave}")
                eq_uuid_map[e_id] = u_id
                u_inst = inst_uuid_map.get(e_inst_id)
                if not u_inst:
                    # Instalação fantasma se não houver
                    u_inst = uuid_estavel("instalacao:sem-instalacao")
                    linhas.append(
                        f"INSERT INTO instalacoes (id, empresa_id, codigo_instalacao, nome) "
                        f"VALUES ({escape_sql(u_inst)}, {escape_sql(self.empresa_id)}, 'sem-instalacao', 'Geral') "
                        f"ON CONFLICT DO NOTHING;"
                    )
                linhas.append(
                    f"INSERT INTO equipamentos (id, instalacao_id, tag_codigo, nome, tipo_equipamento) "
                    f"VALUES ({escape_sql(u_id)}, {escape_sql(u_inst)}, {escape_sql(e_chave)}, {escape_sql(e_nome)}, 'componente') "
                    f"ON CONFLICT (instalacao_id, tag_codigo) DO UPDATE SET nome = EXCLUDED.nome;"
                )
            linhas.append("")

            # 6. Inspeções Termográficas
            linhas.append("-- 6. Inspeções Termográficas")
            ans = c.execute(
                "SELECT id, capturado_em, criado_em, equipamento_id, fonte, radiometrica, modelo, "
                "t_max_cena, t_min_cena, maior_pct_mta, ambiente_c, carga_pct, nome, severidade, dados "
                "FROM analises"
            ).fetchall()

            for a_row in ans:
                (a_id, capturado, criado, e_id, fonte, radiom, mod_nome,
                 t_max, t_min, pct_mta, amb, carga, arq_nome, sev, dados_json) = a_row
                u_inspecao = uuid_estavel(f"inspecao:{a_id}")
                u_eq = eq_uuid_map.get(e_id)

                if not u_eq:
                    # Garantir equipamento genérico
                    u_inst_geral = uuid_estavel("instalacao:sem-instalacao")
                    u_eq = uuid_estavel("equipamento:avulso")
                    linhas.append(
                        f"INSERT INTO instalacoes (id, empresa_id, codigo_instalacao, nome) "
                        f"VALUES ({escape_sql(u_inst_geral)}, {escape_sql(self.empresa_id)}, 'geral', 'Geral') "
                        f"ON CONFLICT DO NOTHING;"
                    )
                    linhas.append(
                        f"INSERT INTO equipamentos (id, instalacao_id, tag_codigo, nome, tipo_equipamento) "
                        f"VALUES ({escape_sql(u_eq)}, {escape_sql(u_inst_geral)}, 'avulso', 'Avulso', 'geral') "
                        f"ON CONFLICT DO NOTHING;"
                    )

                dados = json.loads(dados_json) if dados_json else {}
                resumo = dados.get("resumo") or {}
                meta = dados.get("metadados") or {}
                delta_t = (t_max - amb) if (t_max is not None and amb is not None) else None

                linhas.append(
                    f"INSERT INTO inspecoes_termograficas ("
                    f"id, codigo_legado, instalacao_id, equipamento_id, norma_id, capturado_em, criado_em, "
                    f"origem_captura, arquivo_original_nome, imagem_termica_uri, matriz_temperatura_uri, "
                    f"t_min_cena_c, t_max_cena_c, t_media_cena_c, t_referencia_c, delta_t_global_c, "
                    f"mta_aplicada_c, severidade, acoes_recomendadas, observacoes) VALUES ("
                    f"{escape_sql(u_inspecao)}, {escape_sql(a_id)}, "
                    f"(SELECT instalacao_id FROM equipamentos WHERE id = {escape_sql(u_eq)}), "
                    f"{escape_sql(u_eq)}, {escape_sql(norma_id)}, {escape_sql(capturado or criado)}, {escape_sql(criado)}, "
                    f"{escape_sql(fonte or 'upload_flir')}, {escape_sql(arq_nome)}, "
                    f"{escape_sql(f'imagens/{a_id}.jpg')}, {escape_sql(f'matrizes/{a_id}.npy')}, "
                    f"{escape_sql(t_min)}, {escape_sql(t_max)}, {escape_sql((t_max + t_min)/2 if (t_max and t_min) else None)}, "
                    f"{escape_sql(amb)}, {escape_sql(delta_t)}, {escape_sql(pct_mta)}, {escape_sql(sev)}, "
                    f"{escape_sql(resumo.get('mensagem'))}, {escape_sql('; '.join(resumo.get('avisos') or []))}) "
                    f"ON CONFLICT (codigo_legado) DO UPDATE SET severidade = EXCLUDED.severidade, "
                    f"t_max_cena_c = EXCLUDED.t_max_cena_c;"
                )

                # Parâmetros radiométricos
                par = c.execute("SELECT * FROM parametros_medicao WHERE analise_id = ?", (a_id,)).fetchone()
                if par:
                    linhas.append(
                        f"INSERT INTO parametros_radiometricos_flir ("
                        f"inspecao_id, modelo_camera, emissividade, distancia_m, temp_refletida_c, "
                        f"temp_atmosfera_c, umidade_relativa) VALUES ("
                        f"{escape_sql(u_inspecao)}, {escape_sql(par[1])}, {escape_sql(par[2])}, {escape_sql(par[3])}, "
                        f"{escape_sql(par[4])}, {escape_sql(par[5])}, {escape_sql(par[6])}) "
                        f"ON CONFLICT (inspecao_id) DO NOTHING;"
                    )

                # Regiões / Detecções
                regs = c.execute(
                    "SELECT ordem, regiao_id, classe, x0, y0, x1, y1, t_max, t_med, t_min, x_max, y_max, "
                    "dt_corrigido, confianca, severidade, nome FROM regioes WHERE analise_id = ? ORDER BY ordem",
                    (a_id,)
                ).fetchall()
                for r in regs:
                    u_reg = uuid_estavel(f"regiao:{a_id}:{r[0]}")
                    classe_canon = referencias.classe_da_biblioteca(r[2] or "componente")
                    linhas.append(
                        f"INSERT INTO deteccoes_regioes ("
                        f"id, inspecao_id, indice_regiao, classe_componente, rotulo_regiao, confianca_ml, "
                        f"bbox_x_min, bbox_y_min, bbox_x_max, bbox_y_max, t_min_c, t_max_c, t_media_c, "
                        f"delta_t_regiao_c, hotspot_x, hotspot_y, severidade_regiao) VALUES ("
                        f"{escape_sql(u_reg)}, {escape_sql(u_inspecao)}, {r[0]}, {escape_sql(classe_canon)}, "
                        f"{escape_sql(r[15] or classe_canon)}, {escape_sql(r[13])}, "
                        f"{escape_sql(r[3] or 0)}, {escape_sql(r[4] or 0)}, {escape_sql(r[5] or 0)}, {escape_sql(r[6] or 0)}, "
                        f"{escape_sql(r[9])}, {escape_sql(r[7])}, {escape_sql(r[8])}, {escape_sql(r[12])}, "
                        f"{escape_sql(r[10])}, {escape_sql(r[11])}, {escape_sql(r[14] or 'normal')}) "
                        f"ON CONFLICT (id) DO NOTHING;"
                    )

                # Pendências
                pend = c.execute(
                    "SELECT severidade, status, prazo, prazo_padrao, ordem_servico, responsavel, nota "
                    "FROM pendencias WHERE analise_id = ?", (a_id,)
                ).fetchone()
                if pend:
                    u_pend = uuid_estavel(f"pendencia:{a_id}")
                    linhas.append(
                        f"INSERT INTO pendencias_manutencao ("
                        f"id, inspecao_origem_id, instalacao_id, equipamento_id, responsavel_nome, "
                        f"severidade, regiao_afetada, t_max_detectada_c, detectada_em, prazo_padrao, "
                        f"data_limite, status, ordem_servico_codigo, nota_tecnica) VALUES ("
                        f"{escape_sql(u_pend)}, {escape_sql(u_inspecao)}, "
                        f"(SELECT instalacao_id FROM equipamentos WHERE id = {escape_sql(u_eq)}), "
                        f"{escape_sql(u_eq)}, {escape_sql(pend[5])}, {escape_sql(pend[0])}, "
                        f"{escape_sql('Geral')}, {escape_sql(t_max)}, {escape_sql(capturado or criado)}, "
                        f"{escape_sql(bool(pend[3]))}, {escape_sql(pend[2])}, {escape_sql(pend[1])}, "
                        f"{escape_sql(pend[4])}, {escape_sql(pend[6])}) "
                        f"ON CONFLICT (id) DO NOTHING;"
                    )

            linhas.append("")

            # 7. Alertas
            linhas.append("-- 7. Alertas")
            als = c.execute("SELECT id, criado_em, status, analise_id, severidade, dados FROM alertas").fetchall()
            for al_id, al_criado, al_status, al_analise_id, al_sev, al_dados_json in als:
                u_alerta = uuid_estavel(f"alerta:{al_id}")
                u_insp = uuid_estavel(f"inspecao:{al_analise_id}") if al_analise_id else None
                al_dados = json.loads(al_dados_json) if al_dados_json else {}
                msg = al_dados.get("mensagem") or al_dados.get("resumo") or "Alerta térmico"
                linhas.append(
                    f"INSERT INTO alertas ("
                    f"id, codigo_legado, inspecao_id, equipamento_id, severidade, temperatura_excedida_c, "
                    f"status, mensagem_formatada, criado_em) VALUES ("
                    f"{escape_sql(u_alerta)}, {escape_sql(al_id)}, {escape_sql(u_insp)}, "
                    f"(SELECT equipamento_id FROM inspecoes_termograficas WHERE id = {escape_sql(u_insp)}), "
                    f"{escape_sql(al_sev or 'urgente')}, 0.0, {escape_sql(al_status or 'pendente')}, "
                    f"{escape_sql(msg)}, {escape_sql(al_criado)}) "
                    f"ON CONFLICT (codigo_legado) DO NOTHING;"
                )

        linhas.append("")
        linhas.append("COMMIT;")
        return "\n".join(linhas) + "\n"

    def exportar_para_arquivo(self, caminho_arquivo: Path) -> int:
        caminho_arquivo = Path(caminho_arquivo)
        sql = self.gerar_script_sql()
        caminho_arquivo.write_text(sql, encoding="utf-8")
        return len(sql)


def main():
    parser = argparse.ArgumentParser(description="Exporta dados do SQLite Pyron para PostgreSQL.")
    parser.add_argument("--saida", default="exportacao_pyron.sql", help="Arquivo SQL de saída.")
    parser.add_argument("--dados", default="app/dados_app", help="Pasta dados_app com inspecoes.sqlite.")
    parser.add_argument("--url", help="URL do PostgreSQL para ingestão direta (ex: postgresql://...).")
    args = parser.parse_args()

    arm = Armazenamento(Path(args.dados))
    exp = ExportadorPostgres(arm)
    saida = Path(args.saida)
    bytes_gerados = exp.exportar_para_arquivo(saida)
    print(f"Exportação gerada com sucesso em: {saida.resolve()} ({bytes_gerados} bytes)")

    if args.url:
        try:
            import psycopg
            print(f"Conectando ao PostgreSQL em {args.url}...")
            with psycopg.connect(args.url) as conn:
                with conn.cursor() as cur:
                    cur.execute(saida.read_text(encoding="utf-8"))
                conn.commit()
            print("Dados aplicados no PostgreSQL com sucesso!")
        except ImportError:
            print("Aviso: 'psycopg' não está instalado no ambiente para conexão direta.")
            print(f"Execute o arquivo {saida} manualmente no seu cliente PostgreSQL (ex: psql -d <url> -f {saida}).")


if __name__ == "__main__":
    main()

