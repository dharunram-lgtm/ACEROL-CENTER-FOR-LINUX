"""Central application configuration and constants.

This module holds every tunable value used across the application:

* Application metadata (name, version, author, GitHub link, license).
* The list of supported keyboard colors and their RGB values.
* Default window geometry, refresh timings and file paths.
* Filesystem layout used both when running from a source checkout and
  after a system-wide installation (``/usr/share/acer-alg``).

No business logic lives here on purpose; importing this module must never
require GTK or raise an exception.
"""

from __future__ import annotations

import os
from typing import Dict, List

# ---------------------------------------------------------------------------
# Application metadata
# ---------------------------------------------------------------------------

APP_ID: str = "com.acer.algcontrolcenter"
APP_NAME: str = "Acer ALG Control Center"
VERSION: str = "1.0.0"
AUTHOR: str = "Dharun"
AUTHOR_EMAIL: str = "dharun@localhost"
GITHUB_URL: str = "https://github.com/dharun/acer-alg-control-center"
LICENSE_NAME: str = "MIT"
LICENSE_FILE: str = "LICENSE"

SUPPORTED_DISTROS: List[str] = ["Ubuntu", "Pop!_OS", "Linux Mint", "Debian"]

# ---------------------------------------------------------------------------
# Hardware model (documented target device)
# ---------------------------------------------------------------------------

DEVICE_MODEL: str = "Acer ALG AL15G-53"
DEFAULT_CPU_NAME: str = "Intel Core i5-13420H"
DEFAULT_GPU_NAME: str = "RTX 3050 Laptop GPU"

# ---------------------------------------------------------------------------
# Keyboard backlight (alg-rgb)
# ---------------------------------------------------------------------------

RGB_COMMAND: str = "alg-rgb"

#: ``name -> hexadecimal RGB`` colour mapping supported by ``alg-rgb``.
RGB_COLORS: Dict[str, str] = {
    "red": "#FF0000",
    "orange": "#FFA500",
    "yellow": "#FFFF00",
    "green": "#00FF00",
    "cyan": "#00FFFF",
    "blue": "#0000FF",
    "violet": "#8F00FF",
    "magenta": "#FF00FF",
    "pink": "#FF69B4",
    "white": "#FFFFFF",
    "off": "#000000",
}

#: Brightness range accepted by ``alg-rgb`` (0 = dimmest, 4 = brightest).
RGB_BRIGHTNESS_MIN: int = 0
RGB_BRIGHTNESS_MAX: int = 4
RGB_BRIGHTNESS_DEFAULT: int = 4

# ---------------------------------------------------------------------------
# Keyboard lighting effects
# ---------------------------------------------------------------------------

#: ``effect id -> (label, supported)``.  Unsupported entries are shown
#: disabled in the UI; adding a new effect only requires a new entry here and
#: a matching branch in :mod:`modules.effects`.
RGB_EFFECTS: Dict[str, Dict[str, object]] = {
    "static": {"label": "Static", "supported": True},
    "breathing": {"label": "Breathing", "supported": True},
    "color-cycle": {"label": "Color Cycle", "supported": False},
    "rainbow": {"label": "Rainbow", "supported": False},
    "wave": {"label": "Wave", "supported": False},
}
RGB_EFFECT_DEFAULT: str = "static"

#: Tooltip shown on effects that are not implemented yet.
RGB_EFFECT_UNSUPPORTED_TOOLTIP: str = "Not supported yet"

#: Breathing speed range (1 = slow ... 5 = fast).
RGB_SPEED_MIN: int = 1
RGB_SPEED_MAX: int = 5
RGB_SPEED_DEFAULT: int = 3

# ---------------------------------------------------------------------------
# GPU switching (system76-power)
# ---------------------------------------------------------------------------

GPU_COMMAND: str = "system76-power"
PKEXEC_COMMAND: str = "pkexec"

#: ``mode -> (display name, system76-power argument)``.
GPU_MODES: Dict[str, Dict[str, str]] = {
    "integrated": {"label": "Integrated", "arg": "integrated"},
    "hybrid": {"label": "Hybrid", "arg": "hybrid"},
    "nvidia": {"label": "NVIDIA", "arg": "nvidia"},
}
GPU_DEFAULT_MODE: str = "hybrid"

# ---------------------------------------------------------------------------
# Hardware monitor
# ---------------------------------------------------------------------------

NVIDIA_SMI_COMMAND: str = "nvidia-smi"
SENSORS_COMMAND: str = "sensors"
DEFAULT_REFRESH_INTERVAL: int = 2

#: Temperature thresholds used to colour the readings.
TEMP_GREEN_MAX: float = 60.0
TEMP_ORANGE_MAX: float = 80.0

# ---------------------------------------------------------------------------
# Battery / power (upower)
# ---------------------------------------------------------------------------

UPOWER_COMMAND: str = "upower"
BATTERY_REFRESH_INTERVAL: int = 5

# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

DEFAULT_WIDTH: int = 1100
DEFAULT_HEIGHT: int = 720
MIN_WIDTH: int = 820
MIN_HEIGHT: int = 560

# ---------------------------------------------------------------------------
# Theme / palette (dark, GNOME-Settings like)
# ---------------------------------------------------------------------------

THEME_DARK: bool = True

COLOR_BACKGROUND: str = "#161616"
COLOR_CARD: str = "#222222"
COLOR_CARD_HOVER: str = "#2A2A2A"
COLOR_TEXT: str = "#F2F2F2"
COLOR_TEXT_SECONDARY: str = "#9AA0A6"
COLOR_PRIMARY: str = "#2ECC71"
COLOR_ACCENT: str = "#3BA55D"
COLOR_BORDER: str = "#303030"

COLOR_TEMP_GREEN: str = "#2ECC71"
COLOR_TEMP_ORANGE: str = "#F5A623"
COLOR_TEMP_RED: str = "#E74C3C"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

#: Directory that contains this file (either the source checkout or the
#: system install root ``/usr/share/acer-alg``).
_BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))

ASSETS_DIR: str = os.path.join(_BASE_DIR, "assets")
ICONS_DIR: str = os.path.join(ASSETS_DIR, "icons")
THEME_CSS_PATH: str = os.path.join(_BASE_DIR, "ui", "theme.css")
LOGO_PATH: str = os.path.join(ASSETS_DIR, "acer.png")

CONFIG_DIR: str = os.path.join(os.environ.get("XDG_CONFIG_HOME",
                                              os.path.expanduser("~/.config")),
                               "acer-alg-control-center")
SETTINGS_PATH: str = os.path.join(CONFIG_DIR, "settings.json")

# Pages exposed in the sidebar, in display order.  Keys are the Gtk.Stack
# page names used by the UI.
PAGES: List[Dict[str, str]] = [
    {"name": "rgb", "label": "RGB Keyboard", "icon": "rgb.svg"},
    {"name": "gpu", "label": "GPU", "icon": "gpu.svg"},
    {"name": "hardware", "label": "Hardware", "icon": "hardware.svg"},
    {"name": "battery", "label": "Battery", "icon": "battery.svg"},
    {"name": "about", "label": "About", "icon": "about.svg"},
]
