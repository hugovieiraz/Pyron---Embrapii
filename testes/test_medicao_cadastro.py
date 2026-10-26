"""Perfil de câmera, cadastro de medidas com validação por engenheiro e a API, com fotos sintéticas."""

import io
import math

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
if not hasattr(cv2, "aruco"):
    pytest.skip("OpenCV sem o módulo aruco", allow_module_level=True)

from PIL import Image  # noqa: E402

from app.cadastro_medidas import Cadastro, ErroCadastro  # noqa: E402
from nucleo.medicao import camera as C  # noqa: E402
from nucleo.medicao import mapa_escala as M  # noqa: E402

NX, NY, Q = M.PADRAO["nx"], M.PADRAO["ny"], M.PADRAO["quadrado_mm"]
W, H, F = 1200, 1600, 1250.0
CX, CY = 610.0, 790.0
K1 = -0.08  # distorção radial da lente simulada


def _cena_fundo(semente=5):
    rng = np.random.default_rng(semente)
    f = (rng.random((H // 16, W // 16)) * 200 + 30).astype(np.uint8)
    return cv2.resize(f, (W, H), interpolation=cv2.INTER_CUBIC)


def _foto(rx, ry, rz, dist_m, tx=0.0, ty=0.0, fundo=None, deslocar=(0, 0), k1=K1):
    """Folha vista por uma câmera com focal F, centro (CX, CY) e distorção radial k1."""
    mestre = M.tabuleiro().generateImage((NX * 200, NY * 200), marginSize=0)
    R = (cv2.Rodrigues(np.array([math.radians(rx), 0, 0]))[0] @ cv2.Rodrigues(np.array([0, math.radians(ry), 0]))[0]
         @ cv2.Rodrigues(np.array([0, 0, math.radians(rz)]))[0])
    t = np.array([tx, ty, dist_m * 1000.0])
    K = np.array([[F, 0, CX], [0, F, CY], [0, 0, 1]])
    Cc = np.array([[1, 0, -NX * Q / 2], [0, 1, -NY * Q / 2], [0, 0, 1]])
    Hm = K @ np.c_[R[:, 0], R[:, 1], t] @ Cc @ np.diag([1 / 8, 1 / 8, 1])
    base = fundo if fundo is not None else _cena_fundo()
    folha = cv2.warpPerspective(mestre, Hm, (W, H), flags=cv2.INTER_AREA, borderValue=0)
    masc = cv2.warpPerspective(np.full_like(mestre, 255), Hm, (W, H), borderValue=0)
    im = np.where(masc > 127, folha, base)
    if k1:
        # aplica a distorção: para cada pixel distorcido, busca o ponto ideal (aprox. de 1ª ordem, invertendo)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        x, y = (xx - CX) / F, (yy - CY) / F
        r2 = x * x + y * y
        mx = (x * (1 + k1 * r2)) * F + CX
        my = (y * (1 + k1 * r2)) * F + CY
        im = cv2.remap(im, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LINEAR)
    if deslocar != (0, 0):  # a câmera mexeu: a imagem inteira anda (cena e folha)
        im = cv2.warpAffine(im, np.float32([[1, 0, deslocar[1]], [0, 1, deslocar[0]]]), (W, H), borderMode=cv2.BORDER_REFLECT)
    im = cv2.GaussianBlur(im, (0, 0), 0.7)
    _, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return buf.tobytes()


POSES = [(25, 0, 0, 0.55, -40, 0), (0, 30, 10, 0.6, 60, -80), (-30, 10, -15, 0.55, 0, 90), (35, -25, 5, 0.65, -80, 60),
         (10, 40, 20, 0.6, 50, 40), (-20, -30, 0, 0.5, 30, -60), (40, 20, -10, 0.7, -50, -40)]


@pytest.fixture(scope="module")
def perfil():
    return C.calibrar("celular-teste", [_foto(*p) for p in POSES], modelo="sintética")


def test_calibrar_acha_focal_centro_e_distorcao(perfil):
    assert perfil.n_fotos == len(POSES)
    assert perfil.focal_px == pytest.approx(F, rel=0.01)
    assert perfil.cx == pytest.approx(CX, abs=10) and perfil.cy == pytest.approx(CY, abs=10)
    assert perfil.erro_reprojecao_px < 0.6
    # a lente simulada leva o ponto ideal u ao distorcido d com u = d·(1 + K1·r²); o modelo do OpenCV vai no sentido
    # contrário (d = u·(1 + k1·r²)), então k1 sai com o sinal trocado e quase o mesmo valor
    assert perfil.distorcao[0] == pytest.approx(-K1, rel=0.3)


def test_poucas_fotos_recusa():
    with pytest.raises(ValueError, match="pelo menos"):
        C.calibrar("x", [_foto(*p) for p in POSES[:3]])


def test_perfil_em_outra_resolucao(perfil):
    p = perfil.para_resolucao(600, 800)
    assert p.focal_px == pytest.approx(perfil.focal_px / 2)
    deitada = perfil.para_resolucao(800, 600)
    assert deitada.cx == pytest.approx(perfil.cy / 2)
    with pytest.raises(ValueError, match="cortada"):
        perfil.para_resolucao(1000, 1000)


def test_ficha_termica():
    p = C.perfil_da_ficha("flir-c5", 160, 120, 54.0, modelo="FLIR C5")
    # 54° em 160 px: f = 80 / tan(27°) = 157 px; 1 px a 5 m = 3,18 cm
    assert p.focal_px == pytest.approx(157.0, abs=0.5)
    assert p.tamanho_pixel_cm(5.0) == pytest.approx(3.18, abs=0.02)


def test_camera_fixa_confere_se_mexeu(perfil):
    fundo = _cena_fundo(9)
    pos = C.registrar_posicao(perfil, _foto(20, 10, 0, 0.6, fundo=fundo))
    assert pos.distancia_cm["mediana"] == pytest.approx(60, rel=0.05)
    parada = C.conferir_posicao(pos, _foto(20, 10, 0, 0.6, fundo=fundo))
    assert parada["vale"] and parada["deslocamento_px"] < 1.0
    mexeu = C.conferir_posicao(pos, _foto(20, 10, 0, 0.6, fundo=fundo, deslocar=(0, 12)))
    assert not mexeu["vale"] and mexeu["deslocamento_px"] > 5


def test_escala_por_componente_cadastrado():
    p = C.perfil_da_ficha("flir-c5", 160, 120, 54.0)
    # para-raio de 120 cm a 5 m: 120 / 3,18 = 37,7 px
    r = C.escala_por_referencia(p, 37.7, 120.0, incerteza_cm=1.0)
    assert r["distancia_m"] == pytest.approx(5.0, rel=0.01)
    assert r["incerteza_rel"] == pytest.approx(math.hypot(1 / 120, 2 / 37.7), rel=1e-3)


# ---------------------------------------------------------------- cadastro


def test_fluxo_de_validacao(tmp_path):
    cad = Cadastro(tmp_path)
    m = cad.propor("se-campina--tr-01", "para-raio fase A", "comprimento", 121.5, "folha", "Técnico Silva",
                   incerteza_cm=0.6, classe="para_raio", fase="A", origem={"camera": "celular-teste"})
    assert m["status"] == "proposta"
    assert cad.referencias("se-campina--tr-01") == []  # proposta não dá escala
    with pytest.raises(ErroCadastro, match="CREA"):
        cad.validar(m["id"], "Eng. Souza", "")
    with pytest.raises(ErroCadastro, match="não pode validá-la"):
        cad.validar(m["id"], "técnico silva", "CREA-PB 123")
    v = cad.validar(m["id"], "Eng. Souza", "CREA-PB 123456")
    assert v["status"] == "validada" and v["validado_por"] == "Eng. Souza"
    assert [h["acao"] for h in v["historico"]] == ["proposta", "validada"]
    assert len(cad.referencias("se-campina--tr-01")) == 1
    with pytest.raises(ErroCadastro, match="só proposta"):
        cad.validar(m["id"], "Eng. Souza", "CREA-PB 123456")

    # correção: nova proposta; ao validar, a antiga vira substituída e continua no histórico
    n = cad.propor("se-campina--tr-01", "para-raio fase A", "comprimento", 120.8, "laser", "Técnico Lima",
                   substitui_id=m["id"])
    cad.validar(n["id"], "Eng. Souza", "CREA-PB 123456")
    assert cad.medida(m["id"])["status"] == "substituida"
    refs = cad.referencias("se-campina--tr-01")
    assert len(refs) == 1 and refs[0]["valor_cm"] == 120.8

    r = cad.propor("se-campina--tr-01", "isolador", "altura", 80, "manual", "Técnico Lima")
    with pytest.raises(ErroCadastro, match="motivo"):
        cad.rejeitar(r["id"], "Eng. Souza", "CREA-PB 123456", "")
    assert cad.rejeitar(r["id"], "Eng. Souza", "CREA-PB 123456", "foto de baixo, inclinada")["status"] == "rejeitada"


def test_fases_iguais_e_diferentes(tmp_path):
    cad = Cadastro(tmp_path)
    for fase, v in (("A", 120.0), ("B", 121.0), ("C", 120.4)):
        cad.propor("se--tr", f"para-raio {fase}", "comprimento", v, "folha", "Téc", classe="para_raio", fase=fase)
    for fase, v in (("A", 80.0), ("B", 88.0)):
        cad.propor("se--tr", f"isolador {fase}", "altura", v, "folha", "Téc", classe="isolador", fase=fase)
    g = {x["classe"]: x for x in cad.conferir_fases("se--tr")}
    assert g["para_raio"]["passa"] and g["para_raio"]["diferenca_rel"] < 0.01
    assert not g["isolador"]["passa"] and g["isolador"]["diferenca_rel"] == pytest.approx(8 / 84, abs=1e-3)  # relativo à mediana


def test_camera_guardada_e_lida(tmp_path, perfil):
    cad = Cadastro(tmp_path)
    cad.salvar_camera(perfil)
    lido = cad.camera("celular-teste")
    assert lido.focal_px == perfil.focal_px and lido.distorcao == perfil.distorcao
    with pytest.raises(ErroCadastro):
        cad.camera("nao-existe")


# ---------------------------------------------------------------- API


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import servidor
    from app.armazenamento import Armazenamento

    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(tmp_path / "dados_app"))
    monkeypatch.setattr(servidor, "PASTA_DADOS", tmp_path / "dados_app")
    return TestClient(servidor.app)


def test_api_cadastro_ponta_a_ponta(cliente):
    r = cliente.post("/api/cadastro/cameras/ficha", json={"nome": "flir-c5", "largura": 160, "altura": 120,
                                                          "fov_horizontal_graus": 54, "modelo": "FLIR C5"})
    assert r.status_code == 200, r.text
    m = cliente.post("/api/cadastro/medidas", json={
        "equipamento_chave": "se--tr-01", "componente": "para-raio A", "medida": "comprimento", "valor_cm": 120,
        "metodo": "projeto", "criado_por": "Téc. Lima", "incerteza_cm": 0.5, "classe": "para_raio", "fase": "A"}).json()
    corpo = {"medida_id": m["id"], "camera": "flir-c5", "largura": 160, "altura": 120, "comprimento_px": 37.7}
    r = cliente.post("/api/cadastro/escala", json=corpo)
    assert r.status_code == 422 and "validada" in r.json()["erro"]
    r = cliente.post(f"/api/cadastro/medidas/{m['id']}/validar", json={"engenheiro": "Eng. Souza", "registro": "CREA 1"})
    assert r.status_code == 200 and r.json()["status"] == "validada"
    r = cliente.post("/api/cadastro/escala", json=corpo)
    assert r.status_code == 200, r.text
    assert r.json()["distancia_m"] == pytest.approx(5.0, rel=0.01)
    assert r.json()["referencia"]["validado_por"] == "Eng. Souza"
    assert len(cliente.get("/api/cadastro/medidas", params={"status": "validada"}).json()) == 1


def test_api_calibrar_e_camera_fixa(cliente):
    fotos = [("fotos", (f"f{i}.jpg", _foto(*p), "image/jpeg")) for i, p in enumerate(POSES)]
    r = cliente.post("/api/cadastro/cameras/calibrar", data={"nome": "cam-patio", "quadrado_mm": "25"}, files=fotos)
    assert r.status_code == 200, r.text
    assert r.json()["focal_px"] == pytest.approx(F, rel=0.01)
    fundo = _cena_fundo(11)
    r = cliente.post("/api/cadastro/cameras/cam-patio/posicao",
                     files={"arquivo": ("i.jpg", _foto(15, 5, 0, 0.6, fundo=fundo), "image/jpeg")})
    assert r.status_code == 200, r.text
    r = cliente.post("/api/cadastro/cameras/cam-patio/conferir",
                     files={"arquivo": ("n.jpg", _foto(15, 5, 0, 0.6, fundo=fundo), "image/jpeg")})
    assert r.json()["vale"]
