#!/usr/bin/env python3
import sys
import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib, Gio

from gps import (GeoLocationBackend, GPS_OK_COLOR, GPS_WAITING_COLOR,
                 format_altitude, format_speed)
from i18n import _
from app_config import (APP_ID, APP_NAME, APP_VERSION, APP_ICON, DEVELOPER,
                        LICENSE, load_settings, save_settings, apply_theme)
from sensors import SensorPoller, AccelBackend
from widgets import (CompassWidget, LevelWidget, LinearLevelWidget,
                     VerticalLevelWidget, GForceWidget)


# ── Settings window ────────────────────────────────────────────────────────────

class SettingsWindow(Adw.PreferencesWindow):

    def __init__(self, parent, settings, lang, on_change):
        super().__init__(transient_for=parent, modal=True)
        self.set_title(_("s_ttl", lang))
        self._settings = settings
        self._on_change = on_change

        page = Adw.PreferencesPage()
        self.add(page)

        grp = Adw.PreferencesGroup(title=_("s_appear", lang))
        page.add(grp)

        theme_row = Adw.ComboRow(title=_("s_theme", lang))
        theme_row.set_model(Gtk.StringList.new([
            _("s_t_auto", lang), _("s_t_lt", lang), _("s_t_dk", lang)]))
        theme_row.set_selected({"auto": 0, "light": 1, "dark": 2}.get(
            settings.get("theme", "auto"), 0))
        theme_row.connect("notify::selected", self._on_theme)
        grp.add(theme_row)

        lang_row = Adw.ComboRow(title=_("s_lang", lang))
        lang_row.set_model(Gtk.StringList.new(["Deutsch", "English"]))
        lang_row.set_selected(0 if lang == "de" else 1)
        lang_row.connect("notify::selected",
                         lambda row, _: [self._set_lang(["de","en"][row.get_selected()]),
                                         on_change()])
        grp.add(lang_row)

        units_row = Adw.ComboRow(title=_("s_units", lang))
        units_row.set_model(Gtk.StringList.new([
            _("s_unit_metric", lang), _("s_unit_imperial", lang)]))
        units_row.set_selected(0 if settings.get("unit_system", "metric") == "metric" else 1)
        units_row.connect("notify::selected", self._on_units)
        grp.add(units_row)

    def _on_theme(self, row, _):
        theme = ["auto", "light", "dark"][row.get_selected()]
        self._settings["theme"] = theme
        save_settings(self._settings)
        apply_theme(theme)

    def _set_lang(self, lang):
        self._settings["lang"] = lang
        save_settings(self._settings)

    def _on_units(self, row, _):
        self._settings["unit_system"] = ["metric", "imperial"][row.get_selected()]
        save_settings(self._settings)
        self._on_change()


# ── Combined window ────────────────────────────────────────────────────────────

