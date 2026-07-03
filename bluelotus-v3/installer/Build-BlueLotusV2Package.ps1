param(
    [string]$SourceRoot = "C:\bluelotus3",
    [string]$OutputRoot = "C:\bluelotus3\installer\dist"
)

$ErrorActionPreference = "Stop"

# ── Helper: robocopy a directory tree, skipping dev/runtime artefacts ─────────
function Copy-SourceTree($From, $To) {
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    $excludeDirs  = @("__pycache__", "archive", "temp", ".venv", "installer", "installer_macos", "build", "dist")
    $excludeFiles = @("*.pyc", "*.log", "*.xlsx", "*.docx", ".env",
                      "analyst_targets.json", "research_report.txt",
                      "research_forecast_accuracy_report.txt")
    $args = @($From, $To, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    foreach ($d in $excludeDirs) { $args += @("/XD", $d) }
    foreach ($f in $excludeFiles) { $args += @("/XF", $f) }
    robocopy @args | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed: $From → $To" }
}

# ── Helper: robocopy a directory tree, skipping NOTHING (for governance configs)
function Copy-ConfigTree($From, $To) {
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    $excludeDirs = @("__pycache__", "archive", "temp")
    $args = @($From, $To, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    foreach ($d in $excludeDirs) { $args += @("/XD", $d) }
    robocopy @args | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed: $From → $To" }
}

# ── Paths ─────────────────────────────────────────────────────────────────────
$installerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$stamp         = Get-Date -Format "yyyyMMdd_HHmmss"
$packageName   = "BlueLotusV2_Windows_Install_$stamp"
$buildRoot     = Join-Path $installerRoot "build\$packageName"
$payload       = Join-Path $buildRoot "payload\bluelotus2"

if (Test-Path $buildRoot) { Remove-Item -Recurse -Force $buildRoot }
New-Item -ItemType Directory -Force -Path $payload | Out-Null
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

Write-Host ""
Write-Host "============================================================"
Write-Host "  BlueLotus V2 Package Builder"
Write-Host "  Package : $packageName"
Write-Host "  Source  : $SourceRoot"
Write-Host "  Output  : $OutputRoot"
Write-Host "============================================================"
Write-Host ""

# ── 1. Source code folders ────────────────────────────────────────────────────
Write-Host "[1/7] Copying source code folders..."

foreach ($dir in @("core", "mid", "research", "documentation", "diagnostics")) {
    $src = Join-Path $SourceRoot $dir
    if (Test-Path $src) {
        Write-Host "      $dir\"
        Copy-SourceTree $src (Join-Path $payload $dir)
    } else {
        Write-Host "      SKIP (not found): $dir"
    }
}

# ── 2. Governance folder (includes JSON config files — NOT private data) ──────
Write-Host "[2/7] Copying governance layer..."
$govSrc = Join-Path $SourceRoot "governance"
$govDst = Join-Path $payload "governance"
if (Test-Path $govSrc) {
    Copy-ConfigTree $govSrc $govDst
    Write-Host "      governance\ (with JSON configs)"
} else {
    Write-Host "      SKIP (not found): governance"
}

# ── 3. Root batch files and launchers ─────────────────────────────────────────
Write-Host "[3/7] Copying root batch files..."
$rootBatFiles = @(
    "run_v2_pipeline.bat",
    "start_daemons.bat",
    "run_bluelotus_v2_smoke_hygiene.bat",
    "run_bluelotus_v2_dataset_contract.bat",
    "run_bluelotus_v2_runtime_guard.bat",
    "repair_bluelotus_v2_runtime.bat"
)
foreach ($f in $rootBatFiles) {
    $src = Join-Path $SourceRoot $f
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination (Join-Path $payload $f) -Force
        Write-Host "      $f"
    } else {
        Write-Host "      SKIP (not found): $f"
    }
}

# ── 4. Empty runtime directories (placeholders so the app can write to them) ──
Write-Host "[4/7] Creating empty runtime directories..."
$runtimeDirs = @(
    "data",
    "data\archive",
    "data\audit",
    "data\brier",
    "data\cio",
    "data\dashboard",
    "data\events",
    "data\execution",
    "data\forecasts",
    "data\frontend",
    "data\governance",
    "data\history",
    "data\portfolio",
    "data\raw",
    "data\reference",
    "data\regime",
    "data\risk",
    "data\strategist",
    "data\thesis",
    "logs",
    "reports",
    "research",
    "temp"
)
foreach ($d in $runtimeDirs) {
    $target = Join-Path $payload $d
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    # Write a placeholder so the directory is preserved in the ZIP
    Set-Content -Path (Join-Path $target ".gitkeep") -Value "" -Encoding UTF8
}
Write-Host "      $($runtimeDirs.Count) directories created"

# ── 5. Installer root files ───────────────────────────────────────────────────
Write-Host "[5/7] Copying installer files..."
$installerFiles = @(
    "Install-BlueLotusV2.ps1",
    "Build-BlueLotusV2Package.ps1",
    "requirements-bluelotus-v2.txt",
    ".env.template",
    "README_INSTALL_WINDOWS.md",
    "MYSQL_8_4_9_INSTALL_GUIDE.md",
    "DEPLOYMENT_SECURITY_PROTOCOL.md"
)
foreach ($f in $installerFiles) {
    $src = Join-Path $installerRoot $f
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $buildRoot -Force
        Write-Host "      $f"
    } else {
        Write-Host "      SKIP (not found): $f"
    }
}

