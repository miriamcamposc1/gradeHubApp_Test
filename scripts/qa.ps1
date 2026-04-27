<# ============================================
   QA — Levantar con Docker en puerto 8502
   Uso: .\scripts\qa.ps1 [up|down|logs|rebuild]
   ============================================ #>
param(
    [ValidateSet("up","down","logs","rebuild")]
    [string]$Action = "up"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot

$composeArgs = @(
    "--env-file", ".env.qa",
    "-f", "docker-compose.yml",
    "-f", "docker-compose.qa.yml"
)

Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "  AMBIENTE: QA (Docker, puerto 8502)"    -ForegroundColor Yellow
Write-Host "  URL: http://localhost:8502"             -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""

switch ($Action) {
    "up"      { docker compose @composeArgs up --build -d; docker compose @composeArgs logs -f }
    "down"    { docker compose @composeArgs down }
    "logs"    { docker compose @composeArgs logs -f }
    "rebuild" { docker compose @composeArgs up --build --force-recreate -d }
}

Pop-Location
