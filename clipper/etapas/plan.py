"""Etapa 7: convierte cada clip elegido en una receta de montaje (clip.json).

Cortes en el silencio real, pausas fuera, velocidad con cuadros exactos, páginas de subtítulos, punch-ins en las
palabras de énfasis y un cambio visual cada pocos segundos. La lógica de cortes viene del motor v4 de AztroTech.
"""
import bisect
import re

from .. import config
from ..config import FPS
from ..energia import Energia
from .segment import inflada

PRE, POST = 0.04, 0.14


def piezas_de(palabras, todas, en, mj, dur_src):
    """Agrupa palabras en tramos continuos y ajusta cada corte al silencio real."""
    piezas, run = [], [palabras[0]]
    for w in palabras[1:]:
        hueco = w["t0"] - run[-1]["t1"] > mj["gap_corte"]
        if hueco:  # Whisper a veces inventa pausas: solo se parte si de verdad hay silencio
            a_, b_ = run[-1]["t1"] - 0.05, w["t0"] + 0.05
            hueco = any(en.quieto(a_ + i * 0.01, a_ + i * 0.01 + 0.1) for i in range(max(0, int((b_ - a_ - 0.1) * 100)) + 1))
        if hueco or w["gi"] != run[-1]["gi"] + 1:  # salto de oración omitida = corte obligado
            piezas.append(run); run = []
        run.append(w)
    piezas.append(run)
    ini_s = [x["t0"] for x in todas]
    out = []
    for k, ws in enumerate(piezas):
        w0, w1 = ws[0], ws[-1]
        i0 = bisect.bisect_left(ini_s, w0["t0"] - 0.005)
        prev_t1 = todas[i0 - 1]["t1"] if i0 > 0 else 0.0
        i1 = bisect.bisect_right(ini_s, w1["t0"] + 0.005)
        next_t0 = todas[i1]["t0"] if i1 < len(todas) else dur_src
        if inflada(w0, True):
            cands = [round(w0["t1"] - 0.6 + i * 0.01, 2) for i in range(55)]
            a_ = min(cands, key=lambda t: (round(en.nivel(t)), -t)) + 0.05
        else:
            a_ = en.inicio(w0["t0"], max(prev_t1 + 0.02, w0["t0"] - 0.35))
            real = en.arranque_real(w0["t0"], w0["t1"])
            if real:
                cands = [round(real - 0.3 + i * 0.01, 2) for i in range(29)]
                a_ = min(cands, key=lambda t: (round(en.nivel(t)), -t)) + 0.05
        b_ = en.fin(w1["t1"], min(next_t0 - 0.02, w1["t1"] + 0.45))
        s0 = max(0.0, a_ - 0.05)
        # el último tramo deja una cola para que el clip no termine en seco, pero nunca entra a la palabra siguiente
        s1 = min(dur_src, b_ + (0.45 if k == len(piezas) - 1 else 0.08), next_t0 - 0.06)
        while s1 - 0.01 > w1["t1"] and max(en.nivel(s1 - x * 0.01) for x in range(3)) >= en.umbral:
            s1 = round(s1 - 0.01, 2)  # nunca cerrar cuando ya arranca otro sonido
        # palabras pegadas (sin silencio entre ellas): el corte va al valle de sonido más cercano, no a ciegas
        if en.nivel(s1) > en.umbral + 6:
            cands = [round(w1["t1"] - 0.25 + i * 0.01, 2) for i in range(56)]
            cands = [t for t in cands if w1["t0"] + 0.1 < t <= next_t0 + 0.12] or [s1]
            s1 = min(cands, key=lambda t: (round(en.nivel(t)), abs(t - w1["t1"])))
        if en.nivel(s0) > en.umbral + 6:
            cands = [round(w0["t0"] - 0.3 + i * 0.01, 2) for i in range(51)]
            cands = [t for t in cands if prev_t1 - 0.12 <= t < w0["t1"] - 0.1] or [s0]
            s0 = max(0.0, min(cands, key=lambda t: (round(en.nivel(t)), abs(t - w0["t0"]))))
        # ajuste fino: entrada y salida al punto más silencioso a ±80 ms (si mejora al menos 4 dB)
        s0 = _afinar(en, s0, max(prev_t1 - 0.02, s0 - 0.08), min(w0["t0"] + 0.03, s0 + 0.08))
        s1 = _afinar(en, s1, max(w1["t1"] - 0.15, s1 - 0.08), s1 + 0.08)
        out.append({"palabras": ws, "s0": s0, "s1": s1})
    return out


def _afinar(en, t, a, b):
    if b <= a:
        return t
    cands = [round(a + i * 0.01, 2) for i in range(int(round((b - a) * 100)) + 1)]
    mejor = min(cands, key=lambda x: (en.nivel(x), abs(x - t)))
    return mejor if en.nivel(mejor) <= en.nivel(t) - 4 else t


def quitar_pausas(piezas, en, mj):
    nuevas = []
    for pz in piezas:
        a0, a1 = pz["s0"], pz["s1"]
        runs = en.silencios(a0, a1, mj["silencio_min"])
        pad = mj["silencio_pad"]
        bordes = [a0] + [x for r in runs for x in (r[0] + pad, r[1] - pad)] + [a1]
        segs = [(bordes[j], bordes[j + 1]) for j in range(0, len(bordes), 2)]
        asign = [[] for _ in segs]
        for w in pz["palabras"]:
            tras = [max(0.0, min(w["t1"], b1) - max(w["t0"], b0)) for b0, b1 in segs]
            mid = (w["t0"] + w["t1"]) / 2
            j_ = max(range(len(segs)), key=lambda j: (tras[j], -min(abs(mid - segs[j][0]), abs(mid - segs[j][1]))))
            asign[j_].append(w)
        for (b0, b1), ws in zip(segs, asign):
            if ws and b1 - b0 > 0.08:
                nuevas.append({"palabras": ws, "s0": b0, "s1": b1})
    fus = []
    for pz in nuevas:
        hueco_voz = pz["palabras"][0]["t0"] - fus[-1]["palabras"][-1]["t1"] if fus else 0
        contiguas = fus and pz["palabras"][0]["gi"] == fus[-1]["palabras"][-1]["gi"] + 1
        if fus and contiguas and pz["s0"] - fus[-1]["s1"] < 0.15 and pz["s0"] > fus[-1]["s0"] and hueco_voz < 0.22:
            fus[-1]["s1"] = pz["s1"]; fus[-1]["palabras"] += pz["palabras"]
        else:
            if fus and pz["s0"] < fus[-1]["s1"]:
                pz["s0"] = fus[-1]["s1"]
            fus.append(pz)
    return fus


def corregir(palabras, correcciones):
    corr = [(c.split(), r) for c, r in correcciones.items()]
    ws = [dict(w) for w in palabras]
    for frase, rep in corr:
        n_, k = len(frase), 0
        while k + n_ <= len(ws):
            if [config.norm(x["w"]) for x in ws[k:k + n_]] == [config.norm(x) for x in frase]:
                punt = re.search(r"[.,?!:;…]*$", ws[k + n_ - 1]["w"])[0]
                ws[k] = {**ws[k], "w": rep + punt, "t1": ws[k + n_ - 1]["t1"]}
                del ws[k + 1:k + n_]
            k += 1
    return ws


def linea_de_tiempo(piezas, vel):
    """Cada tramo dura un número entero de cuadros ya acelerado (sin deriva de audio contra video)."""
    cuadros = 0  # los tiempos de salida salen de cuadros acumulados: cero deriva aunque haya cientos de cortes
    for pz in piezas:
        pz["s0"] = round(pz["s0"], 4)
        nf = max(1, round((pz["s1"] - pz["s0"]) / vel * FPS))
        pz["nf"] = nf
        pz["s1"] = round(pz["s0"] + nf / FPS * vel, 4)
        pz["o0"] = round(cuadros / FPS, 6)
        cuadros += nf
        pz["o1"] = round(cuadros / FPS, 6)
    return round(cuadros / FPS, 6)


def paginas_subtitulos(palabras, total, st):
    paginas, cur = [], []
    for k, w in enumerate(palabras):
        cur.append(k)
        txt = " ".join(palabras[j]["texto"] for j in cur)
        nxt = palabras[k + 1] if k + 1 < len(palabras) else None
        if (len(cur) >= st["max_palabras"] or len(txt) >= st["max_chars"] or re.search(r"[.,?!:;…]$", w["texto"])
                or nxt is None or nxt["pieza"] != w["pieza"] or nxt["t0"] - w["t1"] > 0.25):
            paginas.append(cur); cur = []
    out = []
    for k, idx in enumerate(paginas):
        fin = palabras[idx[-1]]["t1"] + 0.3
        if k + 1 < len(paginas):
            fin = min(fin, palabras[paginas[k + 1][0]]["t0"])
        out.append({"t0": round(palabras[idx[0]]["t0"], 3), "t1": round(min(fin, total), 3), "palabras": idx})
    return out


