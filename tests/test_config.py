"""Unit tests for AppConfig and source rule management."""

from __future__ import annotations

from pathlib import Path

from speak_dropbox.config import AppConfig, default_source_rules
from speak_dropbox.models import SourceRule


def test_default_source_rules() -> None:
    rules = default_source_rules()
    ids = [r.id for r in rules]
    assert "dropbox" in ids
    assert "google_drive" in ids
    assert "onedrive" in ids
    assert "resilio_sync" in ids
    assert all(r.enabled for r in rules)
    assert all(r.builtin for r in rules)


def test_app_config_source_operations() -> None:
    cfg = AppConfig()
    initial_count = len(cfg.sources)

    custom = SourceRule(
        id="pcloud",
        display_name="pCloud",
        keywords=["pcloud"],
        enabled=True,
        builtin=False,
    )
    cfg.add_or_update_source(custom)
    assert len(cfg.sources) == initial_count + 1
    assert cfg.get_source("pcloud") is not None

    # Move custom source up
    assert cfg.move_source("pcloud", -1) is True
    assert cfg.sources[-2].id == "pcloud"

    # Removing custom source deletes it from list
    assert cfg.remove_or_disable_source("pcloud") is True
    assert cfg.get_source("pcloud") is None

    # Removing built-in source disables it instead of deleting
    assert cfg.remove_or_disable_source("dropbox") is True
    dropbox_rule = cfg.get_source("dropbox")
    assert dropbox_rule is not None
    assert dropbox_rule.enabled is False
    assert "dropbox" not in [s.id for s in cfg.get_enabled_sources()]


def test_app_config_save_and_load_roundtrip(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    cfg = AppConfig(
        poll_interval_seconds=2.5,
        enable_speech=False,
        enable_loop_sound=False,
        hotkey_modifier="Ctrl+Shift+Win",
        strip_unread_notifications=True,
    )
    cfg.save(config_file)
    assert config_file.exists()

    loaded = AppConfig.load(config_file)
    assert loaded.poll_interval_seconds == 2.5
    assert loaded.enable_speech is False
    assert loaded.enable_loop_sound is False
    assert loaded.hotkey_modifier == "Ctrl+Shift+Win"
    assert loaded.strip_unread_notifications is True


def test_app_config_corrupt_file_fallback(tmp_path: Path) -> None:
    config_file = tmp_path / "broken.json"
    config_file.write_text("{not valid json", encoding="utf-8")
    loaded = AppConfig.load(config_file)
    assert loaded.enable_speech is True
    assert len(loaded.sources) >= 5
