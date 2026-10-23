# Instalador para Windows (PowerShell). Mismo resultado que seguir INSTALAR.md.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" }
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv tool install --python 3.12 --force -e .
uv tool update-shell
& (Join-Path (uv tool dir --bin) "clipper.exe") setup @args
