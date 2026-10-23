"""Rutas, marcas y lectura/escritura de artefactos del episodio."""
import copy
import json
import os
import re
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MARCAS = REPO / "marcas"
FUENTES = REPO / "recursos" / "fuentes"

FPS, W, H = 30, 1080, 1920

# Valores por defecto de toda marca; marca.json solo sobrescribe lo que cambia.
MARCA_BASE = {
    "id": "plantilla",
    "nombre": "Mi marca",
    "idioma": "es",
    "zona_horaria": "America/Mexico_City",
    "vocabulario": [],
    "correcciones": {},
    "colores": {"texto": "#FFFFFF", "caja": "#0A1A33", "enfasis": "#D9B26A", "acento": "#A5C8FF"},
    "fuentes": {"subtitulos": "Poppins SemiBold", "titulo": "Poppins ExtraBold"},
    "seleccion": {"duracion": [25, 75], "clips_por_hora": [10, 15]},
    "montaje": {
        "velocidad": 1.12, "velocidad_conversacion": 1.06,
        "gap_corte": 0.30, "silencio_min": 0.14, "silencio_pad": 0.04,
        "punch": 0.08, "punch_max": 12, "punch_sep": 1.8, "intervalo_visual_max": 4.0,
        "alterno": 1.12, "cara_objetivo": 0.20, "cara_altura": 0.38, "zoom_max": 2.2,
    },
    "subtitulos": {"tam": 78, "y": 1430, "max_palabras": 4, "max_chars": 24, "caja_alfa": 40, "relleno": 16},
    "gancho": {"dur": 2.8, "tam": 88, "y": 280},
    "color": {"lut": None, "vineta": 0.35},
    "audio": {"lufs": -14.0, "musica": None, "musica_volumen": 0.16},
    "cta": {
        "instagram": "Comenta {PALABRA} y te mando el video completo",
        "facebook": "Comenta {PALABRA} y te mando el video completo",
        "tiktok": "Escríbeme {PALABRA} por DM y te lo mando",
        "youtube": "Video completo en la descripción",
        "overlay": "Comenta {PALABRA}",
        "dur": 3.2,
    },
    "hashtags": [],
    "publicacion": {"redes": ["instagram", "tiktok", "youtube", "facebook"], "borrador": True,
                    "max_por_dia": 2, "separacion_horas": 4, "horarios": ["12:30", "19:30"]},
}


def datos_dir():
    d = os.environ.get("CLIPPER_DATA")
    return Path(d).expanduser() if d else Path.home() / "AztroClipper"


def episodios_dir():
    return datos_dir() / "episodios"


def _fusionar(base, extra):
    out = copy.deepcopy(base)
    for k, v in extra.items():
        out[k] = _fusionar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def cargar_marca(marca_id):
    d = MARCAS / marca_id
    f = d / "marca.json"
    if not f.exists():
        disponibles = sorted(p.name for p in MARCAS.iterdir() if (p / "marca.json").exists())
        raise SystemExit(f"No existe la marca '{marca_id}'. Disponibles: {', '.join(disponibles)}")
    m = _fusionar(MARCA_BASE, json.loads(f.read_text()))
    m["_dir"] = str(d)
    return m


def recurso_marca(marca, rel):
    """Resuelve una ruta de asset de la marca (relativa a su carpeta)."""
    if not rel:
        return None
    p = Path(marca["_dir"]) / rel
    return p if p.exists() else None


def slugify(s, n=40):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n] or "clip"


def norm(s):
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s)


def leer(p):
    return json.loads(Path(p).read_text())


def escribir(p, data):
    """Escritura atómica: nunca deja un JSON a medias si el proceso se corta."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(p)
    return p


class Episodio:
    """Carpeta de trabajo de un episodio: un artefacto JSON por etapa."""

    def __init__(self, ref):
        p = Path(ref).expanduser()
        if not p.is_absolute() and not p.exists():
            p = episodios_dir() / ref
        if not (p / "episodio.json").exists():
            raise SystemExit(f"No encuentro el episodio '{ref}' (busqué en {p}). Créalo con: clipper ingest <video> --marca <marca>")
        self.dir = p.resolve()
        self.meta = leer(p / "episodio.json")
        self.marca = cargar_marca(self.meta["marca"])

    def ruta(self, *partes):
        return self.dir.joinpath(*partes)

    def guardar_meta(self):
        escribir(self.ruta("episodio.json"), self.meta)

    def clips(self):
        return sorted(p for p in self.ruta("clips").glob("*/clip.json"))
