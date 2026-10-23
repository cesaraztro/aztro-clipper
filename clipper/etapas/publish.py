"""Etapa 12: aprobación y calendario de publicación para Metricool.

Este comando NO publica. Arma `calendario.json` con un post por red y clip (texto, primer comentario, título de
YouTube, privacidad, portada), repartido en la semana. El agente lo lleva a Metricool con su MCP oficial
(createScheduledPost, draft=true) solo después del OK humano. Nada sale sin aprobación.
"""
import datetime
import hashlib
import json

from .. import config


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def aprobar(ep, clips, quien="humano"):
    ap_p = ep.ruta("aprobacion.json")
    ap = config.leer(ap_p) if ap_p.exists() else {}
    for d in sorted(ep.ruta("entregables").iterdir()):
        cid = d.name.split("_")[0]
        if clips and cid not in clips:
            continue
        cp = config.leer(d / "copy.json")
        if not cp.get("qa_ok"):
            print(f"  clip {cid}: no se aprueba, el control de calidad no pasó")
            continue
        ap[cid] = {"carpeta": d.name, "sha256": {v.name: sha256(v) for v in sorted(d.glob("video_*.mp4"))},
                   "aprobado_por": quien, "fecha": datetime.datetime.now().isoformat(timespec="seconds")}
        print(f"  clip {cid}: aprobado")
    config.escribir(ap_p, ap)


def correr(ep, inicio=None, mejores_horas=None):
    ap_p = ep.ruta("aprobacion.json")
    if not ap_p.exists():
        raise SystemExit("No hay clips aprobados. Revisa la hoja de contacto y corre: clipper approve <episodio> --clips 01 02 …")
    ap = config.leer(ap_p)
    m = ep.marca
    pub = m["publicacion"]
    horas = json.loads(open(mejores_horas).read()) if mejores_horas else {}
    dia = datetime.date.fromisoformat(inicio) if inicio else datetime.date.today() + datetime.timedelta(days=1)
    clips = []
    for cid, a in sorted(ap.items()):
        d = ep.ruta("entregables", a["carpeta"])
        for v in d.glob("video_*.mp4"):
            if sha256(v) != a["sha256"].get(v.name):
                raise SystemExit(f"El clip {cid} cambió después de aprobarse ({v.name}). Vuelve a aprobarlo.")
        clips.append((cid, d, config.leer(d / "copy.json")))
    clips.sort(key=lambda x: -(x[2].get("viral_score") or 0))
    posts, slot = [], 0
    for cid, d, cp in clips:
        fecha = dia + datetime.timedelta(days=slot // pub["max_por_dia"])
        hora_def = pub["horarios"][slot % len(pub["horarios"])]
        slot += 1
        for red in pub["redes"]:
            hora = horas.get(red, {}).get(fecha.strftime("%A").lower(), hora_def) if horas else hora_def
            post = {"clip": cid, "red": red, "fecha": f"{fecha}T{hora}:00", "zona_horaria": m["zona_horaria"],
                    "video": str(d / f"video_{red}.mp4"), "texto": cp[red]["texto"], "borrador": pub["borrador"],
                    "portada_ms": cp.get("portada_ms", 1200)}
            if red == "youtube":
                post.update(titulo=cp["youtube"]["titulo"], tipo="short", privacidad="public", para_ninos=False,
                            primer_comentario=cp["youtube"].get("primer_comentario"))
            if red == "instagram":
                post.update(tipo="REEL", mostrar_en_feed=True)
            if red == "facebook":
                post.update(tipo="REEL")
            if red == "tiktok":
                post.update(privacidad="PUBLIC_TO_EVERYONE")
            posts.append(post)
    cal = {"episodio": ep.meta["slug"], "marca": m["id"], "palabra_cta": ep.meta.get("palabra_cta"),
           "url_largo": ep.meta.get("url_largo"), "estado": "propuesto", "posts": posts}
    destino = config.escribir(ep.ruta("calendario.json"), cal)
    print(f"  {len(posts)} publicaciones propuestas ({len(clips)} clips × {len(pub['redes'])} redes) → {destino}")
    if not ep.meta.get("url_largo"):
        print("  ! falta el link del video largo: clipper cta <episodio> --palabra X --url https://youtu.be/…")
    return destino
