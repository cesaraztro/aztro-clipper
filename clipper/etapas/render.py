"""Etapa 9: render.

1) Cada tramo se renderiza desde el archivo ORIGINAL (no de un proxy): recorte del hablante, HDR→SDR, velocidad,
   punch-ins y escala a 1080x1920. Los tramos corren en paralelo y se guardan en caché por contenido.
2) Una pasada final por red social une los tramos, aplica color de marca, subtítulos, gancho, CTA y el audio
   masterizado (voz limpia, música que baja cuando hablas, volumen estándar de redes).
Salida: H.264 SDR bt709 a ~8 Mbps (lo que Metricool publica en automático, <100 MB por clip).
"""
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import broll as broll_mod, config, media, subtitulos
from ..config import FPS, H, W
from .ingest import resolver

REDES_VARIANTE = {"general": ["instagram", "facebook"], "tiktok": ["tiktok"], "youtube": ["youtube"]}


def _perspectiva(pz):
    """Punch-ins animados (zoom de golpe con salida exponencial) sobre la cara, como en el motor v4."""
    if not pz.get("punch"):
        return ""
    cam = pz["camara"]
    k = "(1"
    for rel, amt in pz["punch"]:
        f0 = round(rel * FPS)
        # max(0,…): antes del punch el exponente crecería sin límite (inf × 0 = NaN) en tramos largos
        k += f"+{amt:.3f}*gte(on,{f0})*(1-pow(2,-10*max(0,on-{f0})/6))"
    k += ")"
    fx, fy = cam["fx"], cam["fy"]
    L, T = f"({fx:.4f}*W-{fx:.4f}*W/{k})", f"({fy:.4f}*H-{fy:.4f}*H/{k})"
    ancho, alto = f"(W/{k})", f"(H/{k})"
    return (f",perspective=x0='{L}':y0='{T}':x1='{L}+{ancho}':y1='{T}':x2='{L}':y2='{T}+{alto}':"
            f"x3='{L}+{ancho}':y3='{T}+{alto}':interpolation=cubic:eval=frame")


def _cmd_tramo(ep, pz, vel, salida):
    f, local = resolver(ep.meta, pz["s0"])
    if f is None:
        raise SystemExit(f"No hay cámara grabando en t={pz['s0']:.2f}s (revisa la sincronía).")
    info, cam = f["info"], pz["camara"]
    dur = pz["s1"] - pz["s0"]
    tm = media.tonemap_para(info)
    x_expr = str(cam["x"])
    if cam.get("x_keys"):  # paneo suave que sigue a la persona (interpolación lineal entre puntos)
        # suma de tramos sin anidar: un if() por punto anidaba cientos de niveles en tramos largos y ffmpeg lo rechaza
        ks = cam["x_keys"]
        if len(ks) > 60:  # el parser de ffmpeg no acepta más de ~80 términos: tramos largos usan menos puntos
            paso = (len(ks) - 1) / 59
            ks = [ks[round(i * paso)] for i in range(60)]
        partes =[f"lt(t,{ks[0][0]})*{ks[0][1]}", f"gte(t,{ks[-1][0]})*{ks[-1][1]}"]
        partes += [f"gte(t,{t0})*lt(t,{t1})*({x0}+({x1}-{x0})*(t-{t0})/{max(t1 - t0, 0.01)})"
                   for (t0, x0), (t1, x1) in zip(ks, ks[1:])]
        x_expr = "+".join(partes)
    vf = (f"crop={cam['w']}:{cam['h']}:'{x_expr}':{cam['y']}" + (f",{tm}" if tm else "") +
          f",format=yuv420p,setpts=(PTS-STARTPTS)/{vel},fps={FPS}" + _perspectiva(pz) +
          f",scale={W}:{H}:flags=lanczos,setsar=1")
    if pz.get("modo") == "GENERAL":  # nadie en cuadro: video completo al centro con fondo desenfocado
        vf = ((f"{tm}," if tm else "") + f"format=yuv420p,setpts=(PTS-STARTPTS)/{vel},fps={FPS},split[a][b];"
              f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2[bg];"
              f"[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    cmd = [media.ffmpeg_bin(), "-y", "-v", "error", *media.hwaccel(), "-ss", f"{local:.4f}", "-t", f"{dur + 0.2:.4f}",
           "-i", f["ruta"]]
    a_idx = 0
    if ep.meta.get("audio_externo"):  # audio de doble sistema: la voz sale del micrófono, no de la cámara
        cmd += ["-ss", f"{pz['s0']:.4f}", "-t", f"{dur + 0.2:.4f}", "-i", ep.meta["audio_externo"]]
        a_idx = 1
    af = (f"[{a_idx}:a]atrim=duration={dur:.4f},asetpts=PTS-STARTPTS,atempo={vel},"
          f"afade=t=in:d=0.02,afade=t=out:st={max(0, dur / vel - 0.025):.4f}:d=0.025,aresample=48000,aformat=channel_layouts=mono[a]")
    cmd += ["-filter_complex", f"[0:v]{vf}[v];{af}", "-map", "[v]", "-map", "[a]", "-frames:v", str(pz["nf"]),
            "-t", f"{pz['nf'] / FPS:.4f}", *media.encoder_h264(intermedio=True), "-pix_fmt", "yuv420p", *media.BT709,
            "-c:a", "pcm_s16le", "-ar", "48000", str(salida)]
    return cmd


