"""Accessible dialogs for picking a source from live visible/hidden tray icons or adding custom keyword rules."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import re
import wx

from speak_dropbox.models import SourceRule, TrayIconItem
from speak_dropbox.ui.gui_helper import BoxSizerHelper

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def infer_app_name_and_keyword(cleaned_tooltip: str) -> tuple[str, str]:
    """Infer a concise display name and keyword from a cleaned tray tooltip string."""
    if not cleaned_tooltip.strip():
        return "Custom App", "custom"
    head = cleaned_tooltip.split(" - ")[0].split(":")[0].strip()
    # Strip trailing version number if present (e.g. 'Dropbox 274.4.4841' -> 'Dropbox')
    tokens = head.split()
    if len(tokens) > 1 and any(ch.isdigit() for ch in tokens[-1]):
        head = " ".join(tokens[:-1]).strip()
    display = head or cleaned_tooltip[:30].strip()
    return display, display.lower()


def make_source_id(display_name: str) -> str:
    slug = _SLUG_RE.sub("_", display_name.lower()).strip("_")
    return slug or "custom_source"


class DetectTrayIconsDialog(wx.Dialog):
    """Dialog that lists live visible and hidden tray icons so the user can add any app as a monitored source."""

    def __init__(
        self,
        parent: wx.Window | None,
        icons: Sequence[TrayIconItem],
        *,
        rescan_callback: Callable[[], Sequence[TrayIconItem]] | None = None,
    ) -> None:
        super().__init__(
            parent,
            title="Add Source from Detected System Tray Icons",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetSize((640, 440))
        self._icons: list[TrayIconItem] = list(icons)
        self._rescan_callback = rescan_callback

        helper = BoxSizerHelper(self, wx.VERTICAL)

        _, self.icon_list = helper.add_labeled_control(
            "&Detected System Tray Icons (Visible and Hidden Tray):",
            wx.ListCtrl,
            proportion=1,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
        )
        self.icon_list.InsertColumn(0, "Tray Tooltip / Application", width=440)
        self.icon_list.InsertColumn(1, "Location", width=150)

        if self._rescan_callback is not None:
            self.refresh_btn = wx.Button(self, label="&Refresh Tray List")
            self.refresh_btn.SetName("Refresh Tray List")
            helper.add_item(self.refresh_btn, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=6)
            self.refresh_btn.Bind(wx.EVT_BUTTON, self._on_refresh)

        _, self.name_input = helper.add_labeled_control(
            "Source &Display Name:",
            wx.TextCtrl,
        )
        _, self.keyword_input = helper.add_labeled_control(
            "Matching &Keyword:",
            wx.TextCtrl,
        )

        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        if btn_sizer:
            helper.add_item(btn_sizer, flag=wx.ALIGN_RIGHT | wx.ALL, border=10)

        self.SetSizer(helper.sizer)
        self.icon_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)
        self._populate_list()

    def _populate_list(self) -> None:
        self.icon_list.DeleteAllItems()
        for idx, item in enumerate(self._icons):
            row = self.icon_list.InsertItem(idx, item.cleaned_tooltip)
            self.icon_list.SetItem(row, 1, item.location.display_label)
        if self._icons:
            self.icon_list.Select(0)
            self.icon_list.Focus(0)
            self._update_fields_from_index(0)

    def _update_fields_from_index(self, index: int) -> None:
        if 0 <= index < len(self._icons):
            display, keyword = infer_app_name_and_keyword(self._icons[index].cleaned_tooltip)
            self.name_input.SetValue(display)
            self.keyword_input.SetValue(keyword)

    def _on_item_selected(self, event: wx.ListEvent) -> None:
        self._update_fields_from_index(event.GetIndex())

    def _on_refresh(self, _event: wx.CommandEvent) -> None:
        if self._rescan_callback is not None:
            self._icons = list(self._rescan_callback())
            self._populate_list()

    def get_created_rule(self) -> SourceRule | None:
        display = self.name_input.GetValue().strip()
        keyword = self.keyword_input.GetValue().strip()
        if not display or not keyword:
            return None
        return SourceRule(
            id=make_source_id(display),
            display_name=display,
            keywords=[k.strip() for k in keyword.split(",") if k.strip()],
            enabled=True,
            builtin=False,
        )


class CustomSourceRuleDialog(wx.Dialog):
    """Dialog for adding or editing a custom keyword-based source rule."""

    def __init__(
        self,
        parent: wx.Window | None,
        existing_rule: SourceRule | None = None,
    ) -> None:
        title = "Edit Monitored Source" if existing_rule else "Add Custom Keyword Source"
        super().__init__(
            parent,
            title=title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetSize((460, 320))
        self._existing = existing_rule

        helper = BoxSizerHelper(self, wx.VERTICAL)
        _, self.name_input = helper.add_labeled_control(
            "Source &Display Name:",
            wx.TextCtrl,
            value=existing_rule.display_name if existing_rule else "",
        )
        _, self.keywords_input = helper.add_labeled_control(
            "Matching &Keywords (comma-separated):",
            wx.TextCtrl,
            value=", ".join(existing_rule.keywords) if existing_rule else "",
        )

        slot_choices = ["Automatic (Next Available Slot)"] + [f"Slot {i}" for i in range(1, 10)]
        _, self.slot_choice = helper.add_labeled_control(
            "&Pinned Slot Number:",
            wx.Choice,
            choices=slot_choices,
        )
        if existing_rule and existing_rule.pinned_slot and 1 <= existing_rule.pinned_slot <= 9:
            self.slot_choice.SetSelection(existing_rule.pinned_slot)
        else:
            self.slot_choice.SetSelection(0)

        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        if btn_sizer:
            helper.add_item(btn_sizer, flag=wx.ALIGN_RIGHT | wx.ALL, border=10)

        self.SetSizer(helper.sizer)

    def get_rule(self) -> SourceRule | None:
        display = self.name_input.GetValue().strip()
        raw_kw = self.keywords_input.GetValue().strip()
        keywords = [k.strip() for k in raw_kw.split(",") if k.strip()]
        if not display or not keywords:
            return None
        sel = self.slot_choice.GetSelection()
        pinned_slot = sel if (sel != wx.NOT_FOUND and sel >= 1) else None
        source_id = self._existing.id if self._existing else make_source_id(display)
        builtin = self._existing.builtin if self._existing else False
        return SourceRule(
            id=source_id,
            display_name=display,
            keywords=keywords,
            enabled=True,
            pinned_slot=pinned_slot,
            builtin=builtin,
        )
