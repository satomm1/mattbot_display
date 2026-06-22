#!/bin/bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/mattbot/display}"
SERVICE_NAME=mattbot-display
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Syncing $SCRIPT_DIR -> $INSTALL_DIR"
sudo rsync -a --exclude venv --exclude .git "$SCRIPT_DIR/" "$INSTALL_DIR/"

echo "Restarting $SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager
