param(
  [string]$ProjectRoot = $env:BLUELOTUS_PROJECT_ROOT
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
  $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path

$findings = @()

$newsPath = Join-Path $root 'news_reporter_agency'
if (Test-Path -LiteralPath $newsPath) {
  $newsFiles = Get-ChildItem -LiteralPath $newsPath -Recurse -File -Include *.py,*.ps1,*.bat |
    Where-Object { $_.FullName -notmatch '\\__pycache__\\' }
  foreach ($file in $newsFiles) {
    $hits = Select-String -LiteralPath $file.FullName -Pattern 'mysql|v3_db|db_writers|INSERT INTO|UPDATE ' -AllMatches -ErrorAction SilentlyContinue
    foreach ($hit in $hits) {
      $findings += [pscustomobject]@{
        File = $file.FullName
        Line = $hit.LineNumber
        Reason = "News Reporter must not write to MySQL."
        Text = $hit.Line.Trim()
      }
    }
  }
}

$dbPath = Join-Path $root 'db'
if (Test-Path -LiteralPath $dbPath) {
  $dbFiles = Get-ChildItem -LiteralPath $dbPath -Recurse -File -Include *.py |
    Where-Object { $_.FullName -notmatch '\\__pycache__\\' }
  foreach ($file in $dbFiles) {
    $hits = Select-String -LiteralPath $file.FullName -Pattern 'MYSQL_HOST|MYSQL_DATABASE|bluelotus2' -AllMatches -ErrorAction SilentlyContinue
    foreach ($hit in $hits) {
      $findings += [pscustomobject]@{
        File = $file.FullName
        Line = $hit.LineNumber
        Reason = "V3 DB code must not use V2/legacy DB config."
        Text = $hit.Line.Trim()
      }
    }
  }
}

if ($findings.Count -gt 0) {
  Write-Host "FAIL = unsafe V3 database write pattern detected"
  $findings | Format-List
  exit 1
}

Write-Host "PASS = V3 database writes isolated; News Reporter has no DB writes"
exit 0
