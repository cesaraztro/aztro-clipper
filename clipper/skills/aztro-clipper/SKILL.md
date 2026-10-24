---
name: aztro-clipper
description: Convierte un video largo (podcast, entrevista, clase, live; de 10 min a 1 h o más) en clips verticales dinámicos para TikTok, Instagram Reels y YouTube Shorts: subtítulos karaoke, gancho, B-roll (propio o Pexels), tarjetas animadas con la palabra clave, firma, barra de progreso, efectos de sonido, encuadre que sigue a quien habla y CTA para ManyChat. Úsala cuando el usuario diga "saca clips de este video", "procesa el podcast", "haz shorts / reels de esta entrevista", "edita este video largo" o comparta un video de más de 5 minutos.
---

# aztro-clipper

Tú decides (qué momentos, títulos, ganchos, copy); el comando `clipper` hace el trabajo pesado. Funciona igual en
Mac, Windows y Linux. Si `clipper` no existe, instálalo siguiendo `INSTALAR.md` de
https://github.com/cesaraztro/aztro-clipper y después corre `clipper setup`.

Los episodios viven en `~/AztroClipper/episodios/<fecha>_<slug>/` y las marcas en `~/AztroClipper/marcas/<id>/`.

## Flujo
1. **Marca.** `clipper doctor` muestra las marcas disponibles. Si el usuario no tiene una, créala:
   `clipper marca <id> --nombre "Nombre"` y ajusta `marca.json` (colores, vocabulario, CTA) y `criterio.md` con él.
2. **Registrar el video.**
   `clipper ingest "<ruta al video o carpeta>" --marca <id> --hablantes <n>`
   - Varios archivos de cámara: pasa la carpeta. Audio grabado aparte: `--audio <wav>`. Guion: `--guion <pdf>`.
3. **Transcribir.** `clipper transcribe <episodio>` (el episodio es el nombre de la carpeta que imprimió `ingest`).
4. **Elegir clips (tu trabajo).** `clipper select <episodio>` imprime la ruta de `INSTRUCCIONES.md`. Léelo completo y
   lee completa `04_segment/transcripcion.md`. Escribe `05_select/seleccion.json`:
   - Cita IDs de oración (`S0052`), nunca segundos. Recorta palabras con `S0080[4:]` o `S0059[:25]` para quitar
     interrupciones del entrevistador a media oración; usa `"omitir": ["S0075"]` para saltar oraciones.
   - Cada clip abre con gancho, se entiende solo y dura lo que pide la marca. Dos clips no cuentan lo mismo.
   - Una sola `palabra_cta` para todo el episodio.
   Luego `clipper select <episodio> --validar` y corrige hasta 0 errores.
5. **Producir.** `clipper run <episodio>` (receta → encuadre → render → control de calidad → entregables).
6. **Revisar.** Abre `clips/<id>/hoja.jpg` y `reframe.jpg`. Si puedes lanzar subagentes, usa la skill
   `aztro-clipper-revisor` con contexto limpio. Ajusta `seleccion.json` y vuelve a correr `clipper run` si hace falta
   (el render reutiliza lo que no cambió).
7. **Entregar.** Muestra una tabla: clip, título, duración, score, QA, y la ruta `entregables/`. Cada carpeta trae
   `video_instagram.mp4`, `video_tiktok.mp4`, `video_youtube.mp4`, `video_facebook.mp4`, `portada.jpg` y `copy.md`.

Para publicar (Metricool + ManyChat) usa la skill `aztro-clipper-publicar`, solo con el OK del usuario.

## Reglas
- No inventes links. No publiques nada sin aprobación.
- Si una etapa falla, lee el error: casi siempre dice qué comando correr. `clipper doctor` diagnostica la instalación.
