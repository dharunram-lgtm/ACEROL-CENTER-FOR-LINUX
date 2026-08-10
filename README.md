# Acer ALG Control Center

A modern GTK3 control center for the **Acer ALG AL15G-53** laptop, built for
Ubuntu, Pop!_OS, Linux Mint and other Debian-based distributions. It feels
like AcerSense / Lenovo Vantage / MSI Center, but native to Linux.

![GitHub](https://img.shields.io/badge/license-MIT-green.svg)

## Features

- **RGB Keyboard** — pick a colour (red, orange, yellow, green, cyan, blue,
  violet, magenta, pink, white, off), set brightness 0–4, live preview, applied
  instantly via the `alg-rgb` driver.
- **GPU** — switch between Integrated / Hybrid / NVIDIA with `system76-power`
  (requires root for switching only; reading never needs root).
- **Hardware** — live CPU temperature and full NVIDIA GPU telemetry (temp,
  usage, VRAM, power, clocks, driver, PCI bus) refreshed every 2 seconds.
- **Battery** — percentage, state, health/capacity, energy, energy-full,
  voltage and time remaining via `upower`.
- **About** — app info, GitHub link, license and system information.
- Persists window size, last page, RGB selection and refresh interval to
  `~/.config/acer-alg-control-center/settings.json`.

Everything runs on background threads — the interface never freezes, and a
missing driver (`alg-rgb`, `system76-power`, `nvidia-smi`, `upower`) shows a
friendly message instead of a crash.

## Requirements

- Python 3 (>= 3.8) with PyGObject (`python3-gi`)
- GTK 3 (`gir1.2-gtk-3.0`)
- Optional backends:
  - `alg-rgb` — keyboard RGB driver
  - `system76-power` — GPU switching
  - `nvidia-smi` (from the NVIDIA driver) — GPU telemetry
  - `lm-sensors` — CPU temperature
  - `upower` — battery status

## Installation

```bash
git clone https://github.com/dharun/acer-alg-control-center.git
cd acer-alg-control-center
sudo ./install.sh            # add --with-alg-rgb to install the RGB driver too
```

This installs dependencies, copies the app to `/usr/share/acer-alg`, creates
a launcher and a desktop entry, and installs the icon. Launch it from your app
menu or run:

```bash
acer-alg-control-center
```

### GPU switching

The GPU page needs `system76-power`:

```bash
sudo apt install system76-power
```

Only switching modes requires root; the current mode is always readable.

### Keyboard RGB (optional)

Install the bundled driver with:

```bash
sudo pip install hid
sudo cp scripts/alg-rgb /usr/local/bin/
sudo chmod 755 /usr/local/bin/alg-rgb
```

or let `./install.sh --with-alg-rgb` do it for you.

## Running without installation

```bash
python3 main.py
```

## Uninstall

```bash
sudo ./uninstall.sh
```

## Project layout

```
acer-alg-control-center/
├── main.py               # application entry point
├── config.py             # constants, paths, palette
├── modules/              # business logic (no GTK)
│   ├── rgb.py            # alg-rgb wrapper
│   ├── gpu.py            # system76-power wrapper
│   ├── monitor.py        # CPU/GPU telemetry
│   ├── battery.py        # upower parsing
│   ├── utils.py          # async runner, formatters
│   ├── permissions.py    # availability/privilege checks
│   └── settings.py       # JSON settings store
├── ui/                   # GTK layer
│   ├── window.py         # main window + stack
│   ├── sidebar.py        # navigation
│   ├── rgb_page.py ...   # one page per feature
│   ├── widgets.py        # shared building blocks
│   ├── dialogs.py        # confirm/error dialogs
│   └── theme.css         # dark theme
├── assets/               # logo, icons
├── scripts/              # alg-rgb driver
├── install.sh / uninstall.sh
└── acer-alg.desktop
```
```
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
```