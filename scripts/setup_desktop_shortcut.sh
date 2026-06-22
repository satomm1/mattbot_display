#!/bin/bash
# Fix desktop shortcut so double-click launches (not opens in editor).
set -euo pipefail

DESKTOP_USER="${1:-${SUDO_USER:-jetson}}"
DESKTOP_DIR="/home/$DESKTOP_USER/Desktop"
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

install -d -o "$DESKTOP_USER" -g "$DESKTOP_USER" "$DESKTOP_DIR"
install -o "$DESKTOP_USER" -g "$DESKTOP_USER" -m 755 \
    "$SCRIPT_DIR/deploy/Mattbot-Display.desktop" "$DESKTOP_DIR/"
install -o "$DESKTOP_USER" -g "$DESKTOP_USER" -m 755 \
    "$SCRIPT_DIR/deploy/Start-Mattbot-Display.sh" "$DESKTOP_DIR/"

if command -v gio >/dev/null 2>&1; then
    if [[ $EUID -eq 0 ]]; then
        sudo -u "$DESKTOP_USER" gio set "$DESKTOP_DIR/Mattbot-Display.desktop" metadata::trusted true
    else
        gio set "$DESKTOP_DIR/Mattbot-Display.desktop" metadata::trusted true
    fi
    echo "Marked Mattbot-Display.desktop as trusted."
fi

echo "Desktop shortcuts installed for $DESKTOP_USER:"
echo "  $DESKTOP_DIR/Mattbot-Display.desktop"
echo "  $DESKTOP_DIR/Start-Mattbot-Display.sh  (use this if .desktop still opens in editor)"
