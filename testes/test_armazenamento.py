"""Armazém de objetos e esquema versionado do banco (tabelas derivadas do JSON)."""

import json
import sqlite3

import numpy as np
import pytest

from app import objetos
from app.armazenamento import VERSAO_ESQUEMA, Armazenamento


def _analise(id_="a1", sev="urgente", instalacao="SE Campina Grande II", equipamento="TR-01", **extra):
    return {
        "id": id_,
        "criado_em": "2026-10-01T10:00:00",
        "arquivo": f"{id_}.jpg",
        "fonte": "manual",
        "radiometrica": True,
        "metadados": {"camera": "FLIR C5", "data_hora": "2026-09-30 14:05:00", "emissividade": 0.95,
                      "distancia_m": 3.0, "temp_refletida_c": 20.0, "resolucao_sensor": "160×120"},
        "modelo": {"nome": "pontos-quentes"},
        "condicoes": {"ambiente_c": 25.0, "carga_pct": 80.0},
        "identificacao": {"instalacao": instalacao, "equipamento": equipamento},
        "regioes": [
            {"id": "r1", "nome": "Conexão A", "classe": "conexao", "caixa": [1, 2, 10, 12], "origem": "modelo",
             "confianca": 0.9, "medida": {"t_max": 88.5, "t_med": 60.0, "t_min": 40.0, "x_max": 5, "y_max": 6, "pixels": 90},
             "dt_corrigido": 22.0, "pct_mta": 98.3, "severidade": sev},
            {"id": "r2", "nome": "Sem medida", "classe": "conexao", "caixa": [0, 0, 1, 1], "medida": None, "severidade": "sem_medida"},
        ],
        "resumo": {"severidade": sev, "t_max_cena": 88.5, "t_min_cena": 18.0, "maior_pct_mta": 98.3},
        **extra,
    }


def _linhas(arm, sql, *args):
    with arm._conexao() as c:
        return c.execute(sql, args).fetchall()


# ---------------------------------------------------------------- armazém de objetos


def test_armazem_local_grava_le_apaga_e_devolve_sha(tmp_path):
    arm = objetos.ArmazemLocal(tmp_path)
    ficha = arm.gravar("imagens/x.jpg", b"abc")
    assert ficha == {"chave": "imagens/x.jpg", "bytes": 3,
                     "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"}
    assert (tmp_path / "imagens" / "x.jpg").read_bytes() == b"abc"
    assert not list(tmp_path.rglob("*.tmp"))
    assert arm.ler("imagens/x.jpg") == b"abc" and arm.ler("imagens/nada.jpg") is None
    arm.apagar("imagens/x.jpg")
    arm.apagar("imagens/x.jpg")  # apagar o que não existe não é erro
    assert arm.ler("imagens/x.jpg") is None


@pytest.mark.parametrize("chave", ["", "/abs.jpg", "../fora.jpg", "a/../../b", "a\\b.jpg", "a//b"])
def test_chave_que_sai_da_pasta_e_recusada(tmp_path, chave):
    with pytest.raises(ValueError):
        objetos.ArmazemLocal(tmp_path).gravar(chave, b"x")


class _ErroS3(Exception):
    def __init__(self, codigo):
        self.response = {"Error": {"Code": codigo}}


class _ClienteFalso:
    """O mínimo do cliente boto3 que o ArmazemS3 usa."""

    def __init__(self):
        self.objetos = {}

    def put_object(self, Bucket, Key, Body, Metadata):
        self.objetos[(Bucket, Key)] = (Body, Metadata)

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objetos:
            raise _ErroS3("NoSuchKey")
        corpo = self.objetos[(Bucket, Key)][0]
        return {"Body": type("B", (), {"read": lambda self: corpo})()}

    def delete_object(self, Bucket, Key):
        self.objetos.pop((Bucket, Key), None)


