@echo off
REM Run the reusable BR Mitchell CV + GPU OCR table digitisation pipeline.
setlocal
cd /d "%~dp0"
set PYTHONUNBUFFERED=1

python -u core\cli_runner.py %*
exit /b %ERRORLEVEL%

