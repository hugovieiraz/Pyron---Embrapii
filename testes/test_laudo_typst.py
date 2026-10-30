"""Laudo em Typst (0.9, F3): mesmas assinaturas, as duas rotas nos dois motores, injeção, fontes e limpeza."""

from __future__ import annotations

import inspect
import json
import tempfile
from pathlib import Path

import pytest

typst = pytest.importorskip("typst")  # sem o pacote (ou com a DLL barrada), o reportlab continua sendo o motor

from app import laudo, laudo_typst  # noqa: E402

MALICIOSOS = [
    '#panic("injetado")',
    "$x^2$ e $ $",
    "@referencia <rotulo>",
    "] #[ ] fecha e abre ]]",
    "barra \\ invertida \\n",
    "```python\nimport os\n``` e `crase`",
    '#import "/dados.json"',
    '#read("/dados.json")',
    "*negrito* _itálico_ = título // comentário /* bloco",
    "#let x = 1; #x #{ panic() }",
]


def test_mesmas_assinaturas_do_reportlab() -> None:
    for nome in ("gerar", "gerar_relatorio"):
        assert inspect.signature(getattr(laudo, nome)) == inspect.signature(getattr(laudo_typst, nome)), nome


def test_typst_disponivel_e_so_fontes_do_projeto() -> None:
    assert laudo_typst.disponivel() is None
    fontes = typst.Fonts(include_system_fonts=False, include_embedded_fonts=False, font_paths=[str(laudo_typst.FONTES)])
    assert set(fontes.families()) == {"Noto Sans", "Noto Sans Math"}
    for licenca in ("OFL-NotoSans.txt", "OFL-NotoSansMath.txt"):
        assert "SIL Open Font License" in (laudo_typst.FONTES / licenca).read_text(encoding="utf-8")


def test_modelo_nunca_avalia_texto() -> None:
    """O modelo lê os dados com json() e não usa eval: texto do usuário nunca vira código Typst."""
    for arq in [laudo_typst.PASTA / laudo_typst.MODELO, *(laudo_typst.PASTA / "partes").glob("*.typ")]:
        codigo = arq.read_text(encoding="utf-8")
        assert "eval(" not in codigo and "sys.inputs" not in codigo, arq.name
    assert 'json("dados.json")' in (laudo_typst.PASTA / laudo_typst.MODELO).read_text(encoding="utf-8")


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    c = TestClient(servidor.app)
    c.put("/api/configuracoes", json={"responsaveis": [{"nome": "Maria Souza", "registro": "CREA-PB 123456", "funcao": "Engenheira"}]})
    return c


