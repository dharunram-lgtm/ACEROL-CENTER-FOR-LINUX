"""Fan speed collection.

Attempts to read system and GPU fan speeds from several sources:

* ``sensors`` (lm-sensors) — parses fan RPM lines.
* ``/sys/class/hwmon/hwmon*/fan*_input`` — direct sysfs reads.
* ``nvidia-smi`` — GPU fan speed when an NVIDIA GPU is present.
* ``alg-fan`` — Embedded Controller (EC) fallback used when none of the
  standard sources report anything.  The ALG fan is not exposed through the
  standard Linux APIs, only through the EC (see ``scripts/alg-fan``).

Every source is optional.  When no fan data can be found the service returns
``None`` so the UI can show *"Fan data unavailable"* instead of crashing.
"""

from __future__ import annotations

import glob
import re
from typing import Dict, List, Optional

from config import ALG_FAN_COMMAND, NVIDIA_SMI_COMMAND, SENSORS_COMMAND
from modules import utils
from modules.utils import run_command

logger = utils.get_logger(__name__)

#: ``nvidia-smi`` fields for fan speed.
_NVML_FAN_QUERY = "fan.speed"

#: Sysfs fan input files tried in order.
_FAN_SYSFS_GLOBS = [
    "/sys/class/hwmon/hwmon*/fan*_input",
    "/sys/class/hwmon/hwmon*/pwm*",
]


class FanService:
    """Collects fan speeds into plain dictionaries.

    Each ``collect()`` call performs a handful of quick reads, so it is cheap
    enough to run every couple of seconds on a background thread.
    """

    def collect(self) -> Dict[str, Optional[dict]]:
        """Gather every fan metric in one go.

        Returns
        -------
        Dict[str, Optional[dict]]
            ``{"system": {...}, "gpu": {...}}``.  Each entry is ``None`` when
            the corresponding fan data is unavailable.
        """
        system = self._collect_system_fan()
        gpu = self._collect_gpu_fan()

        if system is None and gpu is None:
            data = self._from_ec()
            if data is not None:
                return data

        return {
            "system": system,
            "gpu": gpu,
        }

    # ------------------------------------------------------------------
    # System fan
    # ------------------------------------------------------------------

    def _collect_system_fan(self) -> Optional[dict]:
        data = self._from_sensors()
        if data is None:
            data = self._from_sysfs()
        return data

    @staticmethod
    def _from_sensors() -> Optional[dict]:
        """Parse fan RPM from ``sensors`` output."""
        if not utils.command_exists(SENSORS_COMMAND):
            return None
        try:
            process = run_command([SENSORS_COMMAND], timeout=8.0, check=False)
            if process.returncode != 0:
                return None
            fans = FanService._parse_sensors_fans(process.stdout or "")
            if fans:
                rpm_values = [f["rpm"] for f in fans if f.get("rpm") is not None]
                return {
                    "label": fans[0].get("label", "System Fan"),
                    "rpm": rpm_values[0] if rpm_values else None,
                    "count": len(fans),
                }
        except (OSError, utils.subprocess.TimeoutExpired) as exc:
            logger.debug("sensors fan parse failed: %s", exc)
        return None

    @staticmethod
    def _parse_sensors_fans(output: str) -> List[dict]:
        """Extract fan entries from ``sensors`` text output."""
        fans: List[dict] = []
        current_adapter: Optional[str] = None
        fan_re = re.compile(r"^(fan\d+).*?:\s+([\d,]+)\s*RPM", re.IGNORECASE)

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if line.startswith("Adapter:"):
                current_adapter = line.split("Adapter:", 1)[1].strip()
                continue
            match = fan_re.match(line)
            if match:
                label = match.group(1)
                if current_adapter and current_adapter not in label:
                    label = f"{current_adapter} {label}"
                raw_rpm = match.group(2).replace(",", "")
                try:
                    rpm = int(raw_rpm)
                except ValueError:
                    rpm = None
                fans.append({"label": label, "rpm": rpm})
        return fans

    @staticmethod
    def _from_sysfs() -> Optional[dict]:
        """Read the first readable fan sysfs input."""
        for pattern in _FAN_SYSFS_GLOBS:
            paths = sorted(glob.glob(pattern))
            for path in paths:
                if "pwm" in path:
                    continue
                raw = utils.read_int_file(path)
                if raw is not None and raw > 0:
                    return {
                        "label": path.split("/")[-1],
                        "rpm": raw,
                        "count": 1,
                    }
        return None

    # ------------------------------------------------------------------
    # GPU fan
    # ------------------------------------------------------------------

    def _collect_gpu_fan(self) -> Optional[dict]:
        if not utils.command_exists(NVIDIA_SMI_COMMAND):
            return None
        try:
            process = run_command(
                [
                    NVIDIA_SMI_COMMAND,
                    f"--query-gpu={_NVML_FAN_QUERY}",
                    "--format=csv,noheader,nounits",
                ],
                timeout=8.0,
                check=False,
            )
            if process.returncode != 0:
                return None
            line = (process.stdout or "").strip().splitlines()
            if not line:
                return None
            value = line[0].strip()
            if value.lower() in ("n/a", "unknown", ""):
                return None
            try:
                rpm = int(float(value))
            except (TypeError, ValueError):
                return None
            return {"label": "GPU Fan", "rpm": rpm, "count": 1}
        except (OSError, utils.subprocess.TimeoutExpired) as exc:
            logger.debug("nvidia-smi fan query failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Embedded Controller fallback (alg-fan)
    # ------------------------------------------------------------------

    @staticmethod
    def _from_ec() -> Optional[Dict[str, Optional[dict]]]:
        """Read both fans through the ``alg-fan`` EC helper.

        Returns
        -------
        Optional[Dict[str, Optional[dict]]]
            ``{"system": {...}, "gpu": {...}}`` or ``None`` when the helper is
            missing or produced nothing usable.
        """
        if not utils.command_exists(ALG_FAN_COMMAND):
            return None
        try:
            process = run_command([ALG_FAN_COMMAND], timeout=8.0, check=False)
        except (OSError, utils.subprocess.TimeoutExpired) as exc:
            logger.debug("alg-fan failed: %s", exc)
            return None
        if process.returncode != 0:
            return None

        system_rpm: Optional[int] = None
        gpu_rpm: Optional[int] = None
        for line in (process.stdout or "").splitlines():
            match = re.match(r"^\s*([^:]+):\s+(\d+)\s*RPM", line, re.IGNORECASE)
            if not match:
                continue
            name, raw_rpm = match.group(1).lower(), int(match.group(2))
            if "cpu" in name:
                system_rpm = raw_rpm
            elif "gpu" in name:
                gpu_rpm = raw_rpm

        result: Dict[str, Optional[dict]] = {"system": None, "gpu": None}
        if system_rpm is not None:
            result["system"] = {"label": "System Fan", "rpm": system_rpm, "count": 1}
        if gpu_rpm is not None:
            result["gpu"] = {"label": "GPU Fan", "rpm": gpu_rpm, "count": 1}
        if result["system"] is None and result["gpu"] is None:
            return None
        return result
