param(
    [string]$InstallPath = "C:\bluelotus3",
    [string]$EnvFile = "",
    [switch]$InstallPythonWithWinget,
    [switch]$InitializeDatabase,
    [string]$MySQLHost = "127.0.0.1",
    [int]$MySQLPort = 3306,
    [string]$DatabaseName = "bluelotus2",
    [string]$MySQLAdminUser = "root",
    [string]$MySQLAdminPassword = "",
    [string]$AppMySQLUser = "bluelotus_app",
    [string]$AppMySQLPassword = "",
    [switch]$CheckMoomoo,
    [switch]$NoShortcuts
)

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok($Message) {
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn($Message) {
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Find-Python {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            & py -3.13 --version *> $null
            if ($LASTEXITCODE -eq 0) { return "py -3.13" }
        } catch {}
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return "python" }
    return ""
}

function Invoke-PythonCommand($PythonCommand, [string[]]$ArgsList) {
    if ($PythonCommand -eq "py -3.13") {
        & py -3.13 @ArgsList
    } else {
        & $PythonCommand @ArgsList
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $PythonCommand $($ArgsList -join ' ')"
    }
}

function Update-EnvFile($Path) {
    if (-not (Test-Path $Path)) { return }
    $text = Get-Content -Raw -Path $Path
    $text = $text -replace '^MYSQL_HOST=.*$', "MYSQL_HOST=$MySQLHost"
    $text = $text -replace '^MYSQL_PORT=.*$', "MYSQL_PORT=$MySQLPort"
    $text = $text -replace '^MYSQL_DATABASE=.*$', "MYSQL_DATABASE=$DatabaseName"
    $text = $text -replace '^MYSQL_USER=.*$', "MYSQL_USER=$AppMySQLUser"
    if ($AppMySQLPassword) { $text = $text -replace '^MYSQL_PASSWORD=.*$', "MYSQL_PASSWORD=$AppMySQLPassword" }
    $text = $text -replace '^DB_HOST=.*$', "DB_HOST=$MySQLHost"
    $text = $text -replace '^DB_PORT=.*$', "DB_PORT=$MySQLPort"
    $text = $text -replace '^DB_NAME=.*$', "DB_NAME=$DatabaseName"
    $text = $text -replace '^DB_USER=.*$', "DB_USER=$AppMySQLUser"
    if ($AppMySQLPassword) { $text = $text -replace '^DB_PASSWORD=.*$', "DB_PASSWORD=$AppMySQLPassword" }
    Set-Content -Path $Path -Value $text -Encoding UTF8
}

function New-Shortcut($Name, $Target, $Arguments, $WorkingDirectory) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktop $Name
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $Target
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.Save()
}

$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$payloadRoot = Join-Path $packageRoot "payload\bluelotus2"
$requirements = Join-Path $packageRoot "requirements-bluelotus-v2.txt"
$envTemplate = Join-Path $packageRoot ".env.template"
$schemaPath = Join-Path $packageRoot "schema\bluelotus2_schema_mysql_8_4_9.sql"
$initScript = Join-Path $packageRoot "scripts\initialize_database.py"
$validateScript = Join-Path $packageRoot "scripts\validate_environment.py"

if ($InstallPath -ne "C:\bluelotus3") {
    Write-Warn "BlueLotus V2 production modules contain hardcoded C:\bluelotus3 paths. Installing elsewhere is not recommended."
}

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Warn "PowerShell is not running as Administrator. C:\ installation and shortcut creation may fail."
}

Write-Step "Checking package"
if (-not (Test-Path $payloadRoot)) { throw "Package payload missing: $payloadRoot" }
if (-not (Test-Path $requirements)) { throw "Requirements file missing: $requirements" }
if (-not (Test-Path $schemaPath)) { throw "Schema file missing: $schemaPath" }
Write-Ok "Package files found"

Write-Step "Checking Python 3.13 runtime"
$pythonCommand = Find-Python
if (-not $pythonCommand -and $InstallPythonWithWinget) {
    Write-Step "Installing Python 3.13 with winget"
    winget install --id Python.Python.3.13 -e --accept-package-agreements --accept-source-agreements
    $pythonCommand = Find-Python
}
if (-not $pythonCommand) {
    throw "Python was not found. Install Python 3.13.x first, or rerun with -InstallPythonWithWinget."
}
Write-Ok "Python command: $pythonCommand"

