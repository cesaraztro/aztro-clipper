"""Utilidades de FFmpeg portables (Mac y Windows): sondeo, aceleración por hardware y codificadores."""
import functools
import platform
import re
import shutil
import subprocess
from pathlib import Path

TONEMAP = ("zscale=tin=arib-std-b67:min=bt2020nc:pin=bt2020:rin=tv:t=linear:npl=203,format=gbrpf32le,"
           "zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv")
TONEMAP_PQ = TONEMAP.replace("tin=arib-std-b67", "tin=smpte2084")
BT709 = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]


class ErrorFFmpeg(RuntimeError):
    pass


def ffmpeg_bin():
    b = shutil.which("ffmpeg")
    if not b:
        raise SystemExit("No encuentro ffmpeg. Corre el instalador o: brew install ffmpeg / winget install Gyan.FFmpeg")
    return b


def correr(cmd, **kw):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise ErrorFFmpeg(f"Falló {Path(str(cmd[0])).name} (código {r.returncode}):\n{r.stderr[-2500:]}")
    return r


def es_mac_arm():
    return platform.system() == "Darwin" and platform.machine() == "arm64"


@functools.lru_cache(None)
def _listado(tipo):
    return subprocess.run([ffmpeg_bin(), "-hide_banner", f"-{tipo}"], capture_output=True, text=True).stdout


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


def encoder_h264(bitrate="8M", intermedio=False):
    """H.264 SDR: lo único que Metricool publica en automático. Elige el codificador por hardware disponible."""
    br = "20M" if intermedio else bitrate
    if tiene_encoder("h264_videotoolbox"):
        return ["-c:v", "h264_videotoolbox", "-b:v", br, "-profile:v", "high"]
    if tiene_encoder("h264_nvenc"):
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-b:v", br, "-profile:v", "high"]
    if tiene_encoder("h264_qsv"):
        return ["-c:v", "h264_qsv", "-b:v", br, "-profile:v", "high"]
    if tiene_encoder("h264_amf"):
        return ["-c:v", "h264_amf", "-b:v", br, "-profile:v", "high"]
    crf = "16" if intermedio else "20"
    return ["-c:v", "libx264", "-preset", "faster", "-crf", crf, "-maxrate", br, "-bufsize", "16M", "-profile:v", "high"]


def sondear(ruta):
    """Duración, tamaño visible (ya rotado), fps, HDR y audio. Funciona sin ffprobe (solo con ffmpeg)."""
    err = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", str(ruta)], capture_output=True, text=True).stderr
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
    """Escapa una ruta para usarla dentro de un filtro de ffmpeg (espacios, ':' de Windows, comillas)."""
    s = Path(p).resolve().as_posix()
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(" ", "\\ ").replace(",", "\\,")


def medir_loudness(ruta):
    err = subprocess.run([ffmpeg_bin(), "-hide_banner", "-nostats", "-i", str(ruta), "-af", "ebur128=peak=true",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    resumen = err[err.rfind("Summary:"):]
    i = re.search(r"I:\s*(-?[\d.]+) LUFS", resumen)
    pk = re.search(r"Peak:\s*(-?[\d.]+) dBFS", resumen)
    return (float(i[1]) if i else None, float(pk[1]) if pk else None)
