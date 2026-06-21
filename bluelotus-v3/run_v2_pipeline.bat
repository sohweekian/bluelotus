@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo.
echo ============================================================
echo BlueLotus V3 compatibility shim
echo This V3 sandbox no longer runs a V2 pipeline.
echo Forwarding to run_v3_pipeline.bat
echo ============================================================
call "%~dp0run_v3_pipeline.bat" %*
endlocal
