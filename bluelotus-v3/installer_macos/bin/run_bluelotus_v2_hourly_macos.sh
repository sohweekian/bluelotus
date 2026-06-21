#!/usr/bin/env bash
set -u

ROOT="${BLUELOTUS_ROOT:-$HOME/bluelotus2}"
export BLUELOTUS_ROOT="$ROOT"

mkdir -p "$ROOT/logs"

while true; do
  "$ROOT/run_bluelotus_v2_once_macos.sh" 2>&1 | tee -a "$ROOT/logs/bluelotus_hourly_$(date +%Y%m%d).log"
  echo
  echo "Waiting 3600 seconds before next run..."
  sleep 3600
done
