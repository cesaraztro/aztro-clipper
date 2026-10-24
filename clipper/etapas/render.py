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
        k += f"+{amt:.3f}*gte(on,{f0})*(1-pow(2,-10*(on-{f0})/6))"
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
        ks = cam["x_keys"]
        x_expr = str(ks[-1][1])
        for (t0, x0), (t1, x1) in reversed(list(zip(ks, ks[1:]))):
            x_expr = f"if(lt(t\\,{t1}),{x0}+({x1}-{x0})*(t-{t0})/{max(t1 - t0, 0.01)},{x_expr})"
        x_expr = f"if(lt(t\\,{ks[0][0]}),{ks[0][1]},{x_expr})"
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
    vf.append("format=yuv420p")
    vfc.append(f"{base}{','.join(vf)}[vout]")
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
            if forzar or not seg.exists():
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
                f = broll_mod.conseguir(ep.marca, bro["buscar"], bro["dur"], usados)
            except Exception as e:  # sin internet o sin llave: el clip sale igual, sin ese B-roll
                print(f"  aviso: B-roll '{bro['buscar']}' no disponible ({type(e).__name__})")
                f = None
            bro["archivo"] = str(f) if f else None
        config.escribir(cp, clip)
        salidas = [_final(ep, clip, cdir, lista, red) for red in redes]
        tam = salidas[0].stat().st_size / 1e6
        print(f"  clip {clip['id']}: {clip['dur']:.1f}s · {len(trabajos)}/{len(archivos)} tramos nuevos · "
              f"{len(salidas)} versiones · {tam:.0f} MB · {time.time() - t0:.0f}s")
