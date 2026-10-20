<#
.SYNOPSIS
    Builds the complete Windows distribution package for Crystal AI
.DESCRIPTION
    Compiles frontend assets, packages the Electron desktop harness,
    and produces an NSIS installer (.exe) and portable zip in dist-desktop/.
#>

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "     Building Crystal Windows Distribution   " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# 1. Build Frontend
Write-Host "`n[1/3] Building frontend assets with Vite..." -ForegroundColor Yellow
Push-Location "$RepoRoot\frontend"
& npm run build
Pop-Location

# 2. Prepare Desktop Dependencies
Write-Host "`n[2/3] Setting up Desktop packaging dependencies..." -ForegroundColor Yellow
Push-Location "$RepoRoot\desktop"
if (-not (Test-Path "node_modules")) {
    & npm install
}

# 3. Package Windows Installer & Portable ZIP
Write-Host "`n[3/3] Packaging Windows NSIS Installer (.exe) and Portable ZIP..." -ForegroundColor Yellow
& npm run dist
Pop-Location

$DistPath = "$RepoRoot\dist-desktop"
if (Test-Path $DistPath) {
    Write-Host "`n=============================================" -ForegroundColor Green
    Write-Host "  Build Complete! Artifacts in dist-desktop/: " -ForegroundColor Green
    Write-Host "=============================================" -ForegroundColor Green
    Get-ChildItem -Path $DistPath | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
} else {
    Write-Host "`nDesktop packaging completed." -ForegroundColor Green
}
