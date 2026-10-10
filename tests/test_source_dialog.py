"""Unit tests for ManageSourcesDialog UI, source operations, and settings application."""

from __future__ import annotations

import wx
from speak_dropbox.backends.base import StaticTrayBackend
from speak_dropbox.config import AppConfig
from speak_dropbox.core.monitor import TrayMonitorService
from speak_dropbox.models import TrayIconItem, TrayLocation
from speak_dropbox.ui.source_dialog import ManageSourcesDialog


def test_manage_sources_dialog_population_and_apply(wx_app: wx.App) -> None:
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
        ]
    )
    cfg = AppConfig()
    monitor = TrayMonitorService(backend, cfg)
    monitor.poll()

    applied_configs: list[AppConfig] = []
    dlg = ManageSourcesDialog(
        None,
        cfg,
        monitor,
        on_apply_callback=lambda c: applied_configs.append(c),
    )
    try:
        assert dlg.notebook.GetPageCount() == 3
        assert dlg.sources_list.GetItemCount() == len(cfg.sources)
        assert dlg.sources_list.GetItemText(0, 0) == "Slot 1"
        assert dlg.sources_list.GetItemText(0, 1) == "Dropbox"
        assert "Visible Tray" in dlg.sources_list.GetItemText(0, 4)

        assert dlg.sources_list.GetItemText(1, 0) == "Slot 2"
        assert dlg.sources_list.GetItemText(1, 1) == "Google Drive"
        assert "Hidden Tray" in dlg.sources_list.GetItemText(1, 4)

        # Move Google Drive (index 1) up to index 0
        dlg.sources_list.Select(1)
        dlg._on_move_source(-1)
        assert dlg.working_config.sources[0].id == "google_drive"

        # Toggle enabled on index 0
        dlg._on_toggle_source(wx.CommandEvent())
        assert dlg.working_config.sources[0].enabled is False

        # Modify speech & hotkey settings
        dlg.chk_strip_unread.SetValue(True)
        dlg.spin_loop_interval.SetValue(4.0)
        dlg.modifier_choice.SetSelection(1)  # Ctrl+Shift+Win
        dlg._on_modifier_changed(wx.CommandEvent())

        updated = dlg.apply_to_config()
        assert updated.strip_unread_notifications is True
        assert updated.loop_interval_seconds == 4.0
        assert updated.hotkey_modifier == "Ctrl+Shift+Win"
        assert updated.summary_hotkey == "Ctrl+Shift+Win+0"
    finally:
        dlg.Destroy()
