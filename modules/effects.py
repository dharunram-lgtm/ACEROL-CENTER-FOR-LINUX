"""Keyboard lighting effects manager.

Drives the lighting modes on top of :class:`modules.rgb.RGBController`.

The UI layer never contains animation logic — it only calls the public
methods of :class:`EffectsManager`.  The manager is responsible for:

* applying **static** colours (single async apply, as before),
* running **breathing** (a background thread that smoothly ramps the
  brightness ``0,1,2,3,4,3,2,1`` and repeats),
* guaranteeing that at most **one** breathing loop exists at a time
  (start/stop are serialised with a lock, and every new loop stops and joins
  its predecessor first),
* delivering a per-step *preview* callback on the main thread so the UI can
  mirror the animation without owning any animation state.

Backend protocol
----------------
Static and breathing both go through ``alg-rgb``.  Breathing is implemented
in software (there is no native breathing command), so the manager calls
``alg-rgb <color> <brightness>`` once per brightness step.

If ``alg-rgb`` is missing every ``start_*`` method reports
``"RGB driver not installed."`` through the result callback instead of
raising.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional, Sequence

from config import RGB_BRIGHTNESS_MAX, RGB_BRIGHTNESS_MIN, RGB_COLORS
from modules.rgb import RGBController
from modules import utils

logger = utils.get_logger(__name__)

#: Result callback: ``(ok: bool, message: str)`` on the main thread.
ResultCallback = Callable[[bool, str], None]
#: Preview callback: ``(color: str, brightness: int)`` on the main thread.
PreviewCallback = Callable[[str, int], None]


class EffectsManager:
    """Coordinates static colour and breathing effects.

    Parameters
    ----------
    controller : RGBController
        Backend used to apply colours/brightness.
    result_cb : Optional[ResultCallback]
        Main-thread callback receiving ``(ok, message)`` after each command.
    preview_cb : Optional[PreviewCallback]
        Main-thread callback fired on every brightness step (or once for
        static) so the UI can animate its preview in sync with the keyboard.

    Attributes
    ----------
    current_effect : str
        Identifier of the running effect (``"static"``, ``"breathing"`` or
        ``"none"``).
    """

    #: Brightness ramp used by breathing: 0 up to max then back down to 1.
    #: The loop cycles through this sequence forever.
    BREATH_SEQUENCE: Sequence[int] = (0, 1, 2, 3, 4, 3, 2, 1)

    def __init__(self, controller: RGBController,
                 result_cb: Optional[ResultCallback] = None,
                 preview_cb: Optional[PreviewCallback] = None) -> None:
        self._controller = controller
        self._result_cb = result_cb
        self._preview_cb = preview_cb

        self._lock = threading.Lock()
        self._stop_event: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._generation = 0

        self.current_effect: str = "none"
        self._color: Optional[str] = None
        self._brightness: int = RGB_BRIGHTNESS_MAX
        self._speed: int = 3

    def set_callbacks(self, result_cb: Optional[ResultCallback] = None,
                      preview_cb: Optional[PreviewCallback] = None) -> None:
        """Attach (or replace) the result and preview callbacks.

        Parameters
        ----------
        result_cb : Optional[ResultCallback]
            Main-thread callback receiving ``(ok, message)``.
        preview_cb : Optional[PreviewCallback]
            Main-thread callback receiving ``(color, brightness)`` on every
            preview step.
        """
        self._result_cb = result_cb
        self._preview_cb = preview_cb

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_static(self, color: str, brightness: int) -> None:
        """Stop any running effect and apply ``color`` statically.

        Parameters
        ----------
        color : str
            Colour name from :data:`config.RGB_COLORS`.
        brightness : int
            Brightness between ``RGB_BRIGHTNESS_MIN`` and
            ``RGB_BRIGHTNESS_MAX``.
        """
        with self._lock:
            self._stop_effect_locked()
            self._generation += 1
            self.current_effect = "static"
            self._color = color
            self._brightness = brightness

        if not self._controller.is_available():
            self._report(False, "RGB driver not installed.")
            return

        self._emit_preview(color, brightness)
        self._controller.apply(color, brightness, self._on_apply_result)

    def start_breathing(self, color: str, brightness: int, speed: int) -> None:
        """Start (or restart) the breathing effect with the given colour.

        Any previously running breathing loop is stopped first, then a fresh
        thread is started, guaranteeing no overlapping loops.

        Parameters
        ----------
        color : str
            Colour name to breathe with.
        brightness : int
            Maximum brightness the ramp reaches.
        speed : int
            Breathing speed between 1 (slow) and 5 (fast).
        """
        if color == "off":
            # OFF disables breathing and just turns the keyboard off.
            self.start_static(color, 0)
            return

        if color not in RGB_COLORS:
            self._report(False, f"Unknown colour: {color}")
            return

        brightness = max(RGB_BRIGHTNESS_MIN,
                         min(brightness, RGB_BRIGHTNESS_MAX))
        speed = max(1, min(speed, 5))

        with self._lock:
            self._stop_effect_locked()
            self.current_effect = "breathing"
            self._color = color
            self._brightness = brightness
            self._speed = speed

            self._generation += 1
            generation = self._generation
            stop_event = threading.Event()
            self._stop_event = stop_event

            thread = threading.Thread(
                target=self._breathing_loop,
                args=(color, brightness, speed, stop_event, generation),
                name="rgb-breathing",
                daemon=True,
            )
            self._thread = thread

        thread.start()
        logger.info("Breathing started: %s @ max %d speed %d",
                    color, brightness, speed)

    def stop_effect(self) -> None:
        """Stop the currently running effect (if any).

        This is a no-op when nothing is running.
        """
        with self._lock:
            self._stop_effect_locked()
            self.current_effect = "none"

    def stop_all(self) -> None:
        """Stop every effect and release all animation state.

        Called when the application closes so no background thread outlives
        the window.
        """
        self.stop_effect()
        with self._lock:
            self._color = None

    def is_running(self) -> bool:
        """Return ``True`` when an effect (static or breathing) is active."""
        return self.current_effect != "none"

    # ------------------------------------------------------------------
    # Internals — thread safe
    # ------------------------------------------------------------------

    def _stop_effect_locked(self) -> None:
        """Stop and join any running breathing loop.

        Must be called while holding :attr:`_lock`.
        """
        if self._stop_event is not None:
            self._stop_event.set()
            self._stop_event = None
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        if self.current_effect != "none":
            logger.debug("Stopped effect '%s'", self.current_effect)

    def _breathing_loop(self, color: str, brightness: int, speed: int,
                        stop_event: threading.Event, generation: int) -> None:
        """Worker thread body: ramp brightness until told to stop."""
        interval = self._step_interval(speed)
        cycle = self._ramp_sequence(brightness)
        logger.debug("Breathing loop started (interval=%.3fs, seq=%s)",
                     interval, cycle)

        while not stop_event.is_set():
            for level in cycle:
                if stop_event.wait(interval):
                    logger.debug("Breathing loop stopped by event")
                    return
                if not self._controller.is_available():
                    self._emit_result(generation, False,
                                      "RGB driver not installed.")
                    return
                ok, message = self._controller.apply_now(color, level)
                self._emit_preview(color, level)
                if not ok:
                    logger.warning("Breathing apply failed at level %d: %s",
                                   level, message)
                    self._emit_result(generation, False, message)
                    return

    def _emit_preview(self, color: str, brightness: int) -> None:
        """Dispatch a preview step on the main thread (if a callback is set)."""
        if self._preview_cb is not None:
            with self._lock:
                generation = self._generation
            utils.GLib.idle_add(self._guarded_preview, generation, color,
                                brightness)

    def _guarded_preview(self, generation: int, color: str,
                         brightness: int) -> bool:
        """Forward a preview step only if it still belongs to the live effect."""
        with self._lock:
            stale = generation != self._generation
        if not stale and self._preview_cb is not None:
            self._preview_cb(color, brightness)
        return False

    def _emit_result(self, generation: int, ok: bool, message: str) -> None:
        """Dispatch a result on the main thread, guarded against stale runs."""
        if self._result_cb is not None:
            with self._lock:
                stale = generation != self._generation
            if not stale:
                utils.GLib.idle_add(self._result_cb, ok, message)

    def _on_apply_result(self, ok: bool, message: str) -> None:
        """Forward static-apply results coming from the controller."""
        self._report(ok, message)

    def _report(self, ok: bool, message: str) -> None:
        if self._result_cb is not None:
            self._result_cb(ok, message)

    @staticmethod
    def _ramp_sequence(brightness: int) -> Sequence[int]:
        """Build the up/down ramp capped at ``brightness``.

        For the default brightness (4) this equals the documented
        ``0,1,2,3,4,3,2,1`` cycle.

        Parameters
        ----------
        brightness : int
            Peak brightness for the ramp.

        Returns
        -------
        Sequence[int]
            Levels to cycle through forever.
        """
        if brightness <= 0:
            return (0,)
        upward = tuple(range(brightness + 1))
        downward = tuple(range(brightness - 1, 0, -1))
        return upward + downward

    @staticmethod
    def _step_interval(speed: int) -> float:
        """Map a speed (1-5) to the seconds spent per brightness step.

        Parameters
        ----------
        speed : int
            Speed between 1 (slow) and 5 (fast).

        Returns
        -------
        float
            Seconds per step (``0.5s`` for slow, ``0.1s`` for fast).
        """
        return max(0.05, 0.5 - (max(1, min(speed, 5)) - 1) * 0.1)
