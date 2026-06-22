#!/bin/bash
set -euo pipefail

SERVICE_NAME=mattbot-display
DESKTOP_USER="${SUDO_USER:-jetson}"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-$SCRIPT_DIR}"

write_service() {
    sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<EOF
[Unit]
Description=Mattbot touch display
After=network.target graphical.target
Wants=graphical.target

[Service]
Type=simple
User=$DESKTOP_USER
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/$DESKTOP_USER/.Xauthority
EnvironmentFile=-/etc/default/mattbot-display
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 display_app.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical.target
EOF
}

write_config() {
    sudo tee /etc/default/mattbot-display >/dev/null <<EOF
# Mattbot display install path (edit if repo moves)
MATTBOT_DISPLAY_DIR=$INSTALL_DIR
EOF
}

echo "Installing display from: $INSTALL_DIR"
sudo chmod +x "$INSTALL_DIR/scripts/"*.sh

write_config
write_service
sudo cp "$SCRIPT_DIR/deploy/mattbot-display-sudoers" "/etc/sudoers.d/mattbot-display"
sudo chmod 440 "/etc/sudoers.d/mattbot-display"

"$SCRIPT_DIR/scripts/setup_desktop_shortcut.sh" "$DESKTOP_USER" "$INSTALL_DIR"

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
echo "Installed. Code runs directly from: $INSTALL_DIR"
echo "After editing code, double-click Start-Mattbot-Display.sh to restart (no sync needed)."
echo "Status: sudo systemctl status $SERVICE_NAME"
