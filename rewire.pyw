"""Rewire: keyboard + mouse -> virtual DualShock 4, for PS5 Remote Play through Veyra.

Personal tool. Only acts while armed (F10) AND Veyra is the foreground window.
While live: bound keys/clicks are swallowed, the cursor is pinned in Veyra,
raw mouse motion drives the right stick. Alt+Tab away = everything released.
Two layouts (on foot / driving), GTA-style; F (enter/exit) and Caps Lock switch.
Panic: F10, Alt+Tab, or Ctrl+Alt+Del then Esc (frees the cursor).
"""
import ctypes, ctypes.wintypes as wt, json, math, os, struct, subprocess, sys, threading, time, traceback
import tkinter as tk
import tkinter.font as tkfont

try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass

import vgamepad as vg

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "config.json")
CFG_VERSION = 2

# ---------------------------------------------------------------- inputs / targets
VK = {
    **{chr(c): c for c in range(0x41, 0x5B)},
    **{str(d): 0x30 + d for d in range(10)},
    "Esc": 0x1B, "Space": 0x20, "Tab": 0x09, "Enter": 0x0D, "Backspace": 0x08,
    "LShift": 0xA0, "RShift": 0xA1, "LCtrl": 0xA2, "RCtrl": 0xA3, "LAlt": 0xA4,
    "CapsLock": 0x14, "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75,
    "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
}
VK_NAME = {v: k for k, v in VK.items()}
MOUSE_INPUTS = ["LMB", "RMB", "MMB", "Mouse4", "Mouse5", "WheelUp", "WheelDown"]
RESERVED = {"LAlt", "F10"}   # Alt keeps Alt+Tab; F10 arms/disarms

# target -> label shown on the keys
TARGETS = {
    "CROSS": "✕", "CIRCLE": "○", "SQUARE": "□", "TRIANGLE": "△",
    "L1": "L1", "R1": "R1", "L2": "L2", "R2": "R2", "L3": "L3", "R3": "R3",
    "OPTIONS": "Options", "SHARE": "Create", "TOUCHPAD": "Pad", "PS": "PS",
    "DUP": "D↑", "DDOWN": "D↓", "DLEFT": "D←", "DRIGHT": "D→",
    "LS_UP": "↑", "LS_DOWN": "↓", "LS_LEFT": "←", "LS_RIGHT": "→",
    "MODE": "⇄",
}
# GTA 6 default PS5 scheme, driven by GTA V's PC keys.
FOOT = {
    "W": ["LS_UP"], "A": ["LS_LEFT"], "S": ["LS_DOWN"], "D": ["LS_RIGHT"],
    "Space": ["CROSS"],        # jump / climb
    "LShift": ["L3"],          # run, again = sprint
    "LCtrl": ["CIRCLE"],       # crouch
    "F": ["TRIANGLE", "MODE"], # enter vehicle -> driving layout
    "E": ["TRIANGLE"],         # interact
    "R": ["SQUARE"],           # melee
    "Q": ["R1"],               # cover
    "G": ["R1"],               # quick throw (while aiming)
    "Tab": ["L1"],             # holster / weapon menu
    "C": ["R3"],               # look behind / zoom while aiming
    "M": ["TOUCHPAD"],         # map
    "P": ["OPTIONS"], "Enter": ["OPTIONS"],
    "Up": ["DUP"], "Down": ["DDOWN"], "Left": ["DLEFT"], "Right": ["DRIGHT"],
    "Z": ["DDOWN"],            # objectives / minimap
    "CapsLock": ["MODE"],
    "F1": ["PS"], "F2": ["SHARE"],
    "LMB": ["R2"], "RMB": ["L2"], "MMB": ["R3"], "Mouse4": ["L1"], "Mouse5": ["R1"],
}
DRIVE = {
    "W": ["R2"], "S": ["L2"], "A": ["LS_LEFT"], "D": ["LS_RIGHT"],
    "LCtrl": ["LS_DOWN"],      # lean back: W + Ctrl = wheelie (GTA V PC)
    "X": ["LS_UP"],            # lean forward
    "Space": ["CROSS"],        # handbrake
    "F": ["TRIANGLE", "MODE"], # exit vehicle -> on-foot layout
    "E": ["L3"], "LShift": ["L3"],  # horn / nitrous
    "H": ["CIRCLE"],           # headlights
    "C": ["R3"],               # look behind
    "R": ["SQUARE"],           # melee
    "Q": ["DLEFT"],            # radio
    "Tab": ["L1"],
    "M": ["TOUCHPAD"], "P": ["OPTIONS"], "Enter": ["OPTIONS"],
    "Up": ["DUP"], "Down": ["DDOWN"], "Left": ["DLEFT"], "Right": ["DRIGHT"],  # phone, map, indicators
    "Z": ["DDOWN"], "CapsLock": ["MODE"], "F1": ["PS"], "F2": ["SHARE"],
    "LMB": ["R1"], "RMB": ["L1"],
}
DEFAULTS = {
    "version": CFG_VERSION,
    "toggle_key": "F10",
    # Remote Play apps Rewire drives. Add yours (e.g. chiaki-ng) by its .exe name.
    "targets": ["veyra_qml_ui.exe"],
    "layouts": {"foot": FOOT, "drive": DRIVE},
    # window_ms = one game frame: 16 for a 60 fps game, 33 for 30 fps
    "aim": {"sensitivity": 1.0, "anti_deadzone": 0.34, "curve": 1.0,
            "window_ms": 16.0, "ramp_ms": 0.0, "invert_y": False},
}

DS4B, DS4S, DPAD = vg.DS4_BUTTONS, vg.DS4_SPECIAL_BUTTONS, vg.DS4_DPAD_DIRECTIONS
BTN = {"CROSS": DS4B.DS4_BUTTON_CROSS, "CIRCLE": DS4B.DS4_BUTTON_CIRCLE,
       "SQUARE": DS4B.DS4_BUTTON_SQUARE, "TRIANGLE": DS4B.DS4_BUTTON_TRIANGLE,
       "L1": DS4B.DS4_BUTTON_SHOULDER_LEFT, "R1": DS4B.DS4_BUTTON_SHOULDER_RIGHT,
       "L3": DS4B.DS4_BUTTON_THUMB_LEFT, "R3": DS4B.DS4_BUTTON_THUMB_RIGHT,
       "OPTIONS": DS4B.DS4_BUTTON_OPTIONS, "SHARE": DS4B.DS4_BUTTON_SHARE}
SPECIAL = {"PS": DS4S.DS4_SPECIAL_BUTTON_PS, "TOUCHPAD": DS4S.DS4_SPECIAL_BUTTON_TOUCHPAD}
DPAD_DIR = {(0, 1): DPAD.DS4_BUTTON_DPAD_NORTH, (1, 1): DPAD.DS4_BUTTON_DPAD_NORTHEAST,
            (1, 0): DPAD.DS4_BUTTON_DPAD_EAST, (1, -1): DPAD.DS4_BUTTON_DPAD_SOUTHEAST,
            (0, -1): DPAD.DS4_BUTTON_DPAD_SOUTH, (-1, -1): DPAD.DS4_BUTTON_DPAD_SOUTHWEST,
            (-1, 0): DPAD.DS4_BUTTON_DPAD_WEST, (-1, 1): DPAD.DS4_BUTTON_DPAD_NORTHWEST,
            (0, 0): DPAD.DS4_BUTTON_DPAD_NONE}


# ---------------------------------------------------------------- config
def _clean_layout(lay):
    out = {}
    if isinstance(lay, dict):
        for k, v in lay.items():
            if (k in VK or k in MOUSE_INPUTS) and k not in RESERVED:
                v = v if isinstance(v, list) else [v]
                v = [t for t in v if t in TARGETS]
                if v:
                    out[k] = v
    return out


def load_cfg():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            user = json.load(f)
        if isinstance(user.get("aim"), dict):
            cfg["aim"].update(user["aim"])
        if user.get("version") == CFG_VERSION:
            if user.get("toggle_key") in VK:
                cfg["toggle_key"] = user["toggle_key"]
            win = user.get("window")
            if isinstance(win, list) and len(win) == 4 and all(isinstance(v, int) for v in win):
                cfg["window"] = win
            t = user.get("targets")
            if isinstance(t, list) and t and all(isinstance(x, str) for x in t):
                cfg["targets"] = [x.lower() for x in t]
            lays = user.get("layouts", {})
            for m in ("foot", "drive"):
                if m in lays:
                    cfg["layouts"][m] = _clean_layout(lays[m])
    except FileNotFoundError:
        pass
    except (ValueError, AttributeError, TypeError):
        try:
            os.replace(CFG_PATH, CFG_PATH + ".broken")
        except OSError:
            pass
    a = cfg["aim"]
    a["ramp_ms"] = 0.0   # the turn-boost aim felt like the mouse moved on its own (11-20): always classic
    for k, v in DEFAULTS["aim"].items():
        try:
            a[k] = bool(a[k]) if isinstance(v, bool) else float(a[k])
        except (KeyError, TypeError, ValueError):
            a[k] = v
    save_cfg(cfg)
    return cfg


def save_cfg(cfg):
    tmp = CFG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CFG_PATH)


# ---------------------------------------------------------------- win32
u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
u32.CallNextHookEx.argtypes = [wt.HANDLE, ctypes.c_int, wt.WPARAM, wt.LPARAM]
u32.CallNextHookEx.restype = LRESULT
u32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
u32.DefWindowProcW.restype = LRESULT
u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
u32.SetWindowsHookExW.restype = wt.HANDLE
u32.GetRawInputData.argtypes = [wt.HANDLE, wt.UINT, ctypes.c_void_p, ctypes.POINTER(wt.UINT), wt.UINT]
u32.ClipCursor.argtypes = [ctypes.c_void_p]
u32.CreateWindowExW.restype = wt.HWND
u32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
u32.RegisterRawInputDevices.argtypes = [ctypes.c_void_p, wt.UINT, wt.UINT]
u32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
k32.GetModuleHandleW.restype = wt.HMODULE


class KBD(ctypes.Structure):
    _fields_ = [("vk", wt.DWORD), ("scan", wt.DWORD), ("flags", wt.DWORD), ("time", wt.DWORD),
                ("extra", ctypes.c_size_t)]


class MSLL(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("data", wt.DWORD), ("flags", wt.DWORD), ("time", wt.DWORD),
                ("extra", ctypes.c_size_t)]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE),
                ("hIcon", wt.HICON), ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wt.USHORT), ("usUsage", wt.USHORT), ("dwFlags", wt.DWORD),
                ("hwndTarget", wt.HWND)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


