@echo off
cd /d C:\bluelotus3

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
chcp 65001 >nul

:RUN_LOOP
call C:\bluelotus3\run_bluelotus_v2_once_installed.bat

echo.
echo Waiting 3600 seconds before next run...
timeout /t 3600 /nobreak

goto RUN_LOOP

