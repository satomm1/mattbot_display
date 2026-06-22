#!/bin/bash
set -euo pipefail

SERVICE_NAME=mattbot-display
DESKTOP_USER="${SUDO_USER:-jetson}"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-$SCRIPT_DIR}"
USER_UID="$(id -u "$DESKTOP_USER" 2>/dev/null || echo 1000)"
USER_SERVICE_DIR="/home/$DESKTOP_USER/.config/systemd/user"
RUNTIME_DIR="/run/user/$USER_UID"

user_systemctl() {
    sudo -u "$DESKTOP_USER" \
        XDG_RUNTIME_DIR="$RUNTIME_DIR" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=${RUNTIME_DIR}/bus" \
        systemctl --user "$@"
}

write_user_service() {
    install -d -o "$DESKTOP_USER" -g "$DESKTOP_USER" "$USER_SERVICE_DIR"
    sudo -u "$DESKTOP_USER" tee "$USER_SERVICE_DIR/${SERVICE_NAME}.service" >/dev/null <<EOF
[Unit]
Description=Mattbot touch display
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/scripts/run_display_service.sh
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
EOF
}

write_config() {
    sudo tee /etc/default/mattbot-display >/dev/null <<EOF
# Mattbot display install path (edit if repo moves)
MATTBOT_DISPLAY_DIR=$INSTALL_DIR
EOF
}

remove_system_service() {
    if systemctl is-enabled mattbot-display >/dev/null 2>&1; then
        sudo systemctl disable --now mattbot-display 2>/dev/null || true
    fi
    sudo rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
    sudo systemctl daemon-reload 2>/dev/null || true
}

echo "Installing display from: $INSTALL_DIR"
sudo chmod +x "$INSTALL_DIR/scripts/"*.sh

if ! dpkg -s python3-tk >/dev/null 2>&1; then
    echo "Installing python3-tk (required for the display UI)..."
    sudo apt-get install -y python3-tk
fi
if ! command -v aplay >/dev/null 2>&1; then
    echo "Installing alsa-utils (required for speech playback)..."
    sudo apt-get install -y alsa-utils
fi
if ! command -v xset >/dev/null 2>&1; then
    echo "Installing x11-xserver-utils (X display checks)..."
    sudo apt-get install -y x11-xserver-utils
fi

if [[ -x "$INSTALL_DIR/scripts/setup_piper.sh" ]]; then
    echo "Setting up Piper TTS..."
    "$INSTALL_DIR/scripts/setup_piper.sh" || echo "Warning: Piper setup failed (TTS disabled until setup_piper.sh succeeds)"
fi

write_config
remove_system_service
write_user_service
sudo loginctl enable-linger "$DESKTOP_USER"

"$SCRIPT_DIR/scripts/setup_desktop_shortcut.sh" "$DESKTOP_USER" "$INSTALL_DIR"

user_systemctl daemon-reload
if user_systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    user_systemctl restart "$SERVICE_NAME"
else
    user_systemctl enable --now "$SERVICE_NAME" || {
        echo "Note: service will start after desktop login (auto-login recommended)."
        user_systemctl enable "$SERVICE_NAME"
    }
fi

echo "Installed. Code runs directly from: $INSTALL_DIR"
echo "After editing code, double-click Start-Mattbot-Display.sh to restart (no sync needed)."
echo "Status: systemctl --user status $SERVICE_NAME"