def _inspecao(cliente) -> dict:
    from testes.test_servidor import _termograma_flir

    r = cliente.post("/api/analises", files={"arquivo": ("teste.jpg", _termograma_flir(), "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()


def _motor(pdf: bytes) -> str:
    assert pdf[:4] == b"%PDF"
    return "typst" if b"Typst" in pdf and b"NotoSans" in pdf else "reportlab" if b"ReportLab" in pdf else "?"


def test_as_duas_rotas_nos_dois_motores(cliente) -> None:
    a, b = _inspecao(cliente), _inspecao(cliente)
    for motor in ("reportlab", "typst"):
        assert cliente.put("/api/configuracoes", json={"laudo": {"motor": motor}}).status_code == 200
        assert cliente.get("/api/configuracoes").json()["laudo"] == {"motor": motor}
        um = cliente.get(f"/api/analises/{a['id']}/laudo.pdf")
        assert um.status_code == 200 and _motor(um.content) == motor
        varios = cliente.post("/api/laudos", json={"ids": [a["id"], b["id"]]})
        assert varios.status_code == 200 and _motor(varios.content) == motor
    assert cliente.put("/api/configuracoes", json={"laudo": {"motor": "word"}}).status_code == 422


def test_padrao_e_typst_e_typst_barrado_cai_no_reportlab(cliente, monkeypatch) -> None:
    a = _inspecao(cliente)
    assert cliente.get("/api/configuracoes").json()["laudo"] == {"motor": "typst"}
    assert _motor(cliente.get(f"/api/analises/{a['id']}/laudo.pdf").content) == "typst"
    monkeypatch.setattr(laudo_typst, "disponivel", lambda: "OSError: DLL barrada")
    assert _motor(cliente.get(f"/api/analises/{a['id']}/laudo.pdf").content) == "reportlab"
    assert cliente.put("/api/configuracoes", json={"laudo": {"motor": "typst"}}).status_code == 422


def test_texto_malicioso_nao_executa(cliente) -> None:
    """Se algum texto fosse colado no código Typst, o #panic pararia a compilação e os colchetes soltos a quebrariam."""
    a = _inspecao(cliente)
    regioes = [{**{k: r[k] for k in ("id", "caixa", "classe", "origem")}, "nome": MALICIOSOS[i % len(MALICIOSOS)][:60]}
               for i, r in enumerate(a["regioes"])]
    texto = " | ".join(MALICIOSOS)
    r = cliente.put(f"/api/analises/{a['id']}", json={"regioes": regioes, "identificacao": {
        "instalacao": MALICIOSOS[0], "equipamento": MALICIOSOS[3], "observacoes": texto[:300]}})
    assert r.status_code == 200, r.text
    cliente.put("/api/configuracoes", json={"empresa": {"nome": MALICIOSOS[8][:120], "subtitulo": MALICIOSOS[2]},
                                            "responsaveis": [{"nome": MALICIOSOS[6], "registro": MALICIOSOS[4][:60], "funcao": "x"}],
                                            "laudo": {"motor": "typst"}})
    pdf = cliente.get(f"/api/analises/{a['id']}/laudo.pdf?art=" + "%23panic(%22art%22)")
    assert pdf.status_code == 200, pdf.text
    assert _motor(pdf.content) == "typst"
    varios = cliente.post("/api/laudos", json={"ids": [a["id"]], "art": '#panic("art")]'})
    assert varios.status_code == 200 and _motor(varios.content) == "typst"


def test_dados_ficam_como_texto_no_json(tmp_path) -> None:
    """O montador entrega os textos sem escapar nem marcar: quem garante o literal é o modelo (string do JSON)."""
    import numpy as np

    a = {"id": "abc", "arquivo": "x.jpg", "criado_em": "2026-10-30T10:00:00", "metadados": {}, "condicoes": {}, "regioes": [],
         "identificacao": {"equipamento": MALICIOSOS[0], "observacoes": MALICIOSOS[5]},
         "resumo": {"severidade": "normal", "severidade_rotulo": "Normal", "avisos": []}}
    dados = laudo_typst.montar_dados([(a, np.full((10, 10), 25.0), None)], "0.9", {"nome": MALICIOSOS[1]}, None, None, None, None, tmp_path)
    texto = json.dumps(dados, ensure_ascii=False)
    assert MALICIOSOS[0].replace('"', '\\"') in texto and dados["empresa"]["nome"] == MALICIOSOS[1]
    assert dados["registros"][0]["titulo"] == MALICIOSOS[0]
    assert MALICIOSOS[5] in dados["registros"][0]["observacoes"]


def test_pasta_temporaria_apagada_e_codigo_de_conferencia(cliente) -> None:
    from app import servidor

    a = _inspecao(cliente)
    antes = set(Path(tempfile.gettempdir()).glob("pyron-laudo-*"))
    item = servidor.armazenamento.obter(a["id"])
    matriz = servidor.armazenamento.matriz(a["id"])
    pdf = laudo_typst.gerar(item, matriz, None, "0.9", responsavel={"nome": "Maria", "registro": "CREA 1"})
    assert pdf[:4] == b"%PDF"
    assert set(Path(tempfile.gettempdir()).glob("pyron-laudo-*")) == antes
    c1 = laudo_typst.codigo_conferencia([(item, matriz, None)], {"nome": "Maria", "registro": "CREA 1"})
    c2 = laudo_typst.codigo_conferencia([(item, matriz, None)], {"nome": "Maria", "registro": "CREA 2"})
    assert len(c1) == 64 and c1 != c2  # muda quem assina, muda o código
