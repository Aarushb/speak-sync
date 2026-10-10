"""macOS menu bar extra backend using System Events AXExtrasMenuBar and local client telemetry."""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable

from speak_dropbox.backends.base import TrayBackend
from speak_dropbox.core.classifier import normalize_tooltip_text
from speak_dropbox.models import TrayIconItem, TrayLocation

logger = logging.getLogger(__name__)

_MACOS_AX_MENU_BAR_SCRIPT = """
tell application "System Events"
    set outputLines to {}
    set procList to every application process whose background only is true or visible is true
    repeat with proc in procList
        try
            set pName to name of proc
            if exists (menu bar 2 of proc) then
                set mbItems to every menu bar item of menu bar 2 of proc
                repeat with mbi in mbItems
                    set itemTitle to ""
                    set itemDesc to ""
                    set itemHelp to ""
                    try
                        set itemTitle to (name of mbi as text)
                    end try
                    try
                        set itemDesc to (description of mbi as text)
                    end try
                    try
                        set itemHelp to (help of mbi as text)
                    end try
                    set end of outputLines to pName & "|" & itemTitle & "|" & itemDesc & "|" & itemHelp
                end repeat
            end if
        end try
    end repeat
    set AppleScript's text item delimiters to linefeed
    return outputLines as text
end tell
""".strip()


def parse_macos_ax_menu_bar_lines(
    raw_output: str,
    *,
    strip_unread_notifications: bool = False,
) -> list[TrayIconItem]:
    """Parse pipe-delimited AXExtrasMenuBar output lines into TrayIconItem instances."""
    items: list[TrayIconItem] = []
    seen: set[str] = set()
    for line in raw_output.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        proc_name = parts[0] if parts else ""
        fields = [
            f
            for f in parts[1:]
            if f and f.lower() not in ("missing value", "text", "menu bar item")
        ]
        if not fields and proc_name:
            combined = proc_name
        elif fields:
            prefix = proc_name if proc_name and proc_name.lower() not in fields[0].lower() else ""
            body = " - ".join(dict.fromkeys(fields))
            combined = f"{prefix} - {body}" if prefix else body
        else:
            continue

        cleaned = normalize_tooltip_text(
            combined,
            strip_unread_notifications=strip_unread_notifications,
        )
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            items.append(
                TrayIconItem(
                    raw_tooltip=combined,
                    cleaned_tooltip=cleaned,
                    location=TrayLocation.VISIBLE,
                    process_name=proc_name,
                )
            )
    return items


class MacOSTrayBackend(TrayBackend):
    """Discovers macOS menu bar extra icons (NSStatusItem / AXMenuBarExtra) non-intrusively."""

    def __init__(self, *, command_runner: Callable[[list[str]], str] | None = None) -> None:
        self._runner = command_runner or self._default_run_cmd

    @property
    def platform_name(self) -> str:
        return "macOS AXExtrasMenuBar (Accessibility API)"

    @staticmethod
    def _default_run_cmd(cmd: list[str]) -> str:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=2.5,
                check=False,
            )
            return proc.stdout if proc.returncode == 0 else ""
        except Exception:
            return ""

    def get_tray_icons(self, *, strip_unread_notifications: bool = False) -> list[TrayIconItem]:
        out = self._runner(["osascript", "-e", _MACOS_AX_MENU_BAR_SCRIPT])
        if not out:
            return []
        return parse_macos_ax_menu_bar_lines(
            out,
            strip_unread_notifications=strip_unread_notifications,
        )
