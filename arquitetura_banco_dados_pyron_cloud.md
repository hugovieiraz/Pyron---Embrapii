# Arquitetura de Dados e Modelagem Relacional em Nuvem — Sistema Pyron (EMBRAPII)

## 1. Diagnóstico da Persistência Atual vs. Arquitetura em Nuvem

Na arquitetura atual do repositório [Pyron---Embrapii](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Ftree%2Fmain), documentada em [CLAUDE.md](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2FCLAUDE.md) e implementada em [app/armazenamento.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Farmazenamento.py), o sistema opera de forma monolítica local (Edge/Desktop na porta `8765`) combinando um banco SQLite (`inspecoes.sqlite`) com múltiplos diretórios locais (`dados/` e `dados_app/`).

### Principais Gargalos de Engenharia de Dados no Modelo Atual

* **Anti-padrão de "JSON Blob" em Tabelas Críticas**: Em [app/armazenamento.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Farmazenamento.py), as tabelas `analises` e `alertas` possuem apenas `id`, `criado_em`, `severidade`/`status` e uma coluna textual `dados` contendo todo o payload JSON gerado por [nucleo/analise.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fnucleo%2Fanalise.py). Isso impede índices compostos em métricas térmicas ($\Delta T$, $T_{máx}$, emissividade) e inviabiliza queries analíticas diretas por componente ou subestação.
* **Entidades de Domínio Calculadas em Memória (Sem Integridade Referencial)**: O cadastro e o histórico de ativos em [app/equipamentos.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Fequipamentos.py) (agrupados pela chave composta `instalacao:equipamento`) e a gestão de ordens de serviço em [app/pendencias.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Fpendencias.py) são reconstruídos dinamicamente em memória a partir da leitura e desserialização das linhas de `analises` e `alertas`. Mudanças de grafia no nome de uma instalação ou equipamento quebram o histórico da série temporal.
* **Estado de Jobs e Telemetria Dispersos em Arquivos Locais**: O acompanhamento de vídeos em [app/videos.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Fvideos.py) (`estado.json` e `quadros.jsonl`), o treinamento de modelos em [app/treinos.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Ftreinos.py) (`pedido.json`, `progresso.json`, `registro.txt`) e os pacotes de avaliação em [app/avaliacoes.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Favaliacoes.py) (`meta.json`, `resumo.json`) residem no sistema de arquivos local, sem controle transacional (ACID) nem concorrência multiusuário.
* **Acoplamento entre Metadados Estruturados e Binários Pesados**: Matrizes radiométricas NumPy (`{id}.npy`) extraídas via [nucleo/flir.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fnucleo%2Fflir.py), imagens anotadas (`{id}.jpg`, `{id}_foto.jpg`), frames de vídeo (`quadros/NNNNN.jpg`) e pesos de redes neurais (`modelo.onnx`) precisam ser desacoplados do banco relacional e movidos para Object Storage em nuvem.

| Domínio / Módulo no Código | Persistência Local Atual | Destino na Arquitetura em Nuvem |
| :--- | :--- | :--- |
| **Ativos e Subestações** ([app/equipamentos.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Fequipamentos.py)) | Gerado em memória via chave `instalacao:equipamento` extraída do JSON | Tabelas mestre `instalacoes`, `equipamentos` e `equipamento_regioes` (PostgreSQL) |
| **Análises e Termogramas** ([app/armazenamento.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Farmazenamento.py), [nucleo/analise.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fnucleo%2Fanalise.py)) | Tabela `analises` no `inspecoes.sqlite` (coluna texto `dados`) | Tabelas estruturadas `inspecoes_termograficas`, `parametros_radiometricos_flir` e `deteccoes_regioes` |
| **Matrizes e Imagens** ([nucleo/flir.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fnucleo%2Fflir.py)) | Disco local: `imagens/{id}.jpg`, `{id}_foto.jpg`, `matrizes/{id}.npy` | Object Storage (S3 / GCS / Azure Blob) particionado por data/subestação + URIs no banco |
| **Normas e Limiares** ([nucleo/referencias.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fnucleo%2Freferencias.py)) | Dicionários hardcoded (`COMPONENTES_PADRAO`, faixas de $\Delta T$) | Tabelas versionadas `normas_tecnicas` e `regras_severidade_componente` |
| **Alertas e Manutenção** ([app/pendencias.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Fpendencias.py)) | Tabela `alertas` (`inspecoes.sqlite`) + cálculo dinâmico de prazos | Tabelas transacionais `alertas`, `pendencias_manutencao` e `historico_pendencias` |
| **Laudos Técnicos** ([app/laudo.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Flaudo.py)) | Geração efêmera (`RT-YYYYMMDD-{HASH}`) sem catálogo persistente | Tabelas `laudos_tecnicos` e `laudo_inspecoes` + PDF assinado no Object Storage |
| **Vídeos e Streaming Mobile** ([app/videos.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Fvideos.py), [app/celular.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Fcelular.py)) | `estado.json`, `quadros.jsonl` e `quadros/NNNNN.jpg` + estado em RAM | Tabela `sessoes_video` + Hypertable TimescaleDB `telemetria_quadros_video` |
| **MLOps: Treinos e Avaliações** ([app/treinos.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Ftreinos.py), [app/avaliacoes.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Favaliacoes.py)) | `pedido.json`, `progresso.json`, `meta.json`, `resumo.json`, `.onnx` | Tabelas `modelos_ml`, `treinos_ml`, `treinos_metricas_epoca` e `avaliacoes_ml` |

