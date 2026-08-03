"""Privilege and tool availability checks.

The application never crashes when an optional tool is missing.  This module
centralises every such check so the UI can show friendly messages like
``RGB driver not installed.`` instead of a traceback.

It also probes whether the desktop session can actually display a ``pkexec``
prompt, which is required for GPU switching.
"""

from __future__ import annotations

import os
import pwd
from typing import Optional

from modules.utils import command_exists, get_logger

logger = get_logger(__name__)


class Permissions:
    """Answers "is X available / allowed" questions for the UI layer.

    All checks are cheap (PATH lookup, environment inspection) and safe to
    call from the main thread.

    Attributes
    ----------
    username : str
        Name of the effective user.
    """

    def __init__(self) -> None:
        try:
            self.username = pwd.getpwuid(os.geteuid()).pw_name
        except (KeyError, OSError):
            self.username = "unknown"

    # ------------------------------------------------------------------
    # Tool availability
    # ------------------------------------------------------------------

    def has_rgb_driver(self) -> bool:
        """Return ``True`` when the ``alg-rgb`` tool is installed."""
        return command_exists("alg-rgb")

    def has_gpu_switcher(self) -> bool:
        """Return ``True`` when ``system76-power`` is installed."""
        return command_exists("system76-power")

    def has_nvidia_toolkit(self) -> bool:
        """Return ``True`` when ``nvidia-smi`` is installed."""
        return command_exists("nvidia-smi")

    def has_upower(self) -> bool:
        """Return ``True`` when the ``upower`` command is available."""
        return command_exists("upower")

    def has_sensors(self) -> bool:
        """Return ``True`` when the ``sensors`` command is available."""
        return command_exists("sensors")

    # ------------------------------------------------------------------
    # Privileges
    # ------------------------------------------------------------------

    def can_prompt_for_root(self) -> bool:
        """Return ``True`` when a graphical root prompt can be shown.

        ``pkexec`` needs to exist and a graphical session must be available.
        Without a display the polkit agent cannot ask for a password, so GPU
        switching should be hidden/disabled in that case.
        """
        if not command_exists("pkexec"):
            return False
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    def is_root(self) -> bool:
        """Return ``True`` when the application runs as ``root``."""
        return os.geteuid() == 0

    def describe_gpu_switch(self) -> Optional[str]:
        """Explain why GPU switching is unavailable, if it is.

        Returns
        -------
        Optional[str]
            A human readable reason when switching cannot work, else ``None``.
        """
        if not self.has_gpu_switcher():
            return "GPU switching unavailable."
        if not self.can_prompt_for_root():
            return "Running without a graphical session — cannot prompt for root."
        return None
