"""Etapa 1: registra las fuentes, arma la línea de tiempo maestra y extrae el audio de análisis.

Modo A: un video largo ya editado.
Modo B: varios archivos de cámara (+ audio externo opcional, que se sincroniza).
"""
import datetime
from pathlib import Path

from .. import config, media
from . import sync as sync_mod

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".mxf"}


def expandir(rutas):
    out = []
    for r in rutas:
        p = Path(r).expanduser().resolve()
        if p.is_dir():
            out += sorted(x for x in p.iterdir() if x.suffix.lower() in VIDEO_EXT and not x.name.startswith("."))
        elif p.exists():
            out.append(p)
        else:
            raise SystemExit(f"No existe: {p}")
    if not out:
        raise SystemExit("No encontré videos en lo que me pasaste.")
    return out


def correr(videos, marca, slug=None, audio=None, guion=None, hablantes=None, url_largo=None, palabra=None):
    config.cargar_marca(marca)  # valida que exista
    videos = expandir(videos)
    slug = config.slugify(slug or videos[0].stem)
    ep_dir = config.episodios_dir() / f"{datetime.date.today():%Y-%m-%d}_{slug}"
    ep_dir.mkdir(parents=True, exist_ok=True)

    fuentes = []
    for v in videos:
        info = media.sondear(v)
        if not info["w"]:
            raise SystemExit(f"{v.name} no tiene video legible.")
        fuentes.append({"ruta": str(v), "info": info})
        print(f"  fuente {v.name}: {info['w']}x{info['h']} · {info['dur'] / 60:.1f} min · HDR={info['hdr'] or 'no'}")

    if audio:
        audio = Path(audio).expanduser().resolve()
        print("  sincronizando el audio externo con cada archivo de cámara…")
        res = sync_mod.sincronizar(audio, [f["ruta"] for f in fuentes], ep_dir / "01_sync")
        for f, r in zip(fuentes, res):
            f["offset"], f["deriva_ppm"], f["sync_confianza"] = r["offset"], r["deriva_ppm"], r["confianza"]
            print(f"    {Path(f['ruta']).name}: empieza en {r['offset']:.3f}s del audio · confianza {r['confianza']} · deriva {r['deriva_ppm']} ppm")
        config.escribir(ep_dir / "01_sync" / "sync.json", res)
        dur_total = media.sondear(audio)["dur"]
    else:
        t = 0.0
        for f in fuentes:
            f["offset"] = round(t, 4)
            t += f["info"]["dur"]
        dur_total = t

    meta = {
        "version": 1, "marca": marca, "slug": slug, "creado": datetime.datetime.now().isoformat(timespec="seconds"),
        "modo": "B" if (audio or len(fuentes) > 1) else "A",
        "fuentes": fuentes, "audio_externo": str(audio) if audio else None,
        "guion": str(Path(guion).expanduser().resolve()) if guion else None,
        "hablantes": hablantes, "dur": round(dur_total, 3),
        "url_largo": url_largo, "palabra_cta": palabra.upper() if palabra else None,
    }
    config.escribir(ep_dir / "episodio.json", meta)

    a_dir = ep_dir / "00_ingest"
    a_dir.mkdir(exist_ok=True)
    wav = a_dir / "voz16k.wav"
    if not wav.exists():
        if audio:
            media.extraer_audio(audio, wav)
        elif len(fuentes) == 1:
            media.extraer_audio(fuentes[0]["ruta"], wav)
        else:
            lista = a_dir / "lista.txt"
            lista.write_text("".join(f"file '{Path(f['ruta']).as_posix()}'\n" for f in fuentes), encoding="utf-8")
            media.correr([media.ffmpeg_bin(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lista,
                          "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav])
    vista = a_dir / "vista.jpg"
    if not vista.exists():
        f0 = fuentes[0]
        paso = max(1.0, f0["info"]["dur"] / 7)
        media.correr([media.ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{paso / 2:.1f}", "-i", f0["ruta"],
                      "-vf", f"fps=1/{paso:.2f},scale=320:-2,tile=6x1", "-frames:v", "1", vista])
    print(f"Episodio listo: {ep_dir}")
    return ep_dir


def resolver(meta, t):
    """Tiempo maestro -> (archivo, tiempo local). None si en ese instante no hay cámara grabando."""
    for f in meta["fuentes"]:
        local = t - f["offset"]
        if -0.001 <= local < f["info"]["dur"]:
            return f, max(0.0, local)
    return None, None
