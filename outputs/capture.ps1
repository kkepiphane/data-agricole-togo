# Captures d'écran des vues principales (l'application doit tourner sur http://127.0.0.1:8050).
# Usage : powershell -File outputs\capture.ps1 [-Port 8050]
#         -Query ajoute des paramètres d'URL (ex. "&region=Savanes"), -Suffix nomme la variante.
param([int]$Port = 8050, [int]$Width = 1600, [int]$Height = 1500, [string]$Query = "", [string]$Suffix = "",
      [string[]]$Views = @("territoire", "production", "equipements", "cooperatives", "qualite"))

$browser = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) { throw "Edge ou Chrome introuvable." }

$profile = Join-Path $env:TEMP "atlas-capture-profile"
foreach ($view in ($Views -split ",")) {
    $out = Join-Path $PSScriptRoot "vue_$view$Suffix.png"
    $args = @("--headless=new", "--disable-gpu", "--enable-unsafe-swiftshader", "--hide-scrollbars",
        "--disable-features=msEdgeSidebarV2,msHubApps", "--no-first-run",
        "--user-data-dir=$profile", "--window-size=$Width,$Height", "--virtual-time-budget=25000",
        "--screenshot=$out", "http://127.0.0.1:$Port/?vue=$view$Query")
    Start-Process -FilePath $browser -ArgumentList $args -Wait -NoNewWindow
    Write-Output "$view -> $out"
}
