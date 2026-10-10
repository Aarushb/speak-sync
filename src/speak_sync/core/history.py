"""Bounded activity log for recording timestamped cloud sync transitions."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

from speak_sync.models import ChangeType, StateChangeEvent, SyncState


@dataclass(frozen=True)
class SyncActivityEntry:
    """Single timestamped record in the sync activity history log."""

    timestamp_iso: str
    display_time: str
    source_id: str
    display_name: str
    change_type: ChangeType
    state: SyncState
    spoken_text: str

    def format_line(self) -> str:
        return f"[{self.display_time}] {self.display_name} ({self.state.display_label}): {self.spoken_text}"


class SyncActivityLog:
    """Bounded ring buffer storing recent StateChangeEvents in chronological order."""

    def __init__(self, max_entries: int = 100) -> None:
        self._max_entries = max(1, max_entries)
        self._entries: deque[SyncActivityEntry] = deque(maxlen=self._max_entries)

    def record(
        self,
        event: StateChangeEvent,
        *,
        now: datetime | None = None,
    ) -> SyncActivityEntry:
        """Record a StateChangeEvent into the ring buffer."""
        dt = now or datetime.now().astimezone()
        entry = SyncActivityEntry(
            timestamp_iso=dt.astimezone(timezone.utc).isoformat(),
            display_time=dt.strftime("%H:%M:%S"),
            source_id=event.source_id,
            display_name=event.display_name,
            change_type=event.change_type,
            state=event.new_state,
            spoken_text=event.spoken_announcement,
        )
        self._entries.append(entry)
        return entry

    def get_entries(self, *, newest_first: bool = True) -> list[SyncActivityEntry]:
        """Return recorded entries, newest-first by default for screen reader review."""
        items = list(self._entries)
        if newest_first:
            items.reverse()
        return items

    def clear(self) -> None:
        """Clear all recorded activity entries."""
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
