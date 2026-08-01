"""Utility helpers shared across the application.

Everything here is intentionally free of GTK imports so it can be used from
background worker threads without touching the main loop.

Highlights
----------
* :func:`command_exists` - cheap ``shutil.which`` wrapper.
* :func:`run_command` - blocking subprocess call (threads only).
* :func:`run_async` - run a callable on a worker thread and marshal the
  result back to the GLib main loop.
* Formatting helpers for bytes, durations, temperatures and GPU clocks.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
from typing import Any, Callable, List, Optional

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402  (import order required by gi)

logger = logging.getLogger(__name__)

#: Callback invoked on the main thread with the async result.
Callback = Callable[[Any], None]
#: Callback invoked on the main thread when a background task raises.
ErrorCallback = Callable[[BaseException], None]


def get_logger(module: str) -> logging.Logger:
    """Return a namespaced logger ready to use.

    Parameters
    ----------
    module : str
        Module name, usually ``__name__`` of the caller.

    Returns
    -------
    logging.Logger
        Logger configured to use the standard Python logging stack.
    """
    return logging.getLogger(module)


def command_exists(command: str) -> bool:
    """Return ``True`` when ``command`` is available on ``PATH``.

    Parameters
    ----------
    command : str
        Executable name to look up.

    Returns
    -------
    bool
        ``True`` if the executable can be found.
    """
    return shutil.which(command) is not None


def run_command(
    args: List[str],
    timeout: float = 15.0,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Execute a command synchronously.

    This function **must only** be called from a worker thread; it blocks
    until the process exits.

    Parameters
    ----------
    args : List[str]
        Command and its arguments.
    timeout : float
        Maximum number of seconds to wait before giving up.
    check : bool
        When ``True`` raise on a non-zero exit code.

    Returns
    -------
    subprocess.CompletedProcess
        The finished process descriptor.  ``stdout`` and ``stderr`` are
        decoded UTF-8 strings.

    Raises
    ------
    FileNotFoundError
        If the executable does not exist.
    subprocess.TimeoutExpired
        If the command runs longer than ``timeout``.
    subprocess.CalledProcessError
        If ``check`` is true and the exit code is non-zero.
    """
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
        stdin=subprocess.DEVNULL,
    )


def run_async(
    worker: Callable[[], Any],
    on_done: Optional[Callback] = None,
    on_error: Optional[ErrorCallback] = None,
) -> threading.Thread:
    """Run ``worker`` on a daemon thread and marshal its result to the UI.

    The ``worker`` callable runs without blocking the GTK main loop.  When it
    returns, ``on_done`` is scheduled with :func:`GLib.idle_add` so it is
    invoked on the main thread.  Any exception raised by ``worker`` is passed
    to ``on_error`` (also on the main thread).

    Parameters
    ----------
    worker : Callable[[], Any]
        Zero argument callable executed in the background.
    on_done : Optional[Callback]
        Optional main-thread callback receiving the worker's return value.
    on_error : Optional[ErrorCallback]
        Optional main-thread callback receiving the raised exception.

    Returns
    -------
    threading.Thread
        The started background thread (for introspection/tests).
    """

    def _wrapped() -> None:
        try:
            result = worker()
        except BaseException as exc:  # noqa: BLE001 - reported to UI
            logger.error("Background task failed: %s", exc)
            if on_error is not None:
                GLib.idle_add(on_error, exc)
            return
        if on_done is not None:
            GLib.idle_add(on_done, result)

    thread = threading.Thread(target=_wrapped, daemon=True)
    thread.start()
    return thread


def format_bytes(num: Optional[float], decimals: int = 0) -> str:
    """Format a byte count into a human readable MiB/GB string.

    Parameters
    ----------
    num : Optional[float]
        Raw byte value, or ``None`` to render as "N/A".
    decimals : int
        Decimal places for values >= 1 MiB.

    Returns
    -------
    str
        Formatted value such as ``"1.4 GB"``.
    """
    if num is None:
        return "N/A"
    try:
        num = float(num)
    except (TypeError, ValueError):
        return "N/A"

    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(num) < 1024.0:
            if unit == "B":
                return f"{int(num)} {unit}"
            return f"{num:.{decimals}f} {unit}"
        num /= 1024.0
    return f"{num:.{decimals}f} PiB"


