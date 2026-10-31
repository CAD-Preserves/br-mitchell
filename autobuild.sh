#!/usr/bin/env bash
# Verify Python environment and pre-compile core/ modules for distribution.
set -euo pipefail
cd "$(dirname "$0")"

python -c "import cv2, doctr, numpy, orjson, pyjson5, pymupdf, torch; print('Dependencies verified. CUDA available:', torch.cuda.is_available())"
python -m compileall -q core

echo "Build verification complete."

