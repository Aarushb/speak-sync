"""CLI and GUI entrypoint for Speak Dropbox (`python -m speak_dropbox`)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from speak_dropbox import __version__
from speak_dropbox.backends import TrayBackend, create_tray_backend
from speak_dropbox.config import AppConfig
from speak_dropbox.core.monitor import TrayMonitorService
from speak_dropbox.services.speech import SpeechService


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="speak-dropbox",
        description=(
            "Accessible multi-source system tray and hidden overflow sync monitor "
            "with Prism screen reader speech, 3-stage sync audio cues, and global slot hotkeys."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"speak-dropbox {__version__}",
    )
    parser.add_argument(
        "-s",
        "--status",
        action="store_true",
        help="Query all active monitored sources once, speak and print their status, and exit.",
    )
    parser.add_argument(
        "--slot",
        type=int,
        choices=range(1, 10),
        metavar="1-9",
        help="Query a specific monitored slot (1-9) once, speak and print its status, and exit.",
    )
    parser.add_argument(
        "--list-tray",
        action="store_true",
        help="List all discovered visible and hidden overflow system tray icons and exit.",
    )
    parser.add_argument(
        "--manage",
        action="store_true",
        help="Open the Manage Sources & Settings dialog immediately on startup.",
    )
    parser.add_argument(
        "--no-speak",
        action="store_true",
        help="Suppress Prism screen reader output when running one-shot CLI queries.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a custom config.json file.",
    )
    return parser


def run_cli_one_shot(
    args: argparse.Namespace,
    *,
    backend: TrayBackend | None = None,
    speech: SpeechService | None = None,
) -> int:
    """Execute one-shot CLI inspection commands (--status, --slot, --list-tray)."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    config = AppConfig.load(args.config)
    active_backend = backend or create_tray_backend()
    monitor = TrayMonitorService(active_backend, config)

    try:
        monitor.poll()
        if args.list_tray:
            icons = monitor.get_all_discovered_icons()
            print(f"Backend: {active_backend.platform_name}")
            if not icons:
                print("No system tray icons discovered.")
                return 0
            for idx, item in enumerate(icons, 1):
                print(f"{idx}. [{item.location.display_label}] {item.cleaned_tooltip}")
            return 0

        if args.slot is not None:
            text = monitor.format_slot_announcement(args.slot, refresh=False)
            print(text)
            if not args.no_speak:
                svc = speech or SpeechService(enabled=True)
                svc.output(text, interrupt=True, force=True)
            return 0

        if args.status:
            summary = monitor.format_summary_announcement(refresh=False)
            print(summary)
            if not args.no_speak:
                svc = speech or SpeechService(enabled=True)
                svc.output(summary, interrupt=True, force=True)
            return 0
    finally:
        if backend is None:
            active_backend.close()

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.list_tray or args.status or args.slot is not None:
        return run_cli_one_shot(args)

    import wx
    from speak_dropbox.app import SpeakDropboxController

    app = wx.App(False)
    app.SetAppName("SpeakDropbox")
    controller = SpeakDropboxController(config_path=args.config)
    if args.manage:
        wx.CallAfter(controller.open_manage_dialog)
    app.MainLoop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
