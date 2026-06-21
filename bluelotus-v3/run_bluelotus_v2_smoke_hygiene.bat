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
echo Running BlueLotus V2 smoke/hygiene diagnostics at %date% %time%
echo ============================================================

"%PYTHON_EXE%" C:\bluelotus3\diagnostics\bluelotus_v2_smoke_hygiene.py --root C:\bluelotus3 %*

echo.
echo Diagnostic artifact:
echo C:\bluelotus3\data\audit\smoke_hygiene_latest.json
endlocal

