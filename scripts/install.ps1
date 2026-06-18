#Requires -RunAsAdministrator
# mypeople install helper for Windows.
#
# This script does NOT replace the WSL install — it just checks prerequisites
# and then runs ./install.sh inside WSL for you.

param(
    [string]$Distro = "Ubuntu-24.04"
)

function Test-WSL {
    $out = wsl --list --verbose 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WSL is not installed or not on PATH. Please install WSL2 first:" -ForegroundColor Red
        Write-Host "  wsl --install -d $Distro"
        exit 1
    }
    if (-not ($out -match $Distro)) {
        Write-Host "Distro '$Distro' not found. Installed distros:" -ForegroundColor Red
        Write-Host $out
        exit 1
    }
}

function Test-KimiInWSL {
    $hasKimi = wsl -d $Distro -e bash -lc "command -v kimi" 2>&1
    if ($LASTEXITCODE -ne 0 -or -not $hasKimi) {
        Write-Host "kimi not found inside WSL. Install Kimi Code CLI in WSL first:" -ForegroundColor Red
        Write-Host "  https://moonshotai.github.io/kimi-cli/"
        exit 1
    }
}

Test-WSL
Test-KimiInWSL

$repoPath = Split-Path -Parent $PSScriptRoot | ForEach-Object { $_ -replace '\\', '/' }
$wslRepo = wsl -d $Distro -e bash -lc "wslpath '$repoPath'" 2>&1

Write-Host "Running mypeople install inside WSL ($Distro)..." -ForegroundColor Cyan
wsl -d $Distro -e bash -lc "cd '$wslRepo' && ./scripts/install.sh"

Write-Host ""
Write-Host "Install complete. Next steps:" -ForegroundColor Green
Write-Host "  1. In WSL: cd '$wslRepo' && ./scripts/start-queue-server.sh"
Write-Host "  2. In WSL: ./scripts/start-boss.sh"
Write-Host "  3. On Windows: ./scripts/start-boss.ps1"
