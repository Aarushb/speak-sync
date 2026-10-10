"""Configuration management, default cloud source rules, and atomic JSON persistence."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from speak_dropbox.models import SourceRule

logger = logging.getLogger(__name__)

APP_NAME = "speak_dropbox"


def default_source_rules() -> list[SourceRule]:
    """Return the built-in cloud synchronization source rules in default priority order."""
    return [
        SourceRule(
            id="dropbox",
            display_name="Dropbox",
            keywords=["dropbox"],
            enabled=True,
            builtin=True,
        ),
        SourceRule(
            id="google_drive",
            display_name="Google Drive",
            keywords=["google drive", "googledrivefs"],
            enabled=True,
            builtin=True,
        ),
        SourceRule(
            id="onedrive",
            display_name="OneDrive",
            keywords=["onedrive"],
            enabled=True,
            builtin=True,
        ),
        SourceRule(
            id="resilio_sync",
            display_name="Resilio Sync",
            keywords=["resilio sync", "resilio"],
            enabled=True,
            builtin=True,
        ),
        SourceRule(
            id="icloud",
            display_name="iCloud",
            keywords=["icloud"],
            enabled=True,
            builtin=True,
        ),
        SourceRule(
            id="nextcloud",
            display_name="Nextcloud",
            keywords=["nextcloud"],
            enabled=True,
            builtin=True,
        ),
        SourceRule(
            id="syncthing",
            display_name="Syncthing",
            keywords=["syncthing", "synctrayzor"],
            enabled=True,
            builtin=True,
        ),
        SourceRule(
            id="megasync",
            display_name="MEGAsync",
            keywords=["megasync"],
            enabled=True,
            builtin=True,
        ),
    ]


def get_default_config_dir() -> Path:
    """Return the platform-appropriate user configuration directory."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def get_default_config_path() -> Path:
    """Return the default path to config.json."""
    return get_default_config_dir() / "config.json"