def test_armazem_s3_usa_prefixo_e_guarda_o_sha(tmp_path):
    cliente = _ClienteFalso()
    s3 = objetos.ArmazemS3("pyron", "/campo/se01/", cliente=cliente)
    ficha = s3.gravar("matrizes/a.npy", b"123")
    corpo, meta = cliente.objetos[("pyron", "campo/se01/matrizes/a.npy")]
    assert corpo == b"123" and meta["sha256"] == ficha["sha256"]
    assert s3.ler("matrizes/a.npy") == b"123" and s3.ler("matrizes/b.npy") is None
    s3.apagar("matrizes/a.npy")
    assert s3.ler("matrizes/a.npy") is None
    assert s3.descricao() == "s3://pyron/campo/se01"


def test_armazem_s3_nao_esconde_outros_erros():
    class Negado(_ClienteFalso):
        def get_object(self, Bucket, Key):
            raise _ErroS3("AccessDenied")

    with pytest.raises(_ErroS3):
        objetos.ArmazemS3("pyron", cliente=Negado()).ler("imagens/a.jpg")


def test_escolha_do_armazem_pelo_ambiente(tmp_path, monkeypatch):
    monkeypatch.delenv("PYRON_OBJETOS", raising=False)
    assert isinstance(objetos.do_ambiente(tmp_path), objetos.ArmazemLocal)
    monkeypatch.setenv("PYRON_OBJETOS", "local")
    assert isinstance(objetos.do_ambiente(tmp_path), objetos.ArmazemLocal)
    for invalido in ("ftp://x", "s3://"):
        monkeypatch.setenv("PYRON_OBJETOS", invalido)
        with pytest.raises(ValueError):
            objetos.do_ambiente(tmp_path)


def test_matriz_vai_e_volta_em_float32_com_nan():
    m = np.array([[1.5, np.nan], [3.25, -4.0]], dtype=np.float64)
    volta = objetos.bytes_para_matriz(objetos.matriz_para_bytes(m))
    assert volta.dtype == np.float32
    np.testing.assert_array_equal(volta, m.astype(np.float32))


# ---------------------------------------------------------------- armazenamento sobre um armazém qualquer


def test_armazenamento_funciona_sobre_s3(tmp_path):
    arm = Armazenamento(tmp_path, armazem=objetos.ArmazemS3("b", cliente=_ClienteFalso()))
    matriz = np.full((4, 5), 30.0)
    arm.salvar(_analise(), original=b"jpeg", matriz=matriz)
    arm.salvar_foto("a1", b"foto")
    assert arm.original("a1") == b"jpeg" and arm.foto("a1") == b"foto"
    np.testing.assert_array_equal(arm.matriz("a1"), matriz.astype(np.float32))
    assert not (tmp_path / "imagens").exists()  # nada em disco além do banco
    assert arm.apagar("a1") and arm.original("a1") is None and arm.matriz("a1") is None


# ---------------------------------------------------------------- tabelas derivadas


def test_salvar_preenche_as_tabelas_derivadas(tmp_path):
    arm = Armazenamento(tmp_path)
    arm.salvar(_analise(), original=b"jpeg", matriz=np.zeros((3, 3)))
    arm.salvar_foto("a1", b"foto")

    (linha,) = _linhas(arm, "SELECT capturado_em, fonte, radiometrica, modelo, t_max_cena, maior_pct_mta, ambiente_c, carga_pct "
                            "FROM analises")
    assert linha == ("2026-09-30T14:05:00", "manual", 1, "pontos-quentes", 88.5, 98.3, 25.0, 80.0)

    assert _linhas(arm, "SELECT chave, instalacao, equipamento, inspecoes FROM vw_equipamentos") == [
        ("se-campina-grande-ii--tr-01", "SE Campina Grande II", "TR-01", 1)]

    regioes = _linhas(arm, "SELECT ordem, regiao_id, classe, x0, y1, t_max, pct_mta, severidade FROM regioes ORDER BY ordem")
    assert regioes == [(0, "r1", "conexao", 1.0, 12.0, 88.5, 98.3, "urgente"),
                       (1, "r2", "conexao", 0.0, 1.0, None, None, "sem_medida")]

    assert _linhas(arm, "SELECT camera, emissividade, distancia_m FROM parametros_medicao") == [("FLIR C5", 0.95, 3.0)]

    # urgente: prazo padrão de 7 dias a partir da captura
    assert _linhas(arm, "SELECT severidade, status, prazo, prazo_padrao FROM pendencias") == [
        ("urgente", "aberta", "2026-10-07", 1)]

    arquivos = _linhas(arm, "SELECT chave, tipo, bytes FROM arquivos ORDER BY chave")
    assert arquivos == [("imagens/a1.jpg", "original", 4), ("imagens/a1_foto.jpg", "foto", 4),
                        ("matrizes/a1.npy", "matriz", len(objetos.matriz_para_bytes(np.zeros((3, 3)))))]


