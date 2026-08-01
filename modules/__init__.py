"""Shared low level helpers.

This package contains the *business logic* layer of the application.  Every
module is UI-agnostic: it talks to a command line tool or to the filesystem
and returns plain Python data.  The GTK layer (``ui`` package) only consumes
these results and never spawns processes itself.

Modules
-------
rgb
    Keyboard backlight control through the ``alg-rgb`` tool.
gpu
    GPU switching through ``system76-power``.
monitor
    CPU / GPU / fan hardware telemetry.
battery
    Battery and power state through ``upower``.
permissions
    Availability checks for optional tools and privileges.
settings
    Persistent JSON settings store.
utils
    Async command runner and formatting helpers.
"""