def monitors():
    """-> list of (work_rect (l, t, r, b), is_primary) for every connected monitor."""
    out = []
    PROC = ctypes.WINFUNCTYPE(ctypes.c_int, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)

    def cb(hmon, hdc, rect, data):
        mi = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        if u32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            w = mi.rcWork
            out.append(((w.left, w.top, w.right, w.bottom), bool(mi.dwFlags & 1)))
        return 1
    u32.EnumDisplayMonitors(None, None, PROC(cb), 0)
    return out


def hide_point(hwnd, r):
    """Where to pin the cursor so it can't be seen: on a screen edge with no monitor beyond it,
    the arrow hangs off the screen. Falls back to the window's middle."""
    u32.MonitorFromWindow.restype = wt.HMONITOR; u32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
    u32.MonitorFromPoint.restype = wt.HMONITOR; u32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
    mi = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    if u32.GetMonitorInfoW(u32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi)):
        m = mi.rcMonitor
        mx, my = (m.left + m.right) // 2, (m.top + m.bottom) // 2
        for x, y, ox, oy in ((mx, m.bottom - 1, 0, 8), (m.right - 1, my, 8, 0)):
            if not u32.MonitorFromPoint(wt.POINT(x + ox, y + oy), 0):
                return x, y
    return (r.left + r.right) // 2, (r.top + r.bottom) // 2


def foreground_exe():
    hwnd = u32.GetForegroundWindow()
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = k32.OpenProcess(0x1000, False, pid.value)
    if not h:
        return hwnd, ""
    buf = ctypes.create_unicode_buffer(520)
    n = wt.DWORD(520)
    ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
    k32.CloseHandle(h)
    return hwnd, (os.path.basename(buf.value).lower() if ok else "")


# ---------------------------------------------------------------- real controllers
HIDHIDE = r"C:\Program Files\Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe"
OUR_PAD_GUID = "4c050000c4050000"   # vendor 054C / product 05C4: the virtual DS4 Rewire creates


class Hider:
    """While Rewire runs, HidHide hides real game controllers from every other app, so the
    Remote Play app only sees Rewire's controller (which carries the real pad too).
    Cloaking is switched off again when Rewire closes; unhide.bat does the same by hand."""

    def __init__(self):
        self.ok = os.path.exists(HIDHIDE)
        self.active = False
        self.hidden = set()

    def cli(self, *args):
        try:
            return subprocess.run([HIDHIDE, *args], capture_output=True, text=True, timeout=10,
                                  creationflags=0x08000000).stdout
        except Exception:
            return ""

    def start(self):
        if not self.ok:
            return
        me = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        self.scan(["--app-reg", me, "--cloak-on"])
        self.active = True

    def scan(self, extra=()):
        args = list(extra)
        try:
            groups = json.loads(self.cli("--dev-gaming") or "[]")
        except ValueError:
            groups = []
        for g in groups:
            for d in g.get("devices", []):
                path = d.get("deviceInstancePath", "")
                # virtual pads (ours) have no physical base container: never hide those
                if d.get("present") and d.get("gamingDevice") and d.get("baseContainerDeviceInstancePath") \
                        and path not in self.hidden:
                    args += ["--dev-hide", path]
                    self.hidden.add(path)
        if args:
            self.cli(*args)

    def stop(self):
        if self.ok and self.active:
            self.cli("--cloak-off")
            self.active = False


class RealPad(threading.Thread):
    """Reads the first real controller (DualSense, DS4, Xbox...) so its input is merged
    into Rewire's controller. Rumble from the game is passed back to it."""
    BUTTONS = {0: "CROSS", 1: "CIRCLE", 2: "SQUARE", 3: "TRIANGLE", 4: "SHARE", 5: "PS", 6: "OPTIONS",
               7: "L3", 8: "R3", 9: "L1", 10: "R1", 11: "DUP", 12: "DDOWN", 13: "DLEFT", 14: "DRIGHT",
               20: "TOUCHPAD"}

    def __init__(self, eng):
        super().__init__(daemon=True)
        self.eng = eng
        self.state = None        # latest reading, replaced whole (no lock needed)
        self.name = ""
        self.rumble = (0, 0)

    def run(self):
        os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
        os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
        os.environ["SDL_JOYSTICK_HIDAPI_PS5_RUMBLE"] = "1"
        os.environ["SDL_JOYSTICK_HIDAPI_PS4_RUMBLE"] = "1"
        try:
            import pygame
            from pygame._sdl2 import controller
            pygame.display.init(); pygame.joystick.init(); controller.init()
        except Exception:
            return
        pad, next_scan, sent = None, 0.0, None
        while self.eng.running:
            try:
                pygame.event.pump()
                now = time.perf_counter()
                if (pad is None or not pad.attached()) and now >= next_scan:
                    pad, self.name, self.state = None, "", None
                    next_scan = now + 1.0
                    for i in range(pygame.joystick.get_count()):
                        if not controller.is_controller(i):
                            continue
                        if OUR_PAD_GUID in pygame.joystick.Joystick(i).get_guid():
                            continue
                        pad = controller.Controller(i)
                        self.name = controller.name_forindex(i) or "Controller"
                        break
                if pad is not None:
                    ax = lambda a: pad.get_axis(a) / 32767.0
                    btn = {t for b, t in self.BUTTONS.items() if pad.get_button(b)}
                    self.state = {"lx": ax(0), "ly": -ax(1), "rx": ax(2), "ry": -ax(3),
                                  "lt": max(0.0, ax(4)), "rt": max(0.0, ax(5)), "buttons": btn}
                    if self.rumble != sent:
                        lo, hi = self.rumble
                        if lo or hi:
                            pad.rumble(lo / 255.0, hi / 255.0, 2000)
                        else:
                            pad.stop_rumble()
                        sent = self.rumble
            except Exception:
                pad, self.state = None, None
            time.sleep(0.004)


# ---------------------------------------------------------------- aim
GAME_EXP = 1.8   # GTA 6's stick response, measured with the F9 test (2026-11-19)


class Aim:
    """Mouse counts -> right stick, losing nothing.

    The console reads the stick once per game frame, so every count is spread evenly over one
    frame-length window. A running tally ("debt") of counts received minus counts the camera has
    really turned is fed back in, so the turn adds up to the hand movement.

    GTA 6 also ramps the camera up to speed over ~0.65 s whatever the settings say (F9 test).
    `w` is Rewire's model of how fast the camera is really turning right now: the stick goes
    to full tilt at the start of a move so the ramp climbs as fast as it can, settles on the
    tilt for the wanted speed once the camera gets there, and only what `w` really turned is
    taken off the tally.
    """
    CATCHUP = 0.030     # s to work off the tally

    def __init__(self):
        self.ev = []            # (t, dx, dy) inside the window
        self.debt_x = self.debt_y = 0.0
        self.wx = self.wy = 0.0  # modelled camera speed, counts/s
        self.last = 0.0

    def reset(self):
        self.ev.clear()
        self.debt_x = self.debt_y = 0.0
        self.wx = self.wy = 0.0

    def feed(self, t, dx, dy):
        self.ev.append((t, dx, dy))
        self.debt_x += dx
        self.debt_y += dy
        self.last = t

    def classic(self, ev, win, a):
        """The plain mapping from the version that felt best (11-19): stick tilt = mouse speed
        over the last game frame. No tally, no catch-up: the camera stops the moment the mouse does."""
        self.debt_x = self.debt_y = self.wx = self.wy = 0.0
        vx = sum(e[1] for e in ev) / win
        vy = sum(e[2] for e in ev) / win
        speed = math.hypot(vx, vy)
        full = 6000.0 / max(a["sensitivity"], 0.05)
        if speed < full * 0.03:
            return 0, 0
        adz = min(max(a["anti_deadzone"], 0.0), 0.9)
        d = min(1.0, speed / full) ** max(a["curve"], 0.2)
        out = min(1.0, adz + (1 - adz) * d)
        return round(vx / speed * out * 127), round(vy / speed * out * 127)

    def step(self, now, dt, a):
        """Returns the stick as two bytes offsets (-127..127), x right, y down (mouse sense)."""
        win = min(max(a["window_ms"], 2.0), 60.0) / 1000.0
        ramp = max(a.get("ramp_ms", 0.0), 0.0) / 1000.0
        max_lag = 0.15 if ramp else 0.05     # how far behind the camera may fall before the rest is dropped
        idle = 0.15 if ramp else 0.06        # how long it may keep catching up after the mouse stops
        ev = self.ev
        i = 0
        while i < len(ev) and now - ev[i][0] >= win:
            i += 1
        if i:
            del ev[:i]
        if not ev and now - self.last > win + idle:
            self.debt_x = self.debt_y = self.wx = self.wy = 0.0
            return 0, 0
        if not ramp:
            return self.classic(ev, win, a)
        vx = vy = px = py = 0.0     # window speed, and counts the window still owes
        for t, dx, dy in ev:
            vx += dx; vy += dy
            left = 1.0 - (now - t) / win
            px += dx * left; py += dy * left
        vx /= win; vy /= win
        full = 6000.0 / max(a["sensitivity"], 0.05)   # counts/s that = full tilt
        adz = min(max(a["anti_deadzone"], 0.0), 0.9)
        curve = max(a["curve"], 0.2)
        ex, ey = self.debt_x - px, self.debt_y - py   # what the window won't cover by itself
        cap = full * max_lag
        e = math.hypot(ex, ey)
        if e > cap:
            self.debt_x -= ex * (1 - cap / e); self.debt_y -= ey * (1 - cap / e)
            ex *= cap / e; ey *= cap / e
        tx, ty = vx + ex / self.CATCHUP, vy + ey / self.CATCHUP
        speed = math.hypot(tx, ty)
        if speed <= 0:
            self.wx = self.wy = 0.0
            return 0, 0
        # GTA 6 turns at speed ~ ((tilt - deadzone) / (1 - deadzone)) ** GAME_EXP (measured with F9),
        # so take the GAME_EXP root: then mouse speed -> camera speed is straight (curve 1 = linear)
        want = min(1.0, speed / full)
        out = adz + (1 - adz) * (want ** curve) ** (1.0 / GAME_EXP)
        w_along = (self.wx * tx + self.wy * ty) / speed          # camera speed in the wanted direction
        if ramp and w_along < 0.97 * min(speed, full):
            out = 1.0                                            # still ramping: full tilt climbs fastest
        bx, by = round(tx / speed * out * 127), round(ty / speed * out * 127)
        m = math.hypot(bx, by) / 127.0
        if m <= adz:
            self.wx = self.wy = 0.0
            return 0, 0     # inside the game's deadzone it does nothing: wait and send a real step
        # the speed this tilt asks the game for (counts/s), and how the game gets there
        vt = full * (min(1.0, (m - adz) / (1 - adz)) ** GAME_EXP) ** (1.0 / curve)
        gx, gy = bx / (m * 127.0) * vt, by / (m * 127.0) * vt
        if ramp and vt > math.hypot(self.wx, self.wy):
            dxw, dyw = gx - self.wx, gy - self.wy
            d = math.hypot(dxw, dyw)
            stepw = vt / ramp * dt
            if d > stepw:
                gx, gy = self.wx + dxw / d * stepw, self.wy + dyw / d * stepw
        self.wx, self.wy = gx, gy                                # slowing down is instant in the game
        self.debt_x -= gx * dt; self.debt_y -= gy * dt
        return bx, by


