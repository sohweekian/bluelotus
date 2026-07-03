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
echo Running BlueLotus V2 runtime guard at %date% %time%
echo ============================================================

"%PYTHON_EXE%" C:\bluelotus3\diagnostics\bluelotus_runtime_guard.py --root C:\bluelotus3 %*

echo.
echo Runtime guard artifact:
echo C:\bluelotus3\data\audit\runtime_guard_latest.json
endlocal

