@echo off
setlocal
cd /d C:\bluelotus3

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
chcp 65001 >nul

set PYTHON_EXE=C:\bluelotus3\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

echo.
echo ============================================================
echo Running BlueLotus V2 one-shot pipeline at %date% %time%
echo ============================================================

cd /d C:\bluelotus3\mid
"%PYTHON_EXE%" fetch_analyst_targets.py
"%PYTHON_EXE%" fetch_capital_flow.py
"%PYTHON_EXE%" fetch_fundamentals.py
"%PYTHON_EXE%" fetch_treasury_yields.py
"%PYTHON_EXE%" fetch_cross_market_confirmation.py
"%PYTHON_EXE%" fetch_portfolio_readonly.py
"%PYTHON_EXE%" fetch_execution_records_readonly.py --days 180
if errorlevel 1 echo Execution records read-only refresh warning: continuing to export/risk.
"%PYTHON_EXE%" fetch_corporate_actions.py --limit 200 --sleep-sec 0.02

cd /d C:\bluelotus3
"%PYTHON_EXE%" -m mid.ingest

cd /d C:\bluelotus3\mid
"%PYTHON_EXE%" fetch_tech_publications.py
"%PYTHON_EXE%" fetch_conference_calendar.py --rss-scan
"%PYTHON_EXE%" fetch_ceo_appearances.py
"%PYTHON_EXE%" fetch_ticker_earnings.py
"%PYTHON_EXE%" fetch_catalyst_calendar.py
"%PYTHON_EXE%" fetch_historical_prices.py --portfolio-and-factors --days 180 --sleep-sec 0.55
if errorlevel 1 echo Historical price refresh warning: continuing to export/risk.
"%PYTHON_EXE%" historical_backfill_scheduler.py --batch-size 12 --days 180 --min-rows 90 --sleep-sec 0.55
if errorlevel 1 echo Historical backfill scheduler warning: continuing to export/risk.

"%PYTHON_EXE%" export_dataset_raw.py
"%PYTHON_EXE%" archive_dataset_snapshot.py --no-signal
if errorlevel 1 echo Dataset snapshot archive warning: continuing to recovery/risk.
"%PYTHON_EXE%" run_freshness_recovery.py
if errorlevel 1 echo Freshness recovery warning: continuing to dataset export/risk.
"%PYTHON_EXE%" export_dataset_raw.py
"%PYTHON_EXE%" archive_dataset_snapshot.py --no-signal
"%PYTHON_EXE%" historical_risk_model.py --lookback-days 180
if errorlevel 1 echo Historical risk model warning: continuing to dataset export.
"%PYTHON_EXE%" export_dataset_raw.py
"%PYTHON_EXE%" archive_dataset_snapshot.py --no-signal
"%PYTHON_EXE%" seed_cio_decision_journal.py
if errorlevel 1 echo CIO decision journal warning: continuing to dataset export.
"%PYTHON_EXE%" export_dataset_raw.py
"%PYTHON_EXE%" archive_dataset_snapshot.py --no-signal
"%PYTHON_EXE%" seed_thesis_lifecycle.py
if errorlevel 1 echo Thesis lifecycle warning: continuing to monitoring/export.
"%PYTHON_EXE%" record_cio_cognition.py
if errorlevel 1 echo CIO cognition journal warning: continuing to monitoring/export.
"%PYTHON_EXE%" export_dataset_raw.py
"%PYTHON_EXE%" archive_dataset_snapshot.py --no-signal
"%PYTHON_EXE%" run_monitoring_alerts.py
if errorlevel 1 echo Monitoring governance warning: continuing to dataset export.
"%PYTHON_EXE%" export_dataset_raw.py
"%PYTHON_EXE%" archive_dataset_snapshot.py --no-signal
"%PYTHON_EXE%" institutional_quant_pipeline.py
if errorlevel 1 echo Institutional quant process warning: continuing to dataset export.
"%PYTHON_EXE%" export_dataset_raw.py
"%PYTHON_EXE%" archive_dataset_snapshot.py --no-signal

cd /d C:\bluelotus3\research
"%PYTHON_EXE%" bluelotus_superforecast_engine.py
if errorlevel 1 echo BlueLotus superforecast warning: continuing to resolution/reporting.
"%PYTHON_EXE%" forecast_resolution_tracker.py
if errorlevel 1 echo Forecast resolution warning: continuing to comparison/reporting.
"%PYTHON_EXE%" forecast_method_comparison.py
if errorlevel 1 echo Forecast method comparison warning: continuing to dataset export/reporting.

cd /d C:\bluelotus3\mid
"%PYTHON_EXE%" run_monitoring_alerts.py
if errorlevel 1 echo Monitoring governance warning: continuing to final dataset export/reporting.
"%PYTHON_EXE%" export_dataset_raw.py
"%PYTHON_EXE%" archive_dataset_snapshot.py

cd /d C:\bluelotus3\research
"%PYTHON_EXE%" research_report_generator.py

echo.
echo Pipeline completed at %date% %time%
echo Report: C:\bluelotus3\research\research_report.txt
endlocal

