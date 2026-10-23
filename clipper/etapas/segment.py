"""Etapa 5: divide la transcripción en oraciones numeradas (S0001…) y escribe la versión que lee el agente.

El agente elige clips citando IDs de oración, nunca segundos: el código convierte esa elección en cortes exactos.
"""
import re

from .. import config
from ..energia import Energia

ALUCINACIONES = ["gracias por ver", "suscribete", "subtitulos realizados por", "amara.org", "gracias por su atencion"]


def dur_max(w):
    """Duración máxima creíble de una palabra; si Whisper le asigna más, casi siempre se tragó audio."""
    letras = len(re.sub(r"\W", "", w["w"]))
    digitos = len(re.sub(r"\D", "", w["w"]))
    if digitos:
        letras = max(letras, digitos * 4 + 2)
    return max(0.6, 0.11 * letras + 0.4)


def inflada(w, primera=False):
    return w["t1"] - w["t0"] > dur_max(w) + (0.6 if primera else 0)


def palabras_de(tj, dur):
    words = []
    for seg in tj.get("segments", []):
        for w in seg.get("words", []):
            t = w["word"].strip()
            if t and w["end"] > w["start"] and w["start"] < dur - 0.05:
                words.append({"w": t, "t0": round(w["start"], 3), "t1": round(min(w["end"], dur), 3),
                              "p": round(w.get("p", 1.0), 3)})
    words.sort(key=lambda x: x["t0"])
    limpio = []
    for w in words:
        if limpio and abs(w["t0"] - limpio[-1]["t0"]) < 0.02 and w["w"] == limpio[-1]["w"]:
            continue
        limpio.append(w)
    return limpio


def construir_oraciones(words, max_dur=22.0):
    grupos, actual = [], []
    for w in words:
        if actual and w["t0"] - actual[-1]["t1"] > 1.2:
            grupos.append(actual); actual = []
        actual.append(w)
        fin_frase = re.search(r"[.?!…]$", w["w"])
        larga = actual[-1]["t1"] - actual[0]["t0"] > max_dur and re.search(r"[,;:]$", w["w"])
        if fin_frase or larga:
            grupos.append(actual); actual = []
    if actual:
        grupos.append(actual)
    out = []
    for ws in grupos:
        if ws[-1]["t1"] - ws[0]["t0"] < 0.25:
            continue
        texto = " ".join(x["w"] for x in ws)
        alerta = []
        # en conversación la gente alarga palabras ("y…", "este…"): solo se alerta lo que de verdad no cabe
        if any(w["t1"] - w["t0"] > dur_max(w) + 1.0 for w in ws):
            alerta.append("audio-tragado")
        if any(a in config.norm(texto) for a in map(config.norm, ALUCINACIONES)):
            alerta.append("posible-alucinacion")
        out.append({"id": f"S{len(out) + 1:04d}", "t0": ws[0]["t0"], "t1": ws[-1]["t1"], "texto": texto,
                    "palabras": ws, "alertas": alerta})
    return out


def hhmmss(t):
    return f"{int(t // 3600):02d}:{int(t // 60 % 60):02d}:{t % 60:04.1f}"


def correr(ep):
    tj = config.leer(ep.ruta("02_transcribe", "transcripcion.json"))
    words = palabras_de(tj, ep.meta["dur"])
    en = Energia(ep.ruta("00_ingest", "voz16k.wav"))
    ors = construir_oraciones(words)
    for o in ors:
        # palabras sin voz debajo = Whisper inventó texto en un silencio
        if en.voz_activa(o["t0"], o["t1"]) < 0.15:
            o["alertas"].append("sin-voz")
    config.escribir(ep.ruta("04_segment", "oraciones.json"), ors)
    lineas = [f"# {ep.meta['slug']} · {ep.meta['dur'] / 60:.1f} min · {len(ors)} oraciones · marca {ep.meta['marca']}",
              "# Formato: ID [inicio–fin] texto. Elige clips citando IDs (p. ej. S0412–S0431). "
              "⚠ marca oraciones con audio dudoso: evítalas o revísalas."]
    for o in ors:
        aviso = f" ⚠{','.join(o['alertas'])}" if o["alertas"] else ""
        lineas.append(f"{o['id']} [{hhmmss(o['t0'])}–{hhmmss(o['t1'])}] {o['texto']}{aviso}")
    md = ep.ruta("04_segment", "transcripcion.md")
    md.write_text("\n".join(lineas) + "\n")
    print(f"  {len(ors)} oraciones → {md}")
    return md