@dataclass
class AppConfig:
    """Application settings and monitored source rules."""

    sources: list[SourceRule] = field(default_factory=default_source_rules)
    poll_interval_seconds: float = 1.5

    # Speech preferences
    enable_speech: bool = True
    speak_on_start_sync: bool = True
    speak_on_finish_sync: bool = True
    speak_on_error_or_pause: bool = True
    speak_on_appear_disappear: bool = False
    strip_unread_notifications: bool = False

    # Audio cue preferences (start.flac -> loopty.flac -> finish.flac)
    enable_sounds: bool = True
    enable_loop_sound: bool = True
    loop_interval_seconds: float = 2.6
    start_sound_path: str = ""
    loop_sound_path: str = ""
    finish_sound_path: str = ""

    # Global hotkey preferences
    hotkey_modifier: str = "Alt+Win"
    summary_hotkey: str = "Alt+Win+0"
    manage_hotkey: str = "Alt+Win+M"

    # OS startup
    run_on_startup: bool = False

    # Excluded raw tooltip prefixes if user explicitly hides an unknown source
    ignored_keywords: list[str] = field(default_factory=list)

    def get_enabled_sources(self) -> list[SourceRule]:
        """Return enabled source rules in their configured priority order."""
        return [s for s in self.sources if s.enabled]

    def get_source(self, source_id: str) -> SourceRule | None:
        """Look up a configured source rule by ID."""
        for rule in self.sources:
            if rule.id == source_id:
                return rule
        return None

    def add_or_update_source(self, rule: SourceRule) -> None:
        """Add a new source rule or update an existing rule with the same ID."""
        for idx, existing in enumerate(self.sources):
            if existing.id == rule.id:
                self.sources[idx] = rule
                return
        self.sources.append(rule)

    def remove_or_disable_source(self, source_id: str) -> bool:
        """Disable a built-in source rule or remove a custom source rule."""
        for idx, existing in enumerate(self.sources):
            if existing.id == source_id:
                if existing.builtin:
                    existing.enabled = False
                else:
                    self.sources.pop(idx)
                return True
        return False

    def move_source(self, source_id: str, delta: int) -> bool:
        """Move a source rule up (-1) or down (+1) in the priority list."""
        for idx, existing in enumerate(self.sources):
            if existing.id == source_id:
                new_idx = max(0, min(len(self.sources) - 1, idx + delta))
                if new_idx == idx:
                    return False
                item = self.sources.pop(idx)
                self.sources.insert(new_idx, item)
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": [s.to_dict() for s in self.sources],
            "poll_interval_seconds": self.poll_interval_seconds,
            "enable_speech": self.enable_speech,
            "speak_on_start_sync": self.speak_on_start_sync,
            "speak_on_finish_sync": self.speak_on_finish_sync,
            "speak_on_error_or_pause": self.speak_on_error_or_pause,
            "speak_on_appear_disappear": self.speak_on_appear_disappear,
            "strip_unread_notifications": self.strip_unread_notifications,
            "enable_sounds": self.enable_sounds,
            "enable_loop_sound": self.enable_loop_sound,
            "loop_interval_seconds": self.loop_interval_seconds,
            "start_sound_path": self.start_sound_path,
            "loop_sound_path": self.loop_sound_path,
            "finish_sound_path": self.finish_sound_path,
            "hotkey_modifier": self.hotkey_modifier,
            "summary_hotkey": self.summary_hotkey,
            "manage_hotkey": self.manage_hotkey,
            "run_on_startup": self.run_on_startup,
            "ignored_keywords": list(self.ignored_keywords),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        raw_sources = data.get("sources")
        if isinstance(raw_sources, list) and raw_sources:
            sources = [SourceRule.from_dict(item) for item in raw_sources if isinstance(item, dict)]
        else:
            sources = default_source_rules()

        poll_interval = float(data.get("poll_interval_seconds", 1.5))
        poll_interval = max(0.25, min(60.0, poll_interval))

        loop_interval = float(data.get("loop_interval_seconds", 2.6))
        loop_interval = max(0.5, min(60.0, loop_interval))

        return cls(
            sources=sources,
            poll_interval_seconds=poll_interval,
            enable_speech=bool(data.get("enable_speech", True)),
            speak_on_start_sync=bool(data.get("speak_on_start_sync", True)),
            speak_on_finish_sync=bool(data.get("speak_on_finish_sync", True)),
            speak_on_error_or_pause=bool(data.get("speak_on_error_or_pause", True)),
            speak_on_appear_disappear=bool(data.get("speak_on_appear_disappear", False)),
            strip_unread_notifications=bool(data.get("strip_unread_notifications", False)),
            enable_sounds=bool(data.get("enable_sounds", True)),
            enable_loop_sound=bool(data.get("enable_loop_sound", True)),
            loop_interval_seconds=loop_interval,
            start_sound_path=str(data.get("start_sound_path", "")),
            loop_sound_path=str(data.get("loop_sound_path", "")),
            finish_sound_path=str(data.get("finish_sound_path", "")),
            hotkey_modifier=str(data.get("hotkey_modifier", "Alt+Win")),
            summary_hotkey=str(data.get("summary_hotkey", "Alt+Win+0")),
            manage_hotkey=str(data.get("manage_hotkey", "Alt+Win+M")),
            run_on_startup=bool(data.get("run_on_startup", False)),
            ignored_keywords=[str(k) for k in data.get("ignored_keywords", []) if str(k).strip()],
        )

    def save(self, path: Path | None = None) -> Path:
        """Atomically persist configuration to disk as JSON."""
        target = path or get_default_config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_file = target.with_suffix(".json.tmp")
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        temp_file.write_text(payload, encoding="utf-8")
        temp_file.replace(target)
        return target

    @classmethod
    def load(cls, path: Path | None = None) -> AppConfig:
        """Load configuration from disk, returning defaults if missing or corrupt."""
        target = path or get_default_config_path()
        if not target.exists():
            return cls()
        try:
            raw = target.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return cls.from_dict(data)
        except Exception as exc:
            logger.warning("Failed to load config from %s: %s. Using defaults.", target, exc)
        return cls()
