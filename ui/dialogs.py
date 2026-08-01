"""Modal dialogs used across the application.

* :func:`show_message` - informational message box.
* :func:`show_error` - error box (used when backends are missing).
* :func:`confirm` - yes/no confirmation that runs a callback on the main
  thread without blocking the event loop.

All dialogs are parented to the main window and styled via the shared theme.
"""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

#: Response callback signature: ``callback(confirmed: bool)``.
ConfirmCallback = Callable[[bool], None]


def _make_dialog(parent: Gtk.Window, title: str, message: str,
                 kind: Gtk.MessageType) -> Gtk.MessageDialog:
    """Build and show a message dialog.

    Parameters
    ----------
    parent : Gtk.Window
        Transient parent window.
    title : str
        Dialog title.
    message : str
        Primary text.
    kind : Gtk.MessageType
        Message severity/icon.

    Returns
    -------
    Gtk.MessageDialog
        The dialog, already shown.
    """
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        destroy_with_parent=True,
        message_type=kind,
        buttons=Gtk.ButtonsType.OK,
        text=title,
    )
    dialog.format_secondary_text(message)
    dialog.get_style_context().add_class("app-dialog")
    dialog.connect("response", lambda *_: dialog.destroy())
    dialog.show()
    return dialog


def show_message(parent: Gtk.Window, title: str, message: str) -> Gtk.MessageDialog:
    """Display an informational message box.

    Parameters
    ----------
    parent : Gtk.Window
        Transient parent window.
    title : str
        Dialog title.
    message : str
        Primary text.

    Returns
    -------
    Gtk.MessageDialog
        The dialog handle.
    """
    return _make_dialog(parent, title, message, Gtk.MessageType.INFO)


def show_error(parent: Gtk.Window, title: str, message: str) -> Gtk.MessageDialog:
    """Display an error box.

    Parameters
    ----------
    parent : Gtk.Window
        Transient parent window.
    title : str
        Dialog title.
    message : str
        Primary text.

    Returns
    -------
    Gtk.MessageDialog
        The dialog handle.
    """
    return _make_dialog(parent, title, message, Gtk.MessageType.ERROR)


def show_warning(parent: Gtk.Window, title: str, message: str) -> Gtk.MessageDialog:
    """Display a warning box.

    Parameters
    ----------
    parent : Gtk.Window
        Transient parent window.
    title : str
        Dialog title.
    message : str
        Primary text.

    Returns
    -------
    Gtk.MessageDialog
        The dialog handle.
    """
    return _make_dialog(parent, title, message, Gtk.MessageType.WARNING)


def confirm(parent: Gtk.Window, title: str, message: str,
            callback: ConfirmCallback,
            confirm_label: str = "Confirm") -> Gtk.MessageDialog:
    """Ask the user to confirm a destructive/privileged action.

    Non-blocking: the callback is invoked on the main thread with ``True`` or
    ``False`` once the user answers.

    Parameters
    ----------
    parent : Gtk.Window
        Transient parent window.
    title : str
        Dialog title.
    message : str
        Question text shown as the secondary label.
    callback : ConfirmCallback
        Called with ``True`` if confirmed.
    confirm_label : str
        Text of the confirm button.

    Returns
    -------
    Gtk.MessageDialog
        The dialog handle.
    """
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        destroy_with_parent=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.NONE,
        text=title,
    )
    dialog.format_secondary_text(message)
    dialog.get_style_context().add_class("app-dialog")

    cancel_button = dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    confirm_button = dialog.add_button(confirm_label, Gtk.ResponseType.ACCEPT)
    cancel_button.get_style_context().add_class("flat")
    confirm_button.get_style_context().add_class("primary-button")

    def _on_response(_dialog: Gtk.Dialog, response: int) -> None:
        confirmed = response == Gtk.ResponseType.ACCEPT
        dialog.destroy()
        callback(confirmed)

    dialog.connect("response", _on_response)
    dialog.show()
    return dialog
