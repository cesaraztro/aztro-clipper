---
name: clipper
description: Convierte un video largo (podcast, entrevista, clase de 10 min a 1 h+) en clips verticales para TikTok, Reels y Shorts con aztro-clipper. Úsala cuando el usuario diga "saca clips de este video", "procesa el podcast", "haz shorts de esta entrevista" o suelte un video largo.
---
Sigue `AGENTS.md` del repo aztro-clipper paso a paso. Resumen:
1. `uv run clipper ingest <video> --marca <marca> --hablantes <n>`
2. `uv run clipper transcribe <episodio>`
3. Lee `05_select/INSTRUCCIONES.md` + `04_segment/transcripcion.md` completos y escribe `seleccion.json`.
4. `uv run clipper select <episodio> --validar` hasta 0 errores.
5. `uv run clipper run <episodio>`.
6. Revisa `hoja.jpg` y `reframe.jpg` de cada clip con el subagente revisor.
7. Entrega al usuario la tabla de clips y las rutas de `entregables/`.
