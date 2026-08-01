"""RGB keyboard control page.

Provides a grid of colour swatches, a live preview of the selected colour,
a brightness slider (0-4) and a status line.  Every change is applied
instantly through :class:`modules.rgb.RGBController` on a background thread,
so the UI stays responsive even when the driver is slow.

When the ``alg-rgb`` driver is missing the controls are disabled and an
error message is shown instead of raising a traceback.
"""

from __future__ import annotations

from typing import Dict, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from config import RGB_BRIGHTNESS_MAX, RGB_BRIGHTNESS_MIN, RGB_COLORS
from modules.rgb import RGBController
from modules.utils import get_logger
from ui.widgets import (PageTitle, apply_classes, clear_context_classes,
                        make_card, make_heading)

logger = get_logger(__name__)


class RGBPage(Gtk.Box):
    """Keyboard backlight configuration page.

    Parameters
    ----------
    controller : RGBController
        Backend wrapper used to apply colours.
    window : Gtk.Window
        Parent window for error dialogs.
    initial_color : str
        Colour selected at startup (from settings).
    initial_brightness : int
        Brightness selected at startup (from settings).
    on_changed : Optional[Callable[[str, int], None]]
        Callback fired after every successful apply; used to persist the
        selection.
    """

    def __init__(self, controller: RGBController, window: Gtk.Window,
                 initial_color: str = "green",
                 initial_brightness: int = RGB_BRIGHTNESS_MAX,
                 on_changed=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.get_style_context().add_class("page-content")

        self._controller = controller
        self._window = window
        self._on_changed = on_changed
        self._current_color = initial_color if initial_color in RGB_COLORS else "green"
        self._brightness = max(RGB_BRIGHTNESS_MIN,
                               min(initial_brightness, RGB_BRIGHTNESS_MAX))
        self._color_buttons: Dict[str, Gtk.Button] = {}
        self._preview: Optional[Gtk.EventBox] = None
        self._indicator: Optional[Gtk.EventBox] = None
        self._busy = False

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body.get_style_context().add_class("page-body")
        body.pack_start(
            PageTitle("RGB Keyboard",
                      "Adjust the backlight colour and brightness of the keyboard.",
                      "preferences-desktop-keyboard"),
            False, False, 0)
        body.pack_start(self._build_preview_card(), False, False, 0)
        body.pack_start(self._build_color_card(), False, False, 0)
        body.pack_start(self._build_brightness_card(), False, False, 0)
        body.pack_start(self._build_status_label(), False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(body)
        self.pack_start(scroller, True, True, 0)

        if not controller.is_available():
            self._set_unavailable("RGB driver not installed.")

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_preview_card(self) -> Gtk.EventBox:
        card = make_card(vertical=True, spacing=8)
        card.add(make_heading("Live Preview"))

        self._preview = Gtk.EventBox()
        self._preview.get_style_context().add_class("rgb-preview")
        self._refresh_preview()
        card.add(self._preview)
        return card

    def _build_color_card(self) -> Gtk.EventBox:
        card = make_card(vertical=True, spacing=10)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.pack_start(make_heading("Colour"), True, True, 0)
        self._indicator = Gtk.EventBox()
        self._indicator.get_style_context().add_class("color-indicator-dot")
        self._indicator.set_size_request(18, 18)
        header.pack_start(self._indicator, False, False, 0)
        card.add(header)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        grid.set_halign(Gtk.Align.START)
        for index, name in enumerate(RGB_COLORS):
            button = self._build_color_button(name)
            self._color_buttons[name] = button
            row, col = divmod(index, 4)
            grid.attach(button, col, row, 1, 1)
        card.add(grid)
        self._refresh_color_buttons()
        return card

    def _build_color_button(self, name: str) -> Gtk.Button:
        button = Gtk.Button()
        button.get_style_context().add_class("color-button")
        button.set_tooltip_text(name.title())
        provider = Gtk.CssProvider()
        provider.load_from_data(
            f".color-button {{ background-color: {RGB_COLORS[name]}; }}"
            .encode("utf-8"))
        button.get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        button.connect("clicked", self._on_color_clicked, name)
        return button

    def _build_brightness_card(self) -> Gtk.EventBox:
        card = make_card(vertical=True, spacing=8)
        card.add(make_heading("Brightness"))

        self._brightness_label = Gtk.Label(
            label=f"{self._brightness} / {RGB_BRIGHTNESS_MAX}", xalign=0.0)
        self._brightness_label.get_style_context().add_class("metric-value")

        self._scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, RGB_BRIGHTNESS_MIN,
            RGB_BRIGHTNESS_MAX, 1)
        self._scale.set_value(self._brightness)
        self._scale.set_size_request(-1, 32)
        self._scale.connect("value-changed", self._on_brightness_changed)

        card.add(self._brightness_label)
        card.add(self._scale)
        return card

    def _build_status_label(self) -> Gtk.Label:
        self._status = Gtk.Label(label="", xalign=0.0, wrap=True)
        self._status.get_style_context().add_class("status-muted")
        self._status.set_selectable(True)
        return self._status

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_color_clicked(self, _button: Gtk.Button, name: str) -> None:
        if self._busy or not self._controller.is_available():
            return
        self._current_color = name
        self._refresh_color_buttons()
        self._refresh_preview()
        self._apply()

    def _on_brightness_changed(self, scale: Gtk.Scale) -> None:
        value = int(scale.get_value())
        if value == self._brightness:
            return
        self._brightness = value
        self._brightness_label.set_text(f"{value} / {RGB_BRIGHTNESS_MAX}")
        if self._controller.is_available():
            self._apply()

    def _apply(self) -> None:
        self._busy = True
        self._set_status(f"Applying {self._current_color}…", "status-muted")
        self._controller.apply(
            self._current_color, self._brightness, self._on_apply_result)

    def _on_apply_result(self, ok: bool, message: str) -> None:
        self._busy = False
        if ok:
            self._set_status(message, "status-ok")
            if self._on_changed is not None:
                self._on_changed(self._current_color, self._brightness)
        else:
            self._set_status(message, "status-error")
            self._set_unavailable(message)

    # ------------------------------------------------------------------
    # Visual state
    # ------------------------------------------------------------------

    def _refresh_preview(self) -> None:
        if self._preview is None:
            return
        provider = Gtk.CssProvider()
        provider.load_from_data(
            f".rgb-preview {{ background-color: {RGB_COLORS[self._current_color]}; "
            f"color: #FFFFFF; }}".encode("utf-8"))
        self._preview.get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        if self._indicator is not None:
            provider = Gtk.CssProvider()
            provider.load_from_data(
                f".color-indicator-dot {{ background-color: "
                f"{RGB_COLORS[self._current_color]}; }}".encode("utf-8"))
            self._indicator.get_style_context().add_provider(
                provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _refresh_color_buttons(self) -> None:
        for name, button in self._color_buttons.items():
            context = button.get_style_context()
            if name == self._current_color:
                context.add_class("selected")
            else:
                context.remove_class("selected")

    def _set_unavailable(self, message: str) -> None:
        for widget in (self._scale,):
            widget.set_sensitive(False)
        for button in self._color_buttons.values():
            button.set_sensitive(False)
        self._set_status(message, "status-error")

    def _set_status(self, message: str, css: str) -> None:
        context = self._status.get_style_context()
        clear_context_classes(self._status, "status-ok", "status-warning",
                              "status-error", "status-muted")
        self._status.set_text(message)
        apply_classes(self._status, css)
