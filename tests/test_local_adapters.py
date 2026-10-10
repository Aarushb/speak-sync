"""Unit tests for Google DriveFS and OneDrive local log telemetry enrichment."""

from __future__ import annotations

from pathlib import Path

from speak_dropbox.core.local_adapters import (
    enrich_bare_cloud_tooltip,
    parse_drivefs_log_tail,
    parse_onedrive_diagnostics_tail,
)


def test_parse_drivefs_log_tail_states() -> None:
    idle_log = """
2026-10-10T07:44:59.025ZI [41056:core] sync_engine.cc:2636:operator() Sync engine activity state:
operation_queue_size: 0
all_downloads: 0
change_ids_up_to_date: true
largest_local_change_id: 241411
fetching_changes: false
unique_user_requested_op_count: 0
"""
    assert parse_drivefs_log_tail(idle_log) == "Google Drive - Everything is up to date"

    syncing_log = """
2026-10-10T07:44:59.025ZI [41056:core] sync_engine.cc:2636:operator() Sync engine activity state:
operation_queue_size: 4
all_downloads: 2
change_ids_up_to_date: false
largest_local_change_id: 241411
fetching_changes: false
unique_user_requested_op_count: 0
"""
    assert (
        parse_drivefs_log_tail(syncing_log)
        == "Google Drive - Syncing (4 queued, 2 downloading)"
    )

    fetching_log = """
2026-10-10T07:44:59.025ZI [41056:core] sync_engine.cc:2636:operator() Sync engine activity state:
operation_queue_size: 0
all_downloads: 0
change_ids_up_to_date: false
largest_local_change_id: 241411
fetching_changes: true
unique_user_requested_op_count: 0
"""
    assert parse_drivefs_log_tail(fetching_log) == "Google Drive - Checking for changes..."


def test_parse_onedrive_diagnostics_and_enrich_bare_tooltip(tmp_path: Path) -> None:
    od_log = tmp_path / "SyncDiagnostics.log"
    od_log.write_text("FilesToUpload = 3\nFilesToDownload = 1\n", encoding="utf-8")

    assert parse_onedrive_diagnostics_tail(od_log.read_text(encoding="utf-8")) == "OneDrive - Syncing 4 files"
    assert (
        enrich_bare_cloud_tooltip("Microsoft OneDrive", onedrive_log_path=od_log)
        == "OneDrive - Syncing 4 files"
    )
