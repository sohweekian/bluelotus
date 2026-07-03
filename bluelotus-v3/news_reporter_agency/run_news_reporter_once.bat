@echo off
setlocal
cd /d C:\bluelotus3\news_reporter_agency
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHON=C:\bluelotus3\.venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python
"%PYTHON%" news_probe_runner.py
endlocal
