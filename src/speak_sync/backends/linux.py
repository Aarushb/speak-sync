"""Linux system tray backend using StatusNotifierWatcher D-Bus and Dropbox UNIX command socket."""

from __future__ import annotations

import logging
import re
import socket
import subprocess
from collections.abc import Callable
from pathlib import Path

from speak_dropbox.backends.base import TrayBackend
from speak_dropbox.core.classifier import normalize_tooltip_text
from speak_dropbox.models import TrayIconItem, TrayLocation

logger = logging.getLogger(__name__)

_SNI_ITEM_RE = re.compile(r"""['"]([^'"]+/[^'"]+)['"]""")
_GDBUS_STR_RE = re.compile(r"<'([^']*)'>")


def query_dropbox_command_socket(socket_path: Path | None = None, timeout: float = 1.0) -> str | None:
    """Query the local Linux Dropbox daemon command socket (~/.dropbox/command_socket)."""
    target = socket_path or (Path.home() / ".dropbox" / "command_socket")
    if not target.exists():
        return None
    af_unix = getattr(socket, "AF_UNIX", None)
    if af_unix is None:
        return None
    try:
        with socket.socket(af_unix, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(target))
            sock.sendall(b"get_dropbox_status\ndone\n")
            chunks: list[bytes] = []
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
                if b"done\n" in b"".join(chunks):
                    break
        text = b"".join(chunks).decode("utf-8", errors="replace")
        for line in text.splitlines():
            if line.startswith("status\t"):
                parts = [p.strip() for p in line.split("\t")[1:] if p.strip()]
                if parts:
                    return f"Dropbox - {' - '.join(parts)}"
                return "Dropbox - Idle"
    except Exception as exc:
        logger.debug("Dropbox command socket query failed: %s", exc)
    return None


def parse_sni_registered_items(raw_output: str) -> list[tuple[str, str]]:
    """Parse bus_name and object_path pairs from StatusNotifierWatcher.RegisteredStatusNotifierItems."""
    items: list[tuple[str, str]] = []
    for match in _SNI_ITEM_RE.finditer(raw_output):
        entry = match.group(1).strip()
        if "/" in entry:
            idx = entry.index("/")
            bus_name = entry[:idx]
            obj_path = entry[idx:]
            if bus_name and obj_path:
                items.append((bus_name, obj_path))
    return items


class LinuxTrayBackend(TrayBackend):
    """Discovers Linux system tray icons via Freedesktop/KDE StatusNotifierWatcher and local sockets."""

    def __init__(
        self,
        *,
        command_runner: Callable[[list[str]], str] | None = None,
        dropbox_socket_path: Path | None = None,
    ) -> None:
        self._runner = command_runner or self._default_run_cmd
        self._dropbox_socket_path = dropbox_socket_path

    @property
    def platform_name(self) -> str:
        return "Linux StatusNotifierItem (D-Bus) & Local Socket"

    @staticmethod
    def _default_run_cmd(cmd: list[str]) -> str:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            return proc.stdout if proc.returncode == 0 else ""
        except Exception:
            return ""

    def _query_sni_items(self, *, strip_unread_notifications: bool = False) -> list[TrayIconItem]:
        watcher_out = self._runner(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.kde.StatusNotifierWatcher",
                "--object-path",
                "/StatusNotifierWatcher",
                "--method",
                "org.freedesktop.DBus.Properties.Get",
                "org.kde.StatusNotifierWatcher",
                "RegisteredStatusNotifierItems",
            ]
        )
        if not watcher_out:
            return []

        results: list[TrayIconItem] = []
        for bus_name, obj_path in parse_sni_registered_items(watcher_out):
            props_out = self._runner(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    bus_name,
                    "--object-path",
                    obj_path,
                    "--method",
                    "org.freedesktop.DBus.Properties.GetAll",
                    "org.kde.StatusNotifierItem",
                ]
            )
            if not props_out:
                continue
            strings = [s.strip() for s in _GDBUS_STR_RE.findall(props_out) if s.strip()]
            if not strings:
                continue
            combined = " - ".join(dict.fromkeys(strings[:3]))
            cleaned = normalize_tooltip_text(
                combined,
                strip_unread_notifications=strip_unread_notifications,
            )
            if cleaned:
                results.append(
                    TrayIconItem(
                        raw_tooltip=combined,
                        cleaned_tooltip=cleaned,
                        location=TrayLocation.VISIBLE,
                        process_name=bus_name,
                    )
                )
        return results

    def get_tray_icons(self, *, strip_unread_notifications: bool = False) -> list[TrayIconItem]:
        icons = self._query_sni_items(strip_unread_notifications=strip_unread_notifications)
        has_dropbox = any("dropbox" in item.cleaned_tooltip.lower() for item in icons)
        if not has_dropbox:
            dbx_status = query_dropbox_command_socket(self._dropbox_socket_path)
            if dbx_status:
                cleaned = normalize_tooltip_text(
                    dbx_status,
                    strip_unread_notifications=strip_unread_notifications,
                )
                icons.append(
                    TrayIconItem(
                        raw_tooltip=dbx_status,
                        cleaned_tooltip=cleaned,
                        location=TrayLocation.LOCAL_IPC,
                        process_name="dropbox",
                    )
                )
        return icons
