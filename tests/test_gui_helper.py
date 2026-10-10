"""Unit tests for BoxSizerHelper control labeling and ShortcutReferenceDialog."""

from __future__ import annotations

import wx
from speak_dropbox.ui.gui_helper import BoxSizerHelper, ShortcutReferenceDialog


def test_box_sizer_helper_labeled_control(wx_app: wx.App) -> None:
    dlg = wx.Dialog(None, title="Test Host")
    try:
        helper = BoxSizerHelper(dlg)
        label, text_ctrl = helper.add_labeled_control("&Custom Keyword:", wx.TextCtrl)
        assert label.GetLabel() == "&Custom Keyword:"
        assert text_ctrl.GetName() == "Custom Keyword"
    finally:
        dlg.Destroy()


def test_shortcut_reference_dialog(wx_app: wx.App) -> None:
    dlg = ShortcutReferenceDialog(None, modifier="Ctrl+Shift+Win")
    try:
        assert dlg.list_ctrl.GetItemCount() >= 8
        first_shortcut = dlg.list_ctrl.GetItemText(0, 0)
        assert "Ctrl+Shift+Win+1" in first_shortcut
        assert dlg.list_ctrl.GetName() == "Available Keyboard Shortcuts"
    finally:
        dlg.Destroy()
