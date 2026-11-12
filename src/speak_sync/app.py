"""Main wxPython application controller orchestrating tray polling, Prism speech, audio cues, and hotkeys."""

from __future__ import annotations

import logging
from pathlib import Path
import sys
import threading
import wx

from speak_sync.backends import TrayBackend, create_tray_backend
from speak_sync.config import AppConfig
from speak_sync.core.autostart import set_autostart_enabled
from speak_sync.core.monitor import TrayMonitorService
from speak_sync.services.audio import AudioCueService
from speak_sync.services.hotkey import GlobalHotkeyService
from speak_sync.services.speech import SpeechService
from speak_sync.ui.gui_helper import ShortcutReferenceDialog
from speak_sync.ui.source_dialog import ManageSourcesDialog
from speak_sync.ui.tray import SpeakSyncTrayIcon

logger = logging.getLogger(__name__)


def copy_text_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard using wx.TheClipboard."""
    if not text:
        return False
    try:
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(text))
                wx.TheClipboard.Flush()
                return True
            finally:
                wx.TheClipboard.Close()
    except Exception as exc:
        logger.debug("Clipboard copy failed: %s", exc)
    return False


class SpeakSyncController(wx.EvtHandler):
    """Coordinates background tray polling, speech output, 3-stage audio cues, hotkeys, and UI."""

    def __init__(
        self,
        *,
        config: AppConfig | None = None,
        config_path: Path | None = None,
        backend: TrayBackend | None = None,
        speech_service: SpeechService | None = None,
        audio_service: AudioCueService | None = None,
        create_tray_ui: bool = True,
        register_hotkeys: bool = True,
    ) -> None:
        super().__init__()
        self.config_path = config_path
        self.config = config or AppConfig.load(config_path)
        candidate_procs = [r.display_name for r in self.config.sources]
        self.backend = backend or create_tray_backend(candidate_processes=candidate_procs)
        self.monitor = TrayMonitorService(self.backend, self.config)
        self.speech = speech_service or SpeechService(enabled=self.config.enable_speech)
        self.audio = audio_service or AudioCueService(self.config)

        self.hotkeys = GlobalHotkeyService(
            on_slot_hotkey=self.on_slot_hotkey_triggered,
            on_summary_hotkey=self.speak_summary,
            on_manage_hotkey=self.open_manage_dialog,
            ui_dispatcher=wx.CallAfter if wx.App.Get() is not None else None,
        )

        self.tray_icon: SpeakSyncTrayIcon | None = None
        self._poll_timer: wx.Timer | None = None
        self._manage_dialog_open: bool = False
        self._shortcuts_dialog_open: bool = False
        self._is_polling: bool = False
        self._poll_lock = threading.Lock()

        # Perform initial poll before constructing tray UI so initial slots are ready
        self.poll_once(is_initial=True)

        if (
            self.config.enable_speech
            and self.config.speak_startup_greeting
            and self.config.startup_greeting_text
        ):
            self.speech.output(self.config.startup_greeting_text, interrupt=False)

        if create_tray_ui and wx.App.Get() is not None:
            self.tray_icon = SpeakSyncTrayIcon(
                config=self.config,
                monitor=self.monitor,
                on_speak_slot=self.speak_slot,
                on_copy_slot=self.copy_slot,
                on_speak_summary=self.speak_summary,
                on_open_manage_dialog=self.open_manage_dialog,
                on_open_shortcuts_dialog=self.open_shortcuts_dialog,
                on_config_mutated=self.on_config_updated,
                on_exit=self.shutdown,
            )
            self._poll_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._on_timer_tick, self._poll_timer)
            self._start_poll_timer()

        if register_hotkeys:
            self.hotkeys.start(
                self.config.hotkey_modifier,
                self.config.summary_hotkey,
                self.config.manage_hotkey,
                wx_module=wx if wx.App.Get() is not None else None,
            )

        if sys.platform == "darwin" and wx.App.Get() is not None:
            wx.CallAfter(self._release_macos_windowless_focus)

    def _release_macos_windowless_focus(self) -> None:
        """Release any active keyboard/window focus if running purely as a status bar accessory."""
        if sys.platform != "darwin":
            return
        try:
            import ctypes
            import ctypes.util

            lib_path = ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib"
            objc = ctypes.cdll.LoadLibrary(lib_path)
            msg_send_addr = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
            objc.objc_getClass.restype = ctypes.c_void_p
            objc.objc_getClass.argtypes = [ctypes.c_char_p]
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]

            NSApplication = objc.objc_getClass(b"NSApplication")
            if not NSApplication:
                return
            sel_shared = objc.sel_registerName(b"sharedApplication")
            sel_deactivate = objc.sel_registerName(b"deactivate")
            proto = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
            ns_app = proto(msg_send_addr)(NSApplication, sel_shared)
            if ns_app:
                proto(msg_send_addr)(ns_app, sel_deactivate)
        except Exception as exc:
            logger.debug("Failed to release windowless focus: %s", exc)

    def _start_poll_timer(self) -> None:
        if self._poll_timer is None:
            return
        interval_ms = max(250, int(self.config.poll_interval_seconds * 1000))
        self._poll_timer.Start(interval_ms)

    def _on_timer_tick(self, _event: wx.TimerEvent) -> None:
        if self._manage_dialog_open or self._shortcuts_dialog_open:
            return
        self.trigger_async_poll()

    def trigger_async_poll(self) -> None:
        """Execute a poll cycle in a background worker thread so the wx GUI main thread never freezes."""
        with self._poll_lock:
            if self._is_polling:
                return
            self._is_polling = True

        threading.Thread(target=self._run_background_poll, daemon=True).start()

    def _run_background_poll(self) -> None:
        try:
            events = self.monitor.poll()
            has_active = self.monitor.has_active_transfer()
            if wx.App.Get() is not None:
                wx.CallAfter(self._on_poll_completed, events, has_active)
            else:
                self._on_poll_completed(events, has_active)
        except Exception as exc:
            logger.debug("Background poll failed: %s", exc)
        finally:
            with self._poll_lock:
                self._is_polling = False

    def _on_poll_completed(self, events: list[Any], has_active_transfer: bool) -> None:
        for event in events:
            if self.monitor.should_speak_event(event, is_initial_poll=False):
                self.speech.output(event.spoken_announcement, interrupt=False)

        self.audio.update_sync_activity(has_active_transfer)

        if self.tray_icon is not None:
            self.tray_icon.update_icon_and_tooltip()

    def poll_once(self, *, is_initial: bool = False) -> None:
        """Execute one tray polling cycle synchronously (used on startup or test suites)."""
        events = self.monitor.poll()

        for event in events:
            if self.monitor.should_speak_event(event, is_initial_poll=is_initial):
                self.speech.output(event.spoken_announcement, interrupt=False)

        if not is_initial:
            self.audio.update_sync_activity(self.monitor.has_active_transfer())
        elif self.monitor.has_active_transfer():
            self.audio.update_sync_activity(True)

        if self.tray_icon is not None:
            self.tray_icon.update_icon_and_tooltip()

    def on_slot_hotkey_triggered(self, slot_number: int, is_double_press: bool) -> None:
        """Handle single-press (speak slot) or double-press (copy slot to clipboard)."""
        if is_double_press:
            self.copy_slot(slot_number)
        else:
            self.speak_slot(slot_number)

    def speak_slot(self, slot_number: int) -> str:
        """Refresh tray state and speak the status of 1-indexed slot_number via Prism."""
        announcement = self.monitor.format_slot_announcement(slot_number, refresh=True)
        self.speech.output(announcement, interrupt=True, force=True)
        if self.tray_icon is not None:
            self.tray_icon.update_icon_and_tooltip()
        return announcement

    def copy_slot(self, slot_number: int) -> str:
        """Copy the status of slot_number to the clipboard and announce confirmation."""
        announcement = self.monitor.format_slot_announcement(slot_number, refresh=True)
        if copy_text_to_clipboard(announcement):
            msg = f"Copied to clipboard: {announcement}"
        else:
            msg = announcement
        self.speech.output(msg, interrupt=True, force=True)
        return announcement

    def speak_summary(self) -> str:
        """Refresh tray state and speak a combined summary of all active monitored sources."""
        summary = self.monitor.format_summary_announcement(refresh=True)
        self.speech.output(summary, interrupt=True, force=True)
        if self.tray_icon is not None:
            self.tray_icon.update_icon_and_tooltip()
        return summary

    def on_config_updated(self, new_config: AppConfig | None = None) -> None:
        """Persist updated configuration and apply runtime changes to speech, audio, timer, and hotkeys."""
        if new_config is not None:
            self.config = new_config
            self.monitor.config = new_config
            self.audio.config = new_config
            if self.tray_icon is not None:
                self.tray_icon.config = new_config

        self.speech.enabled = self.config.enable_speech
        self.config.save(self.config_path)
        set_autostart_enabled(self.config.run_on_startup)
        if hasattr(self.backend, "update_candidate_processes"):
            self.backend.update_candidate_processes([r.display_name for r in self.config.sources])

        self._start_poll_timer()
        self.hotkeys.start(
            self.config.hotkey_modifier,
            self.config.summary_hotkey,
            self.config.manage_hotkey,
            wx_module=wx if wx.App.Get() is not None else None,
        )
        self.poll_once(is_initial=True)

    def open_manage_dialog(self) -> None:
        """Open the accessible Manage Sources & Settings dialog if not already open."""
        if self._manage_dialog_open:
            return
        self._manage_dialog_open = True
        if self._poll_timer is not None and self._poll_timer.IsRunning():
            self._poll_timer.Stop()
        try:
            dlg = ManageSourcesDialog(
                None,
                self.config,
                self.monitor,
                self.audio,
                on_apply_callback=self.on_config_updated,
            )
            dlg.Raise()
            try:
                dlg.ShowModal()
            finally:
                dlg.Destroy()
        finally:
            self._manage_dialog_open = False
            self._start_poll_timer()

    def open_shortcuts_dialog(self) -> None:
        """Open the Keyboard Shortcuts Reference dialog if not already open."""
        if self._shortcuts_dialog_open:
            return
        self._shortcuts_dialog_open = True
        if self._poll_timer is not None and self._poll_timer.IsRunning():
            self._poll_timer.Stop()
        try:
            dlg = ShortcutReferenceDialog(None, modifier=self.config.hotkey_modifier)
            dlg.Raise()
            try:
                dlg.ShowModal()
            finally:
                dlg.Destroy()
        finally:
            self._shortcuts_dialog_open = False
            self._start_poll_timer()

    def shutdown(self) -> None:
        """Stop timers, unregister hotkeys, remove tray icon, and exit main loop."""
        if self._poll_timer is not None and self._poll_timer.IsRunning():
            self._poll_timer.Stop()
        self.hotkeys.stop()
        self.audio.reset()
        if self.tray_icon is not None:
            try:
                self.tray_icon.RemoveIcon()
                self.tray_icon.Destroy()
            except Exception:
                pass
            self.tray_icon = None
        self.backend.close()
        app = wx.App.Get()
        if app is not None and app.IsMainLoopRunning():
            app.ExitMainLoop()
