"""Utilidades de FFmpeg portables (Mac y Windows): sondeo, aceleración por hardware y codificadores."""
import functools
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

TXT = {"text": True, "encoding": "utf-8", "errors": "replace"}  # Windows no usa UTF-8 por defecto

TONEMAP = ("zscale=tin=arib-std-b67:min=bt2020nc:pin=bt2020:rin=tv:t=linear:npl=203,format=gbrpf32le,"
           "zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv")
TONEMAP_PQ = TONEMAP.replace("tin=arib-std-b67", "tin=smpte2084")
BT709 = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]


class ErrorFFmpeg(RuntimeError):
    pass


FILTROS_REQUERIDOS = ("subtitles", "zscale", "perspective", "loudnorm", "lut3d", "sidechaincompress", "ebur128")


def _candidatos_ffmpeg():
    """Lugares donde queda ffmpeg al instalarlo (por si la terminal aún no recarga el PATH)."""
    exe = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    if os.environ.get("CLIPPER_FFMPEG"):
        yield Path(os.environ["CLIPPER_FFMPEG"])
    w = shutil.which("ffmpeg")
    if w:
        yield Path(w)
    home = Path.home()
    if platform.system() == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        yield local / "Microsoft" / "WinGet" / "Links" / exe
        yield from (local / "Microsoft" / "WinGet" / "Packages").glob(f"Gyan.FFmpeg*/*/bin/{exe}")
        yield Path("C:/ProgramData/chocolatey/bin") / exe
        yield home / "scoop" / "shims" / exe
    else:
        # Homebrew: la fórmula 'ffmpeg' ya no trae libass/zimg; 'ffmpeg-full' sí (y no se enlaza al PATH)
        for pre in ("/opt/homebrew", "/usr/local"):
            yield Path(pre) / "opt" / "ffmpeg-full" / "bin" / exe
        yield from (Path(p) / exe for p in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"))


@functools.lru_cache(None)
def _filtros_de(binario):
    out = subprocess.run([binario, "-hide_banner", "-filters"], capture_output=True, **TXT).stdout
    return {m[1] for m in re.finditer(r"^\s*\S+\s+(\w+)\s", out, re.M)}


def es_completo(binario):
    return all(f in _filtros_de(str(binario)) for f in FILTROS_REQUERIDOS)


@functools.lru_cache(None)
def ffmpeg_bin():
    """El primer ffmpeg con todos los filtros que usa clipper; si ninguno los tiene, el primero que exista."""
    vistos = [c for c in dict.fromkeys(_candidatos_ffmpeg()) if c.exists()]
    for c in vistos:
        if es_completo(c):
            return str(c)
    if vistos:
        return str(vistos[0])
    raise SystemExit("No encuentro ffmpeg. Corre: clipper setup")


def correr(cmd, **kw):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, **TXT, **kw)
    if r.returncode != 0:
        raise ErrorFFmpeg(f"Falló {Path(str(cmd[0])).name} (código {r.returncode}):\n{r.stderr[-2500:]}")
    return r


def es_mac_arm():
    return platform.system() == "Darwin" and platform.machine() == "arm64"


@functools.lru_cache(None)
def _listado(tipo):
    return subprocess.run([ffmpeg_bin(), "-hide_banner", f"-{tipo}"], capture_output=True, **TXT).stdout


def tiene_filtro(nombre):
    return re.search(rf"^\s*\S+\s+{re.escape(nombre)}\s", _listado("filters"), re.M) is not None


def tiene_encoder(nombre):
    return re.search(rf"^\s*V\S*\s+{re.escape(nombre)}\s", _listado("encoders"), re.M) is not None


def hwaccel():
    """Decodificación por hardware cuando existe (HEVC 4K de iPhone o Canon decodifica 3-5x más rápido)."""
    if platform.system() == "Darwin":
        return ["-hwaccel", "videotoolbox"]
    if platform.system() == "Windows":
        return ["-hwaccel", "auto"]
    return []


