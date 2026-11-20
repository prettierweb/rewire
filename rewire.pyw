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
    "aim": {"sensitivity": 1.0, "anti_deadzone": 0.22, "curve": 0.8,
            "window_ms": 16.0, "invert_y": False},
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
class Aim:
    """Mouse counts -> right stick, losing nothing.

    The console reads the stick only once per game frame, so a stick that follows the
    mouse's instant speed drops or doubles motion between reads. Here every count is
    spread evenly over one frame-length window, and a running tally ("debt") of counts
    received minus counts the stick has actually delivered (after the 8-bit rounding,
    the deadzone and the full-tilt limit) is fed back in, so the turn always adds up
    to the hand movement.
    """
    CATCHUP = 0.030     # s to work off the tally
    MAX_LAG = 0.050     # most over-run kept after a flick faster than full tilt, in s of full tilt
    IDLE = 0.060        # mouse still this long past the window: drop what's left, no creep

    def __init__(self):
        self.ev = []            # (t, dx, dy) inside the window
        self.debt_x = self.debt_y = 0.0
        self.last = 0.0

    def reset(self):
        self.ev.clear()
        self.debt_x = self.debt_y = 0.0

    def feed(self, t, dx, dy):
        self.ev.append((t, dx, dy))
        self.debt_x += dx
        self.debt_y += dy
        self.last = t

    def step(self, now, dt, a):
        """Returns the stick as two bytes offsets (-127..127), x right, y down (mouse sense)."""
        win = min(max(a["window_ms"], 2.0), 60.0) / 1000.0
        ev = self.ev
        i = 0
        while i < len(ev) and now - ev[i][0] >= win:
            i += 1
        if i:
            del ev[:i]
        if not ev and now - self.last > win + self.IDLE:
            self.debt_x = self.debt_y = 0.0
            return 0, 0
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
        cap = full * self.MAX_LAG
        e = math.hypot(ex, ey)
        if e > cap:
            self.debt_x -= ex * (1 - cap / e); self.debt_y -= ey * (1 - cap / e)
            ex *= cap / e; ey *= cap / e
        tx, ty = vx + ex / self.CATCHUP, vy + ey / self.CATCHUP
        speed = math.hypot(tx, ty)
        if speed <= 0:
            return 0, 0
        out = adz + (1 - adz) * min(1.0, speed / full) ** curve
        bx, by = round(tx / speed * out * 127), round(ty / speed * out * 127)
        # what those two bytes really deliver, by the same curve read backwards
        m = math.hypot(bx, by) / 127.0
        if m > adz:
            got = full * min(1.0, (m - adz) / (1 - adz)) ** (1.0 / curve) * dt / (m * 127.0)
            self.debt_x -= bx * got; self.debt_y -= by * got
        else:
            bx = by = 0     # inside the game's deadzone it does nothing: wait and send a real step
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
                    if "MODE" in self.layout().get(name, ()):
                        self.flip_mode()
                self.wake.set()
                return True
            if name in self.down:
                self.down.discard(name)
                self.wake.set()
                return True
        return False

    def on_key(self, vk, down, alt):
        if vk == self.toggle_vk:
            if not (self.armed or self.veyra_front):
                return False          # F10 belongs to other apps when we're idle
            if down and not self.toggle_down:
                self.armed = not self.armed
            self.toggle_down = down
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
        lt = 1.0 if "L2" in targets else 0.0
        rt = 1.0 if "R2" in targets else 0.0
        real = self.real.state
        if real:
            targets |= real["buttons"]
            # keyboard + mouse always win; the pad's sticks only count when they're idle
            # (a resting thumb or worn stick must never fight WASD or the mouse)
            if lx == 0 and ly == 0 and math.hypot(real["lx"], real["ly"]) > 0.15:
                lx, ly = real["lx"], real["ly"]
            if rx == 0 and ry == 0 and math.hypot(real["rx"], real["ry"]) > 0.15:
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
        self.c = tk.Canvas(parent, bg=BG, highlightthickness=0, height=46, cursor="hand2")
        self.c.bind("<Configure>", lambda e: self.draw())
        self.c.bind("<Button-1>", self.drag)
        self.c.bind("<B1-Motion>", self.drag)

    def drag(self, e):
        w = max(self.c.winfo_width() - 60, 10)
        f = min(1.0, max(0.0, (e.x - 8) / w))
        v = self.lo + f * (self.hi - self.lo)
        v = round(round(v / self.res) * self.res, 3)
        if v != self.value:
            self.value = v
            self.draw()
            self.on_change()

    def draw(self):
        c = self.c
        c.delete("all")
        w = max(c.winfo_width() - 60, 10)
        f = (self.value - self.lo) / (self.hi - self.lo)
        y = 32
        c.create_text(0, 9, text=self.label, fill=MUTE, font=(FONT, 8, "bold"), anchor="w")
        c.create_line(8, y, 8 + w, y, fill=KEY, width=4, capstyle="round")
        c.create_line(8, y, 8 + w * f, y, fill=ACC, width=4, capstyle="round")
        x = 8 + w * f
        c.create_oval(x - 7, y - 7, x + 7, y + 7, fill=FG, outline="")
        c.create_text(c.winfo_width() - 2, y, text=f"{self.value:g}", fill=DIM, font=(FONT, 10, "bold"),
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
        self.u = U
        self._fonts = {}
        self._redraw_job = None
        self.view = "foot"
        self.follow = True
        self.hover = None
        self.last_press = None
        self.prev_down = set()

        top = tk.Frame(r, bg=BG); top.pack(fill="x", padx=28, pady=(22, 0))
        self.state = tk.Label(top, text="", bg=BG, fg=FG, font=(FONT, 34, "bold"), anchor="w")
        self.state.pack(side="left")
        right = tk.Frame(top, bg=BG); right.pack(side="right")
        self.tab_btns = {}
        for m, label in (("foot", "ON FOOT"), ("drive", "DRIVING")):
            b = tk.Label(right, text=label, bg=BG, fg=DIM, font=(FONT, 11, "bold"), padx=16, pady=8,
                         cursor="hand2")
            b.pack(side="left", padx=(6, 0))
            b.bind("<Button-1>", lambda e, m=m: self.pick_tab(m))
            self.tab_btns[m] = b
        self.sub = tk.Label(r, text="", bg=BG, fg=DIM, font=(FONT, 10), anchor="w")
        self.sub.pack(fill="x", padx=30)
        self.padline = tk.Label(r, text="", bg=BG, fg=MUTE, font=(FONT, 10), anchor="w")
        self.padline.pack(fill="x", padx=30, pady=(2, 14))

        self.kb = tk.Canvas(r, bg=BG, highlightthickness=0, width=int(U * 15.4 + 8), height=int(U * 6.4 + 8))
        self.kb.pack(padx=28, fill="x")
        r.bind("<Configure>", self.on_resize)
        self.keys = {}
        self.draw_keyboard()

        # inspector: what the key under the mouse (or the last key pressed) does
        self.editing = None
        self.panel_name = None
        self.ip = tk.Canvas(r, bg=PANEL, highlightthickness=0, height=170)
        self.ip.pack(fill="x", padx=28, pady=(16, 0))
        self.ip.bind("<Configure>", lambda e: self.paint_panel())
        r.bind("<Escape>", lambda e: self.stop_edit())

        bottom = tk.Frame(r, bg=BG); bottom.pack(fill="x", padx=28, pady=(16, 22))
        self.bottom = bottom
        self.cv = tk.Canvas(bottom, width=232, height=110, bg=BG, highlightthickness=0)
        self.cv.pack(side="left")
        self.sticks = []
        for i, label in enumerate(("MOVE", "AIM")):
            x0 = 4 + i * 120
            self.cv.create_oval(x0, 4, x0 + 102, 106, outline=EDGE, width=2)
            self.cv.create_text(x0 + 51, 55, text=label, fill=MUTE, font=(FONT, 8, "bold"))
            dot = self.cv.create_oval(0, 0, 0, 0, fill=ACC, outline="")
            self.sticks.append((x0 + 51, 55, dot))
        sl = tk.Frame(bottom, bg=BG); sl.pack(side="left", fill="x", expand=True, padx=(28, 0))
        a = eng.cfg["aim"]
        self.sliders = {}
        self.last_mode = None
        for i, (key, label, lo, hi, res) in enumerate((
                ("sensitivity", "AIM SPEED", 0.2, 4.0, 0.05),
                ("anti_deadzone", "ANTI-DEADZONE", 0.0, 0.45, 0.01),
                ("curve", "CURVE  ·  LOWER = FINER SMALL MOVES", 0.4, 2.0, 0.05),
                ("window_ms", "GAME FRAME MS  ·  16 = 60 FPS, 33 = 30 FPS", 4.0, 40.0, 1.0))):
            sl.columnconfigure(i % 2, weight=1)
            w = Slider(sl, label, lo, hi, res, a[key], lambda k=key: self.set_aim(k))
            w.c.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 26), pady=(0, 6))
            self.sliders[key] = w
        foot = tk.Frame(sl, bg=BG); foot.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.inv = tk.BooleanVar(value=a["invert_y"])
        tk.Checkbutton(foot, text="Invert Y", variable=self.inv, command=lambda: self.set_aim("invert_y"),
                       bg=BG, fg=DIM, selectcolor=BG, activebackground=BG, activeforeground=FG,
                       font=(FONT, 9)).pack(side="left")
        reset = tk.Label(foot, text="Reset this layout", bg=BG, fg=MUTE, font=(FONT, 9), cursor="hand2")
        reset.pack(side="right", padx=(0, 18))
        reset.bind("<Button-1>", lambda e: self.reset_layout())

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

    def on_resize(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        if self._redraw_job:
            self.root.after_cancel(self._redraw_job)
        self._redraw_job = self.root.after(50, self.relayout)

    def relayout(self):
        self._redraw_job = None
        r = self.root
        other = r.winfo_reqheight() - self.kb.winfo_reqheight()   # everything that is not the keyboard
        by_w = (r.winfo_width() - 56 - 8) / 15.4
        by_h = (r.winfo_height() - other - 8) / self.KB_ROWS
        u = max(34.0, min(96.0, by_w, by_h))
        if abs(u - self.u) < 1.5:
            self.center()
            return
        self.u = u
        self.redraw()

    def redraw(self):
        self.kb.delete("all")
        self.keys = {}
        self.kb.config(height=int(self.u * self.KB_ROWS + 8))
        self.draw_keyboard()
        self.center()
        self.prev_down = set()
        self.show(self.view, self.follow)

    def center(self):
        box = self.kb.bbox("all")
        if box:
            dx = (self.kb.winfo_width() - (box[2] - box[0])) / 2 - box[0]
            if abs(dx) > 1:
                self.kb.move("all", dx, 0)

    def font(self, size, bold=True):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(family=FONT, size=size, weight="bold" if bold else "normal")
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
        self.kb.create_text(mx + 2, 4 + U * 0.3, text="MOUSE", fill=MUTE, font=(FONT, 8, "bold"), anchor="w")
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
            c.create_text(x + 12, y + h / 2, text=cap, fill=DIM, font=(FONT, 9), anchor="w")
            act = c.create_text(x + w - 40, y + h / 2, text="", fill=FG, font=(FONT, 10, "bold"), anchor="e")
            sym = c.create_text(x + w - 12, y + h / 2, text="", fill=FG, font=(FONT, 10, "bold"), anchor="e")
        else:
            c.create_text(x + 8, y + 6, text=cap, fill=MUTE, font=(FONT, 7, "bold"), anchor="nw")
            act = c.create_text(x + 8, y + h * 0.62, text="", fill=FG, font=(FONT, 9, "bold"), anchor="w")
            sym = c.create_text(x + w - 8, y + 6, text="", fill=FG, font=(FONT, 8, "bold"), anchor="ne")
        act2 = c.create_text(x + 8, y + h * 0.80, text="", fill=DIM, font=(FONT, 9, "bold"), anchor="w")
        if reserved:
            c.create_text(x + 8, y + h / 2 + 2, anchor="w", fill=MUTE, font=(FONT, 8),
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
        start = max(8, min(13, int(self.u / 5.6)))
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
            x, y, x1, y1 = self.kb.bbox(k["body"])   # where the key is now (the board gets re-centred)
            h, w = y1 - y, k["w"]
            tx = x + (8 if h > self.u * 0.8 else 92)   # short wide mouse rows: text beside the name
            if sf == sd:                       # same job either way: one line
                self.kb.coords(k["act"], tx, y + h * (0.62 if tx == x + 8 else 0.45))
                self.kb.itemconfig(k["act"], text=sf, fill=FG if t else MUTE, font=self.fit(sf, w - 14, start))
                self.kb.itemconfig(k["act2"], text="")
            else:
                small = max(7, start - 2)
                top, bot = (sf or "–"), (sd or "–")
                self.kb.coords(k["act"], tx, y + h * (0.47 if tx == x + 8 else 0.30))
                self.kb.coords(k["act2"], tx, y + h * (0.74 if tx == x + 8 else 0.66))
                self.kb.itemconfig(k["act"], text=top, font=self.fit(top, w - 14, start if live == "foot" else small),
                                   fill=(FG if tf else MUTE) if live == "foot" else DIM)
                self.kb.itemconfig(k["act2"], text=bot, font=self.fit(bot, w - 14, start if live == "drive" else small),
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
        self.inspect(name or self.last_press)

    def inspect(self, name):
        self.panel_name = name
        self.paint_panel()

    def paint_panel(self):
        c = self.ip
        c.delete("all")
        W = max(c.winfo_width(), 600)
        if self.editing:
            self.paint_picker(W)
            return
        name = self.panel_name
        if not name:
            c.create_text(26, 30, text="HOVER A KEY", fill=MUTE, font=(FONT, 9, "bold"), anchor="w")
            c.create_text(24, 82, text="What does it do?", fill=MUTE, font=(FONT, 30, "bold"), anchor="w")
            c.create_text(26, 132, text="Point at any key to see its GTA action.  Click a key to rebind it.",
                          fill=DIM, font=(FONT, 11), anchor="w")
            c.config(height=170)
            return
        c.create_text(26, 26, text=SHORT.get(name, name).upper(), fill=DIM, font=(FONT, 9, "bold"), anchor="w")
        half = (W - 52) / 2
        for i, (m, where) in enumerate((("foot", "ON FOOT"), ("drive", "DRIVING"))):
            t = self.eng.cfg["layouts"][m].get(name, [])
            short, long, ps, col = describe(m, t)
            on = m == self.eng.mode
            x = 26 + i * half
            c.create_text(x, 52, text=where + ("   ·   NOW" if on else ""), fill=OK if on else MUTE,
                          font=(FONT, 9, "bold"), anchor="w")
            c.create_text(x - 2, 92, text=short or "Nothing", fill=(FG if on else DIM) if t else MUTE,
                          font=self.fit(short or "Nothing", half - 30, 28), anchor="w")
            c.create_text(x, 128, text=long, fill=DIM, font=(FONT, 10), anchor="w")
            if t:
                c.create_text(x, 150, text=ps, fill=col, font=(FONT, 9, "bold"), anchor="w")
        c.config(height=170)

    def paint_picker(self, W):
        c = self.ip
        name, mode = self.editing, self.view
        cur = self.eng.cfg["layouts"][mode].get(name, [])
        where = "ON FOOT" if mode == "foot" else "DRIVING"
        c.create_text(26, 28, text=f"{SHORT.get(name, name).upper()}  DOES …", fill=FG,
                      font=(FONT, 13, "bold"), anchor="w")
        px = 26 + self.font(13).measure(f"{SHORT.get(name, name).upper()}  DOES …") + 18
        for m, lab in (("foot", "ON FOOT"), ("drive", "WHEN DRIVING")):
            on = m == mode
            pw = self.font(9).measure(lab) + 24
            b = rrect(c, px, 15, px + pw, 41, 13, fill=FG if on else PANEL, outline="" if on else EDGE)
            tx = c.create_text(px + pw / 2, 28, text=lab, fill=BG if on else DIM, font=(FONT, 9, "bold"))
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
            a1 = c.create_text(x + 14, y + 18, text=act, fill=FG, font=(FONT, 11, "bold"), anchor="w")
            a2 = c.create_text(x + 14, y + 36, text=PS_NAME[t], fill=col, font=(FONT, 8, "bold"), anchor="w")
            for it in (body, a1, a2):
                c.tag_bind(it, "<Button-1>", lambda e, t=t: self.assign(name, t))
                c.tag_bind(it, "<Enter>", lambda e: c.config(cursor="hand2"))
                c.tag_bind(it, "<Leave>", lambda e: c.config(cursor=""))
        rows = -(-len(MENU_ORDER) // cols)
        y = y0 + rows * (ch + gap) + 6

        def pill(x, label, cmd, fill, fg, anchor_right=False):
            f = self.font(10)
            w = f.measure(label) + 32
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
        c.config(height=y + 56)

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
                                 + ("On foot / driving switches by itself." if e.eyes else
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
            if self.hover is None:
                self.inspect(self.last_press)
        for name in held ^ self.prev_down:
            k = self.keys.get(name)
            if k and not k["reserved"]:
                self.kb.itemconfig(k["body"], fill=KEYHI if name in held or name == self.editing
                                   else k.get("base", KEY))
        self.prev_down = held
        for (cx, cy, dot), (x, y) in zip(self.sticks, (e.ls, e.rs)):
            px, py = cx + x * 44, cy - y * 44
            self.cv.coords(dot, px - 5, py - 5, px + 5, py + 5)
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
