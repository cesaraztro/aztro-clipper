"""Etapa 10: control de calidad automático. Un clip que no pasa queda bloqueado para publicar.

Revisa: formato que acepta cada red, duración, volumen (LUFS) y picos, cortes en silencio real, cuadros negros o
congelados, frases repetidas y que lo que se oye sea lo que se planeó (re-transcribe el clip final).
Genera una hoja de contacto para el revisor humano o el subagente revisor.
"""
import difflib
import re
import subprocess

from .. import config, media
from ..config import FPS, H, W
from ..energia import Energia

LIMITES = {"instagram": (3, 900), "facebook": (4, 90), "tiktok": (3, 600), "youtube": (1, 180)}


def repeticiones(textos, ventana=10):
    n_ = [config.norm(t) for t in textos]
    vistas, out = {}, []
    for k in range(len(n_) - 2):
        clave = tuple(n_[k:k + 3])
        if len("".join(clave)) < 10:
            continue
        if clave in vistas and k - vistas[clave] < ventana * 3:
            out.append(" ".join(textos[k:k + 3]))
        vistas[clave] = k
    return out


def similitud(a, b):
    na = [config.norm(x) for x in a.split() if config.norm(x)]
    nb = [config.norm(x) for x in b.split() if config.norm(x)]
    return difflib.SequenceMatcher(None, na, nb).ratio()


def hoja_contacto(video, destino, dur):
    n = 12
    paso = max(0.5, dur / n)
    media.correr([media.ffmpeg_bin(), "-y", "-v", "error", "-i", str(video), "-vf",
                  f"fps=1/{paso:.3f},scale=270:-2,drawtext=text='%{{pts\\:hms}}':x=8:y=8:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.5,tile=6x2",
                  "-frames:v", "1", str(destino)])


def revisar(ep, clip, cdir, en, rapido=False):
    m = ep.marca
    video = cdir / "video_general.mp4"
    fallas, avisos, datos = [], [], {}
    if not video.exists():
        return {"ok": False, "fallas": ["no hay render"], "avisos": [], "datos": {}}
    info_txt = subprocess.run([media.ffmpeg_bin(), "-hide_banner", "-i", str(video)], capture_output=True, text=True).stderr
    info = media.parsear_info(info_txt)
    datos.update(dur=info["dur"], ancho=info["w"], alto=info["h"], codec=info["vcodec"], mb=round(video.stat().st_size / 1e6, 1))
    if info["vcodec"] != "h264" or "yuv420p" not in info_txt or info["hdr"]:
        fallas.append("formato: debe ser H.264 yuv420p SDR (Metricool no autopublica HEVC/HDR)")
    if (info["w"], info["h"]) != (W, H):
        fallas.append(f"tamaño {info['w']}x{info['h']} (esperado {W}x{H})")
    if datos["mb"] > 100:
        fallas.append(f"pesa {datos['mb']} MB (>100 MB: el enlace de Drive falla en Metricool)")
    for red, (a, b) in LIMITES.items():
        if not a <= info["dur"] <= b and red in m["publicacion"]["redes"]:
            avisos.append(f"{red}: duración {info['dur']:.0f}s fuera de {a}–{b}s")
    lufs, pico = media.medir_loudness(video)
    datos.update(lufs=lufs, pico=pico)
    if lufs is None or abs(lufs - m["audio"]["lufs"]) > 1.5:
        fallas.append(f"volumen {lufs} LUFS (meta {m['audio']['lufs']}±1.5)")
    if pico is not None and pico > -0.5:
        fallas.append(f"pico de audio {pico} dBFS (satura)")
    # cortes: cada entrada y salida de tramo debe caer en silencio real del audio original
    malos = []
    for k, pz in enumerate(clip["piezas"]):
        for t, lado in ((pz["s0"], "entrada"), (pz["s1"], "salida")):
            if en.nivel(t) > en.umbral + 6:
                malos.append(f"tramo {k + 1} {lado} ({en.nivel(t):.0f} dB)")
    datos["cortes_en_silencio"] = round(1 - len(malos) / (2 * len(clip["piezas"])), 3)
    if datos["cortes_en_silencio"] < 0.9:
        fallas.append(f"cortes sobre voz: {', '.join(malos[:5])}")
    elif malos:
        avisos.append(f"{len(malos)} corte(s) con algo de sonido: {', '.join(malos[:3])}")
    neg = subprocess.run([media.ffmpeg_bin(), "-hide_banner", "-i", str(video), "-vf",
                          "blackdetect=d=0.4:pix_th=0.08,freezedetect=n=0.002:d=1.5", "-an", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    if "black_start" in neg:
        fallas.append("hay cuadros negros")
    if "freeze_start" in neg:
        avisos.append("hay un tramo congelado de más de 1.5 s")
    rep = repeticiones([w["texto"] for w in clip["palabras"]])
    if rep:
        avisos.append(f"frase repetida (¿toma doble?): {rep[0]}")
    if not rapido:
        from .transcribe import transcribir_wav
        wav = cdir / "render" / "qa16k.wav"
        media.extraer_audio(video, wav)
        r = transcribir_wav(wav, m)
        oido = " ".join(s["text"] for s in r["segments"])
        plan = " ".join(w["texto"] for w in clip["palabras"])
        datos["similitud"] = round(similitud(plan, oido), 3)
        if datos["similitud"] < 0.85:
            fallas.append(f"lo que se oye no coincide con lo planeado (similitud {datos['similitud']})")
    hoja_contacto(video, cdir / "hoja.jpg", info["dur"])
    return {"ok": not fallas, "fallas": fallas, "avisos": avisos, "datos": datos}


def correr(ep, solo=None, rapido=False):
    en = Energia(ep.ruta("00_ingest", "voz16k.wav"))
    todo_ok = True
    for cp in ep.clips():
        clip = config.leer(cp)
        if solo and clip["id"] not in solo:
            continue
        res = revisar(ep, clip, cp.parent, en, rapido)
        config.escribir(cp.parent / "qa.json", res)
        todo_ok &= res["ok"]
        d = res["datos"]
        print(f"  clip {clip['id']}: {'OK' if res['ok'] else 'FALLA'} · {d.get('dur', 0):.1f}s · {d.get('lufs')} LUFS · "
              f"cortes en silencio {d.get('cortes_en_silencio', 0):.0%} · similitud {d.get('similitud', '-')} · {d.get('mb')} MB")
        for f in res["fallas"]:
            print(f"     ✗ {f}")
        for a in res["avisos"]:
            print(f"     ! {a}")
    return todo_ok
