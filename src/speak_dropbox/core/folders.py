"""Local sync folder discovery and file manager launcher for monitored cloud providers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def resolve_dropbox_folder(
    *,
    appdata_dir: Path | None = None,
    local_appdata_dir: Path | None = None,
    home_dir: Path | None = None,
) -> Path | None:
    """Resolve the local Dropbox folder from info.json or standard home paths."""
    home = home_dir or Path.home()
    candidates: list[Path] = []
    if appdata_dir is not None:
        candidates.append(appdata_dir / "Dropbox" / "info.json")
    elif sys.platform == "win32":
        for env_key in ("APPDATA", "LOCALAPPDATA"):
            env_val = os.environ.get(env_key)
            if env_val:
                candidates.append(Path(env_val) / "Dropbox" / "info.json")
    if local_appdata_dir is not None:
        candidates.append(local_appdata_dir / "Dropbox" / "info.json")
    candidates.append(home / ".dropbox" / "info.json")

    for info_path in candidates:
        if info_path.is_file():
            try:
                data = json.loads(info_path.read_text(encoding="utf-8"))
                for account_type in ("personal", "business"):
                    acct = data.get(account_type)
                    if isinstance(acct, dict) and isinstance(acct.get("path"), str):
                        folder = Path(acct["path"])
                        if folder.is_dir():
                            return folder
            except Exception:
                continue

    fallback = home / "Dropbox"
    if fallback.is_dir():
        return fallback
    return None


def resolve_onedrive_folder(
    *,
    env: dict[str, str] | None = None,
    home_dir: Path | None = None,
) -> Path | None:
    """Resolve the local Microsoft OneDrive folder from environment variables or home directory."""
    environ = env if env is not None else dict(os.environ)
    for key in ("OneDriveConsumer", "OneDriveCommercial", "OneDrive"):
        val = environ.get(key)
        if val:
            candidate = Path(val)
            if candidate.is_dir():
                return candidate

    home = home_dir or Path.home()
    fallback = home / "OneDrive"
    if fallback.is_dir():
        return fallback
    return None


def resolve_google_drive_folder(*, home_dir: Path | None = None) -> Path | None:
    """Resolve the local Google Drive mount or folder path."""
    home = home_dir or Path.home()
    for sub in ("Google Drive", "My Drive"):
        candidate = home / sub
        if candidate.is_dir():
            return candidate

    if sys.platform == "win32":
        for letter in ("G", "H", "I", "J", "K"):
            my_drive = Path(f"{letter}:\\My Drive")
            if my_drive.is_dir():
                return my_drive
    elif sys.platform == "darwin":
        cloud_storage = home / "Library" / "CloudStorage"
        if cloud_storage.is_dir():
            for child in sorted(cloud_storage.iterdir()):
                if child.name.startswith("GoogleDrive") and child.is_dir():
                    return child
    return None


def resolve_sync_folder(
    source_id: str,
    display_name: str = "",
    *,
    home_dir: Path | None = None,
    appdata_dir: Path | None = None,
    env: dict[str, str] | None = None,
) -> Path | None:
    """Resolve the local sync folder for a monitored source ID or display name."""
    key = f"{source_id} {display_name}".lower()
    home = home_dir or Path.home()

    if "dropbox" in key:
        return resolve_dropbox_folder(appdata_dir=appdata_dir, home_dir=home)
    if "onedrive" in key:
        return resolve_onedrive_folder(env=env, home_dir=home)
    if "google_drive" in key or "google drive" in key:
        return resolve_google_drive_folder(home_dir=home)
    if "icloud" in key:
        for rel in (
            Path("iCloudDrive"),
            Path("Library/Mobile Documents/com~apple~CloudDocs"),
        ):
            candidate = home / rel
            if candidate.is_dir():
                return candidate
    if "nextcloud" in key:
        candidate = home / "Nextcloud"
        if candidate.is_dir():
            return candidate
    if "resilio" in key:
        for name in ("Resilio Sync", "Sync"):
            candidate = home / name
            if candidate.is_dir():
                return candidate
    if "syncthing" in key:
        candidate = home / "Sync"
        if candidate.is_dir():
            return candidate
    if "mega" in key:
        for name in ("MEGA", "MEGAsync Downloads"):
            candidate = home / name
            if candidate.is_dir():
                return candidate
    return None


def open_sync_folder(folder_path: Path) -> bool:
    """Open the given sync folder in the platform file manager."""
    if not folder_path.is_dir():
        return False
    try:
        if sys.platform == "win32":
            os.startfile(str(folder_path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder_path)])
        else:
            subprocess.Popen(["xdg-open", str(folder_path)])
        return True
    except Exception:
        return False
