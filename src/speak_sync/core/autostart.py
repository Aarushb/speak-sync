"""Cross-platform OS login autostart registration (Windows Registry, macOS LaunchAgent, Linux XDG)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "SpeakSync"


def get_launch_command() -> str:
    """Build the command line used to launch SpeakSync at OS login."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    exe = Path(sys.executable)
    if sys.platform == "win32" and exe.name.lower() == "python.exe":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            exe = pythonw
    return f'"{exe}" -m speak_sync'


def is_autostart_enabled() -> bool:
    """Return True if SpeakSync is currently registered to launch at user login."""
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                RUN_KEY_PATH,
                0,
                winreg.KEY_READ,
            ) as key:
                val, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
                return bool(val)
        except FileNotFoundError:
            return False
        except Exception as exc:
            logger.debug("Failed to query Windows Run registry key: %s", exc)
            return False

    if sys.platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.aarushb.speak_sync.plist"
        return plist.exists()

    xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    desktop_file = xdg_config / "autostart" / "speak-sync.desktop"
    return desktop_file.exists()


def set_autostart_enabled(enabled: bool) -> bool:
    """Enable or disable launching SpeakSync on OS login."""
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                RUN_KEY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                if enabled:
                    winreg.SetValueEx(
                        key,
                        RUN_VALUE_NAME,
                        0,
                        winreg.REG_SZ,
                        get_launch_command(),
                    )
                else:
                    try:
                        winreg.DeleteValue(key, RUN_VALUE_NAME)
                    except FileNotFoundError:
                        pass
            return True
        except Exception as exc:
            logger.warning("Failed to update Windows startup registry: %s", exc)
            return False

    if sys.platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.aarushb.speak_sync.plist"
        try:
            if enabled:
                plist.parent.mkdir(parents=True, exist_ok=True)
                plist.write_text(
                    f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.aarushb.speak_sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>-m</string>
        <string>speak_sync</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
""",
                    encoding="utf-8",
                )
            elif plist.exists():
                plist.unlink()
            return True
        except Exception as exc:
            logger.warning("Failed to update macOS LaunchAgent: %s", exc)
            return False

    xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    desktop_file = xdg_config / "autostart" / "speak-sync.desktop"
    try:
        if enabled:
            desktop_file.parent.mkdir(parents=True, exist_ok=True)
            desktop_file.write_text(
                f"""[Desktop Entry]
Type=Application
Name=SpeakSync
Comment=Accessible cloud sync tray monitor
Exec={get_launch_command()}
Terminal=false
""",
                encoding="utf-8",
            )
        elif desktop_file.exists():
            desktop_file.unlink()
        return True
    except Exception as exc:
        logger.warning("Failed to update Linux XDG autostart: %s", exc)
        return False
