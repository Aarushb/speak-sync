"""Platform system tray backend factory and exports."""

from __future__ import annotations

from collections.abc import Sequence
import sys

from speak_sync.backends.base import StaticTrayBackend, TrayBackend
from speak_sync.backends.linux import LinuxTrayBackend
from speak_sync.backends.macos import MacOSTrayBackend
from speak_sync.backends.windows import WindowsTrayBackend


def create_tray_backend(
    platform_override: str | None = None,
    candidate_processes: Sequence[str] | None = None,
) -> TrayBackend:
    """Create the appropriate TrayBackend for the current (or overridden) OS platform."""
    plat = (platform_override or sys.platform).lower()
    if plat.startswith("win"):
        return WindowsTrayBackend()
    if plat == "darwin":
        return MacOSTrayBackend(candidate_processes=candidate_processes)
    return LinuxTrayBackend()


__all__ = [
    "LinuxTrayBackend",
    "MacOSTrayBackend",
    "StaticTrayBackend",
    "TrayBackend",
    "WindowsTrayBackend",
    "create_tray_backend",
]