@functools.lru_cache(None)
def funciona_encoder(nombre):
    """Que ffmpeg liste un codificador no garantiza que haya hardware (p. ej. nvenc sin tarjeta NVIDIA): se prueba."""
    if not tiene_encoder(nombre):
        return False
    r = subprocess.run([ffmpeg_bin(), "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=256x256:d=0.2",
                        "-c:v", nombre, "-pix_fmt", "yuv420p", "-f", "null", "-"], capture_output=True, **TXT)
    return r.returncode == 0


def encoder_elegido():
    forzado = os.environ.get("CLIPPER_ENCODER")
    if forzado:
        return forzado
    for e in ("h264_videotoolbox", "h264_nvenc", "h264_qsv", "h264_amf"):
        if funciona_encoder(e):
            return e
    return "libx264"


def encoder_h264(bitrate="8M", intermedio=False):
    """H.264 SDR: lo único que Metricool publica en automático. Usa la GPU que de verdad funcione."""
    br = "20M" if intermedio else bitrate
    e = encoder_elegido()
    if e == "libx264":
        crf = "16" if intermedio else "20"
        return ["-c:v", "libx264", "-preset", "faster", "-crf", crf, "-maxrate", br, "-bufsize", "16M", "-profile:v", "high"]
    extra = ["-preset", "p5"] if e == "h264_nvenc" else []
    return ["-c:v", e, *extra, "-b:v", br, "-profile:v", "high"]


def sondear(ruta):
    """Duración, tamaño visible (ya rotado), fps, HDR y audio. Funciona sin ffprobe (solo con ffmpeg)."""
    err = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", str(ruta)], capture_output=True, **TXT).stderr
    return parsear_info(err)


def parsear_info(err):
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0
    v = re.search(r"Stream #\S+.*?Video: (\w+).*?(\d{3,5})x(\d{3,5})", err)
    codec, w, h = (v[1], int(v[2]), int(v[3])) if v else ("", 0, 0)
    rot = re.search(r"rotation of (-?[\d.]+)", err) or re.search(r"rotate\s*:\s*(-?\d+)", err)
    if rot and abs(float(rot[1])) % 180 == 90:
        w, h = h, w
    f = re.search(r"([\d.]+) fps", err)
    hdr = "pq" if "smpte2084" in err else ("hlg" if "arib-std-b67" in err else None)
    return {"dur": round(dur, 3), "w": w, "h": h, "fps": float(f[1]) if f else 30.0, "vcodec": codec,
            "hdr": hdr, "audio": "Audio:" in err}


def tonemap_para(info):
    return {"hlg": TONEMAP, "pq": TONEMAP_PQ}.get(info.get("hdr"), "")


def extraer_audio(src, destino, sr=16000, ss=None, t=None):
    cmd = [ffmpeg_bin(), "-y", "-v", "error"]
    if ss is not None:
        cmd += ["-ss", f"{ss:.3f}"]
    if t is not None:
        cmd += ["-t", f"{t:.3f}"]
    cmd += ["-i", str(src), "-vn", "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(destino)]
    correr(cmd)
    return destino


def ruta_filtro(p):
    """Ruta para un filtro de ffmpeg en cualquier sistema: entre comillas (espacios, comas) y con ':' escapado
    (la letra de unidad de Windows, C:, rompía el filtro de subtítulos)."""
    s = Path(p).resolve().as_posix()
    return "'" + s.replace("'", "'\\''").replace(":", "\\:") + "'"


def medir_loudness(ruta):
    err = subprocess.run([ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(ruta), "-af", "ebur128=peak=true",
                          "-f", "null", "-"], capture_output=True, **TXT).stderr
    resumen = err[err.rfind("Summary:"):]
    i = re.search(r"I:\s*(-?[\d.]+) LUFS", resumen)
    pk = re.search(r"Peak:\s*(-?[\d.]+) dBFS", resumen)
    return (float(i[1]) if i else None, float(pk[1]) if pk else None)