def format_megabytes(mb: Optional[float]) -> str:
    """Format an amount expressed in megabytes.

    Parameters
    ----------
    mb : Optional[float]
        Value in MB.

    Returns
    -------
    str
        Formatted value, e.g. ``"1432 MB"``.
    """
    if mb is None:
        return "N/A"
    try:
        mb = float(mb)
    except (TypeError, ValueError):
        return "N/A"
    return f"{int(round(mb))} MB"


def format_duration(seconds: Optional[float]) -> str:
    """Format a duration in seconds as ``Hh MMm``.

    Parameters
    ----------
    seconds : Optional[float]
        Duration in seconds.

    Returns
    -------
    str
        Formatted duration or ``"Calculating…"`` when unknown.
    """
    if seconds is None or seconds < 0:
        return "Calculating…"
    seconds = int(round(float(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    return f"{hours}h {minutes:02d}m"


def format_watts(value: Optional[float]) -> str:
    """Format a power draw in watts.

    Parameters
    ----------
    value : Optional[float]
        Power in watts.

    Returns
    -------
    str
        Formatted value such as ``"21W"``.
    """
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.0f}W"
    except (TypeError, ValueError):
        return "N/A"


def format_clock(value: Optional[float]) -> str:
    """Format a GPU/SM clock in MHz.

    Parameters
    ----------
    value : Optional[float]
        Clock frequency in MHz.

    Returns
    -------
    str
        Formatted value such as ``"1485 MHz"``.
    """
    if value is None:
        return "N/A"
    try:
        return f"{int(round(float(value)))} MHz"
    except (TypeError, ValueError):
        return "N/A"


def temp_class(degrees: Optional[float]) -> str:
    """Map a temperature reading to a CSS colour class.

    Parameters
    ----------
    degrees : Optional[float]
        Temperature in Celsius.

    Returns
    -------
    str
        One of ``"temp-green"``, ``"temp-orange"``, ``"temp-red"`` or
        ``"temp-none"`` when the value is unknown.
    """
    if degrees is None:
        return "temp-none"
    if degrees < 60:
        return "temp-green"
    if degrees < 80:
        return "temp-orange"
    return "temp-red"


def read_int_file(path: str, fallback: Optional[int] = None) -> Optional[int]:
    """Read a single integer from ``path``, tolerating missing/garbage data.

    Parameters
    ----------
    path : str
        Filesystem path to read.
    fallback : Optional[int]
        Value returned when the file cannot be parsed.

    Returns
    -------
    Optional[int]
        The parsed integer or ``fallback``.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read().strip()
        return int(float(content))
    except (OSError, ValueError, TypeError):
        return fallback


def first_existing(*paths: str) -> Optional[str]:
    """Return the first existing path from ``paths``.

    Parameters
    ----------
    paths : str
        Candidate filesystem paths.

    Returns
    -------
    Optional[str]
        The first path that exists, else ``None``.
    """
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def cpu_model_name() -> str:
    """Read the CPU model name from ``/proc/cpuinfo``.

    Returns
    -------
    str
        The model string of the first CPU, or ``"Unknown CPU"``.
    """
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "Unknown CPU"


def strip_units(value: str) -> str:
    """Remove measurement units and whitespace from a CSV cell.

    ``nvidia-smi`` returns values like ``"21 W"`` or ``"1485 MHz"``.

    Parameters
    ----------
    value : str
        Raw cell content.

    Returns
    -------
    str
        The numeric prefix only, e.g. ``"21"``.
    """
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return match.group(0) if match else value.strip()


def parse_csv_line(line: str) -> List[str]:
    """Split a ``nvidia-smi`` CSV line into cells.

    Parameters
    ----------
    line : str
        One line of CSV output.

    Returns
    -------
    List[str]
        Trimmed cell values.
    """
    return [cell.strip() for cell in line.split(",")]
