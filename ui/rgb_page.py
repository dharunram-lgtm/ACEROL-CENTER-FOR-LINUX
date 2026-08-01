"""RGB keyboard control page.

Provides colour swatches, a live animated keyboard preview, a brightness
slider (0-4), a **Lighting Effect** selector (Static / Breathing and
placeholder effects) and a **Breathing Speed** slider (1-5).

All animation and backend orchestration lives in
:class:`modules.effects.EffectsManager` — this page only calls its public
methods and renders the preview steps it receives through the callback.
No timer or background thread is created here.

Behaviour
---------
* Selecting a colour re-applies the current effect with that colour; the
  ``off`` colour stops every effect and switches back to Static.
* Changing brightness/speed while Breathing is active restarts the loop
  immediately (the manager stops and joins the old loop first).
* Missing ``alg-rgb`` disables the controls, shows the *"RGB Driver Not
  Installed"* dialog and refuses to run any effect.
* Command failures surface as a non-blocking notification; nothing crashes.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from config import (RGB_BRIGHTNESS_MAX, RGB_BRIGHTNESS_MIN, RGB_COLORS,
                    RGB_EFFECT_UNSUPPORTED_TOOLTIP, RGB_EFFECTS,
                    RGB_SPEED_MAX, RGB_SPEED_MIN)
from modules.effects import EffectsManager
from modules.rgb import RGBController
from modules.utils import get_logger
from ui.dialogs import notify, show_error
from ui.widgets import (PageTitle, apply_classes, clear_context_classes,
                        make_card, make_heading, style_with_css)

logger = get_logger(__name__)

#: Callbacks used for settings persistence.
ColorCallback = Callable[[str, int], None]
EffectCallback = Callable[[str, int], None]


class RGBPage(Gtk.Box):
    """Keyboard backlight configuration page.

    Parameters
    ----------
    controller : RGBController
        Backend wrapper used to apply colours.
    window : Gtk.Window
        Parent window for dialogs.
    initial_color : str
        Colour selected at startup (from settings).
    initial_brightness : int
        Brightness selected at startup (from settings).
    initial_effect : str
        Effect selected at startup (from settings).
    initial_speed : int
        Breathing speed selected at startup (from settings).
    on_changed : Optional[ColorCallback]
        Called with ``(color, brightness)`` after a successful apply.
    on_effect_changed : Optional[EffectCallback]
        Called with ``(effect, speed)`` whenever the effect or speed changes.

    Attributes
    ----------
    effects : EffectsManager
        Effect engine backing this page (also used by the window for
        shutdown).
    """

    _KEY_COUNT = 16

    def __init__(self, controller: RGBController, window: Gtk.Window,
                 initial_color: str = "green",
                 initial_brightness: int = RGB_BRIGHTNESS_MAX,
                 initial_effect: str = "static",
                 initial_speed: int = 3,
                 on_changed: Optional[ColorCallback] = None,
                 on_effect_changed: Optional[EffectCallback] = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.get_style_context().add_class("page-content")

        self._controller = controller
        self._window = window
        self._on_changed = on_changed
        self._on_effect_changed = on_effect_changed

        self.effects = EffectsManager(controller)
        self.effects.set_callbacks(result_cb=self._on_effect_result,
                                   preview_cb=self._on_preview_step)

        self._current_color = initial_color if initial_color in RGB_COLORS else "green"
        self._brightness = max(RGB_BRIGHTNESS_MIN,
                               min(initial_brightness, RGB_BRIGHTNESS_MAX))
        self._current_effect = (initial_effect
                                if initial_effect in RGB_EFFECTS else "static")
        self._speed = max(RGB_SPEED_MIN, min(initial_speed, RGB_SPEED_MAX))

        self._color_buttons: Dict[str, Gtk.Button] = {}
        self._effect_buttons: Dict[str, Gtk.ToggleButton] = {}
        self._key_blocks: list = []
        self._indicator: Optional[Gtk.EventBox] = None
        self._driver_dialog_shown = False

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body.get_style_context().add_class("page-body")
        body.pack_start(
            PageTitle("RGB Keyboard",
                      "Adjust the backlight colour, brightness and lighting "
                      "effects of the keyboard.",
                      "preferences-desktop-keyboard"),
            False, False, 0)
        body.pack_start(self._build_preview_card(), False, False, 0)
        body.pack_start(self._build_effect_card(), False, False, 0)
        body.pack_start(self._build_speed_card(), False, False, 0)
        body.pack_start(self._build_color_card(), False, False, 0)
        body.pack_start(self._build_brightness_card(), False, False, 0)
        body.pack_start(self._build_status_label(), False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(body)
        self.pack_start(scroller, True, True, 0)

        if not controller.is_available():
            self._set_unavailable("RGB driver not installed.")
            return

        # Restore the persisted effect and mirror it on the keyboard.
        self._apply_effect()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_preview_card(self) -> Gtk.EventBox:
        card = make_card(vertical=True, spacing=8)
        card.add(make_heading("Live Preview"))

        bar = Gtk.EventBox()
        bar.get_style_context().add_class("keyboard-bar")

        keys = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for _index in range(self._KEY_COUNT):
            block = Gtk.EventBox()
            block.get_style_context().add_class("key-block")
            block.set_hexpand(True)
            keys.pack_start(block, True, True, 0)
            self._key_blocks.append(block)
        bar.add(keys)
        card.add(bar)
        self._render_preview(self._current_color, self._brightness)
        return card

    def _build_effect_card(self) -> Gtk.EventBox:
        card = make_card(vertical=True, spacing=10)
        card.add(make_heading("Lighting Effect"))

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.get_style_context().add_class("segmented")
        for effect_id, info in RGB_EFFECTS.items():
            button = Gtk.ToggleButton(label=str(info["label"]))
            button.get_style_context().add_class("effect-button")
            button.set_hexpand(True)
            supported = bool(info["supported"])
            if not supported:
                button.set_sensitive(False)
                button.set_tooltip_text(RGB_EFFECT_UNSUPPORTED_TOOLTIP)
            else:
                button.connect("clicked", self._on_effect_clicked, effect_id)
            self._effect_buttons[effect_id] = button
            row.pack_start(button, True, True, 0)
        card.add(row)
        self._refresh_effect_buttons()
        return card

    def _build_speed_card(self) -> Gtk.EventBox:
        card = make_card(vertical=True, spacing=8)
        card.add(make_heading("Breathing Speed"))

        self._speed_label = Gtk.Label(label=f"{self._speed}", xalign=0.0)
        self._speed_label.get_style_context().add_class("metric-value")

        self._speed_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, RGB_SPEED_MIN, RGB_SPEED_MAX, 1)
        self._speed_scale.set_value(self._speed)
        self._speed_scale.set_size_request(-1, 28)
        self._speed_scale.connect("value-changed", self._on_speed_changed)

        endpoints = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        slow = Gtk.Label(label="Slow", xalign=0.0)
        fast = Gtk.Label(label="Fast", xalign=1.0)
        slow.get_style_context().add_class("card-caption")
        fast.get_style_context().add_class("card-caption")
        endpoints.pack_start(slow, True, True, 0)
        endpoints.pack_start(fast, True, True, 0)

        card.add(self._speed_label)
        card.add(self._speed_scale)
        card.add(endpoints)
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
        style_with_css(button,
                       f".color-button {{ background-color: {RGB_COLORS[name]}; }}")
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
    # Effect selection
    # ------------------------------------------------------------------

    def _on_effect_clicked(self, button: Gtk.ToggleButton, effect_id: str) -> None:
        if not self._controller.is_available() or not button.get_active():
            return
        if effect_id == self._current_effect:
            return
        self._current_effect = effect_id
        self._refresh_effect_buttons()
        self._apply_effect()

    def _apply_effect(self) -> None:
        effect = self._current_effect
        if self._current_color == "off":
            self.effects.start_static("off", 0)
        elif effect == "breathing":
            self.effects.start_breathing(self._current_color, self._brightness,
                                         self._speed)
        else:
            self.effects.start_static(self._current_color, self._brightness)
        self._emit_effect_changed()

    def _refresh_effect_buttons(self) -> None:
        for effect_id, button in self._effect_buttons.items():
            active = effect_id == self._current_effect
            button.set_active(active)
            context = button.get_style_context()
            if active:
                context.add_class("effect-active")
            else:
                context.remove_class("effect-active")

    # ------------------------------------------------------------------
    # Colour / brightness / speed handlers
    # ------------------------------------------------------------------

    def _on_color_clicked(self, _button: Gtk.Button, name: str) -> None:
        if not self._controller.is_available():
            return
        self._current_color = name
        self._refresh_color_buttons()

        if name == "off":
            self._current_effect = "static"
            self._refresh_effect_buttons()
            self.effects.start_static("off", 0)
        elif self._current_effect == "breathing":
            self.effects.start_breathing(name, self._brightness, self._speed)
        else:
            self.effects.start_static(name, self._brightness)

    def _on_brightness_changed(self, scale: Gtk.Scale) -> None:
        value = int(scale.get_value())
        if value == self._brightness:
            return
        self._brightness = value
        self._brightness_label.set_text(f"{value} / {RGB_BRIGHTNESS_MAX}")
        if not self._controller.is_available() or self._current_color == "off":
            return
        if self._current_effect == "breathing":
            self.effects.start_breathing(self._current_color, value, self._speed)
        else:
            self.effects.start_static(self._current_color, value)

    def _on_speed_changed(self, scale: Gtk.Scale) -> None:
        value = int(scale.get_value())
        if value == self._speed:
            return
        self._speed = value
        self._speed_label.set_text(f"{value}")
        self._emit_effect_changed()
        if (self._controller.is_available()
                and self._current_effect == "breathing"
                and self._current_color != "off"):
            self.effects.start_breathing(self._current_color, self._brightness,
                                         value)

    # ------------------------------------------------------------------
    # Effect callbacks (from EffectsManager, on the main thread)
    # ------------------------------------------------------------------

    def _on_preview_step(self, color: str, brightness: int) -> None:
        self._render_preview(color, brightness)

    def _on_effect_result(self, ok: bool, message: str) -> None:
        if ok:
            self._set_status(message, "status-ok")
            if self._on_changed is not None:
                self._on_changed(self._current_color, self._brightness)
            return

        self._set_status(message, "status-error")
        notify(self._window, "RGB command failed", message,
               timeout_ms=5000)
        if "not installed" in message.lower():
            self._set_unavailable(message)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _emit_effect_changed(self) -> None:
        if self._on_effect_changed is not None:
            self._on_effect_changed(self._current_effect, self._speed)

    # ------------------------------------------------------------------
    # Visual state
    # ------------------------------------------------------------------

    def _render_preview(self, color: str, brightness: int) -> None:
        """Paint the keyboard bar and indicator with the given state."""
        hex_color = RGB_COLORS.get(color, "#000000")
        factor = max(0.0, min(1.0, brightness / RGB_BRIGHTNESS_MAX))
        faded = self._fade_hex(hex_color, factor)

        for block in self._key_blocks:
            style_with_css(block, f".key-block {{ background-color: {faded}; }}")

        if self._indicator is not None:
            style_with_css(self._indicator,
                           f".color-indicator-dot {{ background-color: {faded}; }}")

    def _refresh_color_buttons(self) -> None:
        for name, button in self._color_buttons.items():
            context = button.get_style_context()
            if name == self._current_color:
                context.add_class("selected")
            else:
                context.remove_class("selected")

    @staticmethod
    def _fade_hex(hex_color: str, factor: float) -> str:
        """Scale an ``#RRGGBB`` colour towards black by ``factor``.

        Parameters
        ----------
        hex_color : str
            Hex colour.
        factor : float
            Multiplier in ``[0, 1]``.

        Returns
        -------
        str
            The scaled hex colour.
        """
        value = hex_color.lstrip("#")
        channels = tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        scaled = tuple(int(round(ch * factor)) for ch in channels)
        return "#{:02X}{:02X}{:02X}".format(*scaled)

    def _set_unavailable(self, message: str) -> None:
        for widget in (self._scale, self._speed_scale):
            widget.set_sensitive(False)
        for button in self._color_buttons.values():
            button.set_sensitive(False)
        for button in self._effect_buttons.values():
            button.set_sensitive(False)
        self._set_status(message, "status-error")
        if not self._driver_dialog_shown:
            self._driver_dialog_shown = True
            show_error(self._window, "RGB Driver Not Installed", message)

    def _set_status(self, message: str, css: str) -> None:
        context = self._status.get_style_context()
        clear_context_classes(self._status, "status-ok", "status-warning",
                              "status-error", "status-muted")
        self._status.set_text(message)
        apply_classes(self._status, css)
