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
5. **Subir videos.** Cada `video_<red>.mp4` necesita URL pública (p. ej. Google Drive vinculado a Metricool).
6. **Borradores.** Por cada post del calendario: `createScheduledPost` con `draft: true`, fecha y `timezone`
   de la marca, `text`, `providers: [{network}]`, `media: [url]`, `videoCoverMilliseconds`, y según la red
   `instagramData {type: REEL}`, `facebookData {type: REEL}`, `tiktokData {privacyOption}`,
   `youtubeData {title, type: short, privacy, madeForKids: false}` + `firstCommentText`.
7. **Verificar.** `getScheduledPosts` y reporta fecha, red y estado de cada borrador.
