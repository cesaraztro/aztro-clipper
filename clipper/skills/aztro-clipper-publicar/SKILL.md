---
name: aztro-clipper-publicar
description: Lleva a Metricool (como borradores) los clips aprobados de aztro-clipper y prepara el CTA de ManyChat. Úsala cuando el usuario apruebe clips y diga "prográmalos", "súbelos a Metricool", "arma la semana" o "configura ManyChat".
---

Requisito: OK explícito del usuario para cada clip. Nunca publiques directo.

1. **CTA.** `clipper cta <episodio> --palabra <PALABRA> --url <link del video largo en YouTube>` →
   entrega al usuario `manychat_<PALABRA>.md` (la automatización se crea a mano en ManyChat, ~2 min).
   Instagram/Facebook: comentario → DM. TikTok: "escríbeme PALABRA por DM". YouTube: link en primer comentario.
2. **Aprobar.** `clipper approve <episodio> --clips <ids que aprobó el usuario>`.
3. **Mejores horas (opcional).** Con el MCP de Metricool, `getBestTimeToPostByNetwork` por red → guarda un JSON
   `{"instagram": {"monday": "19:30", ...}, ...}` y pásalo con `--mejores-horas`.
4. **Calendario.** `clipper publish <episodio> --desde AAAA-MM-DD` → `calendario.json`.
5. **Subir videos.** Cada `video_<red>.mp4` necesita una URL pública de descarga directa. Opciones:
   - Google Drive (con Composio o la API de Drive): compartir como "cualquiera con el link" y usar
     `https://drive.google.com/uc?export=download&id=<ID>` (menos de 100 MB por archivo).
   - Sin forma de subir archivos desde el agente: el usuario sube los videos en la web de Metricool y pega el
     texto de `copy.md`; el agente le deja la tabla de fechas, horas y textos lista.
6. **Borradores.** Por cada post del calendario: `createScheduledPost` con `draft: true`, fecha y `timezone`
   de la marca, `text`, `providers: [{network}]`, `media: [url]`, `videoCoverMilliseconds`, y según la red
   `instagramData {type: REEL}`, `facebookData {type: REEL}`, `tiktokData {privacyOption}`,
   `youtubeData {title, type: short, privacy, madeForKids: false}` + `firstCommentText`.
7. **Verificar.** `getScheduledPosts`: compara la hora guardada con la pedida (Metricool puede mover horarios
   cerca de cambios de horario) y reporta fecha, red y estado de cada publicación.
