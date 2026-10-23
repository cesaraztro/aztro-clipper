"""clipper setup: deja todo listo en Mac, Windows o Linux, sin que el usuario tenga que saber cuál usa.

1. FFmpeg: lo instala con el gestor que haya (Homebrew, winget, Chocolatey, Scoop, apt/dnf/pacman).
2. Carpeta de datos (~/AztroClipper): episodios, marcas y modelos.
3. Skills para los agentes: ~/.claude/skills (Claude Code y OpenCode) y ~/.agents/skills (Codex y OpenCode).
4. Modelo de detección de caras y, si se pide, el de transcripción.
5. clipper doctor.
"""
import platform
import shutil
import subprocess
from pathlib import Path

from .. import config, media

DESTINOS_SKILLS = {
    "Claude Code / OpenCode": Path.home() / ".claude" / "skills",
    "Codex / OpenCode": Path.home() / ".agents" / "skills",
}


def _correr(cmd):
    print(f"    $ {' '.join(cmd)}")
    return subprocess.run(cmd).returncode == 0


def instalar_ffmpeg():
    try:
        if media.es_completo(media.ffmpeg_bin()):
            print(f"  ✓ ffmpeg completo: {media.ffmpeg_bin()}")
            return True
        print(f"  ffmpeg encontrado ({media.ffmpeg_bin()}) pero le faltan filtros (subtítulos/zscale): instalo el completo…")
    except SystemExit:
        print("  instalando ffmpeg…")
    so = platform.system()
    if so == "Darwin":
        intentos = [["brew", "install", "ffmpeg-full"]]
    elif so == "Windows":
        intentos = [["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-source-agreements", "--accept-package-agreements"],
                    ["choco", "install", "ffmpeg-full", "-y"],
                    ["scoop", "install", "ffmpeg"]]
    else:
        root = shutil.which("id") and subprocess.run(["id", "-u"], capture_output=True, text=True).stdout.strip() == "0"
        sudo = [] if root else ["sudo", "-n"]
        intentos = [[*sudo, "apt-get", "install", "-y", "ffmpeg"], [*sudo, "dnf", "install", "-y", "ffmpeg"],
                    [*sudo, "pacman", "-S", "--noconfirm", "ffmpeg"]]
    for cmd in intentos:
        exe = cmd[2] if cmd[:2] == ["sudo", "-n"] else cmd[0]
        if not shutil.which(exe) or not _correr(cmd):
            continue
        media.ffmpeg_bin.cache_clear(); media._listado.cache_clear()
        try:
            ff = media.ffmpeg_bin()
        except SystemExit:
            print("  ffmpeg se instaló pero esta terminal aún no lo ve: ciérrala, ábrela y corre de nuevo `clipper setup`.")
            return False
        if media.es_completo(ff):
            print(f"  ✓ ffmpeg completo instalado: {ff}")
            return True
    ayuda = {"Darwin": "instala Homebrew (https://brew.sh) y corre: brew install ffmpeg-full",
             "Windows": "corre en PowerShell: winget install Gyan.FFmpeg",
             "Linux": "corre: sudo apt-get install -y ffmpeg"}.get(so, "instala ffmpeg con libass y zimg")
    print(f"  ✗ no pude dejar un ffmpeg completo automáticamente → {ayuda}")
    return False


def instalar_skills():
    origen = config.PAQUETE / "skills"
    for agente, base in DESTINOS_SKILLS.items():
        for sk in sorted(p for p in origen.iterdir() if (p / "SKILL.md").exists()):
            dest = base / sk.name
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sk / "SKILL.md", dest / "SKILL.md")
        print(f"  ✓ skills para {agente} en {base}")


def preparar_modelos(transcripcion=False):
    from .reframe import modelo_yunet
    modelo_yunet()
    print("  ✓ detector de caras listo")
    if transcripcion:
        from .transcribe import precargar
        precargar()
        print("  ✓ modelo de transcripción descargado")


def correr(sin_ffmpeg=False, sin_skills=False, modelos=False, marca=None, nombre=None):
    print(f"aztro-clipper · {platform.system()} {platform.machine()}")
    if not sin_ffmpeg:
        instalar_ffmpeg()
    for d in (config.episodios_dir(), config.marcas_dir()):
        d.mkdir(parents=True, exist_ok=True)
    print(f"  ✓ carpeta de datos: {config.datos_dir()}")
    if marca:
        print(f"  ✓ marca '{marca}' en {config.crear_marca(marca, nombre)}")
    elif not config.marcas_disponibles():
        print(f"  ✓ marca de ejemplo en {config.crear_marca('mimarca', 'Mi marca')} (edita marca.json y criterio.md)")
    if not sin_skills:
        instalar_skills()
    preparar_modelos(modelos)
    from . import doctor
    return doctor.correr()
