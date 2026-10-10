"""Unit tests for legacy Windows 10 / 11-21H2 ToolbarWindow32 memory parser."""

from __future__ import annotations

import ctypes

from speak_sync.backends.win32_toolbar import (
    TBBUTTON64,
    parse_utf16_buffer,
    read_toolbar_tray_icons,
)
from speak_sync.models import TrayLocation


def test_parse_utf16_buffer_extracts_null_terminated_string() -> None:
    raw = "Dropbox 274.4.4841\nUp to date\x00trailing_garbage".encode("utf-16-le")
    assert parse_utf16_buffer(raw) == "Dropbox 274.4.4841\nUp to date"
    assert parse_utf16_buffer(b"") == ""


def test_tbbutton64_struct_layout() -> None:
    assert ctypes.sizeof(TBBUTTON64) == 32


def test_read_toolbar_tray_icons_handles_invalid_hwnd() -> None:
    assert read_toolbar_tray_icons(0, TrayLocation.OVERFLOW) == []
