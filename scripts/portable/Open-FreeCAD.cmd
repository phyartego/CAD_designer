@echo off
setlocal DisableDelayedExpansion
start "" "%~dp0runtime\freecad\bin\freecad.exe" %*
exit /b %errorlevel%
