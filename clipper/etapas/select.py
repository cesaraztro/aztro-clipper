"""Etapa 6: selección de momentos.

Por defecto la hace el agente (Claude Code, Codex, OpenCode): lee transcripcion.md y escribe seleccion.json
citando IDs de oración. Este módulo prepara las instrucciones, valida lo que el agente escribió y, opcionalmente,
lo resuelve con un endpoint compatible con OpenAI (modo sin agente).
"""
import json
import os
import re
import urllib.request
from pathlib import Path

from .. import config
from ..energia import Energia
from . import cta

CONECTORES = ["y ", "entonces", "pero ", "eso ", "esto ", "o sea", "como te decia", "como decia", "ademas",
              "por eso", "porque ", "asi que", "tambien", "lo que dijo", "y entonces", "bueno"]


def parse_ref(ref):
    """'S0080' o 'S0080[4:]' / 'S0059[:25]' -> (id, (a, b) o None). El recorte es por índice de palabra."""
    m = re.fullmatch(r"(S\d{4})(?:\[(-?\d*):(-?\d*)\])?", (ref or "").strip())
    if not m:
        raise ValueError(f"referencia inválida '{ref}' (usa S0001 o S0001[3:])")
    sl = (int(m[2]) if m[2] else None, int(m[3]) if m[3] else None) if m[2] is not None and (m[2] or m[3]) else None
    return m[1], sl


def instrucciones(ep):
    plantilla = (config.PROMPTS / "seleccion.md").read_text(encoding="utf-8")
    m = ep.marca
    criterio_p = Path(m["_dir"]) / "criterio.md"
    criterio = criterio_p.read_text(encoding="utf-8") if criterio_p.exists() else "(sin criterio específico de marca)"
    horas = ep.meta["dur"] / 3600
    lo, hi = m["seleccion"]["clips_por_hora"]
    txt = (plantilla.replace("{{MARCA}}", m["nombre"])
           .replace("{{CRITERIO}}", criterio)
           .replace("{{DUR_MIN}}", str(m["seleccion"]["duracion"][0]))
           .replace("{{DUR_MAX}}", str(m["seleccion"]["duracion"][1]))
           .replace("{{N_MIN}}", str(max(3, round(lo * horas))))
           .replace("{{N_MAX}}", str(max(5, round(hi * horas))))
           .replace("{{PALABRA}}", ep.meta.get("palabra_cta") or "(la decide el agente: una sola palabra para todo el episodio)")
           .replace("{{TRANSCRIPCION}}", str(ep.ruta("04_segment", "transcripcion.md")))
           .replace("{{SALIDA}}", str(ep.ruta("05_select", "seleccion.json"))))
    d = ep.ruta("05_select", "INSTRUCCIONES.md")
    d.parent.mkdir(parents=True, exist_ok=True)
    d.write_text(txt, encoding="utf-8")
    return d


def _velocidad(ep):
    mj = ep.marca["montaje"]
    return mj["velocidad_conversacion"] if (ep.meta.get("hablantes") or 1) > 1 else mj["velocidad"]


def duracion_estimada(ors, en, minimo, vel):
    """Duración final aproximada: voz sin pausas largas, acelerada."""
    total = 0.0
    for o in ors:
        span = o["t1"] - o["t0"] + 0.1
        sil = sum(b - a for a, b in en.silencios(o["t0"], o["t1"], minimo))
        total += max(0.3, span - sil)
    return total / vel


