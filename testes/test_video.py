"""Vídeo como câmera ao vivo: temperatura rápida por tabela, escala lida só quando muda, leitor de
quadros e o fluxo completo pela API (enviar, acompanhar, salvar quadro como inspeção, apagar)."""

from __future__ import annotations

import json
import time

import numpy as np
import pytest

from app import videos as videos_mod
from nucleo import paleta, video
from testes.test_paleta import _cena, _imagem_sintetica


def _cena_quente() -> np.ndarray:
    t = _cena()
    t[250:274, 400:424] = 45.0  # ponto quente de 24×24 pixels exibidos (12×12 na matriz), ~10 °C acima do entorno
    return t


def _escrever_video(caminho, quadros: list[np.ndarray], fps: int = 10) -> None:
    import cv2

    h, w = quadros[0].shape[:2]
    escritor = cv2.VideoWriter(str(caminho), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
    for q in quadros:
        escritor.write(cv2.cvtColor(q, cv2.COLOR_RGB2BGR))
    escritor.release()


def test_termometro_por_tabela_bate_com_a_inversao_completa() -> None:
    img = _imagem_sintetica(50.0, 10.0, _cena())
    m = video.Termometro(limites=(10.0, 50.0)).medir(img)
    assert m.fonte == "informada" and m.escala == (10.0, 50.0)
    assert m.temperatura_c.shape == (240, 320)  # mesma resolução da foto não radiométrica
    from nucleo.entrada import _reduzir

    esc = paleta.escala(img, None, t_max=50.0, t_min=10.0)
    ref = _reduzir(paleta.inverter(img, esc).temperatura_c, 2)
    dif = np.abs(ref - m.temperatura_c)
    assert np.nanmedian(dif) < 0.2 and np.nanpercentile(dif, 99) < 0.5


def _com_rotulo(img: np.ndarray, digitos: list[int]) -> np.ndarray:
    """Pinta a caixa escura do rótulo do máximo com "dígitos" cinza em posições diferentes."""
    img = img.copy()
    barra = paleta.localizar_barra(img)
    x0, y0, x1, y1 = paleta.regioes_rotulo(barra, img.shape[:2])["max"]
    img[y0 + 8 : y1 - 8, x0 + 5 : x1 - 10] = (20, 20, 24)
    for k in digitos:
        img[y0 + 14 : y1 - 14, x0 + 12 + 18 * k : x0 + 22 + 18 * k] = (175, 175, 175)
    return img


def test_escala_so_vai_para_o_ocr_quando_o_numero_muda(monkeypatch) -> None:
    chamadas = []

    def ler(rgb, barra, ocr, rapido=False):
        chamadas.append(rapido)
        return 50.0, 10.0, {}

    monkeypatch.setattr(paleta, "ler_limites", ler)
    base = _imagem_sintetica(50.0, 10.0, _cena())
    a, b = _com_rotulo(base, [0, 1, 2]), _com_rotulo(base, [0, 3, 4])
    t = video.Termometro(ocr=object())
    assert t.medir(a, 0.0).fonte == "lida"
    assert t.medir(a, 1.0).fonte == "repetida"  # mesmo número: sem OCR
    assert t.medir(b, 2.0).fonte == "lida"  # número novo
    assert t.medir(a, 3.0).fonte == "repetida"  # voltou a um número já lido
    assert t.leituras_ocr == 2 and chamadas == [True, True]  # o reconhecimento rápido bastou
    assert t.medir(a, 3.0 + video.REVALIDAR_S + 1).fonte == "lida"  # relê de tempos em tempos


def test_ocr_rapido_duvidoso_cai_no_completo(monkeypatch) -> None:
    chamadas = []

    def ler(rgb, barra, ocr, rapido=False):
        chamadas.append(rapido)
        return (None, 10.0, {}) if rapido else (50.0, 10.0, {})

    monkeypatch.setattr(paleta, "ler_limites", ler)
    m = video.Termometro(ocr=object()).medir(_imagem_sintetica(50.0, 10.0, _cena()))
    assert m.escala == (10.0, 50.0) and chamadas == [True, False]


def test_sem_barra_nao_inventa_temperatura() -> None:
    m = video.Termometro(limites=(10.0, 50.0)).medir(np.zeros((480, 640, 3), np.uint8))
    assert m.temperatura_c is None and m.fonte == "sem_escala"


def test_leitor_pula_quadros_sem_voltar(tmp_path) -> None:
    quadros = [np.full((48, 64, 3), 8 * i, np.uint8) for i in range(30)]
    arq = tmp_path / "v.avi"
    _escrever_video(arq, quadros)
    leitor = video.Leitor(arq)
    assert leitor.info.fps == pytest.approx(10) and leitor.info.quadros == 30
    i, t, rgb = leitor.em(1.0)
    assert i == 10 and t == pytest.approx(1.0) and rgb.shape == (480, 640, 3)  # ampliado para o leiaute da câmera
    assert leitor.em(0.2)[0] == 11  # o vídeo não volta: vem o próximo
    assert leitor.em(99) is None
    leitor.fechar()


def test_opcoes_do_formulario() -> None:
    o = videos_mod.opcoes_validas("intervalo", "0.5", "1", "", "10", "50")
    assert o == {"modo": "intervalo", "intervalo_s": 0.5, "velocidade": 1.0, "modelo": None, "limites": [10.0, 50.0]}
    for errado in (("x", 1, 1, None, "", ""), ("ao_vivo", 1, 9, None, "", ""), ("ao_vivo", 1, 1, None, "10", ""), ("ao_vivo", 1, 1, None, "10", "10.2")):
        with pytest.raises(ValueError):
            videos_mod.opcoes_validas(*errado)


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    monkeypatch.setattr(servidor, "PASTA_MODELOS", tmp_path / "modelos")
    return TestClient(servidor.app)


def _esperar(cliente, id_: str, limite_s: float = 60) -> dict:
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        d = cliente.get(f"/api/videos/{id_}").json()
        if d["status"] not in videos_mod.ATIVOS:
            return d
        time.sleep(0.1)
    raise AssertionError("o vídeo não terminou a tempo")


def test_video_de_ponta_a_ponta(cliente, tmp_path) -> None:
    quadro = _imagem_sintetica(50.0, 10.0, _cena_quente())
    arq = tmp_path / "ronda.avi"
    _escrever_video(arq, [quadro] * 20)  # 2 s a 10 quadros/s

    r = cliente.post("/api/videos", files={"arquivo": ("ronda.avi", arq.read_bytes(), "video/x-msvideo")},
                     data={"modo": "intervalo", "intervalo_s": "0.5", "t_min": "10", "t_max": "50"})
    assert r.status_code == 200, r.text
    d = _esperar(cliente, r.json()["id"])
    assert d["status"] == "concluido", d.get("erro")
    assert [q["tempo_s"] for q in d["quadros"]] == [0.0, 0.5, 1.0, 1.5]
    q = d["quadros"][0]
    assert q["escala"] == [10.0, 50.0] and q["fonte_escala"] == "informada" and q["matriz"] == [320, 240]
    quente = [x for x in q["regioes"] if x["classe"] == "ponto_quente"]
    assert quente and quente[0]["t_max"] == pytest.approx(45.0, abs=1.0)
    assert d["resumo"]["analisados"] == 4 and d["resumo"]["t_max"] == max(x["t_max"] for x in d["quadros"])  # máxima da cena

    # só o que chegou depois
    assert cliente.get(f"/api/videos/{d['id']}", params={"desde": 3}).json()["quadros"][0]["n"] == 3
    img = cliente.get(f"/api/videos/{d['id']}/quadros/2.jpg")
    assert img.status_code == 200 and img.content[:2] == b"\xff\xd8"

    a = cliente.post(f"/api/videos/{d['id']}/quadros/2/inspecao").json()
    assert a["fonte"] == "video" and a["arquivo"].startswith("ronda 00m01")
    assert a["metadados"]["escala_lida_c"] == [10.0, 50.0]
    assert any(x["classe"] == "ponto_quente" for x in a["regioes"])

    assert [v["id"] for v in cliente.get("/api/videos").json()] == [d["id"]]
    assert cliente.delete(f"/api/videos/{d['id']}").status_code == 200
    assert cliente.get(f"/api/videos/{d['id']}").status_code == 404
    assert cliente.get(f"/api/analises/{a['id']}").status_code == 200  # a inspeção salva continua


def test_formato_errado_e_arquivo_que_nao_e_video(cliente) -> None:
    r = cliente.post("/api/videos", files={"arquivo": ("foto.jpg", b"x", "image/jpeg")})
    assert r.status_code == 422 and "Formato" in r.json()["erro"]
    r = cliente.post("/api/videos", files={"arquivo": ("falso.mp4", b"isto nao e video", "video/mp4")})
    assert r.status_code == 422
    assert cliente.get("/api/videos").json() == []  # nada fica para trás


def test_video_interrompido_mantem_o_que_foi_analisado(tmp_path) -> None:
    pasta = tmp_path / "videos" / "abcdef012345"
    pasta.mkdir(parents=True)
    estado = {"id": "abcdef012345", "arquivo": "x.mp4", "criado_em": "2026-09-30T10:00:00", "info": {"fps": 10, "quadros": 50, "duracao_s": 5},
              "opcoes": {}, "status": "processando", "resumo": {"analisados": 0}}
    (pasta / "estado.json").write_text(json.dumps(estado), encoding="utf-8")
    linhas = [{"n": i, "tempo_s": i * 0.5, "ms": 100, "pulados": 4, "t_max": 30.0 + i, "severidade": "normal", "regioes": [], "escala": [10, 50]} for i in range(3)]
    (pasta / "quadros.jsonl").write_text("\n".join(json.dumps(l) for l in linhas) + "\n{\"n\": 3, \"cortad", encoding="utf-8")
    v = videos_mod.Videos(lambda: tmp_path, lambda _: None)
    [e] = v.listar()
    assert e["status"] == "interrompido" and e["resumo"]["analisados"] == 3 and e["resumo"]["t_max"] == 32.0
