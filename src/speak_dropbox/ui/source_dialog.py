"""Accessible multi-tab Manage Monitored Sources & Settings dialog."""

from __future__ import annotations

from collections.abc import Callable
import copy
import wx

from speak_dropbox.config import AppConfig
from speak_dropbox.core.monitor import TrayMonitorService
from speak_dropbox.models import SourceRule
from speak_dropbox.services.audio import AudioCueService
from speak_dropbox.services.hotkey import SUPPORTED_MODIFIER_PRESETS, normalize_modifier_display
from speak_dropbox.ui.gui_helper import BoxSizerHelper, ShortcutReferenceDialog
from speak_dropbox.ui.tray_picker_dialog import CustomSourceRuleDialog, DetectTrayIconsDialog


class ManageSourcesDialog(wx.Dialog):
    """Accessible configuration dialog for managing monitored tray sources, speech, audio, and hotkeys."""

    def __init__(
        self,
        parent: wx.Window | None,
        config: AppConfig,
        monitor: TrayMonitorService,
        audio_service: AudioCueService | None = None,
        *,
        on_apply_callback: Callable[[AppConfig], None] | None = None,
    ) -> None:
        super().__init__(
            parent,
            title="Speak Dropbox - Manage Sources & Settings",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetSize((760, 540))
        self.working_config = copy.deepcopy(config)
        self.monitor = monitor
        self.audio_service = audio_service
        self._on_apply_callback = on_apply_callback

        main_helper = BoxSizerHelper(self, wx.VERTICAL)
        self.notebook = wx.Notebook(self)
        self.notebook.SetName("Settings Categories")

        self.sources_panel = self._build_sources_tab(self.notebook)
        self.speech_audio_panel = self._build_speech_audio_tab(self.notebook)
        self.hotkeys_panel = self._build_hotkeys_general_tab(self.notebook)

        self.notebook.AddPage(self.sources_panel, "Monitored Sources")
        self.notebook.AddPage(self.speech_audio_panel, "Speech && Audio Cues")
        self.notebook.AddPage(self.hotkeys_panel, "Hotkeys && General")

        main_helper.add_item(self.notebook, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)

        footer_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.shortcuts_btn = wx.Button(self, label="&Keyboard Shortcuts (F1)")
        self.shortcuts_btn.SetName("Keyboard Shortcuts (F1)")
        self.shortcuts_btn.Bind(wx.EVT_BUTTON, lambda _e: self.show_shortcut_reference())
        footer_sizer.Add(self.shortcuts_btn, 0, wx.RIGHT, 12)
        footer_sizer.AddStretchSpacer(1)

        std_btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        if std_btns:
            footer_sizer.Add(std_btns, 0, wx.EXPAND)

        main_helper.add_item(
            footer_sizer,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=10,
        )

        self.SetSizer(main_helper.sizer)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
        self.refresh_sources_list()

    def _build_sources_tab(self, parent: wx.Notebook) -> wx.Panel:
        panel = wx.Panel(parent)
        helper = BoxSizerHelper(panel, wx.VERTICAL)

        _, self.sources_list = helper.add_labeled_control(
            "&Configured Cloud and System Tray Sources:",
            wx.ListCtrl,
            proportion=1,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
        )
        self.sources_list.InsertColumn(0, "Slot", width=70)
        self.sources_list.InsertColumn(1, "Source Name", width=150)
        self.sources_list.InsertColumn(2, "Enabled", width=75)
        self.sources_list.InsertColumn(3, "Keywords", width=155)
        self.sources_list.InsertColumn(4, "Live Tray Status", width=250)

        btn_row1 = wx.BoxSizer(wx.HORIZONTAL)
        self.add_from_tray_btn = wx.Button(panel, label="&Add from System Tray...")
        self.add_custom_btn = wx.Button(panel, label="Add Custom &Keyword...")
        self.edit_source_btn = wx.Button(panel, label="&Edit Source...")
        self.toggle_source_btn = wx.Button(panel, label="&Toggle Enabled")

        for btn in (
            self.add_from_tray_btn,
            self.add_custom_btn,
            self.edit_source_btn,
            self.toggle_source_btn,
        ):
            btn.SetName(btn.GetLabel().replace("&", ""))
            btn_row1.Add(btn, 0, wx.RIGHT, 6)

        btn_row2 = wx.BoxSizer(wx.HORIZONTAL)
        self.move_up_btn = wx.Button(panel, label="Move &Up")
        self.move_down_btn = wx.Button(panel, label="Move &Down")
        self.remove_source_btn = wx.Button(panel, label="&Remove Source")

        for btn in (self.move_up_btn, self.move_down_btn, self.remove_source_btn):
            btn.SetName(btn.GetLabel().replace("&", ""))
            btn_row2.Add(btn, 0, wx.RIGHT, 6)

        helper.add_item(btn_row1, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=6)
        helper.add_item(btn_row2, flag=wx.ALL, border=6)

        self.add_from_tray_btn.Bind(wx.EVT_BUTTON, self._on_add_from_tray)
        self.add_custom_btn.Bind(wx.EVT_BUTTON, self._on_add_custom_source)
        self.edit_source_btn.Bind(wx.EVT_BUTTON, self._on_edit_source)
        self.toggle_source_btn.Bind(wx.EVT_BUTTON, self._on_toggle_source)
        self.move_up_btn.Bind(wx.EVT_BUTTON, lambda _e: self._on_move_source(-1))
        self.move_down_btn.Bind(wx.EVT_BUTTON, lambda _e: self._on_move_source(1))
        self.remove_source_btn.Bind(wx.EVT_BUTTON, self._on_remove_source)

        panel.SetSizer(helper.sizer)
        return panel

    def _build_speech_audio_tab(self, parent: wx.Notebook) -> wx.Panel:
        panel = wx.Panel(parent)
        helper = BoxSizerHelper(panel, wx.VERTICAL)

        speech_box = wx.StaticBoxSizer(
            wx.VERTICAL,
            panel,
            "Screen Reader Speech Output (Prism)",
        )
        self.chk_enable_speech = wx.CheckBox(
            panel,
            label="&Enable screen reader speech and braille announcements",
        )
        self.chk_speak_start = wx.CheckBox(
            panel,
            label="Speak when syncing or indexing &starts",
        )
        self.chk_speak_finish = wx.CheckBox(
            panel,
            label="Speak when syncing &finishes (Up to date)",
        )
        self.chk_speak_error = wx.CheckBox(
            panel,
            label="Speak on sync &errors, paused, or disconnected states",
        )
        self.chk_speak_appear = wx.CheckBox(
            panel,
            label="Speak when monitored sources &appear or close",
        )
        self.chk_strip_unread = wx.CheckBox(
            panel,
            label="Strip &unread notification counts from Dropbox idle status",
        )

        self.chk_enable_speech.SetValue(self.working_config.enable_speech)
        self.chk_speak_start.SetValue(self.working_config.speak_on_start_sync)
        self.chk_speak_finish.SetValue(self.working_config.speak_on_finish_sync)
        self.chk_speak_error.SetValue(self.working_config.speak_on_error_or_pause)
        self.chk_speak_appear.SetValue(self.working_config.speak_on_appear_disappear)
        self.chk_strip_unread.SetValue(self.working_config.strip_unread_notifications)

        for chk in (
            self.chk_enable_speech,
            self.chk_speak_start,
            self.chk_speak_finish,
            self.chk_speak_error,
            self.chk_speak_appear,
            self.chk_strip_unread,
        ):
            chk.SetName(chk.GetLabel().replace("&", ""))
            speech_box.Add(chk, 0, wx.ALL, 4)

        helper.add_item(speech_box, flag=wx.EXPAND | wx.ALL, border=8)

        audio_box = wx.StaticBoxSizer(
            wx.VERTICAL,
            panel,
            "Three-Stage Sync Earcons (start.flac, loopty.flac, finish.flac)",
        )
        self.chk_enable_sounds = wx.CheckBox(
            panel,
            label="&Play start and finish audio cues when sync state changes",
        )
        self.chk_enable_loop = wx.CheckBox(
            panel,
            label="Play sustain &loop sound while syncing is active (loopty.flac)",
        )
        self.chk_enable_sounds.SetValue(self.working_config.enable_sounds)
        self.chk_enable_loop.SetValue(self.working_config.enable_loop_sound)
        self.chk_enable_sounds.SetName(self.chk_enable_sounds.GetLabel().replace("&", ""))
        self.chk_enable_loop.SetName(self.chk_enable_loop.GetLabel().replace("&", ""))
        audio_box.Add(self.chk_enable_sounds, 0, wx.ALL, 4)
        audio_box.Add(self.chk_enable_loop, 0, wx.ALL, 4)

        loop_row = wx.BoxSizer(wx.HORIZONTAL)
        loop_lbl = wx.StaticText(panel, label="Sustain &Loop Interval (seconds):")
        self.spin_loop_interval = wx.SpinCtrlDouble(
            panel,
            min=0.5,
            max=30.0,
            initial=self.working_config.loop_interval_seconds,
            inc=0.5,
        )
        self.spin_loop_interval.SetDigits(1)
        self.spin_loop_interval.SetName("Sustain Loop Interval (seconds)")
        loop_row.Add(loop_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        loop_row.Add(self.spin_loop_interval, 0, wx.ALIGN_CENTER_VERTICAL)
        audio_box.Add(loop_row, 0, wx.ALL, 6)

        test_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_test_start = wx.Button(panel, label="Preview &Start Cue")
        self.btn_test_loop = wx.Button(panel, label="Preview L&oop Cue")
        self.btn_test_finish = wx.Button(panel, label="Preview &Finish Cue")
        for btn in (self.btn_test_start, self.btn_test_loop, self.btn_test_finish):
            btn.SetName(btn.GetLabel().replace("&", ""))
            test_btn_row.Add(btn, 0, wx.RIGHT, 6)
        audio_box.Add(test_btn_row, 0, wx.ALL, 6)

        self.btn_test_start.Bind(wx.EVT_BUTTON, lambda _e: self._preview_sound("start"))
        self.btn_test_loop.Bind(wx.EVT_BUTTON, lambda _e: self._preview_sound("loop"))
        self.btn_test_finish.Bind(wx.EVT_BUTTON, lambda _e: self._preview_sound("finish"))

        helper.add_item(audio_box, flag=wx.EXPAND | wx.ALL, border=8)
        panel.SetSizer(helper.sizer)
        return panel

    def _build_hotkeys_general_tab(self, parent: wx.Notebook) -> wx.Panel:
        panel = wx.Panel(parent)
        helper = BoxSizerHelper(panel, wx.VERTICAL)

        presets = list(SUPPORTED_MODIFIER_PRESETS)
        current_mod = normalize_modifier_display(self.working_config.hotkey_modifier)
        if current_mod not in presets:
            presets.insert(0, current_mod)

        _, self.modifier_choice = helper.add_labeled_control(
            "&Global Slot Hotkey Modifier (press Modifier + 1..9 to speak Slot 1..9):",
            wx.Choice,
            choices=presets,
        )
        self.modifier_choice.SetSelection(presets.index(current_mod))
        self.modifier_choice.Bind(wx.EVT_CHOICE, self._on_modifier_changed)

        _, self.summary_hotkey_input = helper.add_labeled_control(
            "Speak &All Active Sources Summary Hotkey:",
            wx.TextCtrl,
            value=self.working_config.summary_hotkey,
        )
        _, self.manage_hotkey_input = helper.add_labeled_control(
            "Open &Manage Sources & Settings Hotkey:",
            wx.TextCtrl,
            value=self.working_config.manage_hotkey,
        )

        _, self.spin_poll_interval = helper.add_labeled_control(
            "System Tray Background &Poll Interval (seconds):",
            wx.SpinCtrlDouble,
            min=0.5,
            max=30.0,
            initial=self.working_config.poll_interval_seconds,
            inc=0.5,
        )
        self.spin_poll_interval.SetDigits(1)

        self.chk_run_on_startup = wx.CheckBox(
            panel,
            label="&Run Speak Dropbox automatically on system startup",
        )
        self.chk_run_on_startup.SetValue(self.working_config.run_on_startup)
        self.chk_run_on_startup.SetName("Run Speak Dropbox automatically on system startup")
        helper.add_item(self.chk_run_on_startup, flag=wx.ALL, border=8)

        panel.SetSizer(helper.sizer)
        return panel

    def refresh_sources_list(self, select_index: int | None = None) -> None:
        """Populate the sources ListCtrl with current rules and live tray statuses."""
        active_by_id = {s.source_id: s for s in self.monitor.get_active_slots()}
        self.sources_list.DeleteAllItems()

        for idx, rule in enumerate(self.working_config.sources):
            live = active_by_id.get(rule.id)
            if live is not None:
                slot_text = f"Slot {live.slot}"
                status_text = f"{live.spoken_text} ({live.location.display_label})"
            elif rule.pinned_slot is not None:
                slot_text = f"Pin {rule.pinned_slot}"
                status_text = "Not currently in tray"
            else:
                slot_text = f"#{idx + 1}"
                status_text = "Not currently in tray"

            row = self.sources_list.InsertItem(idx, slot_text)
            self.sources_list.SetItem(row, 1, rule.display_name)
            self.sources_list.SetItem(row, 2, "Yes" if rule.enabled else "No")
            self.sources_list.SetItem(row, 3, ", ".join(rule.keywords))
            self.sources_list.SetItem(row, 4, status_text)

        count = len(self.working_config.sources)
        if count > 0:
            target = select_index if (select_index is not None and 0 <= select_index < count) else 0
            self.sources_list.Select(target)
            self.sources_list.Focus(target)

    def get_selected_source_index(self) -> int:
        return self.sources_list.GetFirstSelected()

    def get_selected_rule(self) -> SourceRule | None:
        idx = self.get_selected_source_index()
        if 0 <= idx < len(self.working_config.sources):
            return self.working_config.sources[idx]
        return None

    def _on_add_from_tray(self, _event: wx.CommandEvent) -> None:
        self.monitor.poll()
        candidates = self.monitor.get_unmonitored_icons() or self.monitor.get_all_discovered_icons()
        dlg = DetectTrayIconsDialog(
            self,
            candidates,
            rescan_callback=lambda: (
                self.monitor.poll(),
                self.monitor.get_unmonitored_icons() or self.monitor.get_all_discovered_icons(),
            )[1],
        )
        try:
            if dlg.ShowModal() == wx.ID_OK:
                new_rule = dlg.get_created_rule()
                if new_rule is not None:
                    self.working_config.add_or_update_source(new_rule)
                    self.refresh_sources_list(len(self.working_config.sources) - 1)
        finally:
            dlg.Destroy()

    def _on_add_custom_source(self, _event: wx.CommandEvent) -> None:
        dlg = CustomSourceRuleDialog(self)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                rule = dlg.get_rule()
                if rule is not None:
                    self.working_config.add_or_update_source(rule)
                    self.refresh_sources_list(len(self.working_config.sources) - 1)
        finally:
            dlg.Destroy()

    def _on_edit_source(self, _event: wx.CommandEvent) -> None:
        idx = self.get_selected_source_index()
        rule = self.get_selected_rule()
        if rule is None:
            return
        dlg = CustomSourceRuleDialog(self, existing_rule=rule)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                updated = dlg.get_rule()
                if updated is not None:
                    self.working_config.sources[idx] = updated
                    self.refresh_sources_list(idx)
        finally:
            dlg.Destroy()

    def _on_toggle_source(self, _event: wx.CommandEvent) -> None:
        idx = self.get_selected_source_index()
        rule = self.get_selected_rule()
        if rule is None:
            return
        rule.enabled = not rule.enabled
        self.refresh_sources_list(idx)

    def _on_move_source(self, delta: int) -> None:
        idx = self.get_selected_source_index()
        rule = self.get_selected_rule()
        if rule is None:
            return
        if self.working_config.move_source(rule.id, delta):
            new_idx = max(0, min(len(self.working_config.sources) - 1, idx + delta))
            self.refresh_sources_list(new_idx)

    def _on_remove_source(self, _event: wx.CommandEvent) -> None:
        idx = self.get_selected_source_index()
        rule = self.get_selected_rule()
        if rule is None:
            return
        if self.working_config.remove_or_disable_source(rule.id):
            new_idx = min(idx, max(0, len(self.working_config.sources) - 1))
            self.refresh_sources_list(new_idx)

    def _on_modifier_changed(self, _event: wx.CommandEvent) -> None:
        sel = self.modifier_choice.GetSelection()
        if sel != wx.NOT_FOUND:
            mod = self.modifier_choice.GetString(sel)
            self.summary_hotkey_input.SetValue(f"{mod}+0")
            self.manage_hotkey_input.SetValue(f"{mod}+M")

    def _preview_sound(self, cue_type: str) -> None:
        if self.audio_service is None:
            return
        prev_enabled = self.audio_service.config.enable_sounds
        prev_loop = self.audio_service.config.enable_loop_sound
        try:
            self.audio_service.config.enable_sounds = True
            self.audio_service.config.enable_loop_sound = True
            if cue_type == "start":
                self.audio_service.play_start()
            elif cue_type == "loop":
                self.audio_service.play_loop()
            elif cue_type == "finish":
                self.audio_service.play_finish()
        finally:
            self.audio_service.config.enable_sounds = prev_enabled
            self.audio_service.config.enable_loop_sound = prev_loop

    def show_shortcut_reference(self) -> None:
        sel = self.modifier_choice.GetSelection()
        mod = (
            self.modifier_choice.GetString(sel)
            if sel != wx.NOT_FOUND
            else self.working_config.hotkey_modifier
        )
        dlg = ShortcutReferenceDialog(self, modifier=mod)
        try:
            dlg.ShowModal()
        finally:
            dlg.Destroy()

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        code = event.GetKeyCode()
        if code == wx.WXK_F1:
            self.show_shortcut_reference()
            return
        if code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()

    def apply_to_config(self) -> AppConfig:
        """Read all form controls into working_config and return it."""
        self.working_config.enable_speech = self.chk_enable_speech.GetValue()
        self.working_config.speak_on_start_sync = self.chk_speak_start.GetValue()
        self.working_config.speak_on_finish_sync = self.chk_speak_finish.GetValue()
        self.working_config.speak_on_error_or_pause = self.chk_speak_error.GetValue()
        self.working_config.speak_on_appear_disappear = self.chk_speak_appear.GetValue()
        self.working_config.strip_unread_notifications = self.chk_strip_unread.GetValue()

        self.working_config.enable_sounds = self.chk_enable_sounds.GetValue()
        self.working_config.enable_loop_sound = self.chk_enable_loop.GetValue()
        self.working_config.loop_interval_seconds = float(self.spin_loop_interval.GetValue())

        sel = self.modifier_choice.GetSelection()
        if sel != wx.NOT_FOUND:
            self.working_config.hotkey_modifier = self.modifier_choice.GetString(sel)
        self.working_config.summary_hotkey = (
            self.summary_hotkey_input.GetValue().strip()
            or f"{self.working_config.hotkey_modifier}+0"
        )
        self.working_config.manage_hotkey = (
            self.manage_hotkey_input.GetValue().strip()
            or f"{self.working_config.hotkey_modifier}+M"
        )
        self.working_config.poll_interval_seconds = float(self.spin_poll_interval.GetValue())
        self.working_config.run_on_startup = self.chk_run_on_startup.GetValue()
        return self.working_config

    def _on_ok(self, _event: wx.CommandEvent) -> None:
        updated = self.apply_to_config()
        if self._on_apply_callback is not None:
            self._on_apply_callback(updated)
        self.EndModal(wx.ID_OK)
