"""Accessible wx.adv.TaskBarIcon system tray integration and dynamic context menu."""

from __future__ import annotations

from collections.abc import Callable
import logging
import sys
import wx
import wx.adv

logger = logging.getLogger(__name__)


from speak_sync.config import AppConfig
from speak_sync.macos_support import (
    describe_all_windows_and_screens,
    describe_status_item_state,
    hide_host_window_from_users,
    label_status_item_for_voiceover,
)
from speak_sync.core.folders import open_sync_folder, resolve_sync_folder
from speak_sync.core.monitor import TrayMonitorService
from speak_sync.models import SourceRule, TrayIconItem
from speak_sync.services.hotkey import normalize_modifier_display
from speak_sync.ui.icon_gen import create_tray_icon
from speak_sync.ui.tray_picker_dialog import infer_app_name_and_keyword, make_source_id


class SpeakSyncTrayIcon(wx.adv.TaskBarIcon):
    """System tray icon with dynamic source submenus, quick-add tray scanner, and checkable toggles."""

    def __init__(
        self,
        *,
        config: AppConfig,
        monitor: TrayMonitorService,
        on_speak_slot: Callable[[int], None],
        on_copy_slot: Callable[[int], None],
        on_speak_summary: Callable[[], None],
        on_open_manage_dialog: Callable[[], None],
        on_open_shortcuts_dialog: Callable[[], None],
        on_config_mutated: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> None:
        icon_type = (
            wx.adv.TBI_CUSTOM_STATUSITEM
            if hasattr(wx.adv, "TBI_CUSTOM_STATUSITEM")
            else wx.adv.TBI_DEFAULT_TYPE
        )
        super().__init__(iconType=icon_type)
        self.config = config
        self.monitor = monitor
        self._on_speak_slot = on_speak_slot
        self._on_copy_slot = on_copy_slot
        self._on_speak_summary = on_speak_summary
        self._on_open_manage_dialog = on_open_manage_dialog
        self._on_open_shortcuts_dialog = on_open_shortcuts_dialog
        self._on_config_mutated = on_config_mutated
        self._on_exit = on_exit

        self._current_mode: str = ""
        self._current_tooltip: str = ""
        self.update_icon_and_tooltip()

        if sys.platform == "darwin":
            # The status item window only exists once the run loop is going, so label it a little later.
            wx.CallLater(300, self._finish_macos_status_item_setup)
        else:
            self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self._on_left_click)

    def _finish_macos_status_item_setup(self) -> None:
        """Label the status item for VoiceOver and log its state so a tester log shows whether it exists."""
        labelled = label_status_item_for_voiceover("SpeakSync")
        hide_host_window_from_users()
        logger.info("Status item labelled=%s state: %s", labelled, describe_status_item_state())
        logger.info("App windows and screens: %s", describe_all_windows_and_screens())
        wx.CallLater(4000, lambda: logger.info("Later state: %s", describe_all_windows_and_screens()))

    def _determine_mode(self) -> str:
        if self.monitor.has_active_transfer():
            return "syncing"
        if self.monitor.has_problem_state():
            return "problem"
        return "idle"

    def update_icon_and_tooltip(self) -> None:
        """Refresh the tray icon graphic and tooltip only if state or summary changed."""
        mode = self._determine_mode()
        tooltip = self.monitor.format_tray_tooltip_summary()
        if mode == self._current_mode and tooltip == self._current_tooltip:
            return
        self._current_mode = mode
        self._current_tooltip = tooltip
        try:
            size = 22 if sys.platform == "darwin" else 32
            icon = create_tray_icon(status_mode=mode, size=size)
            success = self.SetIcon(icon, tooltip)
            if not success:
                logger.warning("wx.adv.TaskBarIcon.SetIcon returned False")
            if sys.platform == "darwin":
                label_status_item_for_voiceover("SpeakSync")
        except Exception as exc:
            logger.exception("Failed to update tray icon: %s", exc)

    def _on_left_click(self, _event: wx.adv.TaskBarIconEvent) -> None:
        self._on_speak_summary()

    def CreatePopupMenu(self) -> wx.Menu:  # noqa: N802 (wxPython method override)
        """Build the accessible right-click context menu showing all active sources and controls."""
        return self.build_context_menu()

    def build_context_menu(self) -> wx.Menu:
        """Construct and return the context menu with live source submenus and quick toggles."""
        menu = wx.Menu()
        mod = normalize_modifier_display(self.config.hotkey_modifier)
        active_slots = self.monitor.get_active_slots()

        # 1. Active Monitored Sources
        if active_slots:
            for status in active_slots:
                submenu = wx.Menu()
                slot_num = status.slot
                source_id = status.source_id

                speak_item = submenu.Append(
                    wx.ID_ANY,
                    f"&Speak Status Now\t{mod}+{slot_num}",
                )
                copy_item = submenu.Append(
                    wx.ID_ANY,
                    "&Copy Status Text to Clipboard",
                )
                folder = resolve_sync_folder(status.source_id, status.display_name)
                if folder is not None:
                    open_folder_item = submenu.Append(
                        wx.ID_ANY,
                        f"&Open Local Sync Folder ({folder.name})",
                    )
                    menu.Bind(
                        wx.EVT_MENU,
                        lambda _e, p=folder: open_sync_folder(p),
                        open_folder_item,
                    )
                submenu.AppendSeparator()
                up_item = submenu.Append(wx.ID_ANY, "Move Slot &Up")
                down_item = submenu.Append(wx.ID_ANY, "Move Slot &Down")
                submenu.AppendSeparator()
                remove_item = submenu.Append(
                    wx.ID_ANY,
                    f"&Remove {status.display_name} from Monitored Sources",
                )

                menu.Bind(
                    wx.EVT_MENU,
                    lambda _e, s=slot_num: self._on_speak_slot(s),
                    speak_item,
                )
                menu.Bind(
                    wx.EVT_MENU,
                    lambda _e, s=slot_num: self._on_copy_slot(s),
                    copy_item,
                )
                menu.Bind(
                    wx.EVT_MENU,
                    lambda _e, sid=source_id: self._move_source_in_menu(sid, -1),
                    up_item,
                )
                menu.Bind(
                    wx.EVT_MENU,
                    lambda _e, sid=source_id: self._move_source_in_menu(sid, 1),
                    down_item,
                )
                menu.Bind(
                    wx.EVT_MENU,
                    lambda _e, sid=source_id: self._remove_source_in_menu(sid),
                    remove_item,
                )

                label = (
                    f"&{slot_num}. {status.spoken_text} "
                    f"({status.location.display_label})\t{mod}+{slot_num}"
                )
                menu.AppendSubMenu(submenu, label)
        else:
            empty_item = menu.Append(wx.ID_ANY, "No monitored sources currently running")
            empty_item.Enable(False)

        # 2. Quick-Add from Unmonitored System Tray Icons
        unmonitored = self.monitor.get_unmonitored_icons()
        if unmonitored:
            quick_add_menu = wx.Menu()
            for icon_item in unmonitored[:15]:
                display, _ = infer_app_name_and_keyword(icon_item.cleaned_tooltip)
                item_lbl = f"Add {display} ({icon_item.location.display_label})"
                add_item = quick_add_menu.Append(wx.ID_ANY, item_lbl)
                menu.Bind(
                    wx.EVT_MENU,
                    lambda _e, it=icon_item: self._quick_add_icon_source(it),
                    add_item,
                )
            menu.AppendSubMenu(quick_add_menu, "&Quick Add from System Tray")

        menu.AppendSeparator()

        # 3. Primary Actions
        speak_all_item = menu.Append(
            wx.ID_ANY,
            f"Speak &All Statuses Now\t{self.config.summary_hotkey}",
        )
        manage_item = menu.Append(
            wx.ID_ANY,
            f"&Manage Sources && Settings...\t{self.config.manage_hotkey}",
        )
        menu.Bind(wx.EVT_MENU, lambda _e: self._on_speak_summary(), speak_all_item)
        menu.Bind(wx.EVT_MENU, lambda _e: self._on_open_manage_dialog(), manage_item)

        menu.AppendSeparator()

        # 4. Checkable Toggles
        chk_speech = menu.AppendCheckItem(wx.ID_ANY, "Speak Status &Changes")
        chk_speech.Check(self.config.enable_speech)
        menu.Bind(wx.EVT_MENU, self._toggle_speech, chk_speech)

        chk_sounds = menu.AppendCheckItem(wx.ID_ANY, "Play &Start and Finish Sounds")
        chk_sounds.Check(self.config.enable_sounds)
        menu.Bind(wx.EVT_MENU, self._toggle_sounds, chk_sounds)

        chk_loop = menu.AppendCheckItem(wx.ID_ANY, "Play &Looping Sound While Syncing")
        chk_loop.Check(self.config.enable_loop_sound)
        menu.Bind(wx.EVT_MENU, self._toggle_loop_sound, chk_loop)

        chk_startup = menu.AppendCheckItem(wx.ID_ANY, "&Run on System Startup")
        chk_startup.Check(self.config.run_on_startup)
        menu.Bind(wx.EVT_MENU, self._toggle_startup, chk_startup)

        menu.AppendSeparator()

        shortcuts_item = menu.Append(wx.ID_ANY, "&Keyboard Shortcuts Reference\tF1")
        exit_item = menu.Append(wx.ID_EXIT, "E&xit")
        menu.Bind(wx.EVT_MENU, lambda _e: self._on_open_shortcuts_dialog(), shortcuts_item)
        menu.Bind(wx.EVT_MENU, lambda _e: self._on_exit(), exit_item)

        return menu

    def _move_source_in_menu(self, source_id: str, delta: int) -> None:
        if self.config.move_source(source_id, delta):
            self._on_config_mutated()

    def _remove_source_in_menu(self, source_id: str) -> None:
        if self.config.remove_or_disable_source(source_id):
            self._on_config_mutated()

    def _quick_add_icon_source(self, item: TrayIconItem) -> None:
        display, keyword = infer_app_name_and_keyword(item.cleaned_tooltip)
        rule = SourceRule(
            id=make_source_id(display),
            display_name=display,
            keywords=[keyword],
            enabled=True,
            builtin=False,
        )
        self.config.add_or_update_source(rule)
        self._on_config_mutated()

    def _toggle_speech(self, _event: wx.CommandEvent) -> None:
        self.config.enable_speech = not self.config.enable_speech
        self._on_config_mutated()

    def _toggle_sounds(self, _event: wx.CommandEvent) -> None:
        self.config.enable_sounds = not self.config.enable_sounds
        self._on_config_mutated()

    def _toggle_loop_sound(self, _event: wx.CommandEvent) -> None:
        self.config.enable_loop_sound = not self.config.enable_loop_sound
        self._on_config_mutated()

    def _toggle_startup(self, _event: wx.CommandEvent) -> None:
        self.config.run_on_startup = not self.config.run_on_startup
        self._on_config_mutated()
