"""Shared Cairo drawing widgets: compass, spirit levels, and G-force."""
import math

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk


class CompassWidget(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self._heading = 0.0
        self._has_sensor = False
        self.set_draw_func(self._draw)
        self.set_hexpand(True)
        self.set_vexpand(True)

    def set_heading(self, degrees, has_sensor=True):
        self._heading = degrees % 360
        self._has_sensor = has_sensor
        self.queue_draw()

    def _draw(self, area, cr, width, height):
        cx, cy = width / 2, height / 2
        radius = min(width, height) / 2 * 0.88
        color  = self.get_color()
        fg_r, fg_g, fg_b = color.red, color.green, color.blue

        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.set_source_rgba(0.12, 0.12, 0.14, 0.95)
        cr.fill_preserve()
        cr.set_source_rgba(fg_r, fg_g, fg_b, 0.15)
        cr.set_line_width(2)
        cr.stroke()

        for deg in range(0, 360, 5):
            angle = math.radians(deg - self._heading - 90)
            is_cardinal = deg % 90 == 0
            is_major    = deg % 10 == 0
            tick_len    = radius * (0.12 if is_cardinal else (0.08 if is_major else 0.04))
            r_outer = radius * 0.95
            r_inner = r_outer - tick_len
            x1 = cx + r_outer * math.cos(angle);  y1 = cy + r_outer * math.sin(angle)
            x2 = cx + r_inner * math.cos(angle);  y2 = cy + r_inner * math.sin(angle)
            if is_cardinal:
                cr.set_source_rgba(0.95, 0.3, 0.25, 1.0);  cr.set_line_width(2.5)
            elif is_major:
                cr.set_source_rgba(fg_r, fg_g, fg_b, 0.7);  cr.set_line_width(1.5)
            else:
                cr.set_source_rgba(fg_r, fg_g, fg_b, 0.35); cr.set_line_width(1.0)
            cr.move_to(x1, y1); cr.line_to(x2, y2); cr.stroke()

        cr.set_font_size(radius * 0.13)
        for label, deg in [("N", 0), ("E", 90), ("S", 180), ("W", 270)]:
            angle = math.radians(deg - self._heading - 90)
            tx = cx + radius * 0.75 * math.cos(angle)
            ty = cy + radius * 0.75 * math.sin(angle)
            ext = cr.text_extents(label)
            cr.move_to(tx - ext.width / 2, ty + ext.height / 2)
            cr.set_source_rgba(0.95, 0.3, 0.25, 1.0) if label == "N" \
                else cr.set_source_rgba(fg_r, fg_g, fg_b, 0.9)
            cr.show_text(label)

        nlen = radius * 0.55
        nw   = radius * 0.045
        for color_rgba, base_angle in [
            ((0.92, 0.25, 0.2, 1.0),      math.radians(-self._heading - 90)),
            ((0.95, 0.95, 0.95, 0.92),    math.radians(-self._heading + 90)),
        ]:
            a = base_angle
            cr.move_to(cx + nlen * math.cos(a),          cy + nlen * math.sin(a))
            cr.line_to(cx + nw   * math.cos(a+math.pi/2), cy + nw   * math.sin(a+math.pi/2))
            cr.line_to(cx + nlen * 0.35 * math.cos(a+math.pi), cy + nlen * 0.35 * math.sin(a+math.pi))
            cr.line_to(cx + nw   * math.cos(a-math.pi/2), cy + nw   * math.sin(a-math.pi/2))
            cr.close_path()
            cr.set_source_rgba(*color_rgba)
            cr.fill()

        cr.arc(cx, cy, radius * 0.055, 0, 2 * math.pi)
        cr.set_source_rgba(0.2, 0.2, 0.22, 1.0); cr.fill()
        cr.arc(cx, cy, radius * 0.04,  0, 2 * math.pi)
        cr.set_source_rgba(0.85, 0.85, 0.85, 1.0); cr.fill()

        if not self._has_sensor:
            cr.set_font_size(radius * 0.07)
            msg = "No sensor"
            ext = cr.text_extents(msg)
            cr.move_to(cx - ext.width / 2, cy + radius * 0.35)
            cr.set_source_rgba(1.0, 0.75, 0.1, 0.85)
            cr.show_text(msg)


def _bubble_color(tilt):
    if tilt < 1.0:  return 0.18, 0.78, 0.32
    if tilt < 3.0:  return 0.95, 0.72, 0.05
    return 0.88, 0.18, 0.12

def _draw_bubble(cr, bx, by, br, r, g, b):
    cr.arc(bx, by, br, 0, 2*math.pi)
    cr.set_source_rgba(r, g, b, 0.28); cr.fill()
    cr.arc(bx, by, br, 0, 2*math.pi)
    cr.set_source_rgba(r, g, b, 0.95); cr.set_line_width(2.5); cr.stroke()
    cr.arc(bx, by, br * 0.30, 0, 2*math.pi)
    cr.set_source_rgba(1, 1, 1, 0.25); cr.fill()

def _rounded_rect(cr, x, y, w, h, rad):
    cr.new_sub_path()
    cr.arc(x+w-rad, y+rad,   rad, -math.pi/2, 0)
    cr.arc(x+w-rad, y+h-rad, rad, 0, math.pi/2)
    cr.arc(x+rad,   y+h-rad, rad, math.pi/2, math.pi)
    cr.arc(x+rad,   y+rad,   rad, math.pi, 3*math.pi/2)
    cr.close_path()


class LevelWidget(Gtk.DrawingArea):
    MAX_ANGLE = 15.0

    def __init__(self):
        super().__init__()
        self._roll = self._pitch = 0.0
        self._cal_roll = self._cal_pitch = 0.0
        self._target_roll = self._target_pitch = 0.0
        self.set_draw_func(self._draw)
        self.set_hexpand(True); self.set_vexpand(True)

    def set_raw_tilt(self, roll, pitch):
        self._target_roll  = roll  - self._cal_roll
        self._target_pitch = pitch - self._cal_pitch

    def smooth_tick(self):
        dr = (self._target_roll  - self._roll)  * 0.20
        dp = (self._target_pitch - self._pitch) * 0.20
        if abs(dr) > 0.01 or abs(dp) > 0.01:
            self._roll += dr; self._pitch += dp; self.queue_draw()

    def calibrate(self):
        self._cal_roll  += self._roll;  self._cal_pitch += self._pitch
        self._roll = self._pitch = self._target_roll = self._target_pitch = 0.0
        self.queue_draw()

    def get_cal(self):       return (self._cal_roll, self._cal_pitch)
    def set_cal(self, r, p): self._cal_roll = r; self._cal_pitch = p

    @property
    def total_tilt(self): return math.sqrt(self._roll**2 + self._pitch**2)

    def _draw(self, area, cr, w, h):
        cx, cy = w/2, h/2
        radius = min(w, h) / 2 * 0.85
        br     = radius * 0.14
        roll   = max(-self.MAX_ANGLE, min(self.MAX_ANGLE, self._roll))
        pitch  = max(-self.MAX_ANGLE, min(self.MAX_ANGLE, self._pitch))
        bx     = cx + (roll  / self.MAX_ANGLE) * (radius - br)
        by     = cy - (pitch / self.MAX_ANGLE) * (radius - br)
        r, g, b = _bubble_color(self.total_tilt)

        cr.arc(cx, cy, radius, 0, 2*math.pi)
        cr.set_source_rgba(0.1, 0.1, 0.12, 0.96); cr.fill_preserve()
        cr.set_source_rgba(r, g, b, 0.35); cr.set_line_width(2.5); cr.stroke()

        cr.arc(cx, cy, radius * 0.13, 0, 2*math.pi)
        cr.set_source_rgba(r, g, b, 0.18); cr.fill_preserve()
        cr.set_source_rgba(r, g, b, 0.55); cr.set_line_width(1.5); cr.stroke()

        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            s, e = radius * 0.17, radius * 0.92
            cr.move_to(cx+dx*s, cy+dy*s); cr.line_to(cx+dx*e, cy+dy*e)
        cr.set_source_rgba(0.45, 0.45, 0.45, 0.4); cr.set_line_width(1.0); cr.stroke()
        _draw_bubble(cr, bx, by, br, r, g, b)


class LinearLevelWidget(Gtk.DrawingArea):
    MAX_ANGLE = 10.0

    def __init__(self):
        super().__init__()
        self._angle = self._target = self._cal_offset = 0.0
        self.set_draw_func(self._draw)
        self.set_hexpand(True); self.set_vexpand(False)
        self.set_size_request(-1, 116)

    def set_raw_angle(self, a): self._target = a - self._cal_offset

    def smooth_tick(self):
        d = (self._target - self._angle) * 0.20
        if abs(d) > 0.01: self._angle += d; self.queue_draw()

    def calibrate(self):
        self._cal_offset += self._angle
        self._angle = self._target = 0.0; self.queue_draw()

    def get_cal(self):    return self._cal_offset
    def set_cal(self, v): self._cal_offset = v

    @property
    def tilt(self): return abs(self._angle)

    def _draw(self, area, cr, w, h):
        cx, cy = w/2, h/2
        tw     = w * 0.86
        th     = min(h * 0.54, 68.0)
        br     = th * 0.42
        tx, ty = cx - tw/2, cy - th/2
        max_tr = tw/2 - br
        r, g, b = _bubble_color(self.tilt)

        _rounded_rect(cr, tx, ty, tw, th, th/2)
        cr.set_source_rgba(0.1, 0.1, 0.12, 0.96); cr.fill_preserve()
        cr.set_source_rgba(r, g, b, 0.35); cr.set_line_width(2.0); cr.stroke()

        cr.move_to(cx, ty+th*0.10); cr.line_to(cx, ty+th*0.90)
        cr.set_source_rgba(r, g, b, 0.70); cr.set_line_width(2.0); cr.stroke()

        for deg in (1.0, 2.0, 3.0):
            off = (deg / self.MAX_ANGLE) * max_tr
            f   = 0.22 if deg != 2.0 else 0.16
            for sign in (-1, 1):
                x = cx + sign * off
                cr.move_to(x, ty+th*f); cr.line_to(x, ty+th*(1-f))
            cr.set_source_rgba(0.45, 0.45, 0.45, 0.35); cr.set_line_width(1.0); cr.stroke()

        a  = max(-self.MAX_ANGLE, min(self.MAX_ANGLE, self._angle))
        bx = cx + (a / self.MAX_ANGLE) * max_tr
        _draw_bubble(cr, bx, cy, br, r, g, b)


class VerticalLevelWidget(Gtk.DrawingArea):
    MAX_ANGLE = 10.0

    def __init__(self):
        super().__init__()
        self._angle = self._target = self._cal_offset = 0.0
        self.set_draw_func(self._draw)
        self.set_hexpand(False); self.set_vexpand(True)
        self.set_size_request(68, -1)

    def set_raw_angle(self, a): self._target = a - self._cal_offset

    def smooth_tick(self):
        d = (self._target - self._angle) * 0.20
        if abs(d) > 0.01: self._angle += d; self.queue_draw()

    def calibrate(self):
        self._cal_offset += self._angle
        self._angle = self._target = 0.0; self.queue_draw()

    def get_cal(self):    return self._cal_offset
    def set_cal(self, v): self._cal_offset = v

    @property
    def tilt(self): return abs(self._angle)

    def _draw(self, area, cr, w, h):
        cx, cy = w/2, h/2
        th     = h * 0.82
        tw     = min(w * 0.68, 48.0)
        br     = tw * 0.42
        tx, ty = cx - tw/2, cy - th/2
        max_tr = th/2 - br
        r, g, b = _bubble_color(self.tilt)

        _rounded_rect(cr, tx, ty, tw, th, tw/2)
        cr.set_source_rgba(0.1, 0.1, 0.12, 0.96); cr.fill_preserve()
        cr.set_source_rgba(r, g, b, 0.35); cr.set_line_width(2.0); cr.stroke()

        cr.move_to(tx+tw*0.10, cy); cr.line_to(tx+tw*0.90, cy)
        cr.set_source_rgba(r, g, b, 0.70); cr.set_line_width(2.0); cr.stroke()

        for deg in (1.0, 2.0, 3.0):
            off = (deg / self.MAX_ANGLE) * max_tr
            f   = 0.22 if deg != 2.0 else 0.16
            for sign in (-1, 1):
                y = cy + sign * off
                cr.move_to(tx+tw*f, y); cr.line_to(tx+tw*(1-f), y)
            cr.set_source_rgba(0.45, 0.45, 0.45, 0.35); cr.set_line_width(1.0); cr.stroke()

        a  = max(-self.MAX_ANGLE, min(self.MAX_ANGLE, self._angle))
        by = cy - (a / self.MAX_ANGLE) * max_tr
        _draw_bubble(cr, cx, by, br, r, g, b)


class GForceWidget(Gtk.DrawingArea):
    MAX_G = 2.0

    def __init__(self):
        super().__init__()
        self._x = self._y = self._z = 0.0
        self.set_draw_func(self._draw)
        self.set_hexpand(True); self.set_vexpand(True)

    def update(self, x, y, z):
        self._x, self._y, self._z = x, y, z
        self.queue_draw()

    @staticmethod
    def _text_center(cr, text, tx, ty):
        ext = cr.text_extents(text)
        cr.move_to(tx - ext[2]/2 - ext[0], ty - ext[3]/2 - ext[1])
        cr.show_text(text)

    def _draw(self, area, cr, w, h):
        mag    = math.sqrt(self._x**2 + self._y**2 + self._z**2)
        dev    = abs(mag - 1.0)
        cx, cy = w / 2, h / 2

        if dev < 0.06:   r, g, b = 0.18, 0.78, 0.32
        elif dev < 0.40: r, g, b = 0.95, 0.72, 0.05
        else:            r, g, b = 0.88, 0.18, 0.12

        margin = min(w, h) * 0.185
        radius = min(w, h) / 2 - margin
        if radius < 20: return

        fs_val  = max(radius * 0.150, 12.0)
        fs_ring = max(radius * 0.090,  8.0)
        lc      = margin * 0.52

        cr.arc(cx, cy, radius, 0, 2*math.pi)
        cr.set_source_rgba(0.1, 0.1, 0.12, 0.96); cr.fill_preserve()
        cr.set_source_rgba(r, g, b, 0.35); cr.set_line_width(2.5); cr.stroke()

        for ring_g, alpha, lw in ((0.5, 0.18, 0.9), (1.0, 0.42, 1.5)):
            r_px = (ring_g / self.MAX_G) * radius
            cr.arc(cx, cy, r_px, 0, 2*math.pi)
            cr.set_source_rgba(r, g, b, alpha); cr.set_line_width(lw); cr.stroke()
            rx = cx + r_px * 0.690;  ry = cy - r_px * 0.690
            cr.select_font_face("Sans", 0, 0); cr.set_font_size(fs_ring)
            cr.set_source_rgba(0.55, 0.55, 0.55, 0.70)
            self._text_center(cr, f"{ring_g:.1f}g", rx, ry)

        for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
            cr.move_to(cx+dx*radius*0.06, cy+dy*radius*0.06)
            cr.line_to(cx+dx*radius*0.94, cy+dy*radius*0.94)
        cr.set_source_rgba(0.40, 0.40, 0.40, 0.35); cr.set_line_width(1.0); cr.stroke()

        dot_r  = radius * 0.115
        nx     = self._x / self.MAX_G
        ny     = self._y / self.MAX_G
        dist_n = math.sqrt(nx**2 + ny**2)
        limit  = 1.0 - dot_r / radius
        if dist_n > limit:
            nx *= limit / dist_n; ny *= limit / dist_n
        dot_sx = cx + nx * radius
        dot_sy = cy - ny * radius

        cr.arc(dot_sx, dot_sy, dot_r, 0, 2*math.pi)
        cr.set_source_rgba(r, g, b, 0.22); cr.fill()
        cr.arc(dot_sx, dot_sy, dot_r, 0, 2*math.pi)
        cr.set_source_rgba(r, g, b, 0.95); cr.set_line_width(2.5); cr.stroke()
        cr.arc(dot_sx, dot_sy, dot_r*0.35, 0, 2*math.pi)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.25); cr.fill()

        def value_label(value_str, tx, ty):
            cr.select_font_face("Sans", 0, 0); cr.set_font_size(fs_val)
            cr.set_source_rgba(0.92, 0.92, 0.92, 1.0)
            self._text_center(cr, value_str, tx, ty)

        value_label(f"{self._x:+.2f}g", cx + radius + lc, cy)
        value_label(f"{self._y:+.2f}g", cx, cy - radius - lc)
        value_label(f"{self._z:+.2f}g", cx - radius - lc, cy)
        value_label(f"{mag:.2f}g",      cx, cy + radius + lc)
