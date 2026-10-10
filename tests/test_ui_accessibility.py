"""Live Windows UI Automation (IUIAutomation) accessibility tree audit for all SpeakSync dialogs."""

from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Any
import pytest
import wx

from speak_sync.backends.base import StaticTrayBackend
from speak_sync.config import AppConfig
from speak_sync.core.monitor import TrayMonitorService
from speak_sync.models import TrayIconItem, TrayLocation
from speak_sync.ui.gui_helper import ShortcutReferenceDialog
from speak_sync.ui.source_dialog import ManageSourcesDialog
from speak_sync.ui.tray_picker_dialog import CustomSourceRuleDialog, DetectTrayIconsDialog

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows UI Automation (IUIAutomation) audit runs on win32",
)

UIA_BUTTON = 50000
UIA_CHECKBOX = 50002
UIA_COMBOBOX = 50003
UIA_EDIT = 50004
UIA_LISTITEM = 50007
UIA_LIST = 50008
UIA_SPINNER = 50016
UIA_TAB = 50018
UIA_TABITEM = 50019

INTERACTIVE_CONTROL_TYPES: dict[int, str] = {
    UIA_BUTTON: "Button",
    UIA_CHECKBOX: "CheckBox",
    UIA_COMBOBOX: "ComboBox",
    UIA_EDIT: "Edit",
    UIA_LIST: "List",
    UIA_SPINNER: "Spinner",
    UIA_TAB: "Tab",
    UIA_TABITEM: "TabItem",
}


@dataclass(frozen=True)
class UIANodeSnapshot:
    """Snapshot of an interactive control discovered in the live Windows UIA tree."""

    control_type: int
    control_type_name: str
    name: str
    is_keyboard_focusable: bool
    class_name: str


def _get_uia_client() -> tuple[Any, Any]:
    import comtypes
    import comtypes.client

    comtypes.CoInitialize()
    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient

    uia = comtypes.client.CreateObject(
        UIAutomationClient.CUIAutomation,
        interface=UIAutomationClient.IUIAutomation,
    )
    return uia, uia.CreateTrueCondition()


def snapshot_dialog_uia_controls(dlg: wx.Dialog) -> tuple[str, list[UIANodeSnapshot]]:
    """Query the live Windows IUIAutomation tree for a shown wx.Dialog HWND."""
    uia, true_cond = _get_uia_client()
    root = uia.ElementFromHandle(int(dlg.GetHandle()))
    assert root is not None
    window_name = str(root.CurrentName or "")

    arr = root.FindAll(4, true_cond)  # TreeScope_Descendants = 4
    nodes: list[UIANodeSnapshot] = []
    if arr is not None:
        for idx in range(arr.Length):
            el = arr.GetElement(idx)
            ct = int(el.CurrentControlType)
            if ct in INTERACTIVE_CONTROL_TYPES:
                nodes.append(
                    UIANodeSnapshot(
                        control_type=ct,
                        control_type_name=INTERACTIVE_CONTROL_TYPES[ct],
                        name=str(el.CurrentName or "").strip(),
                        is_keyboard_focusable=bool(el.CurrentIsKeyboardFocusable),
                        class_name=str(el.CurrentClassName or ""),
                    )
                )
    return window_name, nodes


def assert_all_interactive_controls_labeled(nodes: list[UIANodeSnapshot], context: str) -> None:
    """Verify that zero interactive controls in the live UIA tree have an empty CurrentName."""
    unlabeled = [n for n in nodes if not n.name]
    assert not unlabeled, f"Unlabeled interactive UIA controls in {context}: {unlabeled}"


def assert_expected_focusable_controls(
    nodes: list[UIANodeSnapshot],
    expected: list[tuple[int, str]],
    context: str,
) -> None:
    """Verify every expected (control_type, name) exists in the UIA tree and is keyboard-focusable."""
    by_type_and_name = {(n.control_type, n.name): n for n in nodes}
    for ct, expected_name in expected:
        ct_label = INTERACTIVE_CONTROL_TYPES.get(ct, str(ct))
        key = (ct, expected_name)
        assert key in by_type_and_name, (
            f"Missing UIA control [{ct_label}] {expected_name!r} in {context}. "
            f"Available: {[(n.control_type_name, n.name) for n in nodes]}"
        )
        matched = by_type_and_name[key]
        assert matched.is_keyboard_focusable, (
            f"UIA control [{ct_label}] {expected_name!r} in {context} is not keyboard-focusable"
        )


