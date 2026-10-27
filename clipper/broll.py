"""B-roll: material propio de la marca primero (assets/broll/*.mp4|jpg|png) y, si no hay, videos verticales de
Pexels (licencia libre de uso comercial). Se descargan una vez y quedan en caché en la carpeta de datos.
Portado del motor v4 (reel.py, pexels_clip).
"""
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

from . import config

EXT_PROPIO = {".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png"}


def carpeta():
    d = config.datos_dir() / "broll" / "pexels"
    d.mkdir(parents=True, exist_ok=True)
    return d


def propio(marca, buscar, usados):
    """Archivo de la marca cuyo nombre contenga alguna palabra de la búsqueda (p. ej. assets/broll/render-plaza.png)."""
    d = Path(marca["_dir"]) / "assets" / "broll"
    if not d.exists():
        return None
    claves = [config.norm(p) for p in buscar.split() if len(p) > 3]
    for f in sorted(d.iterdir()):
        if f.suffix.lower() in EXT_PROPIO and str(f) not in usados and any(c in config.norm(f.stem) for c in claves):
            usados.add(str(f))
            return f
    return None


def candidatos(buscar):
    """Resultados de Pexels para 'buscar' (videos verticales), en caché."""
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return None
    cache_f = carpeta() / "busquedas.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
    if buscar not in cache or any("imagen" not in v for v in cache[buscar]):
        url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode(
            {"query": buscar, "orientation": "portrait", "size": "medium", "per_page": 12})
        cache[buscar] = [_resumen(v) for v in _api(url, key)["videos"]]
        cache_f.write_text(json.dumps(cache), encoding="utf-8")
    return cache[buscar]


def _api(url, key):
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "aztro-clipper"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def _resumen(v):
    return {"id": v["id"], "dur": v["duration"], "url": v["url"], "imagen": v.get("image"),
            "files": [{"w": f["width"], "h": f["height"], "link": f["link"]} for f in v["video_files"]
                      if f.get("width") and f.get("height") and f["height"] > f["width"]]}


def pexels(buscar, dur, usados, pexels_id=None):
    if pexels_id:  # el agente ya revisó la hoja de candidatos y fijó este video
        key = os.environ.get("PEXELS_API_KEY")
        if not key:
            return None
        v = _resumen(_api(f"https://api.pexels.com/videos/videos/{int(pexels_id)}", key))
        ops = [v] if v["files"] else []
    else:
        ops = candidatos(buscar) or []
        ops = [v for v in ops if v["files"] and v["dur"] >= dur + 0.5 and v["id"] not in usados] or \
              [v for v in ops if v["files"] and v["id"] not in usados]
    if not ops:
        return None
    v = ops[0]
    usados.add(v["id"])
    destino = carpeta() / f"{v['id']}.mp4"
    if not destino.exists():
        f = min(v["files"], key=lambda f: (f["h"] < 1280, abs(f["h"] - 1920)))
        tmp = destino.with_suffix(".part")
        req = urllib.request.Request(f["link"], headers={"User-Agent": "Mozilla/5.0 (aztro-clipper)"})
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as out:
            out.write(r.read())
        tmp.replace(destino)
    return destino


def conseguir(marca, buscar, dur, usados, pexels_id=None):
    """Ruta local de un B-roll para 'buscar' (propio de la marca o Pexels); None si no hay."""
    if pexels_id:
        return pexels(buscar, dur, usados, pexels_id)
    return propio(marca, buscar, usados) or pexels(buscar, dur, usados)


def hoja_candidatos(seleccion, destino, por_busqueda=5):
    """Hoja de contacto con los primeros resultados de Pexels de cada B-roll pedido, con su id, para que el agente
    elija el que de verdad ilustra la frase (y fije "pexels_id") o lo quite. Devuelve las filas escritas."""
    import cv2
    import numpy as np
    filas, alto, ancho = [], 300, 170
    for c in seleccion["clips"]:
        for b in c.get("broll", []):
            vids = (candidatos(b["buscar"]) or [])[:por_busqueda]
            celdas = []
            for v in vids:
                img = None
                if v.get("imagen"):
                    try:
                        raw = urllib.request.urlopen(urllib.request.Request(
                            v["imagen"], headers={"User-Agent": "Mozilla/5.0 (aztro-clipper)"}), timeout=20).read()
                        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
                    except OSError:
                        img = None
                img = cv2.resize(img, (ancho, alto)) if img is not None else np.zeros((alto, ancho, 3), np.uint8)
                cv2.rectangle(img, (0, alto - 28), (ancho, alto), (20, 20, 20), -1)
                cv2.putText(img, str(v["id"]), (6, alto - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
                celdas.append(img)
            etiqueta = np.full((alto, 330, 3), 245, np.uint8)
            for k, linea in enumerate([f"clip {c['id']}", f"palabra: {b.get('palabra', '')}", b["buscar"][:34],
                                       b["buscar"][34:68], f"fijado: {b.get('pexels_id', '-')}"]):
                cv2.putText(etiqueta, linea, (10, 40 + k * 44), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 30, 30), 1)
            celdas += [np.zeros((alto, ancho, 3), np.uint8)] * (por_busqueda - len(celdas))
            filas.append(np.hstack([etiqueta] + celdas))
    if filas:
        cv2.imwrite(str(destino), np.vstack(filas), [cv2.IMWRITE_JPEG_QUALITY, 80])
    return len(filas)
