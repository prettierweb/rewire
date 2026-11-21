"""Rewire's eyes: spots the moment you get into a vehicle, from the game picture.

GTA shows a dark card with the vehicle's name just above the minimap for a few seconds when
you get in or on. That card is the signal: it never shows on foot. Needs numpy; without it
Rewire simply keeps F / Caps Lock.
"""
import ctypes, ctypes.wintypes as wt

try:
    import numpy as np
except ImportError:
    np = None

# the card's place in the game picture, as shares of its width and height (x0, y0, x1, y1)
CARD = (0.0165, 0.697, 0.174, 0.8127)


def has_card(a):
    """a = the CARD region as an RGB array. -> (yes/no, the numbers behind it)."""
    h, w, _ = a.shape
    lum = a.astype(np.int16).sum(2) // 3
    title = lum[int(h * 0.14):int(h * 0.60), int(w * 0.06):int(w * 0.94)]     # name on a dark plate
    strip = lum[int(h * 0.72):int(h * 0.95), int(w * 0.06):int(w * 0.94)]     # grey band with the icons
    above = lum[:max(1, int(h * 0.06)), int(w * 0.06):int(w * 0.94)]          # the road, just over the card
    dark = float(np.median(title))
    text = float((title > 185).mean())                                       # white letters
    plate = float((title < dark + 22).mean())                                # how much of it is the flat plate
    band = float(np.median(strip))
    edge = float(np.median(above)) - dark
    px = a[int(h * 0.72):int(h * 0.95)].astype(np.int16)
    green = float(((px[..., 1] > px[..., 0] + 35) & (px[..., 1] > px[..., 2] + 25)).mean())
    ok = dark < 75 and 0.02 < text < 0.35 and plate > 0.55 and 8 < band - dark < 90 and (edge > 25 or green > 0.01)
    return ok, f"dark {dark:.0f} text {text:.2f} plate {plate:.2f} band {band - dark:+.0f} edge {edge:+.0f} green {green:.3f}"


u32, gdi = ctypes.windll.user32, ctypes.windll.gdi32
u32.GetDC.restype = wt.HDC; u32.GetDC.argtypes = [wt.HWND]
gdi.CreateCompatibleDC.restype = wt.HDC; gdi.CreateCompatibleDC.argtypes = [wt.HDC]
gdi.CreateCompatibleBitmap.restype = wt.HBITMAP
gdi.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
gdi.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]; gdi.SelectObject.restype = wt.HGDIOBJ
u32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
gdi.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
gdi.DeleteObject.argtypes = [wt.HGDIOBJ]; gdi.DeleteDC.argtypes = [wt.HDC]
u32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]


def card_region(hwnd):
    """The CARD region of the window's own picture (16:9, centred in the window) as an RGB array."""
    r = wt.RECT(); u32.GetClientRect(hwnd, ctypes.byref(r))
    w, h = r.right, r.bottom
    if w < 320 or h < 180:
        return None
    pw, ph = (w, round(w * 9 / 16)) if w * 9 <= h * 16 else (round(h * 16 / 9), h)   # the picture inside it
    ox, oy = (w - pw) // 2, (h - ph) // 2
    x0, x1 = ox + round(CARD[0] * pw), ox + round(CARD[2] * pw)
    y0, y1 = oy + round(CARD[1] * ph), oy + round(CARD[3] * ph)
    dc = u32.GetDC(hwnd); mdc = gdi.CreateCompatibleDC(dc); bmp = gdi.CreateCompatibleBitmap(dc, w, h)
    old = gdi.SelectObject(mdc, bmp)
    ok = u32.PrintWindow(hwnd, mdc, 3)
    gdi.SelectObject(mdc, old)
    rows = y1 - y0
    hdr = (ctypes.c_uint32 * 10)(40, w, h, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)    # bottom-up: scan 0 = last row
    buf = ctypes.create_string_buffer(w * rows * 4)
    got = gdi.GetDIBits(mdc, bmp, h - y1, rows, buf, hdr, 0)
    gdi.DeleteObject(bmp); gdi.DeleteDC(mdc); u32.ReleaseDC(hwnd, dc)
    if not ok or got != rows:
        return None
    a = np.frombuffer(buf, np.uint8).reshape(rows, w, 4)[::-1, x0:x1, 2::-1]   # flip up, BGRX -> RGB
    return a


def grab_full(hwnd):
    """The whole window's own picture as an RGB array (for saving a miss)."""
    r = wt.RECT(); u32.GetClientRect(hwnd, ctypes.byref(r))
    w, h = r.right, r.bottom
    if w <= 0 or h <= 0:
        return None
    dc = u32.GetDC(hwnd); mdc = gdi.CreateCompatibleDC(dc); bmp = gdi.CreateCompatibleBitmap(dc, w, h)
    old = gdi.SelectObject(mdc, bmp)
    ok = u32.PrintWindow(hwnd, mdc, 3)
    gdi.SelectObject(mdc, old)
    hdr = (ctypes.c_uint32 * 10)(40, w, (-h) & 0xFFFFFFFF, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)   # top-down
    buf = ctypes.create_string_buffer(w * h * 4)
    got = gdi.GetDIBits(mdc, bmp, 0, h, buf, hdr, 0)
    gdi.DeleteObject(bmp); gdi.DeleteDC(mdc); u32.ReleaseDC(hwnd, dc)
    if not ok or got != h:
        return None
    return np.frombuffer(buf, np.uint8).reshape(h, w, 4)[..., 2::-1]


def save_png(a, path):
    """RGB array -> .png, no Pillow needed."""
    import struct, zlib
    if a is None:
        return
    h, w, _ = a.shape
    raw = b"".join(b"\x00" + np.ascontiguousarray(a[y]).tobytes() for y in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 3)) + chunk(b"IEND", b""))
