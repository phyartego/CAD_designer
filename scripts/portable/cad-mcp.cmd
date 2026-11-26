@echo off
setlocal DisableDelayedExpansion
set "FREECAD_CMD=%~dp0runtime\freecad\bin\freecadcmd.exe"
set "CAD_WORKSPACE=%~dp0workspace"
"%~dp0runtime\python\python.exe" -m consumer_cad_ai serve %*
exit /b %errorlevel%
