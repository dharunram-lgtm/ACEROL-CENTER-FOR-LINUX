#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Acer ALG Control Center — uninstaller
#
# Removes the desktop entry, the launcher, the application directory and the
# installed icon.  System packages installed by install.sh are NOT removed
# because they may be used by other applications.
#
# Usage:
#   sudo ./uninstall.sh
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR="/usr/share/acer-alg"
BIN_DIR="/usr/bin"
ICON_DIR="/usr/share/icons/hicolor/512x512/apps"
APP_DIR_DESKTOP="/usr/share/applications"
APP_NAME="acer-alg-control-center"
DESKTOP_FILE="acer-alg.desktop"

echo "==> Removing desktop entry"
rm -f "$APP_DIR_DESKTOP/$DESKTOP_FILE"
update-desktop-database "$APP_DIR_DESKTOP" 2>/dev/null || true

echo "==> Removing launcher"
rm -f "$BIN_DIR/$APP_NAME"

echo "==> Removing application directory"
rm -rf "$APP_DIR"

echo "==> Removing icon"
rm -f "$ICON_DIR/$APP_NAME.png"
gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true

echo "==> Removing user configuration"
rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/acer-alg-control-center"

echo
echo "Acer ALG Control Center has been removed."
echo "User data (keyboard colour, settings) was also deleted."
echo
