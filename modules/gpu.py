"""GPU switching control through ``system76-power``.

Reading the current mode is a privileged-free, quick operation::

    system76-power graphics        # prints "integrated", "hybrid" or "nvidia"

Switching requires root, so the command is wrapped in ``pkexec`` and is
always run on a worker thread so the polkit prompt never freezes the UI::

    pkexec system76-power graphics nvidia

Because the mode only takes effect after a logout/login cycle, the controller
does not re-read it after a switch; the UI is responsible for telling the
user to log out.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from config import GPU_COMMAND, GPU_MODES, PKEXEC_COMMAND
from modules import utils
from modules.utils import run_async, run_command

logger = utils.get_logger(__name__)

#: Callback receiving the mode name (``"integrated"`` / ``"hybrid"`` /
#: ``"nvidia"``) on the main thread.
ModeCallback = Callable[[str], None]

#: Callback receiving ``(ok: bool, message: str)`` on the main thread.
SwitchCallback = Callable[[bool, str], None]

_UNKNOWN = "unknown"


class GPUController:
    """Wrapper around ``system76-power``.

    Parameters
    ----------
    switch_cb : Optional[Callable[[str, bool, str], None]]
        Main-thread callback fired after a switch attempt.  Receives
        ``(mode, ok, message)``.
    """

    def __init__(self, switch_cb: Optional[Callable[[str, bool, str], None]] = None) -> None:
        self._switch_cb = switch_cb

    def set_switch_callback(
            self, switch_cb: Callable[[str, bool, str], None]) -> None:
        """Attach (or replace) the switch result callback.

        Parameters
        ----------
        switch_cb : Callable[[str, bool, str], None]
            Receives ``(mode, ok, message)`` on the main thread.
        """
        self._switch_cb = switch_cb

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def modes(self) -> Dict[str, Dict[str, str]]:
        """Mapping of mode key to ``{"label": str, "arg": str}``."""
        return GPU_MODES

    def is_available(self) -> bool:
        """Return ``True`` when ``system76-power`` is installed."""
        return utils.command_exists(GPU_COMMAND)

    def mode_label(self, mode: str) -> str:
        """Return the human readable label for ``mode``."""
        info = GPU_MODES.get(mode)
        return info["label"] if info else mode.title()

    # ------------------------------------------------------------------
    # Reading the current mode (no root required)
    # ------------------------------------------------------------------

    def get_current_mode(self) -> str:
        """Return the current graphics mode synchronously.

        This is a single quick subprocess call; the UI should call it from a
        worker thread to be safe.  It never requires root.

        Returns
        -------
        str
            ``"integrated"``, ``"hybrid"``, ``"nvidia"`` or ``"unknown"``.
        """
        if not self.is_available():
            return _UNKNOWN
        try:
            process = run_command([GPU_COMMAND, "graphics"], timeout=10.0,
                                  check=False)
            mode = (process.stdout or "").strip().lower()
            if mode in GPU_MODES:
                return mode
        except (OSError, utils.subprocess.TimeoutExpired) as exc:
            logger.warning("Could not read GPU mode: %s", exc)
        return _UNKNOWN

    def read_mode_async(self, callback: ModeCallback) -> None:
        """Read the current mode in the background.

        Parameters
        ----------
        callback : ModeCallback
            Main-thread callback receiving the mode name.
        """
        def _worker() -> str:
            return self.get_current_mode()

        run_async(_worker, on_done=callback, on_error=lambda exc: callback(_UNKNOWN))

    # ------------------------------------------------------------------
    # Switching modes (root required)
    # ------------------------------------------------------------------

    def switch_to(self, mode: str) -> None:
        """Request a mode switch using ``pkexec`` in the background.

        Parameters
        ----------
        mode : str
            Target mode key (``"integrated"``, ``"hybrid"`` or ``"nvidia"``).
        """
        if mode not in GPU_MODES:
            self._emit(mode, False, f"Unknown GPU mode: {mode}")
            return
        if not self.is_available():
            self._emit(mode, False, "GPU switching unavailable.")
            return

        args = [PKEXEC_COMMAND, GPU_COMMAND, "graphics", GPU_MODES[mode]["arg"]]
        label = self.mode_label(mode)

        def _worker() -> "tuple[bool, str]":
            try:
                process = run_command(args, timeout=30.0, check=False)
            except (OSError, utils.subprocess.TimeoutExpired) as exc:
                return False, str(exc)
            if process.returncode == 0:
                return True, f"Switched to {label} mode. Logout required."
            error = (process.stderr or process.stdout or "").strip()
            return False, error or f"Could not switch to {label} mode."

        def _done(result: "tuple[bool, str]") -> None:
            ok, message = result
            logger.info("GPU switch -> %s: %s (%s)", mode, message, ok)
            self._emit(mode, ok, message)

        run_async(_worker, on_done=_done, on_error=self._on_error(mode))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _emit(self, mode: str, ok: bool, message: str) -> None:
        if self._switch_cb is not None:
            self._switch_cb(mode, ok, message)

    def _on_error(self, mode: str) -> utils.ErrorCallback:
        def _handle(exc: BaseException) -> None:
            self._emit(mode, False, f"Could not run {PKEXEC_COMMAND}: {exc}")
        return _handle
