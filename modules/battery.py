"""Battery and power state collection through ``upower``.

The service runs ``upower --dump`` (a single call) in a worker thread and
parses the human readable tree into a plain dictionary with keys like
``percentage``, ``state``, ``capacity``, ``energy``, ``energy_full``,
``voltage``, ``time_to_empty`` and ``time_to_full``.

All failure modes (missing ``upower``, no battery present, malformed output)
resolve to a dictionary with ``None`` values so the UI never sees an
exception.
"""

from __future__ import annotations

import re
from typing import Dict, Optional

from config import UPOWER_COMMAND
from modules import utils
from modules.utils import run_command

logger = utils.get_logger(__name__)

#: Line prefixes that indicate a new device section in ``upower --dump``.
_DEVICE_RE = re.compile(r"^\s*Device:\s+(\S+)")

#: Keys collected from each battery device.
_INT_KEYS = ("capacity", "percentage")
_FLOAT_KEYS = ("energy", "energy-full", "energy-full-design", "voltage",
               "time to empty", "time to full")
_TEXT_KEYS = ("native-path", "model", "state", "power supply")

#: Parse durations such as ``2.5 hours``, ``45 minutes`` or ``12 seconds``.
_DURATION_RE = re.compile(r"([\d.]+)\s*(hours?|minutes?|seconds?)")
_UNIT_TO_SECONDS = {
    "hour": 3600, "hours": 3600,
    "minute": 60, "minutes": 60,
    "second": 1, "seconds": 1,
}


class BatteryService:
    """Reads battery information through the ``upower`` command.

    Attributes
    ----------
    device_path : Optional[str]
        UPower device path of the battery found during the last poll, e.g.
        ``"/org/freedesktop/UPower/devices/battery_BAT0"``.
    """

    def __init__(self) -> None:
        self.device_path: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return ``True`` when the ``upower`` command exists."""
        return utils.command_exists(UPOWER_COMMAND)

    def collect(self) -> dict:
        """Poll ``upower`` and return battery metrics.

        Never raises.  Every key is present with ``None`` when unavailable so
        callers can render "Battery information unavailable." consistently.

        Returns
        -------
        dict
            Flat dictionary of battery metrics (see module docstring).
        """
        empty = self._empty()
        if not self.is_available():
            return empty
        try:
            process = run_command([UPOWER_COMMAND, "--dump"], timeout=8.0,
                                  check=False)
        except (OSError, utils.subprocess.TimeoutExpired) as exc:
            logger.warning("upower failed: %s", exc)
            return empty
        if process.returncode != 0:
            return empty

        devices = self._parse_dump(process.stdout or "")
        battery = self._pick_battery(devices)
        if battery is None:
            return empty
        self.device_path = battery.get("_path")
        return {
            "percentage": battery.get("percentage"),
            "state": battery.get("state"),
            "capacity": battery.get("capacity"),
            "energy": battery.get("energy"),
            "energy_full": battery.get("energy-full"),
            "energy_design": battery.get("energy-full-design"),
            "voltage": battery.get("voltage"),
            "time_to_empty": battery.get("time to empty"),
            "time_to_full": battery.get("time to full"),
            "model": battery.get("model"),
            "native_path": battery.get("native-path"),
        }

    def collect_async(self, callback) -> None:
        """Poll the battery in the background and call ``callback``.

        Parameters
        ----------
        callback : Callable[[dict], None]
            Main-thread callback receiving the result of :meth:`collect`.
        """
        utils.run_async(self.collect, on_done=callback,
                        on_error=lambda exc: callback(self._empty()))

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @classmethod
    def _parse_dump(cls, dump: str) -> Dict[str, dict]:
        """Split ``upower --dump`` output into per-device dictionaries."""
        devices: Dict[str, dict] = {}
        current: Optional[dict] = None
        current_path: Optional[str] = None

        for raw_line in dump.splitlines():
            line = raw_line.strip()
            match = _DEVICE_RE.match(line)
            if match:
                current_path = match.group(1)
                current = {"_path": current_path}
                devices[current_path] = current
                continue
            if current is None:
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key in _INT_KEYS:
                current[key] = cls._parse_int(value)
            elif key in _FLOAT_KEYS:
                current[key] = cls._parse_float(value)
            elif key in _TEXT_KEYS:
                current[key] = value or None
            else:
                current[key] = value
        return devices

    @staticmethod
    def _parse_int(value: str) -> Optional[int]:
        match = re.search(r"(\d+)", value)
        return int(match.group(1)) if match else None

    @staticmethod
    def _parse_float(value: str) -> Optional[float]:
        match = re.search(r"([\d.]+)", value)
        return float(match.group(1)) if match else None

    @classmethod
    def _pick_battery(cls, devices: Dict[str, dict]) -> Optional[dict]:
        """Pick the first device whose path mentions ``battery_``."""
        for path, data in devices.items():
            if "battery_" in path:
                return data
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty() -> dict:
        return {
            "percentage": None,
            "state": None,
            "capacity": None,
            "energy": None,
            "energy_full": None,
            "energy_design": None,
            "voltage": None,
            "time_to_empty": None,
            "time_to_full": None,
            "model": None,
            "native_path": None,
        }

    @staticmethod
    def parse_duration(value: Optional[str]) -> Optional[float]:
        """Convert a textual duration such as ``"2.5 hours"`` to seconds.

        Parameters
        ----------
        value : Optional[str]
            Duration string from ``upower``.

        Returns
        -------
        Optional[float]
            Seconds, or ``None`` when it cannot be parsed.
        """
        if not value:
            return None
        match = _DURATION_RE.search(str(value))
        if not match:
            return None
        amount = float(match.group(1))
        return amount * _UNIT_TO_SECONDS.get(match.group(2).lower(), 1.0)
