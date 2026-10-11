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


def _termograma_na_sala() -> bytes:
    """Termograma arco-íris sintético (o dos testes da paleta) no meio de uma sala escura."""
    from testes.test_paleta import _cena, _imagem_sintetica

    sala = np.full((1280, 720, 3), (60, 54, 48), np.uint8)
    sala[400:880, 40:680] = _imagem_sintetica(50.0, 10.0, _cena())
    buf = io.BytesIO()
    Image.fromarray(sala).save(buf, format="JPEG", quality=92)
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
                                "caixa": [0.0, 0.0, rgb.shape[1] / 4, rgb.shape[0] / 2]}],
                              {"area": [0, 0, rgb.shape[1], rgb.shape[0]]}),
        capturar=lambda dados, nome: capturas.append(nome) or {"id": "x", "regioes": 1},
        modelo=lambda: {"id": "teste", "nome": "Modelo de teste"},
    )
    modo.token = "codigo-certo"
    c = TestClient(celular.criar_app(modo))

    assert c.get("/c/errado").status_code == 404
    assert c.post("/c/errado/quadro", content=_jpeg()).status_code == 404
    pagina = c.get("/c/codigo-certo")
    assert pagina.status_code == 200 and "celular.js" in pagina.text
    assert c.get("/e/celular.js").headers["cache-control"] == "no-cache"  # o celular sempre confere a versão
    assert c.get("/c/codigo-certo/modelo").json()["nome"] == "Modelo de teste"

    r = c.post("/c/codigo-certo/quadro", content=_jpeg(800, 600), headers={"Content-Type": "image/jpeg"})
    assert r.status_code == 200, r.text
    assert r.json()["deteccoes"] == [] and r.json()["area"] == [0.0, 0.0, 1.0, 1.0]  # um quadro só não confirma
    r = c.post("/c/codigo-certo/quadro", content=_jpeg(800, 600), headers={"Content-Type": "image/jpeg"})
    d = r.json()["deteccoes"][0]
    assert d["caixa"] == [0.0, 0.0, 0.25, 0.5]
    assert c.post("/c/codigo-certo/quadro", content=b"lixo").status_code == 422

    assert c.post("/c/codigo-certo/capturar", content=_jpeg()).json()["regioes"] == 1
    assert capturas and capturas[0].startswith("celular_")
    e = modo.estado()
    assert e["ultimo"]["seq"] == 2 and e["capturas"] == 1 and e["ultimo"]["deteccoes"][0]["nome"] == "Para-raio"


def _modo(tmp_path, espera_s: float = 0.0) -> celular.ModoCelular:
    """Modo celular com um detector que acha um para-raio no quarto esquerdo de qualquer quadro."""
    import time

    def detectar(rgb):
        time.sleep(espera_s)
        return ([{"classe": "para_raio", "nome": "Para-raio", "confianca": 0.9,
                  "caixa": [0.0, 0.0, rgb.shape[1] / 4, rgb.shape[0] / 2]}], {"area": [0, 0, rgb.shape[1], rgb.shape[0]]})

    modo = celular.ModoCelular(tmp_path, detectar=detectar, capturar=None, modelo=lambda: {"id": "teste", "nome": "Teste"})
    modo.token = "codigo-certo"
    return modo


def test_cabecalho_do_quadro_vai_e_volta() -> None:
    dados = celular.cabecalho(7, {"x": 0.125, "y": -0.25, "trecho": 3}) + b"jpeg"
    assert celular.ler_cabecalho(dados) == (7, {"x": 0.125, "y": -0.25, "trecho": 3})
    assert celular.ler_cabecalho(celular.cabecalho(8, None)) == (8, None)  # sem rastro (envio por HTTP)


