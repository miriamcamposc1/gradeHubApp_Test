<# ============================================
   PROD — Levantar con Docker en puerto 8501
   Uso: .\scripts\prod.ps1 [up|down|logs|rebuild]
   ============================================ #>
param(
    [ValidateSet("up","down","logs","rebuild")]
    [string]$Action = "up"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot

$composeArgs = @(
    "--env-file", ".env.prod",
    "-f", "docker-compose.yml",
    "-f", "docker-compose.prod.yml"
)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AMBIENTE: PROD (Docker, puerto 8501)"  -ForegroundColor Cyan
Write-Host "  URL: http://localhost:8501"             -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

switch ($Action) {
    "up"      { docker compose @composeArgs up --build -d; Write-Host "`nContenedor corriendo en background. Usa '.\scripts\prod.ps1 logs' para ver logs." -ForegroundColor Green }
    "down"    { docker compose @composeArgs down }
    "logs"    { docker compose @composeArgs logs -f }
    "rebuild" { docker compose @composeArgs up --build --force-recreate -d }
}

Pop-Location
