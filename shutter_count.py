"""Read the shutter count from a Canon EOS mirrorless camera over USB (Windows, no driver swap).

Read-only. It talks PTP through Windows' built-in camera driver (WPD/MTP) and sends only:
  0x1001 GetDeviceInfo, 0x9114 SetRemoteMode, 0x9115 SetEventMode,
  0x913D SetRequestOLCInfoGroup, 0x9116 GetEvent.
It never fires the shutter or writes camera settings. It also never sends 0x9127
RequestDevicePropValue, which hangs some bodies until they are power-cycled.

The count comes from Canon property 0xD167 (libgphoto2 calls it ShutterReleaseCounter),
which the camera pushes as an event: [16, 1, mechanical, total]. Both are in steps of 1000.

Usage:  python shutter_count.py
"""
import ctypes
import struct
import sys
import time

import comtypes
import comtypes.client
from comtypes import GUID

comtypes.client.GetModule(r"C:\Windows\System32\PortableDeviceApi.dll")
comtypes.client.GetModule(r"C:\Windows\System32\PortableDeviceTypes.dll")
from comtypes.gen import PortableDeviceApiLib as api  # noqa: E402
from comtypes.gen import PortableDeviceTypesLib as types  # noqa: E402

CANON_VID = "vid_04a9"
OK = 0x2001
ALLOW = {0x1001, 0x9114, 0x9115, 0x913D, 0x9116}
PROP_SHUTTER = 0xD167
EVT_PROP_CHANGED = 0xC189

# ---- WPD plumbing: send raw PTP operations through the in-box driver ----

G_COMMON = GUID("{F0422A9C-5DC8-4440-B5BD-5DF28835658A}")
G_MTP = GUID("{4D545058-1A2E-4106-A357-771E0819FC56}")


def _pk(guid, pid):
    k = types._tagpropertykey()
    k.fmtid = guid
    k.pid = pid
    return ctypes.pointer(k)


K_CATEGORY, K_CMDID, K_HRESULT = _pk(G_COMMON, 1001), _pk(G_COMMON, 1002), _pk(G_COMMON, 1003)
K_OPCODE, K_OPPARAMS, K_RESPCODE = _pk(G_MTP, 1001), _pk(G_MTP, 1002), _pk(G_MTP, 1003)
K_CONTEXT, K_TOTAL, K_TOREAD = _pk(G_MTP, 1006), _pk(G_MTP, 1007), _pk(G_MTP, 1008)
K_READ, K_DATA = _pk(G_MTP, 1009), _pk(G_MTP, 1012)
CMD_NODATA, CMD_READ_START, CMD_READ_DATA, CMD_END = 12, 13, 15, 17


def _a(k):
    return ctypes.cast(k, ctypes.POINTER(api._tagpropertykey))


def _values():
    return comtypes.client.CreateObject(types.PortableDeviceValues, interface=types.IPortableDeviceValues)


def _cmd(dev, cmd_pid, extra=None):
    p = _values()
    p.SetGuidValue(K_CATEGORY, G_MTP)
    p.SetUnsignedIntegerValue(K_CMDID, cmd_pid)
    if extra:
        extra(p)
    return dev.SendCommand(0, p)


def open_canon():
    mgr = comtypes.client.CreateObject(api.PortableDeviceManager, interface=api.IPortableDeviceManager)
    mgr.RefreshDeviceList()
    count = ctypes.c_ulong(0)
    mgr.GetDevices(ctypes.POINTER(ctypes.c_wchar_p)(), ctypes.pointer(count))
    arr = (ctypes.c_wchar_p * count.value)()
    mgr.GetDevices(ctypes.cast(arr, ctypes.POINTER(ctypes.c_wchar_p)), ctypes.pointer(count))
    canon = [d for d in arr if CANON_VID in d.lower()]
    if not canon:
        sys.exit("No Canon camera found. Check that it's connected by USB with a data cable and switched on\n"
                 "(not asleep from auto power off), and that its USB/wireless settings match the\n"
                 "'Camera setup' section of the README. Close EOS Utility if it's open.")
    dev = comtypes.client.CreateObject(api.PortableDevice, interface=api.IPortableDevice)
    dev.Open(canon[-1], _values())
    return dev


