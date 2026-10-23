# Instrucciones para agentes (Claude Code, Codex, OpenCode)

¿Te pidieron instalarlo? Sigue `INSTALAR.md`. ¿Desarrollar el repo? `uv sync --extra dev` y `uv run pytest`.

Este repo convierte videos largos en clips verticales. Tú eres el editor jefe: decides qué momentos, títulos,
ganchos y copy. Los comandos `clipper` hacen el trabajo pesado y determinista. Nunca edites video a mano.

## Flujo cuando el usuario dice "procesa este video / episodio"
1. `clipper ingest <video o carpeta> --marca <marca> --hablantes <n>` (pregunta la marca si no la sabes;
   agrega `--audio` si hay un WAV aparte y `--guion` si hay guion PDF).
2. `clipper transcribe <episodio>`.
3. `clipper select <episodio>` → lee `05_select/INSTRUCCIONES.md` y `04_segment/transcripcion.md`
   completos. Escribe `05_select/seleccion.json` siguiendo el formato. Reglas:
   - Cita IDs de oración (`S0412`), nunca segundos. Recorta palabras con `S0412[3:]` / `S0431[:12]` para quitar
     interrupciones a media oración. Usa `omitir` para saltar oraciones del entrevistador o desvíos.
   - Cada clip debe entenderse solo y abrir con gancho. Dos clips no cuentan lo mismo.
   - Una sola `palabra_cta` por episodio.
4. `clipper select <episodio> --validar` y corrige hasta 0 errores.
5. `clipper run <episodio>` (plan → reframe → render → qa → package).
6. Revisa cada `clips/<id>/hoja.jpg` y `reframe.jpg` (lanza el subagente revisor: `clipper/skills/aztro-clipper-revisor`).
   Si algo falla, cambia `seleccion.json` o la marca y vuelve a correr; el render reutiliza caché.
7. Muestra al usuario: lista de clips (título, duración, score, QA) y las hojas de contacto.

## Publicación (solo con OK explícito del usuario)
- `clipper cta <episodio> --palabra X --url <link YouTube>` → entrega el checklist de ManyChat al usuario.
- `clipper approve <episodio> --clips …` solo con los clips que el usuario aprobó.
- `clipper publish <episodio>` → `calendario.json`. Luego, con el MCP de Metricool, crea cada post con
  `createScheduledPost` y `draft: true`, zona horaria explícita de la marca, `firstCommentText` en YouTube y el
  video subido a una URL pública (Google Drive vinculado). Ver `clipper/skills/aztro-clipper-publicar/SKILL.md`.
- Nunca publiques ni crees borradores sin el OK del usuario.

## No hagas
- No inventes links ni palabras CTA ya usadas por otro episodio (el validador lo detecta).
- Las marcas y episodios viven en `~/AztroClipper` (fuera del repo); nunca los subas.
- No uses dependencias AGPL/GPL (YOLO/ultralytics, PyMuPDF, supoclip) ni Remotion: el repo se distribuye.
