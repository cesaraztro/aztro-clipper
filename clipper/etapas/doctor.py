"""clipper doctor: verifica que la instalación funcione en esta máquina (Mac o Windows)."""
import importlib
import platform
import shutil
import sys

from .. import config, media


def correr():
    ok = True

    def check(nombre, cond, ayuda=""):
        nonlocal ok
        print(f"  {'✓' if cond else '✗'} {nombre}" + ("" if cond else f"  → {ayuda}"))
        ok &= bool(cond)

    print(f"Sistema: {platform.system()} {platform.machine()} · Python {sys.version.split()[0]}")
    check("Python 3.11 o 3.12", (3, 11) <= sys.version_info[:2] <= (3, 12), "usa el instalador (uv instala 3.12)")
    ff = shutil.which("ffmpeg")
    check("ffmpeg instalado", ff, "Mac: brew install ffmpeg · Windows: winget install Gyan.FFmpeg")
    if ff:
        for f in ("subtitles", "zscale", "perspective", "loudnorm", "lut3d", "sidechaincompress", "ebur128"):
            check(f"ffmpeg con filtro {f}", media.tiene_filtro(f), "instala un build 'full' de ffmpeg")
        enc = next((e for e in ("h264_videotoolbox", "h264_nvenc", "h264_qsv", "h264_amf", "libx264") if media.tiene_encoder(e)), None)
        check(f"codificador H.264 ({enc})", enc, "ffmpeg sin libx264")
    for mod in ("numpy", "cv2"):
        try:
            importlib.import_module(mod); check(f"módulo {mod}", True)
        except ImportError:
            check(f"módulo {mod}", False, "corre el instalador")
    from .transcribe import backend
    b = backend()
    try:
        importlib.import_module("mlx_whisper" if b == "mlx" else "faster_whisper")
        check(f"transcripción ({b})", True)
    except ImportError:
        check(f"transcripción ({b})", False, "corre el instalador")
    check("fuentes Poppins", len(list(config.FUENTES.glob("*.ttf"))) >= 3, "faltan recursos/fuentes")
    d = config.datos_dir()
    nube = any(x in str(d) for x in ("Mobile Documents", "iCloud", "OneDrive", "Dropbox", "CloudStorage"))
    check(f"carpeta de trabajo fuera de la nube ({d})", not nube, "define CLIPPER_DATA en .env fuera de iCloud/OneDrive")
    marcas = sorted(p.name for p in config.MARCAS.iterdir() if (p / "marca.json").exists())
    check(f"marcas: {', '.join(marcas)}", marcas, "copia marcas/_plantilla")
    print("Todo en verde." if ok else "Hay pendientes (✗).")
    return 0 if ok else 1
