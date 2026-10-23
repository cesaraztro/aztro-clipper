# aztro-clipper

De un video largo (podcast, entrevista, clase) a clips verticales listos para TikTok, Reels y Shorts. El sistema hace:
- transcripción;
- selección de momentos con IA;
- cortes en silencio real;
- encuadre que sigue a quien habla;
- subtítulos animados, gancho y CTA por red social;
- control de calidad;
- copy para Metricool y checklist de ManyChat.

Funciona en **Mac (Apple Silicon)** y **Windows**. Se opera desde un agente (Claude Code, Codex u OpenCode) o
directo desde la terminal.

## Instalación

Mac:
```bash
./instalar.sh
```

Windows (PowerShell):
```powershell
.\instalar.ps1
```

Verifica:
```bash
uv run clipper doctor
```

## Uso en 6 pasos

```bash
# 1. Registrar el episodio (modo A: video ya editado)
uv run clipper ingest "~/Videos/mi-podcast.mp4" --marca aztrotech --hablantes 2

#    Modo B: crudos de cámara + audio externo + guion
uv run clipper ingest ./camara/ --audio ./audio/voz.wav --guion guion.pdf --marca filo --hablantes 2

# 2. Transcribir (Mac: GPU con mlx-whisper · Windows: faster-whisper)
uv run clipper transcribe <episodio>

# 3. Elegir clips: el agente lee 05_select/INSTRUCCIONES.md y escribe seleccion.json
uv run clipper select <episodio>            # genera las instrucciones
uv run clipper select <episodio> --validar  # valida lo que escribió el agente
#    (sin agente: configura LLM_BASE_URL y usa --llm)

# 4. Producir: receta, encuadre, render, control de calidad y entregables
uv run clipper run <episodio>

# 5. CTA: palabra + link del video largo → checklist de ManyChat
uv run clipper cta <episodio> --palabra CONTEXTO --url https://youtu.be/xxxx

# 6. Aprobar y proponer el calendario (el agente lo sube a Metricool como borradores)
uv run clipper approve <episodio> --clips 01 02 03
uv run clipper publish <episodio> --desde 2026-10-27
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

Cada marca vive en `marcas/<id>/` con dos archivos:
- `marca.json`: colores, vocabulario, correcciones, CTA, música, LUT y horarios.
- `criterio.md`: qué temas funcionan.

Copia `marcas/_plantilla/` para crear la tuya. Las marcas reales no se suben al repo (ver `.gitignore`).

## Pruebas

```bash
uv run pytest
```

## Licencias

Código propietario para miembros de la comunidad AztroTech. Las dependencias y atribuciones están en `THIRD_PARTY.md`.
