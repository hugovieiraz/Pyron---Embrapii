"""ml/avaliar_medicao.py: leitura da pasta de fotos (uma subpasta por objeto e medidas.csv) e os grupos."""

import json

from ml.avaliar_medicao import grupo_da_foto, ler_pasta, resumir


def test_grupo_pelo_nome_do_arquivo():
    assert grupo_da_foto("ideal.heic") == "ideal"
    assert grupo_da_foto("dificil (2).heic") == "difícil"
    assert grupo_da_foto("Difícil.jpg") == "difícil"
    assert grupo_da_foto("20261026_114024.heic") == "normal"


def test_ler_pasta(tmp_path):
    (tmp_path / "medidas.csv").write_text(
        "objeto,medida,valor_cm,so_em\npostit,lado,8.0,\nFOX,diametro,7.7,\nfox,altura,3.5,dificil\nA4,comprimento,\"29,7\",\n",
        encoding="utf-8")
    for pasta, fotos in {"FOX": ["ideal.heic", "dificil.heic", "1.jpg"], "A4": ["a.jpg"], "postit": ["p.jpg"], "sem_medida": ["x.jpg"]}.items():
        (tmp_path / pasta).mkdir()
        for f in fotos:
            (tmp_path / pasta / f).write_bytes(b"")
    (tmp_path / "pistas.json").write_text(json.dumps({"FOX/ideal.heic": {"caixa": [1, 2, 3, 4], "usar": "caixa"}}), encoding="utf-8")
    linhas, pistas, ref = ler_pasta(tmp_path)
    assert ref == {"auto": "postit_rosa", "tamanho_cm": 8.0}
    assert set(pistas) == {"A4/a.jpg", "FOX/1.jpg", "FOX/dificil.heic", "FOX/ideal.heic"}  # postit e sem medida fora
    assert pistas["FOX/ideal.heic"]["usar"] == "caixa" and pistas["A4/a.jpg"] == {"centro": True}
    alturas = [l["arquivo"] for l in linhas if l["medida"] == "altura"]
    assert alturas == ["FOX/dificil.heic"]  # so_em: altura do pote só nas fotos de lado
    diam = [l for l in linhas if l["objeto"] == "fox" and l["medida"] == "comprimento"]
    assert len(diam) == 3 and {l["grupo"] for l in diam} == {"ideal", "difícil", "normal"}
    assert [l["valor_cm"] for l in linhas if l["objeto"] == "a4"] == [29.7]


def test_resumo_por_grupo():
    linhas = [{"modelo": "vitl", "pista": "marcada", "grupo": g, "tempos_ms": {"total": 1.0},
               "erro_sem_ref_rel": e, "erro_com_ref_rel": e / 10, "erro_calibrado_rel": None, "erro_plano_rel": None}
              for g, e in (("ideal", 0.1), ("ideal", 0.3), ("difícil", -0.5))]
    r = resumir({"linhas": linhas})
    assert set(r) == {"vitl · marcada · todas", "vitl · marcada · ideal", "vitl · marcada · difícil"}
    assert r["vitl · marcada · ideal"]["sem referência"]["erro_mediano_pct"] == 20.0
    assert r["vitl · marcada · todas"]["sem referência"]["n"] == 3
