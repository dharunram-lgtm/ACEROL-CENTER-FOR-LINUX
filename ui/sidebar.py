"""Custom navigation sidebar.

Instead of the built-in ``Gtk.StackSidebar`` a purpose-built sidebar gives us
full control over the look: an application header (logo + name) on top, then
one flat row per page with an SVG icon and a label.

Rows are ``Gtk.ListBoxRow`` instances styled through ``theme.css``.  The
sidebar emits ``"page-selected"`` with the page name whenever the selection
changes, which the window uses to switch the ``Gtk.Stack``.
"""

from __future__ import annotations

from typing import Dict, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GObject, Gtk  # noqa: E402

from config import APP_NAME, PAGES
from modules.utils import get_logger
from ui.widgets import load_pixbuf

logger = get_logger(__name__)


class Sidebar(Gtk.Box):
    """Application navigation sidebar.

    Attributes
    ----------
    selected : str
        Name of the currently selected page.
    """

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.get_style_context().add_class("sidebar")
        self.set_size_request(230, -1)

        self._rows: Dict[str, Gtk.ListBoxRow] = {}
        self.selected: str = PAGES[0]["name"]

        self.pack_start(self._build_header(), False, False, 0)

        list_box = Gtk.ListBox()
        list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        list_box.get_style_context().add_class("sidebar-list")
        list_box.connect("row-selected", self._on_row_selected)

        for index, page in enumerate(PAGES):
            row = self._build_row(page["label"], page["name"], page["icon"])
            list_box.add(row)
            self._rows[page["name"]] = row

        self.pack_start(list_box, True, True, 0)
        self._select(self.selected)
        list_box.select_row(self._rows[self.selected])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select(self, page_name: str) -> None:
        """Programmatically select a page row.

        Parameters
        ----------
        page_name : str
            Page name from :data:`config.PAGES`.
        """
        if page_name in self._rows:
            self._select(page_name)
            self._rows[page_name].get_parent().select_row(self._rows[page_name])

    def on_page_selected(self, handler) -> None:
        """Register a callback for page changes.

        Parameters
        ----------
        handler : Callable[[str], None]
            Called with the page name on selection.
        """
        self.connect("page-selected", lambda _widget, page: handler(page))

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_header(self) -> Gtk.Box:
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        header.get_style_context().add_class("sidebar-header")

        logo = Gtk.Image.new_from_pixbuf(load_pixbuf("acer.png", 44,
                                                     "applications-system"))
        title = Gtk.Label(label=APP_NAME, xalign=0.5)
        title.get_style_context().add_class("sidebar-title")
        subtitle = Gtk.Label(label="Control Center", xalign=0.5)
        subtitle.get_style_context().add_class("sidebar-subtitle")

        header.pack_start(logo, False, False, 0)
        header.pack_start(title, False, False, 0)
        header.pack_start(subtitle, False, False, 0)
        return header

    def _build_row(self, label: str, page_name: str, icon_file: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.get_style_context().add_class("sidebar-item")
        row.set_name(page_name)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(6)
        box.set_margin_bottom(6)

        icon = Gtk.Image.new_from_pixbuf(
            load_pixbuf(f"icons/{icon_file}", 20, "applications-system"))
        text = Gtk.Label(label=label, xalign=0.0)
        text.get_style_context().add_class("sidebar-item-label")

        box.pack_start(icon, False, False, 0)
        box.pack_start(text, True, True, 0)
        row.add(box)
        return row

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def _on_row_selected(self, _list: Gtk.ListBox, row: Optional[Gtk.ListBoxRow]) -> None:
        if row is None:
            return
        self._select(row.get_name())

    def _select(self, page_name: str) -> None:
        if page_name == self.selected:
            return
        self.selected = page_name
        logger.debug("Sidebar selected %s", page_name)
        self.emit("page-selected", page_name)


#: Register the custom ``page-selected`` signal on the Sidebar type.
GObject.signal_new("page-selected", Sidebar,
                   GObject.SignalFlags.RUN_FIRST,
                   GObject.TYPE_NONE,
                   (GObject.TYPE_STRING,))
