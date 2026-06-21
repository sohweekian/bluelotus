param(
  [string]$ProjectRoot = $env:BLUELOTUS_PROJECT_ROOT
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
  $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$env:BLUELOTUS_PROJECT_ROOT = (Resolve-Path -LiteralPath $ProjectRoot).Path
Set-Location -LiteralPath $env:BLUELOTUS_PROJECT_ROOT

python tests\test_ollama_connection.py
exit $LASTEXITCODE
