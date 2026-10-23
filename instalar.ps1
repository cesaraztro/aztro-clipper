# Instalador de aztro-clipper para Windows (PowerShell). Idempotente.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { winget install --id Gyan.FFmpeg -e --accept-source-agreements }
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" }
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv python install 3.12
uv sync --extra dev
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
uv run clipper doctor
Write-Host "Listo. Prueba: uv run clipper ingest <video> --marca _plantilla"
