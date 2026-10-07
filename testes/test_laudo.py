"""Relatório: responsável só do cadastro, várias imagens num PDF, texto profissional com as normas."""

from __future__ import annotations

import json

import numpy as np
import pytest

from app import laudo
from testes.test_servidor import _termograma_flir

RESPONSAVEL = {"nome": "Maria Souza", "funcao": "Engenheira eletricista", "registro": "CREA-PB 123456"}


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    return TestClient(servidor.app)


def cadastrar_responsavel(cliente) -> str:
    c = cliente.put("/api/configuracoes", json={"responsaveis": [RESPONSAVEL]}).json()
    return c["responsavel_padrao"]


def _analisar(cliente, nome="teste.jpg") -> dict:
    r = cliente.post("/api/analises", files={"arquivo": (nome, _termograma_flir(), "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()


def test_laudo_so_sai_com_responsavel_do_cadastro(cliente) -> None:
    a = _analisar(cliente)
    r = cliente.get(f"/api/analises/{a['id']}/laudo.pdf")
    assert r.status_code == 422 and "responsável" in r.json()["erro"]

    id_resp = cadastrar_responsavel(cliente)
    r = cliente.get(f"/api/analises/{a['id']}/laudo.pdf", params={"responsavel": id_resp, "art": "PB2026001"})
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    # responsável fora do cadastro: recusa, em vez de trocar em silêncio pelo padrão
    assert cliente.get(f"/api/analises/{a['id']}/laudo.pdf", params={"responsavel": "naoexiste"}).status_code == 422


def test_relatorio_com_varias_imagens(cliente) -> None:
    ids = [_analisar(cliente, f"foto{i}.jpg")["id"] for i in range(3)]
    id_resp = cadastrar_responsavel(cliente)
    r = cliente.post("/api/laudos", json={"ids": ids, "responsavel": id_resp, "art": "PB2026001"})
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert "3_imagens" in r.headers["content-disposition"]
    assert cliente.post("/api/laudos", json={"ids": []}).status_code == 422
    assert cliente.post("/api/laudos", json={"ids": ["x" * 32]}).status_code == 404


def test_cadastro_valida_e_migra_o_responsavel_antigo(cliente, tmp_path) -> None:
    r = cliente.put("/api/configuracoes", json={"responsaveis": [{"nome": "Sem registro", "registro": ""}]})
    assert r.status_code == 422 and "registro" in r.json()["erro"]

    (tmp_path / "dados_app").mkdir(exist_ok=True)
    (tmp_path / "dados_app" / "config.json").write_text(json.dumps({"responsavel": {"nome": "João Lima", "registro": "CREA-PE 9"}}), encoding="utf-8")
    c = cliente.get("/api/configuracoes").json()
    assert [r["nome"] for r in c["responsaveis"]] == ["João Lima"]
    assert c["responsavel_padrao"] == c["responsaveis"][0]["id"]


def _textos(flowables) -> list[str]:
    from reportlab.platypus import KeepTogether, Paragraph, Table

    saida = []
    for f in flowables:
        if isinstance(f, Paragraph):
            saida.append(f.text)
        elif isinstance(f, Table):
            for linha in f._cellvalues:
                for c in linha:
                    saida += _textos(c if isinstance(c, list) else [c])
        elif isinstance(f, KeepTogether):
            saida += _textos(f._content)
    return saida


def test_texto_profissional_com_normas_e_sem_cara_de_ia(cliente, monkeypatch) -> None:
    from app import servidor

    analises = [_analisar(cliente, f"FLIR{i}.jpg") for i in range(2)]
    itens = [(servidor.armazenamento.obter(a["id"]), servidor.armazenamento.matriz(a["id"]), None) for a in analises]
    capturado = {}

    class Documento:
        def __init__(self, buf, **_):
            self.buf = buf

        def build(self, corpo, **_):
            capturado["corpo"] = corpo
            self.buf.write(b"%PDF-teste")

    monkeypatch.setattr(laudo, "SimpleDocTemplate", Documento)
    laudo.gerar_relatorio(itens, "0.0", empresa={"nome": "Termo Engenharia"}, responsavel=RESPONSAVEL, art="PB2026001")
    texto = " ".join(_textos(capturado["corpo"]))

    for esperado in ("ABNT NBR 15572:2013", "ABNT NBR 15866:2010", "ABNT NBR 15424", "Relatório de inspeção termográfica",
                     "Maria Souza", "CREA-PB 123456", "PB2026001", "Resumo dos resultados", "4.1", "4.2", "Termo Engenharia"):
        assert esperado in texto, esperado
    for proibido in ("detector", "confiança", "rascunho", "gerado automaticamente", "inteligência artificial", "modelo treinado"):
        assert proibido not in texto.lower(), proibido


def test_desenho_numerado_nao_sobrepoe_rotulos() -> None:
    from nucleo import render

    t = np.full((120, 160), 20.0)
    regioes = [{"caixa": [40, 30, 60, 90], "severidade": "normal", "medida": {"t_max": 30, "x_max": 50, "y_max": 40}, "nome": f"R{i}"}
               for i in range(5)]  # cinco caixas iguais: os números precisam achar lugares diferentes
    img = render.desenhar(t, regioes, largura=640, numerar=True)
    assert img.size == (640, 480)
    ocupadas = []
    for _ in range(5):
        lugar = render.posicionar_rotulo(20, 16, (160, 120, 240, 360), ocupadas, (640, 480))
        assert lugar is not None
        ocupadas.append(lugar)
    assert all(not render._sobrepoe(a, b) for i, a in enumerate(ocupadas) for b in ocupadas[i + 1:])


def test_logotipo_da_empresa_no_cabecalho(cliente) -> None:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (1200, 400), (30, 60, 200, 255)).save(buf, format="PNG")
    r = cliente.post("/api/configuracoes/logo", files={"arquivo": ("logo.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200 and r.json()["largura"] == 800  # reduzido para o laudo não pesar
    assert cliente.get("/api/configuracoes").json()["tem_logo"] is True
    assert cliente.get("/api/configuracoes/logo.png").content[:4] == b"\x89PNG"
    a = _analisar(cliente)
    id_resp = cadastrar_responsavel(cliente)
    assert cliente.get(f"/api/analises/{a['id']}/laudo.pdf", params={"responsavel": id_resp}).status_code == 200
    assert cliente.post("/api/configuracoes/logo", files={"arquivo": ("x.png", b"nao e imagem", "image/png")}).status_code == 422
    assert cliente.delete("/api/configuracoes/logo").status_code == 200
    assert cliente.get("/api/configuracoes").json()["tem_logo"] is False
    assert cliente.get("/api/configuracoes/logo.png").status_code == 404
