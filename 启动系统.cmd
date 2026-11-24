@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local.ps1" %*
set "startup_exit=%errorlevel%"
pause
exit /b %startup_exit%
