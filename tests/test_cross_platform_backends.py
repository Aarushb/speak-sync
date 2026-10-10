"""Unit tests for LinuxTrayBackend, MacOSTrayBackend, StaticTrayBackend, and create_tray_backend."""

from __future__ import annotations

from pathlib import Path

from speak_dropbox.backends import (
    LinuxTrayBackend,
    MacOSTrayBackend,
    StaticTrayBackend,
    WindowsTrayBackend,
    create_tray_backend,
)
from speak_dropbox.backends.linux import parse_sni_registered_items
from speak_dropbox.backends.macos import parse_macos_ax_menu_bar_lines
from speak_dropbox.models import TrayIconItem, TrayLocation


def test_create_tray_backend_factory() -> None:
    win = create_tray_backend("win32")
    assert isinstance(win, WindowsTrayBackend)
    win.close()

    mac = create_tray_backend("darwin")
    assert isinstance(mac, MacOSTrayBackend)

    lin = create_tray_backend("linux")
    assert isinstance(lin, LinuxTrayBackend)


def test_static_tray_backend() -> None:
    item = TrayIconItem(
        raw_tooltip="Dropbox - Up to date",
        cleaned_tooltip="Dropbox - Up to date",
        location=TrayLocation.VISIBLE,
    )
    backend = StaticTrayBackend([item])
    assert backend.platform_name == "StaticTestBackend"
    assert backend.get_tray_icons() == [item]


def test_parse_sni_registered_items_and_linux_backend(tmp_path: Path) -> None:
    watcher_output = (
        "(<[':1.84/org/ayatana/NotificationItem/dropbox_client_1', "
        "'org.kde.StatusNotifierItem-4120-1/StatusNotifierItem']>,)"
    )
    parsed = parse_sni_registered_items(watcher_output)
    assert parsed == [
        (":1.84", "/org/ayatana/NotificationItem/dropbox_client_1"),
        ("org.kde.StatusNotifierItem-4120-1", "/StatusNotifierItem"),
    ]

    def fake_runner(cmd: list[str]) -> str:
        if "RegisteredStatusNotifierItems" in cmd:
            return watcher_output
        if ":1.84" in cmd:
            return "({'Title': <'Dropbox'>, 'ToolTip': <'Syncing 3 files...'>},)"
        if "org.kde.StatusNotifierItem-4120-1" in cmd:
            return "({'Title': <'Nextcloud'>, 'ToolTip': <'All files are in sync'>},)"
        return ""

    backend = LinuxTrayBackend(
        command_runner=fake_runner,
        dropbox_socket_path=tmp_path / "nonexistent_socket",
    )
    icons = backend.get_tray_icons()
    assert len(icons) == 2
    assert icons[0].cleaned_tooltip == "Dropbox - Syncing 3 files..."
    assert icons[1].cleaned_tooltip == "Nextcloud - All files are in sync"


def test_macos_backend_and_ax_line_parser() -> None:
    sample_output = "\n".join(
        [
            "Dropbox|Dropbox|Dropbox 274.4.4841 - Up to date|missing value",
            "Google Drive|Google Drive|Google Drive - Syncing 2 of 5|missing value",
            "OneDrive|missing value|OneDrive - Personal - Up to date|",
        ]
    )
    parsed = parse_macos_ax_menu_bar_lines(sample_output)
    assert len(parsed) == 3
    assert "Dropbox 274.4.4841 - Up to date" in parsed[0].cleaned_tooltip
    assert "Google Drive - Syncing 2 of 5" in parsed[1].cleaned_tooltip
    assert "OneDrive - Personal - Up to date" in parsed[2].cleaned_tooltip

    backend = MacOSTrayBackend(command_runner=lambda _cmd: sample_output)
    assert len(backend.get_tray_icons()) == 3
