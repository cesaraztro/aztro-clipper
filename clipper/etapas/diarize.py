"""Etapa 4: ¿quién habla cuándo? Diarización ligera por voz, sin modelos externos ni tokens.

Cada ventana de 1.5 s con voz se resume con su "huella" MFCC (timbre) y se agrupa en N hablantes con k-means.
Funciona bien con voces distintas (p. ej. entrevistador/a e invitado/a). Para paneles grandes o voces muy
parecidas, la Fase 2 suma pyannote (requiere HF_TOKEN).
"""
import wave

import numpy as np

from .. import config
from ..energia import Energia

SR, N_FFT, WIN, HOP = 16000, 512, 400, 160
VENTANA, PASO = 1.5, 0.5


def _mel(n_mels=26, fmin=60, fmax=7600):
    def hz2mel(f): return 2595 * np.log10(1 + f / 700)
    def mel2hz(m): return 700 * (10 ** (m / 2595) - 1)
    pts = mel2hz(np.linspace(hz2mel(fmin), hz2mel(fmax), n_mels + 2))
    bins = np.floor((N_FFT + 1) * pts / SR).astype(int)
    fb = np.zeros((n_mels, N_FFT // 2 + 1))
    for m in range(1, n_mels + 1):
        a, b, c = bins[m - 1], bins[m], bins[m + 1]
        fb[m - 1, a:b] = (np.arange(a, b) - a) / max(1, b - a)
        fb[m - 1, b:c] = (c - np.arange(b, c)) / max(1, c - b)
    return fb


def mfcc(x, n=13):
    n_fr = 1 + (len(x) - WIN) // HOP
    if n_fr <= 0:
        return np.zeros((0, n))
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n_fr)[:, None]
    fr = x[idx] * np.hamming(WIN)
    pot = np.abs(np.fft.rfft(fr, N_FFT)) ** 2 / N_FFT
    logmel = np.log(pot @ _mel().T + 1e-10)
    k = np.arange(logmel.shape[1])
    dct = np.cos(np.pi / logmel.shape[1] * (k[None, :] + 0.5) * np.arange(1, n + 1)[:, None])
    return logmel @ dct.T


def kmeans(X, k, intentos=12, iters=60, seed=0):
    rng = np.random.default_rng(seed)
    mejor, mejor_inercia = None, np.inf
    for _ in range(intentos):
        c = X[rng.choice(len(X), k, replace=False)]
        for _ in range(iters):
            lab = np.argmin(((X[:, None] - c[None]) ** 2).sum(-1), axis=1)
            nuevo = np.array([X[lab == j].mean(0) if (lab == j).any() else c[j] for j in range(k)])
            if np.allclose(nuevo, c):
                break
            c = nuevo
        inercia = ((X - c[lab]) ** 2).sum()
        if inercia < mejor_inercia:
            mejor, mejor_inercia = lab, inercia
    return mejor


def correr(ep, forzar=False):
    destino = ep.ruta("03_diarize", "hablantes.json")
    k = ep.meta.get("hablantes") or 1
    if destino.exists() and not forzar:
        return config.leer(destino)
    if k < 2:
        res = {"k": 1, "ventanas": []}
        config.escribir(destino, res)
        return res
    wav = ep.ruta("00_ingest", "voz16k.wav")
    with wave.open(str(wav)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    en = Energia(wav)
    M = mfcc(x)
    voz = en.db[: len(M)] >= en.umbral
    ventanas, feats = [], []
    t = 0.0
    while t + VENTANA <= len(M) * 0.01:
        i0, i1 = int(t * 100), int((t + VENTANA) * 100)
        sel = voz[i0:i1]
        if sel.sum() >= 40:
            m = M[i0:i1][sel]
            feats.append(np.concatenate([m.mean(0), m.std(0)]))
            ventanas.append([round(t, 2), round(t + VENTANA, 2)])
        t += PASO
    X = np.array(feats)
    X = (X - X.mean(0)) / (X.std(0) + 1e-9)
    lab = kmeans(X, k)
    # suavizado: una ventana aislada entre dos iguales se corrige
    for i in range(1, len(lab) - 1):
        if lab[i - 1] == lab[i + 1] != lab[i]:
            lab[i] = lab[i - 1]
    res = {"k": k, "metodo": "mfcc-kmeans", "ventanas": [[a, b, int(l)] for (a, b), l in zip(ventanas, lab)]}
    config.escribir(destino, res)
    tot = np.bincount(lab, minlength=k) * PASO
    print("  diarización: " + " · ".join(f"voz {j + 1}: {tot[j] / 60:.1f} min" for j in range(k)))
    return res


def voces_en(diar, a, b):
    """Peso de cada voz dentro de [a, b] (vector de largo k)."""
    v = np.zeros(diar["k"])
    for t0, t1, l in diar["ventanas"]:
        tras = min(b, t1) - max(a, t0)
        if tras > 0:
            v[l] += tras
    return v