# Copy installer sub-folders (scripts/, schema/, bin/)
foreach ($subdir in @("scripts", "schema", "bin")) {
    $src = Join-Path $installerRoot $subdir
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $buildRoot -Recurse -Force
        Write-Host "      $subdir\"
    }
}

# Also copy the System Manual into the installer root for easy reference
$manualSrc = Join-Path $SourceRoot "documentation\BlueLotus_V2_System_Manual.md"
if (Test-Path $manualSrc) {
    Copy-Item -Path $manualSrc -Destination $buildRoot -Force
    Write-Host "      BlueLotus_V2_System_Manual.md (documentation)"
}

# ── 6. Package manifest ───────────────────────────────────────────────────────
Write-Host "[6/7] Writing package manifest..."
$manifest = @"
BlueLotus V2 Windows Installation Package
==========================================
Package   : $packageName
Generated : $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Source    : $SourceRoot
Target    : C:\bluelotus3 (mandatory — hardcoded production path)
Builder   : Windows Platform Team (Claude Code & Codex)

INCLUDED IN THIS PACKAGE
─────────────────────────
Source code folders:
  core\                   MySQL connection layer (db.py, db_writers.py)
  mid\                    Market Intelligence Data layer
    fetch_*.py              15+ data fetchers (Finnhub, Moomoo, RSS, APIs)
    ingest.py               Signal ingestion engine (50+ sources)
    export_dataset_raw.py   Canonical JSON export from MySQL
    historical_risk_model.py  VaR / Expected Shortfall computation
    institutional_quant_pipeline.py  Readiness scoring
    run_monitoring_alerts.py  Alert generation
    bluelotus_publisher.py   GitHub Pages + portfolio_live.json publisher
    news_probe_daemon.py     Watch Tower: RSS news every 10 min → Telegram
    thesis_probe_daemon.py   Watch Tower: Gold thesis live probe every 10 min
  research\               Report generation
    research_report_generator.py     Word + Excel report
    research_report_generator_r6.py  TXT report
  governance\             Governance and approval layer
    governance_gate.py              Release approval gate
    scenario_overlay_engine.py      Breaking catalyst overlay
    regression_tests.py             61 automated regression tests
    governance_config.json          Gate configuration
    report_contract.json            Report schema contract
    breaking_catalyst_rules.json    Catalyst detection rules
  diagnostics\            Runtime validation and repair tools
  documentation\          Architecture and system manual
    BlueLotus_V2_System_Manual.md   Full system manual for Wee Loon & Wee Lian

Root batch files:
  run_v2_pipeline.bat     Main 39-minute pipeline loop
  start_daemons.bat       Starts news + thesis probe daemons
  run_bluelotus_v2_*.bat  Diagnostic runners

