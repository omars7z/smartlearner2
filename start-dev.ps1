# Starts backend (FastAPI) and frontend (Vite) in separate PowerShell windows.
# Run from project root: .\start-dev.ps1
# Or double-click start-dev.bat

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

if (-not (Test-Path $backend)) { throw "Missing folder: $backend" }
if (-not (Test-Path $frontend)) { throw "Missing folder: $frontend" }

$venvPython = @(
    (Join-Path $backend ".venv\Scripts\python.exe"),
    (Join-Path $backend "venv\Scripts\python.exe")
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($venvPython) {
    $backendCmd = "& '$venvPython' -m uvicorn app.main:app --reload"
} else {
    $backendCmd = "python -m uvicorn app.main:app --reload"
}

$commonArgs = @("-NoExit", "-NoProfile", "-Command")
Start-Process powershell -ArgumentList ($commonArgs + $backendCmd) -WorkingDirectory $backend
Start-Process powershell -ArgumentList ($commonArgs + "npm run dev") -WorkingDirectory $frontend

Write-Host "Started: backend (uvicorn) and frontend (npm run dev). Close those windows to stop the servers."
