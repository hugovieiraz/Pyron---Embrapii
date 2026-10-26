"""Fase 4 da medição: /api/medicao e /api/medicao/estado com modelos falsos (não baixa nada)."""

import io
import json

import pytest

from nucleo.medicao import sintetico as s

FOCAL, W, H = 900.0, 1000, 800


def _px(x, y, z):
    return [x / z * FOCAL + W / 2, y / z * FOCAL + H / 2]


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import nucleo.medicao as medicao
    from app import servidor
    from app.armazenamento import Armazenamento

    porta = s.Objeto("porta", (-0.6, 0.0, 3.0), (0.90, 2.10, 0.0))
    regua = s.Objeto("regua", (0.5, 0.3, 2.9), (0.30, 0.035, 0.0))
    cena = s.cena([porta, regua], largura=W, altura=H, focal=FOCAL)
    monkeypatch.setattr(
        medicao, "_padrao", medicao.Medidor(s.ProfundidadeSintetica(cena, 1.05), s.SegmentadorSintetico(cena))
    )
    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    buf = io.BytesIO()
    s.imagem_da_cena(cena).save(buf, format="PNG")
    return TestClient(servidor.app), buf.getvalue()


def _post(cli, foto, pista, referencia=None):
    dados = {"pista": json.dumps(pista)}
    if referencia is not None:
        dados["referencia"] = json.dumps(referencia)
    return cli.post("/api/medicao", files={"arquivo": ("foto.png", foto, "image/png")}, data=dados)


def test_medir_por_ponto(cliente):
    cli, foto = cliente
    r = _post(cli, foto, {"ponto": _px(-0.6, 0.0, 3.0)})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["comprimento_cm"] == pytest.approx(210 * 1.05, rel=0.005)
    assert m["metodo"] == "sem referência"
    assert m["incerteza_cm"]["comprimento"] > 0
    assert m["contorno"]
    assert "total" in m["tempos_ms"]


def test_medir_com_referencia(cliente):
    cli, foto = cliente
    ref = {"ponto": _px(0.5, 0.3, 2.9), "tamanho_cm": 30, "nome": "régua de 30 cm"}
    r = _post(cli, foto, {"ponto": _px(-0.6, 0.0, 3.0)}, ref)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["comprimento_cm"] == pytest.approx(210, rel=0.01)
    assert m["metodo"] == "referência: régua de 30 cm (30 cm)"


def test_medir_dois_pontos(cliente):
    cli, foto = cliente
    r = _post(cli, foto, {"pontos": [_px(-0.6, -1.0, 3.0), _px(-0.6, 1.0, 3.0)]})
    assert r.status_code == 200, r.text
    assert r.json()["distancia_cm"] == pytest.approx(200 * 1.05, rel=0.01)


@pytest.mark.parametrize(
    "pista, referencia",
    [
        ({}, None),
        ({"ponto": [1]}, None),
        ({"caixa": [10, 10, 5, 50]}, None),
        ({"pontos": [[1, 2]]}, None),
        ({"ponto": [500, 400]}, {"ponto": [10, 10]}),  # referência sem tamanho
        ({"ponto": [500, 400]}, {"ponto": [10, 10], "tamanho_cm": -3}),
        ({"ponto": [500, 400]}, {"ponto": [10, 10], "tamanho_cm": 30, "medida": "diagonal"}),
    ],
)
def test_pistas_invalidas(cliente, pista, referencia):
    cli, foto = cliente
    assert _post(cli, foto, pista, referencia).status_code == 422


def test_json_quebrado_e_foto_invalida(cliente):
    cli, foto = cliente
    r = cli.post("/api/medicao", files={"arquivo": ("f.png", foto, "image/png")}, data={"pista": "{nao"})
    assert r.status_code == 422
    r = cli.post("/api/medicao", files={"arquivo": ("f.png", b"nada", "image/png")}, data={"pista": '{"ponto": [1, 1]}'})
    assert r.status_code == 422
    r = cli.post("/api/medicao", files={"arquivo": ("f.png", b"", "image/png")}, data={"pista": '{"ponto": [1, 1]}'})
    assert r.status_code == 422


def test_objeto_nao_encontrado(cliente):
    cli, foto = cliente
    r = _post(cli, foto, {"ponto": [5, 5]})
    assert r.status_code == 422


def test_sem_modelos_responde_503(cliente, monkeypatch):
    import nucleo.medicao as medicao

    cli, foto = cliente

    class SemPacote:
        def estimar(self, *a, **k):
            raise ImportError("No module named 'moge'")

    monkeypatch.setattr(medicao, "_padrao", medicao.Medidor(SemPacote(), None))
    r = _post(cli, foto, {"ponto": [500, 400]})
    assert r.status_code == 503
    assert "moge" in r.json()["erro"]


def test_estado(cliente, tmp_path, monkeypatch):
    cli, _ = cliente
    monkeypatch.setenv("PYRON_MODELOS_MEDICAO", str(tmp_path / "vazia"))
    r = cli.get("/api/medicao/estado")
    assert r.status_code == 200
    e = r.json()
    assert e["pronto"] is False
    assert set(e["profundidade"]) == {"vits", "vitb", "vitl"}
    assert set(e["contorno"]) == {"small", "base-plus"}
    assert e["referencias"]["folha_a4"]["comprimento"] == 29.7
