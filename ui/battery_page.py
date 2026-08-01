"""Battery status page.

Polls ``upower`` in the background and renders percentage, state
(charging / discharging), health/capacity, energy, energy-full, voltage and
remaining / charge-complete times in a set of cards with a progress bar and
a battery icon.

All telemetry is collected on a worker thread and marshalled back to the GTK
main loop, so a slow ``upower`` call never freezes the interface.
"""

from __future__ import annotations

from typing import Dict, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from modules.battery import BatteryService
from modules.utils import format_duration, get_logger
from ui.widgets import MetricRow, PageTitle, make_card, make_heading, make_metric_row

logger = get_logger(__name__)

#: Theme icon shown for each power state.
_STATE_ICONS = {
    "charging": "battery-level-full-charging-symbolic",
    "discharging": "battery-level-full-symbolic",
    "fully-charged": "battery-full-charged-symbolic",
    "pending-charge": "battery-level-full-charging-symbolic",
    "pending-discharge": "battery-level-full-symbolic",
}

_STATE_LABELS = {
    "charging": "Charging",
    "discharging": "Discharging",
    "fully-charged": "Fully Charged",
    "pending-charge": "Pending Charge",
    "pending-discharge": "Pending Discharge",
    "unknown": "Unknown",
}


class BatteryPage(Gtk.Box):
    """Battery monitoring page.

    Parameters
    ----------
    service : BatteryService
        Backend reading battery data through ``upower``.
    refresh_interval : int
        Polling interval in seconds.
    """

    def __init__(self, service: BatteryService, refresh_interval: int = 5) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.get_style_context().add_class("page-content")

        self._service = service
        self._interval = refresh_interval
        self._timer_id: Optional[int] = None
        self._polling = False

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body.get_style_context().add_class("page-body")

        body.pack_start(
            PageTitle("Battery",
                      "Power state and battery health from upower.",
                      "battery"),
            False, False, 0)

        header_card = make_card(vertical=False, spacing=20)
        self._icon = Gtk.Image.new_from_icon_name(
            "battery-level-full-symbolic", Gtk.IconSize.DIALOG)
        self._icon.get_style_context().add_class("battery-icon")
        header_card.add(self._icon)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._percentage = Gtk.Label(label="—", xalign=0.0)
        self._percentage.get_style_context().add_class("card-big-value")
        self._state_label = Gtk.Label(label="", xalign=0.0)
        self._state_label.get_style_context().add_class("metric-value")
        info_box.pack_start(self._percentage, False, False, 0)
        info_box.pack_start(self._state_label, False, False, 0)
        header_card.add(info_box)

        self._progress = Gtk.ProgressBar()
        self._progress.set_fraction(0.0)
        self._progress.get_style_context().add_class("battery-progress")
        self._progress.set_show_text(False)
        header_card.add(self._progress)
        body.pack_start(header_card, False, False, 0)

        # --- Health card -------------------------------------------------
        health_card = make_card(vertical=True, spacing=8)
        health_card.add(make_heading("Health"))
        self._capacity = make_metric_row("Capacity")
        self._energy_design = make_metric_row("Design capacity")
        health_card.add(self._capacity)
        health_card.add(self._energy_design)
        self._health_bar = Gtk.ProgressBar()
        self._health_bar.set_fraction(0.0)
        self._health_bar.get_style_context().add_class("battery-progress")
        health_card.add(self._health_bar)
        body.pack_start(health_card, False, False, 0)

        # --- Power details card -----------------------------------------
        details_card = make_card(vertical=True, spacing=8)
        details_card.add(make_heading("Power Details"))
        self._rows: Dict[str, MetricRow] = {}
        for key, label in (("energy", "Energy"),
                           ("energy_full", "Energy Full"),
                           ("voltage", "Voltage"),
                           ("time_remaining", "Time Remaining"),
                           ("time_full", "Time Until Full")):
            self._rows[key] = make_metric_row(label)
            details_card.add(self._rows[key])
        body.pack_start(details_card, False, False, 0)

        self._status = Gtk.Label(label="", xalign=0.0)
        self._status.get_style_context().add_class("status-muted")
        body.pack_start(self._status, False, False, 0)

        self.pack_start(body, True, True, 0)

        if not service.is_available():
            self._status.set_text("Battery information unavailable.")
            self._status.get_style_context().add_class("status-error")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start periodic polling."""
        if self._timer_id is None:
            self._timer_id = GLib.timeout_add_seconds(self._interval,
                                                      self._on_timer)
            self._collect()

    def stop(self) -> None:
        """Stop periodic polling."""
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def set_interval(self, interval: int) -> None:
        """Change the polling interval.

        Parameters
        ----------
        interval : int
            New interval in seconds.
        """
        self._interval = max(1, int(interval))
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = GLib.timeout_add_seconds(self._interval,
                                                      self._on_timer)

    # ------------------------------------------------------------------
    # Data flow
    # ------------------------------------------------------------------

    def _on_timer(self) -> bool:
        self._collect()
        return True

    def _collect(self) -> None:
        if self._polling:
            return
        self._polling = True
        self._service.collect_async(self._on_data)

    def _on_data(self, data: dict) -> None:
        self._polling = False
        if data.get("percentage") is None and not self._service.is_available():
            self._status.set_text("Battery information unavailable.")
            return

        percentage = data.get("percentage")
        state = data.get("state") or "unknown"
        self._percentage.set_text(self._percent_text(percentage))
        self._update_state(state)
        self._update_icon(state, percentage)

        fraction = (percentage or 0) / 100.0
        self._progress.set_fraction(max(0.0, min(1.0, fraction)))

        capacity = data.get("capacity")
        self._rows["energy"].set_value(self._format_energy(data.get("energy")))
        self._rows["energy_full"].set_value(
            self._format_energy(data.get("energy_full")))
        self._rows["voltage"].set_value(self._format_voltage(data.get("voltage")))

        if capacity is None:
            self._capacity.set_value("N/A")
            self._health_bar.set_fraction(0.0)
        else:
            self._capacity.set_value(f"{capacity:.0f}%")
            self._health_bar.set_fraction(max(0.0, min(1.0, capacity / 100.0)))

        design = data.get("energy_design")
        self._energy_design.set_value(self._format_energy(design))

        if state == "discharging":
            self._rows["time_remaining"].set_value(
                format_duration(data.get("time_to_empty")))
            self._rows["time_full"].set_value("—")
        elif state == "charging":
            self._rows["time_full"].set_value(
                format_duration(data.get("time_to_full")))
            self._rows["time_remaining"].set_value("—")
        else:
            self._rows["time_remaining"].set_value("—")
            self._rows["time_full"].set_value("—")

        if self._status.get_style_context().has_class("status-error"):
            self._status.get_style_context().remove_class("status-error")
            self._status.set_text("")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_state(self, state: str) -> None:
        label = _STATE_LABELS.get(state, "Unknown")
        css = ("status-ok" if state == "charging"
               else "status-warning" if state == "discharging"
               else "status-muted")
        context = self._state_label.get_style_context()
        for cls in ("status-ok", "status-warning", "status-muted"):
            if context.has_class(cls):
                context.remove_class(cls)
        self._state_label.set_text(label)
        context.add_class(css)

    def _update_icon(self, state: str, percentage: Optional[int]) -> None:
        icon_name = _STATE_ICONS.get(state, "battery")
        if icon_name == "battery" and percentage is not None:
            bucket = (percentage // 20) * 20
            icon_name = f"battery-level-{bucket}-symbolic"
        self._icon.set_from_icon_name(icon_name, Gtk.IconSize.DIALOG)

    @staticmethod
    def _percent_text(percentage: Optional[int]) -> str:
        if percentage is None:
            return "—"
        return f"{percentage}%"

    @staticmethod
    def _format_energy(value: Optional[float]) -> str:
        if value is None:
            return "N/A"
        return f"{value:.1f} Wh"

    @staticmethod
    def _format_voltage(value: Optional[float]) -> str:
        if value is None:
            return "N/A"
        return f"{value:.2f} V"
