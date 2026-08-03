"""GPU mode switching page.

Presents three large cards (Integrated / Hybrid / NVIDIA).  The currently
active mode is highlighted.  Clicking another card asks for confirmation and,
when accepted, runs ``pkexec system76-power graphics <mode>`` in the
background.  After a successful switch a *"Logout required"* notice is shown
because the new mode only applies after logging back in.

Reading the current mode never needs root; only switching does.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from config import GPU_MODES
from modules.gpu import GPUController
from modules.utils import get_logger
from ui.dialogs import confirm, show_error, show_message
from ui.widgets import PageTitle, clear_context_classes

logger = get_logger(__name__)

_MODE_DESCRIPTIONS = {
    "integrated": "Uses only the Intel iGPU. Best battery life, "
                  "but no discrete graphics performance.",
    "hybrid": "Balanced. Uses the NVIDIA GPU only when needed. "
              "Recommended for daily use.",
    "nvidia": "Always uses the NVIDIA GPU. Best performance, "
              "highest power consumption.",
}


class GPUPage(Gtk.Box):
    """GPU mode selection page.

    Parameters
    ----------
    controller : GPUController
        Backend wrapper for reading/switching modes.
    window : Gtk.Window
        Parent window for dialogs.
    on_switched : Optional[Callable[[str], None]]
        Main-thread callback fired with the new mode after a switch.
    """

    def __init__(self, controller: GPUController, window: Gtk.Window,
                 on_switched: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.get_style_context().add_class("page-content")

        self._controller = controller
        self._window = window
        self._on_switched = on_switched
        self._mode_boxes: Dict[str, Gtk.EventBox] = {}
        self._badges: Dict[str, Gtk.Label] = {}
        self._current_mode: Optional[str] = None
        self._switching = False

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        body.get_style_context().add_class("page-body")
        body.pack_start(
            PageTitle("GPU",
                      "Switch between the integrated and discrete NVIDIA GPU.",
                      "computer"),
            False, False, 0)

        self._current_label = Gtk.Label(label="", xalign=0.0)
        self._current_label.get_style_context().add_class("metric-value")
        body.pack_start(self._current_label, False, False, 0)

        cards = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        cards.set_halign(Gtk.Align.CENTER)
        for mode in ("integrated", "hybrid", "nvidia"):
            cards.pack_start(self._build_mode_card(mode), True, True, 0)
        body.pack_start(cards, False, False, 0)

        self._notice = Gtk.Label(label="", xalign=0.0, wrap=True)
        self._notice.get_style_context().add_class("status-warning")
        body.pack_start(self._notice, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(body)
        self.pack_start(scroller, True, True, 0)

        if not controller.is_available():
            self._set_unavailable("GPU switching unavailable.")

        self.refresh_mode()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh_mode(self) -> None:
        """Re-read the current GPU mode in the background."""
        if not self._controller.is_available():
            return
        self._controller.read_mode_async(self._on_mode_read)

    def _on_mode_read(self, mode: str) -> None:
        self._current_mode = mode
        self._update_current_label(mode)
        self._highlight(mode)

    def _update_current_label(self, mode: str) -> None:
        if mode == "unknown":
            label = "Current mode: unknown"
            css = "status-muted"
        else:
            label = f"Current mode: {self._controller.mode_label(mode)}"
            css = "status-ok"
        context = self._current_label.get_style_context()
        clear_context_classes(self._current_label, "status-ok", "status-muted",
                              "status-error")
        self._current_label.set_text(label)
        context.add_class(css)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_mode_card(self, mode: str) -> Gtk.EventBox:
        info = GPU_MODES[mode]
        card = Gtk.EventBox()
        card.get_style_context().add_class("mode-card")
        card.set_hexpand(True)
        card.set_vexpand(True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        badge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        badge = Gtk.Label(label="ACTIVE")
        badge.get_style_context().add_class("mode-badge")
        badge.set_no_show_all(True)
        badge.hide()
        self._badges[mode] = badge
        badge_box.pack_end(badge, False, False, 0)
        content.pack_start(badge_box, False, False, 0)

        title = Gtk.Label(label=info["label"], xalign=0.0)
        title.get_style_context().add_class("mode-title")
        content.pack_start(title, False, False, 0)

        subtitle = Gtk.Label(label=_MODE_DESCRIPTIONS[mode], xalign=0.0,
                             wrap=True, justify=Gtk.Justification.LEFT)
        subtitle.get_style_context().add_class("mode-subtitle")
        content.pack_start(subtitle, False, False, 0)

        card.add(content)
        card.connect("button-press-event", self._on_mode_clicked, mode)
        self._mode_boxes[mode] = card
        return card

    def _highlight(self, mode: str) -> None:
        for name, box in self._mode_boxes.items():
            context = box.get_style_context()
            if name == mode and mode != "unknown":
                context.add_class("selected")
                badge = self._badges.get(name)
                if badge is not None:
                    badge.show()
            else:
                context.remove_class("selected")
                badge = self._badges.get(name)
                if badge is not None:
                    badge.hide()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_mode_clicked(self, _card: Gtk.EventBox, _event, mode: str) -> bool:
        if self._switching or not self._controller.is_available():
            return False
        if mode == self._current_mode:
            return False

        label = self._controller.mode_label(mode)
        confirm(self._window,
                f"Switch to {label}?",
                f"The NVIDIA mode only takes effect after you log out and "
                f"back in. Continue?",
                lambda ok: self._do_switch(mode) if ok else None)
        return True

    def _do_switch(self, mode: str) -> None:
        self._switching = True
        self._set_notice(f"Requesting root access to switch to "
                         f"{self._controller.mode_label(mode)}…", "status-muted")
        self._controller.switch_to(mode)

    def _on_switch_result(self, mode: str, ok: bool, message: str) -> None:
        self._switching = False
        if ok:
            self._current_mode = mode
            self._update_current_label(mode)
            self._highlight(mode)
            self._set_notice("Logout required — the new GPU mode will be "
                             "active after you log back in.", "status-warning")
            if self._on_switched is not None:
                self._on_switched(mode)
            show_message(self._window, "GPU mode changed",
                         "Switch successful.\n\nLogout required — the new "
                         "GPU mode will be active after you log back in.")
        else:
            self._set_notice(message, "status-error")
            show_error(self._window, "GPU switch failed", message)
            logger.warning("GPU switch failed for %s: %s", mode, message)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _set_notice(self, message: str, css: str) -> None:
        context = self._notice.get_style_context()
        clear_context_classes(self._notice, "status-ok", "status-warning",
                              "status-error", "status-muted")
        self._notice.set_text(message)
        context.add_class(css)

    def _set_unavailable(self, message: str) -> None:
        for card in self._mode_boxes.values():
            card.set_sensitive(False)
        self._update_current_label("unknown")
        self._set_notice(message, "status-error")