IMAGEN = {".jpg", ".jpeg", ".png"}


def _eventos_sonido(clip, marca):
    """Momentos con efecto de sonido (whoosh en B-roll, pop en palabra clave, click en firma…), sin amontonarse."""
    sfx, mo = marca.get("sfx") or {}, marca.get("motion", {})
    ev = [("gancho", 0.0)] + [("broll", b["t0"]) for b in clip.get("broll", []) if b.get("archivo")]
    ev += [("tarjeta", t["t0"]) for t in clip.get("tarjetas", [])]
    if (marca.get("firma") or {}).get("nombre"):
        ev.append(("firma", mo.get("firma_desde", 0.6)))
    if clip.get("cta", {}).get("dur"):
        ev.append(("cta", clip["cta"]["t0"]))
    out, ult = [], -9.0
    for tipo, t in sorted(ev, key=lambda x: x[1]):
        cfg = sfx.get(tipo)
        f = config.recurso_marca(marca, cfg.get("archivo")) if cfg else None
        if not f or t - ult < 0.35:
            continue
        out.append((max(0.0, t - cfg.get("antes", 0)), f, cfg.get("db", -12)))
        ult = t
    return out


_FOCOS = {}


def _foco_broll(ruta):
    """(vertical, fx, fy) del B-roll: si es vertical, y el centro de la cara más grande (YuNet en 3 cuadros);
    sin cara, el tercio superior (ahí suelen estar las cabezas)."""
    if ruta in _FOCOS:
        return _FOCOS[ruta]
    import cv2
    from .reframe import modelo_yunet
    cap = cv2.VideoCapture(str(ruta))
    w, h = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 60
    caras = []
    det = None
    for f in (0.1, 0.3, 0.5):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(min(n - 1, 30 * 2.2) * f / 0.5 * 0.5))
        ok, img = cap.read()
        if not ok:
            continue
        esc = 640 / max(img.shape[:2])
        img = cv2.resize(img, None, fx=esc, fy=esc)
        if det is None:
            det = cv2.FaceDetectorYN.create(str(modelo_yunet()), "", (img.shape[1], img.shape[0]), 0.55, 0.3, 20)
        _, r = det.detect(img)
        for c in (r if r is not None else []):
            caras.append(((c[0] + c[2] / 2) / img.shape[1], (c[1] + c[3] / 2) / img.shape[0], c[2] * c[3]))
    cap.release()
    if caras:
        cx, cy, _ = max(caras, key=lambda c: c[2])
    else:
        cx, cy = 0.5, 0.33
    _FOCOS[ruta] = (h > w, cx, cy)
    return _FOCOS[ruta]


