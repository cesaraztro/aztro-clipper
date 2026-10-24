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


def pexels(buscar, dur, usados):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return None
    cache_f = carpeta() / "busquedas.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
    if buscar not in cache:
        url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode(
            {"query": buscar, "orientation": "portrait", "size": "medium", "per_page": 12})
        req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "aztro-clipper"})
        vids = json.loads(urllib.request.urlopen(req, timeout=20).read())["videos"]
        cache[buscar] = [{"id": v["id"], "dur": v["duration"], "url": v["url"],
                          "files": [{"w": f["width"], "h": f["height"], "link": f["link"]} for f in v["video_files"]
                                    if f.get("width") and f.get("height") and f["height"] > f["width"]]} for v in vids]
        cache_f.write_text(json.dumps(cache), encoding="utf-8")
    ops = [v for v in cache[buscar] if v["files"] and v["dur"] >= dur + 0.5 and v["id"] not in usados]
    ops = ops or [v for v in cache[buscar] if v["files"] and v["id"] not in usados]
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


def conseguir(marca, buscar, dur, usados):
    """Ruta local de un B-roll para 'buscar' (propio de la marca o Pexels); None si no hay."""
    return propio(marca, buscar, usados) or pexels(buscar, dur, usados)
