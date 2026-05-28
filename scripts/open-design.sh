#!/usr/bin/env bash
# Wrapper to run open-design tools-dev commands from this project.
# Usage: ./scripts/open-design.sh <command> [args...]
# Examples:
#   ./scripts/open-design.sh run web          # Start daemon + web (foreground)
#   ./scripts/open-design.sh start web        # Start in background
#   ./scripts/open-design.sh status           # Show running processes
#   ./scripts/open-design.sh stop             # Stop all services
#   ./scripts/open-design.sh check            # Diagnostics

set -euo pipefail

OPEN_DESIGN_DIR="${OPEN_DESIGN_DIR:-/home/homeassistant/ai-development/open-design}"

if [ ! -d "$OPEN_DESIGN_DIR" ]; then
  echo "Error: open-design not found at $OPEN_DESIGN_DIR" >&2
  echo "Clone it: git clone https://github.com/nexu-io/open-design.git $OPEN_DESIGN_DIR" >&2
  exit 1
fi

source ~/.nvm/nvm.sh
nvm use 24 --silent

cd "$OPEN_DESIGN_DIR"
exec pnpm tools-dev "$@"
