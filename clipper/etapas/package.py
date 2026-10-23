"""Etapa 11: entregables por clip (video por red, portada y copy listo para Metricool)."""
import shutil

from .. import config, media

VIDEO_POR_RED = {"instagram": "general", "facebook": "general", "tiktok": "tiktok", "youtube": "youtube"}


def copy_por_red(ep, clip):
    m, p, url = ep.marca, ep.meta.get("palabra_cta") or "PALABRA", ep.meta.get("url_largo")
    tags = " ".join(dict.fromkeys(clip.get("hashtags", []) + m.get("hashtags", [])))
    desc = clip.get("descripcion") or clip["titulo"]
    cta = {red: m["cta"][red].replace("{PALABRA}", p) for red in ("instagram", "facebook", "tiktok", "youtube")}
    yt_desc = f"{desc}\n\n▶ Video completo: {url or '[link del video largo]'}\n\n{tags}"
    return {
        "instagram": {"texto": f"{desc}\n\n👉 {cta['instagram']}\n\n{tags}"},
        "facebook": {"texto": f"{desc}\n\n👉 {cta['facebook']}"},
        "tiktok": {"texto": f"{desc} 👉 {cta['tiktok']} {tags}"[:2200]},
        "youtube": {"titulo": clip["titulo"][:100], "texto": yt_desc,
                    "primer_comentario": f"▶ Video completo aquí: {url}" if url else None},
        "palabra_cta": p, "url_largo": url,
    }


def correr(ep, solo=None):
    for cp in ep.clips():
        clip = config.leer(cp)
        if solo and clip["id"] not in solo:
            continue
        qa = config.leer(cp.parent / "qa.json") if (cp.parent / "qa.json").exists() else {"ok": False}
        destino = ep.ruta("entregables", cp.parent.name)
        destino.mkdir(parents=True, exist_ok=True)
        for red, var in VIDEO_POR_RED.items():
            src = cp.parent / f"video_{var}.mp4"
            if src.exists():
                shutil.copy2(src, destino / f"video_{red}.mp4")
        # portada: el gancho ya está en pantalla en el segundo 1.2
        media.correr([media.ffmpeg_bin(), "-y", "-v", "error", "-ss", "1.2", "-i", str(cp.parent / "video_general.mp4"),
                      "-frames:v", "1", "-q:v", "2", str(destino / "portada.jpg")])
        cp_red = copy_por_red(ep, clip)
        cp_red.update(clip_id=clip["id"], titulo=clip["titulo"], viral_score=clip.get("viral_score"),
                      dur=clip["dur"], qa_ok=qa.get("ok", False), portada_ms=1200)
        config.escribir(destino / "copy.json", cp_red)
        md = [f"# {clip['titulo']}", f"Clip {clip['id']} · {clip['dur']:.0f}s · score {clip.get('viral_score')} · QA {'OK' if qa.get('ok') else 'PENDIENTE'}", ""]
        for red in ("instagram", "facebook", "tiktok", "youtube"):
            md += [f"## {red.capitalize()}", cp_red[red].get("titulo", "") or "", cp_red[red]["texto"], ""]
        (destino / "copy.md").write_text("\n".join(md), encoding="utf-8")
        print(f"  clip {clip['id']}: {destino}")
