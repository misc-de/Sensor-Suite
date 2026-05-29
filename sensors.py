"""Shared sensor backends: compass (IIO / hadess / sensorfwd) and accelerometer."""
import os
import math
import struct
import socket as _socket

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gio

# ── Constants ──────────────────────────────────────────────────────────────────
IIO_BASE       = "/sys/bus/iio/devices"
MAGN_KEYWORDS  = ("magn", "compass", "ak09", "ak8", "mmc56", "mmc34",
                  "lis3mdl", "lsm303", "bmm", "qmc", "icp", "hmc")
HADESS_BUS     = "net.hadess.SensorProxy"
HADESS_PATH    = "/net/hadess/SensorProxy"
HADESS_IFACE   = "net.hadess.SensorProxy"
HADESS_COMPASS = "net.hadess.SensorProxy.Compass"
SENSOR_SVC     = "com.nokia.SensorService"
SOCKET_PATH    = "/run/sensord.sock"
_HDR           = struct.Struct('<I')
_CMP           = struct.Struct('<Qiiii')
_ACCEL         = struct.Struct('<Qfffi')


def _read_sysfs(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


# ── Compass backends ───────────────────────────────────────────────────────────

def find_iio_magnetometer():
    if not os.path.isdir(IIO_BASE):
        return None
    for entry in sorted(os.listdir(IIO_BASE)):
        dev_path = os.path.join(IIO_BASE, entry)
        name = _read_sysfs(os.path.join(dev_path, "name")) or ""
        if any(k in name.lower() for k in MAGN_KEYWORDS):
            if os.path.exists(os.path.join(dev_path, "in_magn_x_raw")):
                return dev_path
    return None


class IIOBackend:
    name = "IIO-Sysfs"

    def __init__(self, device_path):
        self._path = device_path
        s = _read_sysfs(os.path.join(device_path, "in_magn_x_scale"))
        self._scale = float(s) if s else 1.0
        self.label = _read_sysfs(os.path.join(device_path, "name")) or device_path

    def read_heading(self):
        rx = _read_sysfs(os.path.join(self._path, "in_magn_x_raw"))
        ry = _read_sysfs(os.path.join(self._path, "in_magn_y_raw"))
        if rx is None or ry is None:
            return None
        x = int(rx) * self._scale
        y = int(ry) * self._scale
        return (math.degrees(math.atan2(-y, x)) % 360, -1)

    def close(self): pass


class HadessBackend:
    name = "hadess D-Bus"

    def __init__(self):
        self._proxy = self._compass_proxy = None
        self.label  = "net.hadess.SensorProxy"
        self._heading = 0.0
        try:
            self._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
                HADESS_BUS, HADESS_PATH, HADESS_IFACE, None)
            self._proxy.call_sync("ClaimCompass", None, Gio.DBusCallFlags.NONE, 2000, None)
            self._compass_proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
                HADESS_BUS, HADESS_PATH, HADESS_COMPASS, None)
            has = self._compass_proxy.get_cached_property("HasCompass")
            if not has or not has.get_boolean():
                raise RuntimeError("No compass")
            self._compass_proxy.connect("g-properties-changed", self._on_props_changed)
        except Exception as e:
            print(f"hadess D-Bus not available: {e}")
            self._proxy = self._compass_proxy = None

    @property
    def available(self): return self._compass_proxy is not None

    def _on_props_changed(self, proxy, changed, invalidated):
        v = changed.lookup_value("CompassHeading", None)
        if v is not None:
            self._heading = v.get_double()

    def read_heading(self):
        if self._compass_proxy is None:
            return None
        v = self._compass_proxy.get_cached_property("CompassHeading")
        if v is not None:
            self._heading = v.get_double()
        return (self._heading % 360, -1)

    def close(self):
        if self._proxy:
            try:
                self._proxy.call_sync("ReleaseCompass", None,
                                      Gio.DBusCallFlags.NONE, 1000, None)
            except Exception: pass


