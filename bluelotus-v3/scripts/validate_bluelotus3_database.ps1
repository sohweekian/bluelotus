$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    python -m db.v3_db_healthcheck
}
finally {
    Pop-Location
}
