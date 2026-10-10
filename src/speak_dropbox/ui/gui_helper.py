"""Accessible wxPython layout helpers modeled after NVDA's guiHelper and F1 shortcut reference dialog."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import re
import sys
from typing import Any
import wx

_PROPID_ACC_NAME_GUID = "{608D3DF8-8128-4AA7-A428-F55E49267291}"
_OBJID_CLIENT = 0xFFFFFFFC
_MNEMONIC_RE = re.compile(r"&(&)|&(?=\S)")
_acc_prop_services: Any = None


def _get_acc_prop_services() -> Any:
    """Return cached COM IAccPropServices instance on Windows for UIA Dynamic Annotation."""
    global _acc_prop_services
    if sys.platform != "win32":
        return None
    if _acc_prop_services is not None:
        return _acc_prop_services
    try:
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        comtypes.client.GetModule("oleacc.dll")
        from comtypes.gen import Accessibility

        _acc_prop_services = comtypes.client.CreateObject(
            Accessibility.CAccPropServices,
            interface=Accessibility.IAccPropServices,
        )
    except Exception:
        _acc_prop_services = None
    return _acc_prop_services


def set_accessible_name(ctrl: wx.Window, name: str) -> str:
    """Set the accessible name on a wx.Window and annotate its Win32 HWND(s) for Windows UIA.

    Composite controls like wx.SpinCtrlDouble create internal Win32 Edit and msctls_updown32
    child HWNDs that do not inherit wx.Window.SetName() without IAccPropServices annotation.
    """
    clean_name = _MNEMONIC_RE.sub(lambda m: "&" if m.group(1) else "", name).rstrip(":").strip()
    ctrl.SetName(clean_name)
    if sys.platform == "win32":
        hwnd = int(ctrl.GetHandle() or 0)
        acc_srv = _get_acc_prop_services()
        if hwnd and acc_srv is not None:
            try:
                import comtypes

                prop_id = comtypes.GUID(_PROPID_ACC_NAME_GUID)
                acc_srv.SetHwndPropStr(hwnd, _OBJID_CLIENT, 0, prop_id, clean_name)
                if isinstance(ctrl, (wx.SpinCtrl, wx.SpinCtrlDouble)):
                    user32 = ctypes.windll.user32
                    enum_proc_t = ctypes.WINFUNCTYPE(
                        wintypes.BOOL,
                        wintypes.HWND,
                        wintypes.LPARAM,
                    )

                    def _annotate_child(child_hwnd: int, _lparam: int) -> bool:
                        try:
                            acc_srv.SetHwndPropStr(
                                int(child_hwnd),
                                _OBJID_CLIENT,
                                0,
                                prop_id,
                                clean_name,
                            )
                        except Exception:
                            pass
                        return True

                    user32.EnumChildWindows(hwnd, enum_proc_t(_annotate_child), 0)
            except Exception:
                pass
    return clean_name


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

        Also sets the control's accessible Name (stripping '&' mnemonic) and annotates its
        Win32 HWND so UIA screen readers announce the label reliably on focus.
        """
        label = wx.StaticText(self.parent, label=label_text)
        ctrl = control_cls(self.parent, **kwargs)
        set_accessible_name(ctrl, label_text)

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
        self.list_ctrl.InsertColumn(0, "Shortcut", width=self.FromDIP(240))
        self.list_ctrl.InsertColumn(1, "Action", width=self.FromDIP(340))
        self.list_ctrl.SetMinSize(self.FromDIP(wx.Size(600, 260)))

        for idx, (keys, desc) in enumerate(shortcuts_data):
            row = self.list_ctrl.InsertItem(idx, keys)
            self.list_ctrl.SetItem(row, 1, desc)

        if shortcuts_data:
            self.list_ctrl.Select(0)
            self.list_ctrl.Focus(0)

        btn_sizer = self.CreateButtonSizer(wx.OK)
        if btn_sizer:
            helper.add_item(btn_sizer, flag=wx.ALIGN_RIGHT | wx.ALL, border=10)

        self.SetSizerAndFit(helper.sizer)
        min_size = self.FromDIP(wx.Size(640, 420))
        cur_size = self.GetSize()
        self.SetSize(wx.Size(max(cur_size.width, min_size.width), max(cur_size.height, min_size.height)))
        self.SetMinSize(self.GetSize())
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()
