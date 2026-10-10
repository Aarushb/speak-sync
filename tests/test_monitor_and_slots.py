"""Unit tests for TrayMonitorService, slot assignment, and transition debouncing."""

from __future__ import annotations

from speak_dropbox.backends.base import StaticTrayBackend
from speak_dropbox.config import AppConfig
from speak_dropbox.core.monitor import TrayMonitorService
from speak_dropbox.models import (
    ChangeType,
    SourceRule,
    SyncState,
    TrayIconItem,
    TrayLocation,
)


def _make_icon(text: str, location: TrayLocation = TrayLocation.VISIBLE) -> TrayIconItem:
    return TrayIconItem(raw_tooltip=text, cleaned_tooltip=text, location=location)


def test_monitor_slot_assignment_and_queries() -> None:
    backend = StaticTrayBackend(
        [
            _make_icon("Dropbox 274.4.4841 - Up to date", TrayLocation.VISIBLE),
            _make_icon("Google Drive - Everything is up to date", TrayLocation.OVERFLOW),
            _make_icon("Discord", TrayLocation.OVERFLOW),
            _make_icon("Speak Dropbox - 2 sources up to date", TrayLocation.VISIBLE),
        ]
    )
    cfg = AppConfig()
    monitor = TrayMonitorService(backend, cfg)

    events = monitor.poll()
    assert len(events) == 2
    assert all(e.change_type == ChangeType.APPEARED for e in events)

    slots = monitor.get_active_slots()
    assert len(slots) == 2
    assert slots[0].slot == 1
    assert slots[0].source_id == "dropbox"
    assert slots[0].location == TrayLocation.VISIBLE
    assert slots[1].slot == 2
    assert slots[1].source_id == "google_drive"
    assert slots[1].location == TrayLocation.OVERFLOW

    assert monitor.format_slot_announcement(1) == "Dropbox: Up to date"
    assert monitor.format_slot_announcement(2) == "Google Drive: Everything is up to date"
    assert monitor.format_slot_announcement(3) == "Slot 3: No source assigned"

    summary = monitor.format_summary_announcement()
    assert "2 active sources." in summary
    assert "Slot 1, Dropbox: Up to date." in summary
    assert "Slot 2, Google Drive: Everything is up to date." in summary

    unmonitored = monitor.get_unmonitored_icons()
    assert len(unmonitored) == 1
    assert unmonitored[0].cleaned_tooltip == "Discord"


def test_monitor_transition_debouncing_and_active_transfer() -> None:
    backend = StaticTrayBackend(
        [_make_icon("Dropbox 274.4.4841 - Up to date", TrayLocation.VISIBLE)]
    )
    cfg = AppConfig()
    monitor = TrayMonitorService(backend, cfg)

    initial_events = monitor.poll()
    assert len(initial_events) == 1
    assert monitor.should_speak_event(initial_events[0], is_initial_poll=True) is False
    assert monitor.has_active_transfer() is False

    # Transition to SYNCING
    backend.set_items(
        [_make_icon("Dropbox 274.4.4841 - Uploading 5 files (2.1 MB/sec)", TrayLocation.VISIBLE)]
    )
    sync_start_events = monitor.poll()
    assert len(sync_start_events) == 1
    assert sync_start_events[0].change_type == ChangeType.STATE_CHANGED
    assert sync_start_events[0].new_state == SyncState.SYNCING
    assert monitor.should_speak_event(sync_start_events[0]) is True
    assert monitor.has_active_transfer() is True
    assert "Syncing: Dropbox" in monitor.format_tray_tooltip_summary()

    # Intermediate progress tick (5 files -> 3 files) stays in SYNCING
    backend.set_items(
        [_make_icon("Dropbox 274.4.4841 - Uploading 3 files (2.4 MB/sec)", TrayLocation.VISIBLE)]
    )
    tick_events = monitor.poll()
    assert len(tick_events) == 1
    assert tick_events[0].change_type == ChangeType.DETAIL_UPDATED
    assert monitor.should_speak_event(tick_events[0]) is False
    # Yet on-demand slot query reflects the latest file count!
    assert "Uploading 3 files" in monitor.format_slot_announcement(1)

    # Transition back to IDLE
    backend.set_items([_make_icon("Dropbox 274.4.4841 - Up to date", TrayLocation.VISIBLE)])
    finish_events = monitor.poll()
    assert len(finish_events) == 1
    assert finish_events[0].change_type == ChangeType.STATE_CHANGED
    assert finish_events[0].new_state == SyncState.IDLE
    assert monitor.should_speak_event(finish_events[0]) is True
    assert monitor.has_active_transfer() is False


def test_pinned_slot_reservation() -> None:
    cfg = AppConfig(
        sources=[
            SourceRule(id="dropbox", display_name="Dropbox", keywords=["dropbox"], enabled=True),
            SourceRule(
                id="onedrive",
                display_name="OneDrive",
                keywords=["onedrive"],
                enabled=True,
                pinned_slot=5,
            ),
        ]
    )
    backend = StaticTrayBackend(
        [
            _make_icon("Dropbox - Up to date"),
            _make_icon("OneDrive - Personal - Up to date"),
        ]
    )
    monitor = TrayMonitorService(backend, cfg)
    monitor.poll()

    assert monitor.format_slot_announcement(1) == "Dropbox: Up to date"
    assert monitor.format_slot_announcement(5) == "OneDrive: Personal - Up to date"
    assert monitor.format_slot_announcement(2) == "Slot 2: No source assigned"
