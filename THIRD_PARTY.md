# Dependencias y atribuciones

| Componente | Uso | Licencia |
|---|---|---|
| FFmpeg | Decodificación, filtros y codificación (se instala aparte) | LGPL/GPL según build; se invoca como programa externo |
| NumPy | Energía de voz, sincronía, diarización | BSD-3 |
| OpenCV (opencv-python-headless) | Lectura de cuadros y detector de caras | Apache-2.0 |
| YuNet (OpenCV Zoo) | Modelo de detección de caras, se descarga en el primer uso | MIT |
| mlx-whisper | Transcripción en Mac | MIT |
| faster-whisper | Transcripción en Windows/Linux | MIT |
| Whisper large-v3-turbo (OpenAI) | Modelo de transcripción | MIT |
| Poppins | Tipografía de subtítulos (`recursos/fuentes`) | SIL Open Font License 1.1 |
| Lógica de cortes, energía, subtítulos y punch-ins | Portada del motor de reels v4 de AztroTech | Propia |

Ideas de diseño (sin copiar código): OpenShorts (MIT), Cutawan (MIT), AI-Youtube-Shorts-Generator (MIT), clipify (MIT).
Excluidos a propósito: ultralytics/YOLO, PyMuPDF, supoclip, whisper-timestamped (AGPL) y Remotion (licencia comercial por persona).