## 2. Decisões Arquiteturais de Nuvem (Visão Senior Data Engineer)

1. **Motor Relacional Unificado (PostgreSQL 16+ com TimescaleDB)**:
   * **Dados Cadastrais e Transacionais (OLTP)**: Hierarquia de ativos elétricos, inspeções, laudos, alertas e workflow de pendências com integridade referencial estrita (chaves estrangeiras, constraints de validação física e auditoria).
   * **Séries Temporais de Alta Frequência (TimescaleDB)**: Os registros quadro a quadro hoje gravados em `quadros.jsonl` ([app/videos.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Fvideos.py)) e os streams em tempo real do [app/celular.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Fcelular.py) são modelados como *hypertables* particionadas automaticamente por tempo, permitindo agregar curvas de aquecimento (`time_bucket`) sem degradar o banco transacional.
   * **Flexibilidade Controlada com `JSONB`**: Colunas `JSONB` indexadas via GIN são reservadas exclusivamente para metadados extensíveis de fabricantes de câmeras ou métricas brutas por classe do Colab, enquanto todas as grandezas físicas e chaves de negócio viram colunas tipadas de primeira classe.
2. **Padrão Claim-Check para Binários e Matrizes Térmicas (Object Storage)**:
   * **Nunca armazenar blobs (`BYTEA`) pesados no banco relacional**. As matrizes térmicas `temperatura_c` e `bruto` ([nucleo/flir.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fnucleo%2Fflir.py)), as imagens térmicas/visíveis, os vídeos e os pesos `.onnx` devem ser salvos em Object Storage (Amazon S3, Google Cloud Storage ou Azure Data Lake Storage Gen2) com estrutura padronizada de prefixos:
     * `s3://pyron-prod-storage/termogramas/ano=YYYY/mes=MM/instalacao={id}/{inspecao_id}_termica.jpg`
     * `s3://pyron-prod-storage/matrizes/ano=YYYY/mes=MM/instalacao={id}/{inspecao_id}.parquet` (ou `.npy.zst` comprimido com Zstandard)
     * `s3://pyron-prod-storage/modelos/{modelo_id}/modelo.onnx`
   * O banco de dados armazena a URI imutável, o hash `SHA-256` de integridade e as dimensões/tamanho em bytes.
3. **Sincronização Edge-to-Cloud (Offline-First nas Subestações)**:
   * Como o Pyron frequentemente roda em campo via lançador desktop ([lancador/Pyron.cs](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Ftree%2Fmain)) ou em subestações com conectividade intermitente, todas as tabelas utilizam chaves primárias `UUID` (v7, ordenáveis no tempo) geradas na borda (Edge) e colunas de sincronização (` criacao_borda_em`, `sincronizado_nuvem_em`, `dispositivo_origem_id`). Isso permite que o SQLite local continue operando como buffer offline e sincronize via API/fila assíncrona sem colisão de IDs.

## 3. DDL Completo do Banco de Dados Estruturado (PostgreSQL + TimescaleDB)