def ptp(dev, opcode, params=(), want_data=False):
    """Run one PTP operation; returns (response_code, data_bytes)."""
    if opcode not in ALLOW:
        raise SystemExit(f"refusing opcode 0x{opcode:04X}")

    def fill(p):
        p.SetUnsignedIntegerValue(K_OPCODE, opcode)
        coll = comtypes.client.CreateObject(types.PortableDevicePropVariantCollection,
                                            interface=types.IPortableDevicePropVariantCollection)
        union = [n for n, t in types.tag_inner_PROPVARIANT._fields_ if hasattr(t, "_fields_")][0]
        for v in params:
            pv = types.tag_inner_PROPVARIANT()
            pv.vt = 19  # VT_UI4
            getattr(pv, union).ulVal = v
            coll.Add(pv)
        p.SetIPortableDevicePropVariantCollectionValue(K_OPPARAMS, coll)

    if not want_data:
        r = _cmd(dev, CMD_NODATA, fill)
        hr = r.GetErrorValue(_a(K_HRESULT)) & 0xFFFFFFFF
        if hr:
            raise RuntimeError(f"0x{opcode:04X}: WPD command failed, HRESULT=0x{hr:08X}")
        return r.GetUnsignedIntegerValue(_a(K_RESPCODE)), b""

    r = _cmd(dev, CMD_READ_START, fill)
    ctx = r.GetStringValue(_a(K_CONTEXT))
    total = r.GetUnsignedIntegerValue(_a(K_TOTAL))
    out = b""
    while len(out) < total:
        want = min(total - len(out), 1 << 20)
        cbuf = (ctypes.c_ubyte * want)()

        def rd(p, want=want, cbuf=cbuf):
            p.SetStringValue(K_CONTEXT, ctx)
            p.SetUnsignedIntegerValue(K_TOREAD, want)
            p.SetBufferValue(K_DATA, ctypes.cast(cbuf, ctypes.POINTER(ctypes.c_ubyte)), want)

        rr = _cmd(dev, CMD_READ_DATA, rd)
        got = rr.GetUnsignedIntegerValue(_a(K_READ))
        chunk = b""
        try:
            raw = rr.GetBufferValue(_a(K_DATA))
            if isinstance(raw, tuple):
                raw = raw[0]
            if raw is not None:
                chunk = ctypes.string_at(ctypes.cast(raw, ctypes.c_void_p), got)
        except Exception:
            pass
        if not chunk or not any(chunk):
            chunk = bytes(cbuf[:got])
        out += chunk

    def end(p):
        p.SetStringValue(K_CONTEXT, ctx)

    re_ = _cmd(dev, CMD_END, end)
    return re_.GetUnsignedIntegerValue(_a(K_RESPCODE)), out


def must(dev, opcode, params=(), want_data=False):
    code, data = ptp(dev, opcode, params, want_data)
    if code != OK:
        raise RuntimeError(f"0x{opcode:04X}{list(params)} -> response 0x{code:04X}")
    return data


# ---- PTP parsing ----

def _ptp_str(b, off):
    n = b[off]
    return b[off + 1: off + 1 + n * 2].decode("utf-16le").rstrip("\0"), off + 1 + n * 2


def model_and_firmware(devinfo):
    off = 8
    _, off = _ptp_str(devinfo, off)  # vendor extension description
    off += 2  # functional mode
    for _ in range(5):  # operations, events, properties, capture formats, image formats
        n = struct.unpack_from("<I", devinfo, off)[0]
        off += 4 + 2 * n
    _, off = _ptp_str(devinfo, off)  # manufacturer
    model, off = _ptp_str(devinfo, off)
    firmware, off = _ptp_str(devinfo, off)
    firmware = firmware.split("-", 1)[-1]  # Canon reports e.g. "3-1.8.0"
    return model, firmware  # the serial number comes next; deliberately not read


def shutter_values(event_data):
    """Yield every 0xD167 payload (list of u32) in one GetEvent reply."""
    off = 0
    while off + 8 <= len(event_data):
        size, ec = struct.unpack_from("<II", event_data, off)
        if size < 8 or (size == 8 and ec == 0) or off + size > len(event_data):
            return
        if ec == EVT_PROP_CHANGED and size >= 16 and struct.unpack_from("<I", event_data, off + 8)[0] == PROP_SHUTTER:
            yield list(struct.unpack_from(f"<{(size - 12) // 4}I", event_data, off + 12))
        off += size


def read_shutter(dev, timeout_s=5.0):
    last, t0 = None, time.time()
    while time.time() - t0 < timeout_s:
        for _ in range(50):
            d = must(dev, 0x9116, want_data=True)
            for v in shutter_values(d):
                last = v
            if len(d) <= 8:
                break
        if last:
            return last
        time.sleep(0.3)
    return None


def main():
    comtypes.CoInitialize()
    dev = open_canon()
    remote = event = False
    try:
        model, firmware = model_and_firmware(must(dev, 0x1001, want_data=True))
        print(f"Camera:   {model} (firmware {firmware})")
        must(dev, 0x9114, (1,)); remote = True
        must(dev, 0x9115, (1,)); event = True
        must(dev, 0x913D, (0x1FFF,))
        v = read_shutter(dev)
        if not v or len(v) < 4:
            print(f"The camera didn't report 0xD167 (got {v}). Please open an issue with your model.")
            return 1
        mech, total = v[2], v[3]
        print(f"Mechanical shutter: about {mech:,}")
        print(f"Total releases:     about {total:,}  (includes electronic shutter)")
        if total > mech:
            print(f"Electronic:         about {total - mech:,}")
        print("Values are in steps of 1,000. Right after shooting, the mechanical value can lag "
              "for a few seconds; run again if it looks off.")
        print(f"Raw 0xD167: {v}")
        return 0
    finally:
        steps = ([(0x9114, (0,)), (0x9114, (1,))] if remote else []) + ([(0x9115, (0,))] if event else [])
        for op, prm in steps:
            try:
                ptp(dev, op, prm)
            except Exception as e:
                print(f"(cleanup 0x{op:04X} failed: {e})")
        dev.Close()


if __name__ == "__main__":
    sys.exit(main())
