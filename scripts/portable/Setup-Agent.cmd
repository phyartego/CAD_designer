@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
set "NO_PAUSE="
for %%A in (%*) do if /I "%%~A"=="--no-pause" set "NO_PAUSE=1"
"%~dp0runtime\python\python.exe" "%~dp0scripts\configure_agent.py" --print-guide --copy %*
set "result=%errorlevel%"
if not defined NO_PAUSE pause
exit /b %result%
