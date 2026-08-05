#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"

PYINSTALLER_CONFIG_DIR=/tmp/ip-scanner-pyinstaller \
  .venv/bin/pyinstaller \
  --noconfirm \
  --windowed \
  --name IP-Scanner \
  --distpath build \
  --workpath build/.work \
  --specpath build \
  --add-data "$PROJECT_DIR/src/ip_scanner/assets:ip_scanner/assets" \
  packaging/macos_entry.py

echo "Built: $PROJECT_DIR/build/IP-Scanner.app"
