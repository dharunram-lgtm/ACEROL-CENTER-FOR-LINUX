#!/usr/bin/env python3
"""Acer ALG Control Center — application entry point.

Initialises the logging stack, loads the theme, creates the settings store
and launches the GTK application.  Run directly (``python3 main.py``) from a
source checkout or via the installed desktop entry.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, Gtk  # noqa: E402

from config import APP_ID, APP_NAME, SETTINGS_PATH, THEME_CSS_PATH
from modules.settings import Settings
from ui.window import MainWindow

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure the root logger with a console handler.

    Parameters
    ----------
    verbose : bool
        When ``True`` use ``DEBUG`` level, otherwise ``INFO``.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)


def load_theme(application: Gtk.Application) -> None:
    """Install the application stylesheet on the GTK provider stack.

    Parameters
    ----------
    application : Gtk.Application
        Application whose windows should pick up the CSS.
    """
    if not os.path.exists(THEME_CSS_PATH):
        logger.warning("Theme file missing: %s", THEME_CSS_PATH)
        return
    try:
        css = open(THEME_CSS_PATH, "r", encoding="utf-8").read()
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load theme: %s", exc)


class AcerAlgApplication(Gtk.Application):
    """GTK application container for the control center.

    Parameters
    ----------
    verbose : bool
        Enable debug logging.
    """

    def __init__(self, verbose: bool = False) -> None:
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.verbose = verbose
        self.window: Optional[MainWindow] = None

    def do_startup(self) -> None:
        """One-time application startup."""
        Gtk.Application.do_startup(self)
        load_theme(self)

    def do_activate(self) -> None:
        """Create (or focus) the main window."""
        if self.window is not None:
            self.window.present()
            return

        settings = Settings(SETTINGS_PATH)
        logger.info("Starting %s", APP_NAME)
        self.window = MainWindow(self, settings)
        self.window.show_all()
        self.window.present()

    def do_shutdown(self) -> None:
        """Clean shutdown hook."""
        logger.info("Shutting down %s", APP_NAME)
        Gtk.Application.do_shutdown(self)


def main(argv: Optional[list] = None) -> int:
    """Application entry point.

    Parameters
    ----------
    argv : Optional[list]
        Command line arguments (defaults to ``sys.argv``).

    Returns
    -------
    int
        Process exit code.
    """
    argv = sys.argv if argv is None else argv
    verbose = "--verbose" in argv or "-v" in argv
    setup_logging(verbose)

    app = AcerAlgApplication(verbose=verbose)
    return app.run(argv)


if __name__ == "__main__":
    sys.exit(main())
