"""Cadastro de medidas: câmeras calibradas e medidas dos equipamentos, com validação por engenheiro.

Banco próprio (``cadastro_medidas.sqlite`` na pasta de dados), ligado às inspeções pela chave do equipamento
(``app.equipamentos.chave``: instalação + equipamento). Fica separado do banco de inspeções para não mexer no
esquema dele.

Fluxo de uma medida:

1. **proposta**: o programa (folha, referência, laser) ou uma pessoa registra o valor, com o método, a incerteza e
   a origem (câmera, foto, distância);
2. **validada** ou **rejeitada** por um engenheiro, com nome e registro profissional (CREA). Quem propôs não valida
   a própria medida;
3. medida validada **não muda**: corrigir é propor outra que a substitui; a antiga fica no histórico como
   substituída. Todo passo fica em ``historico_medidas`` (quem, quando, o quê).

Só medida **validada** serve de referência de escala nas fotos seguintes (``referencias``).
"""

from __future__ import annotations

import json
import sqlite3
import statistics
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

STATUS = ("proposta", "validada", "rejeitada", "substituida")
METODOS = ("folha", "referencia", "laser", "catalogo", "projeto", "manual")
MEDIDAS = ("comprimento", "altura", "largura", "diametro", "distancia")
# fases do mesmo equipamento: diferença relativa acima disso marca a medida para revisão
TOLERANCIA_FASES = 0.03

ESQUEMA = (
    """CREATE TABLE IF NOT EXISTS cameras (
        nome TEXT PRIMARY KEY,
        tipo TEXT NOT NULL,
        perfil TEXT NOT NULL,
        criado_em TEXT NOT NULL,
        atualizado_em TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS posicoes_fixas (
        id INTEGER PRIMARY KEY,
        camera TEXT NOT NULL REFERENCES cameras(nome) ON DELETE CASCADE,
        equipamento_chave TEXT,
        dados TEXT NOT NULL,
        descritores BLOB NOT NULL,
        ativa INTEGER NOT NULL DEFAULT 1,
        criado_em TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS medidas (
        id INTEGER PRIMARY KEY,
        equipamento_chave TEXT NOT NULL,
        componente TEXT NOT NULL,
        classe TEXT,
        fase TEXT,
        medida TEXT NOT NULL,
        valor_cm REAL NOT NULL,
        incerteza_cm REAL,
        metodo TEXT NOT NULL,
        origem TEXT,
        status TEXT NOT NULL,
        substitui_id INTEGER REFERENCES medidas(id),
        criado_em TEXT NOT NULL,
        criado_por TEXT NOT NULL,
        validado_por TEXT,
        registro_validador TEXT,
        validado_em TEXT,
        nota TEXT)""",
    """CREATE TABLE IF NOT EXISTS historico_medidas (
        id INTEGER PRIMARY KEY,
        medida_id INTEGER NOT NULL REFERENCES medidas(id),
        quando TEXT NOT NULL,
        acao TEXT NOT NULL,
        por TEXT NOT NULL,
        nota TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_medidas_equipamento ON medidas (equipamento_chave, status)",
    # um valor em vigor por componente e medida: duas validadas ao mesmo tempo seria ambíguo
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_medida_validada ON medidas (equipamento_chave, componente, medida)
        WHERE status = 'validada'""",
)


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ErroCadastro(ValueError):
    pass