def test_transmissao_por_websocket_responde_com_o_quadro_analisado(tmp_path) -> None:
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    modo = _modo(tmp_path)
    c = TestClient(celular.criar_app(modo))
    with pytest.raises(WebSocketDisconnect) as fechou:
        with c.websocket_connect("/c/errado/ws") as ws:
            ws.receive_json()
    assert fechou.value.code == 4404

    with c.websocket_connect("/c/codigo-certo/ws") as ws:
        ws.send_bytes(b"curto")  # menor que o cabeçalho: ignorado
        ws.send_bytes(celular.cabecalho(1, {"x": 0.0, "y": 0.0, "trecho": 1}) + _jpeg())
        r1 = ws.receive_json()
        ws.send_bytes(celular.cabecalho(2, {"x": 0.02, "y": -0.01, "trecho": 1}) + _jpeg())
        r2 = ws.receive_json()
        ws.send_bytes(celular.cabecalho(3, None) + b"isto nao e imagem")
        r3 = ws.receive_json()
        ws.send_text('{"tipo": "medidas", "camera_por_s": 29.5, "enviados_por_s": 7, "rastro_ms": 3.2, "jpeg_ms": 24, "invasor": "x"}')
        ws.send_text("lixo que não é JSON")
        ws.send_bytes(celular.cabecalho(4, None) + b"isto nao e imagem")  # garante que as mensagens anteriores chegaram
        ws.receive_json()
    assert r1["tipo"] == "resultado" and r1["quadro"] == 1 and r1["deteccoes"] == []  # um quadro só não confirma
    assert r2["quadro"] == 2 and r2["posicao"] == {"x": 0.02, "y": -0.01, "trecho": 1}
    assert r2["deteccoes"][0]["caixa"] == [0.0, 0.0, 0.25, 0.5]
    assert r3["tipo"] == "erro" and r3["quadro"] == 3
    assert modo.vivo.quadro == 4 and modo.estado()["ultimo"]["quadros_por_s"] is not None
    medidas = modo.medidas
    assert medidas["camera_por_s"] == 29.5 and medidas["jpeg_ms"] == 24 and "invasor" not in medidas


def test_transmissao_pula_os_quadros_que_chegam_durante_a_analise(tmp_path) -> None:
    from fastapi.testclient import TestClient

    modo = _modo(tmp_path, espera_s=0.4)
    c = TestClient(celular.criar_app(modo))
    with c.websocket_connect("/c/codigo-certo/ws") as ws:
        for n in (1, 2, 3):  # 2 e 3 chegam enquanto o 1 é analisado: só o mais novo (3) é analisado depois
            ws.send_bytes(celular.cabecalho(n, {"x": 0.0, "y": 0.0, "trecho": 1}) + _jpeg())
        analisados = [ws.receive_json()["quadro"]]
        while analisados[-1] != 3:
            analisados.append(ws.receive_json()["quadro"])
    assert analisados == [1, 3]
    assert modo.vivo.quadro == 3  # o vídeo do computador recebeu todos


def test_computador_recebe_o_video_e_os_resultados_pelo_websocket(cliente, tmp_path, monkeypatch) -> None:
    from app import servidor

    modo = _modo(tmp_path)
    monkeypatch.setattr(servidor, "celular_modo", modo)
    posicao = {"x": 0.1, "y": 0.2, "trecho": 2}
    with cliente.websocket_connect("/api/celular/ws") as ws:
        modo.receber_quadro(b"jpeg-do-celular", 5, posicao)
        quadro = ws.receive_bytes()
        assert celular.ler_cabecalho(quadro) == (5, posicao)
        assert quadro[celular.CABECALHO.size:] == b"jpeg-do-celular"
        modo.processar(_jpeg(), 5, posicao)
        r = ws.receive_json()
    assert r["quadro"] == 5 and r["posicao"] == posicao and r["seq"] == 1 and "deteccoes" in r


def test_peca_so_aparece_confirmada_e_some_sem_termograma(tmp_path) -> None:
    modo = celular.ModoCelular(tmp_path, detectar=None, capturar=None, modelo=None)
    para_raio = {"classe": "para_raio", "caixa": [0.1, 0.1, 0.3, 0.6]}
    assert modo._confirmar([para_raio], True) == []
    mexeu = {"classe": "para_raio", "caixa": [0.12, 0.11, 0.31, 0.62]}  # a mão mexeu um pouco
    assert modo._confirmar([mexeu], True) == [mexeu]
    assert modo._confirmar([{"classe": "terminal_superior", "caixa": [0.5, 0.5, 0.6, 0.6]}], True) == []
    assert modo._confirmar([mexeu], False) == []  # sem termograma: esquece o histórico
    assert modo._confirmar([mexeu], True) == []


