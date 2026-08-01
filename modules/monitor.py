"""Hardware telemetry collection.

Gathers CPU temperature and NVIDIA GPU statistics for the hardware monitor
page.  Everything here is **blocking** on purpose — it must only be invoked
from worker threads (see :func:`modules.utils.run_async`).

Data sources
------------
* CPU temperature: ``sensors -j`` (lm-sensors) with a fallback to the kernel
  thermal zones under ``/sys/class/thermal``.
* GPU: ``nvidia-smi --query-gpu=...``.  When ``nvidia-smi`` is missing or no
  NVIDIA GPU exists, :meth:`MonitorService.collect` returns GPU ``None`` so
  the UI can show *"No NVIDIA GPU detected"* instead of crashing.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from config import NVIDIA_SMI_COMMAND, SENSORS_COMMAND
from modules import utils
from modules.utils import run_command

logger = utils.get_logger(__name__)

#: Fields requested from ``nvidia-smi`` in ``--format=csv`` order.
_QUERY = (
    "name,temperature.gpu,utilization.gpu,memory.used,memory.total,"
    "power.draw,clocks.sm,driver_version,pci.bus_id"
)

#: Kernel thermal zone files tried in order when lm-sensors is unavailable.
_THERMAL_ZONES = (
    "/sys/class/thermal/thermal_zone0/temp",
    "/sys/class/thermal/thermal_zone1/temp",
    "/sys/class/thermal/thermal_zone2/temp",
)


class MonitorService:
    """Collects CPU/GPU telemetry into plain dictionaries.

    Each ``collect()`` call performs two quick subprocess invocations plus a
    sysfs read fallback, so it is cheap enough to run every couple of
    seconds on a background thread.
    """

    def __init__(self) -> None:
        self._thermal_cache: Optional[str] = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def collect(self) -> Dict[str, Optional[dict]]:
        """Gather every metric in one go.

        Returns
        -------
        Dict[str, Optional[dict]]
            ``{"cpu": {...}, "gpu": {...}}``.  The GPU entry is ``None`` when
            no NVIDIA GPU/driver is present.  CPU entry always contains at
            least a ``"name"`` key.
        """
        return {
            "cpu": self._collect_cpu(),
            "gpu": self._collect_gpu(),
        }

    def collect_async(self, callback) -> None:
        """Collect telemetry in the background and call ``callback``.

        Parameters
        ----------
        callback : Callable[[Dict[str, Optional[dict]]], None]
            Main-thread callback receiving the result of :meth:`collect`.
        """
        from modules.utils import run_async  # local import keeps API tidy

        run_async(self.collect, on_done=callback, on_error=lambda exc: callback(self._empty()))

    # ------------------------------------------------------------------
    # CPU
    # ------------------------------------------------------------------

    def _collect_cpu(self) -> dict:
        temperature = self._cpu_temperature()
        return {
            "name": utils.cpu_model_name(),
            "temperature": temperature,
        }

    def _cpu_temperature(self) -> Optional[float]:
        """Return the CPU package temperature in Celsius.

        Tries ``sensors -j`` first (lm-sensors).  If that fails, falls back
        to the first readable kernel thermal zone.
        """
        if utils.command_exists(SENSORS_COMMAND):
            value = self._temperature_from_sensors()
            if value is not None:
                return value
        return self._temperature_from_sysfs()

    def _temperature_from_sensors(self) -> Optional[float]:
        """Parse the CPU temperature from ``sensors -j`` JSON output."""
        try:
            process = run_command([SENSORS_COMMAND, "-j"], timeout=8.0,
                                  check=False)
            if process.returncode != 0:
                return None
            payload = json.loads(process.stdout or "{}")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.debug("sensors -j parse failed: %s", exc)
            return None
        return self._find_sensor_temperature(payload)

    @staticmethod
    def _find_sensor_temperature(payload: dict) -> Optional[float]:
        """Walk ``sensors -j`` output looking for the package temperature."""
        candidates: List[float] = []
        for chip, sections in payload.items():
            if not isinstance(sections, dict):
                continue
            for section, values in sections.items():
                if not isinstance(values, dict):
                    continue
                for key, value in values.items():
                    if "package id" in str(key).lower():
                        candidates.append(MonitorService._to_float(value))
                        break
                for key, value in values.items():
                    if re.search(r"core\s+\d+", str(key), re.IGNORECASE):
                        candidates.append(MonitorService._to_float(value))
        valid = [value for value in candidates if value is not None]
        return max(valid) if valid else None

    def _temperature_from_sysfs(self) -> Optional[float]:
        """Read the CPU temperature from kernel thermal zones."""
        zone = utils.first_existing(*_THERMAL_ZONES)
        if zone is None:
            return None
        raw = utils.read_int_file(zone)
        if raw is None:
            return None
        return raw / 1000.0

    # ------------------------------------------------------------------
    # GPU (NVIDIA)
    # ------------------------------------------------------------------

    def _collect_gpu(self) -> Optional[dict]:
        if not utils.command_exists(NVIDIA_SMI_COMMAND):
            return None
        try:
            process = run_command(
                [NVIDIA_SMI_COMMAND,
                 f"--query-gpu={_QUERY}",
                 "--format=csv,noheader,nounits"],
                timeout=8.0,
                check=False,
            )
            if process.returncode != 0:
                return None
            line = (process.stdout or "").strip().splitlines()
            if not line:
                return None
            return self._parse_gpu_line(line[0])
        except (OSError, utils.subprocess.TimeoutExpired) as exc:
            logger.warning("nvidia-smi failed: %s", exc)
            return None

    @staticmethod
    def _parse_gpu_line(line: str) -> dict:
        """Convert one ``nvidia-smi`` CSV line into a metric dictionary."""
        cells = utils.parse_csv_line(line)
        while len(cells) < 9:
            cells.append("")
        (
            name, temperature, usage, mem_used, mem_total,
            power, clock, driver, bus,
        ) = cells

        def _float(value: str) -> Optional[float]:
            try:
                return float(utils.strip_units(value))
            except (TypeError, ValueError):
                return None

        return {
            "name": name or None,
            "temperature": _float(temperature),
            "usage": _float(usage),
            "memory_used": _float(mem_used),
            "memory_total": _float(mem_total),
            "power": _float(power),
            "clock": _float(clock),
            "driver": driver or None,
            "bus": bus or None,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_float(value: object) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _empty() -> Dict[str, Optional[dict]]:
        return {
            "cpu": {"name": utils.cpu_model_name(), "temperature": None},
            "gpu": None,
        }
