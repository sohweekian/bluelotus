param(
  [string]$ProjectRoot = $env:BLUELOTUS_PROJECT_ROOT,
  [string]$ModelRole = $env:OLLAMA_MODEL_ROLE
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
  $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$env:BLUELOTUS_PROJECT_ROOT = (Resolve-Path -LiteralPath $ProjectRoot).Path
Set-Location -LiteralPath $env:BLUELOTUS_PROJECT_ROOT

if ($ModelRole) {
  $env:OLLAMA_MODEL_ROLE = $ModelRole
}

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
  Write-Host "FAIL: Ollama is not installed or not on PATH."
  Write-Host "Install Ollama from the official installer, then rerun this script."
  exit 1
}

$modelName = python -c "from llm_clients.config_loader import load_dotenv; from llm_clients.model_router import get_default_model_role, get_model_config; load_dotenv(); print(get_model_config(get_default_model_role())['model_name'])"
if (-not $modelName) {
  Write-Host "FAIL: Could not resolve configured model name."
  exit 1
}

Write-Host "Checking Ollama API..."
python -c "import json, urllib.request; from llm_clients.config_loader import load_dotenv, env_required, load_main_config; load_dotenv(); cfg=load_main_config(); url=env_required('OLLAMA_BASE_URL').rstrip('/') + cfg['ollama']['tags_endpoint_path']; urllib.request.urlopen(url, timeout=10).read(); print('Ollama API reachable')"
if ($LASTEXITCODE -ne 0) {
  Write-Host "Ollama API is not reachable yet. Start Ollama, then rerun this script."
  exit 1
}

Write-Host "Pulling configured model: $modelName"
ollama pull $modelName
if ($LASTEXITCODE -ne 0) {
  Write-Host "FAIL: Model pull failed."
  exit 1
}

Write-Host "Running infrastructure smoke test..."
cmd /c run_qwen3_4b_smoke_test.bat
exit $LASTEXITCODE
