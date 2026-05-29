#!/usr/bin/env python3
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib, Gio

from gps import (GeoLocationBackend, GPS_OK_COLOR, GPS_WAITING_COLOR,
                 format_altitude)
from i18n import _
from app_config import (load_settings, APP_ID, APP_VERSION,
                        APP_ICON, DEVELOPER, LICENSE)
from sensors import SensorPoller
from widgets import CompassWidget


class CompassWindow(Adw.ApplicationWindow):

    _CALIB_STARS = ["○○○", "●○○", "●●○", "●●●"]
    _CALIB_HINT  = ["cal_fig8_0", "cal_fig8_1", "cal_fig8_2", None]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._lang        = load_settings().get("lang", "en")
        self._target      = 0.0
        self._display     = 0.0
        self._sensor      = None
        self._geo         = None
        self._demo_timer  = None
        self._anim_timer  = None
        self._altitude_m  = None
        self._calibrating         = False
        self._cal_seen_incomplete = False

        self.set_title(_("p_compass", self._lang))
        self.set_default_size(360, 640)

        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        header = Adw.HeaderBar()
        header.set_centering_policy(Adw.CenteringPolicy.STRICT)
        toolbar_view.add_top_bar(header)

        cal_btn = Gtk.Button(label=_("s_c_btn", self._lang))
        cal_btn.connect("clicked", self._on_calibrate_clicked)
        header.pack_start(cal_btn)

        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_menu_model(self._build_menu())
        header.pack_end(menu_btn)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content_box.set_margin_top(12)
        content_box.set_margin_bottom(24)
        content_box.set_margin_start(16)
        content_box.set_margin_end(16)
        toolbar_view.set_content(content_box)

        self._altitude_label = Gtk.Label()
        self._altitude_label.add_css_class("title-4")
        self._altitude_label.set_margin_top(4)
        content_box.append(self._altitude_label)

        self._altitude_status_label = Gtk.Label(label=_("no_gps", self._lang))
        self._altitude_status_label.add_css_class("caption")
        self._altitude_status_label.add_css_class("dim-label")
        self._altitude_status_label.set_margin_top(2)
        content_box.append(self._altitude_status_label)

        self._compass = CompassWidget()
        self._compass.set_size_request(280, 280)
        content_box.append(self._compass)

        self._heading_label = Gtk.Label(label="0°")
        self._heading_label.add_css_class("title-1")
        self._heading_label.set_margin_top(16)
        content_box.append(self._heading_label)

        self._cardinal_label = Gtk.Label(label="N")
        self._cardinal_label.add_css_class("title-3")
        self._cardinal_label.add_css_class("dim-label")
        self._cardinal_label.set_margin_top(4)
        content_box.append(self._cardinal_label)

        self._calib_bar = Adw.Banner()
        self._calib_bar.connect("button-clicked", self._on_calib_bar_button)
        self._calib_bar.set_revealed(False)
        content_box.append(self._calib_bar)

        self._calib_label = Gtk.Label()
        self._calib_label.add_css_class("caption")
        self._calib_label.add_css_class("dim-label")
        self._calib_label.set_margin_top(4)
        content_box.append(self._calib_label)

        self._sensor_label = Gtk.Label()
        self._sensor_label.add_css_class("caption")
        self._sensor_label.add_css_class("dim-label")
        self._sensor_label.set_margin_top(8)
        content_box.append(self._sensor_label)

        self._anim_timer = GLib.timeout_add(16, self._anim_tick)
        GLib.idle_add(self._init_sensor)
        self._update_altitude_label()

    def _build_menu(self):
        menu = Gio.Menu()
        menu.append(_("m_about", self._lang), "app.about")
        return menu

    def _on_calibrate_clicked(self, _btn):
        lang = self._lang
        dialog = Adw.AlertDialog(
            heading=_("dlg_cmp_ttl", lang),
            body=_("dlg_cmp_body", lang),
        )
        dialog.add_response("cancel", _("btn_cancel", lang))
        dialog.add_response("start", _("btn_start", lang))
        dialog.set_response_appearance("start", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("start")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_cal_dialog_response)
        dialog.present(self)

    def _on_cal_dialog_response(self, _dialog, response):
        if response != "start":
            return
        if self._sensor:
            self._sensor.release()
            self._sensor = None
        lang = self._lang
        self._calib_label.set_text(f"{_('cal_status', lang)} {self._CALIB_STARS[0]}")
        self._calib_bar.set_title(_("cal_hold", lang))
        self._calib_bar.set_button_label(_("btn_skip", lang))
        self._calib_bar.set_revealed(True)
        self._calibrating = True
        self._cal_seen_incomplete = False
        GLib.timeout_add(300, lambda: self._restart_sensor() or False)

    def _on_calib_bar_button(self, banner):
        banner.set_revealed(False)
        self._calibrating = False

    def _restart_sensor(self):
        self._sensor = SensorPoller(self._on_heading)
        if self._sensor.available:
            self._sensor_label.set_text(self._sensor.label)
        else:
            self._sensor_label.set_text(_("demo_none", self._lang))

    def _init_sensor(self):
        self._sensor = SensorPoller(self._on_heading)
        if not self._sensor.available:
            self._sensor_label.set_text(_("demo_none", self._lang))
            self._calib_label.set_text("")
            self._demo_timer = GLib.timeout_add(50, self._demo_tick)
            self._compass.set_heading(0.0, has_sensor=False)
        else:
            self._sensor_label.set_text(self._sensor.label)
        self._geo = GeoLocationBackend(APP_ID)
        if self._geo.available:
            self._geo.add_callback(self._on_location)
        return False

    def _anim_tick(self) -> bool:
        diff = (self._target - self._display + 180) % 360 - 180
        self._display = (self._display + diff * 0.18) % 360
        self._compass.set_heading(self._display, self._sensor is not None and self._sensor.available)
        self._heading_label.set_text(f"{self._display:.0f}°")
        self._cardinal_label.set_text(self._to_cardinal(self._display))
        return True

    def _demo_tick(self):
        self._target = (self._target + 1.5) % 360
        return True

    def _on_heading(self, degrees: float, level: int, has_sensor: bool):
        self._target = degrees
        if level < 0:
            return
        lvl = min(level, 3)
        lang = self._lang
        self._calib_label.set_text(f"{_('cal_status', lang)} {self._CALIB_STARS[lvl]}")

        if self._calibrating:
            hint_key = self._CALIB_HINT[lvl]
            if hint_key is not None:
                self._cal_seen_incomplete = True
                self._calib_bar.set_title(f"{self._CALIB_STARS[lvl]}  {_(hint_key, lang)}")
                self._calib_bar.set_revealed(True)
            elif self._cal_seen_incomplete:
                self._calibrating = False
                self._calib_bar.set_button_label("OK")
                self._calib_bar.set_title(_("cal_complete", lang))
                self._calib_bar.set_revealed(True)
                GLib.timeout_add(2500, lambda: self._calib_bar.set_revealed(False) or False)

    def _on_location(self, altitude_m, _speed_mps):
        self._altitude_m = altitude_m
        self._update_altitude_label()

    def _update_altitude_label(self):
        has_altitude = self._altitude_m is not None
        color = GPS_OK_COLOR if has_altitude else GPS_WAITING_COLOR
        text = format_altitude(self._altitude_m, "metric", self._lang)
        self._altitude_label.set_markup(
            f'<span foreground="{color}">{GLib.markup_escape_text(text)}</span>')
        self._altitude_status_label.set_text("" if has_altitude else _("no_gps", self._lang))

    @staticmethod
    def _to_cardinal(deg: float) -> str:
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                      "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        return directions[round(deg / 22.5) % 16]

    def do_close_request(self):
        if self._anim_timer:
            GLib.source_remove(self._anim_timer)
            self._anim_timer = None
        if self._demo_timer:
            GLib.source_remove(self._demo_timer)
            self._demo_timer = None
        if self._sensor:
            self._sensor.release()
        if self._geo:
            self._geo.close()
        return False


class CompassApp(Adw.Application):

    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.connect("activate", self._on_activate)
        self._add_actions()

    def _add_actions(self):
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

    def _on_activate(self, app):
        CompassWindow(application=app).present()

    def _on_about(self, action, param):
        dialog = Adw.AboutDialog()
        dialog.set_application_name("Compass")
        dialog.set_application_icon(APP_ICON)
        dialog.set_developer_name(DEVELOPER)
        dialog.set_version(APP_VERSION)
        dialog.set_comments("Compass app for Phosh / Linux Mobile")
        dialog.set_license(LICENSE)
        dialog.present(self.get_active_window())


def main():
    return CompassApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
