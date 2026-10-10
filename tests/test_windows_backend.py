"""Unit and live integration tests for WindowsTrayBackend (visible and hidden overflow tray)."""

from __future__ import annotations

import sys
import time
import pytest

from speak_sync.backends.windows import (
    WindowsTrayBackend,
    ensure_default_desktop,
    get_windows_build_info,
    resolve_tray_container_hwnds,
)
from speak_sync.models import TrayLocation

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only tray backend tests")


def test_get_windows_build_info() -> None:
    is_w11, is_22h2, build = get_windows_build_info()
    assert build > 0
    if build >= 22621:
        assert is_w11 is True
        assert is_22h2 is True


def test_resolve_tray_container_hwnds_finds_visible_and_overflow() -> None:
    assert ensure_default_desktop() is True
    targets = resolve_tray_container_hwnds()
    assert len(targets) >= 2
    locations = {t.location for t in targets}
    assert TrayLocation.VISIBLE in locations
    assert TrayLocation.OVERFLOW in locations


def test_windows_tray_backend_live_hidden_overflow_icon_lifecycle() -> None:
    import win32con
    import win32gui

    ensure_default_desktop()
    backend = WindowsTrayBackend()

    initial_icons = backend.get_tray_icons()
    assert len(initial_icons) > 0

    wc = win32gui.WNDCLASS()
    wc.hInstance = win32gui.GetModuleHandle(None)
    wc.lpszClassName = "SpeakSyncLiveOverflowTestWnd"
    wc.lpfnWndProc = {win32con.WM_DESTROY: lambda h, m, w, l: 0}
    atom = win32gui.RegisterClass(wc)
    hwnd = win32gui.CreateWindow(
        atom,
        "SpeakSyncLiveOverflowTestWnd",
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        wc.hInstance,
        None,
    )
    hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
    uid = 9421

    try:
        nid_add = (
            hwnd,
            uid,
            win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
            win32con.WM_USER + 42,
            hicon,
            "SpeakSyncHiddenProbe\nIndexing 12 files...",
        )
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid_add)

        matched = None
        for _ in range(15):
            time.sleep(0.1)
            icons = backend.get_tray_icons()
            for item in icons:
                if "SpeakSyncHiddenProbe" in item.cleaned_tooltip:
                    matched = item
                    break
            if matched is not None:
                break

        assert matched is not None, "Newly added tray icon should be detected in hidden overflow"
        assert matched.location == TrayLocation.OVERFLOW
        assert "Indexing 12 files..." in matched.cleaned_tooltip

        # Update tooltip while overflow remains completely closed
        nid_mod = (
            hwnd,
            uid,
            win32gui.NIF_TIP,
            win32con.WM_USER + 42,
            hicon,
            "SpeakSyncHiddenProbe\nUp to date",
        )
        win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, nid_mod)

        updated = None
        for _ in range(15):
            time.sleep(0.1)
            icons = backend.get_tray_icons()
            for item in icons:
                if (
                    "SpeakSyncHiddenProbe" in item.cleaned_tooltip
                    and "Up to date" in item.cleaned_tooltip
                ):
                    updated = item
                    break
            if updated is not None:
                break

        assert updated is not None, "Modified tooltip in hidden overflow should update in real time"
        assert updated.location == TrayLocation.OVERFLOW

    finally:
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (hwnd, uid))
        except Exception:
            pass
        win32gui.DestroyWindow(hwnd)
        win32gui.UnregisterClass(atom, wc.hInstance)
        backend.close()
