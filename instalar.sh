#!/usr/bin/env bash
# Instalador para Mac y Linux. Mismo resultado que seguir INSTALAR.md.
set -euo pipefail
cd "$(dirname "$0")"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv tool install --python 3.12 --force -e .
uv tool update-shell || true
"$(uv tool dir --bin)/clipper" setup "$@"
