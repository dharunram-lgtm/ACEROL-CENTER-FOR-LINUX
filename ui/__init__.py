"""GTK user interface package.

Every visual element lives here and only here.  UI code never executes
subprocesses or talks to hardware directly — it consumes the plain
dictionaries and callbacks exposed by the ``modules`` package.

Modules
-------
window
    Main application window and sidebar/stack layout.
sidebar
    Custom navigation sidebar.
rgb_page, gpu_page, monitor_page, battery_page, about_page
    One page per feature.
widgets
    Small reusable visual building blocks (cards, icons, headings).
dialogs
    Confirmation and error dialogs.
theme.css
    Application stylesheet (dark theme).
"""
