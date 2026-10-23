"""Etapa 3: transcripción completa con tiempos por palabra.

Mac Apple Silicon -> mlx-whisper (GPU de la Mac). Windows / Linux -> faster-whisper (CUDA si hay, si no CPU int8).
"""
import os
import time

from .. import config, media

MODELO_MLX = "mlx-community/whisper-large-v3-turbo"
MODELO_FASTER = "large-v3-turbo"


def backend():
    forzado = os.environ.get("CLIPPER_ASR")
    if forzado:
        return forzado
    if media.es_mac_arm():
        try:
            import mlx_whisper  # noqa: F401
            return "mlx"
        except ImportError:
            pass
    return "faster"


def _prompt(marca):
    vocab = ", ".join(marca.get("vocabulario", [])[:40])
    return f"Eh, este, o sea... {vocab}." if vocab else "Eh, este, o sea..."


def transcribir_wav(wav, marca, modelo=None):
    b = backend()
    if b == "mlx":
        import mlx_whisper
        r = mlx_whisper.transcribe(str(wav), path_or_hf_repo=modelo or MODELO_MLX, language=marca.get("idioma", "es"),
                                   word_timestamps=True, condition_on_previous_text=False,
                                   hallucination_silence_threshold=2.0, initial_prompt=_prompt(marca), verbose=None)
        segs = [{"start": s["start"], "end": s["end"], "text": s["text"],
                 "words": [{"word": w["word"], "start": w["start"], "end": w["end"], "p": w.get("probability", 1.0)}
                           for w in s.get("words", [])]} for s in r["segments"]]
    else:
        from faster_whisper import WhisperModel
        try:
            import ctranslate2
            cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            cuda = False
        m = WhisperModel(modelo or MODELO_FASTER, device="cuda" if cuda else "cpu",
                         compute_type="float16" if cuda else "int8")
        it, _ = m.transcribe(str(wav), language=marca.get("idioma", "es"), word_timestamps=True,
                             condition_on_previous_text=False, vad_filter=True, initial_prompt=_prompt(marca))
        segs = [{"start": s.start, "end": s.end, "text": s.text,
                 "words": [{"word": w.word, "start": w.start, "end": w.end, "p": w.probability} for w in (s.words or [])]}
                for s in it]
    return {"backend": b, "segments": segs}


def correr(ep, forzar=False):
    destino = ep.ruta("02_transcribe", "transcripcion.json")
    if destino.exists() and not forzar:
        print("  transcripción ya existe (usa --forzar para repetir)")
        return destino
    t0 = time.time()
    print(f"  transcribiendo {ep.meta['dur'] / 60:.1f} min con {backend()}…", flush=True)
    r = transcribir_wav(ep.ruta("00_ingest", "voz16k.wav"), ep.marca)
    r["segundos"] = round(time.time() - t0, 1)
    config.escribir(destino, r)
    n = sum(len(s["words"]) for s in r["segments"])
    print(f"  {n} palabras en {r['segundos']:.0f}s ({ep.meta['dur'] / max(1, r['segundos']):.0f}x tiempo real)")
    return destino