def test_regravar_atualiza_sem_duplicar_e_normal_nao_tem_pendencia(tmp_path):
    arm = Armazenamento(tmp_path)
    arm.salvar(_analise())
    a = _analise(sev="normal")
    a["regioes"] = a["regioes"][:1]
    arm.salvar(a)
    assert _linhas(arm, "SELECT COUNT(*) FROM regioes") == [(1,)]
    assert _linhas(arm, "SELECT COUNT(*) FROM pendencias") == [(0,)]
    assert _linhas(arm, "SELECT severidade FROM analises") == [("normal",)]


def test_mesma_instalacao_com_grafia_diferente_e_um_cadastro_so(tmp_path):
    arm = Armazenamento(tmp_path)
    arm.salvar(_analise("a1", instalacao="SE Campina Grande II", equipamento="TR-01"))
    arm.salvar(_analise("a2", instalacao="se campina grande ii", equipamento="tr-01"))
    arm.salvar(_analise("a3", instalacao="SE Campina Grande II", equipamento="TR-02"))
    arm.salvar(_analise("a4", instalacao="", equipamento=""))
    assert _linhas(arm, "SELECT COUNT(*) FROM instalacoes") == [(1,)]
    assert _linhas(arm, "SELECT chave, inspecoes FROM vw_equipamentos ORDER BY chave") == [
        ("se-campina-grande-ii--tr-01", 2), ("se-campina-grande-ii--tr-02", 1)]
    assert _linhas(arm, "SELECT equipamento_id FROM analises WHERE id = 'a4'") == [(None,)]


def test_acompanhamento_vira_pendencia_e_historico(tmp_path):
    arm = Armazenamento(tmp_path)
    ac = {"status": "programada", "prazo": "2026-10-20", "ordem_servico": "OS-123", "responsavel": "Ana",
          "historico": [{"quando": "2026-10-02T09:00:00", "status": "programada", "nota": "peça pedida"}]}
    arm.salvar(_analise(acompanhamento=ac))
    assert _linhas(arm, "SELECT status, prazo, prazo_padrao, ordem_servico, responsavel FROM pendencias") == [
        ("programada", "2026-10-20", 0, "OS-123", "Ana")]
    assert _linhas(arm, "SELECT quando, status, nota FROM historico_pendencias") == [
        ("2026-10-02T09:00:00", "programada", "peça pedida")]


def test_apagar_leva_as_derivadas_junto(tmp_path):
    arm = Armazenamento(tmp_path)
    arm.salvar(_analise(), original=b"x", matriz=np.zeros((2, 2)))
    assert arm.apagar("a1")
    for tabela in ("analises", "regioes", "parametros_medicao", "pendencias", "arquivos"):
        assert _linhas(arm, f"SELECT COUNT(*) FROM {tabela}") == [(0,)], tabela
    assert not list((tmp_path / "imagens").iterdir()) and not list((tmp_path / "matrizes").iterdir())


def test_alerta_ganha_colunas(tmp_path):
    arm = Armazenamento(tmp_path)
    arm.salvar_alerta({"id": "al1", "criado_em": "2026-10-01T10:00:00", "status": "pendente",
                       "analise_id": "a1", "severidade": "imediato"})
    assert _linhas(arm, "SELECT analise_id, severidade, status FROM alertas") == [("a1", "imediato", "pendente")]


def test_conferir_arquivos_acha_ausente_e_alterado(tmp_path):
    arm = Armazenamento(tmp_path)
    arm.salvar(_analise(), original=b"original", matriz=np.zeros((2, 2)))
    assert arm.conferir_arquivos() == []
    (tmp_path / "imagens" / "a1.jpg").write_bytes(b"mexido")
    (tmp_path / "matrizes" / "a1.npy").unlink()
    assert {(p["chave"], p["problema"]) for p in arm.conferir_arquivos()} == {
        ("imagens/a1.jpg", "alterado"), ("matrizes/a1.npy", "ausente")}


