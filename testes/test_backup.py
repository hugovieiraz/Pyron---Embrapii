"""Backup e restauração: o zip traz tudo o que importa e a restauração guarda o estado anterior."""

from __future__ import annotations

import io
import zipfile

import pytest

from testes.test_servidor import _termograma_flir


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    return TestClient(servidor.app)


def test_backup_e_restauracao_de_ida_e_volta(cliente, tmp_path) -> None:
    enviar = lambda nome: cliente.post("/api/analises", files={"arquivo": (nome, _termograma_flir(), "image/jpeg")},
                                       data={"instalacao": "SE Teste", "equipamento": "TR-01"}).json()
    a = enviar("a.jpg")
    cliente.put("/api/configuracoes", json={"empresa": {"nome": "Termo Ltda.", "subtitulo": ""}})
    (tmp_path / "dados_app" / "videos" / "abc").mkdir(parents=True)
    (tmp_path / "dados_app" / "videos" / "abc" / "original.mp4").write_bytes(b"0" * 1000)

    s = cliente.get("/api/sistema").json()
    assert s["inspecoes"] == 1 and s["bytes"] > 0 and s["bytes_videos"] == 1000

    r = cliente.get("/api/backup.zip")
    assert r.status_code == 200 and "pyron_backup_" in r.headers["content-disposition"]
    nomes = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "inspecoes.sqlite" in nomes and "config.json" in nomes
    assert f"imagens/{a['id']}.jpg" in nomes and f"matrizes/{a['id']}.npy" in nomes
    assert not any(n.startswith("videos/") for n in nomes)  # vídeos ficam de fora (grandes e se refazem)

    # depois do backup: uma inspeção nova e o nome da empresa trocado
    b = enviar("b.jpg")
    cliente.put("/api/configuracoes", json={"empresa": {"nome": "Outra", "subtitulo": ""}})
    assert len(cliente.get("/api/analises").json()) == 2

    rest = cliente.post("/api/backup/restaurar", files={"arquivo": ("backup.zip", r.content, "application/zip")})
    assert rest.status_code == 200, rest.text
    assert rest.json()["inspecoes"] == 1 and "antes_de_restaurar_" in rest.json()["copia_anterior"]
    assert [x["id"] for x in cliente.get("/api/analises").json()] == [a["id"]]
    assert cliente.get(f"/api/analises/{a['id']}").status_code == 200  # matriz e imagem voltaram junto
    assert cliente.get(f"/api/analises/{b['id']}").status_code == 404
    assert cliente.get("/api/configuracoes").json()["empresa"]["nome"] == "Termo Ltda."
    assert len(list((tmp_path / "dados_app" / "backups").glob("antes_de_restaurar_*.zip"))) == 1


def test_restaurar_arquivo_errado_nao_mexe_em_nada(cliente) -> None:
    a = cliente.post("/api/analises", files={"arquivo": ("a.jpg", _termograma_flir(), "image/jpeg")}).json()
    assert cliente.post("/api/backup/restaurar", files={"arquivo": ("x.zip", b"isto nao e zip", "application/zip")}).status_code == 422
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("outra_coisa.txt", "oi")
    r = cliente.post("/api/backup/restaurar", files={"arquivo": ("x.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 422 and "backup do Pyron" in r.json()["erro"]
    assert [x["id"] for x in cliente.get("/api/analises").json()] == [a["id"]]
