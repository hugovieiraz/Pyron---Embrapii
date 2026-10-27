"""Testes automatizados da Biblioteca de Pesos e Contexto de Vídeo + Medição 2D.

Cobre:
1. Extração determinística de pesos multi-ângulo (128 floats) e perfil de 20 fatias.
2. Gravação de pesos a partir de vídeo sintético multi-quadro e persistência (.npz, .jpg, .json).
3. Endpoints REST da biblioteca (/api/medicao/biblioteca, miniatura, remoção, estado).
4. Gravação e reconhecimento de ativos a partir de vídeos processados (/api/videos/{id_}/...).
5. Medição métrica 2D ancorada no contexto (/api/medicao/contexto-2d) com compensação de escorço e cotas.
"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import servidor
from app.armazenamento import Armazenamento
from app.videos import Videos
from nucleo.medicao.biblioteca_contexto import (
    DIM_VETOR_PESOS,
    NUM_FATIAS_PERFIL,
    BibliotecaContexto,
    extrair_pesos_regiao,
)


@pytest.fixture()
def cliente_app(tmp_path, monkeypatch):
    """Configura ambiente isolado em tmp_path para testes de integração de API."""
    pasta_dados = tmp_path / "dados_app"
    pasta_dados.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(servidor, "PASTA_DADOS", pasta_dados)
    monkeypatch.setattr(servidor, "armazenamento", Armazenamento(pasta_dados))

    # Instância do gerenciador de vídeos no diretório temporário isolado por monkeypatch
    mock_preparar = lambda opc: (lambda q, t: {"deteccoes": [], "matriz": None}, {"id": "mock", "nome": "Mock"})
    monkeypatch.setattr(servidor, "videos", Videos(lambda: pasta_dados, mock_preparar))


    return TestClient(servidor.app), pasta_dados


def _gerar_video_sintetico_mp4(
    caminho: Path,
    num_quadros: int = 6,
    largura: int = 320,
    altura: int = 240,
) -> Path:
    """Gera um arquivo MP4 sintético com um ativo elétrico (isolador/bucha) sob variação suave."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(caminho), fourcc, 10.0, (largura, altura))

    for i in range(num_quadros):
        # Fundo acinzentado de subestação
        frame = np.full((altura, largura, 3), 180, dtype=np.uint8)

        # Desenha coluna cilíndrica com aletas (isolador) no centro
        centro_x = largura // 2 + int(np.sin(i * 0.4) * 8)
        y_topo, y_base = 40, 200
        w_corpo = 30

        # Corpo
        cv2.rectangle(
            frame,
            (centro_x - w_corpo // 2, y_topo),
            (centro_x + w_corpo // 2, y_base),
            (70, 90, 160),
            thickness=-1,
        )

        # Aletas periódicas
        for y_aleta in range(y_topo + 15, y_base - 10, 20):
            cv2.ellipse(
                frame,
                (centro_x, y_aleta),
                (w_corpo + 12, 6),
                0,
                0,
                360,
                (50, 70, 130),
                thickness=-1,
            )

        out.write(frame)

    out.release()
    return caminho


# ==============================================================================
# 1. Testes de Extração de Pesos e Perfil
# ==============================================================================


def test_extracao_pesos_regiao_e_fatias():
    """Valida que o extrator de pesos produz tensores normalizados com dimensões exatas."""
    rgb = np.full((200, 200, 3), 120, dtype=np.uint8)
    # Ativo retangular vertical no centro
    cv2.rectangle(rgb, (80, 30), (120, 170), (40, 80, 200), thickness=-1)

    mascara = np.zeros((200, 200), dtype=np.uint8)
    mascara[30:171, 80:121] = 1

    vetor, perfil = extrair_pesos_regiao(rgb, mascara)

    assert isinstance(vetor, np.ndarray)
    assert vetor.shape == (DIM_VETOR_PESOS,)
    assert vetor.dtype == np.float32

    # Norma L2 unitária
    norma = float(np.linalg.norm(vetor))
    assert pytest.approx(norma, abs=1e-4) == 1.0

    # Perfil de 20 fatias
    assert isinstance(perfil, np.ndarray)
    assert perfil.shape == (NUM_FATIAS_PERFIL,)
    assert np.all(perfil >= 0.0)
    assert np.all(perfil <= 1.0)
    # Como o retângulo é uniforme verticalmente, a maioria das fatias deve ter valor positivo
    assert np.mean(perfil) > 0.5


# ==============================================================================
# 2. Testes de Gravação de Vídeo e Persistência Direta
# ==============================================================================


def test_biblioteca_contexto_gravar_video_e_persistencia(tmp_path):
    """Valida a criação e leitura de registros multi-ângulo com arquivos .npz e .jpg."""
    pasta_bib = tmp_path / "medicao"
    bib = BibliotecaContexto(pasta_bib)

    video_path = tmp_path / "video_teste.mp4"
    _gerar_video_sintetico_mp4(video_path, num_quadros=8)

    caixa_ini = [140.0, 35.0, 180.0, 205.0]
    registro = bib.gravar_de_video(
        caminho_video=video_path,
        nome="Isolador 138kV Linha 1",
        classe="isolador",
        caixa_inicial=caixa_ini,
        altura_cm=120.0,
    )

    assert registro["id"].startswith("ctx_")
    assert registro["nome"] == "Isolador 138kV Linha 1"
    assert registro["classe"] == "isolador"
    assert registro["dimensoes_cm"]["altura"] == 120.0
    assert registro["dimensoes_cm"]["largura"] > 0
    assert registro["total_angulos"] > 0
    assert registro["consistencia"] > 0.70

    # Confere persistência no disco
    id_ = registro["id"]
    npz_path = pasta_bib / "pesos_contexto" / f"{id_}.npz"
    jpg_path = pasta_bib / "pesos_contexto" / f"{id_}.jpg"
    json_path = pasta_bib / "biblioteca_contexto.json"

    assert npz_path.exists()
    assert jpg_path.exists()
    assert json_path.exists()

    # Confere conteúdo do .npz
    pesos = bib.obter_pesos(id_)
    assert pesos is not None
    assert "vetor_centroide" in pesos
    assert "pesos_angulos" in pesos
    assert "perfil_fatias" in pesos
    assert pesos["vetor_centroide"].shape == (DIM_VETOR_PESOS,)

    # Confere listagem
    itens = bib.listar()
    assert len(itens) == 1
    assert itens[0]["id"] == id_


# ==============================================================================
# 3. Testes de API REST da Biblioteca (/api/medicao/biblioteca)
# ==============================================================================


def test_api_biblioteca_endpoints(cliente_app):
    """Testa listagem, miniatura, remoção e estado via endpoints HTTP."""
    cli, pasta_dados = cliente_app

    # Inicialmente vazia
    r_estado = cli.get("/api/medicao/estado")
    assert r_estado.status_code == 200
    assert r_estado.json()["biblioteca_total"] == 0

    # Grava item diretamente na biblioteca
    bib = BibliotecaContexto(pasta_dados / "medicao")
    video_path = pasta_dados / "vid_demo.mp4"
    _gerar_video_sintetico_mp4(video_path, num_quadros=5)
    item = bib.gravar_de_video(
        caminho_video=video_path,
        nome="Bucha Transformador TR-02",
        classe="bucha",
        altura_cm=95.0,
    )
    id_ = item["id"]

    # 1. Estado atualizado
    r_estado2 = cli.get("/api/medicao/estado")
    assert r_estado2.status_code == 200
    assert r_estado2.json()["biblioteca_total"] == 1

    # 2. Listar
    r_list = cli.get("/api/medicao/biblioteca")
    assert r_list.status_code == 200
    itens = r_list.json()["itens"]
    assert len(itens) == 1
    assert itens[0]["id"] == id_
    assert itens[0]["nome"] == "Bucha Transformador TR-02"

    # 3. Miniatura JPEG
    r_mini = cli.get(f"/api/medicao/biblioteca/{id_}/miniatura.jpg")
    assert r_mini.status_code == 200
    assert "image/jpeg" in r_mini.headers["content-type"]
    assert len(r_mini.content) > 100

    # 4. Remover
    r_del = cli.delete(f"/api/medicao/biblioteca/{id_}")
    assert r_del.status_code == 200
    assert r_del.json()["ok"] is True

    # 5. Após remoção
    r_del_404 = cli.delete(f"/api/medicao/biblioteca/{id_}")
    assert r_del_404.status_code == 404

    r_mini_404 = cli.get(f"/api/medicao/biblioteca/{id_}/miniatura.jpg")
    assert r_mini_404.status_code == 404

    r_list2 = cli.get("/api/medicao/biblioteca")
    assert len(r_list2.json()["itens"]) == 0


# ==============================================================================
# 4. Testes de Gravação e Reconhecimento a partir de Vídeo Processado
# ==============================================================================


def test_api_videos_gravar_pesos_e_reconhecer(cliente_app):
    """Testa fluxo completo de memorização de vídeo (/api/videos/{id_}/gravar-pesos) e reconhecimento futuro."""
    cli, pasta_dados = cliente_app
    vid_id = "a1b2c3d4e5f6"
    pasta_video = pasta_dados / "videos" / vid_id
    pasta_video.mkdir(parents=True)
    pasta_quadros = pasta_video / "quadros"
    pasta_quadros.mkdir(parents=True)

    # Gera quadros e arquivos de simulação
    video_path = pasta_video / "original.mp4"
    _gerar_video_sintetico_mp4(video_path, num_quadros=4)

    # Cria quadros JPEG e quadros.jsonl
    quadros_info = []
    for n in range(4):
        img_arr = np.full((240, 320, 3), 190, dtype=np.uint8)
        # Objeto retangular representando transformador
        cv2.rectangle(img_arr, (100, 40), (220, 200), (60, 80, 150), thickness=-1)
        arq_jpg = pasta_quadros / f"{n:05d}.jpg"
        cv2.imwrite(str(arq_jpg), img_arr)

        quadros_info.append({
            "n": n,
            "tempo_s": n * 0.5,
            "deteccoes": [
                {
                    "classe": "transformador",
                    "caixa": [100.0, 40.0, 220.0, 200.0],
                    "delta_termico": 14.5,
                }
            ],
        })

    estado = {
        "id": vid_id,
        "arquivo": "subestacao.mp4",
        "status": "concluido",
        "opcoes": {"modo": "intervalo"},
        "info": {"duracao_s": 2.0, "fps": 10.0, "largura": 320, "altura": 240},
    }
    (pasta_video / "estado.json").write_text(json.dumps(estado), encoding="utf-8")
    (pasta_video / "quadros.jsonl").write_text(
        "\n".join(json.dumps(q) for q in quadros_info) + "\n",
        encoding="utf-8",
    )

    # 1. Executa POST /api/videos/{id_}/gravar-pesos
    payload_gravar = {
        "nome": "Transformador Principal TR-1",
        "classe": "transformador",
        "caixa": [100.0, 40.0, 220.0, 200.0],
        "altura_cm": 220.0,
    }
    r_gravar = cli.post(f"/api/videos/{vid_id}/gravar-pesos", json=payload_gravar)
    assert r_gravar.status_code == 200, r_gravar.text
    item_gravado = r_gravar.json()
    assert item_gravado["nome"] == "Transformador Principal TR-1"
    assert item_gravado["classe"] == "transformador"
    assert item_gravado["dimensoes_cm"]["altura"] == 220.0

    # 2. Executa POST /api/videos/{id_}/reconhecer-biblioteca
    r_rec = cli.post(f"/api/videos/{vid_id}/reconhecer-biblioteca", json={})
    assert r_rec.status_code == 200, r_rec.text
    dados_rec = r_rec.json()
    assert dados_rec["video_id"] == vid_id
    reconhecidos = dados_rec["reconhecidos"]
    assert len(reconhecidos) > 0
    primeiro = reconhecidos[0]
    assert primeiro["id_contexto"] == item_gravado["id"]
    assert primeiro["classe"] == "transformador"
    assert primeiro["confianca"] >= 0.70
    assert primeiro["dimensoes_cm"]["altura"] == 220.0


# ==============================================================================
# 5. Testes de Medição 2D Contextual (/api/medicao/contexto-2d)
# ==============================================================================


def test_api_medicao_contexto_2d_com_escorco_e_cotas(cliente_app):
    """Testa medição 2D com ancoragem na biblioteca, compensação de escorço e cotas/contorno."""
    cli, pasta_dados = cliente_app

    # Cadastra na biblioteca um isolador com dimensões conhecidas:
    # Altura = 120 cm, Largura = 40 cm (Proporção canônica = 3.0)
    bib = BibliotecaContexto(pasta_dados / "medicao")
    video_path = pasta_dados / "video_isolador.mp4"
    _gerar_video_sintetico_mp4(video_path, num_quadros=6)

    item = bib.gravar_de_video(
        caminho_video=video_path,
        nome="Isolador Padrão 69kV",
        classe="isolador",
        caixa_inicial=[140.0, 30.0, 180.0, 210.0],
        altura_cm=120.0,
        largura_cm=40.0,
    )
    id_ctx = item["id"]

    # Cria uma foto 2D onde o mesmo objeto aparece inclinado / fotografado sob ângulo (escorço)
    # Por exemplo: em vez de 180 px de altura, aparece com 144 px (fator ~0.80) e largura 48 px
    img_2d = np.full((300, 300, 3), 200, dtype=np.uint8)
    cv2.rectangle(img_2d, (126, 78), (174, 222), (50, 70, 130), thickness=-1)

    buf_foto = io.BytesIO()
    Image.fromarray(img_2d).save(buf_foto, format="JPEG")
    bytes_foto = buf_foto.getvalue()

    # 1. Medição especificando id_contexto
    pista_caixa = {"caixa": [126.0, 78.0, 174.0, 222.0]}
    r_med = cli.post(
        "/api/medicao/contexto-2d",
        files={"arquivo": ("foto_2d.jpg", bytes_foto, "image/jpeg")},
        data={"pista": json.dumps(pista_caixa), "id_contexto": id_ctx},
    )
    assert r_med.status_code == 200, r_med.text
    res = r_med.json()

    # Confere retorno estruturado
    assert res["id_contexto"] == id_ctx
    assert res["nome_contexto"] == "Isolador Padrão 69kV"
    assert res["classe_contexto"] == "isolador"
    assert res["metodo"] == "contexto_video_2d"

    # Confere compensação de escorço e recuperação de escala
    assert 0.50 <= res["fator_escorco"] <= 1.0
    assert res["angulo_inclinacao_deg"] >= 0.0
    assert res["altura_cm"] == pytest.approx(120.0, abs=5.0)
    assert res["largura_cm"] == pytest.approx(40.0, abs=5.0)
    assert res["area_cm2"] > 0.0

    # Confere cotas e contorno
    assert "cotas" in res
    assert "altura" in res["cotas"]
    assert "largura" in res["cotas"]
    assert len(res["cotas"]["altura"]) == 2
    assert len(res["cotas"]["largura"]) == 2

    assert "contorno" in res
    assert isinstance(res["contorno"], list)
    assert len(res["contorno"]) > 0

    # 2. Medição em modo automático (sem id_contexto ou id_contexto="auto")
    r_auto = cli.post(
        "/api/medicao/contexto-2d",
        files={"arquivo": ("foto_2d.jpg", bytes_foto, "image/jpeg")},
        data={"pista": json.dumps(pista_caixa), "id_contexto": "auto"},
    )
    assert r_auto.status_code == 200, r_auto.text
    res_auto = r_auto.json()
    assert res_auto["id_contexto"] == id_ctx
    assert res_auto["altura_cm"] == pytest.approx(120.0, abs=5.0)


def test_api_medicao_upload_video_gravar_pesos(cliente_app):
    """Testa upload direto de arquivo de vídeo para gravação na biblioteca (/api/medicao/video/gravar-pesos)."""
    cli, pasta_dados = cliente_app

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_vid:
        caminho_tmp = Path(tmp_vid.name)

    try:
        _gerar_video_sintetico_mp4(caminho_tmp, num_quadros=5)
        bytes_vid = caminho_tmp.read_bytes()

        r = cli.post(
            "/api/medicao/video/gravar-pesos",
            files={"arquivo": ("drone_scan.mp4", bytes_vid, "video/mp4")},
            data={
                "nome": "Chave Seccionadora CS-4",
                "classe": "chave_seccionadora",
                "altura_cm": "140.0",
            },
        )
        assert r.status_code == 200, r.text
        item = r.json()
        assert item["nome"] == "Chave Seccionadora CS-4"
        assert item["classe"] == "chave_seccionadora"
        assert item["dimensoes_cm"]["altura"] == 140.0
        assert item["total_angulos"] > 0
    finally:
        if caminho_tmp.exists():
            caminho_tmp.unlink()
