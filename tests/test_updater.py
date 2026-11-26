"""Unit tests for automatic update checking, asset resolution, and installer launching."""

from __future__ import annotations

import io
import json
import threading
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import wx

from speak_sync.services.updater import (
    UpdateInfo,
    apply_installer_update,
    apply_portable_update,
    check_for_updates,
    download_update_asset,
    is_portable_installation,
    is_version_newer,
    parse_version,
    resolve_matching_asset,
)
from speak_sync.ui.update_dialog import UpdateDialog


def test_parse_version() -> None:
    assert parse_version("v0.1.2") == (0, 1, 2)
    assert parse_version("0.1.1") == (0, 1, 1)
    assert parse_version("v1.0.0") == (1, 0, 0)
    assert parse_version("invalid") == (0, 0, 0)


def test_is_version_newer() -> None:
    assert is_version_newer("0.1.2", "0.1.1") is True
    assert is_version_newer("0.2.0", "0.1.9") is True
    assert is_version_newer("1.0.0", "0.9.9") is True
    assert is_version_newer("0.1.1", "0.1.1") is False
    assert is_version_newer("0.1.0", "0.1.1") is False


def test_resolve_matching_asset_windows() -> None:
    mock_assets = [
        {"name": "SpeakSync-v0.1.2-windows-setup.exe", "browser_download_url": "https://example.com/setup.exe", "size": 100},
        {"name": "SpeakSync-v0.1.2-windows-portable.zip", "browser_download_url": "https://example.com/portable.zip", "size": 100},
        {"name": "SpeakSync-v0.1.2-macos-installer.dmg", "browser_download_url": "https://example.com/macos.dmg", "size": 100},
    ]

    portable = resolve_matching_asset(mock_assets, platform="win32", is_portable=True)
    assert portable is not None
    assert "portable.zip" in portable["name"]

    installer = resolve_matching_asset(mock_assets, platform="win32", is_portable=False)
    assert installer is not None
    assert "setup.exe" in installer["name"]


def test_resolve_matching_asset_unix() -> None:
    mock_assets = [
        {"name": "SpeakSync-v0.1.2-macos-installer.dmg", "browser_download_url": "https://example.com/mac.dmg", "size": 100},
        {"name": "SpeakSync-v0.1.2-linux-installer.deb", "browser_download_url": "https://example.com/linux.deb", "size": 100},
    ]

    mac_asset = resolve_matching_asset(mock_assets, platform="darwin")
    assert mac_asset is not None
    assert "macos-installer.dmg" in mac_asset["name"]

    linux_asset = resolve_matching_asset(mock_assets, platform="linux")
    assert linux_asset is not None
    assert "linux-installer.deb" in linux_asset["name"]


def test_check_for_updates_mock() -> None:
    payload = {
        "tag_name": "v0.1.2",
        "name": "SpeakSync v0.1.2",
        "body": "### 0.1.2\n- Test feature update",
        "html_url": "https://github.com/Aarushb/speak-sync/releases/tag/v0.1.2",
        "assets": [
            {
                "name": "SpeakSync-v0.1.2-windows-portable.zip",
                "browser_download_url": "https://example.com/download.zip",
                "size": 1024,
            }
        ],
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        info = check_for_updates(current_version="0.1.1", platform="win32")
        assert info is not None
        assert info.version == "0.1.2"
        assert info.is_newer is True
        assert "Test feature update" in info.release_notes
        assert info.asset_name == "SpeakSync-v0.1.2-windows-portable.zip"


def test_download_update_asset(tmp_path: Path) -> None:
    target_file = tmp_path / "test_download.zip"
    content = b"Mock zip binary content 1234567890"

    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Length": str(len(content))}
    mock_resp.read.side_effect = [content, b""]
    mock_resp.__enter__.return_value = mock_resp

    progress_calls: list[tuple[int, int]] = []

    def on_progress(down: int, total: int) -> None:
        progress_calls.append((down, total))

    with patch("urllib.request.urlopen", return_value=mock_resp):
        success = download_update_asset(
            "https://example.com/test.zip",
            target_file,
            progress_callback=on_progress,
        )
        assert success is True
        assert target_file.is_file()
        assert target_file.read_bytes() == content
        assert len(progress_calls) > 0


def test_apply_installer_update(tmp_path: Path) -> None:
    fake_installer = tmp_path / "setup.exe"
    fake_installer.write_bytes(b"mock setup")

    with patch("subprocess.Popen") as mock_popen:
        assert apply_installer_update(fake_installer) is True
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert "/SILENT" in args
        assert "/RESTARTAPPLICATIONS" in args


def test_apply_portable_update(tmp_path: Path) -> None:
    fake_zip = tmp_path / "portable.zip"
    with zipfile.ZipFile(fake_zip, "w") as zf:
        zf.writestr("speaksync/speaksync.exe", b"fake exe")
        zf.writestr("speaksync/data.txt", b"data")

    fake_app_dir = tmp_path / "app"
    fake_app_dir.mkdir()
    fake_exe = fake_app_dir / "speaksync.exe"
    fake_exe.touch()

    with patch("subprocess.Popen") as mock_popen:
        assert apply_portable_update(fake_zip, target_dir=fake_app_dir, executable_path=fake_exe) is True
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == "cmd.exe"
        assert call_args[1] == "/c"


def test_update_dialog_ui(wx_app: wx.App) -> None:
    info = UpdateInfo(
        tag_name="v0.1.2",
        version="0.1.2",
        title="SpeakSync v0.1.2",
        release_notes="### 0.1.2\n- Tested update note",
        html_url="https://github.com/Aarushb/speak-sync/releases/tag/v0.1.2",
        asset_name="SpeakSync-v0.1.2-windows-portable.zip",
        asset_download_url="https://example.com/download.zip",
        asset_size=1024,
        is_newer=True,
        is_portable=True,
    )

    dlg = UpdateDialog(None, info)
    try:
        assert "0.1.2" in dlg.GetTitle()
        assert "Tested update note" in dlg.notes_ctrl.GetValue()
        assert dlg.btn_install.IsEnabled()
    finally:
        dlg.Destroy()
