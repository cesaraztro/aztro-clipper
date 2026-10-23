"""Etapa 3: transcripción completa con tiempos por palabra.

Mac Apple Silicon -> mlx-whisper (GPU de la Mac). Windows / Linux -> faster-whisper (CUDA si hay, si no CPU int8).
faster-whisper también queda instalado en Mac como respaldo (p. ej. en máquinas virtuales sin GPU).
"""
import os
import time
import wave

import numpy as np

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


def modelo_para(b, modelo=None):
    """CLIPPER_MODELO permite un modelo más chico (p. ej. 'small' en una PC lenta, 'tiny' en pruebas)."""
    m = modelo or os.environ.get("CLIPPER_MODELO")
    if b == "mlx":
        if not m:
            return MODELO_MLX
        return m if "/" in m else f"mlx-community/whisper-{m}" + ("" if m.endswith("turbo") else "-mlx")
    return m or MODELO_FASTER


def precargar():
    b = backend()
    if b == "mlx":
        from huggingface_hub import snapshot_download
        snapshot_download(modelo_para(b))
    else:
        from faster_whisper import WhisperModel
        WhisperModel(modelo_para(b), device="cpu", compute_type="int8")


def _prompt(marca):
    vocab = ", ".join(marca.get("vocabulario", [])[:40])
    return f"Eh, este, o sea... {vocab}." if vocab else "Eh, este, o sea..."


def _audio(wav):
    """WAV 16 kHz mono como float32: así ningún motor depende de decodificadores externos (PyAV)."""
    with wave.open(str(wav)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def _mlx(wav, marca, modelo):
    import mlx_whisper
    r = mlx_whisper.transcribe(_audio(wav), path_or_hf_repo=modelo_para("mlx", modelo), language=marca.get("idioma", "es"),
                               word_timestamps=True, condition_on_previous_text=False,
                               hallucination_silence_threshold=2.0, initial_prompt=_prompt(marca), verbose=None)
    segs = [{"start": s["start"], "end": s["end"], "text": s["text"],
             "words": [{"word": w["word"], "start": w["start"], "end": w["end"], "p": w.get("probability", 1.0)}
                       for w in s.get("words", [])]} for s in r["segments"]]
    return {"backend": "mlx", "segments": segs}


def _faster(wav, marca, modelo):
    from faster_whisper import WhisperModel
    try:
        import ctranslate2
        cuda = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        cuda = False
    m = WhisperModel(modelo_para("faster", modelo), device="cuda" if cuda else "cpu",
                     compute_type="float16" if cuda else "int8")
    it, _ = m.transcribe(_audio(wav), language=marca.get("idioma", "es"), word_timestamps=True,
                         condition_on_previous_text=False, vad_filter=True, initial_prompt=_prompt(marca))
    segs = [{"start": s.start, "end": s.end, "text": s.text,
             "words": [{"word": w.word, "start": w.start, "end": w.end, "p": w.probability} for w in (s.words or [])]}
            for s in it]
    return {"backend": "faster", "segments": segs}


def transcribir_wav(wav, marca, modelo=None):
    if backend() == "mlx":
        try:
            return _mlx(wav, marca, modelo)
        except Exception as e:  # sin GPU Metal disponible (p. ej. una VM): se usa el motor universal
            print(f"  aviso: mlx-whisper falló ({type(e).__name__}); sigo con faster-whisper")
            os.environ["CLIPPER_ASR"] = "faster"
    return _faster(wav, marca, modelo)


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
