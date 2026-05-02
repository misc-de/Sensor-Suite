#!/usr/bin/env bash
set -euo pipefail

APP_ID="de.cais.SensorSuite"
INSTALL_DIR="$HOME/.local/share/sensor-suite"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
DESKTOP_DIR="$HOME/.local/share/applications"

rm -rf "$INSTALL_DIR"
rm -f  "$ICON_DIR/$APP_ID.png"
rm -f  "$DESKTOP_DIR/$APP_ID.desktop"

if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo "Sensor Suite uninstalled."
