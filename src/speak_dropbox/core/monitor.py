"""Tray icon matching, slot assignment, and stateful transition monitoring engine."""

from __future__ import annotations

import time
from collections.abc import Sequence

from speak_dropbox.config import AppConfig
from speak_dropbox.core.classifier import (
    classify_sync_state,
    format_spoken_status,
    normalize_tooltip_text,
)
from speak_dropbox.models import (
     MonitoredSourceStatus,
    SourceRule,
    TrayIconItem,
)

SELF_TRAY_PREFIX = "speak dropbox"


def is_ignored_or_self_icon(item: TrayIconItem, ignored_keywords: Sequence[str] = ()) -> bool:
    """Return True if a tray icon belongs to Speak Dropbox itself or matches an ignored keyword."""
    lower = item.cleaned_tooltip.lower()
    if lower.startswith(SELF_TRAY_PREFIX):
        return True
    return any(kw.lower() in lower for kw in ignored_keywords if kw.strip())


def match_icons_to_rules(
    icons: Sequence[TrayIconItem],
    rules: Sequence[SourceRule],
    *,
    strip_unread_notifications: bool = False,
    ignored_keywords: Sequence[str] = (),
) -> tuple[list[tuple[SourceRule, TrayIconItem]], list[TrayIconItem]]:
    """Match discovered tray icons against enabled source rules.

    Returns (matched_pairs, unmatched_icons).
    """
    matched_pairs: list[tuple[SourceRule, TrayIconItem]] = []
    used_icon_indices: set[int] = set()

    enabled_rules = [r for r in rules if r.enabled]
    for rule in enabled_rules:
        for idx, icon in enumerate(icons):
            if idx in used_icon_indices:
                continue
            if is_ignored_or_self_icon(icon, ignored_keywords):
                continue
            if rule.matches(icon.cleaned_tooltip, icon.process_name):
                used_icon_indices.add(idx)
                cleaned = normalize_tooltip_text(
                    icon.raw_tooltip,
                    strip_unread_notifications=strip_unread_notifications,
                )
                normalized_icon = TrayIconItem(
                    raw_tooltip=icon.raw_tooltip,
                    cleaned_tooltip=cleaned or icon.cleaned_tooltip,
                    location=icon.location,
                    process_name=icon.process_name,
                    automation_id=icon.automation_id,
                    hwnd=icon.hwnd,
                )
                matched_pairs.append((rule, normalized_icon))
                break

    unmatched: list[TrayIconItem] = [
        icon
        for idx, icon in enumerate(icons)
        if idx not in used_icon_indices and not is_ignored_or_self_icon(icon, ignored_keywords)
    ]
    return matched_pairs, unmatched


def assign_slots(
    matched_pairs: Sequence[tuple[SourceRule, TrayIconItem]],
    *,
    now: float | None = None,
) -> list[MonitoredSourceStatus]:
    """Assign 1-indexed slots to matched sources respecting pinned_slot and rule priority order."""
    timestamp = now if now is not None else time.time()
    taken_slots: dict[int, MonitoredSourceStatus] = {}
    unpinned: list[tuple[SourceRule, TrayIconItem]] = []

    for rule, icon in matched_pairs:
        if rule.pinned_slot is not None and rule.pinned_slot >= 1 and rule.pinned_slot not in taken_slots:
            state = classify_sync_state(icon.cleaned_tooltip)
            spoken = format_spoken_status(rule.display_name, icon.cleaned_tooltip)
            taken_slots[rule.pinned_slot] = MonitoredSourceStatus(
                source_id=rule.id,
                display_name=rule.display_name,
                slot=rule.pinned_slot,
                raw_tooltip=icon.raw_tooltip,
                cleaned_tooltip=icon.cleaned_tooltip,
                spoken_text=spoken,
                state=state,
                location=icon.location,
                last_updated=timestamp,
            )
        else:
            unpinned.append((rule, icon))

    next_slot = 1
    for rule, icon in unpinned:
        while next_slot in taken_slots:
            next_slot += 1
        state = classify_sync_state(icon.cleaned_tooltip)
        spoken = format_spoken_status(rule.display_name, icon.cleaned_tooltip)
        taken_slots[next_slot] = MonitoredSourceStatus(
            source_id=rule.id,
            display_name=rule.display_name,
            slot=next_slot,
            raw_tooltip=icon.raw_tooltip,
            cleaned_tooltip=icon.cleaned_tooltip,
            spoken_text=spoken,
            state=state,
            location=icon.location,
            last_updated=timestamp,
        )
        next_slot += 1

    return [taken_slots[s] for s in sorted(taken_slots)]
