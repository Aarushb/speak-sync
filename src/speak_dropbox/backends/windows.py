"""Windows system tray and hidden overflow HWND resolution and UIA backend."""

from __future__ import annotations

import ctypes
import logging
import platform
import sys
from ctypes import wintypes
from dataclasses import dataclass

from speak_dropbox.models import TrayLocation

logger = logging.getLogger(__name__)

_GENERIC_ALL = 0x10000000

SHELL_TRAY_CLASS = "Shell_TrayWnd"
WIN11_OVERFLOW_XAML_CLASS = "TopLevelWindowForOverflowXamlIsland"
LEGACY_OVERFLOW_CLASS = "NotifyIconOverflowWindow"
CONTENT_BRIDGE_CLASS = "Windows.UI.Composition.DesktopWindowContentBridge"
INPUT_SITE_CLASS = "Windows.UI.Input.InputSite.WindowClass"
TRAY_NOTIFY_CLASS = "TrayNotifyWnd"
SYS_PAGER_CLASS = "SysPager"
TOOLBAR_CLASS = "ToolbarWindow32"


@dataclass(frozen=True)
class TrayContainerTarget:
    """Represents a resolved Win32 HWND container holding tray icon elements."""

    hwnd: int
    location: TrayLocation
    container_kind: str  # "xaml_input_site", "content_bridge", or "toolbar32"


def get_windows_build_info() -> tuple[bool, bool, int]:
    """Return (is_win11, is_win11_22h2_or_later, build_number)."""
    if sys.platform != "win32":
        return False, False, 0
    try:
        ver = platform.win32_ver()
        release_str = ver[0]
        parts = ver[1].split(".")
        build = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
        is_win11 = release_str == "11" or build >= 22000
        is_win11_22h2 = is_win11 and build >= 22621
        return is_win11, is_win11_22h2, build
    except Exception as exc:
        logger.debug("Could not parse Windows version: %s", exc)
        return False, False, 0


def _get_user32() -> ctypes.WinDLL | None:
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
    ]
    user32.FindWindowExW.restype = wintypes.HWND
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    return user32


def ensure_default_desktop() -> bool:
    """Attach the current thread to the interactive Default desktop if running in an isolated desktop."""
    user32 = _get_user32()
    if user32 is None:
        return False
    if user32.FindWindowW(SHELL_TRAY_CLASS, None):
        return True
    try:
        user32.OpenDesktopW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.ACCESS_MASK,
        ]
        user32.OpenDesktopW.restype = wintypes.HANDLE
        user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
        user32.SetThreadDesktop.restype = wintypes.BOOL
        hdesk = user32.OpenDesktopW("Default", 0, False, _GENERIC_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception as exc:
        logger.debug("ensure_default_desktop fallback failed: %s", exc)
    return bool(user32.FindWindowW(SHELL_TRAY_CLASS, None))


def resolve_tray_container_hwnds() -> list[TrayContainerTarget]:
    """Resolve both visible taskbar tray and hidden overflow tray container HWNDs without showing hidden windows."""
    user32 = _get_user32()
    if user32 is None:
        return []

    ensure_default_desktop()
    targets: list[TrayContainerTarget] = []

    # 1. Visible System Tray inside Shell_TrayWnd
    shell_hwnd = user32.FindWindowW(SHELL_TRAY_CLASS, None)
    if shell_hwnd:
        bridge_vis = user32.FindWindowExW(shell_hwnd, 0, CONTENT_BRIDGE_CLASS, None)
        if bridge_vis:
            site_vis = user32.FindWindowExW(bridge_vis, 0, INPUT_SITE_CLASS, None)
            if site_vis:
                targets.append(
                    TrayContainerTarget(
                        hwnd=int(site_vis),
                        location=TrayLocation.VISIBLE,
                        container_kind="xaml_input_site",
                    )
                )
            else:
                targets.append(
                    TrayContainerTarget(
                        hwnd=int(bridge_vis),
                        location=TrayLocation.VISIBLE,
                        container_kind="content_bridge",
                    )
                )

        # Also check legacy ToolbarWindow32 inside Shell_TrayWnd -> TrayNotifyWnd -> SysPager
        tray_notify = user32.FindWindowExW(shell_hwnd, 0, TRAY_NOTIFY_CLASS, None)
        if tray_notify:
            sys_pager = user32.FindWindowExW(tray_notify, 0, SYS_PAGER_CLASS, None)
            if sys_pager:
                toolbar_vis = user32.FindWindowExW(sys_pager, 0, TOOLBAR_CLASS, None)
                if toolbar_vis:
                    targets.append(
                        TrayContainerTarget(
                            hwnd=int(toolbar_vis),
                            location=TrayLocation.VISIBLE,
                            container_kind="toolbar32",
                        )
                    )

    # 2. Windows 11 22H2+ Hidden Overflow XAML Island (TopLevelWindowForOverflowXamlIsland)
    # Note: FindWindowW locates this top-level window even when IsWindowVisible == 0!
    overflow_xaml = user32.FindWindowW(WIN11_OVERFLOW_XAML_CLASS, None)
    if overflow_xaml:
        bridge_ov = user32.FindWindowExW(overflow_xaml, 0, CONTENT_BRIDGE_CLASS, None)
        if bridge_ov:
            site_ov = user32.FindWindowExW(bridge_ov, 0, INPUT_SITE_CLASS, None)
            if site_ov:
                targets.append(
                    TrayContainerTarget(
                        hwnd=int(site_ov),
                        location=TrayLocation.OVERFLOW,
                        container_kind="xaml_input_site",
                    )
                )
            else:
                targets.append(
                    TrayContainerTarget(
                        hwnd=int(bridge_ov),
                        location=TrayLocation.OVERFLOW,
                        container_kind="content_bridge",
                    )
                )

    # 3. Windows 10 & Windows 11 21H2 Hidden Overflow Window (NotifyIconOverflowWindow)
    legacy_overflow = user32.FindWindowW(LEGACY_OVERFLOW_CLASS, None)
    if legacy_overflow:
        toolbar_ov = user32.FindWindowExW(legacy_overflow, 0, TOOLBAR_CLASS, None)
        if toolbar_ov:
            targets.append(
                TrayContainerTarget(
                    hwnd=int(toolbar_ov),
                    location=TrayLocation.OVERFLOW,
                    container_kind="toolbar32",
                )
            )

    return targets
