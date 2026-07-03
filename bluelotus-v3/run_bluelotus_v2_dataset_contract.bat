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
echo Running BlueLotus V2 dataset contract validator at %date% %time%
echo ============================================================

"%PYTHON_EXE%" C:\bluelotus3\diagnostics\dataset_contract_v2.py --dataset C:\bluelotus3\data\frontend\dataset_raw.json %*

echo.
echo Dataset contract artifact:
echo C:\bluelotus3\data\audit\dataset_contract_latest.json
endlocal

