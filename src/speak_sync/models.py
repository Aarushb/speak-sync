"""Domain models, enums, and state transition events for Speak Dropbox."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TrayLocation(str, Enum):
    """Where a system tray icon was discovered."""

    VISIBLE = "visible"
    OVERFLOW = "overflow"
    LOCAL_IPC = "local_ipc"
    UNKNOWN = "unknown"

    @property
    def display_label(self) -> str:
        labels = {
            TrayLocation.VISIBLE: "Visible Tray",
            TrayLocation.OVERFLOW: "Hidden Tray",
            TrayLocation.LOCAL_IPC: "Background Service",
            TrayLocation.UNKNOWN: "System Tray",
        }
        return labels.get(self, "System Tray")


class SyncState(str, Enum):
    """Semantic synchronization state classified from a source's status text."""

    IDLE = "idle"
    SYNCING = "syncing"
    INDEXING = "indexing"
    PAUSED = "paused"
    ERROR = "error"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"

    @property
    def is_active_transfer(self) -> bool:
        """Return True if the source is actively transferring or indexing files."""
        return self in (SyncState.SYNCING, SyncState.INDEXING)

    @property
    def is_problem(self) -> bool:
        """Return True if the source is in an error or disconnected state."""
        return self in (SyncState.ERROR, SyncState.DISCONNECTED)

    @property
    def display_label(self) -> str:
        labels = {
            SyncState.IDLE: "Up to date",
            SyncState.SYNCING: "Syncing",
            SyncState.INDEXING: "Indexing",
            SyncState.PAUSED: "Paused",
            SyncState.ERROR: "Sync error",
            SyncState.DISCONNECTED: "Disconnected",
            SyncState.UNKNOWN: "Running",
        }
        return labels.get(self, "Running")


class ChangeType(str, Enum):
    """Type of change detected on a monitored source."""

    APPEARED = "appeared"
    DISAPPEARED = "disappeared"
    STATE_CHANGED = "state_changed"
    DETAIL_UPDATED = "detail_updated"


@dataclass(frozen=True)
class TrayIconItem:
    """Represents a single system tray icon discovered by an OS backend."""

    raw_tooltip: str
    cleaned_tooltip: str
    location: TrayLocation = TrayLocation.UNKNOWN
    process_name: str = ""
    automation_id: str = ""
    hwnd: int = 0


@dataclass
class SourceRule:
    """Configuration rule defining how to match and monitor a tray source."""

    id: str
    display_name: str
    keywords: list[str]
    enabled: bool = True
    pinned_slot: int | None = None
    builtin: bool = False

    def matches(self, text: str, process_name: str = "") -> bool:
        """Return True if any configured keyword matches the tooltip or process name."""
        if not self.enabled:
            return False
        haystack = f"{text} {process_name}".lower()
        return any(kw.lower() in haystack for kw in self.keywords if kw.strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "keywords": list(self.keywords),
            "enabled": self.enabled,
            "pinned_slot": self.pinned_slot,
            "builtin": self.builtin,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceRule:
        raw_keywords = data.get("keywords", [])
        if isinstance(raw_keywords, str):
            keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
        else:
            keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
        pinned = data.get("pinned_slot")
        pinned_int = int(pinned) if isinstance(pinned, (int, str)) and str(pinned).isdigit() else None
        return cls(
            id=str(data.get("id", "")).strip() or "custom_source",
            display_name=str(data.get("display_name", "Custom Source")).strip(),
            keywords=keywords or [str(data.get("display_name", "custom")).lower()],
            enabled=bool(data.get("enabled", True)),
            pinned_slot=pinned_int,
            builtin=bool(data.get("builtin", False)),
        )


@dataclass
class MonitoredSourceStatus:
    """Live runtime status of an active monitored source assigned to a slot."""

    source_id: str
    display_name: str
    slot: int
    raw_tooltip: str
    cleaned_tooltip: str
    spoken_text: str
    state: SyncState
    location: TrayLocation = TrayLocation.UNKNOWN
    last_updated: float = field(default_factory=time.time)


@dataclass(frozen=True)
class StateChangeEvent:
    """Emitted by the monitor when a source appears, disappears, or updates."""

    source_id: str
    display_name: str
    change_type: ChangeType
    previous_state: SyncState | None
    new_state: SyncState
    previous_tooltip: str
    new_tooltip: str
    spoken_announcement: str
    location: TrayLocation = TrayLocation.UNKNOWN

    @property
    def should_announce_speech(self) -> bool:
        """Only announce meaningful transitions by default, not intermediate progress ticks."""
        return self.change_type in (
            ChangeType.APPEARED,
            ChangeType.DISAPPEARED,
            ChangeType.STATE_CHANGED,
        )
