"""Inspeções salvas: SQLite para os dados, um armazém de objetos para a imagem original e a matriz.

A análise completa continua guardada como JSON (coluna ``analises.dados``): é o que a API devolve e
o que se recalcula quando o critério muda. A cada gravação, os campos que interessam a consultas
saem também em colunas e tabelas próprias (equipamentos, regiões, parâmetros de medição,
pendências, arquivos), na mesma transação. Assim o banco responde perguntas como "quais conexões
passaram de 80% da MTA neste ano" em SQL, com índice, e o caminho para um banco na nuvem
(PostgreSQL) é um espelho dessas tabelas, sem garimpar JSON.

O esquema tem versão (``PRAGMA user_version``) e se atualiza sozinho ao abrir: um banco antigo, ou
restaurado de um backup antigo, ganha as tabelas novas e é reindexado a partir do JSON.

O banco fica em modo WAL (desde a 0.9): quem lê não espera quem grava, o que importa no modo servidor,
com vários engenheiros ao mesmo tempo. Na versão 3 do esquema entram os comentários com autor, as
sessões de quem entrou no modo servidor e o registro dos laudos emitidos (trilha de auditoria).

Os arquivos (``imagens/<id>.jpg``, ``imagens/<id>_foto.jpg``, ``matrizes/<id>.npy``) passam pelo
armazém de ``app.objetos``: a pasta de dados por padrão, ou um bucket S3 com ``PYRON_OBJETOS``.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import numpy as np

from app import objetos

VERSAO_ESQUEMA = 3
ESPERA_TRAVA_S = 15  # quanto uma gravação espera outra terminar antes de desistir (o padrão do sqlite3 é 5 s)


def _destaque(a: dict) -> dict | None:
    """A região que decide a severidade da inspeção: é o que o Painel mostra."""
    ordem = ["sem_medida", "nao_avaliado", "normal", "atencao", "programar", "urgente", "imediato"]
    regioes = [r for r in a.get("regioes", []) if r.get("severidade")]
    if not regioes:
        return None
    pior = max(regioes, key=lambda r: (ordem.index(r["severidade"]), r.get("pct_mta") or 0, (r.get("medida") or {}).get("t_max") or 0))
    return {
        "nome": pior.get("nome"),
        "severidade": pior["severidade"],
        "t_max": (pior.get("medida") or {}).get("t_max"),
        "pct_mta": pior.get("pct_mta"),
        "dt": pior.get("dt_corrigido"),
    }


# ---------------------------------------------------------------- esquema

ESQUEMA_V1 = (
    "CREATE TABLE IF NOT EXISTS analises (id TEXT PRIMARY KEY, criado_em TEXT, nome TEXT, severidade TEXT, dados TEXT)",
    "CREATE TABLE IF NOT EXISTS alertas (id TEXT PRIMARY KEY, criado_em TEXT, status TEXT, dados TEXT)",
)

# Colunas novas em tabelas que já existiam (ALTER TABLE só acrescenta; quem não conhece, ignora).
COLUNAS_V2 = {
    "analises": {
        "capturado_em": "TEXT",  # data da câmera (EXIF); sem ela, a de entrada no Pyron
        "equipamento_id": "INTEGER REFERENCES equipamentos(id) ON DELETE SET NULL",
        "fonte": "TEXT",  # manual, monitoramento, video, celular…
        "radiometrica": "INTEGER",
        "modelo": "TEXT",
        "t_max_cena": "REAL",
        "t_min_cena": "REAL",
        "maior_pct_mta": "REAL",
        "ambiente_c": "REAL",
        "carga_pct": "REAL",
    },
    "alertas": {
        "analise_id": "TEXT",  # sem chave estrangeira: o alerta fica no histórico mesmo se a inspeção for apagada
        "severidade": "TEXT",
    },
}

TABELAS_V2 = (
    # Cadastro: o que hoje se digita na identificação da inspeção. A chave é a mesma da URL
    # (equipamentos.chave): sem acento e sem diferença de maiúsculas, então "SE Campina" e
    # "se campina" são a mesma instalação.
    """CREATE TABLE IF NOT EXISTS instalacoes (
        id INTEGER PRIMARY KEY,
        chave TEXT NOT NULL UNIQUE,
        nome TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS equipamentos (
        id INTEGER PRIMARY KEY,
        chave TEXT NOT NULL UNIQUE,
        instalacao_id INTEGER REFERENCES instalacoes(id) ON DELETE SET NULL,
        nome TEXT NOT NULL)""",
    # Uma linha por região medida (caixa do modelo ou desenhada), com a avaliação em vigor.
    """CREATE TABLE IF NOT EXISTS regioes (
        analise_id TEXT NOT NULL REFERENCES analises(id) ON DELETE CASCADE,
        ordem INTEGER NOT NULL,
        regiao_id TEXT,
        nome TEXT,
        classe TEXT,
        origem TEXT,
        confianca REAL,
        x0 REAL, y0 REAL, x1 REAL, y1 REAL,
        t_max REAL, t_med REAL, t_min REAL,
        x_max INTEGER, y_max INTEGER,
        dt_corrigido REAL,
        pct_mta REAL,
        severidade TEXT,
        PRIMARY KEY (analise_id, ordem))""",
    # Parâmetros de medição lidos da câmera (radiométrica) ou a escala lida na barra de cores.
    """CREATE TABLE IF NOT EXISTS parametros_medicao (
        analise_id TEXT PRIMARY KEY REFERENCES analises(id) ON DELETE CASCADE,
        camera TEXT,
        emissividade REAL,
        distancia_m REAL,
        temp_refletida_c REAL,
        temp_atmosfera_c REAL,
        umidade_relativa REAL,
        resolucao_sensor TEXT,
        escala_min_c REAL,
        escala_max_c REAL)""",
    # Pendência: toda inspeção fora do normal (como em app/pendencias.py), com o prazo em vigor.
    """CREATE TABLE IF NOT EXISTS pendencias (
        analise_id TEXT PRIMARY KEY REFERENCES analises(id) ON DELETE CASCADE,
        severidade TEXT NOT NULL,
        status TEXT NOT NULL,
        prazo TEXT NOT NULL,
        prazo_padrao INTEGER NOT NULL,
        ordem_servico TEXT,
        responsavel TEXT,
        nota TEXT)""",
    """CREATE TABLE IF NOT EXISTS historico_pendencias (
        analise_id TEXT NOT NULL REFERENCES analises(id) ON DELETE CASCADE,
        ordem INTEGER NOT NULL,
        quando TEXT,
        status TEXT,
        nota TEXT,
        PRIMARY KEY (analise_id, ordem))""",
    # Catálogo dos arquivos no armazém de objetos: tamanho e SHA-256 para conferir a integridade.
    """CREATE TABLE IF NOT EXISTS arquivos (
        chave TEXT PRIMARY KEY,
        analise_id TEXT NOT NULL REFERENCES analises(id) ON DELETE CASCADE,
        tipo TEXT NOT NULL,
        bytes INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        gravado_em TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_analises_equipamento ON analises (equipamento_id, capturado_em)",
    "CREATE INDEX IF NOT EXISTS idx_analises_severidade ON analises (severidade, capturado_em)",
    "CREATE INDEX IF NOT EXISTS idx_regioes_classe ON regioes (classe, severidade)",
    "CREATE INDEX IF NOT EXISTS idx_pendencias_status ON pendencias (status, prazo)",
    "CREATE INDEX IF NOT EXISTS idx_alertas_status ON alertas (status, criado_em)",
    "CREATE INDEX IF NOT EXISTS idx_arquivos_analise ON arquivos (analise_id)",
    # Resumo por equipamento direto no SQL (a tela continua usando app/equipamentos.py, que tem a tendência).
    """CREATE VIEW IF NOT EXISTS vw_equipamentos AS
        SELECT e.id AS equipamento_id, e.chave, i.nome AS instalacao, e.nome AS equipamento,
               COUNT(a.id) AS inspecoes, MIN(a.capturado_em) AS primeira, MAX(a.capturado_em) AS ultima,
               MAX(a.t_max_cena) AS maior_t_max_cena, MAX(a.maior_pct_mta) AS maior_pct_mta
        FROM equipamentos e
        LEFT JOIN instalacoes i ON i.id = e.instalacao_id
        LEFT JOIN analises a ON a.equipamento_id = e.id
        GROUP BY e.id""",
)

# Versão 3 (0.9): autor no histórico da pendência, comentários, sessões e laudos emitidos.
COLUNAS_V3 = {"historico_pendencias": {"autor": "TEXT"}}

TABELAS_V3 = (
    # Comentário de alguém do time sobre uma inspeção (ou uma região dela). Só se acrescenta: não há edição.
    """CREATE TABLE IF NOT EXISTS comentarios (
        id TEXT PRIMARY KEY,
        analise_id TEXT NOT NULL REFERENCES analises(id) ON DELETE CASCADE,
        regiao_id TEXT,
        autor_id TEXT,
        autor_nome TEXT NOT NULL,
        criado_em TEXT NOT NULL,
        texto TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_comentarios_analise ON comentarios (analise_id, criado_em)",
    # Sessão do modo servidor: só o SHA-256 do código do cookie fica guardado.
    """CREATE TABLE IF NOT EXISTS sessoes (
        codigo_hash TEXT PRIMARY KEY,
        membro_id TEXT NOT NULL,
        criada_em TEXT NOT NULL,
        usada_em TEXT NOT NULL,
        expira_em TEXT NOT NULL)""",
    # Laudo emitido: quem pediu, quem assina, quando, quais inspeções e o SHA-256 do PDF entregue.
    # Sem chave estrangeira: o registro fica mesmo que a inspeção seja apagada depois.
    """CREATE TABLE IF NOT EXISTS laudos_emitidos (
        id TEXT PRIMARY KEY,
        emitido_em TEXT NOT NULL,
        emitido_por_id TEXT,
        emitido_por_nome TEXT,
        responsavel_nome TEXT NOT NULL,
        responsavel_registro TEXT,
        analises TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        bytes INTEGER NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_laudos_emitidos ON laudos_emitidos (emitido_em)",
)

ARQUIVOS = {"original": "imagens/{id}.jpg", "foto": "imagens/{id}_foto.jpg", "matriz": "matrizes/{id}.npy"}


def _chave_arquivo(tipo: str, id_: str) -> str:
    return ARQUIVOS[tipo].format(id=id_)


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _data_iso(valor) -> str | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(str(valor).replace(" ", "T")[:19]).isoformat(timespec="seconds")
    except ValueError:
        return None


class Armazenamento:
    def __init__(self, pasta: Path, armazem: objetos.Armazem | None = None):
        self.pasta = pasta
        pasta.mkdir(parents=True, exist_ok=True)
        self.objetos = armazem or objetos.do_ambiente(pasta)
        if isinstance(self.objetos, objetos.ArmazemLocal):
            (pasta / "imagens").mkdir(parents=True, exist_ok=True)
            (pasta / "matrizes").mkdir(parents=True, exist_ok=True)
        self.banco = pasta / "inspecoes.sqlite"
        with self._conexao():
            pass  # cria ou atualiza o esquema

    @contextmanager
    def _conexao(self):
        """Conexão que grava (commit) e fecha ao sair: no Windows, conexão aberta prende o arquivo."""
        c = sqlite3.connect(self.banco, timeout=ESPERA_TRAVA_S)
        try:
            c.execute("PRAGMA journal_mode = WAL")  # fica gravado no arquivo; repetir custa nada (e vale após restaurar)
            c.execute("PRAGMA foreign_keys = ON")
            if c.execute("PRAGMA user_version").fetchone()[0] < VERSAO_ESQUEMA:
                self._migrar(c)
            with c:
                yield c
        finally:
            c.close()

    # ------------------------------------------------------------ migração

    def _migrar(self, c: sqlite3.Connection) -> None:
        """Leva o banco à versão atual numa transação só: ou atualiza tudo, ou nada muda."""
        c.execute("BEGIN IMMEDIATE")  # trava a escrita: outra conexão espera e depois vê a versão nova
        try:
            versao = c.execute("PRAGMA user_version").fetchone()[0]
            if versao < 1:
                for sql in ESQUEMA_V1:
                    c.execute(sql)
            if versao < 2:
                for tabela, colunas in COLUNAS_V2.items():
                    existentes = {linha[1] for linha in c.execute(f"PRAGMA table_info({tabela})")}
                    for nome, tipo in colunas.items():
                        if nome not in existentes:
                            c.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")
                for sql in TABELAS_V2:
                    c.execute(sql)
            if versao < 3:
                for tabela, colunas in COLUNAS_V3.items():
                    existentes = {linha[1] for linha in c.execute(f"PRAGMA table_info({tabela})")}
                    for nome, tipo in colunas.items():
                        if nome not in existentes:
                            c.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")
                for sql in TABELAS_V3:
                    c.execute(sql)
            if versao < 2:  # reindexa depois de todas as colunas existirem (o índice grava o autor da v3)
                for (dados,) in c.execute("SELECT dados FROM analises").fetchall():
                    a = json.loads(dados)
                    self._indexar(c, a)
                    self._catalogar_existentes(c, a["id"])
                for (dados,) in c.execute("SELECT dados FROM alertas").fetchall():
                    al = json.loads(dados)
                    c.execute("UPDATE alertas SET analise_id = ?, severidade = ? WHERE id = ?",
                              (al.get("analise_id"), al.get("severidade"), al["id"]))
            c.execute(f"PRAGMA user_version = {VERSAO_ESQUEMA}")
            c.commit()
        except BaseException:
            c.rollback()
            raise

    def _catalogar_existentes(self, c: sqlite3.Connection, id_: str) -> None:
        """Na migração: registra tamanho e SHA-256 dos arquivos que a inspeção já tinha."""
        for tipo in ARQUIVOS:
            chave = _chave_arquivo(tipo, id_)
            dados = self.objetos.ler(chave)
            if dados is not None:
                self._registrar_arquivo(c, id_, tipo, objetos._ficha(chave, dados))

    # ------------------------------------------------------------ projeção do JSON em tabelas

    @staticmethod
    def _registrar_arquivo(c: sqlite3.Connection, id_: str, tipo: str, ficha: dict) -> None:
        c.execute(
            "INSERT INTO arquivos (chave, analise_id, tipo, bytes, sha256, gravado_em) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET analise_id = excluded.analise_id, tipo = excluded.tipo, "
            "bytes = excluded.bytes, sha256 = excluded.sha256, gravado_em = excluded.gravado_em",
            (ficha["chave"], id_, tipo, ficha["bytes"], ficha["sha256"], datetime.now().isoformat(timespec="seconds")),
        )

    @staticmethod
    def _equipamento_id(c: sqlite3.Connection, ident: dict) -> int | None:
        from app import equipamentos as eq  # import tardio: equipamentos não depende do banco

        nome_eq = (ident.get("equipamento") or "").strip()
        if not nome_eq:
            return None
        nome_inst = (ident.get("instalacao") or "").strip()
        chave = eq.chave(nome_inst, nome_eq)
        inst_id = None
        if nome_inst:
            chave_inst = chave.split("--", 1)[0]
            c.execute("INSERT INTO instalacoes (chave, nome) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET nome = excluded.nome",
                      (chave_inst, nome_inst))
            inst_id = c.execute("SELECT id FROM instalacoes WHERE chave = ?", (chave_inst,)).fetchone()[0]
        c.execute("INSERT INTO equipamentos (chave, instalacao_id, nome) VALUES (?, ?, ?) "
                  "ON CONFLICT(chave) DO UPDATE SET instalacao_id = excluded.instalacao_id, nome = excluded.nome",
                  (chave, inst_id, nome_eq))
        return c.execute("SELECT id FROM equipamentos WHERE chave = ?", (chave,)).fetchone()[0]

    def _indexar(self, c: sqlite3.Connection, a: dict) -> None:
        """Atualiza colunas e tabelas derivadas de uma análise (o JSON já está gravado)."""
        from app import equipamentos as eq
        from app import pendencias as pend

        id_ = a["id"]
        resumo = a.get("resumo") or {}
        meta = a.get("metadados") or {}
        cond = a.get("condicoes") or {}
        criado = a.get("criado_em")
        capturado = _data_iso(meta.get("data_hora")) or _data_iso(criado)
        c.execute(
            "UPDATE analises SET capturado_em = ?, equipamento_id = ?, fonte = ?, radiometrica = ?, modelo = ?, "
            "t_max_cena = ?, t_min_cena = ?, maior_pct_mta = ?, ambiente_c = ?, carga_pct = ? WHERE id = ?",
            (
                capturado, self._equipamento_id(c, a.get("identificacao") or {}), a.get("fonte", "manual"),
                None if a.get("radiometrica") is None else int(bool(a["radiometrica"])),
                (a.get("modelo") or {}).get("nome"), _num(resumo.get("t_max_cena")), _num(resumo.get("t_min_cena")),
                _num(resumo.get("maior_pct_mta")), _num(cond.get("ambiente_c")), _num(cond.get("carga_pct")), id_,
            ),
        )

        c.execute("DELETE FROM regioes WHERE analise_id = ?", (id_,))
        for ordem, r in enumerate(a.get("regioes") or []):
            caixa = list(r.get("caixa") or []) + [None] * 4
            m = r.get("medida") or {}
            c.execute(
                "INSERT INTO regioes (analise_id, ordem, regiao_id, nome, classe, origem, confianca, x0, y0, x1, y1, "
                "t_max, t_med, t_min, x_max, y_max, dt_corrigido, pct_mta, severidade) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    id_, ordem, r.get("id"), r.get("nome"), r.get("classe"), r.get("origem"), _num(r.get("confianca")),
                    *(_num(v) for v in caixa[:4]), _num(m.get("t_max")), _num(m.get("t_med")), _num(m.get("t_min")),
                    m.get("x_max"), m.get("y_max"), _num(r.get("dt_corrigido")), _num(r.get("pct_mta")), r.get("severidade"),
                ),
            )

        escala = meta.get("escala_lida_c") or [None, None]
        c.execute(
            "INSERT OR REPLACE INTO parametros_medicao (analise_id, camera, emissividade, distancia_m, temp_refletida_c, "
            "temp_atmosfera_c, umidade_relativa, resolucao_sensor, escala_min_c, escala_max_c) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                id_, meta.get("camera"), _num(meta.get("emissividade")), _num(meta.get("distancia_m")),
                _num(meta.get("temp_refletida_c")), _num(meta.get("temp_atmosfera_c")), _num(meta.get("umidade_relativa")),
                meta.get("resolucao_sensor"), _num(escala[0]), _num(escala[1]),
            ),
        )

        c.execute("DELETE FROM pendencias WHERE analise_id = ?", (id_,))
        c.execute("DELETE FROM historico_pendencias WHERE analise_id = ?", (id_,))
        severidade = resumo.get("severidade", "normal")
        if severidade not in ("normal", "sem_medida", "nao_avaliado") and severidade in eq.PRAZO_DIAS:
            p = pend.montar({**a, "destaque": _destaque(a), "data_captura": meta.get("data_hora", "")})
            c.execute(
                "INSERT INTO pendencias (analise_id, severidade, status, prazo, prazo_padrao, ordem_servico, responsavel, nota) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (id_, severidade, p["status"], p["prazo"], int(p["prazo_padrao"]), p["ordem_servico"] or None,
                 p["responsavel"] or None, p["nota"] or None),
            )
            for ordem, h in enumerate(p["historico"]):
                c.execute("INSERT INTO historico_pendencias (analise_id, ordem, quando, status, nota, autor) VALUES (?, ?, ?, ?, ?, ?)",
                          (id_, ordem, h.get("quando"), h.get("status"), h.get("nota"), h.get("autor")))

    def reindexar(self) -> int:
        """Refaz todas as tabelas derivadas a partir do JSON (conserto, ou depois de um Pyron antigo gravar no banco)."""
        with self._conexao() as c:
            linhas = c.execute("SELECT dados FROM analises").fetchall()
            for (dados,) in linhas:
                self._indexar(c, json.loads(dados))
        return len(linhas)

    # ------------------------------------------------------------ inspeções

    def salvar(self, analise: dict, original: bytes | None = None, matriz: np.ndarray | None = None) -> None:
        fichas = []
        if original is not None:
            fichas.append(("original", self.objetos.gravar(_chave_arquivo("original", analise["id"]), original)))
        if matriz is not None:
            fichas.append(("matriz", self.objetos.gravar(_chave_arquivo("matriz", analise["id"]), objetos.matriz_para_bytes(matriz))))
        with self._conexao() as c:
            c.execute(
                "INSERT INTO analises (id, criado_em, nome, severidade, dados) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET criado_em = excluded.criado_em, nome = excluded.nome, "
                "severidade = excluded.severidade, dados = excluded.dados",
                (
                    analise["id"],
                    analise["criado_em"],
                    analise["arquivo"],
                    analise["resumo"]["severidade"],
                    json.dumps(analise, ensure_ascii=False),
                ),
            )
            self._indexar(c, analise)
            for tipo, ficha in fichas:
                self._registrar_arquivo(c, analise["id"], tipo, ficha)

    def obter(self, id_: str) -> dict | None:
        with self._conexao() as c:
            linha = c.execute("SELECT dados FROM analises WHERE id = ?", (id_,)).fetchone()
        return json.loads(linha[0]) if linha else None

    def matriz(self, id_: str) -> np.ndarray | None:
        dados = self.objetos.ler(_chave_arquivo("matriz", id_))
        return objetos.bytes_para_matriz(dados) if dados is not None else None

    def original(self, id_: str) -> bytes | None:
        return self.objetos.ler(_chave_arquivo("original", id_))

    def salvar_foto(self, id_: str, foto: bytes) -> None:
        ficha = self.objetos.gravar(_chave_arquivo("foto", id_), foto)
        with self._conexao() as c:
            if c.execute("SELECT 1 FROM analises WHERE id = ?", (id_,)).fetchone():
                self._registrar_arquivo(c, id_, "foto", ficha)

    def foto(self, id_: str) -> bytes | None:
        return self.objetos.ler(_chave_arquivo("foto", id_))

    def listar(self) -> list[dict]:
        with self._conexao() as c:
            linhas = c.execute("SELECT dados FROM analises ORDER BY criado_em DESC").fetchall()
        itens = []
        for (dados,) in linhas:
            a = json.loads(dados)
            itens.append(
                {
                    "id": a["id"],
                    "arquivo": a["arquivo"],
                    "criado_em": a["criado_em"],
                    "data_captura": a["metadados"].get("data_hora", ""),
                    "radiometrica": a["radiometrica"],
                    "modelo": a["modelo"]["nome"],
                    "fonte": a.get("fonte", "manual"),
                    "resumo": a["resumo"],
                    "identificacao": a.get("identificacao", {}),
                    "destaque": _destaque(a),
                    "acompanhamento": a.get("acompanhamento"),
                    "condicoes": a.get("condicoes"),
                }
            )
        return itens

    def conferir_arquivos(self) -> list[dict]:
        """Arquivos catalogados que sumiram ou mudaram desde a gravação (SHA-256 diferente)."""
        import hashlib

        with self._conexao() as c:
            catalogo = c.execute("SELECT chave, analise_id, sha256 FROM arquivos ORDER BY chave").fetchall()
        problemas = []
        for chave, analise_id, sha in catalogo:
            dados = self.objetos.ler(chave)
            if dados is None:
                problemas.append({"chave": chave, "analise_id": analise_id, "problema": "ausente"})
            elif hashlib.sha256(dados).hexdigest() != sha:
                problemas.append({"chave": chave, "analise_id": analise_id, "problema": "alterado"})
        return problemas

    # ------------------------------------------------------------ alertas do monitoramento

    def salvar_alerta(self, alerta: dict) -> None:
        with self._conexao() as c:
            c.execute(
                "INSERT OR REPLACE INTO alertas (id, criado_em, status, dados, analise_id, severidade) VALUES (?, ?, ?, ?, ?, ?)",
                (alerta["id"], alerta["criado_em"], alerta["status"], json.dumps(alerta, ensure_ascii=False),
                 alerta.get("analise_id"), alerta.get("severidade")),
            )

    def alertas(self, limite: int = 200) -> list[dict]:
        with self._conexao() as c:
            linhas = c.execute("SELECT dados FROM alertas ORDER BY criado_em DESC LIMIT ?", (limite,)).fetchall()
        return [json.loads(d) for (d,) in linhas]

    def alerta(self, id_: str) -> dict | None:
        with self._conexao() as c:
            linha = c.execute("SELECT dados FROM alertas WHERE id = ?", (id_,)).fetchone()
        return json.loads(linha[0]) if linha else None

    # ------------------------------------------------------------ comentários

    def comentar(self, analise_id: str, texto: str, autor_nome: str, autor_id: str | None = None,
                 regiao_id: str | None = None) -> dict:
        """Acrescenta um comentário (sem edição: o registro fica como foi escrito)."""
        from uuid import uuid4

        item = {"id": uuid4().hex[:12], "analise_id": analise_id, "regiao_id": regiao_id, "autor_id": autor_id,
                "autor_nome": autor_nome, "criado_em": datetime.now().isoformat(timespec="seconds"), "texto": texto}
        with self._conexao() as c:
            c.execute("INSERT INTO comentarios (id, analise_id, regiao_id, autor_id, autor_nome, criado_em, texto) "
                      "VALUES (:id, :analise_id, :regiao_id, :autor_id, :autor_nome, :criado_em, :texto)", item)
        return item

    def comentarios(self, analise_id: str) -> list[dict]:
        """Comentários de uma inspeção, do mais antigo para o mais novo."""
        with self._conexao() as c:
            c.row_factory = sqlite3.Row
            linhas = c.execute("SELECT id, analise_id, regiao_id, autor_id, autor_nome, criado_em, texto FROM comentarios "
                               "WHERE analise_id = ? ORDER BY criado_em, rowid", (analise_id,)).fetchall()
        return [dict(linha) for linha in linhas]

    # ------------------------------------------------------------ sessões (modo servidor)

    def criar_sessao(self, codigo_hash: str, membro_id: str, agora: datetime, expira: datetime) -> None:
        with self._conexao() as c:
            c.execute("DELETE FROM sessoes WHERE expira_em < ?", (agora.isoformat(timespec="seconds"),))
            c.execute("INSERT INTO sessoes (codigo_hash, membro_id, criada_em, usada_em, expira_em) VALUES (?, ?, ?, ?, ?)",
                      (codigo_hash, membro_id, agora.isoformat(timespec="seconds"), agora.isoformat(timespec="seconds"),
                       expira.isoformat(timespec="seconds")))

    def sessao(self, codigo_hash: str) -> dict | None:
        with self._conexao() as c:
            c.row_factory = sqlite3.Row
            linha = c.execute("SELECT * FROM sessoes WHERE codigo_hash = ?", (codigo_hash,)).fetchone()
        return dict(linha) if linha else None

    def usar_sessao(self, codigo_hash: str, agora: datetime) -> None:
        with self._conexao() as c:
            c.execute("UPDATE sessoes SET usada_em = ? WHERE codigo_hash = ?", (agora.isoformat(timespec="seconds"), codigo_hash))

    def encerrar_sessao(self, codigo_hash: str) -> None:
        with self._conexao() as c:
            c.execute("DELETE FROM sessoes WHERE codigo_hash = ?", (codigo_hash,))

    def encerrar_sessoes_de(self, membro_id: str, menos: str | None = None) -> None:
        """Encerra as sessões de uma pessoa (troca de senha, saiu do time), menos a ``menos``."""
        with self._conexao() as c:
            c.execute("DELETE FROM sessoes WHERE membro_id = ? AND codigo_hash != ?", (membro_id, menos or ""))

    def encerrar_sessoes_fora(self, membros_validos: set[str]) -> None:
        """Encerra as sessões de quem não pode mais entrar (saiu do time ou ficou sem senha)."""
        with self._conexao() as c:
            for (membro,) in c.execute("SELECT DISTINCT membro_id FROM sessoes").fetchall():
                if membro not in membros_validos:
                    c.execute("DELETE FROM sessoes WHERE membro_id = ?", (membro,))

    # ------------------------------------------------------------ laudos emitidos (auditoria)

    def registrar_laudo(self, registro: dict) -> None:
        with self._conexao() as c:
            c.execute("INSERT INTO laudos_emitidos (id, emitido_em, emitido_por_id, emitido_por_nome, responsavel_nome, "
                      "responsavel_registro, analises, sha256, bytes) VALUES (:id, :emitido_em, :emitido_por_id, "
                      ":emitido_por_nome, :responsavel_nome, :responsavel_registro, :analises, :sha256, :bytes)",
                      {**registro, "analises": json.dumps(registro["analises"])})

    def laudos_emitidos(self, limite: int = 200) -> list[dict]:
        with self._conexao() as c:
            c.row_factory = sqlite3.Row
            linhas = c.execute("SELECT * FROM laudos_emitidos ORDER BY emitido_em DESC, rowid DESC LIMIT ?", (limite,)).fetchall()
        return [{**dict(linha), "analises": json.loads(linha["analises"])} for linha in linhas]

    def apagar(self, id_: str) -> bool:
        with self._conexao() as c:
            n = c.execute("DELETE FROM analises WHERE id = ?", (id_,)).rowcount  # regiões, pendência e catálogo vão junto
        for tipo in ARQUIVOS:
            self.objetos.apagar(_chave_arquivo(tipo, id_))
        return n > 0
