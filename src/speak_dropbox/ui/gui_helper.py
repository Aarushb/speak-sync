"""Accessible wxPython layout helpers modeled after NVDA's guiHelper and F1 shortcut reference dialog."""

from __future__ import annotations

from typing import Any
import wx


class BoxSizerHelper:
    """Helper modeled after NVDA's guiHelper.BoxSizerHelper for explicit StaticText control labeling."""

    def __init__(self, parent: wx.Window, orientation: int = wx.VERTICAL) -> None:
        self.parent = parent
        self.sizer = wx.BoxSizer(orientation)

    def add_item(
        self,
        item: wx.Window | wx.Sizer,
        *,
        proportion: int = 0,
        flag: int = wx.EXPAND | wx.ALL,
        border: int = 6,
    ) -> wx.Window | wx.Sizer:
        self.sizer.Add(item, proportion=proportion, flag=flag, border=border)
        return item

    def add_labeled_control(
        self,
        label_text: str,
        control_cls: type[wx.Control],
        *,
        proportion: int = 0,
        flag: int = wx.EXPAND | wx.ALL,
        border: int = 6,
        **kwargs: Any,
    ) -> tuple[wx.StaticText, Any]:
        """Create a wx.StaticText immediately preceding its target control in creation & tab order.

        Also sets the control's accessible Name (Stripping '&' mnemonic) so UIA screen readers
        announce the label reliably on focus.
        """
        label = wx.StaticText(self.parent, label=label_text)
        ctrl = control_cls(self.parent, **kwargs)
        clean_name = label_text.replace("&", "").rstrip(":").strip()
        ctrl.SetName(clean_name)

        row_sizer = wx.BoxSizer(wx.VERTICAL)
        row_sizer.Add(label, 0, wx.BOTTOM, 4)
        row_sizer.Add(ctrl, proportion if proportion > 0 else 0, wx.EXPAND)
        self.sizer.Add(row_sizer, proportion=proportion, flag=flag, border=border)
        return label, ctrl


class ShortcutReferenceDialog(wx.Dialog):
    """Accessible dialog listing all global hotkeys and dialog keyboard shortcuts (bound to F1)."""

    def __init__(self, parent: wx.Window | None, modifier: str = "Alt+Win") -> None:
        super().__init__(
            parent,
            title="Speak Dropbox Keyboard Shortcuts",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetSize((580, 420))
        helper = BoxSizerHelper(self, wx.VERTICAL)

        shortcuts_data = [
            (f"{modifier}+1 through {modifier}+9", "Speak status of monitored source in Slot 1-9"),
            (f"Double-press {modifier}+1..9", "Copy that slot's status text to the clipboard"),
            (f"{modifier}+0", "Speak summary of all active monitored sources"),
            (f"{modifier}+M", "Open Manage Monitored Sources & Settings dialog"),
            ("Win+B then Enter / Context Key", "Open Speak Dropbox system tray menu"),
            ("Alt+A (in Manage Sources)", "Add source from currently detected tray icons"),
            ("Alt+K (in Manage Sources)", "Add a custom keyword source rule"),
            ("Alt+U / Alt+D (in Manage Sources)", "Move selected source slot Up or Down"),
            ("Alt+R (in Manage Sources)", "Remove or disable selected source"),
            ("F1", "Open this Keyboard Shortcuts Reference"),
            ("Escape", "Close current dialog"),
        ]

        _, self.list_ctrl = helper.add_labeled_control(
            "&Available Keyboard Shortcuts:",
            wx.ListCtrl,
            proportion=1,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
        )
        self.list_ctrl.InsertColumn(0, "Shortcut", width=230)
        self.list_ctrl.InsertColumn(1, "Action", width=310)

        for idx, (keys, desc) in enumerate(shortcuts_data):
            row = self.list_ctrl.InsertItem(idx, keys)
            self.list_ctrl.SetItem(row, 1, desc)

        if shortcuts_data:
            self.list_ctrl.Select(0)
            self.list_ctrl.Focus(0)

        btn_sizer = self.CreateButtonSizer(wx.OK)
        if btn_sizer:
            helper.add_item(btn_sizer, flag=wx.ALIGN_RIGHT | wx.ALL, border=10)

        self.SetSizer(helper.sizer)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()
