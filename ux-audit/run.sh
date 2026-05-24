#!/usr/bin/env bash
# UX Audit runner — single-command entry point
# Usage: ./ux-audit/run.sh [--skip-claude]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
python3 ux-audit/audit.py "$@"
