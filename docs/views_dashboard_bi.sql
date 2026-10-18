-- =============================================================================
-- PYRON: VIEWS ESTRATÉGICAS PARA DASHBOARDS (BI / LOGÍSTICA / COMPRAS / ENGENHARIA)
-- Compatível com: PostgreSQL 14+ e SQLite (com sintaxe ANSI SQL universal)
-- Ferramentas compatíveis: Metabase (Open Source), Grafana, Power BI Desktop (Gratuito),
--                          Apache Superset (Open Source), DBeaver, Google Looker Studio
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. VIEW LOGÍSTICA E COMPRAS: Planejamento de aquisição de peças e cronograma de reparo
-- Informa: Equipamento, Subestação, Peça em falha, Severidade, Data Limite da Parada,
--          Ordem de Serviço (OS), Faixa de Aquisição (Lead Time) e Prioridade de Compra.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_logistica_suprimentos_reparos AS
SELECT
    p.id AS pendencia_id,
    p.status AS status_manutencao,
    p.ordem_servico_codigo AS ordem_servico,
    i.nome AS subestacao_instalacao,
    i.codigo_instalacao,
    e.nome AS equipamento,
    e.tag_codigo,
    e.tipo_equipamento,
    COALESCE(c.nome_exibicao, p.regiao_afetada, 'Componente Geral') AS peca_a_reparar_substituir,
    c.tipo_aquecimento,
    p.severidade,
    p.t_max_detectada_c,
    c.mta_padrao_c,
    ROUND(((p.t_max_detectada_c / NULLIF(c.mta_padrao_c, 0)) * 100)::numeric, 1) AS pct_mta_atingido,
    p.detectada_em::date AS data_deteccao,
    p.data_limite,
    (p.data_limite - CURRENT_DATE) AS dias_restantes_para_reparo,
    CASE 
        WHEN p.data_limite < CURRENT_DATE THEN 'VENCIDO - PARADA URGENTE'
        WHEN (p.data_limite - CURRENT_DATE) <= 7 THEN 'CRÍTICO - REQUER COMPRA IMEDIATA (ATÉ 7 DIAS)'
        WHEN (p.data_limite - CURRENT_DATE) <= 30 THEN 'PROGRAMAR COMPRA (PRÓXIMOS 30 DIAS)'
        WHEN (p.data_limite - CURRENT_DATE) <= 60 THEN 'PLANEJAMENTO TRIMESTRAL (31-60 DIAS)'
        ELSE 'ROTINA PREVENTIVA (> 60 DIAS)'
    END AS janela_logistica_prioridade,
    p.responsavel_nome AS equipe_responsavel,
    p.nota_tecnica
FROM pendencias_manutencao p
JOIN instalacoes i ON i.id = p.instalacao_id
JOIN equipamentos e ON e.id = p.equipamento_id
LEFT JOIN inspecoes_termograficas it ON it.id = p.inspecao_origem_id
LEFT JOIN deteccoes_regioes dr ON dr.inspecao_id = it.id AND dr.severidade_regiao = p.severidade
LEFT JOIN catalogo_tipos_componente c ON c.codigo_classe = dr.classe_componente
WHERE p.status IN ('aberta', 'programada')
ORDER BY p.data_limite ASC, p.t_max_detectada_c DESC;


-- -----------------------------------------------------------------------------
-- 2. VIEW DEMANDA DE PEÇAS E SOBRESSALENTES: Matriz para Compras e Estoque
-- Agrupa quantas peças de cada tipo precisam ser adquiridas por mês/trimestre
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_demanda_compras_pecas AS
SELECT
    COALESCE(c.nome_exibicao, 'Sobressalente Geral') AS tipo_peca_material,
    c.tipo_aquecimento,
    COUNT(p.id) AS total_pecas_necessarias,
    COUNT(CASE WHEN p.data_limite <= (CURRENT_DATE + INTERVAL '7 days') THEN 1 END) AS demanda_imediata_7d,
    COUNT(CASE WHEN p.data_limite > (CURRENT_DATE + INTERVAL '7 days') AND p.data_limite <= (CURRENT_DATE + INTERVAL '30 days') THEN 1 END) AS demanda_curto_prazo_30d,
    COUNT(CASE WHEN p.data_limite > (CURRENT_DATE + INTERVAL '30 days') THEN 1 END) AS demanda_medio_prazo,
    STRING_AGG(DISTINCT i.nome, ', ') AS subestacoes_destinatarias
FROM pendencias_manutencao p
JOIN instalacoes i ON i.id = p.instalacao_id
LEFT JOIN inspecoes_termograficas it ON it.id = p.inspecao_origem_id
LEFT JOIN deteccoes_regioes dr ON dr.inspecao_id = it.id AND dr.severidade_regiao = p.severidade
LEFT JOIN catalogo_tipos_componente c ON c.codigo_classe = dr.classe_componente
WHERE p.status IN ('aberta', 'programada')
GROUP BY c.nome_exibicao, c.tipo_aquecimento
ORDER BY total_pecas_necessarias DESC;


-- -----------------------------------------------------------------------------
-- 3. VIEW GESTÃO DE ENGENHARIA: Saúde dos Ativos e Risco Operacional
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_engenharia_saude_ativos AS
SELECT
    i.nome AS instalacao,
    e.nome AS equipamento,
    e.tipo_equipamento,
    COUNT(it.id) AS total_inspecoes,
    MAX(it.capturado_em) AS data_ultima_inspecao,
    MAX(it.t_max_cena_c) AS pico_temperatura_historico_c,
    MAX(it.delta_t_global_c) AS max_delta_t_registrado_c,
    (ARRAY_AGG(it.severidade ORDER BY it.capturado_em DESC))[1] AS severidade_estado_atual,
    COUNT(CASE WHEN p.status = 'aberta' THEN 1 END) AS pendencias_abertas,
    COUNT(CASE WHEN p.status = 'programada' THEN 1 END) AS pendencias_em_ordem_servico,
    COUNT(CASE WHEN p.status = 'corrigida' THEN 1 END) AS reparos_aguardando_reinspecao
FROM equipamentos e
JOIN instalacoes i ON i.id = e.instalacao_id
LEFT JOIN inspecoes_termograficas it ON it.equipamento_id = e.id
LEFT JOIN pendencias_manutencao p ON p.equipamento_id = e.id
GROUP BY i.nome, e.nome, e.tipo_equipamento
ORDER BY pico_temperatura_historico_c DESC NULLS LAST;


-- -----------------------------------------------------------------------------
-- 4. VIEW INDICADORES ESTRATÉGICOS (KPIs GERAIS)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_kpis_estrategicos_diretoria AS
SELECT
    (SELECT COUNT(*) FROM instalacoes) AS total_subestacoes_ativas,
    (SELECT COUNT(*) FROM equipamentos) AS total_ativos_monitorados,
    (SELECT COUNT(*) FROM inspecoes_termograficas) AS total_inspecoes_realizadas,
    (SELECT COUNT(*) FROM pendencias_manutencao WHERE status IN ('aberta', 'programada')) AS total_reparos_pendentes,
    (SELECT COUNT(*) FROM pendencias_manutencao WHERE status IN ('aberta', 'programada') AND data_limite < CURRENT_DATE) AS reparos_vencidos,
    (SELECT COUNT(*) FROM pendencias_manutencao WHERE status IN ('aberta', 'programada') AND (data_limite - CURRENT_DATE) <= 7) AS reparos_urgencia_7_dias,
    (SELECT COUNT(*) FROM alertas WHERE status = 'pendente') AS alertas_nao_atendidos;

