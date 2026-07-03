@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
chcp 65001 >nul

set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=C:\bluelotus2\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo.
echo ============================================================
echo BlueLotus V3 -- Starting Daemons  %date% %time%
echo ============================================================

echo.
echo [START] news_probe_daemon.py (RSS headlines - FT, WSJ, Bloomberg, SCMP, Nikkei)
start "BlueLotus V3 News Probe" /min "%PYTHON%" mid\news_probe_daemon.py

echo [START] thesis_probe_daemon.py (Gold Thesis + Live Regime, 10-min)
start "BlueLotus V3 Thesis Probe" /min "%PYTHON%" mid\thesis_probe_daemon.py

echo [START] portfolio_live_updater.py (Moomoo portfolio, hourly)
start "BlueLotus V3 Portfolio Live" /min "%PYTHON%" mid\portfolio_live_updater.py

echo [START] warsh_thesis_probe_daemon.py (Hawkish Warsh Thesis, 10-min)
start "BlueLotus V3 Warsh Probe" /min "%PYTHON%" mid\warsh_thesis_probe_daemon.py

echo [START] boj_yen_carry_probe_daemon.py (BOJ/Yen Carry Event Watcher, 10-min)
start "BlueLotus V3 BOJ Yen Probe" /min "%PYTHON%" mid\boj_yen_carry_probe_daemon.py

echo.
echo All V3 daemons launched in background windows.
echo Logs:
echo   logs\news_probe.log
echo   logs\thesis_probe.log
echo   logs\portfolio_live.log
echo   logs\warsh_probe.log
echo   logs\boj_yen_carry.log
echo ============================================================
endlocal
