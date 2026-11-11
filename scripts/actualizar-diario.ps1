# Actualización diaria del Observatorio de la Curiosidad.
# Descarga solo lo nuevo de Wikimedia (con caché), recalcula y genera las curiosidades del día.
# Pensado para el Programador de tareas de Windows (ver scripts/registrar-tarea.ps1).

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
# Leer la salida de Python como UTF-8 (si no, PowerShell usa la página de códigos de la consola y rompe las tildes).
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$log = Join-Path $root 'data\daily.log'
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null

"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File -FilePath $log -Append -Encoding utf8
& (Join-Path $root '.venv\Scripts\python.exe') -m observatorio daily *>&1 |
    Where-Object { $_ -notmatch '^(visitas|rankings): ' } |
    Out-File -FilePath $log -Append -Encoding utf8
exit $LASTEXITCODE
