"""About page.

Shows the application logo, version, author, license, a GitHub button and
basic system information (Python, GTK, kernel and desktop environment).
"""

from __future__ import annotations

import os
import platform
from typing import List, Tuple

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from config import (APP_NAME, AUTHOR, DEVICE_MODEL, GITHUB_URL,
                    LICENSE_NAME, VERSION)
from modules.utils import get_logger
from ui.widgets import (PageTitle, load_pixbuf, make_card, make_metric_row)

logger = get_logger(__name__)


def desktop_environment() -> str:
    """Detect the running desktop environment.

    Returns
    -------
    str
        The desktop environment name, or ``"Unknown"``.
    """
    xdg_current = os.environ.get("XDG_CURRENT_DESKTOP")
    if xdg_current:
        return xdg_current
    desktop = os.environ.get("DESKTOP_SESSION")
    if desktop:
        return desktop.title()
    return "Unknown"


class AboutPage(Gtk.Box):
    """Static application information page."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.get_style_context().add_class("page-content")

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body.get_style_context().add_class("page-body")

        body.pack_start(
            PageTitle("About",
                      "Application information and system details.",
                      "help-about"),
            False, False, 0)

        # --- Identity card -------------------------------------------------
        identity = make_card(vertical=True, spacing=10)
        logo = Gtk.Image.new_from_pixbuf(load_pixbuf("acer.png", 96,
                                                     "applications-system"))
        logo.get_style_context().add_class("about-logo")
        name = Gtk.Label(label=APP_NAME)
        name.get_style_context().add_class("about-name")
        sub = Gtk.Label(label=f"for {DEVICE_MODEL}")
        sub.get_style_context().add_class("about-sub")
        version = Gtk.Label(label=f"Version {VERSION}")
        version.get_style_context().add_class("about-sub")

        identity.add(logo)
        identity.add(name)
        identity.add(sub)
        identity.add(version)

        github = Gtk.Button(label="GitHub Repository")
        github.get_style_context().add_class("link-button")
        github.connect("clicked", self._on_github_clicked)
        identity.add(github)

        license_label = Gtk.Label(
            label=f"{LICENSE_NAME} License · Author: {AUTHOR}",
            xalign=0.5)
        license_label.get_style_context().add_class("card-caption")
        identity.add(license_label)

        body.pack_start(identity, False, False, 0)

        # --- System information card --------------------------------------
        info_card = make_card(vertical=True, spacing=8)
        info_card.add(PageTitle("System Information", "",
                                "computer"))
        info_rows: List[Tuple[str, str]] = [
            ("Device", DEVICE_MODEL),
            ("Python", platform.python_version()),
            ("GTK", self._gtk_version()),
            ("Kernel", platform.release()),
            ("Desktop Environment", desktop_environment()),
            ("Platform", f"{platform.system()} {platform.machine()}"),
        ]
        for key, value in info_rows:
            info_card.add(make_metric_row(key, value))
        body.pack_start(info_card, False, False, 0)

        self.pack_start(body, True, True, 0)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _on_github_clicked(self, _button: Gtk.Button) -> None:
        try:
            Gtk.show_uri_on_window(self.get_toplevel(), GITHUB_URL,
                                   Gdk.CURRENT_TIME)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not open GitHub URL: %s", exc)

    @staticmethod
    def _gtk_version() -> str:
        return (f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}."
                f"{Gtk.get_micro_version()}")
