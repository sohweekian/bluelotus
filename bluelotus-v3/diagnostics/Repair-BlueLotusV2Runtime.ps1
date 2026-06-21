param(
    [string]$Root = "C:\bluelotus3"
)

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok($Message) {
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Assert-UnderRoot($Path) {
    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd("\") + "\"
    $pathFull = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
    if (-not ($pathFull + "\").StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe path outside root: $Path"
    }
}

function Remove-SafeDirectory($Path) {
    Assert-UnderRoot $Path
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Find-Python {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            & py -3.13 --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return @{ Mode = "py"; Command = "py"; Args = @("-3.13") }
            }
        } catch {}
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ Mode = "python"; Command = $python.Source; Args = @() }
    }
    throw "Python 3.13 was not found. Install Python 3.13.x first."
}

function Invoke-BasePython($PythonInfo, [string[]]$ArgsList) {
    if ($PythonInfo.Mode -eq "py") {
        & py -3.13 @ArgsList
    } else {
        & $PythonInfo.Command @ArgsList
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $($ArgsList -join ' ')"
    }
}

if (-not (Test-Path $Root)) {
    throw "BlueLotus root not found: $Root"
}

$requirements = Join-Path $Root "installer\requirements-bluelotus-v2.txt"
$runtimeGuard = Join-Path $Root "diagnostics\bluelotus_runtime_guard.py"
$venv = Join-Path $Root ".venv"
$tmpVenv = Join-Path $Root ".venv_build_tmp"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupVenv = Join-Path $Root ".venv_backup_$stamp"

Assert-UnderRoot $venv
Assert-UnderRoot $tmpVenv
Assert-UnderRoot $backupVenv

if (-not (Test-Path $requirements)) {
    throw "Requirements file missing: $requirements"
}
if (-not (Test-Path $runtimeGuard)) {
    throw "Runtime guard missing: $runtimeGuard"
}

Write-Step "Finding Python 3.13"
$pythonInfo = Find-Python
Write-Ok "Base Python: $($pythonInfo.Command) $($pythonInfo.Args -join ' ')"

Write-Step "Cleaning temporary runtime build directory"
Remove-SafeDirectory $tmpVenv

Write-Step "Creating temporary virtual environment"
Invoke-BasePython $pythonInfo @("-m", "venv", $tmpVenv)
$tmpPython = Join-Path $tmpVenv "Scripts\python.exe"
if (-not (Test-Path $tmpPython)) {
    throw "Temporary Python was not created: $tmpPython"
}
Write-Ok "Temporary venv created"

try {
    Write-Step "Installing pinned BlueLotus dependencies into temporary venv"
    & $tmpPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
    & $tmpPython -m pip install --no-cache-dir -r $requirements
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
    Write-Ok "Dependencies installed"

    Write-Step "Validating imports inside temporary venv"
    $validation = @'
import importlib
mods = [
    "anthropic", "bs4", "dateutil", "docx", "dotenv", "feedparser",
    "lxml", "matplotlib", "moomoo", "mysql.connector", "numpy",
    "openai", "pandas", "PIL", "requests", "rich", "schedule",
    "seaborn", "simplejson", "tqdm", "vaderSentiment", "yaml"
]
failures = []
for mod in mods:
    try:
        importlib.import_module(mod)
    except Exception as exc:
        failures.append((mod, str(exc)))
if failures:
    for mod, err in failures:
        print(f"{mod}: {err}")
    raise SystemExit(1)
print(f"Import validation passed for {len(mods)} modules.")
'@
    $validationScript = Join-Path $tmpVenv "validate_imports.py"
    Set-Content -Path $validationScript -Value $validation -Encoding UTF8
    & $tmpPython $validationScript
    if ($LASTEXITCODE -ne 0) { throw "Temporary venv import validation failed" }
    Write-Ok "Temporary venv imports validated"

    Write-Step "Promoting temporary venv to production .venv"
    if (Test-Path $venv) {
        Move-Item -LiteralPath $venv -Destination $backupVenv
        Write-Ok "Existing .venv backed up to $backupVenv"
    }
    Move-Item -LiteralPath $tmpVenv -Destination $venv
    Write-Ok "Production .venv promoted"

    Write-Step "Running runtime guard from production .venv"
    $venvPython = Join-Path $venv "Scripts\python.exe"
    & $venvPython $runtimeGuard --root $Root --require-venv --archive --label runtime_repair
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime guard failed after venv promotion"
    }
    Write-Ok "Runtime guard passed"
} catch {
    Write-Host "[FAIL] Runtime repair failed: $($_.Exception.Message)" -ForegroundColor Red
    if (Test-Path $tmpVenv) {
        Remove-SafeDirectory $tmpVenv
    }
    if ((Test-Path $backupVenv) -and -not (Test-Path $venv)) {
        Move-Item -LiteralPath $backupVenv -Destination $venv
        Write-Host "[OK] Previous .venv restored" -ForegroundColor Green
    }
    throw
}

Write-Host ""
Write-Host "BlueLotus V2 runtime repair completed." -ForegroundColor Green

