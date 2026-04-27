<# ============================================
   DEV — Ejecutar la app localmente (sin Docker)
   Uso: .\scripts\dev.ps1
   ============================================ #>
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $projectRoot
try {
    # Crear carpeta de datos si no existe
    if (-not (Test-Path ".\data")) { New-Item -ItemType Directory -Path ".\data" | Out-Null }

    # Activar venv si existe
    if (Test-Path ".\.venv\Scripts\Activate.ps1") {
        & ".\.venv\Scripts\Activate.ps1"
    }

    # Cargar variables de .env.dev
    $env:GRADES_DB_PATH = ".\data\grades.db"
    $env:STREAMLIT_ENV  = "dev"

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  AMBIENTE: DEV (local, sin Docker)"     -ForegroundColor Green
    Write-Host "  BD: .\data\grades.db"                  -ForegroundColor Green
    Write-Host "  URL: http://localhost:8501"             -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""

    .\.venv\Scripts\python.exe -m streamlit run app.py `
        --server.port=8501 `
        --server.headless=true `
        --browser.gatherUsageStats=false
}
finally {
    Pop-Location
}
