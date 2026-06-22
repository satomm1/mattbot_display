#!/bin/bash
# Restart the display service (picks up code changes from the install directory).
set -euo pipefail
SERVICE_NAME=mattbot-display
if systemctl is-active --quiet "$SERVICE_NAME"; then
    sudo systemctl restart "$SERVICE_NAME"
else
    sudo systemctl start "$SERVICE_NAME"
fi
