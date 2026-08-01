"""Keyboard backlight control through the ``alg-rgb`` tool.

The backend exposes a simple API::

    alg-rgb <color> <brightness>

where ``<color>`` is one of the names in :data:`config.RGB_COLORS` and
``<brightness>`` is an integer from 0 to 4.

:class:`RGBController` wraps that command.  Applying a colour is inherently a
fire-and-forget operation so it is always executed on a worker thread;
results (success or a friendly failure reason) are delivered back to the GTK
main loop through callbacks.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from config import RGB_BRIGHTNESS_MAX, RGB_BRIGHTNESS_MIN, RGB_COLORS, RGB_COMMAND
from modules import utils
from modules.utils import run_async, run_command

logger = utils.get_logger(__name__)

#: Callback receiving ``(ok: bool, message: str)`` on the main thread.
ApplyCallback = Callable[[bool, str], None]


class RGBController:
    """Stateless wrapper around the ``alg-rgb`` command line tool.

    Parameters
    ----------
    available_cb : Optional[Callable[[bool], None]]
        Optional main-thread callback fired when availability is discovered
        asynchronously (used by the UI to disable the controls).
    """

    def __init__(self, available_cb: Optional[Callable[[bool], None]] = None) -> None:
        self._available: Optional[bool] = None
        self._available_cb = available_cb

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def colors(self) -> Dict[str, str]:
        """Map of colour name to hexadecimal value."""
        return dict(RGB_COLORS)

    def is_available(self) -> bool:
        """Return ``True`` when ``alg-rgb`` is on ``PATH``.

        Runs synchronously; it is only a ``which`` lookup so it is safe on
        the main thread.
        """
        if self._available is None:
            self._available = utils.command_exists(RGB_COMMAND)
        return self._available

    def brightness_range(self) -> "tuple[int, int]":
        """Return ``(min, max)`` supported brightness values."""
        return RGB_BRIGHTNESS_MIN, RGB_BRIGHTNESS_MAX

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def apply(self, color: str, brightness: int,
              callback: Optional[ApplyCallback] = None) -> None:
        """Apply a colour at a given brightness without blocking the UI.

        Parameters
        ----------
        color : str
            Colour name from :data:`config.RGB_COLORS`.
        brightness : int
            Brightness level between ``RGB_BRIGHTNESS_MIN`` and
            ``RGB_BRIGHTNESS_MAX``.
        callback : Optional[ApplyCallback]
            Main-thread callback ``(ok, message)``.  On failure ``message``
            contains a human readable reason such as ``"RGB driver not
            installed."``
        """
        if not self.is_available():
            self._report(callback, False, "RGB driver not installed.")
            return

        if color not in RGB_COLORS:
            self._report(callback, False, f"Unknown colour: {color}")
            return

        brightness = max(RGB_BRIGHTNESS_MIN, min(brightness, RGB_BRIGHTNESS_MAX))
        args = [RGB_COMMAND, color, str(brightness)]

        def _worker() -> str:
            process = run_command(args, timeout=10.0, check=False)
            if process.returncode == 0:
                return ""
            error = (process.stderr or process.stdout or "").strip()
            return error or f"{RGB_COMMAND} failed with exit code {process.returncode}"

        def _done(message: str) -> None:
            if not message:
                logger.info("Applied RGB: %s @ %d", color, brightness)
                self._report(callback, True, f"Keyboard set to {color}.")
            else:
                logger.warning("RGB apply failed: %s", message)
                self._report(callback, False, self._friendly_error(message))

        run_async(_worker, on_done=_done, on_error=self._on_error(callback))

    def preview_hex(self, color: str) -> str:
        """Return the hexadecimal value of ``color``.

        Parameters
        ----------
        color : str
            Colour name.

        Returns
        -------
        str
            Hex value, or ``"#000000"`` for unknown colours.
        """
        return RGB_COLORS.get(color, "#000000")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _friendly_error(message: str) -> str:
        """Translate a raw driver error into an actionable message.

        Parameters
        ----------
        message : str
            Raw stderr/stdout from ``alg-rgb``.

        Returns
        -------
        str
            Human readable explanation, including a suggested fix when the
            failure is caused by device permissions.
        """
        lowered = message.lower()
        if "permission denied" in lowered or "eacces" in lowered:
            return ("Cannot access the keyboard RGB device (permission "
                    "denied). Give your user access with:\n"
                    "  sudo usermod -aG alg-rgb $USER\n"
                    "then log out and back in.")
        if "no such file" in lowered or "enodev" in lowered \
                or "not found" in lowered or "no compatible" in lowered:
            return ("The RGB keyboard was not detected. Make sure the "
                    "device is connected and the driver is loaded.")
        return message

    @staticmethod
    def _report(callback: Optional[ApplyCallback], ok: bool, message: str) -> None:
        if callback is not None:
            callback(ok, message)

    def _on_error(self, callback: Optional[ApplyCallback]) -> utils.ErrorCallback:
        def _handle(exc: BaseException) -> None:
            self._report(callback, False, f"Could not run {RGB_COMMAND}: {exc}")
        return _handle
