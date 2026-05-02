#!/usr/bin/env bash
set -euo pipefail

APP_ID="de.cais.SensorSuite"
INSTALL_DIR="$HOME/.local/share/sensor-suite"
DESKTOP_DIR="$HOME/.local/share/applications"

rm -rf "$INSTALL_DIR"
rm -f  "$DESKTOP_DIR/$APP_ID.desktop"

if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo "Sensor Suite uninstalled."
