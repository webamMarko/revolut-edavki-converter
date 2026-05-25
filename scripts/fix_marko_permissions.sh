#!/bin/bash
# Fix ownership of marko's data directory

set -e

DATA_DIR="data/marko"

echo "Fixing ownership of ${DATA_DIR}..."
chown -R homeassistant:homeassistant "$DATA_DIR"
chmod 755 "$DATA_DIR"
chmod 644 "$DATA_DIR"/*.db 2>/dev/null || true

echo "Done. Current permissions:"
ls -la "$DATA_DIR"
