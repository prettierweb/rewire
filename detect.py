"""Rewire's eyes: looks at the Remote Play picture and says whether you're on foot or in a vehicle.

Runs as its own process so it can never slow the keys and mouse down. Prints one line per
look: "<drive|foot> <confidence 0..1>". Rewire reads those and switches layout by itself.
Needs torch + open_clip (pip install open_clip_torch). Without them Rewire just uses F / Caps Lock.

Test on saved pictures:  python detect.py a.png b.png
"""
import ctypes, ctypes.wintypes as wt, sys, time

DRIVE = ["a video game screenshot of a character riding a motorcycle",
         "a video game screenshot of a character riding a motorcycle on a road, seen from behind",
         "a video game screenshot of a car on a road, third person view from behind the car",
         "a video game screenshot from inside a car, first person driver's view of the dashboard",
         "a video game screenshot of a character riding a bicycle or a quad bike",
         "a video game screenshot of a boat being driven on water, seen from behind",
         "a video game screenshot of a truck or van driving, seen from behind"]
FOOT = ["a video game screenshot of a character walking on foot, seen from behind",
        "a video game screenshot of a character standing, seen from behind",
        "a video game screenshot of a character aiming a gun, over the shoulder view",
        "a video game screenshot of a person running on foot",
        "a video game screenshot of a character standing next to a parked car or motorcycle",
        "a video game screenshot of a character swimming",
        "a video game screenshot of the inside of a building with a character standing"]
OTHER = ["a video game cutscene with a close-up of people talking",
         "a video game pause menu or map screen",
         "a black loading screen",
         "a wide cinematic landscape shot with no character"]

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
k32 = ctypes.windll.kernel32
k32.OpenProcess.restype = wt.HANDLE; k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
k32.CloseHandle.argtypes = [wt.HANDLE]


def foreground(targets):
    """The Remote Play window, only while it is the one in front."""
    hwnd = u32.GetForegroundWindow()
    pid = wt.DWORD(); u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = k32.OpenProcess(0x1000, False, pid.value)
    if not h:
        return None
    buf = ctypes.create_unicode_buffer(520); n = wt.DWORD(520)
    ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
    k32.CloseHandle(h)
    return hwnd if ok and buf.value.rsplit("\\", 1)[-1].lower() in targets else None


def grab(hwnd):
    """The window's own picture (not what is on top of it), as a PIL image."""
    from PIL import Image
    r = wt.RECT(); u32.GetClientRect(hwnd, ctypes.byref(r))
    w, h = r.right, r.bottom
    if w <= 0 or h <= 0:
        return None
    dc = u32.GetDC(hwnd); mdc = gdi.CreateCompatibleDC(dc); bmp = gdi.CreateCompatibleBitmap(dc, w, h)
    old = gdi.SelectObject(mdc, bmp)
    ok = u32.PrintWindow(hwnd, mdc, 3)
    hdr = (ctypes.c_uint32 * 10)(40, w, (-h) & 0xFFFFFFFF, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi.GetDIBits(mdc, bmp, 0, h, buf, hdr, 0)
    gdi.SelectObject(mdc, old); gdi.DeleteObject(bmp); gdi.DeleteDC(mdc); u32.ReleaseDC(hwnd, dc)
    return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1) if ok else None


class Eyes:
    def __init__(self):
        import torch, open_clip
        torch.set_num_threads(2)            # leave the PC to the stream
        self.torch = torch
        self.model, _, self.pre = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
        self.model.eval()
        with torch.no_grad():
            t = self.model.encode_text(open_clip.get_tokenizer("ViT-B-32")(DRIVE + FOOT + OTHER))
            self.text = t / t.norm(dim=-1, keepdim=True)

    def look(self, im):
        """-> (drive, foot, other) shares that add to 1."""
        w, h = im.size
        im = im.crop((int(w * 0.18), int(h * 0.12), int(w * 0.82), int(h * 0.97)))  # the player, not the HUD
        with self.torch.no_grad():
            i = self.model.encode_image(self.pre(im).unsqueeze(0))
            p = (100 * (i / i.norm(dim=-1, keepdim=True)) @ self.text.T).softmax(-1)[0]
        d = p[:len(DRIVE)].sum().item(); f = p[len(DRIVE):len(DRIVE) + len(FOOT)].sum().item()
        return d, f, 1 - d - f


def main():
    from PIL import Image
    eyes = Eyes()
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        for p in sys.argv[1:]:
            d, f, o = eyes.look(Image.open(p).convert("RGB"))
            print(f"{p}\t{'drive' if d > f else 'foot'}\tdrive {d:.2f} foot {f:.2f} other {o:.2f}")
        return
    targets = [t.lower() for t in sys.argv[2:]] or ["veyra_qml_ui.exe"]
    print("ready", flush=True)
    import os
    keep = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "detect", "live")
    os.makedirs(keep, exist_ok=True)
    n = 0; next_keep = 0.0
    while True:
        t0 = time.perf_counter()
        hwnd = foreground(targets)
        im = grab(hwnd) if hwnd else None
        if im is not None:
            d, f, o = eyes.look(im)
            if t0 >= next_keep and n < 300:   # a small picture every 4 s, named by the verdict, to check it later
                next_keep = t0 + 4; n += 1
                im.resize((480, 270)).save(os.path.join(keep, f"{n:03d}_{'drive' if d > f else 'foot'}_d{d:.2f}_f{f:.2f}_o{o:.2f}.jpg"), quality=80)
            if o < 0.5:                      # menus, cutscenes, loading: say nothing, keep the layout
                print(f"{'drive' if d > f else 'foot'} {max(d, f) / (d + f):.2f}", flush=True)
        time.sleep(max(0.05, 0.3 - (time.perf_counter() - t0)))


if __name__ == "__main__":
    main()
