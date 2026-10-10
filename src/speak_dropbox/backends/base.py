"""Abstract protocol and deterministic mock implementation for OS system tray backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from speak_dropbox.models import TrayIconItem


class TrayBackend(ABC):
    """Protocol for platform-specific system tray and overflow icon discovery."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable name of the active platform backend."""

    @abstractmethod
    def get_tray_icons(self, *, strip_unread_notifications: bool = False) -> list[TrayIconItem]:
        """Return all currently discovered visible and hidden system tray icons."""

    def close(self) -> None:
        """Release any native handles or COM resources held by the backend."""


class StaticTrayBackend(TrayBackend):
    """In-memory tray backend for deterministic unit and integration testing."""

    def __init__(self, items: Sequence[TrayIconItem] | None = None) -> None:
        self._items: list[TrayIconItem] = list(items or [])

    @property
    def platform_name(self) -> str:
        return "StaticTestBackend"

    def set_items(self, items: Sequence[TrayIconItem]) -> None:
        self._items = list(items)

    def get_tray_icons(self, *, strip_unread_notifications: bool = False) -> list[TrayIconItem]:
        return list(self._items)
