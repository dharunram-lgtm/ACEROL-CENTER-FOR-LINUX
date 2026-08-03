#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Acer ALG Control Center — installer
#
# Installs system dependencies, copies the application to /usr/share/acer-alg,
# creates a launcher at /usr/bin/acer-alg-control-center, installs the icon
# and registers the desktop entry.
#
# Usage:
#   sudo ./install.sh                 normal install
#   sudo ./install.sh --with-alg-rgb  also install the keyboard RGB driver
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR="/usr/share/acer-alg"
BIN_DIR="/usr/bin"
ICON_DIR="/usr/share/icons/hicolor/512x512/apps"
APP_DIR_DESKTOP="/usr/share/applications"
APP_NAME="acer-alg-control-center"
DESKTOP_FILE="acer-alg.desktop"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WITH_ALG_RGB=0
for arg in "$@"; do
  case "$arg" in
    --with-alg-rgb) WITH_ALG_RGB=1 ;;
    -h|--help)
      echo "Usage: sudo ./install.sh [--with-alg-rgb]"
      echo "  --with-alg-rgb  also install the keyboard RGB driver"
      exit 0
      ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

echo "==> Installing system dependencies (python3-gi, gir1.2-gtk-3.0, lm-sensors, upower)"
PKGS="python3-gi gir1.2-gtk-3.0 lm-sensors upower"
MISSING=""
for pkg in $PKGS; do
  dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed" \
    || MISSING="$MISSING $pkg"
done
if [ -n "$MISSING" ]; then
  apt-get update -y
  # shellcheck disable=SC2086
  apt-get install -y $MISSING
else
  echo "    already installed — skipping"
fi

if [ "$WITH_ALG_RGB" -eq 1 ]; then
  echo "==> Installing keyboard RGB driver (alg-rgb CLI + udev rule)"
  install -m 755 "$SCRIPT_DIR/scripts/alg-rgb" /usr/local/bin/alg-rgb

  echo "==> Granting user access to the RGB device (udev rule + group)"
  RULE_FILE="/etc/udev/rules.d/99-alg-rgb.rules"
  if [ ! -f "$RULE_FILE" ]; then
    echo 'KERNEL=="alg_rgb", GROUP="alg-rgb", MODE="0660"' > "$RULE_FILE"
  fi
  groupadd -f alg-rgb
  usermod -aG alg-rgb "${SUDO_USER:-$(logname 2>/dev/null || echo root)}"
  udevadm control --reload-rules && udevadm trigger || true
  echo "NOTE: the alg_rgb kernel module is required — install it from"
  echo "      https://github.com/24kaushik/alg-cli (or: sudo modprobe alg_rgb)"
  echo "NOTE: you must log out and back in for the group change to take effect."
fi

echo "==> Copying application files to $APP_DIR"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
cp -r "$SCRIPT_DIR/main.py" \
      "$SCRIPT_DIR/config.py" \
      "$SCRIPT_DIR/modules" \
      "$SCRIPT_DIR/ui" \
      "$SCRIPT_DIR/assets" \
      "$SCRIPT_DIR/scripts" \
      "$APP_DIR/"

echo "==> Creating launcher $BIN_DIR/$APP_NAME"
cat > "$BIN_DIR/$APP_NAME" <<'EOF'
#!/usr/bin/env bash
# Run inside the alg-rgb group (via sg) so keyboard RGB works without a
# logout/login when the group was just added.  Falls back to a plain run if
# the group does not exist.
if sg alg-rgb -c true 2>/dev/null; then
  exec sg alg-rgb -c "exec python3 /usr/share/acer-alg/main.py $*"
else
  exec python3 /usr/share/acer-alg/main.py "$@"
fi
EOF
chmod 755 "$BIN_DIR/$APP_NAME"

echo "==> Installing icon"
mkdir -p "$ICON_DIR"
cp "$SCRIPT_DIR/assets/acer.png" "$ICON_DIR/$APP_NAME.png"
gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true

echo "==> Installing desktop entry"
mkdir -p "$APP_DIR_DESKTOP"
cp "$SCRIPT_DIR/$DESKTOP_FILE" "$APP_DIR_DESKTOP/$DESKTOP_FILE"
chmod 644 "$APP_DIR_DESKTOP/$DESKTOP_FILE"
update-desktop-database "$APP_DIR_DESKTOP" 2>/dev/null || true

echo "==> Configuring lm-sensors for user access"
[ -d "/etc/sensors.d" ] && touch "/etc/sensors.d/acer-alg.conf" || true

echo "==> Installing EC fan reader (alg-fan)"
if [ -f "$SCRIPT_DIR/scripts/alg-fan" ]; then
  install -m 755 "$SCRIPT_DIR/scripts/alg-fan" /usr/local/bin/alg-fan
fi
EC_RULES="/etc/udev/rules.d/60-alg-ec.rules"
if [ ! -f "$EC_RULES" ]; then
  # The ALG fan is only readable via the EC debug interface.  Grant the
  # debugfs parent directories + EC file world-read access so the app can
  # read fan speeds without root.  Load ec_sys (with write_support for the
  # io file) and apply the permissions.
  echo 'KERNEL=="ec0", SUBSYSTEM=="ec", ACTION=="add", RUN+="/bin/sh -c '\''chmod 0755 /sys/kernel/debug; chmod 0755 /sys/kernel/debug/ec; chmod 0644 /sys/kernel/debug/ec/ec0/io'\''"' > "$EC_RULES"
  udevadm control --reload-rules && udevadm trigger || true
fi
if ! grep -qE "^ec_sys" /etc/modules 2>/dev/null; then
  echo "ec_sys" >> /etc/modules
fi
if ! lsmod | grep -q "^ec_sys"; then
  modprobe ec_sys write_support=1 || true
  chmod 0755 /sys/kernel/debug 2>/dev/null || true
  chmod 0755 /sys/kernel/debug/ec 2>/dev/null || true
  chmod 0644 /sys/kernel/debug/ec/ec0/io 2>/dev/null || true
fi

echo
echo "Done! You can now launch Acer ALG Control Center from your app menu"
echo "or by running:  $APP_NAME"
echo
echo "Optional: install the GPU switcher to use the GPU page:"
echo "  sudo apt install system76-power"
echo
