from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32":
    import winreg
else:  # pragma: no cover
    winreg = None


RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "FocusDawn"


def _resolve_command(executable: str | None = None) -> str:
    exe = Path(executable or sys.executable)
    if getattr(sys, "frozen", False):  # pyinstaller/exe
        return f'"{exe}"'

    script = Path(__file__).resolve().with_name("main.py")
    return f'"{exe}" "{script}"'


def is_startup_enabled() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return True
    except FileNotFoundError:
        return False


def enable_startup(executable: str | None = None) -> None:
    if winreg is None:
        raise RuntimeError("Startup registration is only supported on Windows.")
    command = _resolve_command(executable)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
        winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, command)


def disable_startup() -> None:
    if winreg is None:
        raise RuntimeError("Startup registration is only supported on Windows.")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
    except FileNotFoundError:
        pass