class SensorfwBackend:
    _SERVICE  = SENSOR_SVC
    _MGR_PATH = "/SensorManager"
    _MGR_IF   = "local.SensorManager"
    _CMP_PATH = "/SensorManager/compasssensor"
    _CMP_IF   = "local.CompassSensor"

    def __init__(self):
        self._bus = self._sock = self._watch_id = self._session_id = None
        self._buf = b""
        self._heading = 0.0
        self._level   = 0
        self._available = False
        self.label = "sensorfwd"
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            pid = os.getpid()
            self._dbus(self._MGR_PATH, self._MGR_IF, "loadPlugin",
                       GLib.Variant("(s)", ("compasssensor",)))
            res = self._dbus(self._MGR_PATH, self._MGR_IF, "requestSensor",
                             GLib.Variant("(sx)", ("compasssensor", pid)),
                             reply_type=GLib.VariantType.new("(i)"))
            self._session_id = res.get_child_value(0).get_int32()
            self._sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            self._sock.connect(SOCKET_PATH)
            self._sock.send(struct.pack('<i', self._session_id))
            self._sock.recv(1)
            self._sock.setblocking(False)
            self._watch_id = GLib.io_add_watch(
                self._sock.fileno(), GLib.IO_IN | GLib.IO_ERR | GLib.IO_HUP,
                self._on_socket)
            self._dbus(self._CMP_PATH, self._CMP_IF, "setInterval",
                       GLib.Variant("(ii)", (self._session_id, 100)))
            self._dbus(self._CMP_PATH, self._CMP_IF, "start",
                       GLib.Variant("(i)", (self._session_id,)))
            self._available = True
            print(f"Compass: sensorfwd (session {self._session_id})")
        except Exception as e:
            print(f"sensorfwd compass not available: {e}")
            if self._sock:
                self._sock.close()
                self._sock = None

    def _dbus(self, path, iface, method, args=None, reply_type=None):
        return self._bus.call_sync(
            self._SERVICE, path, iface, method, args,
            reply_type, Gio.DBusCallFlags.NONE, 3000, None)

    def _on_socket(self, fd, condition) -> bool:
        if condition & (GLib.IO_ERR | GLib.IO_HUP):
            return False
        try:
            chunk = self._sock.recv(4096)
            if not chunk: return False
            self._buf += chunk
            while len(self._buf) >= _HDR.size:
                (count,) = _HDR.unpack_from(self._buf)
                need = _HDR.size + count * _CMP.size
                if len(self._buf) < need: break
                for i in range(count):
                    off = _HDR.size + i * _CMP.size
                    _, deg, _raw, _north, lvl = _CMP.unpack_from(self._buf, off)
                    self._heading = deg % 360
                    self._level = lvl
                self._buf = self._buf[need:]
        except BlockingIOError: pass
        except Exception as e:
            print(f"sensorfwd socket error: {e}")
            return False
        return True

    @property
    def available(self): return self._available

    def read_heading(self): return (self._heading, self._level)

    def close(self):
        if self._watch_id: GLib.source_remove(self._watch_id)
        if self._sock: self._sock.close()
        if self._bus and self._session_id is not None:
            pid = os.getpid()
            for method, path, iface, args in [
                ("stop",          self._CMP_PATH, self._CMP_IF,
                 GLib.Variant("(i)",   (self._session_id,))),
                ("releaseSensor", self._MGR_PATH, self._MGR_IF,
                 GLib.Variant("(six)", ("compasssensor", self._session_id, pid))),
            ]:
                try: self._dbus(path, iface, method, args)
                except Exception: pass


