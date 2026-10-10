"""Three-stage sync earcon audio cue service (start.flac -> loopty.flac -> finish.flac)."""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path

from speak_dropbox.config import AppConfig

logger = logging.getLogger(__name__)

try:
    import soundobj

    _SOUNDOBJ_AVAILABLE = True
except ImportError:
    soundobj = None
    _SOUNDOBJ_AVAILABLE = False


def get_assets_dir() -> Path:
    """Locate the bundled assets directory containing start.flac, loopty.flac, and finish.flac."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")) / "assets"

    # Package source tree: src/speak_dropbox/services/audio.py -> repo_root/assets
    repo_root = Path(__file__).resolve().parents[3]
    assets_dir = repo_root / "assets"
    if assets_dir.exists():
        return assets_dir
    return repo_root


def resolve_cue_file(custom_path: str, default_filename: str) -> Path | None:
    """Resolve a user-configured sound file or fall back to the bundled asset."""
    if custom_path and custom_path.strip():
        candidate = Path(custom_path.strip()).expanduser()
        if candidate.is_file():
            return candidate

    assets_dir = get_assets_dir()
    bundled = assets_dir / default_filename
    if bundled.is_file():
        return bundled

    fallback_root = Path(__file__).resolve().parents[3] / default_filename
    if fallback_root.is_file():
        return fallback_root

    return None


class AudioCueService:
    """Manages the three-stage sync audio state machine (start -> loopty -> finish)."""

    def __init__(
        self,
        config: AppConfig,
        *,
        player_fn: Callable[[Path], bool] | None = None,
    ) -> None:
        self.config = config
        self._player_fn = player_fn or self._default_play_file
        self._is_sync_active: bool = False
        self._last_cue_timestamp: float = 0.0
        self.played_history: list[str] = []

    @property
    def is_sync_active(self) -> bool:
        """Return True if the sustain sync loop state is currently active."""
        return self._is_sync_active

    @staticmethod
    def _default_play_file(sound_path: Path) -> bool:
        if not _SOUNDOBJ_AVAILABLE or soundobj is None:
            return False
        try:
            soundobj.play_sound(str(sound_path))
            return True
        except Exception as exc:
            logger.debug("soundobj.play_sound(%s) failed: %s", sound_path, exc)
            return False

    def _play_resolved(self, cue_name: str, custom_path: str, default_filename: str) -> bool:
        if not self.config.enable_sounds:
            return False
        path = resolve_cue_file(custom_path, default_filename)
        if path is None:
            logger.debug("Audio cue file %s not found.", default_filename)
            return False
        if self._player_fn(path):
            self.played_history.append(cue_name)
            return True
        return False

    def play_start(self) -> bool:
        """Play the sync start earcon (start.flac)."""
        return self._play_resolved("start", self.config.start_sound_path, "start.flac")

    def play_loop(self) -> bool:
        """Play the sync sustain loop earcon (loopty.flac)."""
        if not self.config.enable_loop_sound:
            return False
        return self._play_resolved("loop", self.config.loop_sound_path, "loopty.flac")

    def play_finish(self) -> bool:
        """Play the sync completion earcon (finish.flac)."""
        return self._play_resolved("finish", self.config.finish_sound_path, "finish.flac")

    def update_sync_activity(
        self,
        has_active_transfer: bool,
        *,
        now: float | None = None,
    ) -> str | None:
        """Advance the 3-stage audio state machine based on whether any source is actively syncing.

        Returns 'start', 'loop', 'finish', or None.
        """
        current_time = now if now is not None else time.monotonic()

        if has_active_transfer:
            if not self._is_sync_active:
                self._is_sync_active = True
                self._last_cue_timestamp = current_time
                if self.play_start():
                    return "start"
                return None

            elapsed = current_time - self._last_cue_timestamp
            if self.config.enable_loop_sound and elapsed >= self.config.loop_interval_seconds:
                self._last_cue_timestamp = current_time
                if self.play_loop():
                    return "loop"
            return None

        if self._is_sync_active:
            self._is_sync_active = False
            self._last_cue_timestamp = current_time
            if self.play_finish():
                return "finish"

        return None

    def reset(self) -> None:
        """Reset active sync loop state without playing a finish sound."""
        self._is_sync_active = False
        self._last_cue_timestamp = 0.0
