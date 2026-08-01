"""Main application window.

Composes the sidebar with a ``Gtk.Stack`` containing the five feature pages,
wires the business logic controllers to the pages, restores persisted
settings (window size, last page, RGB selection) and saves them back when the
window closes.

This class owns the "glue": nothing here implements hardware access.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from config import APP_NAME, MIN_HEIGHT, MIN_WIDTH
from modules.battery import BatteryService
from modules.gpu import GPUController
from modules.monitor import MonitorService
from modules.rgb import RGBController
from modules.settings import Settings
from modules.utils import get_logger
from ui.about_page import AboutPage
from ui.battery_page import BatteryPage
from ui.gpu_page import GPUPage
from ui.monitor_page import MonitorPage
from ui.rgb_page import RGBPage
from ui.sidebar import Sidebar

logger = get_logger(__name__)


class MainWindow(Gtk.ApplicationWindow):
    """Primary application window.

    Parameters
    ----------
    application : Gtk.Application
        Owning GTK application.
    settings : Settings
        Persistent settings store.
    """

    def __init__(self, application: Gtk.Application, settings: Settings) -> None:
        super().__init__(application=application, title=APP_NAME)
        self.get_style_context().add_class("app-window")

        self._settings = settings
        self._size_save_pending = False

        width, height = settings.window_size()
        self.set_default_size(max(width, MIN_WIDTH), max(height, MIN_HEIGHT))
        self.set_size_request(MIN_WIDTH, MIN_HEIGHT)

        # --- Business logic ------------------------------------------------
        self.rgb_controller = RGBController()
        self.gpu_controller = GPUController()
        self.monitor_service = MonitorService()
        self.battery_service = BatteryService()

        # --- Pages ----------------------------------------------------------
        self.rgb_page = RGBPage(
            self.rgb_controller, self,
            initial_color=settings.rgb_color(),
            initial_brightness=settings.rgb_brightness(),
            on_changed=self._on_rgb_changed)
        self.gpu_page = GPUPage(self.gpu_controller, self,
                                on_switched=self._on_gpu_switched)
        self.gpu_controller.set_switch_callback(self.gpu_page._on_switch_result)

        self.monitor_page = MonitorPage(
            self.monitor_service,
            refresh_interval=settings.refresh_interval(),
            on_interval_changed=self._on_interval_changed)
        self.battery_page = BatteryPage(
            self.battery_service,
            refresh_interval=settings.refresh_interval())

        self.about_page = AboutPage()

        # --- Layout ----------------------------------------------------------
        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                                vhomogeneous=True)
        self._stack.add_named(self.rgb_page, "rgb")
        self._stack.add_named(self.gpu_page, "gpu")
        self._stack.add_named(self.monitor_page, "hardware")
        self._stack.add_named(self.battery_page, "battery")
        self._stack.add_named(self.about_page, "about")

        self._sidebar = Sidebar()
        self._sidebar.on_page_selected(self._on_page_selected)

        layout = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        layout.pack_start(self._sidebar, False, False, 0)
        layout.pack_start(self._stack, True, True, 0)
        self.add(layout)

        # --- Restore last page ----------------------------------------------
        last_page = settings.last_page()
        if self._stack.get_child_by_name(last_page) is not None:
            self._stack.set_visible_child_name(last_page)
            self._sidebar.select(last_page)

        # --- Events -----------------------------------------------------------
        self.connect("delete-event", self._on_delete_event)
        self.connect("key-press-event", self._on_key_press_event)
        self.connect("window-state-event", self._on_window_state_event)

        self.show_all()

        # --- Start periodic polling ------------------------------------------
        self.monitor_page.start()
        self.battery_page.start()

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _on_rgb_changed(self, color: str, brightness: int) -> None:
        self._settings.set_many({"rgb_color": color, "rgb_brightness": brightness})

    def _on_interval_changed(self, interval: int) -> None:
        self._settings.set("refresh_interval", interval)
        self.battery_page.set_interval(interval)

    def _on_gpu_switched(self, _mode: str) -> None:
        logger.info("GPU mode switched by user")

    def _on_page_selected(self, page_name: str) -> None:
        if self._stack.get_child_by_name(page_name) is not None:
            self._stack.set_visible_child_name(page_name)
            self._settings.set("last_page", page_name)

    # ------------------------------------------------------------------
    # Window events
    # ------------------------------------------------------------------

    def _on_delete_event(self, _widget: Gtk.Widget, _event) -> bool:
        self._save_size()
        self._settings.set("last_page", self._stack.get_visible_child_name())
        return False

    def _on_window_state_event(self, widget: Gtk.Widget, event) -> bool:
        if not self._size_save_pending:
            self._size_save_pending = True
            GLib.timeout_add_seconds(1, self._flush_size)
        return False

    def _flush_size(self) -> bool:
        self._size_save_pending = False
        self._save_size()
        return False

    def _save_size(self) -> None:
        size = self.get_size()
        try:
            if size != (-1, -1):
                self._settings.save_window_size(*size)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not save window size: %s", exc)

    def _on_key_press_event(self, widget: Gtk.Widget, event) -> bool:
        key = getattr(event, "keyval", None)
        if key is None:
            return False
        # 1-5 switch pages (Escape-compatible accelerator for keyboard users)
        if Gdk.keyval_name(key).isdigit():
            index = int(Gdk.keyval_name(key)) - 1
            if 0 <= index < len(self._stack.get_children()):
                self._stack.set_visible_child_index(index)
                self._sidebar.select(self._stack.get_visible_child_name())
                return True
        return False
