"""Shared pytest fixtures for headless wxPython UI and accessibility tests."""

from __future__ import annotations

import sys
from collections.abc import Generator
import pytest

if sys.platform == "win32":
    from speak_sync.backends.windows import ensure_default_desktop

    ensure_default_desktop()

import wx  # noqa: E402


@pytest.fixture(scope="session")
def wx_app() -> Generator[wx.App, None, None]:
    """Provide a shared wx.App instance for the test session."""
    if sys.platform == "win32":
        ensure_default_desktop()
    app = wx.App.Get()
    if app is None:
        app = wx.App(False)
    yield app
