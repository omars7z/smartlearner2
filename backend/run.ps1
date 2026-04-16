# Run from repo root: .\backend\run.ps1
# Or from backend: .\run.ps1
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py -B -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
