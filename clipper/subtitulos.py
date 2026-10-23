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
        ev.append(f"Dialogue: 1,{ass_t(g['t0'])},{ass_t(g['t0'] + g['dur'])},Gancho,,0,0,0,,"
                  f"{{\\fad(150,250)\\fscx70\\fscy70\\t(0,180,\\fscx104\\fscy104)\\t(180,280,\\fscx100\\fscy100)}}{_escape(g['texto'].upper())}")
    if cta.get("modo") == "seguir" and cta.get("dur"):
        # sin link largo ni ManyChat: el cierre invita a seguir la cuenta (no promete nada que no se entregue)
        a, b, c = marca["cta"]["seguir"]
        txt = f"{{\\fs62}}{_escape(a)}\\N{{\\fs110\\1c{enf}}}{_escape(b)}" + (f"\\N{{\\fs44\\1c{blanco}}}{_escape(c)}" if c else "")
        ev.append(f"Dialogue: 2,{ass_t(cta['t0'])},{ass_t(clip['dur'] + 0.5)},CTA,,0,0,0,,"
                  f"{{\\fad(150,0)\\fscx60\\fscy60\\t(0,200,\\fscx106\\fscy106)\\t(200,320,\\fscx100\\fscy100)}}{txt}")
    elif cta.get("palabra") and cta.get("dur"):
        a, b, c = CTA_TEXTOS.get(red, CTA_TEXTOS["general"])
        p = cta["palabra"]
        linea2 = b.replace("{P}", p)
        grande = "{\\fs128\\1c" + enf + "}" if "{P}" in b else "{\\fs72}"
        txt = f"{{\\fs62}}{a}\\N{grande}{_escape(linea2)}" + (f"\\N{{\\fs44\\1c{blanco}}}{_escape(c)}" if c else "")
        t0 = cta["t0"]
        ev.append(f"Dialogue: 2,{ass_t(t0)},{ass_t(clip['dur'] + 0.5)},CTA,,0,0,0,,"
                  f"{{\\fad(150,0)\\fscx60\\fscy60\\t(0,200,\\fscx106\\fscy106)\\t(200,320,\\fscx100\\fscy100)}}{txt}")
    Path(ruta).write_text(head + "\n".join(ev) + "\n", encoding="utf-8")
    return ruta
