"""Accessible wxPython update dialog with changelog review, live progress, and self-restart."""

from __future__ import annotations

import logging
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
import wx

from speak_sync import __version__
from speak_sync.services.speech import SpeechService
from speak_sync.services.updater import (
    UpdateInfo,
    apply_installer_update,
    apply_portable_update,
    download_update_asset,
)

logger = logging.getLogger(__name__)


class UpdateDialog(wx.Dialog):
    """Accessible modal dialog showing release notes, download progress, and self-restart controls."""

    def __init__(
        self,
        parent: wx.Window | None,
        update_info: UpdateInfo,
        *,
        speech_service: SpeechService | None = None,
        on_restart_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            parent,
            title=f"SpeakSync Update Available - Version {update_info.version}",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
            size=(560, 480),
        )
        self.update_info = update_info
        self.speech = speech_service
        self.on_restart_callback = on_restart_callback
        self._cancel_flag = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._last_spoken_pct = -1

        self._init_ui()
        self.CentreOnScreen()

    def _init_ui(self) -> None:
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Header and version announcement
        hdr = wx.StaticText(
            self,
            label=f"A new version of SpeakSync is available! (v{self.update_info.version})",
        )
        hdr_font = hdr.GetFont()
        hdr_font.SetWeight(wx.FONTWEIGHT_BOLD)
        hdr_font.SetPointSize(hdr_font.GetPointSize() + 2)
        hdr.SetFont(hdr_font)
        main_sizer.Add(hdr, 0, wx.ALL, 12)

        ver_info = wx.StaticText(
            self,
            label=f"Current Version: {__version__}    |    Available Version: {self.update_info.version}",
        )
        main_sizer.Add(ver_info, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        # Changelog / Release notes text area
        notes_label = wx.StaticText(self, label="&What's new in this release:")
        main_sizer.Add(notes_label, 0, wx.LEFT | wx.RIGHT, 12)

        clean_notes = self.update_info.release_notes.strip()
        if not clean_notes:
            clean_notes = f"Release notes are available on GitHub for version {self.update_info.version}."

        self.notes_ctrl = wx.TextCtrl(
            self,
            value=clean_notes,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
            size=(-1, 180),
        )
        self.notes_ctrl.SetName("Release Notes")
        main_sizer.Add(self.notes_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)

        # Progress bar and status indicator
        self.status_label = wx.StaticText(
            self,
            label="Ready to install. Click 'Install and Restart' to begin.",
        )
        self.status_label.SetName("Update Status")
        main_sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)

        self.gauge = wx.Gauge(self, range=100, style=wx.GA_HORIZONTAL)
        self.gauge.SetName("Download Progress")
        self.gauge.Hide()
        main_sizer.Add(self.gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.btn_install = wx.Button(self, label="&Install and Restart")
        self.btn_install.SetDefault()
        self.Bind(wx.EVT_BUTTON, self._on_install_click, self.btn_install)
        btn_sizer.Add(self.btn_install, 0, wx.RIGHT, 8)

        self.btn_later = wx.Button(self, wx.ID_CANCEL, label="Remind Me &Later")
        self.Bind(wx.EVT_BUTTON, self._on_close_click, self.btn_later)
        btn_sizer.Add(self.btn_later, 0, wx.RIGHT, 8)

        btn_sizer.AddStretchSpacer()

        self.btn_web = wx.Button(self, label="&Open Download Page")
        self.Bind(wx.EVT_BUTTON, self._on_web_click, self.btn_web)
        btn_sizer.Add(self.btn_web, 0)

        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 12)

        self.SetSizer(main_sizer)
        self.Bind(wx.EVT_CLOSE, self._on_dialog_close)

    def _on_install_click(self, _event: wx.CommandEvent) -> None:
        if not self.update_info.asset_download_url:
            self._on_failure("No matching downloadable package was found for this release.")
            return

        self.btn_install.Disable()
        self.btn_later.SetLabel("&Cancel Download")
        self.gauge.Show()
        self.Layout()

        self.status_label.SetLabel("Starting download...")
        if self.speech:
            self.speech.output(f"Downloading SpeakSync {self.update_info.version}...", interrupt=True)

        self._cancel_flag.clear()
        self._worker_thread = threading.Thread(
            target=self._download_and_install_worker,
            daemon=True,
            name="speaksync-update-worker",
        )
        self._worker_thread.start()

    def _download_and_install_worker(self) -> None:
        target_dir = Path(tempfile.gettempdir()) / "speaksync_updates"
        target_path = target_dir / self.update_info.asset_name

        def progress_callback(downloaded: int, total: int) -> None:
            if total > 0:
                pct = int((downloaded / total) * 100)
                mb_down = downloaded / (1024 * 1024)
                mb_tot = total / (1024 * 1024)
                msg = f"Downloading: {pct}% ({mb_down:.1f} MB of {mb_tot:.1f} MB)..."
            else:
                pct = 0
                mb_down = downloaded / (1024 * 1024)
                msg = f"Downloading: {mb_down:.1f} MB..."

            wx.CallAfter(self._update_progress_ui, pct, msg)

        success = download_update_asset(
            self.update_info.asset_download_url,
            target_path,
            progress_callback=progress_callback,
            cancel_flag=self._cancel_flag,
        )

        if not success:
            if not self._cancel_flag.is_set():
                wx.CallAfter(self._on_failure, "Download failed or was interrupted.")
            return

        wx.CallAfter(self._apply_and_relaunch, target_path)

    def _update_progress_ui(self, pct: int, status_text: str) -> None:
        if not self or not self.gauge:
            return
        self.gauge.SetValue(pct)
        self.status_label.SetLabel(status_text)

        # Periodically speak milestones (e.g. 25%, 50%, 75%, 100%)
        if self.speech and pct in (25, 50, 75, 100) and pct != self._last_spoken_pct:
            self._last_spoken_pct = pct
            self.speech.output(f"Update download {pct} percent complete.", interrupt=False)

    def _apply_and_relaunch(self, package_path: Path) -> None:
        self.status_label.SetLabel("Applying update and restarting...")
        if self.speech:
            self.speech.output("Update downloaded. Restarting SpeakSync...", interrupt=True)

        if self.update_info.is_portable:
            success = apply_portable_update(package_path)
        else:
            success = apply_installer_update(package_path)

        if not success:
            self._on_failure("Could not apply update automatically. Please install manually.")
            return

        if self.on_restart_callback:
            self.on_restart_callback()
        self.EndModal(wx.ID_OK)

    def _on_failure(self, error_message: str) -> None:
        self.btn_install.Enable()
        self.btn_later.SetLabel("&Close")
        self.gauge.Hide()
        self.Layout()

        err_text = f"Update failed: {error_message}\nYou can download and install manually using the button below."
        self.status_label.SetLabel(err_text)
        if self.speech:
            self.speech.output(f"Update failed: {error_message}. Opening download page.", interrupt=True)
        self.btn_web.SetFocus()

    def _on_web_click(self, _event: wx.CommandEvent) -> None:
        url = self.update_info.html_url or f"https://github.com/{self.update_info.tag_name}"
        wx.LaunchDefaultBrowser(url)

    def _on_close_click(self, _event: wx.CommandEvent) -> None:
        self._cancel_flag.set()
        self.EndModal(wx.ID_CANCEL)

    def _on_dialog_close(self, event: wx.CloseEvent) -> None:
        self._cancel_flag.set()
        event.Skip()
