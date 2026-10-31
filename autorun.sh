#!/usr/bin/env bash
# Run the reusable BR Mitchell CV + GPU OCR table digitisation pipeline.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1

python -u core/cli_runner.py "$@"

