"""Etapa 13: registro de palabras CTA (palabra -> video largo) y checklist de ManyChat.

ManyChat no sabe desde qué publicación llegó un comentario: la palabra es la única llave. Por eso cada video
largo tiene su propia palabra y todos sus clips la comparten.
"""
import datetime
import re
import unicodedata

from .. import config

COMUNES = {"HOLA", "INFO", "PRECIO", "QUIERO", "LINK", "VIDEO", "GRACIAS", "SI", "YES", "MAS", "DM", "AYUDA"}


def normalizar(p):
    p = unicodedata.normalize("NFKD", p).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z]", "", p)


def validar_palabra(p, registradas=()):
    """Lista de problemas (vacía = palabra válida)."""
    n = normalizar(p)
    errores = []
    if n != p.upper().strip():
        errores.append(f"usa solo letras sin acentos: {n}")
    if not 4 <= len(n) <= 12:
        errores.append("debe tener de 4 a 12 letras")
    if n in COMUNES:
        errores.append("es demasiado común: se dispararía con comentarios normales")
    for r in registradas:
        if r != n and (r in n or n in r):
            errores.append(f"choca con '{r}' (ManyChat busca por 'contiene')")
    return errores


def ruta_registro(marca):
    return config.MARCAS / marca["id"] / "cta_registro.json"


def registrar(ep, palabra, url):
    reg_p = ruta_registro(ep.marca)
    reg = config.leer(reg_p) if reg_p.exists() else {}
    n = normalizar(palabra)
    errores = validar_palabra(palabra, [k for k in reg if k != n])
    if errores:
        raise SystemExit(f"Palabra '{palabra}' no válida: " + "; ".join(errores))
    reg[n] = {"url": url, "episodio": ep.meta["slug"], "titulo": ep.meta.get("titulo") or ep.meta["slug"],
              "clips": [p.parent.name for p in ep.clips()], "manychat": reg.get(n, {}).get("manychat", "pendiente"),
              "actualizado": datetime.date.today().isoformat()}
    config.escribir(reg_p, reg)
    ep.meta["palabra_cta"], ep.meta["url_largo"] = n, url
    ep.guardar_meta()
    return n


RESPUESTAS = [
    "¡Listo! Te lo mandé por DM 📩",
    "Revisa tus mensajes, ahí va 👀",
    "¡Enviado! Checa tu bandeja 🚀",
    "Te lo acabo de mandar por mensaje 🙌",
    "Ya está en tu DM 🔥",
]


def checklist(ep):
    n, url = ep.meta.get("palabra_cta"), ep.meta.get("url_largo")
    if not n or not url:
        raise SystemExit("Primero registra la palabra: clipper cta <episodio> --palabra PALABRA --url https://youtu.be/…")
    t = f"""# ManyChat · palabra {n}

Episodio: **{ep.meta['slug']}** → {url}
Todos los clips de este episodio usan la palabra **{n}**.

## Instagram (comentario → DM)
1. ManyChat → Automatizaciones → **Nueva automatización** → disparador **"Comentarios en publicaciones y Reels"**.
2. Alcance: **Cualquier publicación o Reel**. Palabra clave: **contiene `{n}`**.
3. Activa **responder al comentario públicamente** y pega estas variantes (ManyChat rota entre ellas):
""" + "".join(f"   - {r}\n" for r in RESPUESTAS) + f"""4. Primer mensaje privado (DM), **con botón** (el botón abre la conversación de 24 h):
   - Texto: "¡Hola! Aquí tienes el video completo 👇"
   - Botón: "Ver el video completo" → `{url}`
5. Publica la automatización.

## Facebook (comentario → DM)
Repite los pasos 1–5 con el disparador **"Comentarios de Facebook"** y la misma palabra.

## TikTok (DM con palabra)
El comentario → DM de TikTok no está disponible en general. Los clips de TikTok dicen **"Escríbeme {n} por DM"**:
crea un disparador **"Palabra clave en DM" = {n}** con el mismo mensaje y botón.

## YouTube Shorts
ManyChat no aplica. El link va en el primer comentario y en la descripción (lo pone `clipper package`).

## Prueba (obligatoria)
- [ ] Desde otra cuenta, comenta `{n}` en un Reel publicado y confirma que llega el DM con el botón.
- [ ] Cuando funcione: `clipper cta {ep.meta['slug']} --confirmar`

## Reglas de Meta
- Una sola respuesta privada por comentario, dentro de los 7 días siguientes.
- Máximo 750 respuestas privadas por hora por cuenta.
- No mandes ráfagas de mensajes idénticos.
"""
    destino = ep.ruta("manychat_" + n + ".md")
    destino.write_text(t)
    return destino


def confirmar(ep):
    reg_p = ruta_registro(ep.marca)
    reg = config.leer(reg_p)
    reg[ep.meta["palabra_cta"]]["manychat"] = "configurada"
    config.escribir(reg_p, reg)
