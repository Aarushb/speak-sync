"""Unit tests for SyncActivityLog ring buffer."""

from __future__ import annotations

from datetime import datetime, timezone

from speak_dropbox.core.history import SyncActivityLog
from speak_dropbox.models import ChangeType, StateChangeEvent, SyncState, TrayLocation


def test_sync_activity_log_records_and_orders_newest_first() -> None:
    log = SyncActivityLog(max_entries=3)
    base_dt = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)

    for idx in range(4):
        evt = StateChangeEvent(
            source_id="dropbox",
            display_name="Dropbox",
            change_type=ChangeType.STATE_CHANGED,
            previous_state=SyncState.IDLE,
            new_state=SyncState.SYNCING,
            previous_tooltip="Dropbox: Up to date",
            new_tooltip=f"Dropbox: Syncing {idx + 1} files",
            spoken_announcement=f"Dropbox: Syncing {idx + 1} files",
            location=TrayLocation.VISIBLE,
        )
        log.record(evt, now=base_dt.replace(second=idx))

    assert len(log) == 3
    newest = log.get_entries(newest_first=True)
    assert newest[0].spoken_text == "Dropbox: Syncing 4 files"
    assert newest[-1].spoken_text == "Dropbox: Syncing 2 files"
    assert "[12:00:03] Dropbox (Syncing): Dropbox: Syncing 4 files" == newest[0].format_line()

    log.clear()
    assert len(log) == 0