def test_manage_sources_dialog_live_uia_tree_all_tabs(wx_app: wx.App) -> None:
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

    dlg = ManageSourcesDialog(None, cfg, monitor)
    try:
        dlg.Show()
        wx.SafeYield()

        # Tab 0: Monitored Sources
        dlg.notebook.SetSelection(0)
        wx.SafeYield()
        win_name, tab0_nodes = snapshot_dialog_uia_controls(dlg)
        assert win_name == "SpeakSync - Manage Sources & Settings"
        assert_all_interactive_controls_labeled(tab0_nodes, "ManageSourcesDialog Tab 0")
        assert_expected_focusable_controls(
            tab0_nodes,
            [
                (UIA_TAB, "Settings Categories"),
                (UIA_TABITEM, "Monitored Sources"),
                (UIA_TABITEM, "Speech & Audio Cues"),
                (UIA_TABITEM, "Hotkeys & General"),
                (UIA_TABITEM, "Activity Log"),
                (UIA_LIST, "Configured Cloud and System Tray Sources"),
                (UIA_BUTTON, "Add from System Tray..."),
                (UIA_BUTTON, "Add Custom Keyword..."),
                (UIA_BUTTON, "Edit Source..."),
                (UIA_BUTTON, "Toggle Enabled"),
                (UIA_BUTTON, "Move Up"),
                (UIA_BUTTON, "Move Down"),
                (UIA_BUTTON, "Remove Source"),
                (UIA_BUTTON, "Keyboard Shortcuts (F1)"),
                (UIA_BUTTON, "OK"),
                (UIA_BUTTON, "Cancel"),
            ],
            "ManageSourcesDialog Tab 0",
        )

        # Tab 1: Speech & Audio Cues
        dlg.notebook.SetSelection(1)
        wx.SafeYield()
        _, tab1_nodes = snapshot_dialog_uia_controls(dlg)
        assert_all_interactive_controls_labeled(tab1_nodes, "ManageSourcesDialog Tab 1")
        assert_expected_focusable_controls(
            tab1_nodes,
            [
                (UIA_CHECKBOX, "Enable screen reader speech and braille announcements"),
                (UIA_CHECKBOX, "Speak when syncing or indexing starts"),
                (UIA_CHECKBOX, "Speak when syncing finishes (Up to date)"),
                (UIA_CHECKBOX, "Speak on sync errors, paused, or disconnected states"),
                (UIA_CHECKBOX, "Speak when monitored sources appear or close"),
                (UIA_CHECKBOX, "Strip unread notification counts from Dropbox idle status"),
                (UIA_CHECKBOX, "Play start and finish audio cues when sync state changes"),
                (UIA_CHECKBOX, "Play sustain loop sound while syncing is active (loopty.flac)"),
                (UIA_EDIT, "Sustain Loop Interval (seconds)"),
                (UIA_SPINNER, "Sustain Loop Interval (seconds)"),
                (UIA_BUTTON, "Preview Start Cue"),
                (UIA_BUTTON, "Preview Loop Cue"),
                (UIA_BUTTON, "Preview Finish Cue"),
            ],
            "ManageSourcesDialog Tab 1",
        )

        # Tab 2: Hotkeys & General
        dlg.notebook.SetSelection(2)
        wx.SafeYield()
        _, tab2_nodes = snapshot_dialog_uia_controls(dlg)
        assert_all_interactive_controls_labeled(tab2_nodes, "ManageSourcesDialog Tab 2")
        assert_expected_focusable_controls(
            tab2_nodes,
            [
                (
                    UIA_COMBOBOX,
                    "Global Slot Hotkey Modifier (press Modifier + 1..9 to speak Slot 1..9)",
                ),
                (UIA_CHECKBOX, "Use Ctrl modifier"),
                (UIA_CHECKBOX, "Use Alt modifier"),
                (UIA_CHECKBOX, "Use Shift modifier"),
                (UIA_CHECKBOX, "Use Win modifier"),
                (UIA_EDIT, "Speak All Active Sources Summary Hotkey"),
                (UIA_EDIT, "Open Manage Sources & Settings Hotkey"),
                (UIA_EDIT, "System Tray Background Poll Interval (seconds)"),
                (UIA_SPINNER, "System Tray Background Poll Interval (seconds)"),
                (UIA_CHECKBOX, "Run SpeakSync automatically on system startup"),
            ],
            "ManageSourcesDialog Tab 2",
        )

        # Tab 3: Activity Log
        dlg.notebook.SetSelection(3)
        wx.SafeYield()
        _, tab3_nodes = snapshot_dialog_uia_controls(dlg)
        assert_all_interactive_controls_labeled(tab3_nodes, "ManageSourcesDialog Tab 3")
        assert_expected_focusable_controls(
            tab3_nodes,
            [
                (UIA_LIST, "Recent Sync Activity Transitions"),
                (UIA_BUTTON, "Copy Selected Entry"),
                (UIA_BUTTON, "Refresh Log"),
                (UIA_BUTTON, "Clear Log"),
            ],
            "ManageSourcesDialog Tab 3",
        )
    finally:
        dlg.Destroy()


