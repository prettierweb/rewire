<p align="center">
  <img src="docs/banner.png" alt="Rewire: keyboard and mouse for PS5 Remote Play" width="100%">
</p>

<p align="center">
  <b>Play your PS5 or Xbox with a keyboard and mouse, from your PC, over Remote Play or cloud gaming.</b><br>
  No capture card, no adapter, no extra hardware.
</p>

<p align="center">⭐ if you like this, please star it, it really helps people find it ⭐</p>

<p align="center">
  <img alt="Windows" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0c0c0f?style=for-the-badge&logo=windows&logoColor=7fa7ff">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10+-0c0c0f?style=for-the-badge&logo=python&logoColor=3fdcb0">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-0c0c0f?style=for-the-badge&logoColor=f08fd6">
</p>

---

Rewire turns your keyboard and mouse into a virtual PlayStation or Xbox controller. Your Remote Play or
cloud gaming app picks it up like a normal pad and sends it to the console. You stay on your desktop the
whole time. It asks which console on first start.

**Install:** download the code, double-click `install.bat`, then open Rewire from the desktop.
**Have an AI assistant?** Point it at this repo and tell it to follow [SETUP-FOR-AI.md](SETUP-FOR-AI.md).

It ships with layouts modelled on GTA V's PC controls, mapped onto GTA 6's PS5 buttons: one layout
on foot, one for driving. It switches between them when you get in and out of a car.

## What it looks like

<p align="center"><img src="docs/overview.png" alt="Rewire: both layouts on the keyboard, controller map below" width="100%"></p>

**Plain words on every key.** Each key shows what it does in the layout you're looking at (on foot or
driving). "Jump", "Run", "Get in", not "Cross" or "L3". The colour bar
and corner symbol show the PS button underneath, in PlayStation's own colours: blue ✕, red ○, pink □,
green △.

**A controller map.** When the game says "press ○", look at the drawing under the keyboard: every PS
button is labelled with the key that presses it, and it lights up while you hold it.

**Scales properly.** Resize the window and the whole thing shrinks or grows together, text included.

<p align="center"><img src="docs/picker.png" alt="Rebinding picker" width="100%"></p>

**Rebinding takes one click.** Click a key, pick an action from the grid, done. Any key can also flip
between the on-foot and driving layouts, the way F does when you enter a car.

## Highlights

