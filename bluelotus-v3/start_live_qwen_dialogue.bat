@echo off
setlocal
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File scripts\start_live_qwen_dialogue.ps1
endlocal
