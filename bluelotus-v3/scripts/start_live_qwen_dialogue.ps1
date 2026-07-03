$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    python -m llm_clients.live_qwen_dialogue
}
finally {
    Pop-Location
}