class Cadastro:
    def __init__(self, pasta: Path):
        pasta.mkdir(parents=True, exist_ok=True)
        self.banco = pasta / "cadastro_medidas.sqlite"
        with self._conexao():
            pass

    @contextmanager
    def _conexao(self):
        # Sem WAL de propósito: o backup copia este arquivo como está (o banco das inspeções vai pela API de backup).
        c = sqlite3.connect(self.banco, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA foreign_keys = ON")
            for sql in ESQUEMA:
                c.execute(sql)
            yield c
            c.commit()
        finally:
            c.close()

    # ------------------------------------------------------------ câmeras

    def salvar_camera(self, perfil) -> dict:
        d = perfil.para_dict()
        agora = _agora()
        with self._conexao() as c:
            c.execute(
                """INSERT INTO cameras (nome, tipo, perfil, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(nome) DO UPDATE SET tipo = excluded.tipo, perfil = excluded.perfil,
                   atualizado_em = excluded.atualizado_em""",
                (d["nome"], d["tipo"], json.dumps(d), agora, agora),
            )
        return d

    def camera(self, nome: str):
        from nucleo.medicao.camera import PerfilCamera

        with self._conexao() as c:
            r = c.execute("SELECT perfil FROM cameras WHERE nome = ?", (nome,)).fetchone()
        if r is None:
            raise ErroCadastro(f"câmera não cadastrada: {nome}")
        return PerfilCamera(**json.loads(r["perfil"]))

    def cameras(self) -> list[dict]:
        with self._conexao() as c:
            return [json.loads(r["perfil"]) | {"atualizado_em": r["atualizado_em"]}
                    for r in c.execute("SELECT perfil, atualizado_em FROM cameras ORDER BY nome")]

    def salvar_posicao(self, posicao, equipamento_chave: str | None = None) -> int:
        """Nova posição da câmera fixa; a anterior deixa de valer (fica guardada)."""
        with self._conexao() as c:
            c.execute("UPDATE posicoes_fixas SET ativa = 0 WHERE camera = ?", (posicao.camera,))
            cur = c.execute(
                "INSERT INTO posicoes_fixas (camera, equipamento_chave, dados, descritores, criado_em) VALUES (?, ?, ?, ?, ?)",
                (posicao.camera, equipamento_chave, json.dumps(posicao.para_dict() | {"pontos_cena": posicao.pontos_cena}),
                 posicao.descritores, _agora()),
            )
            return int(cur.lastrowid)

    def posicao(self, camera: str):
        from nucleo.medicao.camera import PosicaoFixa

        with self._conexao() as c:
            r = c.execute("SELECT dados, descritores FROM posicoes_fixas WHERE camera = ? AND ativa = 1", (camera,)).fetchone()
        if r is None:
            return None
        d = json.loads(r["dados"])
        d.pop("n_pontos_cena", None)
        return PosicaoFixa(**d, descritores=bytes(r["descritores"]))

    # ------------------------------------------------------------ medidas

    def _historico(self, c, medida_id: int, acao: str, por: str, nota: str | None = None) -> None:
        c.execute("INSERT INTO historico_medidas (medida_id, quando, acao, por, nota) VALUES (?, ?, ?, ?, ?)",
                  (medida_id, _agora(), acao, por, nota))

    def propor(self, equipamento_chave: str, componente: str, medida: str, valor_cm: float, metodo: str,
               criado_por: str, incerteza_cm: float | None = None, classe: str | None = None, fase: str | None = None,
               origem: dict | None = None, substitui_id: int | None = None, nota: str | None = None) -> dict:
        if medida not in MEDIDAS:
            raise ErroCadastro(f"medida desconhecida: {medida} (use {', '.join(MEDIDAS)})")
        if metodo not in METODOS:
            raise ErroCadastro(f"método desconhecido: {metodo} (use {', '.join(METODOS)})")
        if not (valor_cm and valor_cm > 0):
            raise ErroCadastro("o valor precisa ser positivo")
        if not (criado_por or "").strip():
            raise ErroCadastro("informe quem registrou a medida")
        if not (equipamento_chave or "").strip() or not (componente or "").strip():
            raise ErroCadastro("informe o equipamento e o componente")
        with self._conexao() as c:
            if substitui_id is not None:
                antiga = c.execute("SELECT status FROM medidas WHERE id = ?", (substitui_id,)).fetchone()
                if antiga is None:
                    raise ErroCadastro(f"medida {substitui_id} não existe")
            cur = c.execute(
                """INSERT INTO medidas (equipamento_chave, componente, classe, fase, medida, valor_cm, incerteza_cm,
                   metodo, origem, status, substitui_id, criado_em, criado_por, nota)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposta', ?, ?, ?, ?)""",
                (equipamento_chave, componente.strip(), classe, fase, medida, float(valor_cm), incerteza_cm, metodo,
                 json.dumps(origem or {}, ensure_ascii=False), substitui_id, _agora(), criado_por.strip(), nota),
            )
            mid = int(cur.lastrowid)
            self._historico(c, mid, "proposta", criado_por.strip(), nota)
        return self.medida(mid)

    def validar(self, medida_id: int, engenheiro: str, registro: str, nota: str | None = None) -> dict:
        """Engenheiro aprova a medida. Se ela substitui outra validada, a antiga passa a ``substituida``."""
        engenheiro, registro = (engenheiro or "").strip(), (registro or "").strip()
        if not engenheiro or not registro:
            raise ErroCadastro("a validação exige o nome do engenheiro e o registro profissional (CREA)")
        with self._conexao() as c:
            m = c.execute("SELECT * FROM medidas WHERE id = ?", (medida_id,)).fetchone()
            if m is None:
                raise ErroCadastro(f"medida {medida_id} não existe")
            if m["status"] != "proposta":
                raise ErroCadastro(f"medida {medida_id} está {m['status']}: só proposta pode ser validada")
            if m["criado_por"].casefold() == engenheiro.casefold():
                raise ErroCadastro("quem registrou a medida não pode validá-la")
            anteriores = c.execute(
                "SELECT id FROM medidas WHERE equipamento_chave = ? AND componente = ? AND medida = ? AND status = 'validada'",
                (m["equipamento_chave"], m["componente"], m["medida"]),
            ).fetchall()
            for a in anteriores:
                c.execute("UPDATE medidas SET status = 'substituida' WHERE id = ?", (a["id"],))
                self._historico(c, a["id"], "substituida", engenheiro, f"pela medida {medida_id}")
            c.execute("UPDATE medidas SET status = 'validada', validado_por = ?, registro_validador = ?, validado_em = ? WHERE id = ?",
                      (engenheiro, registro, _agora(), medida_id))
            self._historico(c, medida_id, "validada", f"{engenheiro} ({registro})", nota)
        return self.medida(medida_id)

    def rejeitar(self, medida_id: int, engenheiro: str, registro: str, motivo: str) -> dict:
        if not (motivo or "").strip():
            raise ErroCadastro("informe o motivo da rejeição")
        if not (engenheiro or "").strip() or not (registro or "").strip():
            raise ErroCadastro("a rejeição exige o nome do engenheiro e o registro profissional (CREA)")
        with self._conexao() as c:
            m = c.execute("SELECT status FROM medidas WHERE id = ?", (medida_id,)).fetchone()
            if m is None:
                raise ErroCadastro(f"medida {medida_id} não existe")
            if m["status"] != "proposta":
                raise ErroCadastro(f"medida {medida_id} está {m['status']}: só proposta pode ser rejeitada")
            c.execute("UPDATE medidas SET status = 'rejeitada', validado_por = ?, registro_validador = ?, validado_em = ?, nota = ? WHERE id = ?",
                      (engenheiro.strip(), registro.strip(), _agora(), motivo, medida_id))
            self._historico(c, medida_id, "rejeitada", f"{engenheiro.strip()} ({registro.strip()})", motivo)
        return self.medida(medida_id)

    def medida(self, medida_id: int) -> dict:
        with self._conexao() as c:
            m = c.execute("SELECT * FROM medidas WHERE id = ?", (medida_id,)).fetchone()
            if m is None:
                raise ErroCadastro(f"medida {medida_id} não existe")
            h = c.execute("SELECT quando, acao, por, nota FROM historico_medidas WHERE medida_id = ? ORDER BY id", (medida_id,)).fetchall()
        d = dict(m)
        d["origem"] = json.loads(d["origem"] or "{}")
        d["historico"] = [dict(x) for x in h]
        return d

    def medidas(self, equipamento_chave: str | None = None, status: str | None = None) -> list[dict]:
        sql, args = "SELECT id FROM medidas WHERE 1 = 1", []
        if equipamento_chave:
            sql += " AND equipamento_chave = ?"
            args.append(equipamento_chave)
        if status:
            sql += " AND status = ?"
            args.append(status)
        with self._conexao() as c:
            ids = [r["id"] for r in c.execute(sql + " ORDER BY equipamento_chave, componente, medida, id", args)]
        return [self.medida(i) for i in ids]

    def referencias(self, equipamento_chave: str) -> list[dict]:
        """Medidas validadas do equipamento: as únicas que podem dar a escala de uma foto."""
        return self.medidas(equipamento_chave, "validada")

    def conferir_fases(self, equipamento_chave: str, tolerancia: float = TOLERANCIA_FASES) -> list[dict]:
        """Componentes da mesma classe e medida em fases diferentes (A, B, C) devem ter o mesmo tamanho.

        Considera propostas e validadas. Devolve um grupo por classe e medida, com a diferença relativa e se
        passa da tolerância; o engenheiro vê isso antes de validar."""
        grupos: dict = {}
        for m in self.medidas(equipamento_chave):
            if m["status"] not in ("proposta", "validada") or not m["classe"] or not m["fase"]:
                continue
            grupos.setdefault((m["classe"], m["medida"]), []).append(m)
        saida = []
        for (classe, medida), ms in sorted(grupos.items()):
            if len({m["fase"] for m in ms}) < 2:
                continue
            valores = [m["valor_cm"] for m in ms]
            ref = statistics.median(valores)
            dif = (max(valores) - min(valores)) / ref
            saida.append({
                "classe": classe, "medida": medida, "diferenca_rel": round(dif, 4), "passa": dif <= tolerancia,
                "fases": [{"id": m["id"], "fase": m["fase"], "componente": m["componente"], "valor_cm": m["valor_cm"],
                           "status": m["status"]} for m in ms],
            })
        return saida
