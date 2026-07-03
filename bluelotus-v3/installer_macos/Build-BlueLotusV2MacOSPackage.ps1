param(
    [string]$SourceRoot = "C:\bluelotus3",
    [string]$OutputRoot = "C:\bluelotus3\installer_macos\dist"
)

$ErrorActionPreference = "Stop"

function Copy-Tree($From, $To) {
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    $excludeDirs = @("__pycache__", "archive", "temp", ".venv", "installer", "installer_macos")
    $excludeFiles = @(
        "*.pyc",
        "*.log",
        "*.xlsx",
        "*.docx",
        "*.json",
        "*.bat",
        ".env",
        "analyst_targets.json",
        "research_report.txt",
        "research_forecast_accuracy_report.txt"
    )
    $args = @($From, $To, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    foreach ($d in $excludeDirs) { $args += @("/XD", $d) }
    foreach ($f in $excludeFiles) { $args += @("/XF", $f) }
    robocopy @args | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed for $From" }
}

function Write-LF($Path) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    $text = [System.IO.File]::ReadAllText($Path)
    $text = $text -replace "`r`n", "`n"
    $text = $text -replace "`r", "`n"
    [System.IO.File]::WriteAllText($Path, $text, $enc)
}

$installerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$packageName = "BlueLotusV2_MacOS_Collector_$stamp"
$buildRoot = Join-Path $installerRoot "build\$packageName"
$payload = Join-Path $buildRoot "payload\bluelotus2"

if (Test-Path $buildRoot) { Remove-Item -Recurse -Force $buildRoot }
New-Item -ItemType Directory -Force -Path $payload | Out-Null
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

Write-Host "Building BlueLotus V2 macOS collector package: $packageName"

foreach ($dir in @("core", "mid", "news", "research", "documentation")) {
    Copy-Tree (Join-Path $SourceRoot $dir) (Join-Path $payload $dir)
}

foreach ($file in @("moomoo_intelligence.py", "gitignore.env")) {
    $src = Join-Path $SourceRoot $file
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination (Join-Path $payload $file) -Force
    }
}

foreach ($dir in @(
    "data",
    "data\archive",
    "data\audit",
    "data\brier",
    "data\forecasts",
    "data\frontend",
    "data\frontend\archive",
    "data\history",
    "data\portfolio",
    "data\reference",
    "data\regime",
    "data\risk",
    "data\thesis",
    "logs",
    "reports",
    "temp"
)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $payload $dir) | Out-Null
}

python (Join-Path $installerRoot "scripts\patch_payload_for_macos.py") $payload
if ($LASTEXITCODE -ne 0) { throw "macOS payload patch failed" }

Copy-Item -Path (Join-Path $installerRoot "install_bluelotus_v2_macos.sh") -Destination $buildRoot -Force
Copy-Item -Path (Join-Path $installerRoot "Build-BlueLotusV2MacOSPackage.ps1") -Destination $buildRoot -Force
Copy-Item -Path (Join-Path $installerRoot "requirements-bluelotus-v2.txt") -Destination $buildRoot -Force
Copy-Item -Path (Join-Path $installerRoot ".env.template") -Destination $buildRoot -Force
Copy-Item -Path (Join-Path $installerRoot "README_INSTALL_MACOS.md") -Destination $buildRoot -Force
Copy-Item -Path (Join-Path $installerRoot "MACOS_MYSQL_8_4_9_INSTALL_GUIDE.md") -Destination $buildRoot -Force
Copy-Item -Path (Join-Path $installerRoot "MACOS_DEPLOYMENT_SECURITY_PROTOCOL.md") -Destination $buildRoot -Force
Copy-Item -Path (Join-Path $installerRoot "scripts") -Destination $buildRoot -Recurse -Force
Copy-Item -Path (Join-Path $installerRoot "schema") -Destination $buildRoot -Recurse -Force
Copy-Item -Path (Join-Path $installerRoot "bin") -Destination $buildRoot -Recurse -Force

Get-ChildItem -Path $buildRoot -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force
Get-ChildItem -Path $buildRoot -File -Recurse -Filter "*.pyc" -ErrorAction SilentlyContinue |
    Remove-Item -Force

$shellFiles = @(
    (Join-Path $buildRoot "install_bluelotus_v2_macos.sh"),
    (Join-Path $buildRoot "bin\run_bluelotus_v2_once_macos.sh"),
    (Join-Path $buildRoot "bin\run_bluelotus_v2_hourly_macos.sh")
)
foreach ($sh in $shellFiles) {
    if (Test-Path $sh) { Write-LF $sh }
}

$manifest = @"
BlueLotus V2 macOS Collector Package
Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
SourceRoot: $SourceRoot
Default install target: ~/bluelotus2

Included:
- Production source folders: core, mid, news, research, documentation
- Read-only Moomoo intelligence modules
- macOS-patched project-root paths for active mid/research modules
- MySQL schema-only installer for MySQL Community Server 8.4.9 LTS
- Python virtual environment installer and validator
- One-shot and hourly collector shell runners
- LaunchAgent-capable installer for 24/7 collection

Excluded:
- .env secrets
- Portfolio/data/report runtime outputs
- Python bytecode/cache files
- archive/temp development folders
- generated Excel/Word/JSON/text reports
- moomoo_trader.py legacy order helper

Execution doctrine:
- The package is for research/intelligence extraction only.
- Broker order routing remains CIO-only and is not part of this installer.
"@
Set-Content -Path (Join-Path $buildRoot "PACKAGE_MANIFEST.txt") -Value $manifest -Encoding UTF8

$zipPath = Join-Path $OutputRoot "$packageName.zip"
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path (Join-Path $buildRoot "*") -DestinationPath $zipPath -Force

Write-Host "Package created:"
Write-Host $zipPath