# ---------------------------------------------------------------- engine
class Engine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.pad = vg.VDS4Gamepad()
        self.real = RealPad(self)
        self.hider = None
        real = self.real

        def on_rumble(client, target, large_motor, small_motor, lightbar_color, user_data):
            real.rumble = (large_motor, small_motor)   # the game's rumble goes back to the real pad
        try:
            self.pad.register_notification(callback_function=on_rumble)
            self._rumble_cb = on_rumble
        except Exception:
            pass
        self.lock = threading.Lock()
        self.armed = False
        self.live = False          # armed and Veyra in front
        self.veyra_front = False
        self.mode = "foot"
        self.down = set()          # input names whose press we swallowed (held)
        self.pulses = {}           # wheel input -> release time
        self.toggle_down = False
        self.aim = Aim()
        self.seen = 0.0
        self.steer = 0.0
        self.eyes = False          # detect.py is up and watching the picture
        self.eyes_hold = 0.0
        self.eyes_proc = None
        self.hwnd = None
        self.out = frozenset()
        self.calib = None          # F9 test pattern: [(start, end, stick x)]
        self.swipe = None          # F8 swipe test: [(start, end, counts/s, ramp_ms)]
        self.puppet = None         # puppet.json: inputs Claude holds until a set time
        self.macro = None          # F7 first-person trick: [(start, end, button)]     # PS buttons pressed right now (for the controller drawing)
        self.wake = threading.Event()   # input arrived: send it now, don't wait for the next tick
        self.stat = [0, 0.0, 0.0, 0]    # mouse events, worst event->output delay, worst tick gap, ticks
        self.rs = self.ls = (0.0, 0.0)
        self.error = False
        self.running = True
        self.rebuild_maps()

    def rebuild_maps(self):
        self.toggle_vk = VK[self.cfg["toggle_key"]]
        lays = self.cfg["layouts"]
        self.bound = set(lays["foot"]) | set(lays["drive"])

    def layout(self):
        return self.cfg["layouts"][self.mode]

    def flip_mode(self):
        self.mode = "drive" if self.mode == "foot" else "foot"
        self.eyes_hold = time.perf_counter() + 2.5   # you said so: the eyes wait for the animation

    def watch_puppet(self):
        path, seen = os.path.join(HERE, "puppet.json"), 0.0
        while self.running:
            time.sleep(0.02)
            try:
                m = os.path.getmtime(path)
                if m != seen:
                    seen = m
                    with open(path, encoding="utf-8") as f:
                        self.puppet = json.load(f)
                    self.wake.set()
            except (OSError, ValueError):
                pass

    def watch_card(self):
        """Getting in: GTA shows the vehicle's name above the minimap. See it -> driving layout.
        Getting out is the F key itself. So nobody has to switch by hand."""
        try:
            import eyes
        except Exception:
            return
        if eyes.np is None:
            return
        self.eyes = True
        seen = 0
        while self.running:
            time.sleep(0.2)
            hwnd = self.hwnd
            if not (self.live and hwnd):
                seen = 0
                continue
            try:
                a = eyes.card_region(hwnd)
                seen = seen + 1 if a is not None and eyes.has_card(a)[0] else 0
            except Exception:
                seen = 0
            if seen == 2 and self.mode != "drive" and time.perf_counter() >= self.eyes_hold:
                with self.lock:
                    self.mode = "drive"

    def watch(self):
        """Reads detect.py's verdicts and switches on foot / driving by itself."""
        try:
            exe = os.path.join(os.path.dirname(sys.executable), "python.exe")
            proc = subprocess.Popen([exe, os.path.join(HERE, "detect.py"), "--live", *self.cfg["targets"]],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                    creationflags=0x08000000 | 0x00004000)   # no window, below-normal priority
        except OSError:
            return
        self.eyes_proc = proc
        run = 0; last = None
        for line in proc.stdout:
            if not self.running:
                break
            parts = line.split()
            if parts and parts[0] == "ready":
                self.eyes = True
                continue
            if len(parts) != 2 or parts[0] not in ("drive", "foot"):
                continue
            want, conf = parts[0], float(parts[1])
            run = run + 1 if want == last and conf >= 0.62 else (1 if conf >= 0.62 else 0)
            last = want
            if run >= 3 and want != self.mode and self.live and time.perf_counter() >= self.eyes_hold:
                with self.lock:
                    self.mode = want
        self.eyes = False

    # -- hook thread. Only swallow an "up" whose "down" we swallowed,
    # so nothing is ever left half-pressed in Veyra or Windows.
    def _press(self, name, down, pulse=False):
        with self.lock:
            if down:
                if not self.live or name not in self.bound:
                    return False
                if pulse:
                    self.pulses[name] = time.perf_counter() + 0.07
                    if "MODE" in self.layout().get(name, ()):
                        self.flip_mode()
                    return True
                if name not in self.down:
                    self.down.add(name)
                    t = self.layout().get(name, ())
                    if "MODE" in t and (self.mode == "drive" or not self.eyes or len(t) == 1):
                        self.flip_mode()
                self.wake.set()
                return True
            if name in self.down:
                self.down.discard(name)
                self.wake.set()
                return True
        return False

    def start_first_person(self):
        """The GTA 6 first-person glitch, typed for you: phone up, then put it away with Circle
        while spamming the touchpad (set to Camera in Settings > Controller). Press again if the
        view changed when the phone closed: that means it missed."""
        now = time.perf_counter()
        steps = [(now, now + 0.15, "DUP")]          # phone up
        c = now + 1.0
        steps.append((c, c + 0.08, "CIRCLE"))       # put it away...
        t = c + 0.09                                # ...THEN spam the touchpad (Camera); a press while
        while t < c + 1.4:                          # the phone is still up does something else
            steps.append((t, t + 0.05, "TOUCHPAD")); t += 0.1
        self.macro = steps
        self.wake.set()

    def start_swipe(self):
        """The same mouse movement at three speeds, each with the ramp fix off then on, left then
        right. If the fix works, every swipe turns the camera the same amount."""
        full = 6000.0 / max(self.cfg["aim"]["sensitivity"], 0.05)
        counts = 0.32 * full                 # one swipe = 0.32 s of full tilt worth of turn
        t = time.perf_counter() + 1.0
        steps = []
        for dur in (0.4, 0.8, 1.6):
            for ramp in (0.0, 650.0):
                for sign in (1, -1):
                    steps.append((t, t + dur, sign * counts / dur, ramp)); t += dur + 1.3
        self.swipe = steps
        with open(os.path.join(HERE, "calib.log"), "a", encoding="utf-8") as f:
            off = time.time() - time.perf_counter()
            f.write("swipe\n" + "".join(f"{a + off:.4f} {b + off:.4f} {v:+.1f} {r:.0f}\n" for a, b, v, r in steps))

    def start_calib(self):
        """Holds the right stick at known tilts, left then right so you end up facing the same way,
        and writes when each one started. A frame grabber records the camera; together they show
        the game's deadzone, its speed for each tilt, and how long it takes to speed up."""
        t = time.perf_counter() + 1.0
        steps = []
        for d in (0.12, 0.18, 0.24, 0.30, 0.36, 0.45, 0.55, 0.70, 0.85, 1.0):
            for sign in (1, -1):
                steps.append((t, t + 0.9, sign * d)); t += 1.5
        self.calib = steps
        with open(os.path.join(HERE, "calib.log"), "a", encoding="utf-8") as f:
            off = time.time() - time.perf_counter()
            f.write("start\n" + "".join(f"{a + off:.4f} {b + off:.4f} {d:+.2f}\n" for a, b, d in steps))

    def on_key(self, vk, down, alt):
        if vk == self.toggle_vk:
            if not (self.armed or self.veyra_front):
                return False          # F10 belongs to other apps when we're idle
            if down and not self.toggle_down:
                self.armed = not self.armed
            self.toggle_down = down
            return True
        if vk == 0x76 and self.live:  # F7: the first-person trick (in the driver's seat)
            if down and not self.macro:
                self.start_first_person()
            return True
        if vk == 0x77 and self.live and u32.GetKeyState(0x11) < 0:  # F8: swipe test (stand still, hands off, ~30 s)
            if down and not self.swipe:
                self.start_swipe()
            return True
        if vk == 0x78 and self.live and u32.GetKeyState(0x11) < 0:  # F9: measure how the game turns the camera (stand still, don't touch)
            if down and not self.calib:
                self.start_calib()
            return True
        if alt and down:
            return False              # keep Alt+Tab / Alt+F4 working
        name = VK_NAME.get(vk)
        return self._press(name, down) if name else False

    def on_mouse(self, name, down):
        if name.startswith("Wheel"):
            return self._press(name, True, pulse=True)
        if down and self.live and name not in self.bound:
            with self.lock:
                self.down.add(name)   # swallow unbound clicks too, so Veyra doesn't react
            return True
        return self._press(name, down)

    def on_raw(self, dx, dy):
        with self.lock:
            if self.live:
                self.aim.feed(time.perf_counter(), dx, dy)
                self.stat[0] += 1
        self.wake.set()

    # -- output loop
    def release_all(self):
        with self.lock:
            self.down.clear(); self.pulses.clear()
            self.aim.reset()
        self.pad.reset(); self.pad.update()
        self.rs = self.ls = (0.0, 0.0)

    def set_live(self, on):
        with self.lock:
            self.live = on
        if not on:
            self.release_all()

    def loop(self):
        ctypes.windll.winmm.timeBeginPeriod(1)
        sys.setswitchinterval(0.0005)   # the window's redraws may not hold this thread up for 5 ms
        next_stat = time.perf_counter() + 5
        last = time.perf_counter()
        next_fg = 0.0
        clip = None
        try:
            while self.running:
                now = time.perf_counter()
                try:
                    if now >= next_fg:
                        next_fg = now + 0.05
                        hwnd, exe = foreground_exe()
                        self.veyra_front = exe in self.cfg["targets"]
                        self.hwnd = hwnd if self.veyra_front else None
                        want = self.armed and self.veyra_front
                        if want != self.live:
                            self.set_live(want)
                        if self.live:
                            r = wt.RECT(); u32.GetWindowRect(hwnd, ctypes.byref(r))
                            cx, cy = hide_point(hwnd, r)
                            clip = wt.RECT(cx, cy, cx + 1, cy + 1)
                            u32.ClipCursor(ctypes.byref(clip))
                        elif clip is not None:
                            u32.ClipCursor(None); clip = None
                    dt = max(now - last, 1e-4); last = now
                    self.tick(now, dt)   # always: the real controller passes through even when off
                    if now >= next_stat:
                        next_stat = now + 5
                        with self.lock:
                            ev, lag, gap, n = self.stat
                            self.stat = [0, 0.0, 0.0, 0]
                        if n and ev:   # only while live and the mouse moved
                            with open(os.path.join(HERE, "timing.log"), "a", encoding="utf-8") as f:
                                f.write(f"{time.strftime('%H:%M:%S')} mouse {ev / 5:.0f}/s  sent {n / 5:.0f}/s  "
                                        f"worst wait {lag * 1000:.1f} ms  worst gap {gap * 1000:.1f} ms\n")
                except Exception:
                    # never keep swallowing input after an error: drop to OFF and log it
                    self.armed = False
                    self.set_live(False)
                    if clip is not None:
                        u32.ClipCursor(None); clip = None
                    with open(os.path.join(HERE, "errors.log"), "a", encoding="utf-8") as f:
                        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc())
                    self.error = True
                # sleep until input arrives (or 2 ms), but never spin faster than 1 kHz
                self.wake.wait(0.002)
                self.wake.clear()
                spare = 0.001 - (time.perf_counter() - now)
                if spare > 0:
                    time.sleep(spare)
        finally:
            self.armed = False
            with self.lock:
                self.live = False
            if clip is not None:
                u32.ClipCursor(None)
            self.release_all()
            ctypes.windll.winmm.timeEndPeriod(1)

    def tick(self, now, dt):
        a = self.cfg["aim"]
        with self.lock:
            if self.swipe and self.live:
                a = dict(a)
                for s0, s1, cps, rmp in self.swipe:
                    if s0 <= now < s1:
                        self.aim.feed(now, cps * dt, 0.0)
                    if s0 <= now < s1 + 1.0:
                        a["ramp_ms"] = rmp
                if now > self.swipe[-1][1] + 1.2:
                    self.swipe = None
            bx, by = self.aim.step(now, dt, a) if self.live else (0, 0)
            st = self.stat
            if self.live:
                st[3] += 1
                st[2] = max(st[2], dt)
                if self.aim.last != self.seen:    # a new mouse event: how long did it wait for us?
                    st[1] = max(st[1], now - self.aim.last)
                    self.seen = self.aim.last
            active = set(self.down)
            for n, t in list(self.pulses.items()):
                if t > now:
                    active.add(n)
                else:
                    del self.pulses[n]
            lay = self.layout()
        targets = set()
        for n in active:
            targets.update(lay.get(n, ()))
        # left stick from keys, unit circle
        lx = ("LS_RIGHT" in targets) - ("LS_LEFT" in targets)
        ly = ("LS_UP" in targets) - ("LS_DOWN" in targets)
        m = math.hypot(lx, ly)
        if m:
            lx, ly = lx / m, ly / m
        if self.mode == "drive":
            # a key is all-or-nothing; ease the wheel over so A/D steer like a thumb, not a slam
            rate = (5.0 if lx and abs(lx) > abs(self.steer) or lx * self.steer < 0 else 9.0) * dt
            self.steer += max(-rate, min(rate, lx - self.steer))
            if lx and abs(self.steer) < 0.3:
                self.steer = math.copysign(0.3, lx)    # skip the game's dead middle at once
            lx = self.steer
        else:
            self.steer = 0.0
        # right stick from mouse velocity
        if a["invert_y"]:
            by = -by
        rx, ry = bx / 127.0, -by / 127.0
        if self.calib:
            rx = ry = 0.0
            for a0, a1, d in self.calib:
                if a0 <= now < a1:
                    rx = d
            if now > self.calib[-1][1] + 0.5:
                self.calib = None
        lt = 1.0 if "L2" in targets else 0.0
        rt = 1.0 if "R2" in targets else 0.0
        if self.macro:
            for a0, a1, b in self.macro:
                if a0 <= now < a1:
                    targets.add(b)
            if now > self.macro[-1][1]:
                self.macro = None
        pup = self.puppet
        if pup and time.time() < pup.get("until", 0):
            targets |= set(pup.get("buttons", ())) & (set(BTN) | set(SPECIAL) | {"DUP", "DDOWN", "DLEFT", "DRIGHT"})
            if lx == 0 and ly == 0:
                lx, ly = float(pup.get("lx", 0)), float(pup.get("ly", 0))
            if rx == 0 and ry == 0:
                rx, ry = float(pup.get("rx", 0)), float(pup.get("ry", 0))
            lt, rt = max(lt, float(pup.get("lt", 0))), max(rt, float(pup.get("rt", 0)))
        real = self.real.state
        if real:
            targets |= real["buttons"]
            # keyboard + mouse always win; the pad's sticks only count when they're idle
            # (a resting thumb or worn stick must never fight WASD or the mouse)
            # while keys + mouse are on, the pad's sticks are ignored entirely: a worn stick that
            # rests off-centre made the camera "move on its own" (11-20). Off = pad works as normal.
            if not self.live:
                if math.hypot(real["lx"], real["ly"]) > 0.15:
                    lx, ly = real["lx"], real["ly"]
                if math.hypot(real["rx"], real["ry"]) > 0.15:
                    rx, ry = real["rx"], real["ry"]
            lt, rt = max(lt, real["lt"]), max(rt, real["rt"])
        p = self.pad
        p.reset()
        for t in targets:
            if t in BTN:
                p.press_button(BTN[t])
            elif t in SPECIAL:
                p.press_special_button(SPECIAL[t])
        if lt > 0.08:      # a real trigger resting slightly pressed must not aim or fire
            p.press_button(DS4B.DS4_BUTTON_TRIGGER_LEFT); p.left_trigger_float(lt)
        if rt > 0.08:
            p.press_button(DS4B.DS4_BUTTON_TRIGGER_RIGHT); p.right_trigger_float(rt)
        hx = ("DRIGHT" in targets) - ("DLEFT" in targets)
        hy = ("DUP" in targets) - ("DDOWN" in targets)
        p.directional_pad(DPAD_DIR[(hx, hy)])
        p.left_joystick_float(lx, -ly)    # DS4: positive y = down
        p.right_joystick_float(rx, -ry)
        p.update()
        self.ls, self.rs = (lx, ly), (rx, ry)
        out = set(targets)
        if lt > 0.08: out.add("L2")
        if rt > 0.08: out.add("R2")
        for name, on in (("LS_UP", ly > 0.3), ("LS_DOWN", ly < -0.3), ("LS_LEFT", lx < -0.3), ("LS_RIGHT", lx > 0.3)):
            if on: out.add(name)
        self.out = frozenset(out)


