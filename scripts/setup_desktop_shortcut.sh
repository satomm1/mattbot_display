#!/bin/bash
# Fix desktop shortcut so double-click launches (not opens in editor).
set -euo pipefail

DESKTOP_USER="${1:-${SUDO_USER:-jetson}}"
INSTALL_DIR="${2:-$(cd "$(dirname "$0")/.." && pwd)}"
DESKTOP_DIR="/home/$DESKTOP_USER/Desktop"
APPS_DIR="/home/$DESKTOP_USER/.local/share/applications"
USER_HOME="/home/$DESKTOP_USER"

run_as_user() {
    if [[ $EUID -eq 0 ]]; then
        sudo -u "$DESKTOP_USER" "$@"
    else
        "$@"
    fi
}

# Set key=value in an INI file under [config], creating file/section if needed.
set_ini_config() {
    local file="$1" key="$2" value="$3"
    install -d -o "$DESKTOP_USER" -g "$DESKTOP_USER" "$(dirname "$file")"
    if [[ ! -f "$file" ]]; then
        run_as_user tee "$file" >/dev/null <<EOF
[config]
$key=$value
EOF
        return
    fi
    if grep -q "^${key}=" "$file"; then
        sed -i "s/^${key}=.*/${key}=${value}/" "$file"
    elif grep -q '^\[config\]' "$file"; then
        sed -i "/^\[config\]/a ${key}=${value}" "$file"
    else
        run_as_user tee -a "$file" >/dev/null <<EOF

[config]
$key=$value
EOF
    fi
    chown "$DESKTOP_USER:$DESKTOP_USER" "$file"
}

enable_pcmanfm_launch() {
    # "Don't ask options on launch executable file" (libfm)
    set_ini_config "$USER_HOME/.config/libfm/libfm.conf" quick_exec 1
    # "Treat executable text files as programs" (pcmanfm — all profiles)
    while IFS= read -r conf; do
        set_ini_config "$conf" exec_apps 1
    done < <(find "$USER_HOME/.config/pcmanfm" -name pcmanfm.conf 2>/dev/null || true)
    set_ini_config "$USER_HOME/.config/pcmanfm/default/pcmanfm.conf" exec_apps 1
    echo "Enabled PCManFM/LXDE auto-launch (quick_exec, exec_apps)."
}

write_desktop_entry() {
    local dest="$1"
    install -d -o "$DESKTOP_USER" -g "$DESKTOP_USER" "$(dirname "$dest")"
    run_as_user tee "$dest" >/dev/null <<EOF
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
    chown "$DESKTOP_USER:$DESKTOP_USER" "$dest"
    chmod 644 "$dest"
}

try_mark_desktop_trusted() {
    local desktop_file="$1"
    if ! command -v gio >/dev/null 2>&1; then
        return 1
    fi
    local err
    if [[ $EUID -eq 0 ]]; then
        err="$(sudo -u "$DESKTOP_USER" gio set "$desktop_file" metadata::trusted true 2>&1)" || true
    else
        err="$(gio set "$desktop_file" metadata::trusted true 2>&1)" || true
    fi
    if [[ -z "$err" ]]; then
        echo "Marked Mattbot-Display.desktop as trusted (GNOME/Nautilus)."
        return 0
    fi
    if [[ "$err" == *"not supported"* ]]; then
        echo "Note: gio trust not supported on this desktop (use Start-Mattbot-Display.sh or the app menu)."
        return 1
    fi
    echo "Warning: could not mark .desktop trusted: $err" >&2
    return 1
}

install -d -o "$DESKTOP_USER" -g "$DESKTOP_USER" "$DESKTOP_DIR" "$APPS_DIR"

# Application menu entry — launches reliably on LXDE/GNOME/XFCE.
write_desktop_entry "$APPS_DIR/mattbot-display.desktop"
if command -v update-desktop-database >/dev/null 2>&1; then
    run_as_user update-desktop-database "$APPS_DIR" 2>/dev/null || true
fi

# Primary desktop launcher: shell script (works on PCManFM when quick_exec is set).
run_as_user tee "$DESKTOP_DIR/Start-Mattbot-Display.sh" >/dev/null <<EOF
#!/bin/bash
exec $INSTALL_DIR/scripts/start_display.sh
EOF
chown "$DESKTOP_USER:$DESKTOP_USER" "$DESKTOP_DIR/Start-Mattbot-Display.sh"
chmod 755 "$DESKTOP_DIR/Start-Mattbot-Display.sh"

# Optional .desktop on Desktop — works on GNOME when trusted; often fails on PCManFM.
write_desktop_entry "$DESKTOP_DIR/Mattbot-Display.desktop"
chmod 755 "$DESKTOP_DIR/Mattbot-Display.desktop"
try_mark_desktop_trusted "$DESKTOP_DIR/Mattbot-Display.desktop" || true

enable_pcmanfm_launch

echo ""
echo "Desktop shortcuts installed for $DESKTOP_USER (app path: $INSTALL_DIR):"
echo "  $DESKTOP_DIR/Start-Mattbot-Display.sh   <- double-click this on LXDE/PCManFM"
echo "  $DESKTOP_DIR/Mattbot-Display.desktop"
echo "  $APPS_DIR/mattbot-display.desktop     <- also in application menu"
echo ""
echo "If a shortcut still opens in a text editor, log out and back in (PCManFM reads config at login),"
echo "or run: sudo ./scripts/setup_desktop_shortcut.sh"
