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
    assert set(e["profundidade"]) == {"vits", "vitb", "vitl", "da3"}
    assert set(e["contorno"]) == {"small", "base-plus"}
    assert e["referencias"]["folha_a4"]["comprimento"] == 29.7


def test_medir_pelo_plano_da_referencia_sem_modelo(cliente):
    cli, _ = cliente
    # A4 de frente a 1 m com focal 1000: 297 × 210 px; pontos a 500 px de distância = 50 cm
    cantos = [[100, 100], [397, 100], [397, 310], [100, 310]]
    r = cli.post("/api/medicao/plano", json={"cantos": cantos, "tamanho_cm": [29.7, 21.0], "pontos": [[100, 400], [600, 400]]})
    assert r.status_code == 200, r.text
    assert r.json()["distancia_cm"] == pytest.approx(50.0, rel=1e-3)
    for corpo in ({"cantos": cantos[:3], "tamanho_cm": [29.7, 21], "pontos": [[0, 0], [1, 1]]},
                  {"cantos": cantos, "tamanho_cm": [29.7], "pontos": [[0, 0], [1, 1]]},
                  {"cantos": cantos, "tamanho_cm": [29.7, 21], "pontos": [[0, 0]]},
                  {"cantos": [[0, 0], [1, 0], [2, 0], [3, 0]], "tamanho_cm": [29.7, 21], "pontos": [[0, 0], [1, 1]]}):
        assert cli.post("/api/medicao/plano", json=corpo).status_code == 422


def test_referencia_automatica_e_por_cantos_validadas(cliente):
    from app import servidor

    v = servidor._validar_pista_medicao({"auto": "postit_rosa"}, "a referência", exige_tamanho=True)
    assert v == {"auto": "postit_rosa", "tamanho_cm": 7.6, "medida": "lado", "nome": ""}
    v = servidor._validar_pista_medicao({"auto": "postit_rosa", "tamanho_cm": 7.5}, "a referência", exige_tamanho=True)
    assert v["tamanho_cm"] == 7.5
    v = servidor._validar_pista_medicao({"cantos": [[0, 0], [10, 0], [10, 7], [0, 7]], "tamanho_cm": 29.7, "outro_lado_cm": 21},
                                         "a referência", exige_tamanho=True)
    assert v["medida"] == "lado" and v["outro_lado_cm"] == 21 and len(v["cantos"]) == 4
    cli, foto = cliente
    assert _post(cli, foto, {"ponto": [500, 400]}, {"auto": "nao_existe"}).status_code == 422
    assert _post(cli, foto, {"ponto": [500, 400]}, {"cantos": [[0, 0]], "tamanho_cm": 8}).status_code == 422
    # foto sintética sem post-it rosa: 422 com o motivo
    r = _post(cli, foto, {"ponto": _px(-0.6, 0.0, 3.0)}, {"auto": "postit_rosa"})
    assert r.status_code == 422 and "não achei" in r.json()["erro"]
    assert "postit_rosa" in cli.get("/api/medicao/estado").json()["referencias_auto"]


def test_achar_referencia_na_foto(cliente):
    import numpy as np
    from PIL import Image

    cli, foto = cliente
    img = np.full((300, 400, 3), 120, np.uint8)
    img[100:180, 150:230] = (236, 64, 150)  # post-it rosa de 80 × 80 px
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    r = cli.post("/api/medicao/referencia", files={"arquivo": ("p.png", buf.getvalue(), "image/png")}, data={"tipo": "postit_rosa"})
    assert r.status_code == 200, r.text
    c = np.array(r.json()["cantos"])
    assert np.abs(c - [[149.5, 99.5], [229.5, 99.5], [229.5, 179.5], [149.5, 179.5]]).max() < 0.6
    r = cli.post("/api/medicao/referencia", files={"arquivo": ("f.png", foto, "image/png")}, data={"tipo": "postit_rosa"})
    assert r.status_code == 422
    r = cli.post("/api/medicao/referencia", files={"arquivo": ("f.png", foto, "image/png")}, data={"tipo": "outro"})
    assert r.status_code == 422


