# Start the GambitLab backend (serves the API and the built frontend).
#   ./run.ps1              # http://127.0.0.1:8000
#   ./run.ps1 -Reload      # auto-reload for backend development
param([switch]$Reload)

$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot 'trainer\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "Python venv not found at $python. Create it with: py -3.10 -m venv trainer\.venv"
}

$args = @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000')
if ($Reload) { $args += '--reload' }

Push-Location (Join-Path $PSScriptRoot 'server')
try {
    & $python @args
} finally {
    Pop-Location
}