def validar(ep):
    sel_p = ep.ruta("05_select", "seleccion.json")
    if not sel_p.exists():
        raise SystemExit(f"Falta {sel_p}. Lee {ep.ruta('05_select', 'INSTRUCCIONES.md')} y escríbelo.")
    sel = config.leer(sel_p)
    ors = config.leer(ep.ruta("04_segment", "oraciones.json"))
    idx = {o["id"]: i for i, o in enumerate(ors)}
    en = Energia(ep.ruta("00_ingest", "voz16k.wav"))
    mj, dmin, dmax = ep.marca["montaje"], *ep.marca["seleccion"]["duracion"]
    vel = _velocidad(ep)
    errores, avisos, clips = [], [], []
    palabra_ep = sel.get("palabra_cta") or ep.meta.get("palabra_cta")
    if not palabra_ep:
        errores.append("falta 'palabra_cta' (una palabra para todo el episodio)")
    else:
        reg_p = cta.ruta_registro(ep.marca)
        reg = config.leer(reg_p) if reg_p.exists() else {}
        problemas = cta.validar_palabra(palabra_ep, [k for k, v in reg.items() if v.get("episodio") != ep.meta["slug"]])
        errores += [f"palabra_cta: {p}" for p in problemas]
    for c in sel.get("clips", []):
        cid = c.get("id") or f"{len(clips) + 1:02d}"
        try:
            (id0, sl0), (id1, sl1) = parse_ref(c.get("inicio", "")), parse_ref(c.get("fin", ""))
        except ValueError as e:
            errores.append(f"clip {cid}: {e}"); continue
        if id0 not in idx or id1 not in idx:
            errores.append(f"clip {cid}: inicio/fin deben ser IDs existentes (S0001…)"); continue
        i0, i1 = idx[id0], idx[id1]
        if i1 < i0:
            errores.append(f"clip {cid}: fin antes que inicio"); continue
        omitir = set(c.get("omitir", []))
        elegidas = [dict(o) for o in ors[i0:i1 + 1] if o["id"] not in omitir]
        recortes = {}
        for oid, sl in ((id0, sl0), (id1, sl1)):
            if sl:
                o = next(x for x in elegidas if x["id"] == oid)
                a, b = recortes.get(oid, [None, None])
                a, b = (sl[0] if sl[0] is not None else a), (sl[1] if sl[1] is not None else b)
                recortes[oid] = [a, b]
                ws = o["palabras"][slice(a, b)]
                if not ws:
                    errores.append(f"clip {cid}: el recorte de {oid} deja la oración vacía"); continue
                o.update(palabras=ws, t0=ws[0]["t0"], t1=ws[-1]["t1"], texto=" ".join(w["w"] for w in ws))
        if not elegidas:
            errores.append(f"clip {cid}: no quedó ninguna oración"); continue
        d = duracion_estimada(elegidas, en, mj["silencio_min"], vel)
        if not dmin * 0.8 <= d <= dmax * 1.15:
            errores.append(f"clip {cid}: dura ~{d:.0f}s, fuera de {dmin}–{dmax}s")
        elif not dmin <= d <= dmax:
            avisos.append(f"clip {cid}: dura ~{d:.0f}s (rango ideal {dmin}–{dmax}s)")
        primera = config.norm(elegidas[0]["texto"][:20]) if elegidas else ""
        txt0 = elegidas[0]["texto"].lower() if elegidas else ""
        if any(txt0.startswith(k) for k in CONECTORES):
            avisos.append(f"clip {cid}: arranca con conector ('{elegidas[0]['texto'][:30]}…'): ¿se entiende sin contexto?")
        malas = [o["id"] for o in elegidas if o["alertas"]]
        if malas:
            avisos.append(f"clip {cid}: incluye oraciones con alerta {malas}")
        for campo in ("titulo", "gancho"):
            if not c.get(campo):
                errores.append(f"clip {cid}: falta '{campo}'")
        clips.append({**c, "id": cid, "t0": elegidas[0]["t0"], "t1": elegidas[-1]["t1"], "recortes": recortes,
                      "oraciones": [o["id"] for o in elegidas], "dur_estimada": round(d, 1), "_primera": primera})
    # dos clips no deben contar lo mismo
    for a in range(len(clips)):
        for b in range(a + 1, len(clips)):
            sa, sb = set(clips[a]["oraciones"]), set(clips[b]["oraciones"])
            iou = len(sa & sb) / max(1, len(sa | sb))
            if iou > 0.3:
                errores.append(f"clips {clips[a]['id']} y {clips[b]['id']} se repiten ({iou:.0%} de oraciones en común)")
    for c in clips:
        c.pop("_primera", None)
    res = {"palabra_cta": cta.normalizar(palabra_ep) if palabra_ep else None, "velocidad": vel,
           "clips": clips, "errores": errores, "avisos": avisos}
    config.escribir(ep.ruta("05_select", "seleccion_validada.json"), res)
    for e in errores:
        print(f"  ✗ {e}")
    for a in avisos:
        print(f"  ! {a}")
    print(f"  {len(clips)} clips · {len(errores)} errores · {len(avisos)} avisos")
    if errores:
        raise SystemExit(1)
    if palabra_ep and not ep.meta.get("palabra_cta"):
        ep.meta["palabra_cta"] = cta.normalizar(palabra_ep)
        ep.guardar_meta()
    return res


def con_llm(ep):
    """Modo sin agente: manda instrucciones + transcripción a un endpoint compatible con OpenAI."""
    base, key, modelo = os.environ.get("LLM_BASE_URL"), os.environ.get("LLM_API_KEY"), os.environ.get("LLM_MODEL")
    if not (base and modelo):
        raise SystemExit("Configura LLM_BASE_URL, LLM_MODEL (y LLM_API_KEY) en .env para el modo sin agente.")
    ins = instrucciones(ep).read_text(encoding="utf-8")
    trans = ep.ruta("04_segment", "transcripcion.md").read_text(encoding="utf-8")
    body = {"model": modelo, "temperature": 0.3, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": ins}, {"role": "user", "content": trans}]}
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})})
    with urllib.request.urlopen(req, timeout=300) as r:
        contenido = json.loads(r.read())["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", contenido, re.S)
    config.escribir(ep.ruta("05_select", "seleccion.json"), json.loads(m[0] if m else contenido))
    return validar(ep)