def test_maxima_mostrada_e_a_mediana_dos_ultimos_quadros(tmp_path) -> None:
    modo = celular.ModoCelular(tmp_path, detectar=None, capturar=None, modelo=None)
    escala = {"estado": "lida", "min": 19.8, "max": 30.0}
    mostradas = []
    for i, t in enumerate([26.0, 26.4, 29.9, 26.2, 26.1]):  # um pico isolado (a mira da câmera em cima)
        peca = {"classe": "para_raio", "caixa": [0.1 + 0.01 * i, 0.1, 0.3 + 0.01 * i, 0.6], "tmax": t, "tmax_acima": t > 29.5}
        posicao = {"x": 0.01 * i, "y": 0.0, "trecho": 1}  # a câmera andando: a peça anda junto
        mostradas.append(modo._suavizar([peca], [peca], posicao, escala)[0])
    assert [m["tmax"] for m in mostradas] == [26.0, 26.2, 26.4, 26.3, 26.2]
    assert not any(m["tmax_acima"] for m in mostradas)
    outra = modo._suavizar([{"classe": "para_raio", "caixa": [0.14, 0.1, 0.34, 0.6], "tmax": 40.0}], [],
                           {"x": 0.05, "y": 0.0, "trecho": 1}, {"estado": "lida", "min": 20.0, "max": 45.0})
    assert outra[0]["tmax"] == 40.0  # outra escala na tela: não mistura


def test_confirmacao_desconta_o_quanto_a_camera_andou(tmp_path) -> None:
    modo = celular.ModoCelular(tmp_path, detectar=None, capturar=None, modelo=None)
    antes = {"classe": "para_raio", "caixa": [0.10, 0.10, 0.20, 0.40]}
    depois = {"classe": "para_raio", "caixa": [0.25, 0.15, 0.35, 0.45]}  # a câmera andou: sem sobreposição
    assert modo._confirmar([antes], True, {"x": 0.0, "y": 0.0, "trecho": 1}) == []
    assert modo._confirmar([depois], True, {"x": 0.15, "y": 0.05, "trecho": 1}) == [depois]
    modo._anteriores.clear()
    modo._confirmar([antes], True, {"x": 0.0, "y": 0.0, "trecho": 1})
    assert modo._confirmar([depois], True, {"x": 0.15, "y": 0.05, "trecho": 2}) == []  # rastro perdido: não compara


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
    # Sem termograma no quadro (só uma parede laranja), nada é procurado e nada é salvo.
    assert servidor._celular_detectar(celular.ler_imagem(_jpeg())) == ([], {"area": None})
    with pytest.raises(ValueError, match="Nenhuma imagem térmica"):
        servidor._celular_capturar(_jpeg(), "celular_teste.jpg")

    caixas, info = servidor._celular_detectar(celular.ler_imagem(_termograma_na_sala()))
    x0, y0, x1, y1 = info["area"]
    assert x0 <= 40 and y0 <= 400 and x1 >= 680 and y1 >= 880 and y1 - y0 < 1280  # a área é o termograma, não a sala
    assert caixas[0]["nome"] == "Para-raio" and caixas[0]["caixa"][0] == x0 and caixas[0]["caixa"][1] == y0

    resumo = servidor._celular_capturar(_termograma_na_sala(), "celular_teste.jpg")
    assert resumo["regioes"] == 1
    a = cliente.get(f"/api/analises/{resumo['id']}").json()
    assert a["fonte"] == "celular"
    assert a["sem_temperatura"] is True and a["resumo"]["severidade"] == "sem_medida"
    assert "celular" in a["metadados"]["aviso"]
    assert a["regioes"][0]["nome"] == "Para-raio 1"


def test_celular_estima_a_temperatura_de_cada_peca_pela_barra_do_quadro(cliente, monkeypatch) -> None:
    from app import servidor
    from nucleo import barra
    from testes.test_barra import _OCRFalso, _caixa

    det = _DetectorImagem()
    monkeypatch.setattr(servidor, "_detector_imagem", lambda: det)
    ocr = _OCRFalso([(_caixa(0, 0, 30, 15), "50.0", 0.9)], [(_caixa(0, 0, 30, 15), "10.0", 0.9)])
    monkeypatch.setattr(servidor, "leitor_escala_celular", barra.LeitorAoVivo(lambda: ocr))
    quadro = celular.ler_imagem(_termograma_na_sala())
    caixas, info = servidor._celular_detectar(quadro)
    assert info["escala"]["estado"] == "lendo" and "tmax" not in caixas[0]  # uma leitura dos números ainda não vale
    caixas, info = servidor._celular_detectar(quadro)
    assert info["escala"]["estado"] == "lida" and (info["escala"]["min"], info["escala"]["max"]) == (10.0, 50.0)
    assert 10.0 <= caixas[0]["tmax"] <= 50.0
    bx0, by0, bx1, by1 = info["escala"]["barra"]
    # a barra em pixels do quadro: o termograma foi posto em (40, 400) e a barra fica em x 20..27, y 122..415 dele
    assert abs(bx0 - 60) < 6 and abs(by0 - 522) < 6 and abs(by1 - 815) < 6


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