def test_detect_tray_icons_dialog_live_uia_tree(wx_app: wx.App) -> None:
    candidates = [
        TrayIconItem(
            raw_tooltip="pCloud Drive - Everything is synced",
            cleaned_tooltip="pCloud Drive - Everything is synced",
            location=TrayLocation.OVERFLOW,
        ),
        TrayIconItem(
            raw_tooltip="Dropbox 274.4.4841 - Up to date",
            cleaned_tooltip="Dropbox 274.4.4841 - Up to date",
            location=TrayLocation.VISIBLE,
        ),
    ]
    dlg = DetectTrayIconsDialog(None, candidates, rescan_callback=lambda: candidates)
    try:
        dlg.Show()
        wx.SafeYield()
        win_name, nodes = snapshot_dialog_uia_controls(dlg)
        assert win_name == "Add Source from Detected System Tray Icons"
        assert_all_interactive_controls_labeled(nodes, "DetectTrayIconsDialog")
        assert_expected_focusable_controls(
            nodes,
            [
                (UIA_LIST, "Detected System Tray Icons (Visible and Hidden Tray)"),
                (UIA_BUTTON, "Refresh Tray List"),
                (UIA_EDIT, "Source Display Name"),
                (UIA_EDIT, "Matching Keyword"),
                (UIA_BUTTON, "OK"),
                (UIA_BUTTON, "Cancel"),
            ],
            "DetectTrayIconsDialog",
        )
    finally:
        dlg.Destroy()


def test_custom_source_rule_dialog_live_uia_tree(wx_app: wx.App) -> None:
    dlg = CustomSourceRuleDialog(None)
    try:
        dlg.Show()
        wx.SafeYield()
        win_name, nodes = snapshot_dialog_uia_controls(dlg)
        assert win_name == "Add Custom Keyword Source"
        assert_all_interactive_controls_labeled(nodes, "CustomSourceRuleDialog")
        assert_expected_focusable_controls(
            nodes,
            [
                (UIA_EDIT, "Source Display Name"),
                (UIA_EDIT, "Matching Keywords (comma-separated)"),
                (UIA_COMBOBOX, "Pinned Slot Number"),
                (UIA_BUTTON, "OK"),
                (UIA_BUTTON, "Cancel"),
            ],
            "CustomSourceRuleDialog",
        )
    finally:
        dlg.Destroy()


def test_shortcut_reference_dialog_and_f1_keyboard_navigation(wx_app: wx.App) -> None:
    dlg = ShortcutReferenceDialog(None, modifier="Alt+Win")
    try:
        dlg.Show()
        wx.SafeYield()
        win_name, nodes = snapshot_dialog_uia_controls(dlg)
        assert win_name == "SpeakSync Keyboard Shortcuts"
        assert_all_interactive_controls_labeled(nodes, "ShortcutReferenceDialog")
        assert_expected_focusable_controls(
            nodes,
            [
                (UIA_LIST, "Available Keyboard Shortcuts"),
                (UIA_BUTTON, "OK"),
            ],
            "ShortcutReferenceDialog",
        )
    finally:
        dlg.Destroy()

    # Verify F1 key event in ManageSourcesDialog opens ShortcutReferenceDialog and Escape dismisses it
    backend = StaticTrayBackend([])
    cfg = AppConfig()
    monitor = TrayMonitorService(backend, cfg)
    manage_dlg = ManageSourcesDialog(None, cfg, monitor)
    captured_f1_dialog_titles: list[str] = []

    def _inspect_and_close_f1_dialog() -> None:
        for top in wx.GetTopLevelWindows():
            if isinstance(top, ShortcutReferenceDialog) and top.IsShown():
                title, f1_nodes = snapshot_dialog_uia_controls(top)
                captured_f1_dialog_titles.append(title)
                assert_all_interactive_controls_labeled(f1_nodes, "F1 ShortcutReferenceDialog")
                esc_event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
                esc_event.SetKeyCode(wx.WXK_ESCAPE)
                top._on_char_hook(esc_event)

    try:
        manage_dlg.Show()
        wx.SafeYield()
        wx.CallLater(80, _inspect_and_close_f1_dialog)
        f1_event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        f1_event.SetKeyCode(wx.WXK_F1)
        manage_dlg._on_char_hook(f1_event)
        assert captured_f1_dialog_titles == ["SpeakSync Keyboard Shortcuts"]
    finally:
        manage_dlg.Destroy()
