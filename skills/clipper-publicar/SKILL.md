---
name: clipper-publicar
description: Lleva los clips aprobados de aztro-clipper a Metricool como borradores y prepara ManyChat. Úsala cuando el usuario apruebe clips y diga "prográmalos", "súbelos a Metricool", "arma la semana".
---
Requisito: OK explícito del usuario para cada clip.
1. `uv run clipper cta <episodio> --palabra <PALABRA> --url <link del video largo>` → comparte `manychat_<PALABRA>.md` con el usuario (la automatización se crea a mano en ManyChat, 2 minutos).
2. `uv run clipper approve <episodio> --clips <ids aprobados>`.
3. Opcional: `getBestTimeToPostByNetwork` del MCP de Metricool por red → guarda JSON `{red: {dia: "HH:MM"}}` y pásalo con `--mejores-horas`.
4. `uv run clipper publish <episodio> --desde AAAA-MM-DD` → `calendario.json`.
5. Sube cada `video_<red>.mp4` a una URL pública (Google Drive vinculado a Metricool; enlace directo de descarga).
6. Por cada post del calendario, `createScheduledPost` con: `draft: true`, `publicationDate` + `timezone` de la marca,
   `text`, `providers: [{network}]`, `media: [url]`, `videoCoverMilliseconds`, y según la red
   `instagramData {type: REEL}`, `facebookData {type: REEL}`, `tiktokData {privacyOption}`,
   `youtubeData {title, type: short, privacy, madeForKids: false}` + `firstCommentText` con el link largo.
7. Verifica con `getScheduledPosts` y reporta al usuario fecha, red y estado de cada borrador.
Nunca publiques directo ni crees borradores sin el OK.
