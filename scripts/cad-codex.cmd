@echo off
"%~dp0..\.venv\Scripts\python.exe" "%~dp0start_codex.py" %*
exit /b %errorlevel%
