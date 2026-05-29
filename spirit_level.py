#!/usr/bin/env python3
import sys
import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib, Gio

from i18n import _
from app_config import APP_ID, load_settings, save_settings, apply_theme
from sensors import AccelBackend
from widgets import LevelWidget, LinearLevelWidget, VerticalLevelWidget


class SettingsWindow(Adw.PreferencesWindow):

    def __init__(self, parent, settings, lang, on_change):
        super().__init__(transient_for=parent, modal=True)
        self.set_title(_("s_ttl", lang))
        self._settings  = settings
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
        lang_row.connect("notify::selected", self._on_lang)
        grp.add(lang_row)

    def _on_theme(self, row, _):
        theme = ["auto", "light", "dark"][row.get_selected()]
        self._settings["theme"] = theme
        save_settings(self._settings)
        apply_theme(theme)

    def _on_lang(self, row, _):
        self._settings["lang"] = ["de", "en"][row.get_selected()]
        save_settings(self._settings)
        self._on_change()


class SpiritLevelWindow(Adw.ApplicationWindow):

    def __init__(self, settings, **kwargs):
        super().__init__(**kwargs)
        self._settings     = settings
        self._lang         = settings.get("lang", "en")
        self._backend      = None
        self._anim_timer   = None
        self._status_msg   = ""
        self._status_until = None
        self._waiting_cal  = False

        apply_theme(settings.get("theme", "auto"))
        self.set_title(_("title", self._lang))
        self.set_default_size(360, 640)

        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        header = Adw.HeaderBar()
        header.set_centering_policy(Adw.CenteringPolicy.STRICT)
        toolbar_view.add_top_bar(header)

        cal_btn = Gtk.Button(label="Calibrate")
        cal_btn.connect("clicked", self._on_calibrate_clicked)
        header.pack_start(cal_btn)

        settings_btn = Gtk.Button(icon_name="preferences-system-symbolic",
                                  tooltip_text="Settings")
        settings_btn.connect("clicked", self._open_settings)
        header.pack_end(settings_btn)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.set_margin_top(8)
        outer.set_margin_bottom(14)
        outer.set_margin_start(10)
        outer.set_margin_end(10)
        toolbar_view.set_content(outer)

        self._cal_hint = Gtk.Label()
        self._cal_hint.add_css_class("heading")
        self._cal_hint.set_justify(Gtk.Justification.CENTER)
        self._cal_hint.set_wrap(True)
        self._cal_revealer = Gtk.Revealer()
        self._cal_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._cal_revealer.set_transition_duration(180)
        self._cal_revealer.set_child(self._cal_hint)
        outer.append(self._cal_revealer)

        self._level_hk = LinearLevelWidget()
        outer.append(self._level_hk)

        mid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        mid.set_vexpand(True)
        outer.append(mid)

        self._level = LevelWidget()
        mid.append(self._level)

        self._level_quer = VerticalLevelWidget()
        mid.append(self._level_quer)

        self._angle_label = Gtk.Label(label="0.0°")
        self._angle_label.add_css_class("title-1")
        self._angle_label.set_margin_top(4)
        outer.append(self._angle_label)

        self._detail_label = Gtk.Label(label=_("level", self._lang))
        self._detail_label.add_css_class("title-3")
        self._detail_label.add_css_class("dim-label")
        outer.append(self._detail_label)

        axis_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        axis_box.set_halign(Gtk.Align.CENTER)
        outer.append(axis_box)

        self._hk_label = Gtk.Label(label="↔ 0.0°")
        self._hk_label.add_css_class("caption")
        self._hk_label.add_css_class("dim-label")
        axis_box.append(self._hk_label)

        self._quer_label = Gtk.Label(label="↕ 0.0°")
        self._quer_label.add_css_class("caption")
        self._quer_label.add_css_class("dim-label")
        axis_box.append(self._quer_label)

        cal_roll  = settings.get("cal_roll",  0.0)
        cal_pitch = settings.get("cal_pitch", 0.0)
        if cal_roll or cal_pitch:
            self._level.set_cal(cal_roll, cal_pitch)
            self._level_hk.set_cal(cal_roll)
            self._level_quer.set_cal(cal_pitch)

        tap = Gtk.GestureClick()
        tap.connect("released", self._on_tap)
        outer.add_controller(tap)

        self._anim_timer = GLib.timeout_add(16, self._anim_tick)
        GLib.idle_add(self._init_sensor)

    def _init_sensor(self):
        self._backend = AccelBackend()
        if self._backend.available:
            self._backend.add_callback(self._on_accel)
        else:
            GLib.timeout_add(50, self._demo_tick)
        return False

    def _demo_tick(self):
        t = GLib.get_monotonic_time() / 1_000_000
        roll  = math.sin(t * 0.5) * 8
        pitch = math.cos(t * 0.7) * 5
        self._level.set_raw_tilt(roll, pitch)
        self._level_hk.set_raw_angle(roll)
        self._level_quer.set_raw_angle(pitch)
        return True

    def _on_accel(self, x, y, z):
        if z == 0:
            return
        roll  = math.degrees(math.atan2(x, math.sqrt(y*y + z*z)))
        pitch = math.degrees(math.atan2(y, math.sqrt(x*x + z*z)))
        self._level.set_raw_tilt(roll, pitch)
        self._level_hk.set_raw_angle(roll)
        self._level_quer.set_raw_angle(pitch)

    def _anim_tick(self) -> bool:
        self._level.smooth_tick()
        self._level_hk.smooth_tick()
        self._level_quer.smooth_tick()

        tilt = self._level.total_tilt
        lang = self._lang
        self._angle_label.set_text(f"{tilt:.1f}°")
        self._hk_label.set_text(f"↔ {self._level_hk.tilt:.1f}°")
        self._quer_label.set_text(f"↕ {self._level_quer.tilt:.1f}°")

        now = GLib.get_monotonic_time()
        if self._status_until and now < self._status_until:
            self._detail_label.set_text(self._status_msg)
        else:
            self._status_until = None
            if tilt < 1.0:   self._detail_label.set_text(_("level",  lang))
            elif tilt < 3.0: self._detail_label.set_text(_("slight", lang))
            else:            self._detail_label.set_text(_("tilted", lang))
        return True

    def _on_calibrate_clicked(self, _btn):
        dialog = Adw.AlertDialog(
            heading="Calibrate Spirit Level",
            body="Place the device in the reference position, then tap the screen to set the zero point.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("start", "Start")
        dialog.set_response_appearance("start", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("start")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda d, r: self._enter_cal_mode() if r == "start" else None)
        dialog.present(self)

    def _enter_cal_mode(self):
        self._waiting_cal = True
        self._cal_hint.set_text(_("cal_tap", self._lang))
        self._cal_revealer.set_reveal_child(True)

    def _on_tap(self, gesture, n_press, x, y):
        if not self._waiting_cal:
            return
        self._waiting_cal = False
        self._cal_revealer.set_reveal_child(False)
        self._do_calibrate()

    def _do_calibrate(self):
        self._level.calibrate()
        self._level_hk.calibrate()
        self._level_quer.calibrate()
        cal_roll, cal_pitch = self._level.get_cal()
        self._settings["cal_roll"]  = cal_roll
        self._settings["cal_pitch"] = cal_pitch
        save_settings(self._settings)
        dialog = Adw.AlertDialog(
            heading="Calibration Complete",
            body="The zero point has been set successfully.",
        )
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.present(self)

    def _open_settings(self, _btn):
        SettingsWindow(
            parent=self,
            settings=self._settings,
            lang=self._lang,
            on_change=self._on_settings_change,
        ).present()

    def _on_settings_change(self):
        new_lang = self._settings.get("lang", "en")
        if new_lang != self._lang:
            self._lang = new_lang
            self.set_title(_("title", new_lang))

    def do_close_request(self):
        if self._anim_timer:
            GLib.source_remove(self._anim_timer)
        if self._backend:
            self._backend.close()
        return False


class SpiritLevelApp(Adw.Application):

    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.connect("activate", self._on_activate)

    def _on_activate(self, app):
        SpiritLevelWindow(settings=load_settings(), application=app).present()


if __name__ == "__main__":
    sys.exit(SpiritLevelApp().run(sys.argv))
