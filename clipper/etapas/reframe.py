"""Etapa 8: encuadre vertical 9:16 que sigue a quien habla.

Por cada clip se leen solo sus tramos del video original (a baja resolución), se detectan las caras, se agrupan
por persona y se mide el movimiento de la boca de cada una mientras hay voz. La persona con más movimiento de
labios es quien habla; la cámara virtual la encuadra y corta en seco cuando cambia el turno.
Detector de caras: YuNet de OpenCV Zoo (MIT), 230 KB, se descarga una vez. Sin modelos de hablante activo de
terceros: la decisión sale del movimiento de labios + la energía de la voz.
"""
import itertools
import subprocess
import urllib.request

import cv2
import numpy as np

from .. import config, media
from ..config import FPS, H, W
from ..energia import Energia
from .ingest import resolver

ANCHO_ANALISIS = 360
FPS_ANALISIS = 8


YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"


def modelo_yunet():
    destino = config.datos_dir() / "modelos" / "face_detection_yunet_2023mar.onnx"
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        print("  descargando detector de caras YuNet (OpenCV Zoo, 230 KB)…")
        urllib.request.urlretrieve(YUNET_URL, destino)
    return destino


def _cascadas():
    return cv2.FaceDetectorYN.create(str(modelo_yunet()), "", (320, 320), 0.45, 0.3, 50)  # 0.45: también perfiles


# Modo escenario (conferencia, clase, live con público): una sola voz, muchas caras y un video ya editado con varias
# cámaras. El presentador suele estar de perfil o de espaldas, así que se busca a la PERSONA (cuerpo), no la cara:
# es la más alta en cuadro (de pie y más cerca de la cámara). Detector: YOLOX-S de OpenCV Zoo (Apache-2.0), 36 MB.
YOLOX_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/object_detection_yolox/object_detection_yolox_2022nov.onnx"
CADA_CUERPO = 4  # cuerpos cada 4 cuadros de análisis (2 por segundo)


def modelo_yolox():
    destino = config.datos_dir() / "modelos" / "object_detection_yolox_2022nov.onnx"
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        print("  descargando detector de personas YOLOX (OpenCV Zoo, 36 MB)…")
        tmp = destino.with_suffix(".part")
        urllib.request.urlretrieve(YOLOX_URL, tmp)
        tmp.replace(destino)
    return destino


class DetectorPersonas:
    def __init__(self):
        self.net = cv2.dnn.readNet(str(modelo_yolox()))
        g, s = [], []
        for st in (8, 16, 32):
            n = 640 // st
            yv, xv = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
            g.append(np.stack((xv, yv), 2).reshape(-1, 2))
            s.append(np.full((n * n, 1), st))
        self.grid, self.paso = np.concatenate(g).astype(np.float32), np.concatenate(s).astype(np.float32)

    def detectar(self, gris):
        """Personas (x, y, w, h) en coordenadas del cuadro de análisis."""
        h, w = gris.shape
        r = min(640 / h, 640 / w)
        lienzo = np.full((640, 640, 3), 114, np.uint8)
        lienzo[:int(h * r), :int(w * r)] = cv2.resize(cv2.cvtColor(gris, cv2.COLOR_GRAY2BGR), (int(w * r), int(h * r)))
        self.net.setInput(cv2.dnn.blobFromImage(lienzo))
        o = self.net.forward()[0]
        xy, wh = (o[:, :2] + self.grid) * self.paso / r, np.exp(o[:, 2:4]) * self.paso / r
        score = o[:, 4] * o[:, 5]  # clase 0 de COCO = persona
        m = score > 0.35
        cajas = [[float(x - a / 2), float(y - b / 2), float(a), float(b)] for (x, y), (a, b) in zip(xy[m], wh[m])]
        keep = cv2.dnn.NMSBoxes(cajas, score[m].tolist(), 0.35, 0.45) if cajas else []
        return [cajas[i] for i in np.array(keep).flatten()]


