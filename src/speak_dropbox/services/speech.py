"""Prism screen reader speech and refreshable braille output service."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import prism

    _PRISM_AVAILABLE = True
except ImportError:
    prism = None
    _PRISM_AVAILABLE = False


class SpeechService:
    """Routes speech and braille announcements directly to the active screen reader via Prism."""

    def __init__(self, *, enabled: bool = True, backend: Any = None) -> None:
        self.enabled: bool = enabled
        self._context: Any = None
        self._backend: Any = backend
        self.last_spoken_text: str = ""
        if self._backend is None:
            self._init_backend()

    def _init_backend(self) -> None:
        if not _PRISM_AVAILABLE or prism is None:
            logger.debug("prismatoid is not available; speech service running in no-op mode.")
            return
        try:
            self._context = prism.Context()
            self._backend = self._context.create_best()
        except Exception as exc:
            logger.warning("Failed to initialize Prism speech backend: %s", exc)
            self._backend = None

    @property
    def is_available(self) -> bool:
        return self._backend is not None

    @property
    def backend_name(self) -> str:
        if self._backend is None:
            return "Unavailable"
        return str(getattr(self._backend, "name", "Prism Active"))

    def speak(self, text: str, *, interrupt: bool = True, force: bool = False) -> bool:
        """Speak text aloud via the active screen reader."""
        if not text or not text.strip():
            return False
        if not self.enabled and not force:
            return False

        self.last_spoken_text = text.strip()
        if self._backend is None:
            self._init_backend()
        if self._backend is None:
            return False

        try:
            self._backend.speak(self.last_spoken_text, interrupt=interrupt)
            return True
        except Exception as exc:
            logger.debug("Prism speak() failed: %s", exc)
            return False

    def braille(self, text: str) -> bool:
        """Send text to a connected refreshable braille display via Prism."""
        if not text or not text.strip() or not self.enabled:
            return False
        if self._backend is None:
            return False
        try:
            if hasattr(self._backend, "braille"):
                self._backend.braille(text.strip())
                return True
        except Exception as exc:
            logger.debug("Prism braille() failed: %s", exc)
        return False

    def output(self, text: str, *, interrupt: bool = True, force: bool = False) -> bool:
        """Speak and braille text simultaneously via Prism."""
        if not text or not text.strip():
            return False
        if not self.enabled and not force:
            return False

        self.last_spoken_text = text.strip()
        if self._backend is None:
            self._init_backend()
        if self._backend is None:
            return False

        try:
            if hasattr(self._backend, "output"):
                self._backend.output(self.last_spoken_text, interrupt=interrupt)
                return True
            return self.speak(self.last_spoken_text, interrupt=interrupt, force=force)
        except Exception as exc:
            logger.debug("Prism output() failed: %s", exc)
            return False

    def stop(self) -> None:
        """Silence ongoing speech immediately."""
        if self._backend is None:
            return
        try:
            if hasattr(self._backend, "stop"):
                self._backend.stop()
        except Exception as exc:
            logger.debug("Prism stop() failed: %s", exc)
