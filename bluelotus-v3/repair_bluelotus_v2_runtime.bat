@echo off
setlocal
cd /d C:\bluelotus3

echo.
echo ============================================================
echo Repairing BlueLotus V2 Python runtime at %date% %time%
echo ============================================================

powershell -NoProfile -ExecutionPolicy Bypass -File C:\bluelotus3\diagnostics\Repair-BlueLotusV2Runtime.ps1 -Root C:\bluelotus3

endlocal

