#!/bin/bash
# Fix desktop shortcut so double-click launches (not opens in editor).
set -euo pipefail

DESKTOP_USER="${1:-${SUDO_USER:-jetson}}"
INSTALL_DIR="${2:-$(cd "$(dirname "$0")/.." && pwd)}"
DESKTOP_DIR="/home/$DESKTOP_USER/Desktop"

install -d -o "$DESKTOP_USER" -g "$DESKTOP_USER" "$DESKTOP_DIR"

sudo -u "$DESKTOP_USER" tee "$DESKTOP_DIR/Mattbot-Display.desktop" >/dev/null <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Mattbot Display
Comment=Start the robot touch screen display
Exec=$INSTALL_DIR/scripts/start_display.sh
Path=$INSTALL_DIR
Icon=video-display
Terminal=false
Categories=Utility;
StartupNotify=false
EOF
sudo chown "$DESKTOP_USER:$DESKTOP_USER" "$DESKTOP_DIR/Mattbot-Display.desktop"
sudo chmod 755 "$DESKTOP_DIR/Mattbot-Display.desktop"

sudo -u "$DESKTOP_USER" tee "$DESKTOP_DIR/Start-Mattbot-Display.sh" >/dev/null <<EOF
#!/bin/bash
exec $INSTALL_DIR/scripts/start_display.sh
EOF
sudo chown "$DESKTOP_USER:$DESKTOP_USER" "$DESKTOP_DIR/Start-Mattbot-Display.sh"
sudo chmod 755 "$DESKTOP_DIR/Start-Mattbot-Display.sh"

if command -v gio >/dev/null 2>&1; then
    if [[ $EUID -eq 0 ]]; then
        sudo -u "$DESKTOP_USER" gio set "$DESKTOP_DIR/Mattbot-Display.desktop" metadata::trusted true
    else
        gio set "$DESKTOP_DIR/Mattbot-Display.desktop" metadata::trusted true
    fi
    echo "Marked Mattbot-Display.desktop as trusted."
fi

echo "Desktop shortcuts installed for $DESKTOP_USER (app path: $INSTALL_DIR):"
echo "  $DESKTOP_DIR/Mattbot-Display.desktop"
echo "  $DESKTOP_DIR/Start-Mattbot-Display.sh"
echo "Run scripts/setup_desktop_shortcut.sh if .desktop opens in a text editor."
