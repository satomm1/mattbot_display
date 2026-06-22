#!/bin/bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/mattbot/display}"
SERVICE_NAME=mattbot-display
DESKTOP_USER="${SUDO_USER:-jetson}"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

sudo mkdir -p "$INSTALL_DIR"
sudo rsync -a --exclude venv --exclude .git "$SCRIPT_DIR/" "$INSTALL_DIR/"
sudo chmod +x "$INSTALL_DIR/scripts/"*.sh

if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "Installing python3-venv..."
    sudo apt install -y python3-venv
fi
sudo python3 -m venv "$INSTALL_DIR/venv" 2>/dev/null || true

sudo cp "$SCRIPT_DIR/deploy/mattbot-display.service" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo cp "$SCRIPT_DIR/deploy/mattbot-display-sudoers" "/etc/sudoers.d/mattbot-display"
sudo chmod 440 "/etc/sudoers.d/mattbot-display"

"$SCRIPT_DIR/scripts/setup_desktop_shortcut.sh" "$DESKTOP_USER"

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
echo "Installed. Run ~/Desktop/Start-Mattbot-Display.sh or double-click Mattbot Display."
echo "Status: sudo systemctl status $SERVICE_NAME"
