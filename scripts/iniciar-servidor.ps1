# Inicia el Observatorio en este PC: la API (que sirve también la web compilada en web/dist) y un túnel
# de Cloudflare que la publica en internet. Pensado para ejecutarse al iniciar sesión en Windows.
# La dirección pública queda en data\url-publica.txt (cambia cada vez que el túnel se reinicia).

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force (Join-Path $root 'data') | Out-Null
$python = Join-Path $root '.venv\Scripts\python.exe'
$cloudflared = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
$env:PYTHONIOENCODING = 'utf-8'
$port = if ($env:OBSERVATORIO_PUERTO) { $env:OBSERVATORIO_PUERTO } else { '8095' }   # 8010 lo usa otro proyecto en Docker

function Test-Api { try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:$port/api/health).StatusCode -eq 200 } catch { $false } }

# 1) API en 127.0.0.1:$port (solo local; al exterior se llega por el túnel).
if (-not (Test-Api)) {
    Start-Process -FilePath $python -WorkingDirectory $root -WindowStyle Hidden `
        -ArgumentList '-m', 'uvicorn', 'observatorio_api.main:app', '--app-dir', 'api', '--host', '127.0.0.1', '--port', $port `
        -RedirectStandardOutput (Join-Path $root 'data\api.log') -RedirectStandardError (Join-Path $root 'data\api.err.log')
    for ($i = 0; $i -lt 30 -and -not (Test-Api); $i++) { Start-Sleep -Seconds 1 }
}
if (-not (Test-Api)) { throw 'La API no respondió. Revisa data\api.err.log' }

# 2) Túnel de Cloudflare (conexión saliente: no abre puertos en el router).
if (-not (Get-Process cloudflared -ErrorAction SilentlyContinue)) {
    $log = Join-Path $root 'data\cloudflared.log'
    Remove-Item $log -ErrorAction SilentlyContinue
    Start-Process -FilePath $cloudflared -WindowStyle Hidden `
        -ArgumentList 'tunnel', '--no-autoupdate', '--url', "http://127.0.0.1:$port", '--logfile', $log
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 1
        $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($m) { $m.Matches[0].Value | Out-File -FilePath (Join-Path $root 'data\url-publica.txt') -Encoding utf8; break }
    }
}
Get-Content (Join-Path $root 'data\url-publica.txt') -ErrorAction SilentlyContinue
