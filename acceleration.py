#!/usr/bin/env python3
import sys
import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib, Gio

from gps import (GeoLocationBackend, GPS_OK_COLOR, GPS_WAITING_COLOR,
                 format_speed)
from i18n import _
from app_config import load_settings, save_settings, APP_ID
from sensors import AccelBackend
from widgets import GForceWidget

_SMOOTH = 0.28


class AccelerationWindow(Adw.ApplicationWindow):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._settings = load_settings()
        self._lang = self._settings.get("lang", "en")
        self.set_title(_("p_gforce", self._lang))
        self.set_default_size(360, 640)

        self._x = self._y = self._z = 0.0
        self._tx = self._ty = self._tz = 0.0
        self._speed_mps = None
        self._backend    = None
        self._geo        = None
        self._anim_timer = None

        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)
        header = Adw.HeaderBar()
        header.set_centering_policy(Adw.CenteringPolicy.STRICT)
        toolbar_view.add_top_bar(header)

        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu = Gio.Menu()
        menu.append(_("s_ttl", self._lang), "app.settings")
        menu_btn.set_menu_model(menu)
        header.pack_end(menu_btn)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12)
        box.set_margin_bottom(8)
        box.set_margin_start(16)
        box.set_margin_end(16)
        toolbar_view.set_content(box)

        self._speed_value_label = Gtk.Label(label="--")
        self._speed_value_label.add_css_class("title-1")
        box.append(self._speed_value_label)

        self._speed_unit_label = Gtk.Label()
        self._speed_unit_label.add_css_class("title-4")
        self._speed_unit_label.add_css_class("dim-label")
        box.append(self._speed_unit_label)

        self._speed_status_label = Gtk.Label()
        self._speed_status_label.add_css_class("caption")
        self._speed_status_label.add_css_class("dim-label")
        box.append(self._speed_status_label)

        self._widget = GForceWidget()
        box.append(self._widget)
        self._update_speed_label()

        self._anim_timer = GLib.timeout_add(16, self._anim_tick)
        GLib.idle_add(self._init_sensor)

    def _init_sensor(self):
        self._backend = AccelBackend()
        if self._backend.available:
            self._backend.add_callback(self._on_accel)
            self._tx = self._ty = 0.0
            self._tz = 1.0
        else:
            GLib.timeout_add(33, self._demo_tick)
        self._geo = GeoLocationBackend(APP_ID)
        if self._geo.available:
            self._geo.add_callback(self._on_location)
        return False

    def _demo_tick(self):
        t = GLib.get_monotonic_time() / 1_000_000
        self._tx = math.sin(t * 1.7) * 0.6
        self._ty = math.cos(t * 1.3) * 0.4
        self._tz = 1.0 + math.sin(t * 2.9) * 0.15
        return True

    def _on_accel(self, x: float, y: float, z: float):
        self._tx, self._ty, self._tz = x / 1000.0, y / 1000.0, z / 1000.0

    def _on_location(self, _altitude_m, speed_mps):
        self._speed_mps = speed_mps
        self._update_speed_label()

    def _anim_tick(self) -> bool:
        self._x += (self._tx - self._x) * _SMOOTH
        self._y += (self._ty - self._y) * _SMOOTH
        self._z += (self._tz - self._z) * _SMOOTH
        self._widget.update(self._x, self._y, self._z)
        self._update_speed_label()
        return True

    def _unit_system(self):
        return self._settings.get("unit_system", "metric")

    def _update_speed_label(self):
        has_speed = self._speed_mps is not None
        value, unit = format_speed(self._speed_mps, self._unit_system())
        color = GPS_OK_COLOR if has_speed else GPS_WAITING_COLOR
        self._speed_value_label.set_markup(
            f'<span foreground="{color}">{GLib.markup_escape_text(value)}</span>')
        self._speed_unit_label.set_text(unit)
        self._speed_status_label.set_text("" if has_speed else _("no_gps", self._lang))

    def open_settings(self):
        SettingsWindow(self, self._settings, self._lang,
                       self._on_settings_change).present()

    def _on_settings_change(self):
        self._update_speed_label()

    def do_close_request(self):
        if self._anim_timer:
            GLib.source_remove(self._anim_timer)
        if self._backend:
            self._backend.close()
        if self._geo:
            self._geo.close()
        return False


class SettingsWindow(Adw.PreferencesWindow):
    def __init__(self, parent, settings, lang, on_change):
        super().__init__(transient_for=parent, modal=True)
        self.set_title(_("s_ttl", lang))
        self._settings = settings
        self._on_change = on_change

        page = Adw.PreferencesPage()
        self.add(page)
        group = Adw.PreferencesGroup(title=_("s_units", lang))
        page.add(group)

        units_row = Adw.ComboRow(title=_("s_speed", lang))
        units_row.set_model(Gtk.StringList.new([
            _("s_unit_metric", lang), _("s_unit_imperial", lang)]))
        units_row.set_selected(0 if settings.get("unit_system", "metric") == "metric" else 1)
        units_row.connect("notify::selected", self._on_units)
        group.add(units_row)

    def _on_units(self, row, _):
        self._settings["unit_system"] = ["metric", "imperial"][row.get_selected()]
        save_settings(self._settings)
        self._on_change()


class AccelerationApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.connect("activate",
                     lambda app: AccelerationWindow(application=app).present())
        settings_action = Gio.SimpleAction.new("settings", None)
        settings_action.connect("activate", self._on_settings)
        self.add_action(settings_action)

    def _on_settings(self, _action, _param):
        win = self.get_active_window()
        if win:
            win.open_settings()


if __name__ == "__main__":
    sys.exit(AccelerationApp().run(sys.argv))