class SensorSuiteWindow(Adw.ApplicationWindow):

    _CALIB_STARS = ["○○○", "●○○", "●●○", "●●●"]
    _CALIB_HINT  = ["cal_fig8_0", "cal_fig8_1", "cal_fig8_2", None]

    def __init__(self, settings, **kwargs):
        super().__init__(**kwargs)
        self._settings      = settings
        self._lang          = settings.get("lang", "de")
        self._page_order    = ["compass", "spirit_level", "gforce"]
        self._accel         = None
        self._compass       = None
        self._geo           = None
        self._anim_timer    = None
        self._demo_timers   = []

        # compass state
        self._cmp_target        = 0.0
        self._cmp_display       = 0.0
        self._calibrating       = False
        self._cal_seen_incomplete = False

        # level state
        self._waiting_cal   = False
        self._status_msg    = ""
        self._status_until  = None

        # gforce smooth values
        self._gx = self._gy = self._gz = 0.0
        self._gtx = self._gty = self._gtz = 0.0
        self._altitude_m = None
        self._speed_mps = None

        apply_theme(settings.get("theme", "auto"))
        self.set_title("Sensor Suite")
        self.set_default_size(360, 640)

        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        # ── Header ──────────────────────────────────────────────────────────
        header = Adw.HeaderBar()
        header.set_centering_policy(Adw.CenteringPolicy.STRICT)
        toolbar_view.add_top_bar(header)

        self._cal_btn = Gtk.Button(label=_("s_c_btn", self._lang))
        self._cal_btn.connect("clicked", self._on_cal_btn_clicked)
        header.pack_start(self._cal_btn)

        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_menu_model(self._build_menu())
        header.pack_end(menu_btn)

        # ── View stack ───────────────────────────────────────────────────────
        self._stack = Adw.ViewStack()
        toolbar_view.set_content(self._stack)

        self._build_compass_page()
        self._build_level_page()
        self._build_gforce_page()

        swipe = Gtk.GestureSwipe()
        swipe.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        swipe.connect("swipe", self._on_stack_swipe)
        self._stack.add_controller(swipe)

        # ── Bottom switcher bar ──────────────────────────────────────────────
        bar = Adw.ViewSwitcherBar()
        bar.set_stack(self._stack)
        bar.set_reveal(True)
        toolbar_view.add_bottom_bar(bar)

        self._stack.connect("notify::visible-child", lambda *_: self._update_cal_btn())
        self._update_cal_btn()

        # ── Load calibration ─────────────────────────────────────────────────
        cal_roll  = settings.get("cal_roll",  0.0)
        cal_pitch = settings.get("cal_pitch", 0.0)
        if cal_roll or cal_pitch:
            self._level_2d.set_cal(cal_roll, cal_pitch)
            self._level_hk.set_cal(cal_roll)
            self._level_quer.set_cal(cal_pitch)

        # ── Tap gesture for level calibration ────────────────────────────────
        tap = Gtk.GestureClick()
        tap.connect("released", self._on_level_tap)
        self._level_box.add_controller(tap)

        # ── Start ────────────────────────────────────────────────────────────
        self._anim_timer = GLib.timeout_add(16, self._anim_tick)
        GLib.idle_add(self._init_sensors)

    # ── Page builders ──────────────────────────────────────────────────────────

    def _build_compass_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_margin_top(12)
        box.set_margin_bottom(8)
        box.set_margin_start(16)
        box.set_margin_end(16)

        self._calib_bar = Adw.Banner()
        self._calib_bar.connect("button-clicked", self._on_calib_bar_button)
        self._calib_bar.set_revealed(False)
        box.append(self._calib_bar)

        self._altitude_label = Gtk.Label()
        self._altitude_label.add_css_class("title-4")
        self._altitude_label.set_margin_top(4)
        box.append(self._altitude_label)

        self._altitude_status_label = Gtk.Label()
        self._altitude_status_label.add_css_class("caption")
        self._altitude_status_label.add_css_class("dim-label")
        self._altitude_status_label.set_margin_top(2)
        box.append(self._altitude_status_label)

        self._compass_widget = CompassWidget()
        self._compass_widget.set_size_request(260, 260)
        box.append(self._compass_widget)

        self._heading_label = Gtk.Label(label="0°")
        self._heading_label.add_css_class("title-1")
        self._heading_label.set_margin_top(12)
        box.append(self._heading_label)

        self._cardinal_label = Gtk.Label(label="N")
        self._cardinal_label.add_css_class("title-3")
        self._cardinal_label.add_css_class("dim-label")
        self._cardinal_label.set_margin_top(4)
        box.append(self._cardinal_label)

        self._calib_level_label = Gtk.Label()
        self._calib_level_label.add_css_class("caption")
        self._calib_level_label.add_css_class("dim-label")
        self._calib_level_label.set_margin_top(4)
        box.append(self._calib_level_label)

        page = self._stack.add_titled(box, "compass", _("p_compass", self._lang))
        page.set_icon_name("find-location-symbolic")

    def _build_level_page(self):
        self._level_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._level_box.set_margin_top(8)
        self._level_box.set_margin_bottom(8)
        self._level_box.set_margin_start(10)
        self._level_box.set_margin_end(10)

        self._cal_hint = Gtk.Label()
        self._cal_hint.add_css_class("heading")
        self._cal_hint.set_justify(Gtk.Justification.CENTER)
        self._cal_hint.set_wrap(True)
        self._cal_revealer = Gtk.Revealer()
        self._cal_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._cal_revealer.set_transition_duration(180)
        self._cal_revealer.set_child(self._cal_hint)
        self._level_box.append(self._cal_revealer)

        self._level_hk = LinearLevelWidget()
        self._level_box.append(self._level_hk)

        mid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        mid.set_vexpand(True)
        self._level_box.append(mid)

        self._level_2d = LevelWidget()
        mid.append(self._level_2d)

        self._level_quer = VerticalLevelWidget()
        mid.append(self._level_quer)

        self._angle_label = Gtk.Label(label="0.0°")
        self._angle_label.add_css_class("title-1")
        self._angle_label.set_margin_top(4)
        self._level_box.append(self._angle_label)

        self._detail_label = Gtk.Label(label=_("level", self._lang))
        self._detail_label.add_css_class("title-3")
        self._detail_label.add_css_class("dim-label")
        self._level_box.append(self._detail_label)

        axis_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        axis_box.set_halign(Gtk.Align.CENTER)
        self._level_box.append(axis_box)

        self._hk_label = Gtk.Label(label="↔ 0.0°")
        self._hk_label.add_css_class("caption")
        self._hk_label.add_css_class("dim-label")
        axis_box.append(self._hk_label)

        self._quer_label = Gtk.Label(label="↕ 0.0°")
        self._quer_label.add_css_class("caption")
        self._quer_label.add_css_class("dim-label")
        axis_box.append(self._quer_label)

        page = self._stack.add_titled(self._level_box, "spirit_level", _("p_level", self._lang))
        page.set_icon_name("view-grid-symbolic")

    def _build_gforce_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12)
        box.set_margin_bottom(8)
        box.set_margin_start(16)
        box.set_margin_end(16)

        self._speed_value_label = Gtk.Label(label="--")
        self._speed_value_label.add_css_class("title-1")
        self._speed_value_label.set_margin_top(4)
        box.append(self._speed_value_label)

        self._speed_unit_label = Gtk.Label(label="km/h")
        self._speed_unit_label.add_css_class("title-4")
        self._speed_unit_label.add_css_class("dim-label")
        box.append(self._speed_unit_label)

        self._speed_status_label = Gtk.Label()
        self._speed_status_label.add_css_class("caption")
        self._speed_status_label.add_css_class("dim-label")
        box.append(self._speed_status_label)

        self._gforce_widget = GForceWidget()
        box.append(self._gforce_widget)

        page = self._stack.add_titled(box, "gforce", _("p_gforce", self._lang))
        page.set_icon_name("system-run-symbolic")

    # ── Menu ───────────────────────────────────────────────────────────────────

    def _build_menu(self):
        menu = Gio.Menu()
        menu.append(_("s_ttl", self._lang),   "app.settings")
        menu.append(_("m_about", self._lang), "app.about")
        return menu

    def _update_cal_btn(self):
        page = self._stack.get_visible_child_name()
        self._cal_btn.set_visible(page in ("compass", "spirit_level"))

    def _on_cal_btn_clicked(self, _btn):
        page = self._stack.get_visible_child_name()
        lang = self._lang
        if page == "compass":
            dialog = Adw.AlertDialog(
                heading=_("dlg_cmp_ttl", lang),
                body=_("dlg_cmp_body", lang),
            )
            dialog.add_response("cancel", _("btn_cancel", lang))
            dialog.add_response("start", _("btn_start", lang))
            dialog.set_response_appearance("start", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("start")
            dialog.set_close_response("cancel")
            dialog.connect("response", lambda d, r: self.start_compass_calibration() if r == "start" else None)
            dialog.present(self)
        elif page == "spirit_level":
            dialog = Adw.AlertDialog(
                heading=_("dlg_lvl_ttl", lang),
                body=_("dlg_lvl_body", lang),
            )
            dialog.add_response("cancel", _("btn_cancel", lang))
            dialog.add_response("start", _("btn_start", lang))
            dialog.set_response_appearance("start", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("start")
            dialog.set_close_response("cancel")
            dialog.connect("response", lambda d, r: self._enter_level_cal_mode() if r == "start" else None)
            dialog.present(self)

    def _on_stack_swipe(self, _gesture, velocity_x, velocity_y):
        if abs(velocity_x) < 250 or abs(velocity_x) < abs(velocity_y):
            return
        current = self._stack.get_visible_child_name()
        if current not in self._page_order:
            return
        direction = 1 if velocity_x < 0 else -1
        idx = self._page_order.index(current) + direction
        if 0 <= idx < len(self._page_order):
            self._stack.set_visible_child_name(self._page_order[idx])

    def _on_calib_bar_button(self, banner):
        banner.set_revealed(False)
        self._calibrating = False

    # ── Sensor init ────────────────────────────────────────────────────────────

    def _init_sensors(self):
        self._accel = AccelBackend()
        if self._accel.available:
            self._accel.add_callback(self._on_accel)
        else:
            tid = GLib.timeout_add(50, self._demo_accel_tick)
            self._demo_timers.append(tid)

        self._compass = SensorPoller(self._on_compass)
        if not self._compass.available:
            tid = GLib.timeout_add(50, self._demo_compass_tick)
            self._demo_timers.append(tid)
            self._compass_widget.set_heading(0.0, has_sensor=False)

        self._geo = GeoLocationBackend(APP_ID)
        if self._geo.available:
            self._geo.add_callback(self._on_location)

        return False

    # ── Compass callbacks ──────────────────────────────────────────────────────

    def _on_compass(self, degrees, level, has_sensor):
        self._cmp_target = degrees
        if level < 0:
            return
        lvl = min(level, 3)
        lang = self._lang
        self._calib_level_label.set_text(f"{_('cal_status', lang)} {self._CALIB_STARS[lvl]}")
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
                GLib.timeout_add(2500,
                    lambda: self._calib_bar.set_revealed(False) or False)

    def _demo_compass_tick(self):
        self._cmp_target = (self._cmp_target + 1.5) % 360
        return True

    def start_compass_calibration(self):
        if self._compass:
            self._compass.release()
            self._compass = None
        lang = self._lang
        self._calib_level_label.set_text(f"{_('cal_status', lang)} {self._CALIB_STARS[0]}")
        self._calib_bar.set_title(_("cal_hold", lang))
        self._calib_bar.set_button_label(_("btn_skip", lang))
        self._calib_bar.set_revealed(True)
        self._calibrating = True
        self._cal_seen_incomplete = False
        GLib.timeout_add(300, lambda: self._restart_compass() or False)

    def _restart_compass(self):
        self._compass = SensorPoller(self._on_compass)
        if not self._compass.available:
            tid = GLib.timeout_add(50, self._demo_compass_tick)
            self._demo_timers.append(tid)

    # ── Accel / level callbacks ────────────────────────────────────────────────

    def _on_accel(self, x, y, z):
        if z == 0:
            return
        roll  = math.degrees(math.atan2(x, math.sqrt(y*y + z*z)))
        pitch = math.degrees(math.atan2(y, math.sqrt(x*x + z*z)))
        self._level_2d.set_raw_tilt(roll, pitch)
        self._level_hk.set_raw_angle(roll)
        self._level_quer.set_raw_angle(pitch)
        self._gtx = x / 1000.0
        self._gty = y / 1000.0
        self._gtz = z / 1000.0

    def _demo_accel_tick(self):
        t = GLib.get_monotonic_time() / 1_000_000
        roll  = math.sin(t * 0.5) * 8
        pitch = math.cos(t * 0.7) * 5
        self._level_2d.set_raw_tilt(roll, pitch)
        self._level_hk.set_raw_angle(roll)
        self._level_quer.set_raw_angle(pitch)
        self._gtx = math.sin(t * 1.7) * 0.6
        self._gty = math.cos(t * 1.3) * 0.4
        self._gtz = 1.0 + math.sin(t * 2.9) * 0.15
        return True

    def _on_location(self, altitude_m, speed_mps):
        self._altitude_m = altitude_m
        self._speed_mps = speed_mps
        self._update_location_labels()

    def _do_calibrate_level(self, show_dialog=True):
        self._level_2d.calibrate()
        self._level_hk.calibrate()
        self._level_quer.calibrate()
        cal_roll, cal_pitch = self._level_2d.get_cal()
        self._settings["cal_roll"]  = cal_roll
        self._settings["cal_pitch"] = cal_pitch
        save_settings(self._settings)
        if show_dialog:
            dialog = Adw.AlertDialog(
                heading=_("dlg_done_ttl", self._lang),
                body=_("dlg_done_body", self._lang),
            )
            dialog.add_response("ok", "OK")
            dialog.set_default_response("ok")
            dialog.present(self)
        else:
            self._status_msg   = _("cal_done", self._lang)
            self._status_until = GLib.get_monotonic_time() + 2_000_000

    def _enter_level_cal_mode(self):
        self._waiting_cal = True
        self._cal_hint.set_text(_("cal_tap", self._lang))
        self._cal_revealer.set_reveal_child(True)
        self._stack.set_visible_child_name("spirit_level")

    def _on_level_tap(self, gesture, n_press, x, y):
        if not self._waiting_cal:
            return
        self._waiting_cal = False
        self._cal_revealer.set_reveal_child(False)
        self._do_calibrate_level()

    # ── Animation tick ─────────────────────────────────────────────────────────

    def _anim_tick(self) -> bool:
        # compass
        diff = (self._cmp_target - self._cmp_display + 180) % 360 - 180
        self._cmp_display = (self._cmp_display + diff * 0.18) % 360
        has = self._compass is not None and self._compass.available
        self._compass_widget.set_heading(self._cmp_display, has)
        self._heading_label.set_text(f"{self._cmp_display:.0f}°")
        self._cardinal_label.set_text(self._to_cardinal(self._cmp_display))

        # level widgets
        self._level_2d.smooth_tick()
        self._level_hk.smooth_tick()
        self._level_quer.smooth_tick()

        tilt = self._level_2d.total_tilt
        self._angle_label.set_text(f"{tilt:.1f}°")
        self._hk_label.set_text(f"↔ {self._level_hk.tilt:.1f}°")
        self._quer_label.set_text(f"↕ {self._level_quer.tilt:.1f}°")

        now = GLib.get_monotonic_time()
        if self._status_until and now < self._status_until:
            self._detail_label.set_text(self._status_msg)
        else:
            self._status_until = None
            lang = self._lang
            if tilt < 1.0:   self._detail_label.set_text(_("level",  lang))
            elif tilt < 3.0: self._detail_label.set_text(_("slight", lang))
            else:            self._detail_label.set_text(_("tilted", lang))

        # gforce smooth
        SMOOTH = 0.28
        self._gx += (self._gtx - self._gx) * SMOOTH
        self._gy += (self._gty - self._gy) * SMOOTH
        self._gz += (self._gtz - self._gz) * SMOOTH
        self._gforce_widget.update(self._gx, self._gy, self._gz)
        self._update_location_labels()

        return True

    # ── Settings ───────────────────────────────────────────────────────────────

    def open_settings(self):
        SettingsWindow(
            parent=self,
            settings=self._settings,
            lang=self._lang,
            on_change=self._on_settings_change,
        ).present()

    def _on_settings_change(self):
        new_lang = self._settings.get("lang", "de")
        if new_lang != self._lang:
            self._lang = new_lang
        self._update_location_labels()

    def _unit_system(self):
        return self._settings.get("unit_system", "metric")

    def _update_location_labels(self):
        if hasattr(self, "_altitude_label"):
            has_altitude = self._altitude_m is not None
            text = format_altitude(self._altitude_m, self._unit_system(), self._lang)
            self._set_colored_label(self._altitude_label, text, has_altitude)
            self._altitude_status_label.set_text("" if has_altitude else _("no_gps", self._lang))
        if hasattr(self, "_speed_value_label"):
            has_speed = self._speed_mps is not None
            value, unit = format_speed(self._speed_mps, self._unit_system())
            self._set_colored_label(self._speed_value_label, value, has_speed)
            self._speed_unit_label.set_text(unit)
            self._speed_status_label.set_text("" if has_speed else _("no_gps", self._lang))

    @staticmethod
    def _set_colored_label(label, text, has_signal):
        color = GPS_OK_COLOR if has_signal else GPS_WAITING_COLOR
        label.set_markup(
            f'<span foreground="{color}">{GLib.markup_escape_text(text)}</span>')

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_cardinal(deg):
        directions = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
                      "S","SSW","SW","WSW","W","WNW","NW","NNW"]
        return directions[round(deg / 22.5) % 16]

    def do_close_request(self):
        if self._anim_timer:
            GLib.source_remove(self._anim_timer)
        for tid in self._demo_timers:
            GLib.source_remove(tid)
        if self._accel:
            self._accel.close()
        if self._compass:
            self._compass.release()
        if self._geo:
            self._geo.close()
        return False


# ── Application ────────────────────────────────────────────────────────────────

class SensorSuiteApp(Adw.Application):

    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.connect("activate", self._on_activate)
        self._add_actions()

    def _add_actions(self):
        for name, handler in [
            ("settings", self._on_settings),
            ("about",    self._on_about),
        ]:
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", handler)
            self.add_action(a)

    def _on_activate(self, app):
        SensorSuiteWindow(settings=load_settings(), application=app).present()

    def _on_settings(self, action, param):
        win = self.get_active_window()
        if win: win.open_settings()

    def _on_about(self, action, param):
        win = self.get_active_window()
        lang = getattr(win, "_lang", "en")
        dialog = Adw.AboutDialog()
        dialog.set_application_name(APP_NAME)
        dialog.set_application_icon(APP_ICON)
        dialog.set_developer_name(DEVELOPER)
        dialog.set_version(APP_VERSION)
        dialog.set_comments(_("about_comments", lang))
        dialog.set_license(LICENSE)
        dialog.present(win)


if __name__ == "__main__":
    sys.exit(SensorSuiteApp().run(sys.argv))
