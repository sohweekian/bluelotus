$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    python -m llm_clients.create_ollama_alias
}
finally {
    Pop-Location
}