```sql
-- =============================================================================
-- EXTENSÕES NECESSÁRIAS
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
-- Opcional mas altamente recomendado para séries temporais de vídeo e evolução térmica:
-- CREATE EXTENSION IF NOT EXISTS "timescaledb";

-- =============================================================================
-- 1. ENUMS E DOMÍNIOS DE NEGÓCIO (Alinhados com nucleo/analise.py e app/pendencias.py)
-- =============================================================================
CREATE TYPE tipo_severidade AS ENUM (
    'sem_medida',
    'nao_avaliado',
    'normal',
    'atencao',
    'programar',
    'urgente',
    'imediato'
);

CREATE TYPE tipo_referencia_delta_t AS ENUM (
    'semelhantes',
    'entorno',
    'ambiente'
);

CREATE TYPE status_alerta AS ENUM (
    'pendente',
    'enviado',
    'resolvido'
);

CREATE TYPE status_pendencia AS ENUM (
    'aberta',
    'programada',
    'corrigida',
    'verificada',
    'descartada'
);

CREATE TYPE status_job_processamento AS ENUM (
    'na_fila',
    'executando',
    'processando',
    'concluido',
    'erro',
    'cancelado'
);

CREATE TYPE modo_processamento_video AS ENUM (
    'ao_vivo',
    'intervalo'
);

-- =============================================================================
-- 2. CADASTRO MESTRE: EMPRESAS, INSTALAÇÕES, NORMAS E EQUIPAMENTOS
-- Substitui o agrupamento dinâmico em memória de app/equipamentos.py
-- =============================================================================
CREATE TABLE empresas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome VARCHAR(255) NOT NULL,
    cnpj VARCHAR(20) UNIQUE,
    logo_storage_uri TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE usuarios_responsaveis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id UUID REFERENCES empresas(id) ON DELETE RESTRICT,
    nome VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    cargo VARCHAR(120),
    registro_crea VARCHAR(60), -- Usado na emissão de laudos em app/laudo.py
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE instalacoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id UUID NOT NULL REFERENCES empresas(id) ON DELETE RESTRICT,
    codigo_instalacao VARCHAR(100) NOT NULL, -- Ex.: sigla da subestação
    nome VARCHAR(255) NOT NULL,
    subestacao VARCHAR(255),
    setor VARCHAR(150),
    ambiente VARCHAR(100), -- Ex.: interno, externo/tempo, abrigado
    latitude NUMERIC(9, 6),
    longitude NUMERIC(9, 6),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, codigo_instalacao)
);

-- Catálogo de componentes e limites térmicos (baseado em nucleo/referencias.py)
CREATE TABLE normas_tecnicas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo_norma VARCHAR(80) UNIQUE NOT NULL, -- Ex.: 'NBR 15866', 'IEEE 1458', 'NETA MTS'
    descricao TEXT NOT NULL,
    versao VARCHAR(40),
    criterios_padrao JSONB NOT NULL DEFAULT '{}'::JSONB, -- Faixas de severidade do critério
    ativa BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE catalogo_tipos_componente (
    codigo_classe VARCHAR(80) PRIMARY KEY, -- Ex.: 'bucha', 'cabo', 'conexao', 'para_raio', 'tanque', 'radiador'
    nome_exibicao VARCHAR(150) NOT NULL,
    tipo_aquecimento VARCHAR(80), -- 'resistivo', 'dieletrico', 'oleo'
    mta_padrao_c NUMERIC(6, 2), -- Ex.: 90.0, 95.0, 70.0, 100.0 ou NULL para para_raio/isolador
    fonte TEXT -- Referência normativa ou prática (ex.: IEC 62271-1, NBR 5410)
);

CREATE TABLE equipamentos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instalacao_id UUID NOT NULL REFERENCES instalacoes(id) ON DELETE RESTRICT,
    tag_codigo VARCHAR(120) NOT NULL, -- Identificador único na instalação (substitui chave instalacao:equipamento)
    nome VARCHAR(255) NOT NULL,
    tipo_equipamento VARCHAR(100) NOT NULL, -- Ex.: para-raios, disjuntor, seccionadora, transformador
    fabricante VARCHAR(150),
    modelo_fabricante VARCHAR(150),
    numero_serie VARCHAR(120),
    fase VARCHAR(20), -- Ex.: 'A', 'B', 'C', 'Trifásico'
    tensao_nominal_kv NUMERIC(8, 2),
    corrente_nominal_a NUMERIC(10, 2),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    metadados_extras JSONB NOT NULL DEFAULT '{}'::JSONB,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (instalacao_id, tag_codigo)
);

-- =============================================================================
-- 3. GOVERNANÇA DE MLOPS: MODELOS ONNX, TREINAMENTOS E AVALIAÇÕES
-- Estruturado a partir de app/treinos.py, app/avaliacoes.py e nucleo/detectores/
-- =============================================================================
CREATE TABLE modelos_ml (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_identificador VARCHAR(150) UNIQUE NOT NULL, -- Ex.: nome_saida do modelo
    arquitetura VARCHAR(80) NOT NULL, -- Ex.: 'RF-DETR', 'YOLOv8', 'ONNX'
    versao VARCHAR(50) NOT NULL,
    onnx_storage_uri TEXT NOT NULL, -- Caminho no Object Storage para modelo.onnx
    onnx_sha256 CHAR(64),
    tamanho_entrada_px INTEGER,
    classes_suportadas JSONB NOT NULL DEFAULT '[]'::JSONB,
    metricas_cartao JSONB NOT NULL DEFAULT '{}'::JSONB, -- Dados antes em cartao.json
    em_producao BOOLEAN NOT NULL DEFAULT FALSE,
    instalado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE treinos_ml (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo_externo VARCHAR(100) UNIQUE, -- Compatibilidade com ID de dados_app/treinos/<id>
    solicitado_por UUID REFERENCES usuarios_responsaveis(id),
    rotulo_arquivo_uri TEXT NOT NULL, -- URI do pacote CVAT no Object Storage (antes em dados/rotulos)
    modelo_base VARCHAR(150) NOT NULL,
    nome_saida VARCHAR(150) NOT NULL,
    epocas_total INTEGER NOT NULL,
    tamanho_imagem INTEGER NOT NULL,
    batch_size INTEGER NOT NULL,
    dispositivo VARCHAR(50) NOT NULL, -- Ex.: 'cuda', 'cpu'
    status status_job_processamento NOT NULL DEFAULT 'na_fila',
    epoca_atual INTEGER NOT NULL DEFAULT 0,
    porcentagem_conclusao NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
    perda_atual NUMERIC(10, 6),
    map50_atual NUMERIC(6, 4),
    tempo_decorrido_s INTEGER DEFAULT 0,
    tempo_restante_s INTEGER,
    mensagem_status TEXT,
    log_storage_uri TEXT, -- Substitui registro.txt local
    modelo_gerado_id UUID REFERENCES modelos_ml(id),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    iniciado_em TIMESTAMPTZ,
    finalizado_em TIMESTAMPTZ
);

-- Histórico época a época para curvas de aprendizado em nuvem
CREATE TABLE treinos_metricas_epoca (
    treino_id UUID NOT NULL REFERENCES treinos_ml(id) ON DELETE CASCADE,
    epoca INTEGER NOT NULL,
    perda_treino NUMERIC(10, 6),
    perda_validacao NUMERIC(10, 6),
    map50 NUMERIC(6, 4),
    map50_95 NUMERIC(6, 4),
    tempo_epoca_s NUMERIC(8, 2),
    registrado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (treino_id, epoca)
);

CREATE TABLE avaliacoes_ml (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo_externo VARCHAR(100) UNIQUE, -- Compatibilidade com dados_app/avaliacoes/<id>
    arquivo_pacote_uri TEXT NOT NULL,
    melhor_modelo_nome VARCHAR(150),
    map50_melhor NUMERIC(6, 4),
    total_fotos_teste INTEGER,
    gpu_utilizada VARCHAR(120),
    modelo_instalado_id UUID REFERENCES modelos_ml(id),
    modelos_avaliados JSONB NOT NULL DEFAULT '[]'::JSONB,
    resumo_metricas_classes JSONB NOT NULL DEFAULT '{}'::JSONB, -- Conteúdo de resumo.json
    figuras_storage_uris JSONB NOT NULL DEFAULT '[]'::JSONB, -- URIs das imagens .png
    tabelas_storage_uris JSONB NOT NULL DEFAULT '[]'::JSONB, -- URIs dos relatórios .csv
    importado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- 4. INSPEÇÕES TERMOGRÁFICAS, FÍSICA RADIOMÉTRICA FLIR E DETECÇÕES (CAIXAS)
-- Desnormalização estruturada de app/armazenamento.py, nucleo/analise.py e nucleo/flir.py
-- =============================================================================
CREATE TABLE inspecoes_termograficas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo_legado VARCHAR(100) UNIQUE, -- Mapeamento direto com analises.id do SQLite local
    instalacao_id UUID NOT NULL REFERENCES instalacoes(id) ON DELETE RESTRICT,
    equipamento_id UUID NOT NULL REFERENCES equipamentos(id) ON DELETE RESTRICT,
    inspetor_id UUID REFERENCES usuarios_responsaveis(id),
    modelo_ml_id UUID REFERENCES modelos_ml(id),
    norma_id UUID REFERENCES normas_tecnicas(id),

    -- Timestamps de captura, criação na borda e sincronização em nuvem
    capturado_em TIMESTAMPTZ NOT NULL, -- Extraído de metadados.data_hora
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sincronizado_nuvem_em TIMESTAMPTZ,
    origem_captura VARCHAR(40) NOT NULL DEFAULT 'upload_flir', -- 'upload_flir', 'celular_ao_vivo', 'video_frame'

    -- Referências para Object Storage (Substitui imagens/ e matrizes/ locais)
    arquivo_original_nome VARCHAR(255) NOT NULL,
    imagem_termica_uri TEXT NOT NULL, -- Substitui dados/imagens/{id}.jpg
    imagem_visivel_uri TEXT,          -- Substitui dados/imagens/{id}_foto.jpg
    matriz_temperatura_uri TEXT NOT NULL, -- Substitui dados/matrizes/{id}.npy
    matriz_largura_px INTEGER,
    matriz_altura_px INTEGER,

    -- Métricas térmicas globais da cena (nucleo/analise.py)
    -- Podem ser NULL em imagens sem dados radiométricos (ex.: fotos visíveis ou capturas sem escala)
    t_min_cena_c NUMERIC(6, 2),
    t_max_cena_c NUMERIC(6, 2),
    t_media_cena_c NUMERIC(6, 2),
    hotspot_global_x INTEGER,
    hotspot_global_y INTEGER,
    t_referencia_c NUMERIC(6, 2),
    tipo_referencia tipo_referencia_delta_t,
    delta_t_global_c NUMERIC(6, 2),
    mta_aplicada_c NUMERIC(6, 2),

    -- Diagnóstico consolidado
    severidade tipo_severidade NOT NULL,
    acoes_recomendadas TEXT,
    observacoes TEXT
);

-- Parâmetros radiométricos e constantes Planck extraídos por nucleo/flir.py (Relação 1:1 com inspeção)
CREATE TABLE parametros_radiometricos_flir (
    inspecao_id UUID PRIMARY KEY REFERENCES inspecoes_termograficas(id) ON DELETE CASCADE,
    modelo_camera VARCHAR(120),
    faixa_camera_min_c NUMERIC(6, 2),
    faixa_camera_max_c NUMERIC(6, 2),
    emissividade NUMERIC(5, 4) CHECK (emissividade > 0 AND emissividade <= 1.0),
    distancia_m NUMERIC(6, 2),
    temp_refletida_c NUMERIC(6, 2),
    temp_atmosfera_c NUMERIC(6, 2),
    temp_janela_c NUMERIC(6, 2),
    transmissao_janela NUMERIC(5, 4),
    umidade_relativa NUMERIC(5, 4),
    -- Constantes de calibração Planck e Atmosféricas da câmera FLIR (opcionais quando disponíveis no raw EXIF)
    planck_r1 DOUBLE PRECISION,
    planck_r2 DOUBLE PRECISION,
    planck_b DOUBLE PRECISION,
    planck_f DOUBLE PRECISION,
    planck_o DOUBLE PRECISION,
    atm_alpha1 DOUBLE PRECISION,
    atm_alpha2 DOUBLE PRECISION,
    atm_beta1 DOUBLE PRECISION,
    atm_beta2 DOUBLE PRECISION,
    atm_x DOUBLE PRECISION
);

-- Regiões de Interesse (ROIs) e Detecções da IA dentro de cada termograma (1:N)
CREATE TABLE deteccoes_regioes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inspecao_id UUID NOT NULL REFERENCES inspecoes_termograficas(id) ON DELETE CASCADE,
    indice_regiao INTEGER NOT NULL,
    classe_componente VARCHAR(80) NOT NULL REFERENCES catalogo_tipos_componente(codigo_classe),
    rotulo_regiao VARCHAR(150), -- Identificação específica da região no ativo (ex.: 'Terminal Superior Fase A')
    confianca_ml NUMERIC(5, 4) CHECK (confianca_ml >= 0 AND confianca_ml <= 1.0),
    -- Bounding Box normalizada ou em pixels
    bbox_x_min NUMERIC(8, 2) NOT NULL,
    bbox_y_min NUMERIC(8, 2) NOT NULL,
    bbox_x_max NUMERIC(8, 2) NOT NULL,
    bbox_y_max NUMERIC(8, 2) NOT NULL,
    -- Métricas térmicas internas da caixa (NULL caso a região não tenha medição/sem pixels válidos)
    t_min_c NUMERIC(6, 2),
    t_max_c NUMERIC(6, 2),
    t_media_c NUMERIC(6, 2),
    delta_t_regiao_c NUMERIC(6, 2),
    hotspot_x INTEGER,
    hotspot_y INTEGER,
    severidade_regiao tipo_severidade NOT NULL
);

-- =============================================================================
-- 5. ALERTAS, PENDÊNCIAS DE MANUTENÇÃO E LAUDOS TÉCNICOS
-- Substitui a tabela alertas do SQLite e as estruturas de app/pendencias.py e app/laudo.py
-- =============================================================================
CREATE TABLE alertas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo_legado VARCHAR(100) UNIQUE,
    inspecao_id UUID NOT NULL REFERENCES inspecoes_termograficas(id) ON DELETE CASCADE,
    deteccao_regiao_id UUID REFERENCES deteccoes_regioes(id) ON DELETE SET NULL,
    equipamento_id UUID NOT NULL REFERENCES equipamentos(id) ON DELETE RESTRICT,
    severidade tipo_severidade NOT NULL,
    temperatura_excedida_c NUMERIC(6, 2) NOT NULL,
    delta_t_excedido_c NUMERIC(6, 2),
    status status_alerta NOT NULL DEFAULT 'pendente',
    mensagem_formatada TEXT NOT NULL,
    canal_notificacao VARCHAR(60), -- Ex.: 'email', 'webhook', 'whatsapp', 'painel'
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    enviado_em TIMESTAMPTZ
);

CREATE TABLE pendencias_manutencao (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inspecao_origem_id UUID NOT NULL REFERENCES inspecoes_termograficas(id) ON DELETE CASCADE,
    instalacao_id UUID REFERENCES instalacoes(id) ON DELETE RESTRICT,
    equipamento_id UUID REFERENCES equipamentos(id) ON DELETE RESTRICT,
    responsavel_nome VARCHAR(150),

    severidade tipo_severidade NOT NULL,
    regiao_afetada VARCHAR(150),
    t_max_detectada_c NUMERIC(6, 2),
    detectada_em TIMESTAMPTZ NOT NULL,
    prazo_padrao BOOLEAN NOT NULL DEFAULT TRUE,
    data_limite DATE NOT NULL,

    status status_pendencia NOT NULL DEFAULT 'aberta',
    ordem_servico_codigo VARCHAR(100), -- Integração com SAP PM / IBM Maximo / ERP
    nota_tecnica TEXT,

    -- Vínculo direto com a reinspeção que comprovou a resolução do ponto quente
    inspecao_reinspecao_id UUID REFERENCES inspecoes_termograficas(id) ON DELETE SET NULL,
    resolvida_em TIMESTAMPTZ,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trilha de auditoria imutável para mudanças de status, prazos e OS (substitui array historico)
CREATE TABLE historico_pendencias (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pendencia_id UUID NOT NULL REFERENCES pendencias_manutencao(id) ON DELETE CASCADE,
    usuario_id UUID REFERENCES usuarios_responsaveis(id),
    status_anterior status_pendencia,
    status_novo status_pendencia NOT NULL,
    ordem_servico_informada VARCHAR(100),
    comentario TEXT,
    registrado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE laudos_tecnicos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numero_relatorio VARCHAR(60) UNIQUE NOT NULL, -- Formato RT-YYYYMMDD-{HASH} de app/laudo.py
    empresa_id UUID NOT NULL REFERENCES empresas(id) ON DELETE RESTRICT,
    instalacao_id UUID REFERENCES instalacoes(id) ON DELETE RESTRICT,
    responsavel_tecnico_id UUID NOT NULL REFERENCES usuarios_responsaveis(id),
    codigo_art VARCHAR(80), -- Anotação de Responsabilidade Técnica
    versao_emissor VARCHAR(30) NOT NULL,
    criterios_utilizados JSONB NOT NULL DEFAULT '{}'::JSONB,
    pdf_storage_uri TEXT NOT NULL, -- URI do PDF gerado em nuvem
    html_storage_uri TEXT,
    emitido_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE laudo_inspecoes (
    laudo_id UUID NOT NULL REFERENCES laudos_tecnicos(id) ON DELETE CASCADE,
    inspecao_id UUID NOT NULL REFERENCES inspecoes_termograficas(id) ON DELETE RESTRICT,
    ordem_exibicao INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (laudo_id, inspecao_id)
);

-- =============================================================================
-- 6. PROCESSAMENTO DE VÍDEOS E STREAMING MOBILE (SÉRIES TEMPORAIS)
-- Substitui estado.json, quadros.jsonl (app/videos.py) e estado de app/celular.py
-- =============================================================================
CREATE TABLE sessoes_video (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo_externo VARCHAR(100) UNIQUE,
    instalacao_id UUID REFERENCES instalacoes(id),
    equipamento_id UUID REFERENCES equipamentos(id),
    modelo_ml_id UUID REFERENCES modelos_ml(id),
    origem VARCHAR(30) NOT NULL DEFAULT 'arquivo_video', -- 'arquivo_video' ou 'celular_stream'
    nome_arquivo VARCHAR(255),
    video_storage_uri TEXT,
    tamanho_bytes BIGINT,
    duracao_s NUMERIC(10, 2),
    fps_original NUMERIC(6, 2),
    largura_px INTEGER,
    altura_px INTEGER,
    modo modo_processamento_video NOT NULL DEFAULT 'intervalo',
    intervalo_amostragem_s NUMERIC(6, 2),
    fator_velocidade NUMERIC(5, 2) DEFAULT 1.0,
    status status_job_processamento NOT NULL DEFAULT 'na_fila',
    total_quadros_processados INTEGER NOT NULL DEFAULT 0,
    fps_processamento NUMERIC(6, 2),
    alertas_gerados INTEGER NOT NULL DEFAULT 0,
    progresso_porcentagem NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
    dispositivo_cliente_ip VARCHAR(60), -- Usado no modo celular (app/celular.py)
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finalizado_em TIMESTAMPTZ
);

-- Tabela de alta frequência (candidata ideal a Hypertable no TimescaleDB)
CREATE TABLE telemetria_quadros_video (
    sessao_video_id UUID NOT NULL REFERENCES sessoes_video(id) ON DELETE CASCADE,
    capturado_em TIMESTAMPTZ NOT NULL,
    numero_quadro INTEGER NOT NULL,
    tempo_video_s NUMERIC(10, 3) NOT NULL,
    latencia_inferencia_ms NUMERIC(8, 2),
    t_max_quadro_c NUMERIC(6, 2),
    t_min_quadro_c NUMERIC(6, 2),
    escala_conversao JSONB,
    caixas_detectadas JSONB NOT NULL DEFAULT '[]'::JSONB, -- Lista de detecções {classe, confianca, bbox, t_max}
    posicao_dispositivo JSONB, -- Orientação espacial do app/celular.py
    quadro_imagem_uri TEXT, -- Preenchido apenas para keyframes ou frames com anomalia
    PRIMARY KEY (sessao_video_id, capturado_em, numero_quadro)
);

-- Se TimescaleDB estiver ativo:
-- SELECT create_hypertable('telemetria_quadros_video', 'capturado_em', chunk_time_interval => INTERVAL '7 days');

-- =============================================================================
-- 7. ÍNDICES DE PERFORMANCE E VIEWS MATERIALIZADAS PARA O FRONTEND DO PYRON
-- =============================================================================
CREATE INDEX idx_inspecoes_equipamento_data ON inspecoes_termograficas (equipamento_id, capturado_em DESC);
CREATE INDEX idx_inspecoes_instalacao_severidade ON inspecoes_termograficas (instalacao_id, severidade, capturado_em DESC);
CREATE INDEX idx_deteccoes_classe_severidade ON deteccoes_regioes (classe_componente, severidade_regiao);
CREATE INDEX idx_pendencias_status_limite ON pendencias_manutencao (status, data_limite ASC) WHERE status IN ('aberta', 'em_andamento');
CREATE INDEX idx_alertas_status_criado ON alertas (status, criado_em DESC);

-- View que substitui o processamento em memória de app/equipamentos.py
CREATE VIEW vw_resumo_equipamentos AS
SELECT
    e.id AS equipamento_id,
    i.nome AS instalacao,
    e.tag_codigo AS equipamento,
    (i.codigo_instalacao || ':' || e.tag_codigo) AS chave,
    COUNT(it.id) AS total_inspecoes,
    MAX(it.capturado_em) AS ultima_inspecao,
    MAX(it.t_max_cena_c) AS maior_temperatura_historica_c,
    MAX(it.delta_t_global_c) AS maior_delta_t_historico_c,
    (ARRAY_AGG(it.severidade ORDER BY it.capturado_em DESC))[1] AS severidade_atual
FROM equipamentos e
JOIN instalacoes i ON i.id = e.instalacao_id
LEFT JOIN inspecoes_termograficas it ON it.equipamento_id = e.id
GROUP BY e.id, i.nome, e.tag_codigo, i.codigo_instalacao;
```

