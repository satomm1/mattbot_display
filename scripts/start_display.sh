#!/bin/bash
# Start or restart the display service (passwordless sudo required — see install.sh).
set -euo pipefail
SERVICE_NAME=mattbot-display
if systemctl is-active --quiet "$SERVICE_NAME"; then
    sudo systemctl restart "$SERVICE_NAME"
else
    sudo systemctl start "$SERVICE_NAME"
fi
