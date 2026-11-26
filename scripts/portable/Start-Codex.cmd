@echo off
setlocal DisableDelayedExpansion
"%~dp0runtime\python\python.exe" "%~dp0scripts\start_codex.py" %*
set "result=%errorlevel%"
if not "%result%"=="0" if "%~1"=="" pause
exit /b %result%
