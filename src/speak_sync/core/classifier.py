"""Tooltip string normalization and Windows 11 XAML prefix deduplication."""

from __future__ import annotations

import re

from speak_sync.models import SyncState

_REPEATED_PREFIX_RE = re.compile(r"^([^\r\n]{2,40}?)\s+\1(?=\b|\s|$|-|:)", re.IGNORECASE)
_APP_HEADER_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9 ._-]{2,35}?)(?=\s*(?:\r?\n|\s-\s|:\s))",
)
_UNREAD_NOTIFICATIONS_RE = re.compile(
    r"\.?\s*you have \d+ unread notifications?\.?", re.IGNORECASE
)
_VERSION_AFTER_APP_RE = re.compile(
    r"^(dropbox|onedrive|google drive|resilio sync|nextcloud|megasync|icloud)\s+v?\d+(?:\.\d+)+(?:\s*-\s*|\s+)",
    re.IGNORECASE,
)

_ERROR_PHRASES: tuple[str, ...] = (
    "can't sync",
    "cannot sync",
    "sync error",
    "error during sync",
    "sync issues",
    "sync issue",
    "storage full",
    "out of space",
    "action required",
    "attention required",
    "failed to sync",
    " - error",
    ": error",
)

_DISCONNECTED_PHRASES: tuple[str, ...] = (
    "not signed in",
    "sign-in required",
    "sign in required",
    "signed out",
    "logged out",
    "isn't connected",
    "not connected",
    "disconnected",
    "offline",
    "connecting...",
)

_PAUSED_PHRASES: tuple[str, ...] = (
    "syncing paused",
    "syncing is paused",
    "synchronization paused",
    "transfers paused",
    " - paused",
    ": paused",
    "paused",
)

_INDEXING_PHRASES: tuple[str, ...] = (
    "indexing",
    "preparing to sync",
    "preparing sync",
    "processing changes",
    "looking for changes",
    "checking for changes",
    "scanning files",
    "scanning",
    "loading...",
    "starting...",
    "updating...",
)

_SYNCING_PHRASES: tuple[str, ...] = (
    "syncing",
    "uploading",
    "downloading",
    "transferring",
    "mb/sec",
    "kb/sec",
    "secs left",
    "mins left",
    "remaining",
)

_IDLE_PHRASES: tuple[str, ...] = (
    "up to date",
    "everything is up to date",
    "all files are in sync",
    "files are in sync",
    "synced",
    " - idle",
    ": idle",
)


def deduplicate_win11_prefix(raw_text: str) -> str:
    """Remove duplicated leading InitialTooltip prefix added by Windows 11 XAML NotifyItemIcon."""
    text = raw_text.strip()
    if not text:
        return ""

    # Case 1: InitialTooltip was a full multi-line or 'App - Status' string followed by
    # CurrentTooltip starting with the same App header (e.g. 'App\nOldStatus App\nNewStatus'
    # or 'Windows Security - No actions needed. Windows Security - Actions recommended.').
    header_match = _APP_HEADER_RE.match(text)
    if header_match:
        app_header = header_match.group(1).strip()
        if len(app_header) >= 3:
            second_occurrence = re.search(
                r"(?<=\s)" + re.escape(app_header) + r"(?=\s*(?:\r?\n|\s-\s|:\s|$))",
                text[len(app_header) :],
                flags=re.IGNORECASE,
            )
            if second_occurrence:
                start_idx = len(app_header) + second_occurrence.start()
                return text[start_idx:].strip()

    # Case 2: InitialTooltip was just 'AppName' immediately followed by 'AppName ...'
    match = _REPEATED_PREFIX_RE.match(text)
    if match:
        prefix = match.group(1)
        remainder = text[match.end(1) :].lstrip()
        if remainder.lower().startswith(prefix.lower()):
            return remainder
    return text


def normalize_tooltip_text(
    raw_text: str,
    *,
    strip_unread_notifications: bool = False,
) -> str:
    """Clean a raw system tray tooltip into a single normalized readable line."""
    if not raw_text:
        return ""

    deduped = deduplicate_win11_prefix(raw_text)
    lines = [
        " ".join(line.split())
        for line in deduped.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    lines = [line for line in lines if line]
    if not lines:
        return ""

    parts: list[str] = [lines[0]]
    for line in lines[1:]:
        prev = parts[-1]
        if prev.endswith((".", ":", "-", ";", ",")):
            parts.append(f" {line}")
        else:
            parts.append(f" - {line}")

    cleaned = "".join(parts).strip()
    if strip_unread_notifications:
        cleaned = _UNREAD_NOTIFICATIONS_RE.sub("", cleaned).strip(" -.")
    return cleaned


def classify_sync_state(tooltip_text: str) -> SyncState:
    """Classify normalized or raw tooltip text into a semantic SyncState."""
    if not tooltip_text or not tooltip_text.strip():
        return SyncState.UNKNOWN

    lower = tooltip_text.lower()

    if any(phrase in lower for phrase in _ERROR_PHRASES):
        return SyncState.ERROR

    if any(phrase in lower for phrase in _DISCONNECTED_PHRASES):
        return SyncState.DISCONNECTED

    if any(phrase in lower for phrase in _PAUSED_PHRASES):
        return SyncState.PAUSED

    if any(phrase in lower for phrase in _INDEXING_PHRASES):
        return SyncState.INDEXING

    if any(phrase in lower for phrase in _SYNCING_PHRASES):
        return SyncState.SYNCING

    if any(phrase in lower for phrase in _IDLE_PHRASES):
        return SyncState.IDLE

    return SyncState.UNKNOWN


def format_spoken_status(display_name: str, cleaned_tooltip: str) -> str:
    """Format a concise, screen-reader-friendly status phrase for a source."""
    if not cleaned_tooltip:
        return f"{display_name}: Status unavailable"

    without_version = _VERSION_AFTER_APP_RE.sub(f"{display_name}: ", cleaned_tooltip, count=1)
    if without_version != cleaned_tooltip:
        return without_version.strip()

    lower_tip = cleaned_tooltip.lower()
    lower_name = display_name.lower()
    if lower_tip == lower_name:
        return f"{display_name}: Running"

    if lower_tip.startswith(lower_name):
        suffix = cleaned_tooltip[len(display_name) :].lstrip(" -:\t")
        if suffix:
            return f"{display_name}: {suffix}"
        return f"{display_name}: Running"

    return f"{display_name}: {cleaned_tooltip}"