def _final(ep, clip, cdir, lista, red):
    m = ep.marca
    ass = subtitulos.escribir(clip, m, cdir / "render" / f"subs_{red}.ass", red)
    total = clip["dur"]
    entradas = ["-f", "concat", "-safe", "0", "-i", str(lista)]
    idx = 1
    musica = config.recurso_marca(m, m["audio"].get("musica"))
    i_mus = None
    if musica:
        entradas += ["-stream_loop", "-1", "-i", str(musica)]
        i_mus, idx = idx, idx + 1
    # video: base → B-roll encima (entra y sale suave, paneo lento) → color de marca → gráficos y subtítulos
    vfc, base = [], "[0:v]"
    for k, b in enumerate(b for b in clip.get("broll", []) if b.get("archivo")):
        d, t0 = b["dur"], b["t0"]
        if Path(b["archivo"]).suffix.lower() in IMAGEN:
            entradas += ["-loop", "1", "-t", f"{d + 0.2:.3f}", "-i", b["archivo"]]
        else:
            entradas += ["-t", f"{d + 0.2:.3f}", "-i", b["archivo"]]
        if b.get("panel") in ("arriba", "abajo"):
            # panel animado sobre media pantalla: entra deslizándose (lado alterno), paneo lento y sale hacia el otro lado
            ph = b.get("panel_h", 957)
            py = b.get("panel_y", 0 if b["panel"] == "arriba" else 963)
            sg = -1 if k % 2 == 0 else 1
            vertical, fx, fy = _foco_broll(b["archivo"])
            if vertical:
                # video vertical en un panel casi cuadrado: completo al centro (sin cortar cabezas) y fondo desenfocado
                vfc.append(f"[{idx}:v]trim=duration={d:.3f},setpts=PTS-STARTPTS,fps={FPS},split[bf{k}][bg{k}];"
                           f"[bg{k}]scale={W}:{ph}:force_original_aspect_ratio=increase,crop={W}:{ph},boxblur=28:2,"
                           f"eq=brightness=-0.08:saturation=0.8[bb{k}];"
                           f"[bf{k}]scale=w='trunc({ph}*1.0*(1+0.04*t/{d:.3f})*iw/ih/2)*2':h='trunc({ph}*(1+0.04*t/{d:.3f})/2)*2':eval=frame,"
                           f"eq=contrast=1.05:saturation=1.12[bv{k}];"
                           f"[bb{k}][bv{k}]overlay=x='(W-w)/2':y='(H-h)/2',format=yuva420p,setpts=PTS+{t0:.3f}/TB[br{k}]")
            else:
                # horizontal: llena el panel con el recorte anclado a la cara (o al tercio superior si no hay cara)
                vfc.append(f"[{idx}:v]trim=duration={d:.3f},setpts=PTS-STARTPTS,"
                           f"scale={int(W * 1.06)}:{int(ph * 1.06)}:force_original_aspect_ratio=increase,"
                           f"crop={W}:{ph}:x='max(0,min(iw-ow,{fx:.3f}*iw-ow/2+(iw-ow)*0.2*(t/{d:.3f}-0.5)))':"
                           f"y='max(0,min(ih-oh,{fy:.3f}*ih-0.42*oh))',eq=contrast=1.05:saturation=1.12,"
                           f"fps={FPS},format=yuva420p,setpts=PTS+{t0:.3f}/TB[br{k}]")
            u = f"(t-{t0:.3f})"
            x = (f"if(lt({u},0.24),{sg * W}*pow(1-{u}/0.24,3),"
                 f"if(gt({u},{d - 0.2:.3f}),{-sg * W}*pow(({u}-{d - 0.2:.3f})/0.2,3),0))")
            vfc.append(f"{base}[br{k}]overlay=x='{x}':y={py}:eof_action=pass[v{k}]")
        else:
            vfc.append(f"[{idx}:v]trim=duration={d:.3f},setpts=PTS-STARTPTS,"
                       f"scale={int(W * 1.1)}:{int(H * 1.1)}:force_original_aspect_ratio=increase,"
                       f"crop={W}:{H}:x='(iw-ow)*t/{d:.3f}':y='(ih-oh)/2',fps={FPS},format=yuva420p,"
                       f"fade=t=in:st=0:d=0.12:alpha=1,fade=t=out:st={max(0, d - 0.15):.3f}:d=0.15:alpha=1,"
                       f"setpts=PTS+{t0:.3f}/TB[br{k}]")
            vfc.append(f"{base}[br{k}]overlay=0:0:eof_action=pass[v{k}]")
        base, idx = f"[v{k}]", idx + 1
    vf = []
    lut = config.recurso_marca(m, m["color"].get("lut"))
    if lut:
        vf.append(f"lut3d=file={media.ruta_filtro(lut)}")
    if m["color"].get("vineta"):
        vf.append(f"vignette=angle={0.2 + 0.4 * m['color']['vineta']:.3f}")
    vf.append(f"subtitles={media.ruta_filtro(ass)}:fontsdir={media.ruta_filtro(config.FUENTES)}")
    lg, cta = m.get("logo") or {}, clip.get("cta") or {}
    logo = config.recurso_marca(m, lg.get("archivo"))
    vfc.append(f"{base}{','.join(vf)}[subs]")
    cur = "[subs]"
    # firmas con logo (podcast): el logo de la marca entra deslizándose junto al rótulo, justo encima de él
    for k, (a0, a1, fi, y_f) in enumerate(subtitulos.firmas_ubicadas(clip, m)):
        if not (fi.get("logo") and logo):
            continue
        ancho = fi.get("logo_ancho", 360)
        y_logo = y_f - 140 - round(ancho * 140 / 1297) - 20
        entradas += ["-loop", "1", "-t", f"{total + 0.5:.3f}", "-i", str(logo)]
        vfc.append(f"[{idx}:v]scale={ancho}:-1,format=rgba,fade=t=in:st={a0:.3f}:d=0.2:alpha=1,"
                   f"fade=t=out:st={max(a0, a1 - 0.2):.3f}:d=0.2:alpha=1[fl{k}]")
        x = f"if(lt(t,{a0 + 0.26:.3f}),-440+510*(t-{a0:.3f})/0.26,70)"
        vfc.append(f"{cur}[fl{k}]overlay=x='{x}':y={y_logo}:enable='between(t,{a0:.3f},{a1:.3f})':shortest=1[fo{k}]")
        cur, idx = f"[fo{k}]", idx + 1
    # emojis (assets/emoji/<codepoint>.png de la marca): saltan con rebote a un lado, sin tapar caras ni subtítulos
    em_dir = config.recurso_marca(m, "assets/emoji")
    for k, e in enumerate(clip.get("emojis", [])):
        nombre = "-".join(f"{ord(ch):x}" for ch in e["emoji"] if ord(ch) != 0xFE0F) + ".png"
        png = Path(em_dir) / nombre if em_dir else None
        if not png or not png.exists():
            continue
        a0, d = e["t0"], e["dur"]
        a1 = a0 + d
        ubic = subtitulos.emoji_pos(clip, e, m)
        if not ubic:
            continue
        ex, ey, tam = ubic
        z = f"if(lt(t-{a0:.3f},0.16),0.4+0.75*(t-{a0:.3f})/0.16,if(lt(t-{a0:.3f},0.26),1.15-0.15*(t-{a0 + 0.16:.3f})/0.1,1))"
        entradas += ["-loop", "1", "-t", f"{total + 0.5:.3f}", "-i", str(png)]
        vfc.append(f"[{idx}:v]format=rgba,scale=w='trunc({tam}*{z}/2)*2':h='trunc({tam}*{z}/2)*2':eval=frame,"
                   f"fade=t=out:st={a1 - 0.18:.3f}:d=0.18:alpha=1[em{k}]")
        vfc.append(f"{cur}[em{k}]overlay=x='{ex}-w/2':y='{ey}-h/2-30*(t-{a0:.3f})':"
                   f"enable='between(t,{a0:.3f},{a1:.3f})':shortest=1[eo{k}]")
        cur, idx = f"[eo{k}]", idx + 1
    if logo and cta.get("dur"):
        # logo de la marca durante el cierre, centrado arriba (sobre la cabeza y debajo de la interfaz de la red)
        entradas += ["-loop", "1", "-t", f"{total + 0.5:.3f}", "-i", str(logo)]
        t0 = cta["t0"]
        vfc.append(f"[{idx}:v]scale={lg.get('ancho', 520)}:-1,format=rgba,"
                   f"fade=t=in:st={t0:.3f}:d=0.25:alpha=1[logo]")
        vfc.append(f"{cur}[logo]overlay=(W-w)/2:{lg.get('y', 200)}:enable='gte(t,{t0:.3f})':shortest=1,format=yuv420p[vout]")
        idx += 1
    else:
        vfc.append(f"{cur}format=yuv420p[vout]")
    # audio: voz pulida + música que baja cuando hablas + efectos de sonido + volumen estándar de redes
    af = [f"[0:a]highpass=f=90,afftdn=nr=10:nf=-42:tn=1,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120:makeup=1.5,"
          f"aresample=48000,aformat=channel_layouts=stereo,asplit=2[voz][llave]"]
    mezcla = ["[voz]"]
    if i_mus is not None:
        af.append(f"[{i_mus}:a]atrim=duration={total:.3f},aresample=48000,aformat=channel_layouts=stereo,"
                  f"equalizer=f=2500:t=o:w=1.3:g=-4,volume={m['audio']['musica_volumen']},"
                  f"afade=t=in:d=0.6,afade=t=out:st={max(0, total - 1.2):.3f}:d=1.2[mus]")
        af.append("[mus][llave]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=250[mduck]")
        mezcla.append("[mduck]")
    else:
        af.append("[llave]anullsink")
    for k, (t, f, db) in enumerate(_eventos_sonido(clip, m)):
        entradas += ["-i", str(f)]
        af.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={db}dB,"
                  f"adelay={int(t * 1000)}:all=1[s{k}]")
        mezcla.append(f"[s{k}]")
        idx += 1
    af.append("".join(mezcla) + f"amix=inputs={len(mezcla)}:normalize=0:duration=first,"
              f"loudnorm=I={m['audio']['lufs']}:TP=-1.5:LRA=9,aresample=48000,aformat=channel_layouts=stereo[aout]")
    fc = ";".join(vfc + af)
    (cdir / "render" / f"filtro_{red}.txt").write_text(fc, encoding="utf-8")
    salida = cdir / f"video_{red}.mp4"
    media.correr([media.ffmpeg_bin(), "-y", "-v", "error", *entradas, "-filter_complex", fc,
                  "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}", "-r", str(FPS),
                  *media.encoder_h264("8M"), "-pix_fmt", "yuv420p", *media.BT709,
                  "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(salida)])
    return salida


def correr(ep, solo=None, forzar=False, redes=("general", "tiktok", "youtube")):
    for cp in ep.clips():
        clip = config.leer(cp)
        if solo and clip["id"] not in solo:
            continue
        if not all(pz.get("camara") for pz in clip["piezas"]):
            raise SystemExit(f"Clip {clip['id']}: falta el encuadre. Corre: clipper reframe {ep.meta['slug']}")
        t0 = time.time()
        cdir = cp.parent
        rdir = cdir / "render"
        rdir.mkdir(exist_ok=True)
        trabajos, archivos = [], []
        for k, pz in enumerate(clip["piezas"]):
            huella = hashlib.sha1(json.dumps([pz, clip["velocidad"], ep.meta["fuentes"][0]["ruta"]],
                                             sort_keys=True).encode()).hexdigest()[:10]
            seg = rdir / f"tramo_{k:03d}_{huella}.mov"
            archivos.append(seg)
            if forzar or not seg.exists() or seg.stat().st_size == 0:  # un render fallido deja el archivo vacío
                trabajos.append(_cmd_tramo(ep, pz, clip["velocidad"], seg))
        vigentes = {a.name for a in archivos}
        for viejo in rdir.glob("tramo_*.mov"):
            if viejo.name not in vigentes:
                viejo.unlink()
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(media.correr, trabajos))
        lista = rdir / "lista.txt"
        lista.write_text("".join(f"file '{a.as_posix()}'\n" for a in archivos), encoding="utf-8")
        usados = set()
        for bro in clip.get("broll", []):
            try:
                f = broll_mod.conseguir(ep.marca, bro["buscar"], bro["dur"], usados, bro.get("pexels_id"))
            except Exception as e:  # sin internet o sin llave: el clip sale igual, sin ese B-roll
                print(f"  aviso: B-roll '{bro['buscar']}' no disponible ({type(e).__name__})")
                f = None
            bro["archivo"] = str(f) if f else None
        config.escribir(cp, clip)
        salidas = [_final(ep, clip, cdir, lista, red) for red in redes]
        tam = salidas[0].stat().st_size / 1e6
        print(f"  clip {clip['id']}: {clip['dur']:.1f}s · {len(trabajos)}/{len(archivos)} tramos nuevos · "
              f"{len(salidas)} versiones · {tam:.0f} MB · {time.time() - t0:.0f}s")
