#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"

.venv/bin/python packaging/build_release.py

echo "Built macOS application: $PROJECT_DIR/build/IP-Scanner.app"
