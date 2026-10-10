"""Tooltip string normalization and Windows 11 XAML prefix deduplication."""

from __future__ import annotations

import re

_REPEATED_PREFIX_RE = re.compile(r"^([^\r\n]{2,40}?)\s+\1(?=\b|\s|$|-|:)", re.IGNORECASE)
_UNREAD_NOTIFICATIONS_RE = re.compile(
    r"\.?\s*you have \d+ unread notifications?\.?", re.IGNORECASE
)
_VERSION_AFTER_APP_RE = re.compile(
    r"^(dropbox|onedrive|google drive|resilio sync|nextcloud|megasync|icloud)\s+v?\d+(?:\.\d+)+(?:\s*-\s*|\s+)",
    re.IGNORECASE,
)


def deduplicate_win11_prefix(raw_text: str) -> str:
    """Remove duplicated leading prefix added by Windows 11 XAML NotifyItemIcon."""
    text = raw_text.strip()
    if not text:
        return ""
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
