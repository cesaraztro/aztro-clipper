"""Pruebas del núcleo: cortes en silencio, sincronía, línea de tiempo, selección, CTA y subtítulos."""
import numpy as np
import pytest

from clipper import config
from clipper.config import FPS
from clipper.energia import Energia
from clipper.etapas import cta, diarize, plan, segment, select, sync
from clipper.media import parsear_info
from clipper import subtitulos
from pathlib import Path

SR = 16000


def voz_sintetica(tramos, dur, sr=SR, seed=0):
    """Audio con 'voz' (ruido modulado fuerte) en los tramos dados y silencio suave en el resto."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 30, int(dur * sr))
    for a, b in tramos:
        i0, i1 = int(a * sr), int(b * sr)
        t = np.arange(i1 - i0) / sr
        x[i0:i1] += rng.normal(0, 6000, i1 - i0) * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
    return np.clip(x, -32768, 32767).astype(np.int16)


def test_energia_corta_en_silencio():
    en = Energia(muestras=voz_sintetica([(1.0, 2.0), (3.0, 4.0)], 5.0))
    assert en.nivel(1.5) > en.umbral > en.nivel(2.5)
    assert en.quieto(2.2, 2.8) and not en.quieto(1.2, 1.8)
    assert 1.95 <= en.fin(1.9, 2.9) <= 2.1          # la salida cae justo donde termina la voz
    assert 2.9 <= en.inicio(3.1, 2.1) <= 3.05       # la entrada justo antes de que arranque
    sil = en.silencios(0.0, 5.0, 0.14)
    assert any(a <= 2.1 and b >= 2.9 for a, b in sil)


def test_sincronia_encuentra_offset():
    rng = np.random.default_rng(1)
    maestro = rng.normal(0, 1, sync.SR * 120).astype(np.float32)
    off = 37.25
    camara = maestro[int(off * sync.SR): int((off + 30) * sync.SR)] * 0.3 + rng.normal(0, 0.05, sync.SR * 30)
    t, conf = sync.correlacion(maestro, camara)
    assert abs(t - off) < 1 / FPS  # dentro de un cuadro
    assert conf > 3


def test_linea_de_tiempo_cuadros_exactos():
    piezas = [{"s0": 1.0, "s1": 2.37}, {"s0": 5.0, "s1": 7.11}]
    total = plan.linea_de_tiempo(piezas, 1.12)
    for pz in piezas:
        assert pz["nf"] == round((pz["o1"] - pz["o0"]) * FPS)
        assert abs((pz["s1"] - pz["s0"]) / 1.12 - pz["nf"] / FPS) < 1e-3
    assert abs(total - sum(p["nf"] for p in piezas) / FPS) < 1e-6
    assert piezas[1]["o0"] == piezas[0]["o1"]


def _palabras(frases):
    out, t = [], 0.5
    for f in frases:
        for w in f.split():
            out.append({"w": w, "t0": round(t, 2), "t1": round(t + 0.3, 2), "p": 1.0})
            t += 0.35
        t += 1.5
    return out


def test_oraciones_y_recortes():
    ws = _palabras(["Hola a todos.", "La IA no adivina tu negocio.", "Dale contexto siempre."])
    ors = segment.construir_oraciones(ws)
    assert [o["id"] for o in ors] == ["S0001", "S0002", "S0003"]
    assert select.parse_ref("S0002[2:]") == ("S0002", (2, None))
    assert select.parse_ref("S0003[:2]") == ("S0003", (None, 2))
    assert select.parse_ref("S0003") == ("S0003", None)
    with pytest.raises(ValueError):
        select.parse_ref("12.5")


def test_cortes_no_invaden_palabras():
    ws = _palabras(["Esto es una prueba de cortes.", "Segunda frase aquí."])
    tramos = [(w["t0"] - 0.02, w["t1"] + 0.02) for w in ws]
    en = Energia(muestras=voz_sintetica(tramos, 8.0))
    for i, w in enumerate(ws):
        w["gi"] = i
    mj = config.MARCA_BASE["montaje"]
    piezas = plan.piezas_de(ws, ws, en, mj, 8.0)
    piezas = plan.quitar_pausas(piezas, en, mj)
    for pz in piezas:
        for w in pz["palabras"]:
            assert pz["s0"] <= w["t0"] + 0.03 and w["t1"] - 0.03 <= pz["s1"]


def test_palabra_cta():
    assert cta.validar_palabra("CONTEXTO") == []
    assert cta.validar_palabra("HOLA")                       # demasiado común
    assert cta.validar_palabra("IA")                         # muy corta
    assert cta.validar_palabra("ARQUITECTO", ["ARQUI"])      # choca por "contiene"
    assert cta.normalizar("Construcción") == "CONSTRUCCION"


def test_kmeans_separa_dos_voces():
    rng = np.random.default_rng(2)
    X = np.vstack([rng.normal(0, 0.3, (40, 4)), rng.normal(3, 0.3, (25, 4))])
    lab = diarize.kmeans(X, 2)
    assert len(set(lab[:40])) == 1 and len(set(lab[40:])) == 1 and lab[0] != lab[-1]


def test_parsear_info_iphone_hdr_vertical():
    txt = ("Duration: 00:14:31.78, start: 0.000000\n  Stream #0:0[0x1](und): Video: hevc (Main 10) (hvc1), "
           "yuv420p10le(tv, bt2020nc/bt2020/arib-std-b67), 3840x2160, 24887 kb/s, 30 fps\n"
           "      displaymatrix: rotation of -90.00 degrees\n  Stream #0:1: Audio: aac")
    i = parsear_info(txt)
    assert (i["w"], i["h"]) == (2160, 3840) and i["hdr"] == "hlg" and i["audio"] and abs(i["dur"] - 871.78) < 0.01


def test_subtitulos_ass(tmp_path):
    marca = config.MARCA_BASE | {"_dir": str(tmp_path)}
    clip = {"dur": 5.0, "palabras": [{"texto": "La", "t0": 0.0, "t1": 0.3, "enfasis": False},
                                     {"texto": "IA", "t0": 0.3, "t1": 0.6, "enfasis": True}],
            "paginas": [{"t0": 0.0, "t1": 0.9, "palabras": [0, 1]}],
            "gancho_overlay": {"texto": "Gancho", "t0": 0, "dur": 2}, "cta": {"palabra": "CONTEXTO", "t0": 3.0, "dur": 2.0}}
    for red in ("general", "tiktok", "youtube"):
        txt = subtitulos.escribir(clip, marca, tmp_path / f"s_{red}.ass", red).read_text(encoding="utf-8")
        assert "Style: Sub" in txt and "GANCHO" in txt
    assert "CONTEXTO" in (tmp_path / "s_general.ass").read_text(encoding="utf-8")
    assert "por DM" in (tmp_path / "s_tiktok.ass").read_text(encoding="utf-8")
    assert "descripción" in (tmp_path / "s_youtube.ass").read_text(encoding="utf-8")


def test_ruta_filtro_windows_y_espacios():
    from clipper import media
    r = media.ruta_filtro(Path("/tmp/AZTROTECH /mis videos, prueba/sub.ass"))
    assert r.startswith("'") and r.endswith("'") and "AZTROTECH /mis videos, prueba" in r
    # todo ':' (p. ej. la unidad C: de Windows) va escapado; sin escapar rompe el filtro de subtítulos
    assert ":" not in r.replace("\\:", "")


def test_titulos_nunca_sobre_la_cara():
    # cabeza arriba (presentador de pie): el gancho baja; cabeza al centro: el gancho se queda arriba
    pz = lambda cab: {"o0": 0.0, "o1": 5.0, "camara": {"cabeza": cab}}
    arriba = {"piezas": [pz([150, 600])], "broll": []}
    assert subtitulos.y_libre(arriba, 0, 3, 260, [280, 700, 960]) == 700
    centro = {"piezas": [pz([600, 1000])], "broll": []}
    assert subtitulos.y_libre(centro, 0, 3, 260, [280, 700, 960]) == 280
    # con B-roll a pantalla completa no hay cara que esquivar
    tapada = {"piezas": [pz([150, 600])], "broll": [{"t0": 0.0, "dur": 5.0, "archivo": "x.mp4"}]}
    assert subtitulos.y_libre(tapada, 1, 3, 260, [280, 700, 960]) == 280