# ---------------------------------------------------------------- input thread
def input_thread(eng, ready):
    hinst = k32.GetModuleHandleW(None)
    WM_KEYDOWN, WM_SYSKEYDOWN = 0x100, 0x104
    mouse_names = {0x201: ("LMB", 1), 0x202: ("LMB", 0), 0x204: ("RMB", 1), 0x205: ("RMB", 0),
                   0x207: ("MMB", 1), 0x208: ("MMB", 0)}

    def kb_proc(n, w, l):
        if n == 0:
            ev = ctypes.cast(l, ctypes.POINTER(KBD)).contents
            if not (ev.flags & 0x10):  # ignore injected keys
                if eng.on_key(ev.vk, w in (WM_KEYDOWN, WM_SYSKEYDOWN), bool(ev.flags & 0x20)):
                    return 1
        return u32.CallNextHookEx(None, n, w, l)

    def ms_proc(n, w, l):
        if n == 0 and w != 0x200:
            ev = ctypes.cast(l, ctypes.POINTER(MSLL)).contents
            if w in mouse_names:
                name, down = mouse_names[w]
                if eng.on_mouse(name, down):
                    return 1
            elif w in (0x20B, 0x20C):
                xb = "Mouse4" if (ev.data >> 16) == 1 else "Mouse5"
                if eng.on_mouse(xb, w == 0x20B):
                    return 1
            elif w == 0x20A:
                delta = ctypes.c_short(ev.data >> 16).value
                if eng.on_mouse("WheelUp" if delta > 0 else "WheelDown", True):
                    return 1
        return u32.CallNextHookEx(None, n, w, l)

    buf = ctypes.create_string_buffer(64)

    def wnd_proc(h, msg, w, l):
        if msg == 0x00FF:  # WM_INPUT
            size = wt.UINT(64)
            if u32.GetRawInputData(l, 0x10000003, buf, ctypes.byref(size), 24) > 0:
                if struct.unpack_from("<I", buf, 0)[0] == 0:
                    flags, _, _, lx, ly = struct.unpack_from("<HxxIIii", buf, 24)
                    if not (flags & 1):
                        eng.on_raw(lx, ly)
        return u32.DefWindowProcW(h, msg, w, l)

    kb_cb, ms_cb, wp_cb = HOOKPROC(kb_proc), HOOKPROC(ms_proc), WNDPROC(wnd_proc)
    wc = WNDCLASSEXW(cbSize=ctypes.sizeof(WNDCLASSEXW), lpfnWndProc=wp_cb, hInstance=hinst,
                     lpszClassName="RewireRaw")
    u32.RegisterClassExW(ctypes.byref(wc))
    hwnd = u32.CreateWindowExW(0, "RewireRaw", "rewire", 0, 0, 0, 0, 0, None, None, hinst, None)
    rid = RAWINPUTDEVICE(1, 2, 0x100, hwnd)  # mouse, RIDEV_INPUTSINK
    u32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))
    h1 = u32.SetWindowsHookExW(13, kb_cb, hinst, 0)
    h2 = u32.SetWindowsHookExW(14, ms_cb, hinst, 0)
    ready.append(k32.GetCurrentThreadId())
    msg = wt.MSG()
    while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        u32.TranslateMessage(ctypes.byref(msg)); u32.DispatchMessageW(ctypes.byref(msg))
    u32.UnhookWindowsHookEx(h1); u32.UnhookWindowsHookEx(h2)


