"""Shared settings persistence, theme application, and config paths."""
import os
import json

import gi

gi.require_version("Adw", "1")

from gi.repository import Adw

APP_ID      = "de.cais.SensorSuite"
CONFIG_DIR  = os.path.expanduser(f"~/.config/{APP_ID}")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

# ── About / packaging metadata ──────────────────────────────────────────────
APP_NAME    = "Sensor Suite"
APP_VERSION = "1.0"
APP_ICON    = "find-location-symbolic"
DEVELOPER   = "misc-de"
LICENSE     = "MIT License"


def load_settings():
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("settings must be a JSON object")
        return data
    except Exception:
        return {"theme": "auto", "lang": "en"}


def save_settings(s):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(s, f, indent=2)


def apply_theme(theme: str):
    Adw.StyleManager.get_default().set_color_scheme({
        "dark":  Adw.ColorScheme.FORCE_DARK,
        "light": Adw.ColorScheme.FORCE_LIGHT,
    }.get(theme, Adw.ColorScheme.DEFAULT))
