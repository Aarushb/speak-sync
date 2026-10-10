"""Unit tests for OS autostart command generation and Linux XDG autostart handling."""

from __future__ import annotations

from pathlib import Path
import pytest

from speak_sync.core import autostart


def test_get_launch_command() -> None:
    cmd = autostart.get_launch_command()
    assert "-m speak_sync" in cmd


def test_linux_xdg_autostart_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert autostart.is_autostart_enabled() is False
    assert autostart.set_autostart_enabled(True) is True
    assert autostart.is_autostart_enabled() is True

    desktop_file = tmp_path / "autostart" / "speak-sync.desktop"
    assert desktop_file.exists()
    assert "SpeakSync" in desktop_file.read_text(encoding="utf-8")

    assert autostart.set_autostart_enabled(False) is True
    assert autostart.is_autostart_enabled() is False
