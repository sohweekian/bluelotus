@echo off
setlocal
set "BLUELOTUS_PROJECT_ROOT=%~dp0"
set "BLUELOTUS_PROJECT_ROOT=%BLUELOTUS_PROJECT_ROOT:~0,-1%"
cd /d "%BLUELOTUS_PROJECT_ROOT%"
if exist "%BLUELOTUS_PROJECT_ROOT%\.venv\Scripts\activate.bat" call "%BLUELOTUS_PROJECT_ROOT%\.venv\Scripts\activate.bat"
python -m llm_clients.llm_healthcheck
if errorlevel 1 (
  echo FAIL
  exit /b 1
)
echo PASS
exit /b 0
