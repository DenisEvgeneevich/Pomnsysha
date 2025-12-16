# Запустить backend (PowerShell)
# Рекомендуется запускать из корня репозитория.
# Использование:
#   .\run_backend.ps1

$projectRoot = (Resolve-Path .).Path
Write-Host "Project root: $projectRoot"
$env:PYTHONPATH = $projectRoot
# Активируем виртуальное окружение, если существует
$venv = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $venv) {
    Write-Host "Activating virtualenv"
    & $venv
}
# Запускаем uvicorn из корня, импортируя backend.app
Write-Host "Starting uvicorn backend.app:app --reload --port 8000"
& "$projectRoot\.venv\Scripts\python.exe" -m uvicorn backend.app:app --reload --port 8000
