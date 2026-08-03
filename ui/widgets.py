"""Reusable visual building blocks.

A small set of widgets shared by every page so that cards, section headings
and metric rows look and behave identically across the application.

* :func:`make_card` - a rounded ``Gtk.EventBox`` container.
* :class:`MetricRow` - a "label / value" pair inside a card.
* :func:`load_pixbuf` - load an SVG/PNG asset with a graceful fallback.
* :class:`PageTitle` - standard page heading.
"""

from __future__ import annotations

import os
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gtk  # noqa: E402


class Card(Gtk.EventBox):
    """A rounded, styled container that forwards ``add`` to its inner box.

    Parameters
    ----------
    vertical : bool
        ``True`` for a vertical inner box, ``False`` for horizontal.
    spacing : int
        Spacing between packed children.
    style_class : str
        CSS class applied to the card itself.
    """

    def __init__(self, vertical: bool = True, spacing: int = 8,
                 style_class: str = "card") -> None:
        super().__init__()
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical
                            else Gtk.Orientation.HORIZONTAL, spacing=spacing)
        self.get_style_context().add_class(style_class)
        super().add(self._box)

    def add(self, child: Gtk.Widget) -> None:
        """Pack ``child`` into the card's inner box.

        Parameters
        ----------
        child : Gtk.Widget
            Widget to add.
        """
        self._box.pack_start(child, False, False, 0)


def make_card(*children: Gtk.Widget,
              vertical: bool = True,
              spacing: int = 8,
              style_class: str = "card") -> Card:
    """Build a card pre-populated with ``children``.

    Parameters
    ----------
    *children : Gtk.Widget
        Widgets placed inside the card.
    vertical : bool
        ``True`` for a vertical box, ``False`` for horizontal.
    spacing : int
        Spacing between children.
    style_class : str
        CSS class applied to the card.

    Returns
    -------
    Card
        The styled card container (an ``Gtk.EventBox`` subclass).  Call
        ``.add()`` on it to append more children.
    """
    card = Card(vertical=vertical, spacing=spacing, style_class=style_class)
    for child in children:
        card.add(child)
    return card


def make_heading(text: str, css: str = "card-title") -> Gtk.Label:
    """Create a styled section heading.

    Parameters
    ----------
    text : str
        Heading text.
    css : str
        CSS class name.

    Returns
    -------
    Gtk.Label
        The configured label.
    """
    label = Gtk.Label(label=text, xalign=0.0)
    label.get_style_context().add_class(css)
    return label


def make_metric_row(label: str, value: str = "—", css: str = "metric-value") -> "MetricRow":
    """Shortcut that builds a complete :class:`MetricRow`.

    Parameters
    ----------
    label : str
        Metric label.
    value : str
        Initial value text.
    css : str
        CSS class for the value label.

    Returns
    -------
    MetricRow
        The built row.
    """
    return MetricRow(label, value, css)


class MetricRow(Gtk.Box):
    """A horizontal ``label ........ value`` line for metric cards.

    Parameters
    ----------
    label : str
        Metric name shown on the left.
    value : str
        Metric value shown on the right (right aligned).
    css : str
        CSS class applied to the value label.
    """

    def __init__(self, label: str, value: str = "—", css: str = "metric-value") -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._label = Gtk.Label(label=label, xalign=0.0)
        self._label.get_style_context().add_class("metric-label")
        self._value = Gtk.Label(label=value, xalign=1.0)
        self._value.get_style_context().add_class(css)

        self.pack_start(self._label, True, True, 0)
        self.pack_start(self._value, False, False, 0)

    def set_value(self, value: str) -> None:
        """Update the value text.

        Parameters
        ----------
        value : str
            New value.
        """
        self._value.set_text(value)

    def set_value_class(self, css: str) -> None:
        """Swap the value label's CSS class.

        Parameters
        ----------
        css : str
            New class name.
        """
        context = self._value.get_style_context()
        for cls in ("metric-value", "temp-green", "temp-orange", "temp-red"):
            if context.has_class(cls):
                context.remove_class(cls)
        context.add_class(css)


class PageTitle(Gtk.Box):
    """Page heading composed of an optional icon, a title and a subtitle.

    Parameters
    ----------
    title : str
        Main page title.
    subtitle : str
        Supporting line under the title.
    icon_name : Optional[str]
        Theme icon name shown next to the title.
    """

    def __init__(self, title: str, subtitle: str,
                 icon_name: Optional[str] = None) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)

        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name,
                                                Gtk.IconSize.DIALOG)
            icon.get_style_context().add_class("page-icon")
            self.pack_start(icon, False, False, 0)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_label = Gtk.Label(label=title, xalign=0.0)
        title_label.get_style_context().add_class("page-title")
        subtitle_label = Gtk.Label(label=subtitle, xalign=0.0)
        subtitle_label.get_style_context().add_class("page-subtitle")
        text_box.pack_start(title_label, False, False, 0)
        text_box.pack_start(subtitle_label, False, False, 0)
        self.pack_start(text_box, True, True, 0)


def load_pixbuf(rel_path: str, size: int = 32,
                fallback_icon: str = "applications-system") -> Optional[GdkPixbuf.Pixbuf]:
    """Load an image asset, falling back to a theme icon.

    Parameters
    ----------
    rel_path : str
        Path relative to the project ``assets`` directory.
    size : int
        Target pixel size (width and height).
    fallback_icon : str
        GTK theme icon used when the file is missing or unreadable.

    Returns
    -------
    Optional[GdkPixbuf.Pixbuf]
        The loaded pixbuf or ``None`` if both sources fail.
    """
    from config import ASSETS_DIR

    path = os.path.join(ASSETS_DIR, rel_path)
    try:
        if os.path.exists(path):
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
            if pixbuf is not None:
                return pixbuf
    except Exception:  # noqa: BLE001 - missing/corrupt asset must not crash
        pass

    theme = Gtk.IconTheme.get_default()
    info = theme.lookup_icon(fallback_icon, size, 0)
    if info is not None:
        try:
            return info.load_icon()
        except Exception:  # noqa: BLE001
            return None
    return None


def clear_context_classes(widget: Gtk.Widget, *classes: str) -> None:
    """Remove a set of CSS classes from a widget's style context.

    Parameters
    ----------
    widget : Gtk.Widget
        Target widget.
    *classes : str
        CSS class names to remove.
    """
    context = widget.get_style_context()
    for css in classes:
        if context.has_class(css):
            context.remove_class(css)


def apply_classes(widget: Gtk.Widget, *classes: str) -> None:
    """Add CSS classes, avoiding duplicates.

    Parameters
    ----------
    widget : Gtk.Widget
        Target widget.
    *classes : str
        CSS class names to add.
    """
    context = widget.get_style_context()
    for css in classes:
        if not context.has_class(css):
            context.add_class(css)


def style_with_css(widget: Gtk.Widget, css_rule: str) -> None:
    """Replace a widget's dynamic CSS provider with ``css_rule``.

    Each widget keeps at most one dynamic provider: the previous rule is
    removed before the new one is applied, so the visual state is fully
    replaced instead of layered.

    Parameters
    ----------
    widget : Gtk.Widget
        Target widget whose style context receives the provider.
    css_rule : str
        Complete CSS rule(s), e.g. ``".rgb-preview { background-color: red; }"``.
    """
    context = widget.get_style_context()
    provider = getattr(widget, "_dynamic_provider", None)
    if provider is not None:
        context.remove_provider(provider)

    provider = Gtk.CssProvider()
    provider.load_from_data(css_rule.encode("utf-8"))
    context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    widget._dynamic_provider = provider
