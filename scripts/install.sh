#!/bin/bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/mattbot/display}"
SERVICE_NAME=mattbot-display
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

sudo mkdir -p "$INSTALL_DIR"
sudo rsync -a --exclude venv --exclude .git "$SCRIPT_DIR/" "$INSTALL_DIR/"
sudo python3 -m venv "$INSTALL_DIR/venv"
sudo cp "$SCRIPT_DIR/deploy/mattbot-display.service" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
echo "Installed. Status: sudo systemctl status $SERVICE_NAME"