def punch_ins(piezas, palabras, mj, total, cta_dur):
    """Zoom de golpe en palabras de énfasis; luego rellena huecos sin cambio visual mayores al máximo."""
    n_total = 0
    ult = -9.0
    for w in palabras:
        if not w["enfasis"] or n_total >= mj["punch_max"]:
            continue
        if w["t0"] < 1.5 or w["t0"] - ult < mj["punch_sep"] or w["t0"] > total - cta_dur - 0.3:
            continue
        pz = piezas[w["pieza"]]
        rel = w["t0"] - 0.04 - pz["o0"]
        if rel < 0.25 or pz["o1"] - w["t0"] < 0.3:
            continue
        pz.setdefault("punch", []).append([round(rel, 3), mj["punch"]])
        n_total += 1
        ult = w["t0"]
    # regla de ritmo: un cambio visual cada intervalo_visual_max segundos como máximo
    eventos = sorted({0.0, *(pz["o0"] for pz in piezas), *(pz["o0"] + p[0] for pz in piezas for p in pz.get("punch", []))})
    eventos.append(total)
    for a, b in zip(eventos, eventos[1:]):
        hueco = b - a
        if hueco <= mj["intervalo_visual_max"] or a > total - cta_dur:
            continue
        n = int(hueco // mj["intervalo_visual_max"])
        for j in range(1, n + 1):
            t = a + hueco * j / (n + 1)
            pz = next((p for p in piezas if p["o0"] + 0.3 <= t <= p["o1"] - 0.4), None)
            if pz:
                pz.setdefault("punch", []).append([round(t - pz["o0"], 3), round(mj["punch"] * 0.6, 3)])
    for pz in piezas:
        if "punch" in pz:
            pz["punch"].sort()


def construir_clip(ep, c, ors, todas, en, vel):
    mj, st, cta_cfg = ep.marca["montaje"], ep.marca["subtitulos"], ep.marca["cta"]
    por_id = {o["id"]: o for o in ors}
    rec = c.get("recortes", {})
    palabras = [dict(w, lid=oid) for oid in c["oraciones"]
                for w in por_id[oid]["palabras"][slice(*rec.get(oid, [None, None]))]]
    gi_por_t = {(w["t0"], w["w"]): i for i, w in enumerate(todas)}
    for w in palabras:
        w["gi"] = gi_por_t.get((w["t0"], w["w"]), -10)
    piezas = piezas_de(palabras, todas, en, mj, ep.meta["dur"])
    piezas = quitar_pausas(piezas, en, mj)
    for pz in piezas:
        pz["palabras"] = corregir(pz["palabras"], ep.marca.get("correcciones", {}))
    total = linea_de_tiempo(piezas, vel)
    enfasis = {config.norm(x) for x in c.get("enfasis", [])}
    salida = []
    for k, pz in enumerate(piezas):
        for w in pz["palabras"]:
            t0 = pz["o0"] + max(0.0, w["t0"] - pz["s0"]) / vel
            t1 = pz["o0"] + max(0.0, min(w["t1"], pz["s1"]) - pz["s0"]) / vel
            n = config.norm(w["w"])
            salida.append({"texto": w["w"], "t0": round(t0, 3), "t1": round(max(t1, t0 + 0.05), 3), "pieza": k,
                           "enfasis": bool(n and (n in enfasis or re.search(r"\d", w["w"])))})
    cta_dur = min(cta_cfg["dur"], total * 0.25)
    punch_ins(piezas, salida, mj, total, cta_dur)
    paginas = paginas_subtitulos(salida, total, st)
    return {
        "version": 1, "id": c["id"], "marca": ep.marca["id"], "titulo": c["titulo"], "gancho": c["gancho"],
        "hook_tipo": c.get("hook_tipo"), "viral_score": c.get("viral_score"), "razon": c.get("razon"),
        "descripcion": c.get("descripcion", ""), "hashtags": c.get("hashtags", []),
        "oraciones": c["oraciones"], "velocidad": vel, "dur": total,
        "piezas": [{"s0": pz["s0"], "s1": pz["s1"], "o0": pz["o0"], "o1": pz["o1"], "nf": pz["nf"],
                    "punch": pz.get("punch", []), "texto": " ".join(w["w"] for w in pz["palabras"])} for pz in piezas],
        "palabras": salida, "paginas": paginas,
        "gancho_overlay": {"texto": c["gancho"], "t0": 0.0, "dur": min(ep.marca["gancho"]["dur"], total)},
        "cta": {"modo": ep.meta.get("cta_modo", "palabra"), "palabra": ep.meta.get("palabra_cta"),
                "t0": round(total - cta_dur, 3), "dur": round(cta_dur, 3)},
    }


def correr(ep, solo=None):
    sel = config.leer(ep.ruta("05_select", "seleccion_validada.json"))
    ors = config.leer(ep.ruta("04_segment", "oraciones.json"))
    todas = [w for o in ors for w in o["palabras"]]
    en = Energia(ep.ruta("00_ingest", "voz16k.wav"))
    for c in sel["clips"]:
        if solo and c["id"] not in solo:
            continue
        clip = construir_clip(ep, c, ors, todas, en, sel["velocidad"])
        d = ep.ruta("clips", f"{c['id']}_{config.slugify(c['titulo'], 32)}")
        config.escribir(d / "clip.json", clip)
        n_p = sum(len(p["punch"]) for p in clip["piezas"])
        print(f"  clip {c['id']}: {clip['dur']:.1f}s · {len(clip['piezas'])} cortes · {n_p} punch-ins · {d.name}")