def cortes_de_camara(cuadros):
    """Índices de cuadro donde el video original cambia de toma (edición multicámara)."""
    if len(cuadros) < 2:
        return []
    chicos = np.array([cv2.resize(g, (64, 36), interpolation=cv2.INTER_AREA) for g in cuadros]).astype(np.int16)
    dif = np.abs(np.diff(chicos, axis=0)).mean(axis=(1, 2))
    return [i + 1 for i, d in enumerate(dif) if d > 22]


def seguir_presentador(cuadros, detector, cortes):
    """{cuadro: (cx, arriba, alto)} del presentador: la persona más alta, con continuidad dentro de cada toma."""
    out, prev, cortes = {}, None, set(cortes)
    for i in range(0, len(cuadros), CADA_CUERPO):
        if any(c in cortes for c in range(i - CADA_CUERPO + 1, i + 1)):
            prev = None  # toma nueva: se vuelve a elegir sin arrastrar la anterior
        cajas = detector.detectar(cuadros[i])
        if not cajas:
            continue
        alto_max = max(c[3] for c in cajas)
        candidatas = [c for c in cajas if c[3] >= 0.7 * alto_max]
        if prev is not None:
            elegida = min(candidatas, key=lambda c: abs(c[0] + c[2] / 2 - prev))
        else:
            elegida = max(candidatas, key=lambda c: c[3])
        if elegida[3] < 0.25 * cuadros.shape[1]:
            continue  # nadie de pie en cuadro (plano del público o de la pantalla)
        prev = elegida[0] + elegida[2] / 2
        out[i] = (prev, elegida[1], elegida[3])
    return out


def camara_escenario(muestras, cortes, i0, i1, info, mj, escala, extra=1.0):
    """Recorte 9:16 que sigue al presentador (cuerpo) con paneo suave y salto seco en cada cambio de toma."""
    sw, sh = info["w"], info["h"]
    bw, bh = (sh * 9 / 16, sh) if sw / sh > 9 / 16 else (sw, sw * 16 / 9)
    ks = sorted(k for k in muestras if i0 - 2 <= k <= i1 + 2)
    if not ks:  # sin muestra en el tramo: la más cercana dentro de 1 s
        cerca = [k for k in muestras if abs(k - (i0 + i1) / 2) <= FPS_ANALISIS]
        ks = [min(cerca, key=lambda k: abs(k - (i0 + i1) / 2))] if cerca else []
    if not ks:
        return None
    # zoom moderado: el cuerpo ocupa ~80 % del alto y nunca más de 1.4x (un video editado ya trae sus planos cerrados)
    zmax = min(mj["zoom_max"], mj.get("zoom_escenario", 1.4), max(1.0, sw / (W * 0.55)))
    # el plano más abierto del tramo manda (si cambia de toma a la mitad, nadie queda cortado)
    z = min(float(np.clip(bh * 0.8 / (muestras[k][2] * escala), 1.0, zmax)) for k in ks)
    arribas = [muestras[k][1] * escala for k in ks]
    if min(arribas) < 0.05 * sh:
        z = 1.0  # la cabeza ya toca el borde del plano original: acercar la cortaría
    else:
        z = min(z * extra, zmax)
    cw, ch = bw / z, bh / z
    arriba = float(np.median(arribas))
    y = float(np.clip(arriba - 0.08 * ch, 0, sh - ch))
    xs = [float(np.clip(muestras[k][0] * escala - cw / 2, 0, sw - cw)) for k in ks]
    x = float(np.median(xs))
    cam = {"x": round(x), "y": round(y), "w": int(cw) // 2 * 2, "h": int(ch) // 2 * 2, "z": round(z, 3),
           "fx": 0.5, "fy": 0.2,
           # cabeza ≈ el 22 % superior de la caja de la persona; unión de todas las muestras del tramo
           "cabeza": _en_salida(min(arribas), max(muestras[k][1] * escala + 0.22 * muestras[k][2] * escala for k in ks), y, ch)}
    if len(ks) >= 2 and max(xs) - min(xs) > 0.04 * sw:
        keys = []
        for (ka, xa), (kb, xb) in zip(zip(ks, xs), zip(ks[1:], xs[1:])):
            keys.append([round((ka - i0) / FPS_ANALISIS, 2), round(xa)])
            corte = next((c for c in sorted(cortes) if ka < c <= kb), None)
            if corte is not None:  # cambio de toma: salto seco, no paneo
                t = (corte - i0) / FPS_ANALISIS
                keys += [[round(t - 0.02, 2), round(xa)], [round(t, 2), round(xb)]]
        keys.append([round((ks[-1] - i0) / FPS_ANALISIS, 2), round(xs[-1])])
        cam["x_keys"] = keys
    return cam


