# Guia de Implementação: Dashboard Estratégico e Logística (Formatos Gratuitos)

Este guia orienta como conectar ferramentas de BI **100% gratuitas e open-source** ao banco de dados do **Pyron (PostgreSQL / SQLite)** para viabilizar o acompanhamento conjunto da **Engenharia**, **Logística** e **Suprimentos / Compras**.

---

## 1. As Melhores Ferramentas Gratuitas

| Ferramenta | Custo / Licença | Conexão Direta | Perfil de Usuário |
| :--- | :--- | :--- | :--- |
| **Metabase (Open Source)** | Gratuito (Docker / .jar) | PostgreSQL & SQLite | **Recomendado:** Interface amigável para diretores e compradores, filtros dinâmicos, gráficos e exportação em Excel em 1 clique. |
| **Power BI Desktop** | Gratuito para uso local | PostgreSQL & SQLite | Engenharia que já utiliza pacote Microsoft, permitindo gerar relatórios em `.pbix` ou exportar em PDF. |
| **Grafana (OSS)** | Gratuito (Open Source) | PostgreSQL | Monitoramento em tempo real com telas de centro de operação (NOC). |
| **Apache Superset** | Gratuito (Apache 2.0) | PostgreSQL & SQLite | Plataforma completa de BI corporativo sem limites de usuários. |
| **DBeaver Community** | Gratuito Desktop | PostgreSQL & SQLite | Ideal para extrações rápidas em CSV/XLSX para suprimentos. |

---

## 2. Views Estruturadas Prontas para o Dashboard

O script [`docs/views_dashboard_bi.sql`](views_dashboard_bi.sql) cria automaticamente as 4 visualizações de negócio necessárias:

### 📦 A. Planejamento de Compras e Logística (`vw_logistica_suprimentos_reparos`)
Conecta a falha térmica à ação de compra e substituição:
- **`subestacao_instalacao`** e **`equipamento`**: Onde a peça deve ser entregue.
- **`peca_a_reparar_substituir`**: Componente específico em risco (ex: *Conexão*, *Terminal Superior*, *Bucha Fase A*, *Corpo Para-raios*).
- **`data_limite`**: Data máxima antes do colapso térmico pela NBR 15866.
- **`dias_restantes_para_reparo`**: Contagem regressiva em dias.
- **`janela_logistica_prioridade`**:
  - `VENCIDO - PARADA URGENTE`
  - `CRÍTICO - REQUER COMPRA IMEDIATA (ATÉ 7 DIAS)`
  - `PROGRAMAR COMPRA (PRÓXIMOS 30 DIAS)`
  - `PLANEJAMENTO TRIMESTRAL (31-60 DIAS)`
- **`ordem_servico`**: Código da OS para faturamento e rastreio.

### 📊 B. Matriz de Sobressalentes (`vw_demanda_compras_pecas`)
Quantifica o volume de compra para negociação em lote:
- Quantidade total de peças necessárias agrupadas por tipo.
- Quantitativo de demanda imediata ($\le$ 7 dias) vs curto prazo (30 dias).
- Relação das subestações de destino para roteirização logística.

### ⚙️ C. Visão de Engenharia de Ativos (`vw_engenharia_saude_ativos`)
Acompanha o parque instalado:
- Pico histórico de temperatura ($T_{máx}$) e $\Delta T$.
- Estado atual de criticidade.
- Quantidade de manutenções em aberto vs aguardando reinspeção pós-reparo.

### 🎯 D. Cartão de KPIs da Diretoria (`vw_kpis_estrategicos_diretoria`)
- Total de ativos monitorados.
- Total de ordens de serviço pendentes e reparos vencidos.
- Alertas não atendidos.

---

## 3. Passo a Passo Rápido: Subindo com Metabase (Recomendado)

O **Metabase** é a opção mais produtiva para compras e diretoria:

1. **Subir via Docker (1 comando):**
   ```bash
   docker run -d -p 3000:3000 --name pyron-metabase metabase/metabase
   ```
   *(Ou baixar o `metabase.jar` gratuito e rodar `java -jar metabase.jar`)*.

2. **Acessar a interface:**
   Abra no navegador: `http://localhost:3000`.

3. **Conectar ao banco:**
   - Tipo de banco: **PostgreSQL**
   - Host: `localhost` (ou o host da sua nuvem)
   - Porta: `5432`
   - Banco de dados: `pyron`
   - Usuário e senha configurados.

4. **Criar as Perguntas e o Painel:**
   - Adicione uma tabela apontando para `vw_logistica_suprimentos_reparos`.
   - Adicione um gráfico de pizza para `janela_logistica_prioridade`.
   - Adicione um gráfico de barras para `vw_demanda_compras_pecas` (demanda por tipo de material).

5. **Exportação para Compras:**
   - Qualquer usuário clica no ícone de download no canto inferior da tabela e baixa diretamente em **.XLSX** ou **.CSV** pronto para envio aos fornecedores.

---

## 4. Passo a Passo Rápido: Power BI Desktop (Gratuito)

1. Baixe gratuitamente o **Power BI Desktop**.
2. Clique em **Obter Dados** $\rightarrow$ **Banco de Dados PostgreSQL**.
3. Insira o servidor e o banco de dados.
4. Selecione as tabelas/views que começam com `vw_`.
5. Arraste os campos de data limite e equipamento para criar um gráfico de Gantt ou tabela de prioridade com formatação condicional (Vermelho para $\le$ 7 dias, Laranja para 30 dias).

