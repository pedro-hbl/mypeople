# Launch Brave pointing at the mypeople dashboard running inside WSL.

param(
    [string]$Distro = "Ubuntu-24.04",
    [int]$Port = 9900
)

$wslIp = (wsl -d $Distro -e bash -lc "hostname -I" 2>&1).Split()[0].Trim()
if (-not $wslIp) {
    Write-Host "Could not determine WSL IP. Is WSL running?" -ForegroundColor Red
    exit 1
}

$url = "http://${wslIp}:${Port}/dashboard"
Write-Host "Opening Brave at $url" -ForegroundColor Cyan

$bravePath = "${env:ProgramFiles}\BraveSoftware\Brave-Browser\Application\brave.exe"
if (Test-Path $bravePath) {
    Start-Process $bravePath $url
} else {
    Start-Process $url
}
