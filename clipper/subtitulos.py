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


def _degradado(colores, n):
    """n colores repartidos sobre el degradado lineal entre 'colores' (con uno solo, n veces el mismo)."""
    if len(colores) == 1:
        return colores[:1]
    rgb = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in colores]
    out = []
    for k in range(n):
        x = k / (n - 1) * (len(rgb) - 1)
        i = min(int(x), len(rgb) - 2)
        f = x - i
        out.append("#" + "".join(f"{round(a + (b - a) * f):02X}" for a, b in zip(rgb[i], rgb[i + 1])))
    return out


def _escape(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def caras_en(clip, t0, t1):
    """Franjas verticales (px del video final) donde hay una cabeza entre t0 y t1; el B-roll a pantalla completa las tapa."""
    if clip.get("caras_t"):  # mapa exacto de caras por tramo (fuente armada aparte, p. ej. pantalla dividida)
        return [c for a, b, _, bandas in clip["caras_t"] if a < t1 and b > t0 for c in bandas]
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


def y_libre(clip, t0, t1, alto, opciones, ocupado=()):
    """Primer borde superior de 'opciones' cuya caja [y, y+alto] no toca ninguna cara ni otro texto ya puesto
    (ocupado: [(t0, t1, y0, y1)]); si todas chocan, la que menos."""
    caras = caras_en(clip, t0, t1) + [[a, b] for x, y, a, b in ocupado if x < t1 and y > t0]
    choque = lambda y: sum(max(0, min(y + alto, c1) - max(y, c0)) for c0, c1 in caras)
    return min(opciones, key=lambda y: (choque(y), opciones.index(y)))


CTA_TEXTOS = {
    "general": ("Comenta", "{P}", "y te mando el video completo"),
    "tiktok": ("Escríbeme", "{P}", "por DM y te mando el video completo"),
    "youtube": ("Video completo", "en la descripción", ""),
}


def emoji_pos(clip, e, marca):
    """(x, y, tam) del centro del emoji, o None si no hay lugar libre (lo calcula escribir())."""
    return (clip.get("_pos") or {}).get("emojis", {}).get(round(e["t0"], 3))


def firmas_ubicadas(clip, marca):
    """[(a0, a1, firma, y)]: cada rótulo abajo a la izquierda del panel de su dueño (quien va arriba en la
    pantalla dividida: justo sobre la línea; si no, abajo) y fuera de los B-roll (se recorta o se pasa después)."""
    mo = marca.get("motion", {})
    y_abajo = mo.get("firma_y", H - 230)
    brs = sorted((b["t0"] - 0.15, b["t0"] + b["dur"] + 0.15) for b in clip.get("broll", []) if b.get("archivo"))
    out = []
    for a0, a1, fi in firmas_de(clip, marca):
        d = a1 - a0
        for x, z in brs:
            if x < a1 and a0 < z:
                if x - a0 >= 1.6:
                    a1 = x
                else:
                    a0, a1 = z, z + d
        if a1 > clip.get("dur", 999) - 3.6:   # no compite con el cierre
            continue
        seg = next((c for c in clip.get("caras_t", []) if c[0] <= a0 + 0.3 < c[1]), None)
        lay = seg[2] if seg else ""
        if seg and seg[1] - 0.05 < a1 and seg[1] - 0.05 - a0 >= 1.6:   # se va antes de que cambie el plano
            a1 = seg[1] - 0.05
        y = 925 if (lay == "split" and fi.get("arriba")) else y_abajo
        out.append((round(a0, 3), round(a1, 3), fi, y))
    return out


def firmas_de(clip, marca):
    """[(t0, t1, firma)]: el rótulo de cada persona la primera vez que habla, mientras siga hablando (máx. firma_dur).
    marca["firmas"] es una lista en el orden de las voces de diarize (pieza["hablante"])."""
    firmas = marca.get("firmas") or []
    mo = marca.get("motion", {})
    out, vistos, piezas = [], set(), clip.get("piezas", [])
    clave = "voz" if marca.get("firmas_por") == "voz" else "hablante"  # "voz": índice de diarize, no la cara
    for k, pz in enumerate(piezas):
        h = pz.get(clave)
        if h is None or h in vistos or not (0 <= h < len(firmas)) or not firmas[h].get("nombre"):
            continue
        vistos.add(h)
        fin = pz["o1"]
        for q in piezas[k + 1:]:
            if q.get(clave) != h:
                break
            fin = q["o1"]
        a0 = pz["o0"] + (mo.get("firma_desde", 0.6) if k == 0 else 0.25)
        a1 = min(a0 + mo.get("firma_dur", 3.2), fin - 0.1)
        if a1 - a0 >= 1.2:
            out.append((round(a0, 3), round(a1, 3), firmas[h]))
    return out


def escribir(clip, marca, ruta, red="general"):
    st, col, fu, gc = marca["subtitulos"], marca["colores"], marca["fuentes"], marca["gancho"]
    caja = ass_color(col["caja"], st.get("caja_alfa", 40))
    blanco, enf = ass_color(col["texto"]), ass_color(col["enfasis"])
    oscuro = ass_color(col["caja"])
    g_caja, g_txt = ass_color(col.get("gancho_caja", col["enfasis"])), ass_color(col.get("gancho_texto", col["caja"]))
    b_caja, b_txt = ass_color(col.get("boton", col["enfasis"])), ass_color(col.get("boton_texto", col["caja"]))
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{fu['subtitulos']},{st['tam']},{blanco},{blanco},{caja},{caja},0,0,0,0,100,100,0,0,3,{st.get('relleno', 16)},0,2,80,80,{H - st['y']},1
Style: Gancho,{fu['titulo']},{gc['tam']},{g_txt},{g_txt},{g_caja},{g_caja},0,0,0,0,100,100,0,0,3,22,0,8,90,90,{gc['y']},1
Style: CTA,{fu['titulo']},64,{blanco},{blanco},{caja},{caja},0,0,0,0,100,100,0,0,3,26,0,2,90,90,{H - 1260},1
Style: Tarjeta,{fu['titulo']},124,{oscuro},{oscuro},{enf},{enf},0,0,0,0,100,100,0,0,3,24,0,5,60,60,0,1
Style: Firma,{fu['titulo']},62,{blanco},{blanco},{caja},{caja},0,0,0,0,100,100,0,0,3,18,0,1,70,70,{H - 1640},1
Style: Chip,{fu['titulo']},72,{oscuro},{oscuro},{enf},{enf},0,0,0,0,100,100,2,0,3,16,0,7,0,0,0,1
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
    # franja de los subtítulos (casi siempre hay alguien hablando): ningún otro texto se pone encima
    ocupado = [(0, clip.get("dur", 999) + 1, st["y"] - st["tam"] * 1.25 - st.get("relleno", 16) - 10, st["y"] + st.get("relleno", 16) + 10)]
    pos = clip["_pos"] = {}
    for a0, a1, fi, y_f in firmas_ubicadas(clip, marca):   # rótulo (+ logo encima si lo lleva)
        ocupado.append((a0, a1, y_f - (215 if fi.get("logo") else 150), y_f))
    g = clip.get("gancho_overlay")
    if g and g.get("texto"):
        # nunca sobre la cara: arriba si la cabeza está abajo, si no a media pantalla (sobre el pecho)
        lineas = 1 + len(g["texto"]) * gc["tam"] * 0.62 // (W - 180)
        alto_g = int(lineas * gc["tam"] * 1.3 + 50)
        y = y_libre(clip, g["t0"], g["t0"] + g["dur"], alto_g, gc.get("opciones") or [gc["y"], 700, 960], ocupado)
        ocupado.append((g["t0"], g["t0"] + g["dur"], y, y + alto_g))
        # la caja entra de golpe y las palabras se encienden una por una (se lee al ritmo de la voz)
        paso = min(110, int(900 / max(1, len(g["texto"].split()))))
        letras = " ".join(f"{{\\1a&HFF&\\t({120 + k * paso},{200 + k * paso},\\1a&H00&)}}{_escape(p)}"
                          for k, p in enumerate(g["texto"].upper().split()))
        ev.append(f"Dialogue: 1,{ass_t(g['t0'])},{ass_t(g['t0'] + g['dur'])},Gancho,,0,0,0,,"
                  f"{{\\an8\\pos({W // 2},{y})\\fad(120,250)\\fscx70\\fscy70\\t(0,180,\\fscx104\\fscy104)"
                  f"\\t(180,280,\\fscx100\\fscy100)}}{letras}")
    mo = marca.get("motion", {})
    # barra de progreso arriba: se llena durante todo el clip (retención: "ya casi acaba")
    if mo.get("barra", True) and clip.get("dur"):
        ms = int(clip["dur"] * 1000)
        acento = ass_color(col.get("acento", col["enfasis"]))
        # con varios colores la barra es el degradado de la marca: franjas angostas bajo el mismo \clip que avanza
        tramos = _degradado(col.get("barra") or [col["enfasis"]], 36)
        ancho = W / len(tramos)
        for k, c in enumerate(tramos):
            x0, x1 = round(k * ancho), round((k + 1) * ancho)
            ev.append(f"Dialogue: 3,{ass_t(0)},{ass_t(clip['dur'] + 0.5)},Grafico,,0,0,0,,"
                      f"{{\\pos(0,0)\\1c{ass_color(c)}\\clip(0,0,0,14)\\t(0,{ms},\\clip(0,0,{W},14))\\p1}}"
                      f"m {x0} 0 l {x1} 0 {x1} 14 {x0} 14{{\\p0}}")
        ev.append(f"Dialogue: 2,{ass_t(0)},{ass_t(clip['dur'] + 0.5)},Grafico,,0,0,0,,"
                  f"{{\\pos(0,0)\\1c{acento}\\1a&HB0&\\p1}}m 0 0 l {W} 0 {W} 14 0 14{{\\p0}}")
    # palabras clave: entran con rebote y salen rápido (motion graphic sobre la palabra que se está diciendo)
    for tj in clip.get("tarjetas", []):
        t0, t1 = tj["t0"], tj["t0"] + tj["dur"]
        y0 = mo.get("tarjeta_y", 1180)
        centros = mo.get("tarjeta_centros") or [y0, 975, 655]
        y = y_libre(clip, t0, t1, 190, [c - 95 for c in centros], ocupado) + 95  # \pos es el centro de la tarjeta
        fs_t = min(124, int(124 * (W - 140) / (len(tj["texto"]) * 124 * 0.68 + 48)))
        ancho_t = len(tj["texto"]) * fs_t * 0.68 + 48
        ocupado.append((t0, t1, y - 95, y + 95))
        pos.setdefault("tarjetas", []).append((t0, t1, y, ancho_t))
        ev.append(f"Dialogue: 4,{ass_t(t0)},{ass_t(t1)},Tarjeta,,0,0,0,,"
                  f"{{\\pos({W // 2},{y})\\fs{fs_t}\\frz-3\\fad(60,140)\\fscx30\\fscy30\\t(0,140,\\fscx115\\fscy115)"
                  f"\\t(140,260,\\fscx100\\fscy100\\frz0)}}{_escape(tj['texto'])}")
    # emojis: a un lado, en la primera altura que no toque cara ni otro texto; si no hay, no salen
    tam_e = mo.get("emoji_tam", 230)
    pos["emojis"] = {}
    for e in clip.get("emojis", []):
        t0, t1 = e["t0"], e["t0"] + e["dur"]
        # el emoji termina con su plano: si el encuadre cambia a media animación, se corta ahí (o no sale si queda < 0.6 s)
        cambio = min((x[0] for x in clip.get("caras_t", []) if t0 + 0.05 < x[0] < t1), default=None)
        if cambio is not None:
            if cambio - t0 < 0.6:
                continue
            e["dur"] = round(cambio - t0, 3)
            t1 = cambio
        caras =caras_en(clip, t0, t1) + [[a, b] for x, y, a, b in ocupado if x < t1 and y > t0]
        for yc in mo.get("emoji_ys") or [mo.get("emoji_y", 760)]:
            y0, y1 = yc - tam_e / 2 - 30 * e["dur"], yc + tam_e / 2
            if not any(min(y1, b) > max(y0, a) for a, b in caras):
                pos["emojis"][round(t0, 3)] = (mo.get("emoji_x", 850), yc, tam_e)
                ocupado.append((t0, t1, y0, y1))
                break
    # B-roll en panel: marco de color de la marca que se dibuja alrededor y la palabra en una etiqueta lima
    acento_c = ass_color(col.get("acento", col["enfasis"]))
    for b in clip.get("broll", []):
        if not (b.get("archivo") and b.get("panel")):
            continue
        t0, t1 = b["t0"], b["t0"] + b["dur"]
        y0 = b.get("panel_y", 0 if b["panel"] == "arriba" else 963)
        y1 = y0 + b.get("panel_h", 957)
        ms = int(b["dur"] * 1000)
        # marco violeta de 8 px que se "traza" en 0.3 s (los cuatro lados crecen desde la esquina)
        for x_a, y_a, x_b, y_b in ((0, y0, W, y0 + 8), (0, y1 - 8, W, y1), (0, y0, 8, y1), (W - 8, y0, W, y1)):
            ev.append(f"Dialogue: 3,{ass_t(t0 + 0.22)},{ass_t(t1 - 0.2)},Grafico,,0,0,0,,"
                      f"{{\\pos(0,0)\\1c{acento_c}\\clip({x_a},{y_a},{x_a},{y_a})\\t(0,300,\\clip({x_a},{y_a},{x_b},{y_b}))"
                      f"\\fad(0,120)\\p1}}m {x_a} {y_a} l {x_b} {y_a} {x_b} {y_b} {x_a} {y_b}{{\\p0}}")
        pal = (b.get("etiqueta") or "").strip().upper()
        if pal:
            yc = max(y0 + 40, 1120) if b["panel"] == "abajo" else 200   # bajo los subtítulos / bajo la barra, lejos de la interfaz
            ev.append(f"Dialogue: 5,{ass_t(t0 + 0.25)},{ass_t(t1 - 0.2)},Chip,,0,0,0,,"
                      f"{{\\pos(60,{yc})\\fad(0,120)\\frz2\\fscx40\\fscy40\\t(0,160,\\fscx108\\fscy108\\frz0)"
                      f"\\t(160,260,\\fscx100\\fscy100)\\t({max(300, ms - 400)},{ms},\\fscx104\\fscy104)}}{_escape(pal)}")
    # firmas por persona (podcast): el rótulo de cada quien sale la primera vez que habla en el clip
    for a0, a1, fi, y in firmas_ubicadas(clip, marca):
        rol = f"\\N{{\\fs40\\b0\\1c{enf}}}{_escape(fi['rol'])}" if fi.get("rol") else ""
        ev.append(f"Dialogue: 4,{ass_t(a0)},{ass_t(a1)},Firma,,0,0,0,,"
                  f"{{\\an1\\move(-420,{y},70,{y},0,260)\\fad(0,200)}}{_escape(fi['nombre'])}{rol}")
    # firma: nombre y rol al inicio, se desliza desde la izquierda
    fi = marca.get("firma") or {}
    if fi.get("nombre") and not marca.get("firmas"):
        a0 = mo.get("firma_desde", 0.6)
        a1 = min(a0 + mo.get("firma_dur", 3.2), clip.get("dur", 10) * 0.4)
        y = mo.get("firma_y", H - 230)
        rol = f"\\N{{\\fs40\\b0\\1c{enf}}}{_escape(fi['rol'])}" if fi.get("rol") else ""
        ev.append(f"Dialogue: 4,{ass_t(a0)},{ass_t(a1)},Firma,,0,0,0,,"
                  f"{{\\an1\\move(-420,{y},70,{y},0,260)\\fad(0,200)}}{_escape(fi['nombre'])}{rol}")
    cta_pos = ""
    if cta.get("dur"):  # el bloque del CTA (~310 px) termina en 1260 o, si ahí hay cara, más arriba/abajo
        alto = 400 if cta.get("linea") else 310  # el CTA con promesa es una escalera de tres renglones
        base = y_libre(clip, cta["t0"], clip.get("dur", cta["t0"] + cta["dur"]), alto,
                       [b - alto for b in (marca.get("cta_bases") or [1260, 950, 690])], ocupado) + alto
        pos["cta"] = (base - alto, base)
        cta_pos = f"\\an2\\pos({W // 2},{base})"
    if cta.get("modo") == "seguir" and cta.get("dur") and cta.get("linea"):
        # botón que se "presiona", la promesa de este clip y la cuenta de esa red, en escalera
        cfg = marca["cta"]
        boton = cfg.get("seguir_youtube", "Suscríbete") if red == "youtube" else cfg["seguir"][0]
        cuenta = (cfg.get("cuentas") or {}).get(red, "")
        base = int(cta_pos.split(",")[1].rstrip(")")) - (0 if cuenta else 60)
        t0, t1 = ass_t(cta["t0"]), ass_t(clip["dur"] + 0.5)
        ev.append(f"Dialogue: 2,{t0},{t1},CTA,,0,0,0,,{{\\an2\\pos({W // 2},{base - 185})\\fs150\\1c{b_txt}\\3c{b_caja}"
                  f"\\fad(120,0)\\fscx60\\fscy60\\t(0,200,\\fscx108\\fscy108)\\t(200,320,\\fscx100\\fscy100)"
                  f"\\t(850,930,\\fscx88\\fscy88)\\t(930,1080,\\fscx100\\fscy100)}}{_escape(boton.upper())}")
        ev.append(f"Dialogue: 2,{t0},{t1},CTA,,0,0,0,,{{\\an2\\pos({W // 2},{base - 80})\\fs70\\alpha&HFF&"
                  f"\\t(250,420,\\alpha&H00&)}}{_escape(cta['linea'])}")
        if cuenta:
            ev.append(f"Dialogue: 2,{t0},{t1},CTA,,0,0,0,,{{\\an2\\pos({W // 2},{base})\\fs50\\1c{enf}\\alpha&HFF&"
                      f"\\t(450,600,\\alpha&H00&)}}{_escape(cuenta)}")
    elif cta.get("modo") == "seguir" and cta.get("dur"):
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
