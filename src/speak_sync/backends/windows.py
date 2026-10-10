"""Windows system tray and hidden overflow HWND resolution and UIA backend."""

from __future__ import annotations

import ctypes
import logging
import platform
import sys
import threading
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any

from speak_sync.backends.base import TrayBackend
from speak_sync.core.classifier import normalize_tooltip_text
from speak_sync.models import TrayIconItem, TrayLocation

logger = logging.getLogger(__name__)

_GENERIC_ALL = 0x10000000
_TREESCOPE_CHILDREN = 2
_TREESCOPE_DESCENDANTS = 4
_UIA_BUTTON_CONTROL_TYPE_ID = 50000

SHELL_TRAY_CLASS = "Shell_TrayWnd"
WIN11_OVERFLOW_XAML_CLASS = "TopLevelWindowForOverflowXamlIsland"
LEGACY_OVERFLOW_CLASS = "NotifyIconOverflowWindow"
CONTENT_BRIDGE_CLASS = "Windows.UI.Composition.DesktopWindowContentBridge"
INPUT_SITE_CLASS = "Windows.UI.Input.InputSite.WindowClass"
TRAY_NOTIFY_CLASS = "TrayNotifyWnd"
SYS_PAGER_CLASS = "SysPager"
TOOLBAR_CLASS = "ToolbarWindow32"

_IGNORED_SYSTEM_BUTTON_NAMES: frozenset[str] = frozenset(
    {
        "start",
        "search",
        "task view",
        "widgets",
        "chat",
        "copilot",
        "show hidden icons",
        "notification chevron",
        "chevron",
        "show desktop",
    }
)


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
    """Attach the current thread to the interactive Default desktop before any Win32 GUI call."""
    user32 = _get_user32()
    if user32 is None:
        return False
    try:
        user32.OpenDesktopW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
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
    # FindWindowW locates this top-level window even when IsWindowVisible == 0!
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


class _ThreadLocalUIAState(threading.local):
    """Per-thread COM and IUIAutomation state for thread-safe tray queries."""

    def __init__(self) -> None:
        super().__init__()
        self.initialized = False
        self.uia: Any = None
        self.cond_notify_item: Any = None
        self.cond_button: Any = None
        self.cache_req: Any = None
        self.element_cache: dict[int, Any] = {}


