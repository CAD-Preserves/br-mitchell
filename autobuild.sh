#!/usr/bin/env bash
# Verify Python environment and pre-compile core/ modules for distribution.
set -euo pipefail
cd "$(dirname "$0")"

python -c "import cv2, easyocr, numpy, orjson, PIL, pyjson5, pymupdf, requests, shapely, torch; print('Dependencies verified. CUDA available:', torch.cuda.is_available())"
python -m compileall -q core

echo "Build verification complete."

