"""Unit tests for core domain models and enums."""

from __future__ import annotations

from speak_sync.models import (
    ChangeType,
    MonitoredSourceStatus,
    SourceRule,
    StateChangeEvent,
    SyncState,
    TrayIconItem,
    TrayLocation,
)


def test_tray_location_display_labels() -> None:
    assert TrayLocation.VISIBLE.display_label == "Visible Tray"
    assert TrayLocation.OVERFLOW.display_label == "Hidden Tray"
    assert TrayLocation.LOCAL_IPC.display_label == "Background Service"
    assert TrayLocation.UNKNOWN.display_label == "System Tray"


def test_sync_state_properties() -> None:
    assert SyncState.SYNCING.is_active_transfer is True
    assert SyncState.INDEXING.is_active_transfer is True
    assert SyncState.IDLE.is_active_transfer is False
    assert SyncState.PAUSED.is_active_transfer is False
    assert SyncState.ERROR.is_active_transfer is False

    assert SyncState.ERROR.is_problem is True
    assert SyncState.DISCONNECTED.is_problem is True
    assert SyncState.IDLE.is_problem is False
    assert SyncState.SYNCING.display_label == "Syncing"
    assert SyncState.IDLE.display_label == "Up to date"


def test_source_rule_matching_and_serialization() -> None:
    rule = SourceRule(
        id="dropbox",
        display_name="Dropbox",
        keywords=["dropbox"],
        enabled=True,
        pinned_slot=1,
        builtin=True,
    )
    assert rule.matches("Dropbox 274.4.4841\nUp to date") is True
    assert rule.matches("SomeApp", process_name="Dropbox.exe") is True
    assert rule.matches("Google Drive - Up to date") is False

    rule.enabled = False
    assert rule.matches("Dropbox 274.4.4841") is False

    serialized = rule.to_dict()
    restored = SourceRule.from_dict(serialized)
    assert restored.id == "dropbox"
    assert restored.display_name == "Dropbox"
    assert restored.keywords == ["dropbox"]
    assert restored.enabled is False
    assert restored.pinned_slot == 1
    assert restored.builtin is True


def test_source_rule_from_dict_comma_string_keywords() -> None:
    restored = SourceRule.from_dict(
        {
            "id": "syncthing",
            "display_name": "Syncthing",
            "keywords": "syncthing, synctrayzor",
            "pinned_slot": "4",
        }
    )
    assert restored.keywords == ["syncthing", "synctrayzor"]
    assert restored.pinned_slot == 4


def test_state_change_event_speech_filtering() -> None:
    state_changed = StateChangeEvent(
        source_id="dropbox",
        display_name="Dropbox",
        change_type=ChangeType.STATE_CHANGED,
        previous_state=SyncState.IDLE,
        new_state=SyncState.SYNCING,
        previous_tooltip="Dropbox - Up to date",
        new_tooltip="Dropbox - Syncing 3 files",
        spoken_announcement="Dropbox: Syncing 3 files",
        location=TrayLocation.VISIBLE,
    )
    assert state_changed.should_announce_speech is True

    detail_tick = StateChangeEvent(
        source_id="dropbox",
        display_name="Dropbox",
        change_type=ChangeType.DETAIL_UPDATED,
        previous_state=SyncState.SYNCING,
        new_state=SyncState.SYNCING,
        previous_tooltip="Dropbox - Syncing 3 files",
        new_tooltip="Dropbox - Syncing 2 files",
        spoken_announcement="Dropbox: Syncing 2 files",
        location=TrayLocation.VISIBLE,
    )
    assert detail_tick.should_announce_speech is False