Write-Step "Copying BlueLotus V2 application to $InstallPath"
New-Item -ItemType Directory -Force -Path $InstallPath | Out-Null
Copy-Item -Path (Join-Path $payloadRoot "*") -Destination $InstallPath -Recurse -Force
Copy-Item -Path (Join-Path $packageRoot "bin\run_bluelotus_v2_once_installed.bat") -Destination (Join-Path $InstallPath "run_bluelotus_v2_once_installed.bat") -Force
Copy-Item -Path (Join-Path $packageRoot "bin\run_bluelotus_v2_hourly_installed.bat") -Destination (Join-Path $InstallPath "run_bluelotus_v2_hourly_installed.bat") -Force
Copy-Item -Path $envTemplate -Destination (Join-Path $InstallPath ".env.template") -Force
Write-Ok "Application copied"

Write-Step "Preparing environment file"
$installedEnv = Join-Path $InstallPath ".env"
if ($EnvFile) {
    if (-not (Test-Path $EnvFile)) { throw "EnvFile not found: $EnvFile" }
    Copy-Item -Path $EnvFile -Destination $installedEnv -Force
    Write-Ok "Private .env copied"
} elseif (-not (Test-Path $installedEnv)) {
    Copy-Item -Path $envTemplate -Destination $installedEnv -Force
    Write-Warn "Created .env from template. Fill missing API keys and passwords before production runs."
}
Update-EnvFile $installedEnv

Write-Step "Creating Python virtual environment"
$venv = Join-Path $InstallPath ".venv"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    Invoke-PythonCommand $pythonCommand @("-m", "venv", $venv)
}
$venvPython = Join-Path $venv "Scripts\python.exe"
Write-Ok "Virtual environment ready: $venv"

Write-Step "Installing Python dependencies"
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $venvPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
Write-Ok "Dependencies installed"

if ($InitializeDatabase) {
    Write-Step "Initializing MySQL database"
    $dbArgs = @(
        "--root", $InstallPath,
        "--schema", $schemaPath,
        "--host", $MySQLHost,
        "--port", "$MySQLPort",
        "--database", $DatabaseName,
        "--admin-user", $MySQLAdminUser,
        "--app-user", $AppMySQLUser
    )
    if ($MySQLAdminPassword) { $dbArgs += @("--admin-password", $MySQLAdminPassword) }
    if ($AppMySQLPassword) { $dbArgs += @("--app-password", $AppMySQLPassword) }
    & $venvPython $initScript @dbArgs
    if ($LASTEXITCODE -ne 0) { throw "Database initialization failed" }
    Write-Ok "Database initialized"
} else {
    Write-Warn "Database initialization skipped. Use MYSQL_8_4_9_INSTALL_GUIDE.md for setup."
}

if (-not $NoShortcuts) {
    Write-Step "Creating desktop shortcuts"
    New-Shortcut "BlueLotus V2 - Run Once.lnk" "$env:ComSpec" "/c `"$InstallPath\run_bluelotus_v2_once_installed.bat`"" $InstallPath
    New-Shortcut "BlueLotus V2 - Hourly Loop.lnk" "$env:ComSpec" "/c `"$InstallPath\run_bluelotus_v2_hourly_installed.bat`"" $InstallPath
    Write-Ok "Desktop shortcuts created"
}

Write-Step "Running deployment validation"
$validateArgs = @("--root", $InstallPath)
if ($CheckMoomoo) { $validateArgs += "--check-moomoo" }
& $venvPython $validateScript @validateArgs
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Validation reported issues. Fix them before production hourly runs."
} else {
    Write-Ok "Validation passed"
}

Write-Host ""
Write-Host "BlueLotus V2 installation finished." -ForegroundColor Green
Write-Host "Run once : $InstallPath\run_bluelotus_v2_once_installed.bat"
Write-Host "Hourly   : $InstallPath\run_bluelotus_v2_hourly_installed.bat"
Write-Host "Reports  : $InstallPath\research"