# ---------------------------------------------------------------- UI
BG, PANEL, KEY, KEYHI, EDGE = "#09090b", "#111115", "#17171c", "#26262e", "#202027"
FG, DIM, MUTE, ACC, OK = "#f4f2ec", "#8a877f", "#4a4842", "#ff5a36", "#3ddc84"
FONT = "Segoe UI"
U = 58   # key unit in px

# PlayStation's own symbol colours carry through every key.
SYM = {"CROSS": "#7fa7ff", "CIRCLE": "#ff6b6b", "SQUARE": "#f08fd6", "TRIANGLE": "#3fdcb0"}
GROUP = {"L1": "#c9b8ff", "R1": "#c9b8ff", "L2": "#ffb86b", "R2": "#ffb86b", "L3": "#e8e4d8",
         "R3": "#e8e4d8", "DUP": "#9fd36b", "DDOWN": "#9fd36b", "DLEFT": "#9fd36b", "DRIGHT": "#9fd36b",
         "LS_UP": FG, "LS_DOWN": FG, "LS_LEFT": FG, "LS_RIGHT": FG, "OPTIONS": "#b8b4aa",
         "TOUCHPAD": "#b8b4aa", "SHARE": "#b8b4aa", "PS": "#b8b4aa", "MODE": "#6fa8ff"}
COLOR = {**GROUP, **SYM}
PS_NAME = {"CROSS": "✕ Cross", "CIRCLE": "○ Circle", "SQUARE": "□ Square", "TRIANGLE": "△ Triangle",
           "L1": "L1", "R1": "R1", "L2": "L2", "R2": "R2", "L3": "L3 · left stick click",
           "R3": "R3 · right stick click", "OPTIONS": "Options", "SHARE": "Create", "TOUCHPAD": "Touchpad",
           "PS": "PS button", "DUP": "D-pad ↑", "DDOWN": "D-pad ↓", "DLEFT": "D-pad ←", "DRIGHT": "D-pad →",
           "LS_UP": "Left stick ↑", "LS_DOWN": "Left stick ↓", "LS_LEFT": "Left stick ←",
           "LS_RIGHT": "Left stick →", "MODE": "Switch layout"}

# What each PS button does in GTA 6 (default scheme): (short, long)
ACTIONS = {
    "foot": {
        "LS_UP": ("Forward", "Walk forward"), "LS_DOWN": ("Back", "Walk back"),
        "LS_LEFT": ("Left", "Strafe left"), "LS_RIGHT": ("Right", "Strafe right"),
        "CROSS": ("Jump", "Jump · climb · vault"), "CIRCLE": ("Crouch", "Crouch · hold to rest"),
        "SQUARE": ("Melee", "Melee attack"), "TRIANGLE": ("Interact", "Interact · enter a vehicle"),
        "L1": ("Weapons", "Holster · hold for the weapon and item menu"),
        "R1": ("Cover", "Take cover · quick throw while aiming"),
        "L2": ("Aim", "Aim · interact"), "R2": ("Shoot", "Shoot"),
        "L3": ("Run", "Run · press again to sprint"),
        "R3": ("Look back", "Look behind · zoom or throw path while aiming"),
        "TOUCHPAD": ("Map", "Open the map"), "OPTIONS": ("Pause", "Pause menu"),
        "DUP": ("Phone", "Phone · zoom scope in while aiming"),
        "DDOWN": ("Minimap", "Objectives and minimap · zoom scope out while aiming"),
        "DLEFT": ("Radio", "Radio · switch shoulder while aiming"),
        "DRIGHT": ("Detonate", "Detonate · hold for partner menu / switch character"),
        "PS": ("PS menu", "PlayStation button"), "SHARE": ("Capture", "Create · screenshot or clip"),
        "MODE": ("Switch", "Switch between the on-foot and driving layouts"),
    },
    "drive": {
        "LS_LEFT": ("Steer L", "Steer left"), "LS_RIGHT": ("Steer R", "Steer right"),
        "LS_UP": ("Lean fwd", "Lean forward (bikes)"), "LS_DOWN": ("Lean back", "Lean back (bikes)"),
        "R2": ("Gas", "Accelerate"), "L2": ("Brake", "Brake · reverse"),
        "CROSS": ("Handbrake", "Handbrake"), "TRIANGLE": ("Get out", "Exit the vehicle"),
        "CIRCLE": ("Lights", "Headlights"), "SQUARE": ("Melee", "Melee from the vehicle"),
        "L3": ("Horn", "Horn · nitrous"), "R3": ("Look back", "Look behind"),
        "R1": ("Shoot", "Drive-by shooting"), "L1": ("Weapons", "Holster · weapon menu"),
        "TOUCHPAD": ("Map", "Open the map"), "OPTIONS": ("Pause", "Pause menu"),
        "DUP": ("Phone", "Phone"), "DDOWN": ("Minimap", "Objectives and minimap"),
        "DLEFT": ("Blinker L", "Left indicator · hold for the radio"),
        "DRIGHT": ("Blinker R", "Right indicator"),
        "PS": ("PS menu", "PlayStation button"), "SHARE": ("Capture", "Create · screenshot or clip"),
        "MODE": ("Switch", "Switch between the driving and on-foot layouts"),
    },
}

ROWS = [
    [("Esc", 1), None, ("F1", 1), ("F2", 1), ("F3", 1), ("F4", 1), ("F5", 1), ("F6", 1), None, ("F10", 1)],
    [("1", 1), ("2", 1), ("3", 1), ("4", 1), ("5", 1), ("6", 1), ("7", 1), ("8", 1), ("9", 1), ("0", 1),
     ("Backspace", 1.6)],
    [("Tab", 1.5), ("Q", 1), ("W", 1), ("E", 1), ("R", 1), ("T", 1), ("Y", 1), ("U", 1), ("I", 1),
     ("O", 1), ("P", 1)],
    [("CapsLock", 1.8), ("A", 1), ("S", 1), ("D", 1), ("F", 1), ("G", 1), ("H", 1), ("J", 1), ("K", 1),
     ("L", 1), ("Enter", 1.9)],
    [("LShift", 2.3), ("Z", 1), ("X", 1), ("C", 1), ("V", 1), ("B", 1), ("N", 1), ("M", 1)],
    [("LCtrl", 1.5), ("LAlt", 1.3), ("Space", 5.2)],
]
SHORT = {"Backspace": "Bksp", "CapsLock": "Caps", "LShift": "Shift", "LCtrl": "Ctrl", "LAlt": "Alt",
         "Mouse4": "Side 1", "Mouse5": "Side 2", "WheelUp": "Wheel up", "WheelDown": "Wheel down",
         "LMB": "Left click", "RMB": "Right click", "MMB": "Middle click"}
MENU_ORDER = ["CROSS", "CIRCLE", "SQUARE", "TRIANGLE", "L1", "R1", "L2", "R2", "L3", "R3",
              "DUP", "DDOWN", "DLEFT", "DRIGHT", "LS_UP", "LS_DOWN", "LS_LEFT", "LS_RIGHT",
              "OPTIONS", "TOUCHPAD", "SHARE", "PS"]


def describe(mode, targets):
    """-> (short action, long action, ps label, colour) for a key's targets."""
    main = [t for t in targets if t != "MODE"]
    if not targets:
        return "", "Not bound", "", MUTE
    if not main:
        s, l = ACTIONS[mode]["MODE"]
        return s, l, PS_NAME["MODE"], COLOR["MODE"]
    t = main[0]
    s, l = ACTIONS[mode].get(t, (PS_NAME[t], PS_NAME[t]))
    if "MODE" in targets:
        if t == "TRIANGLE":
            s, l = ("Get in", "Enter a vehicle · switches to the driving layout") if mode == "foot" else \
                   ("Get out", "Exit the vehicle · switches to the on-foot layout")
        else:
            l += " · also switches layout"
    return s, l, PS_NAME[t], COLOR.get(t, FG)


def rrect(c, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
           x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, splinesteps=12, **kw)


class Slider:
    """Thin custom slider: label, track, accent fill, knob, value."""

    def __init__(self, parent, label, lo, hi, res, value, on_change):
        self.label, self.lo, self.hi, self.res = label, lo, hi, res
        self.value, self.on_change = value, on_change
        self.c = tk.Canvas(parent, bg=BG, highlightthickness=0, height=46 * Slider.app.s, cursor="hand2")
        self.c.bind("<Configure>", lambda e: self.draw())
        self.c.bind("<Button-1>", self.drag)
        self.c.bind("<B1-Motion>", self.drag)

    def drag(self, e):
        z = Slider.app.s
        w = max(self.c.winfo_width() - 60 * z, 10)
        f = min(1.0, max(0.0, (e.x - 8 * z) / w))
        v = self.lo + f * (self.hi - self.lo)
        v = round(round(v / self.res) * self.res, 3)
        if v != self.value:
            self.value = v
            self.draw()
            self.on_change()

    def draw(self):
        c = self.c
        c.delete("all")
        z = Slider.app.s
        c.config(height=46 * z)
        w = max(c.winfo_width() - 60 * z, 10)
        f = (self.value - self.lo) / (self.hi - self.lo)
        y = 32 * z
        c.create_text(0, 9 * z, text=self.label, fill=MUTE, font=Slider.app.font(8), anchor="w")
        c.create_line(8 * z, y, 8 * z + w, y, fill=KEY, width=max(2, 4 * z), capstyle="round")
        c.create_line(8 * z, y, 8 * z + w * f, y, fill=ACC, width=max(2, 4 * z), capstyle="round")
        x = 8 * z + w * f
        c.create_oval(x - 7 * z, y - 7 * z, x + 7 * z, y + 7 * z, fill=FG, outline="")
        c.create_text(c.winfo_width() - 2, y, text=f"{self.value:g}", fill=DIM, font=Slider.app.font(10),
                      anchor="e")


