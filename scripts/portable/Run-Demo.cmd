@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
set "FREECAD_CMD=%~dp0runtime\freecad\bin\freecadcmd.exe"
"%~dp0runtime\python\python.exe" "%~dp0scripts\portable_demo.py" %*
set "result=%errorlevel%"
if "%~1"=="" pause
exit /b %result%
