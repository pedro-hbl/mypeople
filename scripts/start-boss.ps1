# Launch Brave pointing at the Kimi web UI running inside WSL.

param(
    [string]$Distro = "Ubuntu-24.04",
    [int]$Port = 5494
)

# Get the first IP WSL reports.
$wslIp = (wsl -d $Distro -e bash -lc "hostname -I" 2>&1).Split()[0].Trim()
if (-not $wslIp) {
    Write-Host "Could not determine WSL IP. Is WSL running?" -ForegroundColor Red
    exit 1
}

# Read the queue secret from WSL, which start-boss.sh uses as the web auth token.
$secretOutput = wsl -d $Distro -u pedro -e bash -lc "source ~/.config/mypeople/queue.env && echo `$QUEUE_SECRET" 2>&1
$secret = ($secretOutput | Where-Object { $_ -match '^[A-Za-z0-9_-]+$' } | Select-Object -First 1).Trim()
if (-not $secret) {
    Write-Host "Could not read QUEUE_SECRET from ~/.config/mypeople/queue.env. Is install.sh complete?" -ForegroundColor Red
    exit 1
}

$url = "http://${wslIp}:${Port}/?token=${secret}"
Write-Host "Opening Brave at $url" -ForegroundColor Cyan

$bravePath = "${env:ProgramFiles}\BraveSoftware\Brave-Browser\Application\brave.exe"
if (Test-Path $bravePath) {
    Start-Process $bravePath $url
} else {
    Start-Process $url
}