class WindowsTrayBackend(TrayBackend):
    """Queries visible and hidden overflow Windows system tray icons in the background via UIA ElementFromHandle."""

    def __init__(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        self._tls = _ThreadLocalUIAState()
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="SpeakSyncWinUIA",
        )

    @property
    def platform_name(self) -> str:
        is_w11, is_22h2, build = get_windows_build_info()
        if is_22h2:
            return f"Windows 11 XAML Tray & Hidden Overflow (Build {build})"
        if is_w11:
            return f"Windows 11 Tray & Overflow (Build {build})"
        return f"Windows Win32/UIA Tray & Overflow (Build {build})"

    def _ensure_uia(self) -> bool:
        if sys.platform != "win32":
            return False
        if self._tls.initialized and self._tls.uia is not None:
            return True

        ensure_default_desktop()
        try:
            import comtypes
            import comtypes.client

            comtypes.CoInitialize()
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient

            uia = comtypes.client.CreateObject(
                UIAutomationClient.CUIAutomation,
                interface=UIAutomationClient.IUIAutomation,
            )
            cond_notify = uia.CreatePropertyCondition(
                UIAutomationClient.UIA_AutomationIdPropertyId,
                "NotifyItemIcon",
            )
            cond_button = uia.CreatePropertyCondition(
                UIAutomationClient.UIA_ControlTypePropertyId,
                _UIA_BUTTON_CONTROL_TYPE_ID,
            )
            cache_req = uia.CreateCacheRequest()
            cache_req.AddProperty(UIAutomationClient.UIA_NamePropertyId)
            cache_req.AddProperty(UIAutomationClient.UIA_AutomationIdPropertyId)

            self._tls.uia = uia
            self._tls.cond_notify_item = cond_notify
            self._tls.cond_button = cond_button
            self._tls.cache_req = cache_req
            self._tls.element_cache = {}
            self._tls.initialized = True
            return True
        except Exception as exc:
            logger.error("Failed to initialize Windows IUIAutomation client: %s", exc)
            return False

    def _get_element_for_hwnd(self, hwnd: int) -> Any | None:
        user32 = _get_user32()
        if user32 is not None and not user32.IsWindow(hwnd):
            self._tls.element_cache.pop(hwnd, None)
            return None

        cached = self._tls.element_cache.get(hwnd)
        if cached is not None:
            return cached

        try:
            el = self._tls.uia.ElementFromHandle(hwnd)
            if el is not None:
                self._tls.element_cache[hwnd] = el
            return el
        except Exception as exc:
            logger.debug("ElementFromHandle(%#x) failed: %s", hwnd, exc)
            self._tls.element_cache.pop(hwnd, None)
            return None

    def _extract_items_from_target(
        self,
        target: TrayContainerTarget,
        *,
        strip_unread_notifications: bool = False,
    ) -> list[TrayIconItem]:
        el = self._get_element_for_hwnd(target.hwnd)
        if el is None:
            return []

        results: list[TrayIconItem] = []
        try:
            if target.container_kind == "xaml_input_site":
                array = el.FindAllBuildCache(
                    _TREESCOPE_CHILDREN,
                    self._tls.cond_notify_item,
                    self._tls.cache_req,
                )
                if array is None or array.Length == 0:
                    array = el.FindAllBuildCache(
                        _TREESCOPE_CHILDREN,
                        self._tls.cond_button,
                        self._tls.cache_req,
                    )
            else:
                array = el.FindAllBuildCache(
                    _TREESCOPE_DESCENDANTS,
                    self._tls.cond_button,
                    self._tls.cache_req,
                )

            if array is not None:
                for idx in range(array.Length):
                    item_el = array.GetElement(idx)
                    raw_name = item_el.CachedName or ""
                    auto_id = item_el.CachedAutomationId or ""
                    if not raw_name or not raw_name.strip():
                        continue
                    cleaned = normalize_tooltip_text(
                        raw_name,
                        strip_unread_notifications=strip_unread_notifications,
                    )
                    if not cleaned:
                        continue
                    if (
                        auto_id != "NotifyItemIcon"
                        and cleaned.lower() in _IGNORED_SYSTEM_BUTTON_NAMES
                    ):
                        continue
                    results.append(
                        TrayIconItem(
                            raw_tooltip=raw_name,
                            cleaned_tooltip=cleaned,
                            location=target.location,
                            automation_id=auto_id,
                            hwnd=target.hwnd,
                        )
                    )
        except Exception as exc:
            logger.debug("UIA query on container %#x failed, invalidating cache: %s", target.hwnd, exc)
            self._tls.element_cache.pop(target.hwnd, None)

        if not results and target.container_kind == "toolbar32":
            from speak_sync.backends.win32_toolbar import read_toolbar_tray_icons

            results = read_toolbar_tray_icons(
                target.hwnd,
                target.location,
                strip_unread_notifications=strip_unread_notifications,
            )

        return results

    def _query_on_worker(self, strip_unread_notifications: bool) -> list[TrayIconItem]:
        if not self._ensure_uia():
            return []

        targets = resolve_tray_container_hwnds()
        seen_keys: set[tuple[str, TrayLocation]] = set()
        icons: list[TrayIconItem] = []

        for target in targets:
            extracted = self._extract_items_from_target(
                target,
                strip_unread_notifications=strip_unread_notifications,
            )
            for item in extracted:
                dedup_key = (item.cleaned_tooltip.lower(), item.location)
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)
                    icons.append(item)

        return icons

    def get_tray_icons(self, *, strip_unread_notifications: bool = False) -> list[TrayIconItem]:
        """Return all visible and hidden overflow system tray icons on Windows."""
        try:
            future = self._executor.submit(self._query_on_worker, strip_unread_notifications)
            return future.result(timeout=5.0)
        except Exception as exc:
            logger.error("WindowsTrayBackend worker failed: %s", exc)
            return []

    def close(self) -> None:
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
