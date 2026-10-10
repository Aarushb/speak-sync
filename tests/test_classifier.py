"""Unit tests for tooltip normalization and spoken status formatting."""

from __future__ import annotations

from speak_dropbox.core.classifier import (
    deduplicate_win11_prefix,
    format_spoken_status,
    normalize_tooltip_text,
)


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
