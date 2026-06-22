#!/bin/bash
# Systemd entrypoint — resolve DISPLAY/XAUTHORITY, verify deps, run display_app.py.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$INSTALL_DIR"

pick_x11_from_gui_session() {
    local user="$1" proc pid line
    for proc in gnome-session gnome-session-binary lxsession xfce4-session \
                openbox-session pcmanfm Xorg Xwayland X; do
        pid="$(pgrep -u "$user" -x "$proc" 2>/dev/null | head -1 || true)"
        [[ -z "$pid" || ! -r "/proc/$pid/environ" ]] && continue
        while IFS= read -r line; do
            case "$line" in
                DISPLAY=*) export "$line" ;;
                XAUTHORITY=*) export "$line" ;;
            esac
        done < <(tr '\0' '\n' < "/proc/$pid/environ" | grep -E '^(DISPLAY|XAUTHORITY)=' || true)
        [[ -n "${DISPLAY:-}" ]] && return 0
    done
    return 1
}

pick_xauthority_fallback() {
    local uid="${1:-$(id -u)}" display="${DISPLAY:-:0}"
    local cand
    for cand in \
        "${XAUTHORITY:-}" \
        "${HOME}/.Xauthority" \
        "/run/user/${uid}/gdm/Xauthority" \
        "/run/user/${uid}/.Xauthority" \
        "/var/run/lightdm/root/${display#:}"
    do
        [[ -n "$cand" && -f "$cand" ]] || continue
        export XAUTHORITY="$cand"
        return 0
    done
    return 1
}

x11_works() {
    command -v xset >/dev/null 2>&1 || return 0
    xset q >/dev/null 2>&1
}

resolve_x11() {
    local user uid sock display
    user="$(whoami)"
    uid="$(id -u)"

    pick_x11_from_gui_session "$user" || true
    export DISPLAY="${DISPLAY:-:0}"
    pick_xauthority_fallback "$uid" || true

    if x11_works; then
        return 0
    fi

    # Brute-force: try each local X socket with each auth file.
    for sock in /tmp/.X11-unix/X*; do
        [[ -e "$sock" ]] || continue
        display=":${sock##*/X}"
        export DISPLAY="$display"
        pick_xauthority_fallback "$uid" || true
        if x11_works; then
            return 0
        fi
        for cand in "${HOME}/.Xauthority" "/run/user/${uid}/gdm/Xauthority" \
                    "/run/user/${uid}/.Xauthority"; do
            [[ -f "$cand" ]] || continue
            export XAUTHORITY="$cand"
            if x11_works; then
                return 0
            fi
        done
    done
    return 1
}

if ! /usr/bin/python3 -c "import tkinter" 2>/dev/null; then
    echo "ERROR: python3-tk is not installed. Run: sudo apt install python3-tk" >&2
    exit 1
fi

if ! resolve_x11; then
    echo "ERROR: cannot connect to an X display (DISPLAY=${DISPLAY:-unset}, XAUTHORITY=${XAUTHORITY:-unset})." >&2
    echo "  Log in to the desktop first (auto-login recommended for kiosk use)." >&2
    echo "  Then: systemctl --user restart mattbot-display" >&2
    exit 1
fi

echo "Using DISPLAY=$DISPLAY XAUTHORITY=${XAUTHORITY:-unset}" >&2
exec /usr/bin/python3 "$INSTALL_DIR/display_app.py"
