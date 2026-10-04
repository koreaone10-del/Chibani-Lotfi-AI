#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../backend"
python -m pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port "${PORT:-8080}"