## 4. Arquitetura do Pipeline de Dados (Ingestão, Lakehouse e MLOps)

Para operar em escala industrial (múltiplas subestações e equipes de inspeção), o banco estruturado deve ser integrado em três camadas complementares:

1. **Camada Transacional e API de Ingestão (FastAPI + PostgreSQL + Object Storage)**:
   * Quando o inspetor envia um termograma FLIR ou finaliza uma captura via [app/celular.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fapp%2Fcelular.py), o backend gera *Presigned URLs* para upload direto das imagens (`.jpg`) e da matriz térmica (`.npy` comprimida ou convertida em Apache Parquet/Zarr) para o Object Storage.
   * O motor [nucleo/analise.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fnucleo%2Fanalise.py) grava em uma única transação ACID o registro em `inspecoes_termograficas`, a calibração em `parametros_radiometricos_flir`, as caixas em `deteccoes_regioes` e, caso `severidade != 'normal'`, dispara automaticamente a criação em `alertas` e `pendencias_manutencao` (via trigger ou serviço de domínio).
2. **Camada de Série Temporal e Degradação Preditiva**:
   * Com `inspecoes_termograficas` e `deteccoes_regioes` normalizadas e indexadas por `(equipamento_id, rotulo_regiao, capturado_em)`, o cálculo de tendência de aquecimento ($\frac{d(\Delta T)}{dt}$) passa a ser uma query SQL nativa (usando funções de janela `LAG()` e `REGR_SLOPE()`), permitindo prever em quantos dias um componente atingirá sua Temperatura Máxima Admissível (`mta_padrao_c` de [nucleo/referencias.py](https://www.google.com/search?q=https%3A%2F%2Fgithub.com%2Fhugovieiraz%2FPyron---Embrapii%2Fblob%2Fmain%2Fnucleo%2Freferencias.py)) mesmo antes de cruzar o limiar crítico.
3. **Ciclo Fechado de Active Learning (Data Flywheel para o RF-DETR / ONNX)**:
   * Sempre que um engenheiro corrige manualmente uma caixa delimitadora ou valida uma reinspeção na interface do Pyron, essa revisão é registrada no banco e exportada seletivamente para um dataset versionado no Object Storage, alimentando novas execuções rastreadas nas tabelas `treinos_ml` e `avaliacoes_ml`.
