"""Sincroniza audio de doble sistema: encuentra en qué segundo del audio externo empieza cada archivo de cámara.

Caso típico: cámara Canon que parte la grabación en varios MVI_xxxx.MP4 y un micrófono que graba un solo WAV.
Se compara la forma de onda (correlación cruzada por FFT) al inicio, mitad y final de cada archivo para medir
también la deriva de reloj entre aparatos.
"""
import wave
from pathlib import Path

import numpy as np

from .. import media

SR = 4000  # 0.25 ms de resolución, de sobra para quedar dentro de un cuadro (33 ms)


def leer_wav(ruta):
    with wave.open(str(ruta)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    return x / 32768.0


def _preparar(x):
    x = x - x.mean()
    # se compara la "forma" de la voz, no el volumen (cada micrófono tiene su ganancia)
    return x / (np.abs(x).max() + 1e-9)


def correlacion(maestro, trozo, sr=SR):
    """Devuelve (offset_s, confianza): dónde empieza 'trozo' dentro de 'maestro'. Confianza = pico / 2º pico."""
    a, b = _preparar(maestro), _preparar(trozo)
    n = len(a) + len(b)
    nfft = 1 << (n - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(a, nfft) * np.conj(np.fft.rfft(b, nfft)), nfft)
    c = np.abs(c[: len(a)])
    i = int(np.argmax(c))
    guarda = int(0.1 * sr)
    resto = np.concatenate([c[: max(0, i - guarda)], c[i + guarda:]])
    segundo = float(resto.max()) if len(resto) else 1e-9
    return i / sr, float(c[i] / (segundo + 1e-9))


def sincronizar(audio_externo, videos, tmp_dir, ventana=45.0):
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    m_wav = media.extraer_audio(audio_externo, tmp_dir / "maestro_4k.wav", sr=SR)
    maestro = leer_wav(m_wav)
    out = []
    for k, v in enumerate(videos):
        info = media.sondear(v)
        puntos = []
        for frac in (0.0, 0.5, 1.0):
            ini = max(0.0, min(info["dur"] - ventana, frac * (info["dur"] - ventana)))
            w = media.extraer_audio(v, tmp_dir / f"cam{k}_{int(frac * 100)}.wav", sr=SR, ss=ini, t=min(ventana, info["dur"]))
            off, conf = correlacion(maestro, leer_wav(w))
            puntos.append({"t_local": round(ini, 3), "offset": round(off - ini, 4), "confianza": round(conf, 2)})
        buenos = [p for p in puntos if p["confianza"] >= 3] or puntos
        base = buenos[0]["offset"]
        deriva = 0.0
        if len(buenos) > 1 and buenos[-1]["t_local"] > buenos[0]["t_local"]:
            deriva = (buenos[-1]["offset"] - base) / (buenos[-1]["t_local"] - buenos[0]["t_local"]) * 1e6
        out.append({"ruta": str(v), "offset": round(base, 4), "deriva_ppm": round(deriva, 1), "puntos": puntos,
                    "confianza": min(p["confianza"] for p in puntos)})
    return out
