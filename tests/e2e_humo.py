"""Prueba de punta a punta con el comando `clipper` instalado. Corre igual en Mac, Windows y Linux (CI).

Genera voz con el sintetizador del sistema, arma un video de prueba y pasa por todas las etapas:
ingest → transcribe → select (como lo haría el agente) → run (plan, reframe, render, qa, package) → cta.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FRASES = [
    "Artificial intelligence is changing how small businesses work.",
    "Most owners do not know where to start, so they buy tools they never use.",
    "The secret is simple. Give the model real context about your company.",
    "Write down your process, your clients and your goals.",
    "Then automate one small task every single week.",
    "In three months you will save hours every day.",
]


def clipper(*args, env):
    exe = shutil.which("clipper", path=env.get("PATH"))
    cmd = [exe, *args] if exe else [sys.executable, "-m", "clipper.cli", *args]
    print("$ clipper " + " ".join(args), flush=True)
    r = subprocess.run(cmd, env=env, text=True, encoding="utf-8", errors="replace", capture_output=True)
    print(r.stdout[-3000:], r.stderr[-3000:], sep="\n", flush=True)
    if r.returncode:
        raise SystemExit(f"falló: clipper {' '.join(args)}")
    return r.stdout


def _frase(texto, destino):
    so = platform.system()
    if so == "Darwin":
        subprocess.run(["say", "-r", "170", "-o", str(destino.with_suffix(".aiff")), texto], check=True)
        return destino.with_suffix(".aiff")
    if so == "Windows":
        ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.SetOutputToWaveFile('{destino}'); $s.Speak('{texto}'); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
        return destino
    subprocess.run(["espeak-ng", "-s", "150", "-w", str(destino), texto], check=True)
    return destino


def voz(destino, ff):
    """Una frase por archivo, unidas con pausas de 0.7 s y 1 s de silencio al inicio (como una charla real)."""
    partes = [_frase(f, destino.parent / f"frase{i}.wav") for i, f in enumerate(FRASES)]
    entradas = [x for p in partes for x in ("-i", str(p))]
    filtro = "".join(f"[{i}:a]aresample=16000,aformat=channel_layouts=mono,apad=pad_dur=0.7[a{i}];" for i in range(len(partes)))
    filtro += "".join(f"[a{i}]" for i in range(len(partes))) + f"concat=n={len(partes)}:v=0:a=1,adelay=1000:all=1[out]"
    subprocess.run([ff, "-y", "-v", "error", *entradas, "-filter_complex", filtro, "-map", "[out]", str(destino)], check=True)
    return destino


def main():
    for flujo in (sys.stdout, sys.stderr):  # consola de Windows sin UTF-8
        flujo.reconfigure(encoding="utf-8", errors="replace")
    tmp = Path(tempfile.mkdtemp(prefix="clipper-humo-"))
    env = dict(os.environ, CLIPPER_DATA=str(tmp / "datos"))
    env.setdefault("CLIPPER_MODELO", "tiny")
    from clipper import media  # mismo ffmpeg que usará clipper
    ff = media.ffmpeg_bin()

    audio = voz(tmp / "voz.wav", ff)
    video = tmp / "entrevista de prueba.mp4"  # con espacio a propósito
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-i", str(audio),
                    "-af", "apad=pad_dur=1", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)],
                   check=True)

    clipper("marca", "prueba", "--nombre", "Marca de prueba ñ", env=env)
    mj = tmp / "datos" / "marcas" / "prueba" / "marca.json"
    m = json.loads(mj.read_text(encoding="utf-8"))
    m.update(idioma="en", seleccion={"duracion": [5, 120], "clips_por_hora": [10, 15]},
             audio={"lufs": -14.0, "musica": None, "musica_volumen": 0.14})
    mj.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")

    clipper("ingest", str(video), "--marca", "prueba", "--slug", "humo", "--hablantes", "1", env=env)
    ep = next((tmp / "datos" / "episodios").iterdir())
    clipper("transcribe", ep.name, env=env)
    ors = json.loads((ep / "04_segment" / "oraciones.json").read_text(encoding="utf-8"))
    assert len(ors) >= 3, f"muy pocas oraciones transcritas: {len(ors)}"
    (ep / "05_select").mkdir(exist_ok=True)
    (ep / "05_select" / "seleccion.json").write_text(json.dumps({"palabra_cta": "PRUEBA", "clips": [{
        "id": "01", "inicio": ors[0]["id"], "fin": ors[-1]["id"], "titulo": "Prueba de humo: contexto para la IA",
        "gancho": "Dale contexto a la IA", "viral_score": 70, "enfasis": ["context", "automate", "hours"],
        "descripcion": "Clip de prueba automática."}]}, ensure_ascii=False), encoding="utf-8")
    clipper("select", ep.name, "--validar", env=env)
    clipper("run", ep.name, env=env)
    clipper("cta", ep.name, "--palabra", "PRUEBA", "--url", "https://youtu.be/prueba", env=env)

    clip_dir = next((ep / "clips").iterdir())
    qa = json.loads((clip_dir / "qa.json").read_text(encoding="utf-8"))
    entregable = ep / "entregables" / clip_dir.name
    videos = sorted(p.name for p in entregable.glob("video_*.mp4"))
    assert qa["ok"], f"QA falló: {qa['fallas']}"
    assert videos == ["video_facebook.mp4", "video_instagram.mp4", "video_tiktok.mp4", "video_youtube.mp4"], videos
    assert (entregable / "portada.jpg").exists() and (ep / "manychat_PRUEBA.md").exists()
    print(f"\nOK en {platform.system()}: {qa['datos']}")


if __name__ == "__main__":
    main()
