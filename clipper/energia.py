"""Nivel de la voz cada 10 ms para que los cortes caigan en silencio real y nunca a media palabra.

Portado del motor v4 (reel.py, clase Energia) y vectorizado con numpy: una hora de audio se analiza
en menos de un segundo en lugar de minutos.
"""
import wave

import numpy as np

HOP_S = 0.01


class Energia:
    def __init__(self, wav=None, muestras=None, sr=16000):
        if wav is not None:
            with wave.open(str(wav)) as w:
                sr = w.getframerate()
                muestras = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        x = np.asarray(muestras, dtype=np.float64)
        hop = int(sr * HOP_S)
        n = max(0, len(x) // hop)
        bloques = x[: n * hop].reshape(n, hop) if n else np.zeros((1, hop))
        self.db = 10 * np.log10((bloques ** 2).mean(axis=1) / 1073741824 + 1e-12)
        orden = np.sort(self.db)
        piso, voz = orden[len(orden) // 10], orden[int(len(orden) * 0.9)]
        self.umbral = float(max(piso + 8, voz - 26))
        self.fuerte = float(voz - 10)   # voz clara (no ruido de silla, respiración ni roce)
        self.dur = len(self.db) * HOP_S

    def nivel(self, t):
        i = int(round(t / HOP_S))
        return float(self.db[i]) if 0 <= i < len(self.db) else -120.0

    def tramo(self, a, b):
        i0, i1 = max(0, int(round(a / HOP_S))), min(len(self.db), int(round(b / HOP_S)) + 1)
        return self.db[i0:i1] if i1 > i0 else np.array([-120.0])

    def quieto(self, a, b):
        return bool((self.tramo(a, b) < self.umbral).all())

    def voz_activa(self, a, b):
        """Fracción del tramo con voz (sirve para cruzar con el movimiento de labios)."""
        return float((self.tramo(a, b) >= self.umbral).mean())

    def arranque_real(self, t0, t1):
        """Primera voz clara dentro de [t0, t1]; None si la palabra arranca de inmediato."""
        x = t0
        while x < t1:
            if all(self.nivel(x + k * HOP_S) >= self.fuerte for k in range(3)):
                return x if x - t0 > 0.3 else None
            x = round(x + HOP_S, 2)
        return None

    def inicio(self, t, limite):
        """Retrocede desde t hasta el silencio anterior (sin pasar 'limite')."""
        x = t
        while x - 0.06 >= limite:
            if self.quieto(x - 0.06, x):
                return x
            x -= HOP_S
        cands = [limite + i * HOP_S for i in range(int((t - limite) / HOP_S) + 1)]
        return min(cands, key=self.nivel) if cands else t

    def fin(self, t, limite):
        """Avanza desde t hasta el silencio siguiente (sin pasar 'limite')."""
        x = t
        while x + 0.08 <= limite:
            if self.quieto(x, x + 0.08):
                return x
            x += HOP_S
        cands = [t + i * HOP_S for i in range(int((limite - t) / HOP_S) + 1)]
        return min(cands, key=self.nivel) if cands else t

    def silencios(self, a, b, minimo):
        """Tramos de silencio de al menos 'minimo' segundos dentro de [a, b] (respiros de ≤40 ms no los parten)."""
        out, ini, t = [], None, a + 0.06
        while t < b - 0.08:
            n = self.nivel(t)
            blip = (ini is not None and n < self.fuerte
                    and any(self.nivel(t + k * HOP_S) < self.umbral for k in range(1, 5)))
            if n < self.umbral or blip:
                ini = t if ini is None else ini
            else:
                if ini is not None and t - ini >= minimo:
                    out.append((ini, t))
                ini = None
            t = round(t + HOP_S, 2)
        return out
