"""Tray icon matching, slot assignment, and stateful transition monitoring engine."""

from __future__ import annotations

import time
from collections.abc import Sequence

from speak_dropbox.backends.base import TrayBackend
from speak_dropbox.config import AppConfig
from speak_dropbox.core.classifier import (
    classify_sync_state,
    format_spoken_status,
    normalize_tooltip_text,
)
from speak_dropbox.core.local_adapters import enrich_bare_cloud_tooltip
from speak_dropbox.models import (
    ChangeType,
    MonitoredSourceStatus,
    SourceRule,
    StateChangeEvent,
    SyncState,
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
                enriched = enrich_bare_cloud_tooltip(cleaned or icon.cleaned_tooltip)
                normalized_icon = TrayIconItem(
                    raw_tooltip=icon.raw_tooltip,
                    cleaned_tooltip=enriched,
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
        if (
            rule.pinned_slot is not None
            and rule.pinned_slot >= 1
            and rule.pinned_slot not in taken_slots
        ):
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


class TrayMonitorService:
    """Polls a TrayBackend, maintains slot assignments, and emits debounced StateChangeEvents."""

    def __init__(self, backend: TrayBackend, config: AppConfig) -> None:
        self.backend = backend
        self.config = config
        self._active_slots: list[MonitoredSourceStatus] = []
        self._previous_by_id: dict[str, MonitoredSourceStatus] = {}
        self._unmonitored_icons: list[TrayIconItem] = []
        self._all_icons: list[TrayIconItem] = []
        self._has_polled_once: bool = False

    @property
    def has_polled_once(self) -> bool:
        return self._has_polled_once

    def get_active_slots(self) -> list[MonitoredSourceStatus]:
        """Return currently active monitored sources ordered by slot number."""
        return list(self._active_slots)

    def get_unmonitored_icons(self) -> list[TrayIconItem]:
        """Return discovered tray icons that do not currently match an enabled rule."""
        return list(self._unmonitored_icons)

    def get_all_discovered_icons(self) -> list[TrayIconItem]:
        """Return all discovered tray icons excluding Speak Dropbox itself."""
        return [
            item
            for item in self._all_icons
            if not is_ignored_or_self_icon(item, self.config.ignored_keywords)
        ]

    def get_slot_status(self, slot_number: int) -> MonitoredSourceStatus | None:
        """Look up the active monitored source assigned to 1-indexed slot_number."""
        for status in self._active_slots:
            if status.slot == slot_number:
                return status
        return None

    def has_active_transfer(self) -> bool:
        """Return True if any active monitored source is currently syncing or indexing."""
        return any(s.state.is_active_transfer for s in self._active_slots)

    def has_problem_state(self) -> bool:
        """Return True if any active monitored source is in an error or disconnected state."""
        return any(s.state.is_problem for s in self._active_slots)

    def format_slot_announcement(self, slot_number: int, *, refresh: bool = False) -> str:
        """Return the speech announcement string for a specific 1-indexed slot."""
        if refresh or not self._has_polled_once:
            self.poll()

        status = self.get_slot_status(slot_number)
        if status is not None:
            return status.spoken_text

        for rule in self.config.get_enabled_sources():
            if rule.pinned_slot == slot_number:
                return f"Slot {slot_number}, {rule.display_name}: Not running"

        if not self._active_slots:
            return f"Slot {slot_number}: No monitored cloud sources are currently running"

        return f"Slot {slot_number}: No source assigned"

    def format_summary_announcement(self, *, refresh: bool = False) -> str:
        """Return a combined speech summary for all active monitored sources."""
        if refresh or not self._has_polled_once:
            self.poll()

        if not self._active_slots:
            return "No monitored cloud sources found in the system tray."

        count = len(self._active_slots)
        header = "1 active source." if count == 1 else f"{count} active sources."
        items = [f"Slot {s.slot}, {s.spoken_text}." for s in self._active_slots]
        return f"{header} {' '.join(items)}"

    def format_tray_tooltip_summary(self) -> str:
        """Format a concise tooltip (<120 chars) for Speak Dropbox's own system tray icon."""
        if not self._active_slots:
            return "Speak Dropbox - No active sources detected"

        active_syncs = [s for s in self._active_slots if s.state.is_active_transfer]
        if active_syncs:
            names = ", ".join(s.display_name for s in active_syncs)
            return f"Speak Dropbox - Syncing: {names}"[:120]

        problems = [s for s in self._active_slots if s.state.is_problem]
        if problems:
            names = ", ".join(s.display_name for s in problems)
            return f"Speak Dropbox - Attention: {names}"[:120]

        count = len(self._active_slots)
        noun = "source" if count == 1 else "sources"
        return f"Speak Dropbox - {count} {noun} up to date"

    def should_speak_event(self, event: StateChangeEvent, *, is_initial_poll: bool = False) -> bool:
        """Evaluate whether a StateChangeEvent should be spoken aloud based on AppConfig."""
        if not self.config.enable_speech:
            return False

        if event.change_type == ChangeType.DETAIL_UPDATED:
            return False

        if event.change_type in (ChangeType.APPEARED, ChangeType.DISAPPEARED):
            if is_initial_poll and not self.config.speak_on_appear_disappear:
                return False
            return self.config.speak_on_appear_disappear

        if event.change_type == ChangeType.STATE_CHANGED:
            if event.new_state.is_active_transfer:
                return self.config.speak_on_start_sync
            if event.new_state == SyncState.IDLE:
                return self.config.speak_on_finish_sync
            if event.new_state in (SyncState.PAUSED, SyncState.ERROR, SyncState.DISCONNECTED):
                return self.config.speak_on_error_or_pause
            return True

        return False

    def poll(self) -> list[StateChangeEvent]:
        """Query the tray backend, update slots, and return any state transition events."""
        icons = self.backend.get_tray_icons(
            strip_unread_notifications=self.config.strip_unread_notifications
        )
        self._all_icons = list(icons)

        matched_pairs, unmatched = match_icons_to_rules(
            icons,
            self.config.sources,
            strip_unread_notifications=self.config.strip_unread_notifications,
            ignored_keywords=self.config.ignored_keywords,
        )
        self._unmonitored_icons = unmatched
        current_slots = assign_slots(matched_pairs)
        self._active_slots = current_slots

        current_by_id = {s.source_id: s for s in current_slots}
        events: list[StateChangeEvent] = []

        for source_id, status in current_by_id.items():
            prev = self._previous_by_id.get(source_id)
            if prev is None:
                events.append(
                    StateChangeEvent(
                        source_id=source_id,
                        display_name=status.display_name,
                        change_type=ChangeType.APPEARED,
                        previous_state=None,
                        new_state=status.state,
                        previous_tooltip="",
                        new_tooltip=status.cleaned_tooltip,
                        spoken_announcement=status.spoken_text,
                        location=status.location,
                    )
                )
            elif prev.state != status.state:
                events.append(
                    StateChangeEvent(
                        source_id=source_id,
                        display_name=status.display_name,
                        change_type=ChangeType.STATE_CHANGED,
                        previous_state=prev.state,
                        new_state=status.state,
                        previous_tooltip=prev.cleaned_tooltip,
                        new_tooltip=status.cleaned_tooltip,
                        spoken_announcement=status.spoken_text,
                        location=status.location,
                    )
                )
            elif prev.cleaned_tooltip != status.cleaned_tooltip:
                events.append(
                    StateChangeEvent(
                        source_id=source_id,
                        display_name=status.display_name,
                        change_type=ChangeType.DETAIL_UPDATED,
                        previous_state=prev.state,
                        new_state=status.state,
                        previous_tooltip=prev.cleaned_tooltip,
                        new_tooltip=status.cleaned_tooltip,
                        spoken_announcement=status.spoken_text,
                        location=status.location,
                    )
                )

        for source_id, prev in self._previous_by_id.items():
            if source_id not in current_by_id:
                events.append(
                    StateChangeEvent(
                        source_id=source_id,
                        display_name=prev.display_name,
                        change_type=ChangeType.DISAPPEARED,
                        previous_state=prev.state,
                        new_state=SyncState.DISCONNECTED,
                        previous_tooltip=prev.cleaned_tooltip,
                        new_tooltip="",
                        spoken_announcement=f"{prev.display_name}: Closed or removed from system tray",
                        location=prev.location,
                    )
                )

        self._previous_by_id = current_by_id
        self._has_polled_once = True
        return events
