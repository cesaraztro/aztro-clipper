"""Subtítulos ASS (libass): palabra por palabra con énfasis, gancho arriba y CTA por red social.

La paginación y el resaltado palabra a palabra vienen del motor v4 de AztroTech.
"""
from pathlib import Path

from .config import H, W


def ass_color(hexrgb, alpha=0):
    r, g, b = hexrgb[1:3], hexrgb[3:5], hexrgb[5:7]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_t(t):
    cs = int(round(max(0.0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _escape(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def caras_en(clip, t0, t1):
    """Franjas verticales (px del video final) donde hay una cabeza entre t0 y t1; el B-roll a pantalla completa las tapa."""
    br = [(b["t0"], b["t0"] + b["dur"]) for b in clip.get("broll", []) if b.get("archivo")]
    out = []
    for pz in clip.get("piezas", []):
        a, b = max(pz["o0"], t0), min(pz["o1"], t1)
        if b <= a or any(x <= a and b <= y for x, y in br):
            continue
        cab = (pz.get("camara") or {}).get("cabeza")
        if cab:
            out.append(cab)
    return out


def y_libre(clip, t0, t1, alto, opciones):
    """Primer borde superior de 'opciones' cuya caja [y, y+alto] no toca ninguna cara; si todas chocan, la que menos."""
    caras = caras_en(clip, t0, t1)
    choque = lambda y: sum(max(0, min(y + alto, c1) - max(y, c0)) for c0, c1 in caras)
    return min(opciones, key=lambda y: (choque(y), opciones.index(y)))


CTA_TEXTOS = {
    "general": ("Comenta", "{P}", "y te mando el video completo"),
    "tiktok": ("Escríbeme", "{P}", "por DM y te mando el video completo"),
    "youtube": ("Video completo", "en la descripción", ""),
}


def escribir(clip, marca, ruta, red="general"):
    st, col, fu, gc = marca["subtitulos"], marca["colores"], marca["fuentes"], marca["gancho"]
    caja = ass_color(col["caja"], st.get("caja_alfa", 40))
    blanco, enf = ass_color(col["texto"]), ass_color(col["enfasis"])
    oscuro = ass_color(col["caja"])
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{fu['subtitulos']},{st['tam']},{blanco},{blanco},{caja},{caja},0,0,0,0,100,100,0,0,3,{st.get('relleno', 16)},0,2,80,80,{H - st['y']},1
Style: Gancho,{fu['titulo']},{gc['tam']},{oscuro},{oscuro},{enf},{enf},0,0,0,0,100,100,0,0,3,22,0,8,90,90,{gc['y']},1
Style: CTA,{fu['titulo']},64,{blanco},{blanco},{caja},{caja},0,0,0,0,100,100,0,0,3,26,0,2,90,90,{H - 1260},1
Style: Tarjeta,{fu['titulo']},124,{oscuro},{oscuro},{enf},{enf},0,0,0,0,100,100,0,0,3,24,0,5,60,60,0,1
Style: Firma,{fu['titulo']},62,{blanco},{blanco},{caja},{caja},0,0,0,0,100,100,0,0,3,18,0,1,70,70,{H - 1640},1
Style: Grafico,Arial,10,{blanco},{blanco},{blanco},{blanco},0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    palabras, ev = clip["palabras"], []
    cta = clip.get("cta") or {}
    for pg in clip["paginas"]:
        idx = pg["palabras"]
        for j, k in enumerate(idx):
            t0 = pg["t0"] if j == 0 else palabras[k]["t0"]
            t1 = palabras[idx[j + 1]]["t0"] if j + 1 < len(idx) else pg["t1"]
            if t1 - t0 < 0.01:
                continue
            partes = []
            for kk in idx:
                w = palabras[kk]
                c = enf if w["enfasis"] else blanco
                alfa = "&H00&" if kk <= k else "&H50&"
                partes.append(f"{{\\1c{c}\\1a{alfa}}}{_escape(w['texto'])}")
            pop = "{\\fad(120,0)\\fscx92\\fscy92\\t(0,120,\\fscx100\\fscy100)}" if j == 0 else ""
            ev.append(f"Dialogue: 0,{ass_t(t0)},{ass_t(t1)},Sub,,0,0,0,,{pop}{' '.join(partes)}")
    g = clip.get("gancho_overlay")
    if g and g.get("texto"):
        # nunca sobre la cara: arriba si la cabeza está abajo, si no a media pantalla (sobre el pecho)
        lineas = 1 + len(g["texto"]) * gc["tam"] * 0.62 // (W - 180)
        y = y_libre(clip, g["t0"], g["t0"] + g["dur"], int(lineas * gc["tam"] * 1.3 + 50), [gc["y"], 700, 960])
        ev.append(f"Dialogue: 1,{ass_t(g['t0'])},{ass_t(g['t0'] + g['dur'])},Gancho,,0,0,0,,"
                  f"{{\\an8\\pos({W // 2},{y})\\fad(150,250)\\fscx70\\fscy70\\t(0,180,\\fscx104\\fscy104)"
                  f"\\t(180,280,\\fscx100\\fscy100)}}{_escape(g['texto'].upper())}")
    mo = marca.get("motion", {})
    # barra de progreso arriba: se llena durante todo el clip (retención: "ya casi acaba")
    if mo.get("barra", True) and clip.get("dur"):
        ms = int(clip["dur"] * 1000)
        acento = ass_color(col.get("acento", col["enfasis"]))
        ev.append(f"Dialogue: 3,{ass_t(0)},{ass_t(clip['dur'] + 0.5)},Grafico,,0,0,0,,"
                  f"{{\\pos(0,0)\\1c{enf}\\clip(0,0,0,14)\\t(0,{ms},\\clip(0,0,{W},14))\\p1}}m 0 0 l {W} 0 {W} 14 0 14{{\\p0}}")
        ev.append(f"Dialogue: 2,{ass_t(0)},{ass_t(clip['dur'] + 0.5)},Grafico,,0,0,0,,"
                  f"{{\\pos(0,0)\\1c{acento}\\1a&HB0&\\p1}}m 0 0 l {W} 0 {W} 14 0 14{{\\p0}}")
    # palabras clave: entran con rebote y salen rápido (motion graphic sobre la palabra que se está diciendo)
    for tj in clip.get("tarjetas", []):
        t0, t1 = tj["t0"], tj["t0"] + tj["dur"]
        y0 = mo.get("tarjeta_y", 1180)
        y = y_libre(clip, t0, t1, 190, [y0 - 95, 880, 560]) + 95  # \pos es el centro de la tarjeta
        ev.append(f"Dialogue: 4,{ass_t(t0)},{ass_t(t1)},Tarjeta,,0,0,0,,"
                  f"{{\\pos({W // 2},{y})\\frz-3\\fad(60,140)\\fscx30\\fscy30\\t(0,140,\\fscx115\\fscy115)"
                  f"\\t(140,260,\\fscx100\\fscy100\\frz0)}}{_escape(tj['texto'])}")
    # firma: nombre y rol al inicio, se desliza desde la izquierda
    fi = marca.get("firma") or {}
    if fi.get("nombre"):
        a0 = mo.get("firma_desde", 0.6)
        a1 = min(a0 + mo.get("firma_dur", 3.2), clip.get("dur", 10) * 0.4)
        y = H - 230
        rol = f"\\N{{\\fs40\\b0\\1c{enf}}}{_escape(fi['rol'])}" if fi.get("rol") else ""
        ev.append(f"Dialogue: 4,{ass_t(a0)},{ass_t(a1)},Firma,,0,0,0,,"
                  f"{{\\an1\\move(-420,{y},70,{y},0,260)\\fad(0,200)}}{_escape(fi['nombre'])}{rol}")
    cta_pos = ""
    if cta.get("dur"):  # el bloque del CTA (~310 px) termina en 1260 o, si ahí hay cara, más arriba/abajo
        base = y_libre(clip, cta["t0"], clip.get("dur", cta["t0"] + cta["dur"]), 310, [950, 640, 380]) + 310
        cta_pos = f"\\an2\\pos({W // 2},{base})"
    if cta.get("modo") == "seguir" and cta.get("dur"):
        # sin link largo ni ManyChat: el cierre invita a seguir la cuenta (no promete nada que no se entregue)
        a, b, c = marca["cta"]["seguir"]
        txt = f"{{\\fs62}}{_escape(a)}\\N{{\\fs110\\1c{enf}}}{_escape(b)}" + (f"\\N{{\\fs44\\1c{blanco}}}{_escape(c)}" if c else "")
        ev.append(f"Dialogue: 2,{ass_t(cta['t0'])},{ass_t(clip['dur'] + 0.5)},CTA,,0,0,0,,"
                  f"{{{cta_pos}\\fad(150,0)\\fscx60\\fscy60\\t(0,200,\\fscx106\\fscy106)\\t(200,320,\\fscx100\\fscy100)}}{txt}")
    elif cta.get("palabra") and cta.get("dur"):
        a, b, c = CTA_TEXTOS.get(red, CTA_TEXTOS["general"])
        p = cta["palabra"]
        linea2 = b.replace("{P}", p)
        grande = "{\\fs128\\1c" + enf + "}" if "{P}" in b else "{\\fs72}"
        txt = f"{{\\fs62}}{a}\\N{grande}{_escape(linea2)}" + (f"\\N{{\\fs44\\1c{blanco}}}{_escape(c)}" if c else "")
        t0 = cta["t0"]
        ev.append(f"Dialogue: 2,{ass_t(t0)},{ass_t(clip['dur'] + 0.5)},CTA,,0,0,0,,"
                  f"{{{cta_pos}\\fad(150,0)\\fscx60\\fscy60\\t(0,200,\\fscx106\\fscy106)\\t(200,320,\\fscx100\\fscy100)}}{txt}")
    Path(ruta).write_text(head + "\n".join(ev) + "\n", encoding="utf-8")
    return ruta
