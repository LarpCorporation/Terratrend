#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv --system-site-packages .venv
fi
if ! .venv/bin/python -c 'import numpy, scipy, requests, netCDF4' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python backend/server.py "${1:-8517}"
