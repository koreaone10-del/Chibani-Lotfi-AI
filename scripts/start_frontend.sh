#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../frontend"
python -m http.server "${FRONTEND_PORT:-5500}"
