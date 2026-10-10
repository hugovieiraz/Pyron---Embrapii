"""Câmera do celular: rotas só do celular (com código), quadros ao vivo e captura virando inspeção."""

from __future__ import annotations

import io
import shutil

import numpy as np
import pytest
from PIL import Image

from app import celular
from nucleo.detectores import Deteccao, Detector


def _jpeg(largura: int = 800, altura: int = 600) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (largura, altura), (200, 80, 30)).save(buf, format="JPEG")
    return buf.getvalue()


class _DetectorImagem(Detector):
    """Acha sempre um para-raio no quarto esquerdo da imagem (em pixels da matriz)."""

    def __init__(self):
        super().__init__("teste-imagem", "Modelo de teste", "aprendizado", "-", "", ["para_raio"],
                         nomes={"para_raio": "Para-raio"}, precisa_imagem=True)

    def detectar(self, temperatura, imagem=None):
        assert imagem is not None  # a caixa sai em pixels da matriz, que pode ser menor que a imagem
        h, w = temperatura.shape
        return [Deteccao("para_raio", [0.0, 0.0, w / 4, h / 2], 0.9)]


def test_ler_imagem_reduz_e_recusa_o_que_nao_e_imagem() -> None:
    rgb = celular.ler_imagem(_jpeg(2560, 1440))
    assert max(rgb.shape[:2]) == celular.LADO_MAXIMO
    with pytest.raises(ValueError):
        celular.ler_imagem(b"isto nao e imagem")
    with pytest.raises(ValueError):
        celular.ler_imagem(b"")


def test_qr_code_le_o_link() -> None:
    import cv2

    link = "https://192.168.0.4:8791/c/AbCdEf12"
    png = np.frombuffer(celular.qr_png(link), dtype=np.uint8)
    lido, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.imdecode(png, cv2.IMREAD_GRAYSCALE))
    assert lido == link


def test_rotas_do_celular_pedem_o_codigo_e_devolvem_caixas_normalizadas(tmp_path) -> None:
    from fastapi.testclient import TestClient

    capturas = []
    modo = celular.ModoCelular(
        tmp_path,
        detectar=lambda rgb: ([{"classe": "para_raio", "nome": "Para-raio", "confianca": 0.9,
                                "caixa": [0.0, 0.0, rgb.shape[1] / 4, rgb.shape[0] / 2]}], {}),
        capturar=lambda dados, nome: capturas.append(nome) or {"id": "x", "regioes": 1},
        modelo=lambda: {"id": "teste", "nome": "Modelo de teste"},
    )
    modo.token = "codigo-certo"
    c = TestClient(celular.criar_app(modo))

    assert c.get("/c/errado").status_code == 404
    assert c.post("/c/errado/quadro", content=_jpeg()).status_code == 404
    pagina = c.get("/c/codigo-certo")
    assert pagina.status_code == 200 and "celular.js" in pagina.text
    assert c.get("/c/codigo-certo/modelo").json()["nome"] == "Modelo de teste"

    r = c.post("/c/codigo-certo/quadro", content=_jpeg(800, 600), headers={"Content-Type": "image/jpeg"})
    assert r.status_code == 200, r.text
    d = r.json()["deteccoes"][0]
    assert d["caixa"] == [0.0, 0.0, 0.25, 0.5]
    assert c.post("/c/codigo-certo/quadro", content=b"lixo").status_code == 422

    assert c.post("/c/codigo-certo/capturar", content=_jpeg()).json()["regioes"] == 1
    assert capturas and capturas[0].startswith("celular_")
    e = modo.estado()
    assert e["ultimo"]["seq"] == 1 and e["capturas"] == 1 and e["ultimo"]["deteccoes"][0]["nome"] == "Para-raio"


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    return TestClient(servidor.app)


def test_sem_modelo_de_imagem_nao_liga(cliente) -> None:
    e = cliente.get("/api/celular").json()
    assert e["ligado"] is False and "erro" in e["modelo"]
    r = cliente.post("/api/celular/ligar")
    assert r.status_code == 409 and "Nenhum modelo" in r.json()["erro"]


def test_captura_do_celular_vira_inspecao_sem_temperatura(cliente, monkeypatch) -> None:
    from app import servidor

    det = _DetectorImagem()
    monkeypatch.setattr(servidor, "_detector_imagem", lambda: det)
    monkeypatch.setattr(servidor, "_detector", lambda _id: det)
    caixas, modelo = servidor._celular_detectar(celular.ler_imagem(_jpeg()))
    assert caixas[0]["nome"] == "Para-raio" and modelo["nome"] == "Modelo de teste"

    resumo = servidor._celular_capturar(_jpeg(), "celular_teste.jpg")
    assert resumo["regioes"] == 1
    a = cliente.get(f"/api/analises/{resumo['id']}").json()
    assert a["fonte"] == "celular"
    assert a["sem_temperatura"] is True and a["resumo"]["severidade"] == "sem_medida"
    assert "celular" in a["metadados"]["aviso"]
    assert a["regioes"][0]["nome"] == "Para-raio 1"


@pytest.mark.skipif(celular._openssl() is None, reason="sem OpenSSL neste computador")
def test_certificado_proprio_carrega_e_e_reaproveitado(tmp_path) -> None:
    import ssl

    cert, chave = celular.certificado(tmp_path, "192.168.0.4")
    ssl.create_default_context(ssl.Purpose.CLIENT_AUTH).load_cert_chain(cert, chave)
    antes = cert.stat().st_mtime_ns
    assert celular.certificado(tmp_path, "192.168.0.4")[0].stat().st_mtime_ns == antes  # mesmo endereço: o mesmo
    celular.certificado(tmp_path, "10.0.0.7")
    assert (tmp_path / "endereco.txt").read_text(encoding="utf-8") == "10.0.0.7"
    shutil.rmtree(tmp_path, ignore_errors=True)
