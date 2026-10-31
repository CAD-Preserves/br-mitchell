@echo off
REM Verify Python environment and pre-compile core/ modules for distribution.
setlocal
cd /d "%~dp0"

python -c "import cv2, easyocr, numpy, orjson, pyjson5, pymupdf, torch; print('Dependencies verified. CUDA available:', torch.cuda.is_available())"
if errorlevel 1 exit /b 1

python -m compileall -q core
if errorlevel 1 exit /b 1

echo Build verification complete.
exit /b 0

