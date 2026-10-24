# Instalar aztro-clipper (instrucciones para el agente)

Si eres un agente (Claude Code, OpenCode, Codex u otro) y te pidieron instalar aztro-clipper, sigue estos pasos
en orden. Funcionan en Mac, Windows y Linux; tú detectas el sistema, el usuario no tiene que decírtelo.

## 0. Detecta el sistema
- Si `uname` responde `Darwin` → **Mac**. Si responde `Linux` → **Linux**. Usa bash/zsh.
- Si no existe `uname` o estás en PowerShell/cmd → **Windows**. Usa PowerShell.

## 1. uv (gestor de Python; instala Python 3.12 por su cuenta)
Comprueba con `uv --version`. Si no existe:
- Mac / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

Después de instalarlo, si la terminal no encuentra `uv`, usa la ruta completa:
`~/.local/bin/uv` (Mac/Linux) o `$env:USERPROFILE\.local\bin\uv.exe` (Windows).

## 2. Código
El repo es público (no hace falta cuenta de GitHub). Clónalo en la carpeta de datos:
`git clone https://github.com/cesaraztro/aztro-clipper ~/AztroClipper/app`

Si no hay `git`, descarga https://github.com/cesaraztro/aztro-clipper/archive/refs/heads/main.zip y descomprímelo en
`~/AztroClipper/app` (en ese caso `clipper actualizar` no funciona; para actualizar, vuelve a descargarlo).

En Windows usa `$HOME\AztroClipper\app` como destino. Si ya existe, entra y corre `git pull`.

## 3. Instalar el comando `clipper`
```
uv tool install --python 3.12 -e ~/AztroClipper/app
uv tool update-shell
```
(Windows: `uv tool install --python 3.12 -e $HOME\AztroClipper\app`.)

Si `clipper` no se encuentra en esta misma terminal, usa la ruta que imprime `uv tool dir --bin`
(p. ej. `~/.local/bin/clipper` o `$env:USERPROFILE\.local\bin\clipper.exe`). En terminales nuevas ya funciona.

## 4. Configurar todo lo demás
```
clipper setup
```
Instala FFmpeg con el gestor del sistema (Homebrew, winget, Chocolatey, Scoop o apt), crea `~/AztroClipper`,
instala las skills `aztro-clipper`, `aztro-clipper-revisor` y `aztro-clipper-publicar` para Claude Code, OpenCode y
Codex, descarga el detector de caras y corre `clipper doctor`.

- Si el usuario ya tiene marca: `clipper setup --marca <id> --nombre "Nombre visible"`.
- Si FFmpeg se acaba de instalar y no se detecta, cierra y abre la terminal y repite `clipper setup`.
- Opcional: `clipper setup --modelos` descarga ya el modelo de transcripción (~1.5 GB); si no, se baja en el primer uso.

## 5. Verificar
`clipper doctor` debe terminar en "Todo en verde.". Dile al usuario que reinicie su agente para que cargue las
skills nuevas, y que para usarlo basta con decir: **"saca clips de este video: <ruta>"**.

## Actualizar
`clipper actualizar` (baja la última versión y reinstala las skills).
