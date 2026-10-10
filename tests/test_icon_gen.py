"""Unit tests for programmatic system tray icon generation."""

from __future__ import annotations

import wx
from speak_dropbox.ui.icon_gen import create_tray_bitmap, create_tray_icon


def test_create_tray_icons_for_all_modes(wx_app: wx.App) -> None:
    for mode in ("idle", "syncing", "problem"):
        bmp = create_tray_bitmap(status_mode=mode, size=32)
        assert bmp.IsOk() is True
        assert bmp.GetWidth() == 32
        assert bmp.GetHeight() == 32

        icon = create_tray_icon(status_mode=mode, size=32)
        assert icon.IsOk() is True
