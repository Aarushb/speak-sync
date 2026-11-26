"""Automatic background update checking, release asset resolution, and self-updating services."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from speak_sync import __version__

logger = logging.getLogger(__name__)

DEFAULT_REPO = "Aarushb/speak-sync"
GITHUB_LATEST_RELEASE_URL = f"https://api.github.com/repos/{DEFAULT_REPO}/releases/latest"


@dataclass
class UpdateInfo:
    """Metadata describing an available remote release."""

    tag_name: str
    version: str
    title: str
    release_notes: str
    html_url: str
    asset_name: str
    asset_download_url: str
    asset_size: int
    is_newer: bool
    is_portable: bool


def parse_version(version_str: str) -> tuple[int, ...]:
    """Extract numeric components from a version string (e.g., 'v0.1.2' -> (0, 1, 2))."""
    cleaned = version_str.strip().lstrip("vV")
    parts = re.findall(r"\d+", cleaned)
    if not parts:
        return (0, 0, 0)
    return tuple(int(p) for p in parts)


def is_version_newer(remote_version: str, local_version: str = __version__) -> bool:
    """Return True if the remote version tuple is strictly greater than the local version."""
    remote_tuple = parse_version(remote_version)
    local_tuple = parse_version(local_version)
    return remote_tuple > local_tuple


def is_portable_installation() -> bool:
    """Determine whether the current application is running in portable mode."""
    if not getattr(sys, "frozen", False):
        return True

    exe_dir = Path(sys.executable).resolve().parent
    # Check for Inno Setup uninstaller
    if (exe_dir / "unins000.exe").exists():
        return False

    # Check for installation in standard Program Files directories
    prog_files = os.environ.get("ProgramFiles", "C:\\Program Files").lower()
    prog_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)").lower()
    exe_str = str(exe_dir).lower()

    if exe_str.startswith(prog_files) or exe_str.startswith(prog_files_x86):
        return False

    return True


def resolve_matching_asset(
    assets: list[dict[str, Any]],
    *,
    platform: str = sys.platform,
    is_portable: bool | None = None,
) -> dict[str, Any] | None:
    """Select the appropriate release asset dictionary based on operating system and package type."""
    if is_portable is None:
        is_portable = is_portable_installation()

    if platform == "win32":
        target_pattern = "windows-portable.zip" if is_portable else "windows-setup.exe"
        fallback_pattern = "windows-setup.exe" if is_portable else "windows-portable.zip"
    elif platform == "darwin":
        target_pattern = "macos-installer.dmg"
        fallback_pattern = "macos-portable.zip"
    else:  # linux and others
        target_pattern = "linux-installer.deb"
        fallback_pattern = "linux-portable.tar.gz"

    # Search for target pattern
    for asset in assets:
        name = asset.get("name", "").lower()
        if target_pattern in name:
            return asset

    # Search for fallback pattern
    for asset in assets:
        name = asset.get("name", "").lower()
        if fallback_pattern in name:
            return asset

    return assets[0] if assets else None


def check_for_updates(
    current_version: str = __version__,
    *,
    api_url: str = GITHUB_LATEST_RELEASE_URL,
    timeout_seconds: float = 8.0,
    platform: str = sys.platform,
) -> UpdateInfo | None:
    """Query GitHub releases API and return UpdateInfo if a release is found."""
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": f"SpeakSync-Updater/{current_version}",
            "Accept": "application/vnd.github.v3+json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            if resp.status != 200:
                logger.debug("Update check returned status code %d", resp.status)
                return None
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.debug("Failed to check for updates against %s: %s", api_url, exc)
        return None

    tag_name = payload.get("tag_name", "")
    version_clean = tag_name.lstrip("vV")
    if not version_clean:
        return None

    is_newer = is_version_newer(version_clean, current_version)
    assets = payload.get("assets", [])
    portable_mode = is_portable_installation()
    selected_asset = resolve_matching_asset(assets, platform=platform, is_portable=portable_mode)

    asset_name = selected_asset.get("name", "") if selected_asset else ""
    asset_url = selected_asset.get("browser_download_url", "") if selected_asset else ""
    asset_size = selected_asset.get("size", 0) if selected_asset else 0

    return UpdateInfo(
        tag_name=tag_name,
        version=version_clean,
        title=payload.get("name", f"SpeakSync {tag_name}"),
        release_notes=payload.get("body", ""),
        html_url=payload.get("html_url", ""),
        asset_name=asset_name,
        asset_download_url=asset_url,
        asset_size=asset_size,
        is_newer=is_newer,
        is_portable=portable_mode,
    )


def download_update_asset(
    download_url: str,
    target_path: Path,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    cancel_flag: threading.Event | None = None,
    chunk_size: int = 65536,
    timeout_seconds: float = 30.0,
) -> bool:
    """Download a remote release asset to target_path with chunked progress reporting."""
    req = urllib.request.Request(
        download_url,
        headers={"User-Agent": f"SpeakSync-Updater/{__version__}"},
    )

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(target_path, "wb") as f_out:
                while True:
                    if cancel_flag is not None and cancel_flag.is_set():
                        logger.info("Download cancelled by user.")
                        return False
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f_out.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total_size)
        return True
    except Exception as exc:
        logger.exception("Failed to download update asset from %s: %s", download_url, exc)
        if target_path.exists():
            try:
                target_path.unlink()
            except OSError:
                pass
        return False


def apply_installer_update(installer_path: Path) -> bool:
    """Execute the Windows Inno Setup installer silently and instruct it to restart the app."""
    if not installer_path.is_file():
        logger.error("Installer file does not exist: %s", installer_path)
        return False

    try:
        # /SILENT runs the installer without prompting for wizard pages
        # /CLOSEAPPLICATIONS closes running instances
        # /RESTARTAPPLICATIONS relaunches the application when installation finishes
        args = [
            str(installer_path.resolve()),
            "/SILENT",
            "/CLOSEAPPLICATIONS",
            "/RESTARTAPPLICATIONS",
        ]
        subprocess.Popen(args, close_fds=True)
        return True
    except Exception as exc:
        logger.exception("Failed to spawn installer process: %s", exc)
        return False


def apply_portable_update(
    zip_path: Path,
    *,
    target_dir: Path | None = None,
    executable_path: Path | None = None,
) -> bool:
    """Unpack a portable update ZIP into staging and launch the detached batch replacement script."""
    if not zip_path.is_file():
        logger.error("Portable ZIP does not exist: %s", zip_path)
        return False

    app_exe = executable_path or (
        Path(sys.executable).resolve()
        if getattr(sys, "frozen", False)
        else Path(target_dir or ".").resolve() / "speaksync.exe"
    )
    app_dir = target_dir or app_exe.parent

    staging_dir = Path(tempfile.mkdtemp(prefix="speaksync_update_stage_"))

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(staging_dir)

        # Locate directory inside staging that contains the executable or payload
        source_dir = staging_dir
        if (staging_dir / "speaksync").is_dir():
            source_dir = staging_dir / "speaksync"
        elif list(staging_dir.glob("SpeakSync*")):
            dirs = [d for d in staging_dir.iterdir() if d.is_dir()]
            if len(dirs) == 1:
                source_dir = dirs[0]

        current_pid = os.getpid()
        script_path = Path(tempfile.gettempdir()) / f"speaksync_update_{current_pid}.bat"

        script_content = f"""@echo off
setlocal
set "PID={current_pid}"
set "STAGING={source_dir.resolve()}"
set "TARGET={app_dir.resolve()}"
set "EXE={app_exe.resolve()}"

set count=0
:wait_loop
tasklist /fi "PID eq %PID%" 2>nul | find "%PID%" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    set /a count+=1
    if %count% leq 30 goto wait_loop
)

robocopy "%STAGING%" "%TARGET%" /E /R:3 /W:1 /NJH /NJS /NFL /NDL >nul

start "" "%EXE%"

rmdir /s /q "{staging_dir.resolve()}" 2>nul
(goto) 2>nul & del "%~f0" 2>nul
"""
        script_path.write_text(script_content, encoding="utf-8")

        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000

        subprocess.Popen(
            ["cmd.exe", "/c", str(script_path)],
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
            close_fds=True,
        )
        return True
    except Exception as exc:
        logger.exception("Failed to prepare portable update script: %s", exc)
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        return False
