param(
  [string]$ProjectRoot = $env:BLUELOTUS_PROJECT_ROOT
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
  $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path

$patterns = @(
  'C:\\bluelotus2',
  'C:\\bluelotus3',
  '127\.0\.0\.1',
  'localhost',
  '11434',
  '11111',
  '3306',
  'qwen3:4b',
  'qwen3:8b',
  'bluelotus2',
  'bluelotus3'
)

$businessPaths = @(
  (Join-Path $root 'llm_clients')
  (Join-Path $root 'db')
  (Join-Path $root 'orchestration')
  (Join-Path $root 'agents')
  (Join-Path $root 'chief_strategist')
  (Join-Path $root 'thesis_engine')
  (Join-Path $root 'archive')
)

$findings = @()
foreach ($path in $businessPaths) {
  if (-not (Test-Path -LiteralPath $path)) { continue }
  $files = Get-ChildItem -LiteralPath $path -Recurse -File -Include *.py,*.ps1,*.bat |
    Where-Object {
      $_.FullName -notmatch '\\__pycache__\\' -and
      $_.FullName -notmatch '\\build\\' -and
      $_.FullName -notmatch '\\dist\\'
    }
  foreach ($file in $files) {
    foreach ($pattern in $patterns) {
      $hits = Select-String -LiteralPath $file.FullName -Pattern $pattern -AllMatches -ErrorAction SilentlyContinue
      foreach ($hit in $hits) {
        $findings += [pscustomobject]@{
          File = $file.FullName
          Line = $hit.LineNumber
          Pattern = $pattern
          Explanation = "Suspicious environment-specific constant in business logic. Move it to .env, YAML, registry, schema, CLI, or installer parameters."
          Text = $hit.Line.Trim()
        }
      }
    }
  }
}

if ($findings.Count -gt 0) {
  Write-Host "FAIL = suspicious hardcoded values detected"
  $findings | Format-List
  exit 1
}

Write-Host "PASS = no hardcoded production constants in business logic"
exit 0
