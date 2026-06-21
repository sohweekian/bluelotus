#!/usr/bin/env bash
set -u

ROOT="${BLUELOTUS_ROOT:-$HOME/bluelotus2}"
PY="$ROOT/.venv/bin/python"

if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || true)"
fi

if [ -z "${PY:-}" ]; then
  echo "[FAIL] python3 not found."
  exit 1
fi

export BLUELOTUS_ROOT="$ROOT"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

mkdir -p "$ROOT/logs"

echo
echo "============================================================"
echo "Running BlueLotus V2 one-shot pipeline at $(date)"
echo "Root: $ROOT"
echo "============================================================"

cd "$ROOT/mid" || exit 1
"$PY" fetch_analyst_targets.py
"$PY" fetch_capital_flow.py
"$PY" fetch_fundamentals.py
"$PY" fetch_treasury_yields.py
"$PY" fetch_cross_market_confirmation.py
"$PY" fetch_portfolio_readonly.py
"$PY" fetch_corporate_actions.py --limit 200 --sleep-sec 0.02

cd "$ROOT" || exit 1
"$PY" -m mid.ingest

cd "$ROOT/mid" || exit 1
"$PY" fetch_tech_publications.py
"$PY" fetch_conference_calendar.py --rss-scan
"$PY" fetch_ceo_appearances.py
"$PY" fetch_ticker_earnings.py
"$PY" fetch_catalyst_calendar.py
"$PY" fetch_historical_prices.py --portfolio-and-factors --days 180 --sleep-sec 0.55 || echo "Historical price refresh warning: continuing to export/risk."
"$PY" historical_backfill_scheduler.py --batch-size 12 --days 180 --min-rows 90 --sleep-sec 0.55 || echo "Historical backfill scheduler warning: continuing to export/risk."

"$PY" export_dataset_raw.py
"$PY" archive_dataset_snapshot.py --no-signal || echo "Dataset snapshot archive warning: continuing to recovery/risk."
"$PY" run_freshness_recovery.py || echo "Freshness recovery warning: continuing to dataset export/risk."
"$PY" export_dataset_raw.py
"$PY" archive_dataset_snapshot.py --no-signal
"$PY" historical_risk_model.py --lookback-days 180 || echo "Historical risk model warning: continuing to dataset export."
"$PY" export_dataset_raw.py
"$PY" archive_dataset_snapshot.py --no-signal
"$PY" seed_cio_decision_journal.py || echo "CIO decision journal warning: continuing to dataset export."
"$PY" export_dataset_raw.py
"$PY" archive_dataset_snapshot.py --no-signal
"$PY" seed_thesis_lifecycle.py || echo "Thesis lifecycle warning: continuing to monitoring/export."
"$PY" export_dataset_raw.py
"$PY" archive_dataset_snapshot.py --no-signal
"$PY" run_monitoring_alerts.py || echo "Monitoring governance warning: continuing to dataset export."
"$PY" export_dataset_raw.py
"$PY" archive_dataset_snapshot.py --no-signal
"$PY" institutional_quant_pipeline.py || echo "Institutional quant process warning: continuing to dataset export."
"$PY" export_dataset_raw.py
"$PY" archive_dataset_snapshot.py --no-signal

cd "$ROOT/research" || exit 1
"$PY" bluelotus_superforecast_engine.py || echo "BlueLotus superforecast warning: continuing to resolution/reporting."
"$PY" forecast_resolution_tracker.py || echo "Forecast resolution warning: continuing to comparison/reporting."
"$PY" forecast_method_comparison.py || echo "Forecast method comparison warning: continuing to dataset export/reporting."

cd "$ROOT/mid" || exit 1
"$PY" run_monitoring_alerts.py || echo "Monitoring governance warning: continuing to final dataset export/reporting."
"$PY" export_dataset_raw.py
"$PY" archive_dataset_snapshot.py

cd "$ROOT/research" || exit 1
"$PY" research_report_generator.py

echo
echo "Pipeline completed at $(date)"
echo "Report: $ROOT/research/research_report.txt"