@pytest.fixture()
def comparacao(cliente, monkeypatch):
    """Dois modelos falsos: o "da3" vê a cena 5 % maior; o "moge", 10 % menor."""
    import nucleo.medicao as medicao
    from nucleo.medicao import modelos

    porta = s.Objeto("porta", (-0.6, 0.0, 3.0), (0.90, 2.10, 0.0))
    regua = s.Objeto("regua", (0.5, 0.3, 2.9), (0.30, 0.035, 0.0))
    cena = s.cena([porta, regua], largura=W, altura=H, focal=FOCAL)
    seg = s.SegmentadorSintetico(cena)
    monkeypatch.setattr(medicao, "_por_modelo", {"da3": medicao.Medidor(s.ProfundidadeSintetica(cena, 1.05), seg),
                                                  "moge": medicao.Medidor(s.ProfundidadeSintetica(cena, 0.90), seg)})
    monkeypatch.setattr(modelos, "disponiveis", lambda: [{"id": "da3", "nome": "DA3", "instalado": True},
                                                         {"id": "moge", "nome": "MoGe", "instalado": True}])
    return cliente


def test_comparar_os_dois_modelos_e_registrar(comparacao):
    cli, foto = comparacao
    ref = {"ponto": _px(0.5, 0.3, 2.9), "tamanho_cm": 30, "nome": "régua"}
    r = cli.post("/api/medicao/comparar", files={"arquivo": ("f.png", foto, "image/png")},
                 data={"pista": json.dumps({"ponto": _px(-0.6, 0.0, 3.0)}), "referencia": json.dumps(ref)})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["resultados"]["da3"]["sem_referencia"]["comprimento_cm"] == pytest.approx(210 * 1.05, rel=0.005)
    assert d["resultados"]["moge"]["sem_referencia"]["comprimento_cm"] == pytest.approx(210 * 0.90, rel=0.005)
    for modelo in ("da3", "moge"):  # com a régua, os dois corrigem a escala
        assert d["resultados"][modelo]["com_referencia"]["comprimento_cm"] == pytest.approx(210, rel=0.01)
    assert d["contorno"] and d["contorno_referencia"] and d["id"] and d["foto"]

    # a foto fica guardada sem nenhuma alteração
    assert cli.get(f"/api/medicao/fotos/{d['foto']}").content == foto

    # valor real informado: o registro calcula o erro de cada modelo e o resumo
    r = cli.put(f"/api/medicao/registro/{d['id']}", json={"real": {"comprimento": 210}})
    assert r.status_code == 200, r.text
    assert r.json()["erros"]["moge"]["sem_referencia"]["comprimento"] == pytest.approx(-0.10, abs=0.005)
    reg = cli.get("/api/medicao/registro").json()
    assert reg["entradas"][0]["id"] == d["id"] and reg["entradas"][0]["real"] == {"comprimento": 210.0}
    assert reg["resumo"]["da3"]["sem_referencia"]["erro_mediano_pct"] == pytest.approx(5.0, abs=0.5)
    assert reg["resumo"]["moge"]["com_referencia"]["n"] == 1
    assert cli.put("/api/medicao/registro/nao-existe", json={"real": {"comprimento": 1}}).status_code == 404


def test_comparar_dois_pontos_sem_referencia(comparacao):
    cli, foto = comparacao
    r = cli.post("/api/medicao/comparar", files={"arquivo": ("f.png", foto, "image/png")},
                 data={"pista": json.dumps({"pontos": [_px(-0.6, -1.0, 3.0), _px(-0.6, 1.0, 3.0)]})})
    assert r.status_code == 200, r.text
    res = r.json()["resultados"]
    assert res["da3"]["sem_referencia"]["distancia_cm"] == pytest.approx(200 * 1.05, rel=0.01)
    assert res["moge"]["com_referencia"] is None
