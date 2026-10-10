"""Unit tests for tooltip normalization, semantic sync state classification, and spoken formatting."""

from __future__ import annotations

import pytest

from speak_dropbox.core.classifier import (
    classify_sync_state,
    deduplicate_win11_prefix,
    format_spoken_status,
    normalize_tooltip_text,
)
from speak_dropbox.models import SyncState


def test_deduplicate_win11_prefix() -> None:
    assert (
        deduplicate_win11_prefix(" Dropbox 274.4.4841\nUp to date")
        == "Dropbox 274.4.4841\nUp to date"
    )
    assert (
        deduplicate_win11_prefix("Dropbox Dropbox 274.4.4841\nSyncing")
        == "Dropbox 274.4.4841\nSyncing"
    )
    assert (
        deduplicate_win11_prefix("Google Drive Google Drive - Everything is up to date")
        == "Google Drive - Everything is up to date"
    )


def test_normalize_tooltip_text_multiline_and_unread() -> None:
    raw = " Dropbox 274.4.4841\nUp to date. You have 11 unread notifications"
    assert (
        normalize_tooltip_text(raw, strip_unread_notifications=False)
        == "Dropbox 274.4.4841 - Up to date. You have 11 unread notifications"
    )
    assert (
        normalize_tooltip_text(raw, strip_unread_notifications=True)
        == "Dropbox 274.4.4841 - Up to date"
    )


def test_format_spoken_status_strips_build_numbers() -> None:
    cleaned = "Dropbox 274.4.4841 - Up to date"
    assert format_spoken_status("Dropbox", cleaned) == "Dropbox: Up to date"

    gdrive = "Google Drive - Syncing 3 of 10"
    assert format_spoken_status("Google Drive", gdrive) == "Google Drive: Syncing 3 of 10"

    bare = "Resilio Sync"
    assert format_spoken_status("Resilio Sync", bare) == "Resilio Sync: Running"


@pytest.mark.parametrize(
    ("tooltip", "expected_state"),
    [
        ("Dropbox 274.4.4841 - Up to date", SyncState.IDLE),
        ("Google Drive - Everything is up to date", SyncState.IDLE),
        ("OneDrive - Personal - Up to date", SyncState.IDLE),
        ("Nextcloud - All files are in sync", SyncState.IDLE),
        ("SyncTrayzor - Idle", SyncState.IDLE),
        ("Dropbox 274.4.4841 - Uploading 3 files (1.2 MB/sec, 4 secs left)", SyncState.SYNCING),
        ("Google Drive - Syncing 4 of 12", SyncState.SYNCING),
        ("OneDrive - Personal - Downloading 2 files", SyncState.SYNCING),
        ("MEGAsync - Transferring...", SyncState.SYNCING),
        ("Dropbox 274.4.4841 - Indexing 45 files...", SyncState.INDEXING),
        ("Google Drive - Preparing to sync...", SyncState.INDEXING),
        ("OneDrive - Processing changes", SyncState.INDEXING),
        ("SyncTrayzor - Scanning", SyncState.INDEXING),
        ("Dropbox 274.4.4841 - Syncing paused", SyncState.PAUSED),
        ("OneDrive - Personal - Syncing is paused", SyncState.PAUSED),
        ("Nextcloud - Synchronization paused", SyncState.PAUSED),
        ("MEGAsync - Transfers paused", SyncState.PAUSED),
        ("Dropbox - Can't sync report.pdf (permission denied)", SyncState.ERROR),
        ("OneDrive - Personal - 2 sync issues", SyncState.ERROR),
        ("iCloud - Storage full", SyncState.ERROR),
        ("Nextcloud - Error during sync", SyncState.ERROR),
        ("Google Drive - Offline", SyncState.DISCONNECTED),
        ("OneDrive - Not signed in", SyncState.DISCONNECTED),
        ("iCloud - Sign-in required", SyncState.DISCONNECTED),
        ("Resilio Sync", SyncState.UNKNOWN),
        ("", SyncState.UNKNOWN),
    ],
)
def test_classify_sync_state_across_providers(tooltip: str, expected_state: SyncState) -> None:
    assert classify_sync_state(tooltip) == expected_state
