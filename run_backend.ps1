$projectRoot = (Resolve-Path .).Path
Write-Host "Project root: $projectRoot"
$env:PYTHONPATH = $projectRoot
$venv = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $venv) {
    Write-Host "Activating virtualenv"
    & $venv
}
Write-Host "Starting uvicorn backend.app:app --reload --port 8000"
& "$projectRoot\.venv\Scripts\python.exe" -m uvicorn backend.app:app --reload --port 8000
