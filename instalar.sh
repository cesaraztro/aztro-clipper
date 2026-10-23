#!/usr/bin/env bash
# Instalador de aztro-clipper para Mac (Apple Silicon). Idempotente: se puede correr varias veces.
set -euo pipefail
cd "$(dirname "$0")"
command -v brew >/dev/null || { echo "Instala Homebrew primero: https://brew.sh"; exit 1; }
command -v ffmpeg >/dev/null || brew install ffmpeg
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12
uv sync --extra dev
[ -f .env ] || cp .env.example .env
uv run clipper doctor
echo "Listo. Prueba: uv run clipper ingest <video> --marca _plantilla"
