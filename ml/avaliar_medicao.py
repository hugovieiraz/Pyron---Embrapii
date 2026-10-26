"""Avaliação da medição em foto comum no gabarito (fase 3 de docs/07_roteiro_medicao_geral.md).

Uso:
    python -m ml.avaliar_medicao                          (fotos de testes/gabarito, MoGe-2 ViT-S, B e L)
    python -m ml.avaliar_medicao --pasta fotos_medicao --modelos vitl     (uma pasta por objeto + medidas.csv)
    python -m ml.avaliar_medicao --modelos vits --sam small
    python -m ml.avaliar_medicao --sintetico              (cenas sintéticas, sem modelo nenhum)

Lê ``testes/gabarito/gabarito.csv`` (uma linha por medida conhecida) e ``testes/gabarito/pistas.json``
(onde está cada objeto: ``ponto`` no centro e ``caixa`` em volta; opcional ``referencias`` com a pista e o
tamanho de cada referência que aparece na foto). Mede cada objeto pelo ponto e pela caixa e grava em
``saida/medicao/``: ``relatorio.json``, ``relatorio.md`` e ``contornos/`` (o contorno do SAM sobre a foto).

Pasta de fotos (``--pasta``): uma subpasta por objeto (o nome da subpasta é o objeto) e ``medidas.csv`` na raiz
com ``objeto,medida,valor_cm`` (medida: comprimento, largura, altura, espessura; ``lado`` e ``diametro`` valem como
comprimento). A linha ``postit,lado,7.6`` dá o tamanho do post-it. O objeto é o que está no centro da foto, a não
ser que ``pistas.json`` na raiz diga outro ponto ou caixa (chave: ``subpasta/arquivo``). O post-it rosa é achado
sozinho pela cor; foto sem post-it entra só no modo sem referência.

Modos de escala comparados:
- **sem referência**: a escala do MoGe-2;
- **com referência na foto**: quando o CSV aponta ``referencia_na_foto`` ou o post-it é achado; a referência
  corrige a escala da profundidade;
- **plano da referência**: só a homografia dos cantos da referência, sem profundidade (vale no plano dela);
- **calibrado pela câmera**: um fator único (mediana de real/estimado) ajustado nas *outras* fotos e
  aplicado nesta (deixa uma de fora), o passo 1 da parte E do roteiro.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.medicao import Medidor  # noqa: E402
from nucleo.medicao import modelos  # noqa: E402

PASTA_GABARITO = RAIZ / "testes" / "gabarito"
PASTA_SAIDA = RAIZ / "saida" / "medicao"


def ler_gabarito(pasta: Path) -> tuple[list[dict], dict]:
    with open(pasta / "gabarito.csv", encoding="utf-8") as f:
        linhas = [dict(l) for l in csv.DictReader(f)]
    for l in linhas:
        l["valor_cm"] = float(l["valor_cm"])
    pistas = json.loads((pasta / "pistas.json").read_text(encoding="utf-8"))
    return linhas, pistas


def resumo(erros_rel: list[float]) -> dict:
    """Erro relativo: mediana do valor absoluto e intervalo de 95 % (percentis 2,5 e 97,5 do erro com sinal)."""
    e = np.asarray([x for x in erros_rel if x is not None and math.isfinite(x)], dtype=float)
    if len(e) == 0:
        return {"n": 0}
    return {
        "n": int(len(e)),
        "erro_mediano_pct": round(float(np.median(np.abs(e))) * 100, 2),
        "vies_mediano_pct": round(float(np.median(e)) * 100, 2),
        "intervalo_95_pct": [round(float(np.percentile(e, 2.5)) * 100, 2), round(float(np.percentile(e, 97.5)) * 100, 2)],
        "erro_maximo_pct": round(float(np.max(np.abs(e))) * 100, 2),
    }


def _calibrar_deixando_uma_fora(linhas: list[dict], chave_est: str, chave_saida: str) -> None:
    """Fator da câmera = mediana de real/estimado nas outras fotos; aplica nesta."""
    for l in linhas:
        outras = [
            o["valor_cm"] / o[chave_est]
            for o in linhas
            if o["arquivo"] != l["arquivo"] and o.get(chave_est) and o["modelo"] == l["modelo"] and o["pista"] == l["pista"]
        ]
        if l.get(chave_est) and outras:
            fator = float(np.median(outras))
            l["fator_camera"] = round(fator, 4)
            l[chave_saida] = round(l[chave_est] * fator, 2)
        else:
            l[chave_saida] = None


def _erros(linhas: list[dict]) -> None:
    for l in linhas:
        for modo in ("sem_ref", "com_ref", "calibrado", "plano"):
            est = l.get(f"estimado_{modo}")
            if est is None:
                l[f"erro_{modo}_cm"] = l[f"erro_{modo}_rel"] = None
            else:
                l[f"erro_{modo}_cm"] = round(est - l["valor_cm"], 2)
                l[f"erro_{modo}_rel"] = round((est - l["valor_cm"]) / l["valor_cm"], 4)


def _desenhar(img, medida, caminho: Path, rotulo: str) -> None:
    from PIL import ImageDraw

    im = img.copy()
    d = ImageDraw.Draw(im)
    for poli in medida.contorno:
        if len(poli) >= 2:
            d.line([tuple(p) for p in poli] + [tuple(poli[0])], fill=(255, 64, 0), width=max(2, im.width // 300))
    d.text((10, 10), rotulo, fill=(255, 255, 0))
    caminho.parent.mkdir(parents=True, exist_ok=True)
    im.save(caminho, quality=85)


SINONIMOS = {"lado": "comprimento", "diametro": "comprimento", "diâmetro": "comprimento"}
EXTENSOES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def grupo_da_foto(nome: str) -> str:
    """Tipo da foto pelo nome do arquivo: "ideal", "difícil" ou "normal" (as numeradas)."""
    import unicodedata

    n = unicodedata.normalize("NFD", nome.lower()).encode("ascii", "ignore").decode()
    return "ideal" if "ideal" in n else "difícil" if "dificil" in n else "normal"


def ler_pasta(pasta: Path) -> tuple[list[dict], dict, dict | None]:
    """Pasta com uma subpasta por objeto e ``medidas.csv``: devolve (linhas do gabarito, pistas, referência auto)."""
    import unicodedata

    def chave(t: str) -> str:
        return unicodedata.normalize("NFD", t.strip().lower()).encode("ascii", "ignore").decode().replace(" ", "_")

    with open(pasta / "medidas.csv", encoding="utf-8-sig") as f:
        medidas = [{k.strip().lower(): (v or "").strip() for k, v in l.items()} for l in csv.DictReader(f)]
    ref = None
    reais: dict = {}
    for m in medidas:
        valor = float(m["valor_cm"].replace(",", "."))
        if chave(m["objeto"]).startswith("postit"):
            ref = {"auto": "postit_rosa", "tamanho_cm": valor}
            continue
        # coluna opcional so_em: a medida só vale nas fotos cujo nome contém este trecho (altura do pote: só de lado)
        reais.setdefault(chave(m["objeto"]), []).append(
            (SINONIMOS.get(chave(m["medida"]), chave(m["medida"])), valor, chave(m.get("so_em", "") or "")))
    pistas_arquivo = pasta / "pistas.json"
    pistas_extra = json.loads(pistas_arquivo.read_text(encoding="utf-8")) if pistas_arquivo.exists() else {}
    linhas, pistas = [], {}
    for sub in sorted(p for p in pasta.iterdir() if p.is_dir()):
        objeto = chave(sub.name)
        if objeto.startswith("postit") or objeto not in reais:
            if objeto not in reais and not objeto.startswith("postit"):
                print(f"aviso: {sub.name} sem medida no medidas.csv; fica de fora")
            continue
        for foto in sorted(f for f in sub.iterdir() if f.suffix.lower() in EXTENSOES):
            rel = f"{sub.name}/{foto.name}"
            pistas[rel] = pistas_extra.get(rel) or {"centro": True}
            for medida, valor, so_em in reais[objeto]:
                if so_em and so_em not in chave(foto.name):
                    continue
                linhas.append({"arquivo": rel, "objeto": objeto, "medida": medida, "valor_cm": valor,
                               "referencia_na_foto": "auto" if ref else "", "observacao": "",
                               "grupo": grupo_da_foto(foto.name)})
    return linhas, pistas, ref


def avaliar_fotos(pasta: Path, variantes: list[str], sam: str, pistas_modos: list[str], saida: Path,
                  linhas_gab: list[dict] | None = None, pistas: dict | None = None, ref_auto: dict | None = None,
                  usar_exif: bool = True) -> dict:
    from nucleo.medicao.profundidade import Profundidade, abrir
    from nucleo.medicao.segmentar import Segmentador

    if linhas_gab is None:
        linhas_gab, pistas = ler_gabarito(pasta)
    seg = Segmentador(sam)
    resultado_linhas: list[dict] = []
    tempos: dict = {}
    for v in variantes:
        if v == "da3":
            from nucleo.medicao.profundidade import ProfundidadeDA3

            prof = ProfundidadeDA3(usar_exif=usar_exif)
        else:
            prof = Profundidade(v, usar_exif=usar_exif)
        t0 = time.perf_counter()
        prof.carregar()
        tempos[f"carregar_{v}_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        med = Medidor(prof, seg)
        for arquivo in dict.fromkeys(l["arquivo"] for l in linhas_gab):
            img = abrir(pasta / arquivo)
            p = pistas[arquivo]
            # "usar" no pistas.json escolhe a pista daquela foto (ponto ou caixa) e a linha sai como "marcada"
            modos = ["ponto"] if p.get("centro") else ["marcada"] if p.get("usar") else [m for m in pistas_modos if m in p]
            for modo in modos:
                if p.get("centro"):
                    pista = {"ponto": (img.width / 2, img.height / 2)}
                elif modo == "marcada":
                    pista = {p["usar"]: p[p["usar"]]}
                else:
                    pista = {modo: p[modo]}
                ref = None
                linhas_foto = [l for l in linhas_gab if l["arquivo"] == arquivo]
                nome_ref = next((l["referencia_na_foto"] for l in linhas_foto if l["referencia_na_foto"]), "")
                if nome_ref == "auto":
                    ref = dict(ref_auto)
                elif nome_ref:
                    ref = dict(p["referencias"][nome_ref])
                try:
                    m_sem = med.medir(img, pista)
                except ValueError as e:
                    print(f"{v} {modo:5s} {arquivo}: não mediu ({e})")
                    continue
                m_com = None
                if ref:
                    try:
                        m_com = med.medir(img, pista, ref)
                    except ValueError as e:  # foto sem o post-it (as de comparação): só sem referência
                        print(f"{v} {modo:5s} {arquivo}: sem referência na foto ({e})")
                nome_saida = arquivo.replace("/", "__").rsplit(".", 1)[0]
                _desenhar(img, m_com or m_sem, saida / "contornos" / f"{nome_saida}_{v}_{modo}.jpg", f"{v} {modo} {m_sem.forma}")
                print(f"{v} {modo:5s} {arquivo}: {m_sem.forma}, tempos {m_sem.tempos_ms}")
                for l in linhas_foto:
                    chave = f"{l['medida']}_cm"
                    resultado_linhas.append(
                        {
                            "arquivo": arquivo,
                            "objeto": l["objeto"],
                            "medida": l["medida"],
                            "valor_cm": l["valor_cm"],
                            "modelo": v,
                            "pista": modo,
                            "forma": m_sem.forma,
                            "vertical": m_sem.vertical,
                            "lente": m_sem.lente,
                            "nota_contorno": m_sem.nota_contorno,
                            "estimado_sem_ref": getattr(m_sem, chave),
                            "incerteza_sem_ref": m_sem.incerteza_cm.get(l["medida"]),
                            "estimado_com_ref": getattr(m_com, chave) if m_com else None,
                            "incerteza_com_ref": m_com.incerteza_cm.get(l["medida"]) if m_com else None,
                            "estimado_plano": (m_com.no_plano_da_referencia.get(chave) if m_com else None),
                            "tempos_ms": m_sem.tempos_ms,
                            "observacao": l["observacao"],
                            "grupo": l.get("grupo", ""),
                        }
                    )
    _calibrar_deixando_uma_fora(resultado_linhas, "estimado_sem_ref", "estimado_calibrado")
    _erros(resultado_linhas)
    return {"linhas": resultado_linhas, "tempos_carregar": tempos, "sam": modelos.SAM[sam]}


def avaliar_sintetico(semente: int = 0) -> dict:
    """As cenas do roteiro com um erro de escala sorteado por cena (como o de um modelo), mais uma cena com
    a régua ao lado da porta para o modo com referência."""
    from nucleo.medicao import sintetico as s

    rng = np.random.default_rng(semente)
    linhas = []
    cenas = s.cenas_padrao(ruido=0.01)
    porta = s.Objeto("porta", (-0.6, 0.0, 3.0), (0.90, 2.10, 0.0))
    regua = s.Objeto("regua", (0.5, 0.3, 2.9), (0.30, 0.035, 0.0))
    cenas["porta e régua juntas a 3 m"] = (s.cena([porta, regua], ruido=0.01, semente=5), "porta", {"comprimento": 2.10, "largura": 0.90})
    for nome, (cena, objeto, reais) in cenas.items():
        escala = float(rng.normal(1.0, 0.08))
        med = Medidor(s.ProfundidadeSintetica(cena, escala), s.SegmentadorSintetico(cena))
        img = s.imagem_da_cena(cena)
        ys, xs = np.nonzero(cena.mascaras[objeto])
        pista = {"ponto": (float(np.median(xs)), float(np.median(ys)))}
        m_sem = med.medir(img, pista)
        m_com = None
        if "regua" in cena.mascaras and objeto != "regua":
            ry, rx = np.nonzero(cena.mascaras["regua"])
            m_com = med.medir(img, pista, {"ponto": (float(np.median(rx)), float(np.median(ry))), "tamanho_cm": 30.0, "nome": "régua"})
        for medida, real in reais.items():
            linhas.append(
                {
                    "arquivo": nome,
                    "objeto": objeto,
                    "medida": medida,
                    "valor_cm": real * 100,
                    "modelo": "sintético",
                    "pista": "ponto",
                    "forma": m_sem.forma,
                    "vertical": m_sem.vertical,
                    "escala_simulada": round(escala, 4),
                    "estimado_sem_ref": getattr(m_sem, f"{medida}_cm"),
                    "incerteza_sem_ref": m_sem.incerteza_cm.get(medida),
                    "estimado_com_ref": getattr(m_com, f"{medida}_cm") if m_com else None,
                    "tempos_ms": m_sem.tempos_ms,
                    "observacao": "ruído de 1 % na profundidade",
                }
            )
    _calibrar_deixando_uma_fora(linhas, "estimado_sem_ref", "estimado_calibrado")
    _erros(linhas)
    return {"linhas": linhas, "tempos_carregar": {}, "sam": "sintético"}


def resumir(res: dict) -> dict:
    grupos: dict = {}
    for l in res["linhas"]:
        chaves = [f"{l['modelo']} · {l['pista']}"]
        if l.get("grupo"):  # fotos marcadas no nome: também por tipo (ideal, normal, difícil)
            chaves = [f"{chaves[0]} · todas", f"{chaves[0]} · {l['grupo']}"]
        for k in chaves:
            g = grupos.setdefault(k, {"sem_ref": [], "com_ref": [], "calibrado": [], "plano": [], "tempo": []})
            for modo in ("sem_ref", "com_ref", "calibrado", "plano"):
                g[modo].append(l.get(f"erro_{modo}_rel"))
            g["tempo"].append(l["tempos_ms"].get("total"))
    saida = {}
    for k, g in grupos.items():
        tempos = [t for t in g["tempo"] if t]
        saida[k] = {
            "sem referência": resumo(g["sem_ref"]),
            "com referência": resumo(g["com_ref"]),
            "calibrado pela câmera": resumo(g["calibrado"]),
            "plano da referência": resumo(g["plano"]),
            "tempo_mediano_ms": round(float(np.median(tempos)), 1) if tempos else None,
        }
    return saida


def _f(v, casas=1):
    return "—" if v is None else f"{v:.{casas}f}".replace(".", ",")


def markdown(res: dict, resumo_: dict, titulo: str) -> str:
    out = [f"# {titulo}", ""]
    out += ["## Resumo por modelo e pista", "", "| Modelo · pista | Modo | n | Erro mediano | Viés mediano | Intervalo de 95 % | Erro máximo |", "|---|---|---|---|---|---|---|"]
    for k, r in resumo_.items():
        for modo in ("sem referência", "com referência", "calibrado pela câmera", "plano da referência"):
            s = r[modo]
            if not s.get("n"):
                continue
            ic = s["intervalo_95_pct"]
            out.append(
                f"| {k} | {modo} | {s['n']} | {_f(s['erro_mediano_pct'])} % | {_f(s['vies_mediano_pct'])} % | "
                f"{_f(ic[0])} a {_f(ic[1])} % | {_f(s['erro_maximo_pct'])} % |"
            )
    out += ["", "Tempo mediano por medição (ms): " + ", ".join(f"{k}: {_f(r['tempo_mediano_ms'], 0)}" for k, r in resumo_.items()), ""]
    out += ["## Por foto", "", "| Foto | Medida | Real (cm) | Modelo · pista | Forma | Sem ref. (cm) | ± | Erro | Calibrado (cm) | Erro | Com ref. (cm) | Erro | Plano da ref. (cm) | Erro |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for l in res["linhas"]:
        def pct(x):
            return "—" if x is None else f"{x * 100:+.1f} %".replace(".", ",")

        out.append(
            f"| {l['arquivo']} | {l['medida']} | {_f(l['valor_cm'], 2)} | {l['modelo']} · {l['pista']} | {l['forma']} | "
            f"{_f(l['estimado_sem_ref'], 2)} | {_f(l.get('incerteza_sem_ref'), 2)} | {pct(l['erro_sem_ref_rel'])} | "
            f"{_f(l.get('estimado_calibrado'), 2)} | {pct(l['erro_calibrado_rel'])} | {_f(l['estimado_com_ref'], 2)} | {pct(l['erro_com_ref_rel'])} | "
            f"{_f(l.get('estimado_plano'), 2)} | {pct(l.get('erro_plano_rel'))} |"
        )
    out += ["", "## Tempos por etapa (ms)", "", "| Foto | Modelo · pista | Etapas |", "|---|---|---|"]
    vistos = set()
    for l in res["linhas"]:
        k = (l["arquivo"], l["modelo"], l["pista"])
        if k in vistos:
            continue
        vistos.add(k)
        out.append(f"| {l['arquivo']} | {l['modelo']} · {l['pista']} | " + ", ".join(f"{e} {_f(t, 0)}" for e, t in l["tempos_ms"].items()) + " |")
    if res.get("tempos_carregar"):
        out += ["", "Carregar os modelos (ms): " + ", ".join(f"{k} {_f(v, 0)}" for k, v in res["tempos_carregar"].items())]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gabarito", type=Path, default=PASTA_GABARITO)
    ap.add_argument("--pasta", type=Path, help="uma subpasta por objeto e medidas.csv (ver o cabeçalho)")
    ap.add_argument("--modelos", nargs="+", default=list(modelos.MOGE), choices=[*modelos.MOGE, "da3"],
                    help="vits vitb vitl (MoGe-2) e da3 (Depth Anything 3 Metric Large)")
    ap.add_argument("--sam", default=modelos.SAM_PADRAO, choices=list(modelos.SAM))
    ap.add_argument("--pistas", nargs="+", default=["ponto", "caixa"], choices=["ponto", "caixa"])
    ap.add_argument("--sintetico", action="store_true", help="avaliar nas cenas sintéticas (sem modelo)")
    ap.add_argument("--sem-exif", action="store_true", help="ignorar a lente gravada na foto (usar a estimada)")
    ap.add_argument("--saida", type=Path, default=PASTA_SAIDA)
    args = ap.parse_args(argv)

    args.saida.mkdir(parents=True, exist_ok=True)
    if args.sintetico:
        res = avaliar_sintetico()
        titulo = "Medição em foto comum: cenas sintéticas"
    elif args.pasta:
        linhas, pistas, ref = ler_pasta(args.pasta)
        print(f"{len(pistas)} fotos, {len(linhas)} medidas, referência automática: {ref}")
        res = avaliar_fotos(args.pasta, args.modelos, args.sam, args.pistas, args.saida, linhas, pistas, ref,
                            usar_exif=not args.sem_exif)
        titulo = f"Medição em foto comum: {args.pasta.name}"
    else:
        res = avaliar_fotos(args.gabarito, args.modelos, args.sam, args.pistas, args.saida)
        titulo = "Medição em foto comum: gabarito"
    res["dispositivo"] = modelos.dispositivo()
    res["resumo"] = resumir(res)
    nome = "relatorio_sintetico" if args.sintetico else "relatorio"
    (args.saida / f"{nome}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.saida / f"{nome}.md").write_text(markdown(res, res["resumo"], titulo), encoding="utf-8")
    print(json.dumps(res["resumo"], indent=2, ensure_ascii=False))
    print("gravado em", args.saida / f"{nome}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
