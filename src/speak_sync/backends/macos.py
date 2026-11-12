"""macOS menu bar extra backend using System Events AXExtrasMenuBar and local client telemetry."""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable, Sequence

from speak_sync.backends.base import TrayBackend
from speak_sync.core.classifier import normalize_tooltip_text
from speak_sync.models import TrayIconItem, TrayLocation

logger = logging.getLogger(__name__)

DEFAULT_MACOS_TARGET_PROCESSES: tuple[str, ...] = (
    "Dropbox",
    "Google Drive",
    "OneDrive",
    "nextcloud",
    "Nextcloud",
    "Box",
    "Synology Drive",
    "Synology Drive Client",
    "pCloud Drive",
    "pCloud",
    "ownCloud",
    "Insync",
    "Resilio Sync",
)


def build_macos_menu_bar_script(
    target_processes: Sequence[str] = DEFAULT_MACOS_TARGET_PROCESSES,
) -> str:
    """Generate high-performance AppleScript querying specific status processes, SystemUIServer, and visible GUI apps.

    Avoids looping blindly over 100+ headless daemons (background only = true),
    reducing execution time from ~10 seconds to ~30-50 milliseconds.
    """
    clean_targets = [p.replace('"', '\\"') for p in target_processes if p.strip()]
    targets_formatted = "{" + ", ".join(f'"{p}"' for p in clean_targets) + "}"
    return f"""
tell application "System Events"
    set outputLines to {{}}
    set targetList to {targets_formatted}

    -- 1. Targeted O(1) checks for known/configured cloud sync processes
    repeat with t in targetList
        if exists (application process t) then
            try
                tell application process t
                    if exists (menu bar 2) then
                        set mbItems to every menu bar item of menu bar 2
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
                            set end of outputLines to (t as text) & "|" & itemTitle & "|" & itemDesc & "|" & itemHelp
                        end repeat
                    end if
                end tell
            end try
        end if
    end repeat

    -- 2. Query SystemUIServer for standard menu extras (menu bar 1)
    try
        tell application process "SystemUIServer"
            if exists menu bar 1 then
                set mbItems to every menu bar item of menu bar 1
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
                    set end of outputLines to "SystemUIServer|" & itemTitle & "|" & itemDesc & "|" & itemHelp
                end repeat
            end if
        end tell
    end try

    -- 3. Query visible GUI applications only (background only = false, typically 5-10 apps)
    try
        set visApps to (every application process whose background only is false)
        repeat with proc in visApps
            set pName to name of proc
            if pName is not in targetList and pName is not "SystemUIServer" then
                try
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
                            set end of outputLines to (pName as text) & "|" & itemTitle & "|" & itemDesc & "|" & itemHelp
                        end repeat
                    end if
                end try
            end if
        end repeat
    end try

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

    def __init__(
        self,
        *,
        command_runner: Callable[[list[str]], str] | None = None,
        candidate_processes: Sequence[str] | None = None,
    ) -> None:
        self._runner = command_runner or self._default_run_cmd
        self._candidate_processes = (
            tuple(dict.fromkeys((*DEFAULT_MACOS_TARGET_PROCESSES, *candidate_processes)))
            if candidate_processes
            else DEFAULT_MACOS_TARGET_PROCESSES
        )

    @property
    def platform_name(self) -> str:
        return "macOS AXExtrasMenuBar (Accessibility API)"

    @property
    def candidate_processes(self) -> tuple[str, ...]:
        return self._candidate_processes

    def update_candidate_processes(self, processes: Sequence[str]) -> None:
        """Dynamically add newly configured custom sources to targeted process scans."""
        self._candidate_processes = tuple(
            dict.fromkeys((*DEFAULT_MACOS_TARGET_PROCESSES, *processes))
        )

    @staticmethod
    def _default_run_cmd(cmd: list[str]) -> str:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            return proc.stdout if proc.returncode == 0 else ""
        except Exception as exc:
            logger.debug("macOS menu bar command failed: %s", exc)
            return ""

    def get_tray_icons(self, *, strip_unread_notifications: bool = False) -> list[TrayIconItem]:
        script = build_macos_menu_bar_script(self._candidate_processes)
        out = self._runner(["osascript", "-e", script])
        if not out:
            return []
        return parse_macos_ax_menu_bar_lines(
            out,
            strip_unread_notifications=strip_unread_notifications,
        )