class App:
    def __init__(self, eng):
        self.eng = eng
        r = self.root = tk.Tk()
        r.title("Rewire")
        r.configure(bg=BG)
        r.resizable(True, True)
        r.minsize(760, 620)
        self.place_window()
        self.s = 1.0               # window scale vs the design size
        Slider.app = self
        self.u = self.REF_U
        self._fonts = {}
        self._redraw_job = None
        self.view = "foot"
        self.follow = True
        self.hover = None
        self.last_press = None
        self.prev_down = set()

        st = self.stage = tk.Frame(r, bg=BG, width=self.REF_W, height=self.REF_H)
        st.pack_propagate(False)
        st.place(relx=0.5, rely=0.5, anchor="center")
        top = tk.Frame(st, bg=BG); top.pack(fill="x", padx=28, pady=(22, 0))
        self.state = tk.Label(top, text="", bg=BG, fg=FG, font=self.font(34), anchor="w")
        self.state.pack(side="left")
        right = tk.Frame(top, bg=BG); right.pack(side="right")
        self.tab_btns = {}
        for m, label in (("foot", "ON FOOT"), ("drive", "DRIVING")):
            b = tk.Label(right, text=label, bg=BG, fg=DIM, font=self.font(11), padx=16, pady=8,
                         cursor="hand2")
            b.pack(side="left", padx=(6, 0))
            b.bind("<Button-1>", lambda e, m=m: self.pick_tab(m))
            self.tab_btns[m] = b
        self.sub = tk.Label(st, text="", bg=BG, fg=DIM, font=self.font(10, False), anchor="w")
        self.sub.pack(fill="x", padx=30)
        self.padline = tk.Label(st, text="", bg=BG, fg=MUTE, font=self.font(10, False), anchor="w")
        self.padline.pack(fill="x", padx=30, pady=(2, 14))

        self.kb = tk.Canvas(st, bg=BG, highlightthickness=0, width=int(U * 15.4 + 8), height=int(self.REF_U * 6.4 + 8))
        self.kb.pack(padx=28, fill="x")
        r.bind("<Configure>", self.on_resize)
        self.kb.bind("<Configure>", self.center)     # re-centre once the canvas has its new width
        self.keys = {}
        self.draw_keyboard()

        # inspector: what the key under the mouse (or the last key pressed) does
        self.editing = None
        self.panel_name = None
        self.ip = tk.Canvas(st, bg=PANEL, highlightthickness=0, height=300)
        self.ip.pack(fill="x", padx=28, pady=(16, 0))
        self.ip.bind("<Configure>", lambda e: self.paint_panel())
        r.bind("<Escape>", lambda e: self.stop_edit())

        bottom = tk.Frame(st, bg=BG); bottom.pack(fill="x", padx=28, pady=(16, 22))
        self.bottom = bottom
        sl = tk.Frame(bottom, bg=BG); sl.pack(side="left", fill="x", expand=True)
        a = eng.cfg["aim"]
        self.sliders = {}
        self.last_mode = None
        for i, (key, label, lo, hi, res) in enumerate((
                ("sensitivity", "AIM SPEED", 0.2, 4.0, 0.05),
                ("anti_deadzone", "GAME DEADZONE  ·  MEASURED 0.34", 0.0, 0.45, 0.01),
                ("curve", "CURVE  ·  1 = STRAIGHT, HIGHER = FINER SMALL MOVES", 0.4, 2.0, 0.05),
                ("window_ms", "PS5 GAME FRAME MS  ·  16 = 60 FPS  ·  VEYRA FRAME GEN DOESN'T COUNT", 4.0, 40.0, 1.0))):
            sl.columnconfigure(i % 2, weight=1)
            w = Slider(sl, label, lo, hi, res, a[key], lambda k=key: self.set_aim(k))
            w.c.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 26), pady=(0, 6))
            self.sliders[key] = w
        foot = tk.Frame(sl, bg=BG); foot.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.inv = tk.BooleanVar(value=a["invert_y"])
        tk.Checkbutton(foot, text="Invert Y", variable=self.inv, command=lambda: self.set_aim("invert_y"),
                       bg=BG, fg=DIM, selectcolor=BG, activebackground=BG, activeforeground=FG,
                       font=self.font(9, False)).pack(side="left")
        reset = tk.Label(foot, text="Reset this layout", bg=BG, fg=MUTE, font=self.font(9, False), cursor="hand2")
        reset.pack(side="right", padx=(0, 18))
        reset.bind("<Button-1>", lambda e: self.reset_layout())

        self.pads = [(top, 28, (22, 0)), (self.sub, 30, 0), (self.padline, 30, (2, 14)), (self.kb, 28, 0),
                     (self.ip, 28, (16, 0)), (bottom, 28, (16, 22))]
        r.protocol("WM_DELETE_WINDOW", self.quit)
        self.show("foot")
        self.inspect(None)
        self.refresh()

    # -- keyboard
    # -- window placement: never on the main (gaming) monitor by default
    def place_window(self):
        mons = monitors()
        saved = self.eng.cfg.get("window")
        if isinstance(saved, list) and len(saved) == 4:
            x, y, w, h = (int(v) for v in saved)
            if any(l <= x + 40 < r and t <= y + 20 < b for (l, t, r, b), _ in mons):
                self.root.geometry(f"{w}x{h}+{x}+{y}")
                return
        side = [m for m in mons if not m[1]]
        pick = min(side, key=lambda m: (m[0][2] - m[0][0]) * (m[0][3] - m[0][1])) if side else \
            (mons[0] if mons else None)
        if pick:
            l, t, r, b = pick[0]
            w, h = min(1300, r - l - 60), min(980, b - t - 60)
            self.root.geometry(f"{w}x{h}+{l + 30}+{t + 30}")

    def save_window(self):
        try:
            self.root.update_idletasks()
            self.eng.cfg["window"] = [self.root.winfo_x(), self.root.winfo_y(),
                                      self.root.winfo_width(), self.root.winfo_height()]
            save_cfg(self.eng.cfg)
        except Exception:
            pass

    KB_ROWS = 6.4   # keyboard height in key units (mouse column is the tallest part)

    REF_W, REF_H, REF_U = 1300, 1050, 66   # the design: window size and keyboard key size

    def on_resize(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        if self._redraw_job:
            self.root.after_cancel(self._redraw_job)
        self._redraw_job = self.root.after(40, self.relayout)

    def relayout(self):
        self._redraw_job = None
        r = self.root
        z = max(0.4, min(r.winfo_width() / self.REF_W, r.winfo_height() / self.REF_H))
        if abs(z - self.s) < 0.004 and self.keys:
            return
        self.s = z
        for (size, bold), f in self._fonts.items():
            f.configure(size=max(4, round(size * z)))
        self.stage.config(width=round(self.REF_W * z), height=round(self.REF_H * z))
        for w, px, py in self.pads:
            sc = lambda v: tuple(round(i * z) for i in v) if isinstance(v, tuple) else round(v * z)
            w.pack_configure(padx=sc(px), pady=sc(py))
        for b in self.tab_btns.values():
            b.config(padx=round(16 * z), pady=round(8 * z))
        self.ip.config(height=300 * z)
        for sl in self.sliders.values():
            sl.draw()
        self.redraw()
        self.paint_panel()

    def redraw(self):
        self.kb.delete("all")
        self.keys = {}
        z = self.s
        self.kb.config(height=int((self.u * self.KB_ROWS + 8) * z))
        self.draw_keyboard()          # drawn at design size...
        self.kb.scale("all", 0, 0, z, z)   # ...then scaled
        self.center()
        self.prev_down = set()
        self.show(self.view, self.follow)

    def center(self, event=None):
        box = self.kb.bbox("all")
        if box:
            dx = (self.kb.winfo_width() - (box[2] - box[0])) / 2 - box[0]
            if abs(dx) > 1:
                self.kb.move("all", dx, 0)

    def font(self, size, bold=True):
        """Font at design size `size`, shown at size * scale. One object per size: when the window
        is resized every text using it resizes with it."""
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(family=FONT, size=max(4, round(size * self.s)),
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    def fit(self, text, width, start):
        for size in range(start, 6, -1):
            if self.font(size).measure(text) <= width:
                return self.font(size)
        return self.font(6)

    def draw_keyboard(self):
        U = self.u
        g = max(5, int(U * 0.12))
        y = 4
        for row in ROWS:
            x = 4
            for item in row:
                if item is None:
                    x += U * 0.4
                    continue
                name, w = item
                self._key(name, x, y, U * w - g, U - g)
                x += U * w
            y += U
        ax, ay = 4 + U * 9.5, 4 + U * 4
        self._key("Up", ax + U, ay, U - g, U - g)
        for i, n in enumerate(("Left", "Down", "Right")):
            self._key(n, ax + U * i, ay + U, U - g, U - g)
        mx, mw, mh = 4 + U * 12.75, U * 2.6, U * 0.74
        self.kb.create_text(mx + 2, 4 + U * 0.3, text="MOUSE", fill=MUTE, font=self.font(8), anchor="w")
        for i, n in enumerate(MOUSE_INPUTS):
            self._key(n, mx, 4 + U * 0.62 + i * (mh + g * 0.6), mw, mh)

    def _key(self, name, x, y, w, h, row=False):
        c = self.kb
        reserved = name in RESERVED
        body = rrect(c, x, y, x + w, y + h, 9, fill=BG if reserved else KEY,
                     outline=EDGE if reserved else "", width=1)
        bar = c.create_line(x + 10, y + h - 4, x + w - 10, y + h - 4, fill=KEY, width=3, capstyle="round")
        cap = SHORT.get(name, name)
        if row:
            c.create_text(x + 12, y + h / 2, text=cap, fill=DIM, font=self.font(9, False), anchor="w")
            act = c.create_text(x + w - 40, y + h / 2, text="", fill=FG, font=self.font(10), anchor="e")
            sym = c.create_text(x + w - 12, y + h / 2, text="", fill=FG, font=self.font(10), anchor="e")
        else:
            c.create_text(x + 8, y + 6, text=cap, fill=MUTE, font=self.font(7), anchor="nw")
            act = c.create_text(x + 8, y + h * 0.62, text="", fill=FG, font=self.font(9), anchor="w")
            sym = c.create_text(x + w - 8, y + 6, text="", fill=FG, font=self.font(8), anchor="ne")
        act2 = c.create_text(x + 8, y + h * 0.80, text="", fill=DIM, font=self.font(9), anchor="w")
        if reserved:
            c.create_text(x + 8, y + h / 2 + 2, anchor="w", fill=MUTE, font=self.font(8, False),
                          text="on / off" if name == "F10" else "Alt+Tab")
        else:
            for item in (body, bar, act, act2, sym):
                c.tag_bind(item, "<Button-1>", lambda e, n=name: self.edit(n, e))
                c.tag_bind(item, "<Enter>", lambda e, n=name: self.on_hover(n))
                c.tag_bind(item, "<Leave>", lambda e, n=name: self.on_hover(None, n))
        self.keys[name] = {"body": body, "bar": bar, "act": act, "act2": act2, "sym": sym,
                           "reserved": reserved, "w": w, "x": x, "y": y, "h": h}

    def show(self, mode, follow=True):
        """Every key shows both jobs at once: on foot above, driving below. The layout that is
        live right now is bright, the other one dim. `mode` is only which one a click edits."""
        self.view, self.follow = mode, follow
        live = self.eng.mode
        for m, b in self.tab_btns.items():
            on = m == live
            b.config(fg=BG if on else DIM, bg=(OK if self.eng.live else FG) if on else BG)
        lays = self.eng.cfg["layouts"]
        start = 12
        for name, k in self.keys.items():
            if k["reserved"]:
                continue
            tf, td = lays["foot"].get(name, []), lays["drive"].get(name, [])
            sf, sd = describe("foot", tf)[0], describe("drive", td)[0]
            t = tf if live == "foot" else td
            col = describe(live, t)[3]
            main = [x for x in t if x != "MODE"]
            glyph = TARGETS[main[0]] if main else ("⇄" if t else "")
            if main and main[0].startswith("LS_"):
                glyph = ""
            x, y, x1, y1 = self.kb.bbox(k["body"])   # where the key is now (scaled and re-centred)
            z = self.s
            h, w = y1 - y, k["w"] * z
            side = not (h > self.u * 0.8 * z or w < 200 * z)   # short wide mouse rows: text beside the name
            tx = x + (92 if side else 8) * z
            if side:
                w -= 110 * z                   # ...and clear of the button badge on the right
            if sf == sd:                       # same job either way: one line
                self.kb.coords(k["act"], tx, y + h * (0.45 if side else 0.62))
                self.kb.itemconfig(k["act"], text=sf, fill=FG if t else MUTE, font=self.fit(sf, w - 14 * z, start))
                self.kb.itemconfig(k["act2"], text="")
            else:
                small = max(7, start - 2)
                top, bot = (sf or "–"), (sd or "–")
                self.kb.coords(k["act"], tx, y + h * (0.30 if side else 0.47))
                self.kb.coords(k["act2"], tx, y + h * (0.66 if side else 0.74))
                self.kb.itemconfig(k["act"], text=top, font=self.fit(top, w - 14 * z, start if live == "foot" else small),
                                   fill=(FG if tf else MUTE) if live == "foot" else DIM)
                self.kb.itemconfig(k["act2"], text=bot, font=self.fit(bot, w - 14 * z, start if live == "drive" else small),
                                   fill=(FG if td else MUTE) if live == "drive" else DIM)
            self.kb.itemconfig(k["sym"], text=glyph, fill=col)
            self.kb.itemconfig(k["bar"], fill=col if t else BG)
            k["base"] = KEY if (tf or td) else BG
            sel = name == self.editing
            self.kb.itemconfig(k["body"], fill=KEYHI if sel or name in self.prev_down else k["base"],
                               outline=FG if sel else ("" if (tf or td) else EDGE), width=2 if sel else 1)
        self.inspect(self.hover)

    def pick_tab(self, m):
        with self.eng.lock:
            self.eng.mode = m
        self.show(m)

    def pick_edit(self, m):
        self.show(m, follow=False)

    def on_hover(self, name, leaving=None):
        if name is None and leaving != self.hover:
            return
        self.hover = name
        self.inspect(name)

    def inspect(self, name):
        self.panel_name = name
        self.paint_panel()

    def paint_panel(self):
        c = self.ip
        c.delete("all")
        z = self.s
        W = max(c.winfo_width() / z, 600)       # design units
        self.pad_items = {}
        if self.editing:
            self.paint_picker(W)
        elif not self.panel_name:
            self.paint_pad(W)
        else:
            self.paint_text(W)
        c.scale("all", 0, 0, z, z)
        if self.pad_items:
            self.update_pad()

    def paint_text(self, W):
        c, name = self.ip, self.panel_name
        c.create_text(26, 26, text=SHORT.get(name, name).upper(), fill=DIM, font=self.font(9), anchor="w")
        half = (W - 52) / 2
        for i, (m, where) in enumerate((("foot", "ON FOOT"), ("drive", "DRIVING"))):
            t = self.eng.cfg["layouts"][m].get(name, [])
            short, long, ps, col = describe(m, t)
            on = m == self.eng.mode
            x = 26 + i * half
            c.create_text(x, 52, text=where + ("   ·   NOW" if on else ""), fill=OK if on else MUTE,
                          font=self.font(9), anchor="w")
            c.create_text(x - 2, 92, text=short or "Nothing", fill=(FG if on else DIM) if t else MUTE,
                          font=self.fit(short or "Nothing", (half - 30) * self.s, 28), anchor="w")
            c.create_text(x, 128, text=long, fill=DIM, font=self.font(10, False), anchor="w")
            if t:
                c.create_text(x, 150, text=ps, fill=col, font=self.font(9), anchor="w")
        c.config(height=300 * self.s)      # same height as the controller: hovering doesn't jump the window

    # (target, shape, x, y, w, h, label side) — x from the centre, in a 640 x 250 box
    PAD = [
        ("L2", "rect", -215, 18, 92, 20, "w"), ("L1", "rect", -215, 44, 92, 16, "w"),
        ("R2", "rect", 215, 18, 92, 20, "e"), ("R1", "rect", 215, 44, 92, 16, "e"),
        ("SHARE", "pill", -120, 78, 20, 30, "n"), ("OPTIONS", "pill", 120, 78, 20, 30, "n"),
        ("TOUCHPAD", "rect", 0, 92, 170, 64, "c"),
        ("DUP", "rect", -205, 102, 24, 26, "w"), ("DDOWN", "rect", -205, 158, 24, 26, "w"),
        ("DLEFT", "rect", -233, 130, 26, 24, "w"), ("DRIGHT", "rect", -177, 130, 26, 24, "e"),
        ("TRIANGLE", "circle", 205, 100, 30, 30, "e"), ("CROSS", "circle", 205, 160, 30, 30, "e"),
        ("SQUARE", "circle", 175, 130, 30, 30, "w"), ("CIRCLE", "circle", 235, 130, 30, 30, "e"),
        ("L3", "circle", -105, 190, 50, 50, "s"), ("R3", "circle", 105, 190, 50, 50, "s"),
        ("PS", "circle", 0, 185, 22, 22, "s"),
    ]
    GLYPH = {"CROSS": "✕", "CIRCLE": "○", "SQUARE": "□", "TRIANGLE": "△", "DUP": "▲", "DDOWN": "▼",
             "DLEFT": "◀", "DRIGHT": "▶", "TOUCHPAD": "", "SHARE": "", "OPTIONS": "", "PS": "PS"}

    def keys_for(self, target):
        lay = self.eng.cfg["layouts"][self.eng.mode]
        ks = [SHORT.get(k, k) for k, v in lay.items() if target in v]
        return " / ".join(ks[:2]) + (" …" if len(ks) > 2 else "")

    def paint_pad(self, W):
        """The PS5 controller. The game says "press L3"? Find L3 here: it names your key."""
        c = self.ip
        H = 300
        c.config(height=H * self.s)
        mode = self.eng.mode
        c.create_text(26, H - 44, text="GAME SAYS A BUTTON?", fill=DIM, font=self.font(9), anchor="w")
        c.create_text(26, H - 26, text=("ON FOOT" if mode == "foot" else "DRIVING") + " keys shown",
                      fill=MUTE, font=self.font(9, False), anchor="w")
        cx, top = W / 2, 22
        # body: two grips joined by the middle
        body = [cx - 250, top + 64, cx - 140, top + 52, cx + 140, top + 52, cx + 250, top + 64,
                cx + 292, top + 175, cx + 300, top + 245, cx + 250, top + 258, cx + 200, top + 220,
                cx + 135, top + 218, cx - 135, top + 218, cx - 200, top + 220, cx - 250, top + 258,
                cx - 300, top + 245, cx - 292, top + 175]
        c.create_polygon(body, smooth=True, splinesteps=16, fill="#15151a", outline=EDGE, width=1)
        f_lab, f_glyph = self.font(9), self.font(10)
        for t, shape, x, y, w, h, side in self.PAD:
            x0, y0 = cx + x - w / 2, top + y - h / 2
            col = COLOR.get(t, FG)
            if shape == "circle":
                body_id = c.create_oval(x0, y0, x0 + w, y0 + h, fill=KEY, outline=EDGE)
            else:
                body_id = rrect(c, x0, y0, x0 + w, y0 + h, min(9, h / 2), fill=KEY, outline=EDGE)
            g = self.GLYPH.get(t, t)
            gl = c.create_text(cx + x, top + y, text=g, fill=col, font=f_glyph) if g else None
            key = self.keys_for(t)
            act = ACTIONS[mode].get(t, ("",))[0]
            lab = f"{key}  ·  {act}" if key and act else (key or "")
            lx, ly, anc = {"w": (x0 - 8, top + y, "e"), "e": (x0 + w + 8, top + y, "w"),
                           "n": (cx + x, y0 - 8, "s"), "s": (cx + x, y0 + h + (24 if t in ("L3", "R3") else 8), "n"),
                           "c": (cx + x, top + y, "c")}[side]
            if t in ("L1", "L2", "R1", "R2"):
                lx = x0 - 10 if side == "w" else x0 + w + 10
            label = c.create_text(lx, ly, text=lab or "—", fill=FG if key else MUTE,
                                  font=f_lab if key else self.font(8, False), anchor=anc)
            if t in ("L1", "L2", "R1", "R2", "TOUCHPAD", "SHARE", "OPTIONS", "L3", "R3"):
                name = {"TOUCHPAD": "touchpad", "SHARE": "create", "OPTIONS": "options"}.get(t, t)
                c.create_text(cx + x, top + y + (0 if t != "TOUCHPAD" else -20), text=name, fill=MUTE,
                              font=self.font(7))
            self.pad_items[t] = (body_id, gl, label, col)
        # left stick's four directions, around L3
        sx, sy = cx - 105, top + 190
        for t, dx, dy, anc in (("LS_UP", 0, -30, "s"), ("LS_DOWN", 0, 30, "n"), ("LS_LEFT", -32, 0, "e"), ("LS_RIGHT", 32, 0, "w")):
            key = self.keys_for(t)
            if key:
                txt = c.create_text(sx + dx, sy + dy, text=key, fill=DIM, font=self.font(8), anchor=anc)
                self.pad_items[t] = (None, None, txt, ACC)
        c.create_text(cx + 105, top + 160, text="mouse", fill=MUTE, font=self.font(8), anchor="s")
        self.pad_dots = (c.create_oval(0, 0, 0, 0, fill=ACC, outline=""), c.create_oval(0, 0, 0, 0, fill=ACC, outline=""))
        self.pad_lit = None
        self.pad_box = (cx, top)

    def update_pad(self):
        items = getattr(self, "pad_items", None)
        if not items:
            return
        e, c, z = self.eng, self.ip, self.s
        cx, top = self.pad_box
        for dot, (x, y), (px, py) in zip(self.pad_dots, (e.ls, e.rs), ((cx - 105, top + 190), (cx + 105, top + 190))):
            px, py = (px + x * 16) * z, (py - y * 16) * z
            c.coords(dot, px - 5 * z, py - 5 * z, px + 5 * z, py + 5 * z)
        lit = e.out
        if lit == self.pad_lit:
            return
        for t, (body_id, gl, label, col) in items.items():
            on = t in lit
            was = self.pad_lit is not None and t in self.pad_lit
            if self.pad_lit is not None and on == was:
                continue
            if body_id is not None:
                c.itemconfig(body_id, fill=col if on else KEY)
                if gl is not None:
                    c.itemconfig(gl, fill=BG if on else col)
            elif label is not None:
                c.itemconfig(label, fill=ACC if on else DIM)
        self.pad_lit = lit

    def paint_picker(self, W):
        c = self.ip
        name, mode = self.editing, self.view
        cur = self.eng.cfg["layouts"][mode].get(name, [])
        where = "ON FOOT" if mode == "foot" else "DRIVING"
        c.create_text(26, 28, text=f"{SHORT.get(name, name).upper()}  DOES …", fill=FG,
                      font=self.font(13), anchor="w")
        px = 26 + self.font(13).measure(f"{SHORT.get(name, name).upper()}  DOES …") / self.s + 18
        for m, lab in (("foot", "ON FOOT"), ("drive", "WHEN DRIVING")):
            on = m == mode
            pw = self.font(9).measure(lab) / self.s + 24
            b = rrect(c, px, 15, px + pw, 41, 13, fill=FG if on else PANEL, outline="" if on else EDGE)
            tx = c.create_text(px + pw / 2, 28, text=lab, fill=BG if on else DIM, font=self.font(9))
            for it in (b, tx):
                c.tag_bind(it, "<Button-1>", lambda e, m=m: self.pick_edit(m))
            px += pw + 8
        cols = max(4, int((W - 40 + 10) // 158))
        cw, ch, gap = (W - 40 - (cols - 1) * 10) / cols, 50, 10
        y0 = 52
        for i, t in enumerate(MENU_ORDER):
            x = 20 + (i % cols) * (cw + gap)
            y = y0 + (i // cols) * (ch + gap)
            on = t in cur
            col = COLOR.get(t, FG)
            body = rrect(c, x, y, x + cw, y + ch, 9, fill=KEYHI if on else KEY,
                         outline=col if on else "", width=2)
            act = ACTIONS[mode].get(t, (PS_NAME[t],))[0]
            a1 = c.create_text(x + 14, y + 18, text=act, fill=FG, font=self.font(11), anchor="w")
            a2 = c.create_text(x + 14, y + 36, text=PS_NAME[t], fill=col, font=self.font(8), anchor="w")
            for it in (body, a1, a2):
                c.tag_bind(it, "<Button-1>", lambda e, t=t: self.assign(name, t))
                c.tag_bind(it, "<Enter>", lambda e: c.config(cursor="hand2"))
                c.tag_bind(it, "<Leave>", lambda e: c.config(cursor=""))
        rows = -(-len(MENU_ORDER) // cols)
        y = y0 + rows * (ch + gap) + 6

        def pill(x, label, cmd, fill, fg, anchor_right=False):
            f = self.font(10)
            w = f.measure(label) / self.s + 32
            x0 = x - w if anchor_right else x
            b = rrect(c, x0, y, x0 + w, y + 36, 18, fill=fill, outline=EDGE if fill == PANEL else "")
            tx = c.create_text(x0 + w / 2, y + 18, text=label, fill=fg, font=f)
            for it in (b, tx):
                c.tag_bind(it, "<Button-1>", lambda e: cmd())
                c.tag_bind(it, "<Enter>", lambda e: c.config(cursor="hand2"))
                c.tag_bind(it, "<Leave>", lambda e: c.config(cursor=""))
            return w

        sw = "MODE" in cur
        x = 20
        x += pill(x, ("⇄  Also switches layout: ON" if sw else "⇄  Also switches layout: off"),
                  lambda: self.toggle_mode_flag(name), COLOR["MODE"] if sw else PANEL,
                  BG if sw else DIM) + 10
        pill(x, "Clear", lambda: self.assign(name, None), PANEL, DIM)
        pill(W - 20, "Done", self.stop_edit, FG, BG, anchor_right=True)
        c.config(height=max(300, y + 56) * self.s)

    # -- editing
    def edit(self, name, event=None):
        self.editing = None if self.editing == name else name
        self.sync_bottom()
        self.show(self.view, self.follow)

    def sync_bottom(self):
        # the picker takes the sliders' space while it's open
        if self.editing:
            self.bottom.pack_forget()
        elif not self.bottom.winfo_ismapped():
            self.bottom.pack(fill="x", padx=28, pady=(16, 22))

    def stop_edit(self):
        if self.editing:
            self.editing = None
            self.sync_bottom()
            self.show(self.eng.mode)

    def _save_layout(self):
        save_cfg(self.eng.cfg)
        with self.eng.lock:
            self.eng.rebuild_maps()
        self.show(self.view, self.follow)

    def assign(self, name, target):
        lay = self.eng.cfg["layouts"][self.view]
        keep_mode = "MODE" in lay.get(name, [])
        new = ([target] if target else []) + (["MODE"] if keep_mode and target else [])
        if new:
            lay[name] = new
        else:
            lay.pop(name, None)
        self._save_layout()

    def toggle_mode_flag(self, name):
        lay = self.eng.cfg["layouts"][self.view]
        had = "MODE" in lay.get(name, [])
        cur = [t for t in lay.get(name, []) if t != "MODE"] + ([] if had else ["MODE"])
        if cur:
            lay[name] = cur
        else:
            lay.pop(name, None)
        self._save_layout()

    def reset_layout(self):
        base = FOOT if self.view == "foot" else DRIVE
        self.eng.cfg["layouts"][self.view] = json.loads(json.dumps(base))
        self._save_layout()

    def set_aim(self, key):
        a = self.eng.cfg["aim"]
        a[key] = bool(self.inv.get()) if key == "invert_y" else round(self.sliders[key].value, 3)
        save_cfg(self.eng.cfg)

    # -- live refresh
    def refresh(self):
        e = self.eng
        tk_ = e.cfg["toggle_key"]
        if e.live:
            self.state.config(text="LIVE", fg=OK)
            self.sub.config(text=f"Keys and mouse are driving the PS5.   {tk_} or Alt+Tab to stop.   "
                                 + ("Driving layout turns on by itself when you get in.  Caps Lock if it ever misses." if e.eyes else
                                    "F and Caps Lock switch on foot / driving."))
        elif e.armed:
            self.state.config(text="ARMED", fg=ACC)
            self.sub.config(text="Click into Veyra's window to go live.")
        else:
            self.state.config(text="OFF", fg=MUTE)
            msg = f"Press {tk_} with Veyra in front to start."
            if e.error:
                msg = "Stopped after an error (see errors.log).   " + msg
            self.sub.config(text=msg)
        if e.real.name:
            hid = "  ·  hidden from other apps, so Veyra uses Rewire" if e.hider and e.hider.active else \
                "  ·  install HidHide so Veyra stops grabbing it directly"
            self.padline.config(text=f"🎮  {e.real.name} works alongside keys + mouse{hid}", fg=SYM["TRIANGLE"])
        else:
            self.padline.config(text="🎮  No controller plugged in. Plug one in any time and it just works.",
                                fg=MUTE)
        if (e.mode, e.live) != self.last_mode:
            self.last_mode = (e.mode, e.live)
            self.show(self.view if self.editing else e.mode)
        held = set(e.down)
        new = held - self.prev_down
        if new:
            self.last_press = sorted(new)[0]
        for name in held ^ self.prev_down:
            k = self.keys.get(name)
            if k and not k["reserved"]:
                self.kb.itemconfig(k["body"], fill=KEYHI if name in held or name == self.editing
                                   else k.get("base", KEY))
        self.prev_down = held
        self.update_pad()
        self.root.after(33, self.refresh)

    def quit(self):
        self.save_window()
        self.eng.running = False
        self.root.after(80, self.root.destroy)


def main():
    eng = Engine(load_cfg())
    eng.hider = Hider()
    eng.hider.start()
    eng.real.start()

    def rescan():
        while eng.running:
            time.sleep(3)
            if eng.hider.active:
                eng.hider.scan()   # hide controllers plugged in later
    threading.Thread(target=rescan, daemon=True).start()
    ready = []
    threading.Thread(target=input_thread, args=(eng, ready), daemon=True).start()
    out = threading.Thread(target=eng.loop, daemon=True)
    out.start()
    threading.Thread(target=eng.watch_card, daemon=True).start()
    threading.Thread(target=eng.watch_puppet, daemon=True).start()
    if eng.cfg.get("auto_switch"):   # off: the picture-watcher guessed wrong too often (walking on a road = "driving")
        threading.Thread(target=eng.watch, daemon=True).start()
    app = App(eng)
    try:
        app.root.mainloop()
    finally:
        eng.running = False
        out.join(timeout=1)
        if eng.eyes_proc:
            eng.eyes_proc.kill()
        eng.hider.stop()          # give the real controller back to every app
        if ready:
            u32.PostThreadMessageW(ready[0], 0x12, 0, 0)


if __name__ == "__main__":
    main()
