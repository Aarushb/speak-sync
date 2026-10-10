"""Unit tests for local cloud sync folder resolution."""

from __future__ import annotations

import json
from pathlib import Path

from speak_dropbox.core.folders import (
    open_sync_folder,
    resolve_dropbox_folder,
    resolve_google_drive_folder,
    resolve_onedrive_folder,
    resolve_sync_folder,
)


def test_resolve_dropbox_folder_from_info_json(tmp_path: Path) -> None:
    appdata = tmp_path / "AppData"
    dropbox_cfg = appdata / "Dropbox"
    dropbox_cfg.mkdir(parents=True)
    sync_dir = tmp_path / "MyDropbox"
    sync_dir.mkdir()
    (dropbox_cfg / "info.json").write_text(
        json.dumps({"personal": {"path": str(sync_dir)}}),
        encoding="utf-8",
    )

    resolved = resolve_dropbox_folder(appdata_dir=appdata, home_dir=tmp_path)
    assert resolved == sync_dir


def test_resolve_onedrive_folder_from_env(tmp_path: Path) -> None:
    od_dir = tmp_path / "OneDrive - Org"
    od_dir.mkdir()
    resolved = resolve_onedrive_folder(
        env={"OneDriveCommercial": str(od_dir)},
        home_dir=tmp_path,
    )
    assert resolved == od_dir


def test_resolve_google_drive_folder_from_home(tmp_path: Path) -> None:
    gd_dir = tmp_path / "Google Drive"
    gd_dir.mkdir()
    resolved = resolve_google_drive_folder(home_dir=tmp_path)
    assert resolved == gd_dir


def test_resolve_sync_folder_across_providers(tmp_path: Path) -> None:
    (tmp_path / "Nextcloud").mkdir()
    (tmp_path / "Resilio Sync").mkdir()
    (tmp_path / "MEGA").mkdir()

    assert resolve_sync_folder("nextcloud", home_dir=tmp_path) == tmp_path / "Nextcloud"
    assert resolve_sync_folder("resilio_sync", home_dir=tmp_path) == tmp_path / "Resilio Sync"
    assert resolve_sync_folder("megasync", home_dir=tmp_path) == tmp_path / "MEGA"
    assert resolve_sync_folder("unknown_app", home_dir=tmp_path) is None


def test_open_sync_folder_returns_false_for_missing_path(tmp_path: Path) -> None:
    assert open_sync_folder(tmp_path / "does_not_exist") is False
