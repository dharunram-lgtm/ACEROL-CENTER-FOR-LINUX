"""Persistent application settings.

Settings are stored as a single JSON document at
``~/.config/acer-alg-control-center/settings.json``.  The :class:`Settings`
class keeps the values in memory, writes them atomically on every change and
exposes attribute style access to the rest of the application.

Persisted keys
--------------
window_width, window_height
    Last window geometry.
rgb_color
    Last selected keyboard colour name.
rgb_brightness
    Last keyboard brightness (0-4).
last_page
    Name of the Gtk.Stack page shown when the app closed.
refresh_interval
    Hardware page refresh interval in seconds.
theme
    Theme identifier (``"dark"`` is currently the only value).
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, Optional

from config import SETTINGS_PATH
from modules.utils import get_logger

logger = get_logger(__name__)


class Settings:
    """JSON backed key/value settings store.

    Parameters
    ----------
    path : str
        Absolute path of the JSON file.  Defaults to
        :data:`config.SETTINGS_PATH`.

    Attributes
    ----------
    data : Dict[str, Any]
        In-memory settings.  Prefer the explicit getters/setters below over
        touching ``data`` directly.
    """

    DEFAULTS: Dict[str, Any] = {
        "window_width": 1100,
        "window_height": 720,
        "rgb_color": "green",
        "rgb_brightness": 4,
        "rgb_effect": "static",
        "rgb_breathing_speed": 3,
        "last_page": "rgb",
        "refresh_interval": 2,
        "theme": "dark",
    }

    def __init__(self, path: Optional[str] = None) -> None:
        self._path: str = path or SETTINGS_PATH
        self.data: Dict[str, Any] = dict(self.DEFAULTS)
        self.load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load settings from disk, merging over the defaults.

        Missing keys, a corrupt file and unreadable paths are all handled
        gracefully: defaults remain in effect and nothing is raised.
        """
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if isinstance(stored, dict):
                self.data.update(stored)
        except FileNotFoundError:
            logger.debug("No settings file yet at %s", self._path)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read settings file %s: %s",
                           self._path, exc)

    def save(self) -> None:
        """Atomically write the settings to disk.

        The document is written to a temporary file in the same directory and
        renamed over the target, so a crash in between never corrupts the
        stored settings.
        """
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            descriptor, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(self._path), suffix=".json")
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self._path)
        except OSError as exc:
            logger.warning("Could not write settings file %s: %s",
                           self._path, exc)

    # ------------------------------------------------------------------
    # Typed accessors
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Return ``data[key]`` if present else ``default``.

        Parameters
        ----------
        key : str
            Setting name.
        default : Any
            Value returned when the key is absent.

        Returns
        -------
        Any
            The stored value or ``default``.
        """
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Store ``value`` under ``key`` and persist immediately.

        Parameters
        ----------
        key : str
            Setting name.
        value : Any
            JSON-serialisable value.
        """
        self.data[key] = value
        self.save()

    def set_many(self, values: Dict[str, Any]) -> None:
        """Store several values and persist once.

        Parameters
        ----------
        values : Dict[str, Any]
            Mapping of key to JSON-serialisable value.
        """
        self.data.update(values)
        self.save()

    # ------------------------------------------------------------------
    # Named accessors used by the UI layer
    # ------------------------------------------------------------------

    def get_int(self, key: str, default: int = 0) -> int:
        """Return an integer setting.

        Parameters
        ----------
        key : str
            Setting name.
        default : int
            Fallback value.

        Returns
        -------
        int
            The stored value coerced to ``int``.
        """
        try:
            return int(self.get(key, default))
        except (TypeError, ValueError):
            return default

    def window_size(self) -> "tuple[int, int]":
        """Return the stored window size.

        Returns
        -------
        tuple[int, int]
            ``(width, height)``.
        """
        return (self.get_int("window_width", 1100),
                self.get_int("window_height", 720))

    def save_window_size(self, width: int, height: int) -> None:
        """Persist the window geometry.

        Parameters
        ----------
        width : int
            Window width in pixels.
        height : int
            Window height in pixels.
        """
        self.set_many({"window_width": width, "window_height": height})

    def rgb_color(self) -> str:
        """Return the last selected RGB colour name."""
        return str(self.get("rgb_color", "green"))

    def rgb_brightness(self) -> int:
        """Return the last selected RGB brightness (0-4)."""
        return self.get_int("rgb_brightness", 4)

    def rgb_effect(self) -> str:
        """Return the last selected lighting effect id."""
        return str(self.get("rgb_effect", "static"))

    def rgb_breathing_speed(self) -> int:
        """Return the last selected breathing speed (1-5)."""
        return self.get_int("rgb_breathing_speed", 3)

    def last_page(self) -> str:
        """Return the last visible page name."""
        return str(self.get("last_page", "rgb"))

    def refresh_interval(self) -> int:
        """Return the hardware refresh interval in seconds."""
        return max(1, self.get_int("refresh_interval", 2))

    def theme(self) -> str:
        """Return the active theme identifier."""
        return str(self.get("theme", "dark"))