- **Controller and keyboard at the same time.** Plug your DualSense (or any pad) in and Rewire merges it
  into the same virtual controller, rumble included. Grab the pad for a cutscene, the mouse for a shootout,
  no switching or unplugging. [HidHide](https://github.com/nefarius/HidHide) hides the real pad from other
  apps while Rewire runs, so the Remote Play app only sees one controller, and gives it back when you close Rewire.
- **Mouse aim that feels like a mouse.** Raw mouse speed turns into stick tilt, glided so it's smooth,
  and it stops the moment your hand does. Three plain sliders: mouse speed, starting push, small moves.
  Under 2 ms of added delay. (A controller stick has a top turning speed set by the game; past it, a
  faster swipe can't turn faster.)
- **PlayStation or Xbox.** A virtual DualShock 4 for PS Remote Play, Veyra and Chiaki, or a virtual Xbox
  controller for the Xbox app and xbox.com/play. The whole screen switches to that console's buttons.
- **Special ability on V.** Both stick clicks at once, for games that put an ability there.
- **Two layouts, switched automatically.** Rewire watches the game picture for the vehicle-name card GTA
  shows when you get in a car or on a bike, and swaps WASD from walking to gas, brake and steering. Caps
  Lock swaps by hand (after a crash or a ragdoll out of the car).
- **Bikes work.** S brakes and reverses, Ctrl leans back for a wheelie (W + Ctrl), X leans forward.
- **Cursor out of the way.** While Rewire is live your cursor is hidden and locked, so it never shows
  over the game.
- **It never fights your PC.** Rewire only takes over while it's armed **and** your Remote Play window is
  in front. Alt+Tab away and every key goes back to normal and your cursor is freed. Alt+Tab and Alt+F4
  always work.
- **Nothing gets stuck.** A key is only held on the controller if Rewire saw you press it, so stray
  releases can't get stuck, and any error drops it to OFF and frees your cursor.
- **Resizable.** The whole keyboard scales with the window.

## How it works

```mermaid
flowchart LR
    A[Keyboard + mouse] -->|low-level hooks + raw input| B(Rewire)
    B -->|virtual DualShock 4<br/>via ViGEmBus| C[Remote Play app<br/>Veyra / chiaki-ng]
    C -->|Remote Play over your network| D[PS5]
```

Rewire never touches the console or the game. To the PS5 it is just a controller connected through
Remote Play.

## Setup

The quick way: run `install.bat` (it does all of this). By hand:

1. **Install [ViGEmBus](https://github.com/nefarius/ViGEmBus/releases)**, the virtual controller driver.
   It needs one admin prompt.
2. **Optional, to use your controller alongside keyboard + mouse:** install
   [HidHide](https://github.com/nefarius/HidHide/releases), then unplug and replug your controller once.
3. **Install Python 3.10+**, then:
   ```
   pip install -r requirements.txt
   ```
4. **Pair your PS5** with a Remote Play app. Rewire is built and tested against
   [Veyra](https://github.com/Likely7/Veyra-NRVideo). For another app, add its `.exe` name to
   `targets` in `config.json`.
5. Run `Rewire.bat`. It opens on your second monitor if you have one, and remembers where you put it. (or `pythonw rewire.pyw`).

## Playing

| | |
|---|---|
| **F10** | Arm / disarm. Rewire goes **LIVE** once your Remote Play window is in front |
| **Alt+Tab** | Leave. Everything is released and your cursor comes back |
| **Caps Lock** | Switch between the on-foot and driving layouts by hand (it also switches by itself) |
| **F7** | First-person trick, in the driver's seat: phone up, close it, then spam the touchpad (needs Touch Pad Button set to Camera in GTA's settings) |
| **V** | Special ability (both sticks clicked) |
| **Ctrl+F8 / Ctrl+F9** | Aim tests for tuning: stand still and keep your hands off for ~30 s. Results go to `calib.log` |
| **Ctrl+Alt+Del, then Esc** | Emergency: frees the cursor whatever happens |

> Without HidHide, unplug your real controller while you play: most Remote Play apps only listen to one pad.
> If Rewire ever crashes while hiding your controller, run `unhide.bat`.
>
> If your Remote Play app has its own shortcuts on Space, F or Tab (Veyra does), move them to
> Ctrl+key in its settings. Otherwise they fire while Rewire is off.

## Default GTA layout

| Key | On foot | Driving |
|---|---|---|
| WASD | Move | W gas · S brake · A/D steer |
| Mouse | Look and aim · L-click shoot · R-click aim | Look · L-click drive-by |
| Space | Jump / climb | Handbrake |
| Shift | Run, press again to sprint | Nitrous |
| Ctrl | Crouch | Lean back (wheelie) |
| X | | Lean forward |
| F | Get in | Get out |
| E | Interact | Horn |
| Q · Tab · C · R | Cover · weapons · look back · melee | Radio · weapons · look back · melee |
| H | | Headlights |
| M · P | Map · pause | Map · pause |
| Arrows | Phone · radio · objectives · detonate | Phone · blinkers · objectives |

All of it can be rebound in the app. Bindings and aim settings save to `config.json`.

**Best GTA 6 settings for mouse aim:** Look and Aim Acceleration 0, look and aim sensitivity at max,
Aim Assist off. Then set Rewire's aim speed to taste.

## Notes

- Built for **single-player**. Using a mouse against controller players online is unfair, and those games'
  rules may treat it like an adapter. Keep it to story mode.
- GTA 6's controls come from its in-game control screens as reported on launch day. If a default is off,
  click the key and fix it.
- Not affiliated with Sony, Rockstar or the Remote Play apps it works with.

## License

MIT