Installer files:
  Install-BlueLotusV2.ps1           Automated installer script
  requirements-bluelotus-v2.txt     Pinned Python packages
  .env.template                     Environment configuration template
  README_INSTALL_WINDOWS.md         Installation guide
  MYSQL_8_4_9_INSTALL_GUIDE.md      MySQL setup guide
  schema\bluelotus2_schema_mysql_8_4_9.sql  Empty database schema
  scripts\initialize_database.py    Database initialiser
  scripts\validate_environment.py   Post-install validator
  bin\run_bluelotus_v2_once_installed.bat
  bin\run_bluelotus_v2_hourly_installed.bat

Empty runtime directories (created ready for pipeline output):
  data\frontend\           dataset_raw.json lives here
  data\governance\         approved_operating_truth.json lives here
  data\audit\  data\risk\  data\thesis\  data\cio\  etc.
  logs\                    Pipeline and daemon log files
  reports\                 Generated reports (TXT, DOCX, XLSX)

NOT INCLUDED (private, machine-specific, or runtime output)
────────────────────────────────────────────────────────────
  .env                     Private credentials (never shipped)
  .venv\                   Virtual environment (built on target)
  data\frontend\dataset_raw.json   Live data export (regenerated on first run)
  data\governance\approved_*.json  Governance outputs (regenerated on first run)
  reports\*.docx / *.xlsx / *.txt  Generated reports (regenerated on first run)
  logs\*.log               Runtime logs
  Any MySQL data rows      All database content stays on source machine

INSTALL STEPS (QUICK REFERENCE)
─────────────────────────────────
1.  Install Python 3.13 (tick "Add to PATH")
2.  Install MySQL 8.4.9 LTS — see MYSQL_8_4_9_INSTALL_GUIDE.md
3.  Install Git for Windows
4.  Install Moomoo Desktop + Moomoo OpenD
5.  Extract this package anywhere on the target machine
6.  Open PowerShell as Administrator:
      Set-ExecutionPolicy -Scope Process Bypass
      cd <extracted folder>
      .\Install-BlueLotusV2.ps1 -EnvFile <path to your .env> -InitializeDatabase -MySQLAdminUser root -MySQLAdminPassword "ROOT_PW" -AppMySQLUser bluelotus_app -AppMySQLPassword "APP_PW"
7.  Start Moomoo OpenD, then validate:
      C:\bluelotus3\.venv\Scripts\python.exe scripts\validate_environment.py --root C:\bluelotus3 --check-moomoo
8.  Run first pipeline cycle:
      C:\bluelotus3\run_v2_pipeline.bat
9.  Start watch tower daemons (separate window):
      C:\bluelotus3\start_daemons.bat

DOCTRINE
─────────
  Database is memory.  Python extracts.  JSON publishes.  HTML displays.
  CIO executes manually.  No automated trading.  No order routing.
  All execution authority: CIO_ONLY_MANUAL.
"@
Set-Content -Path (Join-Path $buildRoot "PACKAGE_MANIFEST.txt") -Value $manifest -Encoding UTF8
Write-Host "      PACKAGE_MANIFEST.txt"

# ── 7. Compress to ZIP ────────────────────────────────────────────────────────
Write-Host "[7/7] Compressing package to ZIP..."
$zipPath = Join-Path $OutputRoot "$packageName.zip"
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path (Join-Path $buildRoot "*") -DestinationPath $zipPath -Force

$zipSize = (Get-Item $zipPath).Length
$zipSizeMB = [math]::Round($zipSize / 1MB, 1)

Write-Host ""
Write-Host "============================================================"
Write-Host "  PACKAGE READY" -ForegroundColor Green
Write-Host "  File : $zipPath"
Write-Host "  Size : $zipSizeMB MB"
Write-Host "============================================================"
Write-Host ""
Write-Host "Distribute this ZIP to Wee Loon / Wee Lian."
Write-Host "They extract it and run Install-BlueLotusV2.ps1 as Administrator."
Write-Host ""

