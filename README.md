<div align="center">

# 🎬 aztro-clipper

**Tu podcast de 1 hora → 10 clips virales para TikTok, Reels y Shorts. Sin abrir un editor.**

<img src="docs/media/demo.gif" width="260" alt="Clip generado por aztro-clipper: gancho, firma, B-roll y subtítulos karaoke">

▶️ [Ver el clip completo con audio](docs/media/clip-demo.mp4) · Mac · Windows · Linux · Claude Code · Codex · OpenCode

</div>

---

## ✨ Antes y después

<p align="center"><img src="docs/media/antes-despues.jpg" width="520" alt="Toma cruda contra clip terminado"></p>

A la izquierda, la toma cruda. A la derecha, lo que entrega `clipper` sin que toques nada: encuadre cerrado sobre quien habla,
gancho arriba, subtítulos palabra por palabra y tu firma.

## 💥 Efectos que trae cada clip

<p align="center"><img src="docs/media/efectos.jpg" alt="Gancho, firma, B-roll, tarjeta, karaoke y CTA"></p>

| Efecto | Qué hace |
|---|---|
| 🪝 **Gancho** | Frase de impacto en los primeros 1.5 s para frenar el scroll |
| 🏷️ **Firma** | Nombre y rol que entran deslizando (lower-third) |
| 🎞️ **B-roll** | Imágenes que ilustran lo que dices, con Ken Burns y fundido. Primero tu material, luego Pexels |
| 🟨 **Tarjetas** | La palabra clave salta en grande con rebote y sonido *pop* |
| 🔤 **Karaoke** | Subtítulos que iluminan cada palabra al decirla |
| 📢 **CTA** | Cierre por red: "comenta PALABRA" (IG/FB), "mándame DM" (TikTok) o "Sígueme" |
| 🎯 **Cámara viva** | Sigue a quien habla, punch-ins al ritmo y cambio visual cada ≤ 4 s |
| 🔊 **Diseño sonoro** | *Whoosh*, *pop* e impacto en cada evento, música con ducking y audio a −14 LUFS |
| 📊 **Barra de progreso** | Línea dorada que invita a ver hasta el final |

## 🖼️ Imágenes y 🎥 videos

- **Tu marca primero:** pon fotos o videos en `marcas/<id>/assets/broll/` y el sistema los usa cuando el nombre del
  archivo coincide con lo que se dice (`render-plaza.png` aparece cuando hablas de "plaza").
- **Pexels después:** si no hay material propio, descarga videos verticales con licencia libre de uso comercial
  (necesita `PEXELS_API_KEY`) y los guarda en caché para no bajarlos dos veces.
- **El agente elige:** en `seleccion.json` escribe qué buscar y en qué palabra mostrarlo; tú solo apruebas.
- **Tres versiones por clip:** `general`, `tiktok` y `youtube`, cada una con su CTA, en H.264 listo para Metricool.

## ⚙️ Cómo funciona

```mermaid
flowchart TD
  A[🎙️ Video largo] --> B[📝 Transcribe]
  B --> C[🧠 El agente elige momentos]
  C --> D[✂️ Corta en silencio]
  D --> E[🎯 Encuadra a quien habla]
  E --> F[💥 Efectos + B-roll + sonido]
  F --> G[✅ Control de calidad]
  G --> H[📅 Metricool + ManyChat]
```

## Instalación (cualquier agente, cualquier sistema)

Abre tu agente (Claude Code, OpenCode, Codex…) y escríbele:

> Clona https://github.com/cesaraztro/aztro-clipper y sigue su INSTALAR.md

El agente detecta si estás en Mac, Windows o Linux, instala `uv`, el comando `clipper`, FFmpeg y las skills, y
verifica todo con `clipper doctor`. Después solo dile: **"saca clips de este video: <ruta>"**.

¿Prefieres la terminal? `./instalar.sh` (Mac/Linux) o `.\instalar.ps1` (Windows) hacen lo mismo.

## Uso en 6 pasos

```bash
# 1. Registrar el episodio (modo A: video ya editado)
clipper ingest "~/Videos/mi-podcast.mp4" --marca aztrotech --hablantes 2

#    Modo B: crudos de cámara + audio externo + guion
clipper ingest ./camara/ --audio ./audio/voz.wav --guion guion.pdf --marca filo --hablantes 2

# 2. Transcribir (Mac: GPU con mlx-whisper · Windows: faster-whisper)
clipper transcribe <episodio>

# 3. Elegir clips: el agente lee 05_select/INSTRUCCIONES.md y escribe seleccion.json
clipper select <episodio>            # genera las instrucciones
clipper select <episodio> --validar  # valida lo que escribió el agente
#    (sin agente: configura LLM_BASE_URL y usa --llm)

# 4. Producir: receta, encuadre, render, control de calidad y entregables
clipper run <episodio>

# 5. CTA: palabra + link del video largo → checklist de ManyChat
clipper cta <episodio> --palabra CONTEXTO --url https://youtu.be/xxxx

# 6. Aprobar y proponer el calendario (el agente lo sube a Metricool como borradores)
clipper approve <episodio> --clips 01 02 03
clipper publish <episodio> --desde 2026-10-27
```

`<episodio>` es el nombre de la carpeta en `~/AztroClipper/episodios/` (p. ej. `2026-10-23_entrevista-reencuentro`).

## Qué hace cada etapa

| Etapa | Resultado | Cómo |
|---|---|---|
| `ingest` | `episodio.json`, `00_ingest/voz16k.wav`, `vista.jpg` | Une archivos de cámara en orden; sincroniza el audio externo por correlación de forma de onda |
| `transcribe` | `02_transcribe/transcripcion.json`, `04_segment/transcripcion.md` | Tiempos por palabra; oraciones numeradas S0001…; alerta de audio dudoso |
| `select` | `05_select/seleccion_validada.json` | El agente cita IDs de oración, con recortes por palabra como `S0080[4:]`. Se validan duración, duplicados, conectores y palabra CTA |
| `plan` | `clips/<id>/clip.json` | Cortes en silencio real, pausas >0.14 s fuera, velocidad con cuadros exactos, subtítulos, punch-ins, y un cambio visual cada ≤4 s |
| `reframe` | encuadre por tramo + `reframe.jpg` | Caras (YuNet) + diarización por voz + movimiento de labios: la cámara sigue a quien habla y alterna tomas |
| `render` | `video_general/tiktok/youtube.mp4` | Desde el original en 4K/HDR, en paralelo y con caché. Color de marca, subtítulos, gancho, CTA por red y audio masterizado |
| `qa` | `qa.json`, `hoja.jpg` | Formato para Metricool, LUFS, picos, cortes en silencio, cuadros negros y re-transcripción del clip final |
| `package` | `entregables/<id>/` | Video por red, portada y `copy.json` (texto, título de YouTube, primer comentario) |
| `cta` | `manychat_<PALABRA>.md` | Registro palabra → link, validación anti-choques y checklist de ManyChat |
| `approve` / `publish` | `aprobacion.json`, `calendario.json` | Huella de cada video aprobado y calendario de borradores para Metricool |

## Marcas

Cada marca vive en `~/AztroClipper/marcas/<id>/` (fuera del código) con dos archivos:
- `marca.json`: colores, vocabulario, correcciones, CTA, música, LUT y horarios.
- `criterio.md`: qué temas funcionan.

Créala con `clipper marca <id> --nombre "Mi marca"`. Las marcas nunca se suben al repo.

## Pruebas

```bash
uv run pytest
```

## Licencias

Código propietario para miembros de la comunidad AztroTech. Las dependencias y atribuciones están en `THIRD_PARTY.md`.
