"""Hardware monitor page.

Shows live CPU temperature, fan speeds and, when an NVIDIA GPU is present, a
detailed GPU card (temperature, usage, VRAM, power, clocks, driver and PCI bus).

Telemetry is collected on a background thread (never on the GTK main loop)
every ``refresh_interval`` seconds through a ``GLib.timeout_add_seconds``
timer.  When the timer fires it starts a collection; the result arrives back
on the main loop and updates the widgets, so the UI never stalls even if
``nvidia-smi`` is slow.
"""

from __future__ import annotations

from typing import Dict, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from modules.monitor import MonitorService
from modules.utils import (format_clock, format_megabytes, format_watts,
                           get_logger, temp_class)
from ui.widgets import (MetricRow, PageTitle, make_card, make_heading,
                        make_metric_row)

logger = get_logger(__name__)

from config import FAN_UNAVAILABLE_MSG  # noqa: E402  (import order)


class MonitorPage(Gtk.Box):
    """Live hardware telemetry page.

    Parameters
    ----------
    service : MonitorService
        Telemetry collector.
    refresh_interval : int
        Polling interval in seconds.
    on_interval_changed : Optional[Callable[[int], None]]
        Callback fired when the user changes the refresh interval.
    """

    def __init__(self, service: MonitorService, refresh_interval: int = 2,
                 on_interval_changed=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.get_style_context().add_class("page-content")

        self._service = service
        self._interval = refresh_interval
        self._on_interval_changed = on_interval_changed
        self._timer_id: Optional[int] = None
        self._polling = False

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body.get_style_context().add_class("page-body")

        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        header_row.pack_start(
            PageTitle("Hardware",
                      "Live CPU, fan and GPU telemetry, refreshed automatically.",
                      "utilities-system-monitor"),
            True, True, 0)
        header_row.pack_start(self._build_interval_selector(), False, False, 0)
        body.pack_start(header_row, False, False, 0)

        self._cards_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self._cpu_card = self._build_cpu_card()
        self._fan_card = self._build_fan_card()
        self._gpu_card = self._build_gpu_card()
        self._cards_box.pack_start(self._cpu_card, True, True, 0)
        self._cards_box.pack_start(self._fan_card, True, True, 0)
        self._cards_box.pack_start(self._gpu_card, True, True, 0)
        body.pack_start(self._cards_box, True, True, 0)

        self._status = Gtk.Label(label="", xalign=0.0)
        self._status.get_style_context().add_class("status-muted")
        body.pack_start(self._status, False, False, 0)

        self.pack_start(body, True, True, 0)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the automatic refresh timer."""
        if self._timer_id is None:
            self._timer_id = GLib.timeout_add_seconds(self._interval,
                                                      self._on_timer)
            self._collect()

    def stop(self) -> None:
        """Stop the automatic refresh timer."""
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def set_interval(self, interval: int) -> None:
        """Change the refresh interval and restart the timer.

        Parameters
        ----------
        interval : int
            New interval in seconds (>= 1).
        """
        self._interval = max(1, int(interval))
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = GLib.timeout_add_seconds(self._interval,
                                                      self._on_timer)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_interval_selector(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        label = Gtk.Label(label="Refresh", xalign=1.0)
        label.get_style_context().add_class("metric-label")

        combo = Gtk.ComboBoxText()
        for seconds in (1, 2, 3, 5, 10):
            combo.append(str(seconds), f"{seconds}s")
        combo.set_active_id(str(self._interval))
        combo.connect("changed", self._on_interval_changed_signal)

        box.pack_end(combo, False, False, 0)
        box.pack_end(label, False, False, 0)
        return box

    def _build_cpu_card(self) -> Gtk.EventBox:
        card = make_card(vertical=True, spacing=8, style_class="card cpu-card")
        card.add(make_heading("CPU"))
        self._cpu_name = Gtk.Label(label="", xalign=0.0, wrap=True)
        self._cpu_name.get_style_context().add_class("card-caption")
        self._cpu_temp = Gtk.Label(label="—", xalign=0.0)
        self._cpu_temp.get_style_context().add_class("card-big-value")
        card.add(self._cpu_name)
        card.add(self._cpu_temp)
        card.add(make_metric_row("Package temperature", "—"))
        return card

    def _build_fan_card(self) -> Gtk.EventBox:
        card = make_card(vertical=True, spacing=8, style_class="card fan-card")
        card.add(make_heading("Fan"))

        self._fan_placeholder = Gtk.Label(
            label=FAN_UNAVAILABLE_MSG, xalign=0.0, wrap=True, justify=Gtk.Justification.LEFT)
        self._fan_placeholder.get_style_context().add_class("status-muted")
        card.add(self._fan_placeholder)

        self._fan_name = Gtk.Label(label="", xalign=0.0, wrap=True)
        self._fan_name.get_style_context().add_class("card-caption")
        card.add(self._fan_name)

        self._fan_rpm = Gtk.Label(label="—", xalign=0.0)
        self._fan_rpm.get_style_context().add_class("card-big-value")
        card.add(self._fan_rpm)

        self._fan_rows: Dict[str, MetricRow] = {}
        for key, label in (("system", "System Fan"),
                           ("gpu", "GPU Fan")):
            self._fan_rows[key] = make_metric_row(label)
            card.add(self._fan_rows[key])
        return card

    def _build_gpu_card(self) -> Gtk.EventBox:
        card = make_card(vertical=True, spacing=8, style_class="card gpu-card")
        card.add(make_heading("GPU"))

        self._gpu_placeholder = Gtk.Label(
            label="No NVIDIA GPU detected", xalign=0.0, wrap=True)
        self._gpu_placeholder.get_style_context().add_class("status-muted")
        card.add(self._gpu_placeholder)

        self._gpu_name = Gtk.Label(label="", xalign=0.0, wrap=True)
        self._gpu_name.get_style_context().add_class("card-caption")
        card.add(self._gpu_name)

        self._gpu_temp = Gtk.Label(label="—", xalign=0.0)
        self._gpu_temp.get_style_context().add_class("card-big-value")
        card.add(self._gpu_temp)

        rows: Dict[str, MetricRow] = {}
        for key, label in (("usage", "Usage"),
                           ("memory", "VRAM"),
                           ("power", "Power Draw"),
                           ("clock", "Clock"),
                           ("driver", "Driver Version"),
                           ("bus", "PCI Bus")):
            rows[key] = make_metric_row(label)
            card.add(rows[key])
        self._gpu_rows = rows
        return card

    # ------------------------------------------------------------------
    # Data flow
    # ------------------------------------------------------------------

    def _on_timer(self) -> bool:
        """Timer callback; returns ``True`` to keep the timer alive."""
        self._collect()
        return True

    def _collect(self) -> None:
        if self._polling:
            return
        self._polling = True
        self._service.collect_async(self._on_data)

    def _on_data(self, data: Dict[str, Optional[dict]]) -> None:
        self._polling = False
        self._update_cpu(data.get("cpu") or {})
        fan = data.get("fan")
        if isinstance(fan, dict):
            self._update_fan(fan)
        self._update_gpu(data.get("gpu"))

    def _update_cpu(self, cpu: dict) -> None:
        name = cpu.get("name") or "Intel Core i5-13420H"
        temperature = cpu.get("temperature")
        self._cpu_name.set_text(name)
        self._set_temp_label(self._cpu_temp, temperature)

    def _update_gpu(self, gpu: Optional[dict]) -> None:
        has_gpu = gpu is not None
        self._gpu_placeholder.set_visible(not has_gpu)
        self._gpu_name.set_visible(has_gpu)
        self._gpu_temp.set_visible(has_gpu)
        for row in self._gpu_rows.values():
            row.set_visible(has_gpu)

        if not has_gpu:
            self._gpu_name.set_text("")
            self._gpu_temp.set_text("—")
            self._set_temp_class(self._gpu_temp, None)
            return

        self._gpu_name.set_text(gpu.get("name") or "NVIDIA GPU")
        self._set_temp_label(self._gpu_temp, gpu.get("temperature"))
        self._set_row_value("usage", self._percent(gpu.get("usage")))
        self._set_row_value("memory", self._memory(gpu))
        self._set_row_value("power", format_watts(gpu.get("power")))
        self._set_row_value("clock", format_clock(gpu.get("clock")))
        self._set_row_value("driver", gpu.get("driver") or "N/A")
        self._set_row_value("bus", gpu.get("bus") or "N/A")

    def _update_fan(self, fan: dict) -> None:
        system = fan.get("system")
        gpu_fan = fan.get("gpu")
        has_fan = system is not None or gpu_fan is not None
        has_error = fan.get("error") is not None

        if not has_fan and has_error:
            self._fan_placeholder.set_text(fan["error"])

        self._fan_placeholder.set_visible(not has_fan)
        self._fan_name.set_visible(has_fan)
        self._fan_rpm.set_visible(has_fan)
        for row in self._fan_rows.values():
            row.set_visible(has_fan)

        if not has_fan:
            self._fan_name.set_text("")
            self._fan_rpm.set_text("—")
            return

        labels = []
        if system is not None:
            labels.append(system.get("label", "System Fan"))
        if gpu_fan is not None:
            labels.append(gpu_fan.get("label", "GPU Fan"))
        self._fan_name.set_text(" / ".join(labels))

        rpm_values = []
        if system is not None and system.get("rpm") is not None:
            rpm_values.append(str(system["rpm"]))
        if gpu_fan is not None and gpu_fan.get("rpm") is not None:
            rpm_values.append(str(gpu_fan["rpm"]))
        self._fan_rpm.set_text(" RPM, ".join(rpm_values) + " RPM" if rpm_values else "—")

        self._set_fan_row("system", self._format_rpm(system))
        self._set_fan_row("gpu", self._format_rpm(gpu_fan))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_temp_label(self, label: Gtk.Label, temperature: Optional[float]) -> None:
        if temperature is None:
            label.set_text("—")
            self._set_temp_class(label, None)
        else:
            label.set_text(f"{temperature:.0f}°C")
            self._set_temp_class(label, temperature)

    def _set_temp_class(self, label: Gtk.Label, temperature: Optional[float]) -> None:
        context = label.get_style_context()
        for css in ("temp-green", "temp-orange", "temp-red", "temp-none"):
            if context.has_class(css):
                context.remove_class(css)
        context.add_class(temp_class(temperature))

    def _set_row_value(self, key: str, value: str) -> None:
        row = self._gpu_rows.get(key)
        if row is not None:
            row.set_value(value)

    def _set_fan_row(self, key: str, value: str) -> None:
        row = self._fan_rows.get(key)
        if row is not None:
            row.set_value(value)

    @staticmethod
    def _format_rpm(fan: Optional[dict]) -> str:
        if fan is None or fan.get("rpm") is None:
            return "N/A"
        return f"{fan['rpm']} RPM"

    @staticmethod
    def _percent(value: Optional[float]) -> str:
        if value is None:
            return "N/A"
        return f"{value:.0f}%"

    @staticmethod
    def _memory(gpu: dict) -> str:
        used = gpu.get("memory_used")
        total = gpu.get("memory_total")
        if used is None and total is None:
            return "N/A"
        used_text = format_megabytes(used)
        total_text = format_megabytes(total)
        return f"{used_text} / {total_text}"

    def _on_interval_changed_signal(self, combo: Gtk.ComboBoxText) -> None:
        interval = int(combo.get_active_id() or "2")
        self.set_interval(interval)
        self._status.set_text(f"Refreshing automatically every {interval}s.")
        if self._on_interval_changed is not None:
            self._on_interval_changed(interval)
