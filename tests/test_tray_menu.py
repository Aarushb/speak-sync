"""Unit tests for SpeakSyncTrayIcon context menu construction and actions."""

from __future__ import annotations

import wx
from speak_sync.backends.base import StaticTrayBackend
from speak_sync.config import AppConfig
from speak_sync.core.monitor import TrayMonitorService
from speak_sync.models import TrayIconItem, TrayLocation
from speak_sync.ui.tray import SpeakSyncTrayIcon


def test_tray_icon_context_menu_and_actions(wx_app: wx.App) -> None:
    backend = StaticTrayBackend(
        [
            TrayIconItem(
                raw_tooltip="Dropbox 274.4.4841 - Up to date",
                cleaned_tooltip="Dropbox 274.4.4841 - Up to date",
                location=TrayLocation.VISIBLE,
            ),
            TrayIconItem(
                raw_tooltip="Google Drive - Everything is up to date",
                cleaned_tooltip="Google Drive - Everything is up to date",
                location=TrayLocation.OVERFLOW,
            ),
            TrayIconItem(
                raw_tooltip="Box Drive - Synced",
                cleaned_tooltip="Box Drive - Synced",
                location=TrayLocation.OVERFLOW,
            ),
        ]
    )
    cfg = AppConfig()
    monitor = TrayMonitorService(backend, cfg)
    monitor.poll()

    mutations: list[int] = []
    tray = SpeakSyncTrayIcon(
        config=cfg,
        monitor=monitor,
        on_speak_slot=lambda _s: None,
        on_copy_slot=lambda _s: None,
        on_speak_summary=lambda: None,
        on_open_manage_dialog=lambda: None,
        on_open_shortcuts_dialog=lambda: None,
        on_config_mutated=lambda: mutations.append(1),
        on_exit=lambda: None,
    )
    try:
        menu = tray.build_context_menu()
        labels = [item.GetItemLabelText() for item in menu.GetMenuItems() if not item.IsSeparator()]
        assert any("1. Dropbox: Up to date (Visible Tray)" in lbl for lbl in labels)
        assert any("2. Google Drive: Everything is up to date (Hidden Tray)" in lbl for lbl in labels)
        assert any("Quick Add from System Tray" in lbl for lbl in labels)

        # Quick-add Box Drive via helper
        tray._quick_add_icon_source(
            TrayIconItem(
                raw_tooltip="Box Drive - Synced",
                cleaned_tooltip="Box Drive - Synced",
                location=TrayLocation.OVERFLOW,
            )
        )
        assert cfg.get_source("box_drive") is not None
        assert len(mutations) == 1

        # Remove Google Drive from menu
        tray._remove_source_in_menu("google_drive")
        gdrive = cfg.get_source("google_drive")
        assert gdrive is not None and gdrive.enabled is False
        assert len(mutations) == 2

        menu.Destroy()
    finally:
        tray.RemoveIcon()
        tray.Destroy()