# ---------------------------------------------------------------- migração de um banco antigo


def _banco_v1(pasta, analises=(), alertas=()):
    """Banco como o Pyron 0.7.7 grava: duas tabelas, JSON em ``dados``, user_version 0."""
    pasta.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(pasta / "inspecoes.sqlite")
    c.execute("CREATE TABLE analises (id TEXT PRIMARY KEY, criado_em TEXT, nome TEXT, severidade TEXT, dados TEXT)")
    c.execute("CREATE TABLE alertas (id TEXT PRIMARY KEY, criado_em TEXT, status TEXT, dados TEXT)")
    for a in analises:
        c.execute("INSERT INTO analises VALUES (?, ?, ?, ?, ?)",
                  (a["id"], a["criado_em"], a["arquivo"], a["resumo"]["severidade"], json.dumps(a)))
    for al in alertas:
        c.execute("INSERT INTO alertas VALUES (?, ?, ?, ?)", (al["id"], al["criado_em"], al["status"], json.dumps(al)))
    c.commit()
    c.close()


def test_banco_antigo_e_migrado_e_reindexado_ao_abrir(tmp_path):
    pasta = tmp_path / "dados_app"
    _banco_v1(pasta, [_analise("a1"), _analise("a2", sev="normal")],
              [{"id": "al1", "criado_em": "2026-10-01T10:00:00", "status": "enviado", "analise_id": "a1", "severidade": "urgente"}])
    (pasta / "imagens").mkdir()
    (pasta / "imagens" / "a1.jpg").write_bytes(b"jpeg antigo")

    arm = Armazenamento(pasta)
    assert _linhas(arm, "PRAGMA user_version") == [(VERSAO_ESQUEMA,)]
    assert arm.obter("a1")["id"] == "a1" and len(arm.listar()) == 2  # o JSON continua lá, intacto
    assert _linhas(arm, "SELECT COUNT(*) FROM regioes") == [(4,)]
    assert _linhas(arm, "SELECT analise_id FROM pendencias") == [("a1",)]
    assert _linhas(arm, "SELECT analise_id, severidade FROM alertas") == [("a1", "urgente")]
    assert _linhas(arm, "SELECT chave, bytes FROM arquivos") == [("imagens/a1.jpg", 11)]

    Armazenamento(pasta)  # abrir de novo não migra outra vez nem duplica
    assert _linhas(arm, "SELECT COUNT(*) FROM regioes") == [(4,)]


def test_restaurar_backup_antigo_migra_na_proxima_conexao(tmp_path):
    """O backup troca o banco por dentro: um .zip da versão anterior chega com user_version 0."""
    pasta = tmp_path / "dados_app"
    arm = Armazenamento(pasta)
    antigo = tmp_path / "antigo"
    _banco_v1(antigo, [_analise("velha")])
    src, dst = sqlite3.connect(antigo / "inspecoes.sqlite"), sqlite3.connect(pasta / "inspecoes.sqlite")
    src.backup(dst)
    src.close()
    dst.close()
    assert [it["id"] for it in arm.listar()] == ["velha"]
    assert _linhas(arm, "SELECT analise_id FROM pendencias") == [("velha",)]


def test_reindexar_conserta_o_que_um_pyron_antigo_gravou(tmp_path):
    arm = Armazenamento(tmp_path)
    arm.salvar(_analise(sev="urgente"))
    # Pyron 0.7.7 regravando o JSON direto (sem saber das tabelas novas)
    novo = _analise(sev="normal")
    c = sqlite3.connect(arm.banco)
    c.execute("INSERT OR REPLACE INTO analises (id, criado_em, nome, severidade, dados) VALUES (?, ?, ?, ?, ?)",
              ("a1", novo["criado_em"], novo["arquivo"], "normal", json.dumps(novo)))
    c.commit()
    c.close()
    assert arm.reindexar() == 1
    assert _linhas(arm, "SELECT COUNT(*) FROM pendencias") == [(0,)]
    assert _linhas(arm, "SELECT severidade FROM regioes WHERE ordem = 0") == [("normal",)]

