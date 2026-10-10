"""Unit tests for DetectTrayIconsDialog and CustomSourceRuleDialog."""

from __future__ import annotations

import wx
from speak_sync.models import TrayIconItem, TrayLocation
from speak_sync.ui.tray_picker_dialog import (
    CustomSourceRuleDialog,
    DetectTrayIconsDialog,
    infer_app_name_and_keyword,
)


def test_infer_app_name_and_keyword() -> None:
    assert infer_app_name_and_keyword("Dropbox 274.4.4841 - Up to date") == ("Dropbox", "dropbox")
    assert infer_app_name_and_keyword("Resilio Sync") == ("Resilio Sync", "resilio sync")


def test_detect_tray_icons_dialog(wx_app: wx.App) -> None:
    icons = [
        TrayIconItem(
            raw_tooltip="pCloud Drive - Up to date",
            cleaned_tooltip="pCloud Drive - Up to date",
            location=TrayLocation.OVERFLOW,
        ),
        TrayIconItem(
            raw_tooltip="Box Drive - Synced",
            cleaned_tooltip="Box Drive - Synced",
            location=TrayLocation.VISIBLE,
        ),
    ]
    dlg = DetectTrayIconsDialog(None, icons)
    try:
        assert dlg.icon_list.GetItemCount() == 2
        assert dlg.name_input.GetValue() == "pCloud Drive"
        assert dlg.keyword_input.GetValue() == "pcloud drive"
        rule = dlg.get_created_rule()
        assert rule is not None
        assert rule.id == "pcloud_drive"
        assert rule.keywords == ["pcloud drive"]
    finally:
        dlg.Destroy()


def test_custom_source_rule_dialog(wx_app: wx.App) -> None:
    dlg = CustomSourceRuleDialog(None)
    try:
        dlg.name_input.SetValue("Seafile")
        dlg.keywords_input.SetValue("seafile, seadrive")
        dlg.slot_choice.SetSelection(4)  # Slot 4
        rule = dlg.get_rule()
        assert rule is not None
        assert rule.id == "seafile"
        assert rule.display_name == "Seafile"
        assert rule.keywords == ["seafile", "seadrive"]
        assert rule.pinned_slot == 4
    finally:
        dlg.Destroy()
