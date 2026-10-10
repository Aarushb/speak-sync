"""Integration tests for SpeakDropboxController and CLI entrypoint."""

from __future__ import annotations

from pathlib import Path
import pytest
import wx

from speak_dropbox.__main__ import build_arg_parser, run_cli_one_shot
from speak_dropbox.app import SpeakDropboxController
from speak_dropbox.backends.base import StaticTrayBackend
from speak_dropbox.config import AppConfig
from speak_dropbox.models import TrayIconItem, TrayLocation
from speak_dropbox.services.audio import AudioCueService
from speak_dropbox.services.speech import SpeechService


class _RecorderBackend:
    name = "RecorderPrism"

    def __init__(self) -> None:
        self.outputs: list[str] = []

    def output(self, text: str, interrupt: bool = True) -> None:
        self.outputs.append(text)

    def speak(self, text: str, interrupt: bool = True) -> None:
        self.outputs.append(text)


def test_controller_end_to_end_transitions(wx_app: wx.App, tmp_path: Path) -> None:
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
    recorder = _RecorderBackend()
    speech = SpeechService(enabled=True, backend=recorder)
    played_cues: list[str] = []
    audio = AudioCueService(cfg, player_fn=lambda p: (played_cues.append(p.name), True)[1])

    ctrl = SpeakDropboxController(
        config=cfg,
        config_path=tmp_path / "config.json",
        backend=backend,
        speech_service=speech,
        audio_service=audio,
        create_tray_ui=False,
        register_hotkeys=False,
    )
    try:
        # Initial poll should not speak or play start sound when idle
        assert recorder.outputs == []
        assert played_cues == []

        # Query Slot 1 and Slot 2 via hotkey callback
        ctrl.on_slot_hotkey_triggered(1, is_double_press=False)
        assert recorder.outputs[-1] == "Dropbox: Up to date"

        ctrl.on_slot_hotkey_triggered(2, is_double_press=False)
        assert recorder.outputs[-1] == "Google Drive: Everything is up to date"

        # Transition Google Drive (in hidden tray) to Syncing
        backend.set_items(
            [
                TrayIconItem(
                    raw_tooltip="Dropbox 274.4.4841 - Up to date",
                    cleaned_tooltip="Dropbox 274.4.4841 - Up to date",
                    location=TrayLocation.VISIBLE,
                ),
                TrayIconItem(
                    raw_tooltip="Google Drive - Syncing 3 of 8",
                    cleaned_tooltip="Google Drive - Syncing 3 of 8",
                    location=TrayLocation.OVERFLOW,
                ),
            ]
        )
        ctrl.poll_once(is_initial=False)
        assert recorder.outputs[-1] == "Google Drive: Syncing 3 of 8"
        assert played_cues == ["start.flac"]

        # Transition Google Drive back to Up to date
        backend.set_items(
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
        ctrl.poll_once(is_initial=False)
        assert recorder.outputs[-1] == "Google Drive: Everything is up to date"
        assert played_cues == ["start.flac", "finish.flac"]
    finally:
        ctrl.shutdown()


def test_cli_one_shot_commands(capsys: pytest.CaptureFixture[str]) -> None:
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
    parser = build_arg_parser()

    args_list = parser.parse_args(["--list-tray", "--no-speak"])
    assert run_cli_one_shot(args_list, backend=backend) == 0
    out_list = capsys.readouterr().out
    assert "[Visible Tray] Dropbox 274.4.4841 - Up to date" in out_list
    assert "[Hidden Tray] Google Drive - Everything is up to date" in out_list

    args_slot = parser.parse_args(["--slot", "2", "--no-speak"])
    assert run_cli_one_shot(args_slot, backend=backend) == 0
    out_slot = capsys.readouterr().out
    assert "Google Drive: Everything is up to date" in out_slot

    args_status = parser.parse_args(["--status", "--no-speak"])
    assert run_cli_one_shot(args_status, backend=backend) == 0
    out_status = capsys.readouterr().out
    assert "2 active sources." in out_status
