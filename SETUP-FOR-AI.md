# Rewire setup, for an AI assistant

You are helping someone install Rewire, a Windows tool that turns keyboard + mouse into a virtual
PlayStation (DualShock 4) or Xbox (360) controller for Remote Play / cloud gaming apps. Follow these steps in
order and stop to ask the user only where it says ASK.

## 1. Check the machine

- Windows 10 or 11 only.
- `python --version` must be 3.10 or newer. If missing: `winget install -e --id Python.Python.3.12`,
  then open a new terminal so PATH updates.

## 2. Get the code

```
git clone https://github.com/prettierweb/rewire.git
cd rewire
```

## 3. Drivers (admin prompts the user must accept)

- Required: `winget install -e --id ViGEm.ViGEmBus` (virtual controller driver).
- Optional, ASK first: `winget install -e --id Nefarius.HidHide`. Only needed if they want to use their
  real controller at the same time as keyboard + mouse. After installing, they must unplug and replug the
  controller once.

## 4. Packages and shortcut

```
python -m pip install -r requirements.txt
```

Then make a desktop shortcut to `Rewire.bat` (or just run `install.bat`, which does steps 1, 3 and 4).

## 5. First run

- Run `Rewire.bat`. On first start it asks PlayStation or Xbox (saved in `config.json` as `console`).
- PlayStation: works with Veyra, Chiaki / chiaki-ng and Sony's PS Remote Play.
- Xbox: works with the Xbox app (cloud gaming and remote play) and xbox.com/play in Edge, Chrome,
  Firefox or Brave.
- Another app: add its `.exe` name (lower case) to `targets` in `config.json`.

## 6. Using it

- F10 turns it on. Click into the game window to start. Alt+Tab or F10 stops it.
- Rewire only acts while it is on AND the game app is the window in front, so it never touches other apps.
- Sliders: Mouse speed, Starting push (raise if tiny mouse moves do nothing), Small moves (lower = small
  moves turn more).

## Things not to do

- Don't change Windows settings, startup entries or file associations. Rewire needs none.
- If a controller ever stays hidden after a crash, run `unhide.bat`.