class SensorPoller:
    POLL_MS = 100

    def __init__(self, on_heading_changed):
        self._cb = on_heading_changed
        self._timer = self._backend = None
        iio_path = find_iio_magnetometer()
        if iio_path:
            self._backend = IIOBackend(iio_path)
        else:
            hb = HadessBackend()
            if hb.available:
                self._backend = hb
            else:
                sf = SensorfwBackend()
                if sf.available:
                    self._backend = sf
        if self._backend:
            self._timer = GLib.timeout_add(self.POLL_MS, self._tick)
        else:
            print("No compass backend → demo mode")

    def _tick(self):
        result = self._backend.read_heading()
        if result is not None:
            heading, level = result
            self._cb(heading, level, True)
        return True

    @property
    def available(self): return self._backend is not None

    @property
    def label(self): return self._backend.label if self._backend else ""

    def release(self):
        if self._timer: GLib.source_remove(self._timer)
        if self._backend: self._backend.close()


# ── Accelerometer backend (shared, fan-out) ────────────────────────────────────

class AccelBackend:
    """sensorfwd accelerometer. Emits raw (x, y, z) milli-g to every callback;
    callers scale/interpret as needed."""

    def __init__(self, interval_ms=33):
        self._callbacks  = []
        self._bus = self._sock = self._watch_id = self._session_id = None
        self._buf = b""
        self._available  = False
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            pid = os.getpid()
            self._call("/SensorManager", "local.SensorManager", "loadPlugin",
                       GLib.Variant("(s)", ("accelerometersensor",)))
            res = self._call("/SensorManager", "local.SensorManager", "requestSensor",
                             GLib.Variant("(sx)", ("accelerometersensor", pid)),
                             GLib.VariantType.new("(i)"))
            self._session_id = res.get_child_value(0).get_int32()
            self._sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            self._sock.connect(SOCKET_PATH)
            self._sock.send(struct.pack('<i', self._session_id))
            self._sock.recv(1)
            self._sock.setblocking(False)
            self._watch_id = GLib.io_add_watch(
                self._sock.fileno(), GLib.IO_IN | GLib.IO_ERR | GLib.IO_HUP,
                self._on_socket)
            self._call("/SensorManager/accelerometersensor",
                       "local.AccelerometerSensor", "setInterval",
                       GLib.Variant("(ii)", (self._session_id, interval_ms)))
            self._call("/SensorManager/accelerometersensor",
                       "local.AccelerometerSensor", "start",
                       GLib.Variant("(i)", (self._session_id,)))
            self._available = True
            print(f"Accel: sensorfwd (session {self._session_id})")
        except Exception as e:
            print(f"AccelBackend not available: {e}")

    def _call(self, path, iface, method, args=None, reply_type=None):
        return self._bus.call_sync(SENSOR_SVC, path, iface, method, args,
                                   reply_type, Gio.DBusCallFlags.NONE, 3000, None)

    def _on_socket(self, fd, condition) -> bool:
        if condition & (GLib.IO_ERR | GLib.IO_HUP): return False
        try:
            chunk = self._sock.recv(4096)
            if not chunk: return False
            self._buf += chunk
            while len(self._buf) >= 4:
                (count,) = _HDR.unpack_from(self._buf)
                need = 4 + count * _ACCEL.size
                if len(self._buf) < need: break
                last_xyz = None
                for i in range(count):
                    _, x, y, z, _ = _ACCEL.unpack_from(self._buf, 4 + i * _ACCEL.size)
                    last_xyz = (x, y, z)
                self._buf = self._buf[need:]
                if last_xyz:
                    for cb in self._callbacks:
                        cb(*last_xyz)
        except BlockingIOError: pass
        except Exception as e:
            print(f"Accel socket error: {e}")
            return False
        return True

    def add_callback(self, cb):
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    @property
    def available(self): return self._available

    def close(self):
        if self._watch_id: GLib.source_remove(self._watch_id)
        if self._sock:     self._sock.close()
        if self._bus and self._session_id is not None:
            pid = os.getpid()
            for m, p, i, a in [
                ("stop", "/SensorManager/accelerometersensor",
                 "local.AccelerometerSensor", GLib.Variant("(i)", (self._session_id,))),
                ("releaseSensor", "/SensorManager", "local.SensorManager",
                 GLib.Variant("(six)", ("accelerometersensor", self._session_id, pid))),
            ]:
                try: self._call(p, i, m, a)
                except Exception: pass
