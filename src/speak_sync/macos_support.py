"""macOS only helpers: VoiceOver labelling of the status item, a startup log file and state snapshots.

Everything here is a no-op on other platforms and never raises, so callers can use it unconditionally.
"""

from __future__ import annotations

import faulthandler
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

STATUS_WINDOW_LEVEL = 25
_log_stream = None


def macos_log_path() -> Path:
    """Return the path of the log file the tester can send back when something goes wrong."""
    return Path.home() / "Library" / "Logs" / "SpeakSync" / "speaksync.log"


def setup_macos_file_logging() -> Path | None:
    """Send all logging and hard crash tracebacks to the macOS log file; return its path or None."""
    global _log_stream
    if sys.platform != "darwin":
        return None
    try:
        path = macos_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _log_stream = open(path, "w", encoding="utf-8", buffering=1)
        logging.basicConfig(
            level=logging.INFO,
            stream=_log_stream,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            force=True,
        )
        # faulthandler covers segfaults and aborts that never reach a Python exception handler.
        faulthandler.enable(file=_log_stream, all_threads=True)
        return path
    except Exception:
        return None


def _status_bar_windows() -> list:
    """Return the NSStatusBarWindow objects of this process (empty list when AppKit is unavailable)."""
    import AppKit

    app = AppKit.NSApplication.sharedApplication()
    return [w for w in app.windows() if "StatusBar" in str(w.className())]


def _label_view(view, label: str, tree: list[str], depth: int = 0) -> bool:
    """Set the VoiceOver label and title on a view and its subviews; record class names in tree."""
    done = False
    tree.append("  " * depth + str(view.className()))
    for setter in ("setAccessibilityLabel_", "setAccessibilityTitle_"):
        try:
            getattr(view, setter)(label)
            done = True
        except Exception:
            pass
    for sub in view.subviews() or []:
        if _label_view(sub, label, tree, depth + 1):
            done = True
    return done


def label_status_item_for_voiceover(label: str = "SpeakSync") -> bool:
    """Give the menu bar status item a spoken name so VoiceOver does not announce an unnamed button."""
    if sys.platform != "darwin":
        return False
    try:
        labelled = False
        tree: list[str] = []
        for win in _status_bar_windows():
            content = win.contentView()
            if content is not None and _label_view(content, label, tree):
                labelled = True
        logger.info("Status item view tree: %s", " | ".join(tree))
        return labelled
    except Exception as exc:
        logger.debug("Could not label the status item: %s", exc)
        return False


def describe_status_item_state() -> str:
    """Return a one line snapshot of the activation policy and status item windows for the log."""
    if sys.platform != "darwin":
        return "not macOS"
    try:
        import AppKit

        app = AppKit.NSApplication.sharedApplication()
        windows = _status_bar_windows()
        details = ", ".join(
            f"level={w.level()} visible={w.isVisible()} x={w.frame().origin.x} y={w.frame().origin.y} "
            f"width={w.frame().size.width}"
            for w in windows
        )
        return (
            f"activationPolicy={app.activationPolicy()} running={app.isRunning()} "
            f"statusWindows={len(windows)} [{details}]"
        )
    except Exception as exc:
        return f"state unavailable: {exc}"


def describe_all_windows_and_screens() -> str:
    """Return every window this app owns and every screen frame, to identify stray windows and notch issues."""
    if sys.platform != "darwin":
        return "not macOS"
    try:
        import AppKit

        app = AppKit.NSApplication.sharedApplication()
        wins = [
            f"class={w.className()} title={w.title()!r} visible={w.isVisible()} level={w.level()} "
            f"alpha={w.alphaValue()} frame=({w.frame().origin.x},{w.frame().origin.y},"
            f"{w.frame().size.width},{w.frame().size.height})"
            for w in app.windows()
        ]
        screens = [
            f"({s.frame().origin.x},{s.frame().origin.y},{s.frame().size.width},{s.frame().size.height})"
            for s in AppKit.NSScreen.screens()
        ]
        return f"windows: {wins} screens: {screens}"
    except Exception as exc:
        return f"windows unavailable: {exc}"


def hide_host_window_from_users() -> bool:
    """Make the keep-alive frame invisible, click-through and unreachable by VoiceOver."""
    if sys.platform != "darwin":
        return False
    try:
        import AppKit

        hidden = False
        for win in AppKit.NSApplication.sharedApplication().windows():
            if str(win.title()) == "SpeakSyncHost":
                win.setAlphaValue_(0.0)
                win.setIgnoresMouseEvents_(True)
                win.setAccessibilityElement_(False)
                win.orderOut_(None)
                hidden = True
        return hidden
    except Exception as exc:
        logger.debug("Could not hide host window: %s", exc)
        return False
