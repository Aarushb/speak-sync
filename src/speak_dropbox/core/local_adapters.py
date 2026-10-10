"""Local log and telemetry enrichment for cloud clients that expose bare tray tooltips."""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_DRIVEFS_ACTIVITY_RE = re.compile(
    r"Sync engine activity state:\s*"
    r"operation_queue_size:\s*(\d+)\s*"
    r"all_downloads:\s*(\d+)\s*"
    r"change_ids_up_to_date:\s*(true|false)\s*"
    r"largest_local_change_id:\s*\d+\s*"
    r"fetching_changes:\s*(true|false)",
    re.IGNORECASE | re.MULTILINE,
)

_ONEDRIVE_UPLOAD_RE = re.compile(r"^FilesToUpload\s*=\s*(\d+)", re.IGNORECASE | re.MULTILINE)
_ONEDRIVE_DOWNLOAD_RE = re.compile(r"^FilesToDownload\s*=\s*(\d+)", re.IGNORECASE | re.MULTILINE)


def read_file_tail(path: Path, max_bytes: int = 16384) -> str:
    """Read up to the last max_bytes of a file as UTF-8 text without loading the entire file."""
    if not path.is_file():
        return ""
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
            data = fh.read(max_bytes)
        return data.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.debug("Failed to read tail of %s: %s", path, exc)
        return ""


def get_default_drivefs_log_path() -> Path | None:
    """Return the platform-specific path to Google DriveFS's drive_fs.txt log."""
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        base = Path(local_app) if local_app else (Path.home() / "AppData" / "Local")
        return base / "Google" / "DriveFS" / "Logs" / "drive_fs.txt"
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Google"
            / "DriveFS"
            / "Logs"
            / "drive_fs.txt"
        )
    return None


def parse_drivefs_log_tail(tail_text: str) -> str | None:
    """Parse the latest Sync engine activity state block from drive_fs.txt tail."""
    if not tail_text:
        return None
    matches = list(_DRIVEFS_ACTIVITY_RE.finditer(tail_text))
    if not matches:
        return None

    last = matches[-1]
    op_queue = int(last.group(1))
    downloads = int(last.group(2))
    fetching = last.group(4).lower() == "true"

    if downloads > 0 and op_queue > 0:
        return f"Google Drive - Syncing ({op_queue} queued, {downloads} downloading)"
    if downloads > 0:
        noun = "file" if downloads == 1 else "files"
        return f"Google Drive - Downloading {downloads} {noun}"
    if op_queue > 0:
        noun = "item" if op_queue == 1 else "items"
        return f"Google Drive - Syncing {op_queue} {noun}"
    if fetching:
        return "Google Drive - Checking for changes..."
    return "Google Drive - Everything is up to date"


def get_default_onedrive_diagnostics_path() -> Path | None:
    """Return the path to Microsoft OneDrive's SyncDiagnostics.log if present."""
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA")
        base = Path(local_app) if local_app else (Path.home() / "AppData" / "Local")
        personal = base / "Microsoft" / "OneDrive" / "logs" / "Personal" / "SyncDiagnostics.log"
        if personal.is_file():
            return personal
        business = base / "Microsoft" / "OneDrive" / "logs" / "Business1" / "SyncDiagnostics.log"
        if business.is_file():
            return business
    return None


def parse_onedrive_diagnostics_tail(tail_text: str) -> str | None:
    """Parse FilesToUpload and FilesToDownload from OneDrive SyncDiagnostics.log."""
    if not tail_text:
        return None
    up_match = _ONEDRIVE_UPLOAD_RE.search(tail_text)
    down_match = _ONEDRIVE_DOWNLOAD_RE.search(tail_text)
    if up_match is None and down_match is None:
        return None
    uploads = int(up_match.group(1)) if up_match else 0
    downloads = int(down_match.group(1)) if down_match else 0
    total = uploads + downloads
    if total > 0:
        noun = "file" if total == 1 else "files"
        return f"OneDrive - Syncing {total} {noun}"
    return "OneDrive - Up to date"


def enrich_bare_cloud_tooltip(
    cleaned_tooltip: str,
    *,
    drivefs_log_path: Path | None = None,
    onedrive_log_path: Path | None = None,
) -> str:
    """Enrich a bare tray tooltip (like 'Google Drive' or 'OneDrive') using local client logs."""
    stripped = cleaned_tooltip.strip()
    lower = stripped.lower()

    if lower == "google drive":
        log_path = drivefs_log_path or get_default_drivefs_log_path()
        if log_path is not None:
            enriched = parse_drivefs_log_tail(read_file_tail(log_path))
            if enriched:
                return enriched

    if lower in ("onedrive", "microsoft onedrive"):
        log_path = onedrive_log_path or get_default_onedrive_diagnostics_path()
        if log_path is not None:
            enriched = parse_onedrive_diagnostics_tail(read_file_tail(log_path))
            if enriched:
                return enriched

    return stripped
