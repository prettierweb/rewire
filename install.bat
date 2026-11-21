@echo off
rem Rewire one-click install: Python (if missing), the controller driver, packages, desktop shortcut.
cd /d "%~dp0"
echo.
echo  Rewire setup
echo  ------------

where python >nul 2>nul
if errorlevel 1 (
  echo  Installing Python 3.12 ...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo  Could not install Python. Get it from https://www.python.org/downloads/ ^(tick "Add to PATH"^), then run this again.
    pause & exit /b 1
  )
  echo  Python installed. Close this window and double-click install.bat again so Windows finds it.
  pause & exit /b 0
)

echo  Installing the virtual controller driver ^(ViGEmBus^) - say Yes to the admin prompt ...
winget install -e --id ViGEm.ViGEmBus --accept-package-agreements --accept-source-agreements >nul 2>nul

echo  Optional: HidHide lets your real controller work alongside keyboard + mouse.
choice /c YN /m "  Install HidHide too"
if errorlevel 2 goto packages
winget install -e --id Nefarius.HidHide --accept-package-agreements --accept-source-agreements

:packages
echo  Installing Python packages ...
python -m pip install --upgrade --quiet -r requirements.txt
if errorlevel 1 ( echo  pip failed, see above. & pause & exit /b 1 )

echo  Making a desktop shortcut ...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Rewire.lnk'); $s.TargetPath='%~dp0Rewire.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.Save()"

echo.
echo  Done. Open Rewire from the desktop. It asks once whether you play on PlayStation or Xbox.
echo  To remove: delete this folder and the desktop shortcut ^(ViGEmBus / HidHide uninstall from Windows Settings, Apps^).
pause
