"""Unit tests for AudioCueService 3-stage sync earcon state machine."""

from __future__ import annotations

from pathlib import Path

from speak_sync.config import AppConfig
from speak_sync.services.audio import AudioCueService, resolve_cue_file


def test_resolve_bundled_cue_files() -> None:
    for filename in ("start.flac", "loopty.flac", "finish.flac"):
        resolved = resolve_cue_file("", filename)
        assert resolved is not None, f"Bundled {filename} must resolve"
        assert resolved.name == filename
        assert resolved.is_file()


def test_resolve_frozen_cue_files(tmp_path: Path, monkeypatch) -> None:
    fake_exe = tmp_path / "bin" / "speaksync.exe"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.touch()

    # Mock frozen app with _internal/assets
    internal_assets = tmp_path / "bin" / "_internal" / "assets"
    internal_assets.mkdir(parents=True)
    (internal_assets / "start.flac").write_bytes(b"mock_start")

    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(fake_exe))

    from speak_sync.services.audio import get_assets_dir

    assets_dir = get_assets_dir()
    assert assets_dir == internal_assets
    resolved = resolve_cue_file("", "start.flac")
    assert resolved == internal_assets / "start.flac"


def test_audio_cue_three_stage_state_machine() -> None:
    played_files: list[str] = []

    def fake_player(path: Path) -> bool:
        played_files.append(path.name)
        return True

    cfg = AppConfig(enable_sounds=True, enable_loop_sound=True, loop_interval_seconds=2.5)
    audio = AudioCueService(cfg, player_fn=fake_player)

    # Idle -> Idle: no sound
    assert audio.update_sync_activity(False, now=10.0) is None
    assert played_files == []

    # Idle -> Syncing: plays start.flac
    assert audio.update_sync_activity(True, now=11.0) == "start"
    assert played_files == ["start.flac"]
    assert audio.is_sync_active is True

    # 1.0s later (before loop_interval_seconds=2.5): no loop yet
    assert audio.update_sync_activity(True, now=12.0) is None
    assert played_files == ["start.flac"]

    # 2.6s after start: plays loopty.flac
    assert audio.update_sync_activity(True, now=13.6) == "loop"
    assert played_files == ["start.flac", "loopty.flac"]

    # Another 2.6s later: plays loopty.flac again
    assert audio.update_sync_activity(True, now=16.2) == "loop"
    assert played_files == ["start.flac", "loopty.flac", "loopty.flac"]

    # Syncing -> Idle: stops loop and plays finish.flac
    assert audio.update_sync_activity(False, now=17.0) == "finish"
    assert played_files == ["start.flac", "loopty.flac", "loopty.flac", "finish.flac"]
    assert audio.is_sync_active is False


def test_audio_cue_loop_disabled_and_sounds_disabled() -> None:
    played_files: list[str] = []
    cfg = AppConfig(enable_sounds=True, enable_loop_sound=False, loop_interval_seconds=2.0)
    audio = AudioCueService(cfg, player_fn=lambda p: (played_files.append(p.name), True)[1])

    assert audio.update_sync_activity(True, now=1.0) == "start"
    assert audio.update_sync_activity(True, now=5.0) is None
    assert audio.update_sync_activity(False, now=6.0) == "finish"
    assert played_files == ["start.flac", "finish.flac"]

    cfg.enable_sounds = False
    played_files.clear()
    assert audio.update_sync_activity(True, now=10.0) is None
    assert played_files == []
