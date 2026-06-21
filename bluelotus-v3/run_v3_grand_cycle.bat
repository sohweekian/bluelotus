@echo off
setlocal
cd /d "%~dp0"
python -m orchestration.run_v3_grand_cycle %*
endlocal
