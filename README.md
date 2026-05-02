# Sensor Suite

A GTK4/Libadwaita sensor display app for Linux mobile devices (Phosh, FuriOS, Droidian).

![Sensor Suite](sensors.png)

## Features

- **Compass** — magnetic heading with animated needle, calibration support
- **Spirit Level** — 2D bubble level + horizontal and vertical linear levels
- **G-Force** — accelerometer display with X/Y/Z values and total magnitude

## Requirements

- Python 3.10+
- GTK 4 + Libadwaita (`python-gobject`, `gtk4`, `libadwaita`)
- One of the following sensor backends:
  - `iio-sensor-proxy` / `hadess-sensorfw-proxy` (D-Bus)
  - `sensorfwd` (FuriOS / Droidian, via `/run/sensord.sock`)
  - Direct IIO sysfs (`/sys/bus/iio/devices`)
- Without a sensor the app runs in demo mode

## Install

```bash
./install.sh
```

Copies files to `~/.local/share/sensor-suite/`, installs the icon, and registers the app in your application menu. Does nothing if already installed.

## Uninstall

```bash
./uninstall.sh
```

## Run without installing

```bash
python3 sensor_suite.py
```

## Files

| File | Description |
|---|---|
| `sensor_suite.py` | Main app — Compass, Spirit Level, G-Force in one window |
| `compass.py` | Standalone compass app |
| `spirit_level.py` | Standalone spirit level app |
| `acceleration.py` | Standalone G-force / accelerometer app |
| `install.sh` | Install to `~/.local/share` and register desktop entry |
| `uninstall.sh` | Remove installed files |

## Calibration

**Compass** — open the hamburger menu → *Calibrate compass*, then slowly draw a figure-8 in the air until all three stars are filled.

**Spirit Level** — open Settings → *Set zero point*, then tap the screen when the device is in the reference position. Auto-calibration on startup can be enabled in Settings.

## License

GPL-3.0
