"""Legacy Windows 10 / 11-21H2 ToolbarWindow32 cross-process memory reader fallback.

On Windows 10 and Windows 11 21H2, NotifyIconOverflowWindow hosts a Win32 ToolbarWindow32
control whose UIA tree may not be populated until the overflow flyout is first shown.
Sending TB_BUTTONCOUNT and TB_GETBUTTON with ReadProcessMemory reads the live UTF-16
tooltip strings directly from explorer.exe memory without ever opening the flyout.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys

from speak_sync.core.classifier import normalize_tooltip_text
from speak_sync.models import TrayIconItem, TrayLocation

TB_BUTTONCOUNT = 0x0418
TB_GETBUTTON = 0x0417
TBSTATE_HIDDEN = 0x08

PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

MEM_COMMIT = 0x1000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04


class TBBUTTON64(ctypes.Structure):
    """64-bit Win32 TBBUTTON structure used by 64-bit explorer.exe."""

    _fields_ = [
        ("iBitmap", ctypes.c_int),
        ("idCommand", ctypes.c_int),
        ("fsState", ctypes.c_ubyte),
        ("fsStyle", ctypes.c_ubyte),
        ("bReserved", ctypes.c_ubyte * 6),
        ("dwData", ctypes.c_uint64),
        ("iString", ctypes.c_uint64),
    ]


def parse_utf16_buffer(raw_bytes: bytes) -> str:
    """Decode a null-terminated UTF-16LE byte buffer into a Python string."""
    if not raw_bytes:
        return ""
    text = raw_bytes.decode("utf-16-le", errors="ignore")
    null_idx = text.find("\x00")
    if null_idx != -1:
        text = text[:null_idx]
    return text.strip()


def read_toolbar_tray_icons(
    toolbar_hwnd: int,
    location: TrayLocation,
    *,
    strip_unread_notifications: bool = False,
) -> list[TrayIconItem]:
    """Read tray icon tooltips from a Win32 ToolbarWindow32 HWND via TB_GETBUTTON."""
    if sys.platform != "win32" or not toolbar_hwnd:
        return []

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    count = int(user32.SendMessageW(toolbar_hwnd, TB_BUTTONCOUNT, 0, 0))
    if count <= 0 or count > 256:
        return []

    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(toolbar_hwnd, ctypes.byref(pid))
    if not pid.value:
        return []

    h_process = kernel32.OpenProcess(
        PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
        False,
        pid.value,
    )
    if not h_process:
        return []

    remote_buf = kernel32.VirtualAllocEx(
        h_process,
        None,
        ctypes.sizeof(TBBUTTON64),
        MEM_COMMIT,
        PAGE_READWRITE,
    )
    if not remote_buf:
        kernel32.CloseHandle(h_process)
        return []

    results: list[TrayIconItem] = []
    try:
        for idx in range(count):
            ok = user32.SendMessageW(toolbar_hwnd, TB_GETBUTTON, idx, remote_buf)
            if not ok:
                continue

            btn = TBBUTTON64()
            bytes_read = ctypes.c_size_t(0)
            if not kernel32.ReadProcessMemory(
                h_process,
                remote_buf,
                ctypes.byref(btn),
                ctypes.sizeof(TBBUTTON64),
                ctypes.byref(bytes_read),
            ):
                continue

            if btn.fsState & TBSTATE_HIDDEN:
                continue
            if not btn.iString or btn.iString == 0xFFFFFFFFFFFFFFFF:
                continue

            str_buf = ctypes.create_string_buffer(1024)
            if not kernel32.ReadProcessMemory(
                h_process,
                ctypes.c_void_p(btn.iString),
                str_buf,
                1024,
                ctypes.byref(bytes_read),
            ):
                continue

            raw_tip = parse_utf16_buffer(str_buf.raw)
            if not raw_tip:
                continue

            cleaned = normalize_tooltip_text(
                raw_tip,
                strip_unread_notifications=strip_unread_notifications,
            )
            if cleaned:
                results.append(
                    TrayIconItem(
                        raw_tooltip=raw_tip,
                        cleaned_tooltip=cleaned,
                        location=location,
                        automation_id="ToolbarWindow32Button",
                        hwnd=toolbar_hwnd,
                    )
                )
    finally:
        kernel32.VirtualFreeEx(h_process, remote_buf, 0, MEM_RELEASE)
        kernel32.CloseHandle(h_process)

    return results