def leer_cuadros(ruta, t0, dur, info):
    """Cuadros en gris (ANCHO_ANALISIS de ancho) del tramo [t0, t0+dur] del archivo original."""
    alto = int(round(ANCHO_ANALISIS * info["h"] / info["w"] / 2)) * 2
    cmd = [media.ffmpeg_bin(), "-v", "error", *media.hwaccel(), "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", str(ruta),
           "-vf", f"fps={FPS_ANALISIS},scale={ANCHO_ANALISIS}:{alto},format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (ANCHO_ANALISIS * alto)
    return np.frombuffer(raw[: n * ANCHO_ANALISIS * alto], np.uint8).reshape(n, alto, ANCHO_ANALISIS), alto


def detectar(cuadros, detector):
    dets = []
    if not len(cuadros):
        return dets
    detector.setInputSize((cuadros.shape[2], cuadros.shape[1]))
    for i, g in enumerate(cuadros):
        if i % 2:  # caras cada 2 cuadros (4 por segundo) es suficiente para un set estático
            continue
        _, caras = detector.detect(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR))
        for (x, y, w, h, *_resto) in (caras if caras is not None else []):
            dets.append((i, x + w / 2, y + h / 2, w, h))
    return dets


def agrupar_personas(dets, n_cuadros, ancho):
    """Agrupa detecciones por posición horizontal (las personas en un set no cambian de silla)."""
    if not dets:
        return []
    xs = sorted(dets, key=lambda d: d[1])
    grupos, cur = [], [xs[0]]
    for d in xs[1:]:
        if d[1] - cur[-1][1] > 0.10 * ancho:
            grupos.append(cur); cur = []
        cur.append(d)
    grupos.append(cur)
    muestras = max(1, n_cuadros // 2)
    personas = []
    for g in grupos:
        cuadros_con = len({d[0] for d in g})
        if cuadros_con < 0.15 * muestras:
            continue  # falsos positivos sueltos (pósters, pantallas)
        arr = np.array([d[1:] for d in g])
        cx, cy, w, h = np.median(arr, axis=0)
        personas.append({"cx": float(cx), "cy": float(cy), "w": float(w), "h": float(h), "soporte": cuadros_con / muestras})
    # una "persona" con caras muy chicas comparada con las demás suele ser un póster o una foto
    if personas:
        hmax = max(p["h"] for p in personas)
        personas = [p for p in personas if p["h"] > 0.45 * hmax]
    return sorted(personas, key=lambda p: p["cx"])


def actividad_boca(cuadros, personas):
    """Movimiento de la boca menos movimiento de la frente (descuenta que la persona mueva la cabeza)."""
    out = np.zeros((len(cuadros), len(personas)))
    for k, p in enumerate(personas):
        x0, x1 = int(p["cx"] - p["w"] * 0.35), int(p["cx"] + p["w"] * 0.35)
        boca = (int(p["cy"] + p["h"] * 0.12), int(p["cy"] + p["h"] * 0.55))
        frente = (int(p["cy"] - p["h"] * 0.45), int(p["cy"] - p["h"] * 0.15))
        alto = cuadros.shape[1]
        x0, x1 = max(0, x0), min(cuadros.shape[2], x1)
        for i in range(1, len(cuadros)):
            a = cuadros[i, max(0, boca[0]):min(alto, boca[1]), x0:x1].astype(np.int16)
            b = cuadros[i - 1, max(0, boca[0]):min(alto, boca[1]), x0:x1].astype(np.int16)
            fa = cuadros[i, max(0, frente[0]):min(alto, frente[1]), x0:x1].astype(np.int16)
            fb = cuadros[i - 1, max(0, frente[0]):min(alto, frente[1]), x0:x1].astype(np.int16)
            if a.size and fa.size:
                out[i, k] = max(0.0, np.abs(a - b).mean() - 0.7 * np.abs(fa - fb).mean())
    return out


def seguir(persona, personas, dets, i0, i1):
    """Dónde está la persona en este tramo (puede caminar). Devuelve la persona con su posición en el tramo y
    'ruta': [(cuadro, cx)] para un paneo suave. Sin caras en el tramo, usa la detección más cercana en el tiempo."""
    def suyas(a, b):
        out = []
        for (i, cx, cy, w, h) in dets:
            if a <= i <= b:
                mas_cercana = min(personas, key=lambda p: abs(p["cx"] - cx) + abs(p["h"] - h))
                if mas_cercana is persona or len(personas) == 1:
                    out.append((i, cx, cy, h))
        return out
    cerca = suyas(i0 - 4, i1 + 4)
    if not cerca:  # sin cara en este tramo (de espaldas, de perfil, fuera de cuadro): plano abierto, nunca a ciegas
        return dict(persona, perdida=True)
    arr = np.array(cerca)
    # ruta: mediana de la posición por medio segundo (4 cuadros de análisis)
    ruta = []
    for k in range(int(i0), int(i1) + 1, 4):
        v = arr[(arr[:, 0] >= k - 2) & (arr[:, 0] <= k + 6)]
        if len(v):
            ruta.append((float(k - i0), float(np.median(v[:, 1]))))
    return dict(persona, cx=float(np.median(arr[:, 1])), cy=float(np.median(arr[:, 2])), h=float(np.median(arr[:, 3])),
                ruta=ruta)


def _en_salida(src0, src1, y, ch):
    """Franja vertical del original [src0, src1] en píxeles del video final (0–1920), con margen para punch-ins."""
    a, b = (src0 - y) / ch * H, (src1 - y) / ch * H
    m = 0.06 * (b - a) + 20
    return [int(max(0, a - m)), int(min(H, b + m))]


def camara_para(persona, info, mj, escala, extra=1.0):
    """Recorte 9:16 en píxeles del original con la cara a la altura y tamaño de la marca ('extra' = más cerrado)."""
    sw, sh = info["w"], info["h"]
    bw, bh = (sh * 9 / 16, sh) if sw / sh > 9 / 16 else (sw, sw * 16 / 9)
    if persona is None or persona.get("perdida"):
        z, cx, cy = 1.0, sw / 2, sh / 2
    else:
        cara_h = persona["h"] * escala
        # zoom limitado por la resolución: el recorte nunca baja de ~55% del ancho final (evita imagen suave)
        zmax = min(mj["zoom_max"] * extra, max(1.0, sw / (W * 0.55)))
        z = float(np.clip(mj["cara_objetivo"] * bh / max(cara_h, 1) * extra, 1.0, zmax))
        cx, cy = persona["cx"] * escala, persona["cy"] * escala
    cw, ch = bw / z, bh / z
    x = float(np.clip(cx - cw / 2, 0, sw - cw))
    y = float(np.clip(cy - mj["cara_altura"] * ch, 0, sh - ch)) if (persona and not persona.get("perdida")) else (sh - ch) / 2
    cam = {"x": round(x), "y": round(y), "w": int(cw) // 2 * 2, "h": int(ch) // 2 * 2, "z": round(z, 3),
           "fx": round((cx - x) / cw, 4), "fy": round((cy - y) / ch, 4)}
    if persona is not None and not persona.get("perdida"):
        cam["cabeza"] = _en_salida(cy - 0.7 * cara_h, cy + 0.8 * cara_h, y, ch)
    ruta = (persona or {}).get("ruta") or []
    if len(ruta) >= 2:
        xs = [float(np.clip(c * escala - cw / 2, 0, sw - cw)) for _, c in ruta]
        xs = np.convolve(np.pad(xs, 1, mode="edge"), np.ones(3) / 3, mode="valid")  # suaviza el paneo
        if max(xs) - min(xs) > 0.04 * sw:  # solo si de verdad se movió
            cam["x_keys"] = [[round(k / FPS_ANALISIS, 2), round(float(v))] for (k, _), v in zip(ruta, xs)]
    return cam


def correr(ep, solo=None):
    from . import diarize
    en = Energia(ep.ruta("00_ingest", "voz16k.wav"))
    diar = diarize.correr(ep)
    detector = _cascadas()
    cuerpos = None
    mj = ep.marca["montaje"]
    un_hablante = int(ep.meta.get("hablantes") or 1) == 1
    # 1) análisis por clip: caras, movimiento de boca y voz de cada tramo
    analisis = []
    for cp in ep.clips():
        clip = config.leer(cp)
        if solo and clip["id"] not in solo:
            continue
        piezas = clip["piezas"]
        f, local = resolver(ep.meta, piezas[0]["s0"])
        info = f["info"]
        t_a, t_b = piezas[0]["s0"], piezas[-1]["s1"]
        cuadros, _ = leer_cuadros(f["ruta"], local, t_b - t_a, info)
        dets = detectar(cuadros, detector)
        personas = agrupar_personas(dets, len(cuadros), ANCHO_ANALISIS)
        clip["_dets"] = dets
        # una sola voz y varias caras por cuadro (público) = conferencia: se sigue el cuerpo del presentador
        caras_por_cuadro = len(dets) / max(1, (len(cuadros) + 1) // 2)
        if ep.meta.get("encuadre") == "escenario" or (un_hablante and caras_por_cuadro >= 2.0 and ep.meta.get("encuadre") != "caras"):
            cuerpos = cuerpos or DetectorPersonas()
            cortes = cortes_de_camara(cuadros)
            clip["_esc"] = (seguir_presentador(cuadros, cuerpos, cortes), cortes)
            analisis.append((cp, clip, info, [], cuadros[len(cuadros) // 2] if len(cuadros) else None, t_a))
            continue
        act = actividad_boca(cuadros, personas) if len(personas) > 1 else None
        for pz in piezas:
            pz["_voz"] = diarize.voces_en(diar, pz["s0"], pz["s1"]) if diar["k"] > 1 else np.ones(1)
            if act is not None:
                i0 = int((pz["s0"] - t_a) * FPS_ANALISIS)
                i1 = min(len(act), max(i0 + 1, int((pz["s1"] - t_a) * FPS_ANALISIS)))
                pesos = np.array([en.voz_activa(t_a + i / FPS_ANALISIS, t_a + (i + 1) / FPS_ANALISIS) for i in range(i0, i1)])
                pz["_boca"] = (act[i0:i1] * pesos[:, None]).sum(axis=0) if len(pesos) else np.zeros(len(personas))
        analisis.append((cp, clip, info, personas, cuadros[len(cuadros) // 2] if len(cuadros) else None, t_a))
    # 2) qué voz es qué cara: se cruza la voz de cada tramo con el movimiento de boca, sumando todo el episodio
    k_voz = diar["k"]
    n_caras = max((len(a[3]) for a in analisis), default=0)
    mapa = {0: 0} if n_caras else {}
    if k_voz > 1 and n_caras > 1:
        C = np.zeros((k_voz, n_caras))
        for _, clip, _, personas, _, _ in analisis:
            for pz in clip["piezas"]:
                if "_boca" in pz and pz["_voz"].sum() > 0 and pz["_boca"].sum() > 0:
                    b = np.zeros(n_caras); b[:len(pz["_boca"])] = pz["_boca"] / pz["_boca"].sum()
                    C += np.outer(pz["_voz"] / pz["_voz"].sum(), b)
        perms = itertools.permutations(range(n_caras), min(k_voz, n_caras))
        mejor = max(perms, key=lambda pm: sum(C[l, c] for l, c in enumerate(pm)))
        mapa = {l: c for l, c in enumerate(mejor)}
        print("  voces → caras: " + ", ".join(f"voz {l + 1} = persona {c + 1}" for l, c in mapa.items()))
    elif k_voz == 1 and n_caras > 1:
        # un solo hablante pero más caras en cuadro (público, póster, alguien detrás): se sigue a quien mueve la boca
        total = np.zeros(n_caras)
        for _, clip, _, personas, _, _ in analisis:
            for pz in clip["piezas"]:
                if "_boca" in pz:
                    total[:len(pz["_boca"])] += pz["_boca"]
        mapa = {0: int(np.argmax(total))}
        print(f"  un hablante: persona {mapa[0] + 1} de {n_caras} caras en cuadro")
    # 3) cámara por tramo
    for cp, clip, info, personas, cuadro, t_a in analisis:
        piezas = clip["piezas"]
        escala = info["w"] / ANCHO_ANALISIS
        if "_esc" in clip:
            _camaras_escenario(cp, clip, info, mj, escala, t_a, cuadro)
            continue
        # quién habla: la voz manda; donde no hay evidencia (tramos de medio segundo) se hereda del vecino
        for pz in piezas:
            voz, boca = pz.pop("_voz"), pz.pop("_boca", None)
            if not personas:
                pz["hablante"] = None
            elif len(personas) == 1:
                pz["hablante"] = 0
            elif voz.sum() > 0.2 and voz.max() >= 0.6 * voz.sum() and int(np.argmax(voz)) in mapa:
                pz["hablante"] = mapa[int(np.argmax(voz))]
                pz["confianza"] = round(float(voz.max() / voz.sum()), 2)
            else:
                pz["hablante"] = -1
        for orden in (piezas, piezas[::-1]):
            prev = None
            for pz in orden:
                if pz["hablante"] == -1 and prev is not None:
                    pz["hablante"] = prev
                if pz["hablante"] not in (-1, None):
                    prev = pz["hablante"]
        for pz in piezas:
            if pz["hablante"] == -1:
                pz["hablante"] = 0
        # tomas: el encuadre alterna (abierto / cerrado) cada ~3 s o al cambiar de hablante, no en cada micro-corte
        toma, inicio_toma, cerrado = 0, 0.0, False
        for k, pz in enumerate(piezas):
            cambio = k > 0 and piezas[k - 1].get("hablante") != pz.get("hablante")
            if k > 0 and (cambio or pz["o0"] - inicio_toma >= 3.0):
                toma += 1
                inicio_toma = pz["o0"]
                cerrado = False if cambio else not cerrado
            persona = personas[pz["hablante"]] if pz.get("hablante") is not None else None
            if persona is not None:  # la cámara sigue dónde está la persona EN ESTE tramo (puede caminar)
                persona = seguir(persona, personas, clip["_dets"], (pz["s0"] - t_a) * FPS_ANALISIS,
                                 (pz["s1"] - t_a) * FPS_ANALISIS)
            pz["camara"] = camara_para(persona, info, mj, escala, mj["alterno"] if cerrado else 1.0)
            pz["toma"] = toma
            pz["modo"] = "TRACK" if persona is not None else "GENERAL"
        clip.pop("_dets", None)
        clip["personas"] = [{k: round(v * escala, 1) if k != "soporte" else round(v, 2) for k, v in p.items()} for p in personas]
        config.escribir(cp, clip)
        if cuadro is not None:
            _vista(cuadro[None], personas, piezas, t_a, escala, cp.parent / "reframe.jpg")
        cambios = sum(1 for a, b in zip(piezas, piezas[1:]) if a.get("hablante") != b.get("hablante"))
        hablan = sorted({p["hablante"] + 1 for p in piezas if p.get("hablante") is not None})
        print(f"  clip {clip['id']}: {len(personas)} persona(s) · habla persona {hablan} · {cambios} cambios · zoom {piezas[0]['camara']['z']}x")


def _camaras_escenario(cp, clip, info, mj, escala, t_a, cuadro):
    muestras, cortes = clip.pop("_esc")
    clip.pop("_dets", None)
    piezas = clip["piezas"]
    toma, inicio_toma, cerrado, abiertos = 0, 0.0, False, 0
    for k, pz in enumerate(piezas):
        if k > 0 and pz["o0"] - inicio_toma >= 3.0:
            toma, inicio_toma, cerrado = toma + 1, pz["o0"], not cerrado
        i0, i1 = (pz["s0"] - t_a) * FPS_ANALISIS, (pz["s1"] - t_a) * FPS_ANALISIS
        cam = camara_escenario(muestras, cortes, i0, i1, info, mj, escala, mj["alterno"] if cerrado else 1.0)
        pz["hablante"] = 0
        pz["toma"] = toma
        if cam is None:  # nadie de pie en cuadro: el plano completo con fondo desenfocado
            pz["camara"], pz["modo"] = camara_para(None, info, mj, escala), "GENERAL"
            abiertos += 1
        else:
            pz["camara"], pz["modo"] = cam, "ESCENARIO"
    clip["personas"] = []
    config.escribir(cp, clip)
    if cuadro is not None:
        img = cv2.cvtColor(cuadro, cv2.COLOR_GRAY2BGR)
        k = min(muestras, key=lambda k: abs(k - len(muestras) * CADA_CUERPO / 2), default=None)
        if k is not None:
            cx, arriba, alto = muestras[k]
            cv2.rectangle(img, (int(cx - alto * 0.25), int(arriba)), (int(cx + alto * 0.25), int(arriba + alto)), (80, 200, 255), 2)
        cam = next((p["camara"] for p in piezas if p["modo"] == "ESCENARIO"), None)
        if cam:
            cv2.rectangle(img, (int(cam["x"] / escala), int(cam["y"] / escala)),
                          (int((cam["x"] + cam["w"]) / escala), int((cam["y"] + cam["h"]) / escala)), (120, 255, 120), 1)
        cv2.imwrite(str(cp.parent / "reframe.jpg"), img)
    print(f"  clip {clip['id']}: escenario · presentador en {len(muestras)} muestras · {len(cortes)} cambios de toma · "
          f"{abiertos} tramos en plano completo · zoom {piezas[0]['camara']['z']}x")


def _vista(cuadros, personas, piezas, t_a, escala, destino):
    """Imagen de control: cuadro del clip con las caras detectadas y el recorte vertical de cada hablante."""
    if not len(cuadros):
        return
    img = cv2.cvtColor(cuadros[len(cuadros) // 2], cv2.COLOR_GRAY2BGR)
    colores = [(80, 200, 255), (120, 255, 120), (255, 160, 80)]
    for k, p in enumerate(personas):
        c = colores[k % 3]
        cv2.rectangle(img, (int(p["cx"] - p["w"] / 2), int(p["cy"] - p["h"] / 2)),
                      (int(p["cx"] + p["w"] / 2), int(p["cy"] + p["h"] / 2)), c, 2)
        pz = next((z for z in piezas if z.get("hablante") == k), None)
        if pz:
            cam = pz["camara"]
            cv2.rectangle(img, (int(cam["x"] / escala), int(cam["y"] / escala)),
                          (int((cam["x"] + cam["w"]) / escala), int((cam["y"] + cam["h"]) / escala)), c, 1)
        cv2.putText(img, f"P{k + 1}", (int(p["cx"] - 10), int(p["cy"] - p["h"] / 2 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1)
    cv2.imwrite(str(destino), img)
